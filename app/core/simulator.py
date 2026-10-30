"""Toolpath playback and step-by-step simulation state engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.models import MovementType, ToolpathMove


@dataclass
class SimulationState:
    """Instantaneous state of the simulated toolhead."""
    current_move_index: int = 0
    segment_progress: float = 0.0  # 0.0 to 1.0 within current move
    x: float = 0.0
    y: float = 0.0
    z: float = 18.0
    is_pen_down: bool = False
    move_type: MovementType = MovementType.TRAVEL
    current_gcode_command: str = "G90 ; Ready"
    current_gcode_line: int = 1
    elapsed_time_seconds: float = 0.0
    total_time_seconds: float = 0.0
    is_playing: bool = False
    playback_speed: float = 1.0


class ToolpathSimulator:
    """Animates the actual generated `ToolpathMove` sequence with time-accurate interpolation and stepping."""

    def __init__(self) -> None:
        self.moves: list[ToolpathMove] = []
        self._cumulative_times: list[float] = []
        self.state = SimulationState()

    def load_moves(self, moves: list[ToolpathMove], initial_z: float = 18.0) -> None:
        self.moves = list(moves)
        self._cumulative_times.clear()
        total = 0.0
        for mv in self.moves:
            total += mv.duration_seconds
            self._cumulative_times.append(total)

        self.state = SimulationState(
            current_move_index=0,
            segment_progress=0.0,
            x=self.moves[0].start_x if self.moves else 0.0,
            y=self.moves[0].start_y if self.moves else 0.0,
            z=self.moves[0].start_z if self.moves else initial_z,
            is_pen_down=False,
            move_type=self.moves[0].move_type if self.moves else MovementType.TRAVEL,
            current_gcode_command=self.moves[0].gcode_command if self.moves else "Ready",
            current_gcode_line=self.moves[0].gcode_line_number if self.moves else 1,
            elapsed_time_seconds=0.0,
            total_time_seconds=total,
            is_playing=False,
            playback_speed=self.state.playback_speed,
        )

    def restart(self) -> SimulationState:
        self.state.is_playing = False
        if not self.moves:
            return self.state
        self.seek_to_move(0, progress=0.0)
        return self.state

    def step_forward(self) -> SimulationState:
        if not self.moves:
            return self.state
        if self.state.current_move_index < len(self.moves) - 1:
            self.seek_to_move(self.state.current_move_index + 1, progress=1.0)
        else:
            self.seek_to_move(len(self.moves) - 1, progress=1.0)
            self.state.is_playing = False
        return self.state

    def step_backward(self) -> SimulationState:
        if not self.moves:
            return self.state
        target = max(0, self.state.current_move_index - 1)
        self.seek_to_move(target, progress=1.0 if target > 0 else 0.0)
        return self.state

    def seek_to_move(self, move_index: int, progress: float = 1.0) -> SimulationState:
        if not self.moves:
            return self.state

        idx = max(0, min(len(self.moves) - 1, int(move_index)))
        prog = max(0.0, min(1.0, float(progress)))
        mv = self.moves[idx]

        x = mv.start_x + (mv.end_x - mv.start_x) * prog
        y = mv.start_y + (mv.end_y - mv.start_y) * prog
        z = mv.start_z + (mv.end_z - mv.start_z) * prog

        is_down = mv.move_type == MovementType.DRAW or (
            mv.move_type == MovementType.PEN_DOWN and prog >= 0.8
        )

        prev_time = self._cumulative_times[idx - 1] if idx > 0 else 0.0
        elapsed = prev_time + mv.duration_seconds * prog

        self.state.current_move_index = idx
        self.state.segment_progress = prog
        self.state.x = x
        self.state.y = y
        self.state.z = z
        self.state.is_pen_down = is_down
        self.state.move_type = mv.move_type
        self.state.current_gcode_command = mv.gcode_command or f"{mv.move_type.value.upper()} -> ({x:.2f}, {y:.2f}, {z:.2f})"
        self.state.current_gcode_line = mv.gcode_line_number
        self.state.elapsed_time_seconds = elapsed
        return self.state

    def advance_time(self, dt_seconds: float) -> SimulationState:
        """Advances playback by `dt_seconds * playback_speed`."""
        if not self.moves or not self.state.is_playing:
            return self.state

        target_time = self.state.elapsed_time_seconds + dt_seconds * self.state.playback_speed
        if target_time >= self.state.total_time_seconds:
            self.seek_to_move(len(self.moves) - 1, progress=1.0)
            self.state.is_playing = False
            return self.state

        # Binary search in _cumulative_times
        lo = 0
        hi = len(self._cumulative_times) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self._cumulative_times[mid] < target_time:
                lo = mid + 1
            else:
                hi = mid

        idx = lo
        prev_time = self._cumulative_times[idx - 1] if idx > 0 else 0.0
        mv_dur = max(1e-6, self.moves[idx].duration_seconds)
        prog = (target_time - prev_time) / mv_dur
        return self.seek_to_move(idx, progress=prog)

    @property
    def overall_progress_ratio(self) -> float:
        if not self.moves:
            return 0.0
        if self.state.total_time_seconds <= 1e-6:
            return (self.state.current_move_index + self.state.segment_progress) / len(self.moves)
        return min(1.0, max(0.0, self.state.elapsed_time_seconds / self.state.total_time_seconds))
