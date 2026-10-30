"""Live Toolpath Simulator control bar with Play, Pause, Restart, Step, Speed, Coordinates, and G-Code readout."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.models import ToolpathMove
from app.core.simulator import SimulationState, ToolpathSimulator
from app.ui.icons import make_icon


class SimulatorControlBar(QFrame):
    """Bottom interactive playback bar for animating the generated movement trajectory."""

    simulation_updated = Signal(SimulationState, bool)
    inspect_gcode_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SimulatorBar")
        self.setFixedHeight(74)

        self.simulator = ToolpathSimulator()
        self._sim_active = False
        self._updating_slider = False

        self.timer = QTimer(self)
        self.timer.setInterval(33)  # ~30 FPS animation
        self.timer.timeout.connect(self._on_timer_tick)

        self._build_ui()

    def _build_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(10, 6, 10, 6)
        vbox.setSpacing(4)

        # Row 1: Transport Controls, Scrubber, Speed
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self.btn_restart = QToolButton(self)
        self.btn_restart.setIcon(make_icon("restart", size=15))
        self.btn_restart.setToolTip("Restart Simulation")
        self.btn_restart.clicked.connect(self.on_restart)
        row1.addWidget(self.btn_restart)

        self.btn_step_back = QToolButton(self)
        self.btn_step_back.setIcon(make_icon("step_back", size=15))
        self.btn_step_back.setToolTip("Step Backward One Movement")
        self.btn_step_back.clicked.connect(self.on_step_backward)
        row1.addWidget(self.btn_step_back)

        self.btn_play_pause = QPushButton("Simulate", self)
        self.btn_play_pause.setObjectName("PrimaryButton")
        self.btn_play_pause.setIcon(make_icon("play", "#09110B", size=14))
        self.btn_play_pause.setFixedWidth(98)
        self.btn_play_pause.clicked.connect(self.on_toggle_play)
        row1.addWidget(self.btn_play_pause)

        self.btn_step_fwd = QToolButton(self)
        self.btn_step_fwd.setIcon(make_icon("step_forward", size=15))
        self.btn_step_fwd.setToolTip("Step Forward One Movement")
        self.btn_step_fwd.clicked.connect(self.on_step_forward)
        row1.addWidget(self.btn_step_fwd)

        self.slider_progress = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_progress.setRange(0, 1000)
        self.slider_progress.setValue(0)
        self.slider_progress.valueChanged.connect(self._on_slider_scrubbed)
        row1.addWidget(self.slider_progress, 1)

        lbl_spd = QLabel("Speed:", self)
        lbl_spd.setObjectName("MutedLabel")
        row1.addWidget(lbl_spd)

        self.cmb_speed = QComboBox(self)
        for spd in (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0):
            self.cmb_speed.addItem(f"{spd:g}×", spd)
        self.cmb_speed.setCurrentIndex(2)  # 1x
        self.cmb_speed.currentIndexChanged.connect(self._on_speed_changed)
        row1.addWidget(self.cmb_speed)

        self.btn_exit_sim = QPushButton("Show Full Plot", self)
        self.btn_exit_sim.setToolTip("Exit progressive simulation overlay and display complete toolpath")
        self.btn_exit_sim.clicked.connect(self.on_exit_simulation_view)
        row1.addWidget(self.btn_exit_sim)

        vbox.addLayout(row1)

        # Row 2: Live X/Y/Z Readout, Pen State Pill, and Current G-code Command
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        self.lbl_pen_state = QLabel("PEN UP", self)
        self.lbl_pen_state.setStyleSheet(
            "background-color: rgba(56, 189, 248, 0.16); color: #38BDF8; "
            "border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 3px; padding: 1px 8px; font-weight: 700;"
        )
        row2.addWidget(self.lbl_pen_state)

        self.lbl_xyz = QLabel("X:   0.00 mm   Y:   0.00 mm   Z:  18.00 mm", self)
        self.lbl_xyz.setObjectName("MonoValueLabel")
        row2.addWidget(self.lbl_xyz)

        self.lbl_step_info = QLabel("Move: 0 / 0  (00:00 / 00:00)", self)
        self.lbl_step_info.setObjectName("MutedLabel")
        row2.addWidget(self.lbl_step_info)

        self.lbl_gcode_cmd = QLabel("G90 ; Ready to simulate", self)
        self.lbl_gcode_cmd.setObjectName("MonoValueLabel")
        self.lbl_gcode_cmd.setStyleSheet("color: #4ADE80; background-color: #121519; padding: 2px 8px; border-radius: 3px;")
        row2.addWidget(self.lbl_gcode_cmd, 1)

        btn_view_gcode = QPushButton("G-Code Viewer", self)
        btn_view_gcode.setFixedHeight(22)
        btn_view_gcode.clicked.connect(self.inspect_gcode_requested.emit)
        row2.addWidget(btn_view_gcode)

        vbox.addLayout(row2)

    def load_moves(self, moves: list[ToolpathMove], initial_z: float = 18.0) -> None:
        self.timer.stop()
        self._sim_active = False
        self.simulator.load_moves(moves, initial_z=initial_z)
        self.slider_progress.setRange(0, max(1, len(moves) - 1))
        self._sync_ui_from_state()

    def on_toggle_play(self) -> None:
        if not self.simulator.moves:
            return
        self._sim_active = True
        if self.simulator.state.is_playing:
            self.simulator.state.is_playing = False
            self.timer.stop()
        else:
            if self.simulator.overall_progress_ratio >= 0.999:
                self.simulator.restart()
            self.simulator.state.is_playing = True
            self.timer.start()
        self._sync_ui_from_state()
        self.simulation_updated.emit(self.simulator.state, self._sim_active)

    def on_restart(self) -> None:
        self.timer.stop()
        self._sim_active = True
        self.simulator.restart()
        self._sync_ui_from_state()
        self.simulation_updated.emit(self.simulator.state, self._sim_active)

    def on_step_forward(self) -> None:
        self.timer.stop()
        self.simulator.state.is_playing = False
        self._sim_active = True
        self.simulator.step_forward()
        self._sync_ui_from_state()
        self.simulation_updated.emit(self.simulator.state, self._sim_active)

    def on_step_backward(self) -> None:
        self.timer.stop()
        self.simulator.state.is_playing = False
        self._sim_active = True
        self.simulator.step_backward()
        self._sync_ui_from_state()
        self.simulation_updated.emit(self.simulator.state, self._sim_active)

    def on_exit_simulation_view(self) -> None:
        self.timer.stop()
        self.simulator.state.is_playing = False
        self._sim_active = False
        self._sync_ui_from_state()
        self.simulation_updated.emit(self.simulator.state, False)

    def _on_slider_scrubbed(self, val: int) -> None:
        if self._updating_slider or not self.simulator.moves:
            return
        self.timer.stop()
        self.simulator.state.is_playing = False
        self._sim_active = True
        self.simulator.seek_to_move(val, progress=1.0)
        self._sync_ui_from_state()
        self.simulation_updated.emit(self.simulator.state, self._sim_active)

    def _on_speed_changed(self) -> None:
        spd = float(self.cmb_speed.currentData() or 1.0)
        self.simulator.state.playback_speed = spd

    def _on_timer_tick(self) -> None:
        st = self.simulator.advance_time(0.033)
        if not st.is_playing:
            self.timer.stop()
        self._sync_ui_from_state()
        self.simulation_updated.emit(st, self._sim_active)

    def _sync_ui_from_state(self) -> None:
        st = self.simulator.state
        if st.is_playing:
            self.btn_play_pause.setText("Pause")
            self.btn_play_pause.setIcon(make_icon("pause", "#09110B", size=14))
        else:
            self.btn_play_pause.setText("Simulate")
            self.btn_play_pause.setIcon(make_icon("play", "#09110B", size=14))

        self._updating_slider = True
        self.slider_progress.setValue(st.current_move_index)
        self._updating_slider = False

        if st.is_pen_down:
            self.lbl_pen_state.setText("PEN DOWN (DRAW)")
            self.lbl_pen_state.setStyleSheet(
                "background-color: rgba(34, 197, 94, 0.22); color: #4ADE80; "
                "border: 1px solid #22C55E; border-radius: 3px; padding: 1px 8px; font-weight: 700;"
            )
        else:
            self.lbl_pen_state.setText("PEN UP (TRAVEL)")
            self.lbl_pen_state.setStyleSheet(
                "background-color: rgba(56, 189, 248, 0.16); color: #38BDF8; "
                "border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 3px; padding: 1px 8px; font-weight: 700;"
            )

        self.lbl_xyz.setText(f"X: {st.x:6.2f} mm   Y: {st.y:6.2f} mm   Z: {st.z:6.2f} mm")

        total_moves = len(self.simulator.moves)
        e_min, e_sec = divmod(int(round(st.elapsed_time_seconds)), 60)
        t_min, t_sec = divmod(int(round(st.total_time_seconds)), 60)
        self.lbl_step_info.setText(
            f"Move: {st.current_move_index + (1 if total_moves else 0)} / {total_moves}  "
            f"({e_min:02d}:{e_sec:02d} / {t_min:02d}:{t_sec:02d})"
        )
        self.lbl_gcode_cmd.setText(f"[Line {st.current_gcode_line}]  {st.current_gcode_command}")
