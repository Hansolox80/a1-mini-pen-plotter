"""Bambu Lab A1 Mini hardware profile definitions and G-code workflow templates."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


# Default startup G-code for Standard Generic Plotter Mode
DEFAULT_STANDARD_START_GCODE = """; === A1 Mini Pen Plotter - Standard Plotter G-code ===
; Mode: Generic 2D Plotter G-code (No firmware-specific macros, pure cold plotting)
; WARNING: Verify Z-heights and physical clearances before execution.
G21 ; Set units to millimeters
G90 ; Use absolute positioning
G0 Z{safe_z:.3f} F{z_feed:.0f} ; Lift to safe Z height
"""

DEFAULT_STANDARD_END_GCODE = """; === End of Plot ===
G0 Z{safe_z:.3f} F{z_feed:.0f} ; Lift pen to safe clearance height
G0 X{park_x:.2f} Y{park_y:.2f} F{travel_feed:.0f} ; Present build plate / park head
M84 ; Disable steppers
"""

# Default startup G-code for Bambu Lab A1 Mini Direct SD Card Plotting
DEFAULT_A1_MINI_SD_START_GCODE = """; === Bambu Lab A1 Mini - Cold Pen Plotting Start Sequence ===
; Workflow: Direct MicroSD Card Execution (Root Directory)
; Physical Safety Notice:
; - Ensure filament is unloaded and pen mount is securely attached.
; - Heater commands are explicitly forced to 0C (Cold Mode).
; - Nozzle wipe and resonance vibration macros are omitted to protect the pen tip.
M220 S100 ; Reset feedrate magnitude to 100%
M221 S100 ; Reset flowrate magnitude to 100%
G21 ; Metric values (mm)
G90 ; Absolute positioning
M83 ; Relative extruder mode (extruder stays inactive)
M104 S0 ; Force hotend temperature to 0C (Cold safety)
M140 S0 ; Force bed temperature to 0C (Cold safety)
M106 S0 ; Turn off part cooling fan
G28 ; Home X, Y, Z axes safely
G0 Z{safe_z:.3f} F{z_feed:.0f} ; Immediately raise to safe Z clearance
"""

DEFAULT_A1_MINI_SD_END_GCODE = """; === Bambu Lab A1 Mini - Cold Pen Plotting End Sequence ===
G0 Z{safe_z:.3f} F{z_feed:.0f} ; Lift pen to safe Z clearance
G0 X{park_x:.2f} Y{park_y:.2f} F{travel_feed:.0f} ; Move bed forward to present drawing
M104 S0 ; Confirm hotend OFF
M140 S0 ; Confirm bed OFF
M106 S0 ; Confirm fan OFF
M84 ; Disable motors
"""


@dataclass
class MachineProfile:
    """Configurable machine geometry, speed limits, and offset parameters."""
    id: str = "bambu_a1_mini"
    name: str = "Bambu Lab A1 Mini"
    manufacturer: str = "Bambu Lab"
    model: str = "A1 Mini"
    # Nominal build volume (mm)
    nominal_x_mm: float = 180.0
    nominal_y_mm: float = 180.0
    nominal_z_mm: float = 180.0
    # Safety margins restricting usable plotting area (mm from build plate edges)
    margin_left_mm: float = 15.0
    margin_right_mm: float = 15.0
    margin_front_mm: float = 15.0
    margin_back_mm: float = 15.0
    # Origin & global coordinate offsets
    origin_position: str = "front_left"  # "front_left", "center", "back_left"
    coord_offset_x_mm: float = 0.0
    coord_offset_y_mm: float = 0.0
    # Physical pen holder bracket offset relative to nozzle (mm)
    pen_holder_offset_x_mm: float = 0.0
    pen_holder_offset_y_mm: float = -22.0
    # Speed & Z safety limits
    max_travel_speed_mm_s: float = 200.0
    max_draw_speed_mm_s: float = 80.0
    max_z_speed_mm_s: float = 25.0
    safe_z_mm: float = 22.0
    min_safe_z_mm: float = 0.5
    max_safe_z_mm: float = 160.0
    park_x_mm: float = 0.0
    park_y_mm: float = 170.0
    # G-code templates
    start_gcode_standard: str = DEFAULT_STANDARD_START_GCODE
    end_gcode_standard: str = DEFAULT_STANDARD_END_GCODE
    start_gcode_bambu_sd: str = DEFAULT_A1_MINI_SD_START_GCODE
    end_gcode_bambu_sd: str = DEFAULT_A1_MINI_SD_END_GCODE
    is_builtin: bool = True

    @property
    def usable_min_x(self) -> float:
        return max(0.0, self.margin_left_mm)

    @property
    def usable_max_x(self) -> float:
        return max(self.usable_min_x, self.nominal_x_mm - self.margin_right_mm)

    @property
    def usable_min_y(self) -> float:
        return max(0.0, self.margin_front_mm)

    @property
    def usable_max_y(self) -> float:
        return max(self.usable_min_y, self.nominal_y_mm - self.margin_back_mm)

    @property
    def usable_width_mm(self) -> float:
        return max(0.0, self.usable_max_x - self.usable_min_x)

    @property
    def usable_height_mm(self) -> float:
        return max(0.0, self.usable_max_y - self.usable_min_y)

    @property
    def effective_usable_min_x(self) -> float:
        """Strict soft stop considering margins and pen holder bracket offset relative to carriage [0..nominal]."""
        return max(self.usable_min_x, self.pen_holder_offset_x_mm)

    @property
    def effective_usable_max_x(self) -> float:
        """Strict soft stop considering margins and pen holder bracket offset relative to carriage [0..nominal]."""
        return min(self.usable_max_x, self.nominal_x_mm + self.pen_holder_offset_x_mm)

    @property
    def effective_usable_min_y(self) -> float:
        """Strict soft stop considering margins and pen holder bracket offset relative to carriage [0..nominal]."""
        return max(self.usable_min_y, self.pen_holder_offset_y_mm)

    @property
    def effective_usable_max_y(self) -> float:
        """Strict soft stop considering margins and pen holder bracket offset relative to carriage [0..nominal]."""
        return min(self.usable_max_y, self.nominal_y_mm + self.pen_holder_offset_y_mm)

    @property
    def effective_usable_width_mm(self) -> float:
        return max(0.0, self.effective_usable_max_x - self.effective_usable_min_x)

    @property
    def effective_usable_height_mm(self) -> float:
        return max(0.0, self.effective_usable_max_y - self.effective_usable_min_y)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MachineProfile:
        return cls(
            id=str(data.get("id", "bambu_a1_mini")),
            name=str(data.get("name", "Bambu Lab A1 Mini")),
            manufacturer=str(data.get("manufacturer", "Bambu Lab")),
            model=str(data.get("model", "A1 Mini")),
            nominal_x_mm=float(data.get("nominal_x_mm", 180.0)),
            nominal_y_mm=float(data.get("nominal_y_mm", 180.0)),
            nominal_z_mm=float(data.get("nominal_z_mm", 180.0)),
            margin_left_mm=float(data.get("margin_left_mm", 15.0)),
            margin_right_mm=float(data.get("margin_right_mm", 15.0)),
            margin_front_mm=float(data.get("margin_front_mm", 15.0)),
            margin_back_mm=float(data.get("margin_back_mm", 15.0)),
            origin_position=str(data.get("origin_position", "front_left")),
            coord_offset_x_mm=float(data.get("coord_offset_x_mm", 0.0)),
            coord_offset_y_mm=float(data.get("coord_offset_y_mm", 0.0)),
            pen_holder_offset_x_mm=float(data.get("pen_holder_offset_x_mm", 0.0)),
            pen_holder_offset_y_mm=float(data.get("pen_holder_offset_y_mm", -22.0)),
            max_travel_speed_mm_s=float(data.get("max_travel_speed_mm_s", 200.0)),
            max_draw_speed_mm_s=float(data.get("max_draw_speed_mm_s", 80.0)),
            max_z_speed_mm_s=float(data.get("max_z_speed_mm_s", 25.0)),
            safe_z_mm=float(data.get("safe_z_mm", 22.0)),
            min_safe_z_mm=float(data.get("min_safe_z_mm", 0.5)),
            max_safe_z_mm=float(data.get("max_safe_z_mm", 160.0)),
            park_x_mm=float(data.get("park_x_mm", 0.0)),
            park_y_mm=float(data.get("park_y_mm", 170.0)),
            start_gcode_standard=str(data.get("start_gcode_standard", DEFAULT_STANDARD_START_GCODE)),
            end_gcode_standard=str(data.get("end_gcode_standard", DEFAULT_STANDARD_END_GCODE)),
            start_gcode_bambu_sd=str(data.get("start_gcode_bambu_sd", DEFAULT_A1_MINI_SD_START_GCODE)),
            end_gcode_bambu_sd=str(data.get("end_gcode_bambu_sd", DEFAULT_A1_MINI_SD_END_GCODE)),
            is_builtin=bool(data.get("is_builtin", False)),
        )


def create_default_a1_mini_profile() -> MachineProfile:
    """Returns the factory default Bambu Lab A1 Mini machine profile."""
    return MachineProfile()
