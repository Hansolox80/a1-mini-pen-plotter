"""Mandatory physical and G-code safety validation system for the A1 Mini Pen Plotter."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import math
import re
from typing import Any, Optional

from app.core.models import MovementType, ToolpathMove
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile


class ValidationSeverity(str, Enum):
    """Classification of safety validation findings."""
    VALID = "valid"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """Single validation finding with exact coordinates and responsible G-code command."""
    severity: ValidationSeverity
    code: str
    title: str
    message: str
    line_number: Optional[int] = None
    command: str = ""
    coordinates: Optional[tuple[float, float, float]] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class SafetyValidationReport:
    """Comprehensive validation report for a generated toolpath and G-code program."""
    overall_status: ValidationSeverity = ValidationSeverity.VALID
    can_export_executable: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    collision_risk_warnings: list[str] = field(default_factory=list)
    checked_movements: int = 0
    checked_gcode_lines: int = 0
    min_x_found: float = 0.0
    max_x_found: float = 0.0
    min_y_found: float = 0.0
    max_y_found: float = 0.0
    min_z_found: float = 0.0
    max_z_found: float = 0.0
    disclaimer: str = (
        "IMPORTANT SAFETY NOTICE: Software validation verifies coordinate bounds, feed rates, "
        "and command syntax, but CANNOT guarantee physical collision prevention. Always verify "
        "pen holder clearance, nozzle height relative to the pen tip, bed surface obstacles, "
        "and Z contact calibration manually before running on the Bambu Lab A1 Mini."
    )

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "can_export_executable": self.can_export_executable,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "checked_movements": self.checked_movements,
            "checked_gcode_lines": self.checked_gcode_lines,
            "bounds": {
                "min_x": round(self.min_x_found, 3),
                "max_x": round(self.max_x_found, 3),
                "min_y": round(self.min_y_found, 3),
                "max_y": round(self.max_y_found, 3),
                "min_z": round(self.min_z_found, 3),
                "max_z": round(self.max_z_found, 3),
            },
            "collision_risk_warnings": self.collision_risk_warnings,
            "disclaimer": self.disclaimer,
            "issues": [i.to_dict() for i in self.issues],
        }


# Supported G/M commands for pen plotting
ALLOWED_GCODE_COMMANDS = {
    "G0", "G00",
    "G1", "G01",
    "G4", "G04",    # Dwell (pen stabilization)
    "G21",          # Metric units (mm)
    "G28",          # Home axes
    "G90",          # Absolute positioning
    "M82", "M83",   # Extruder mode (harmless setup)
    "M84", "M18",   # Disable steppers
    "M104",         # Set hotend temp (ONLY allowed with S0)
    "M140",         # Set bed temp (ONLY allowed with S0)
    "M106", "M107", # Fan control
    "M220", "M221", # Speed/flow override reset
    "M400",         # Wait for moves to finish
}

# Explicitly prohibited or dangerous commands for pen plotting
FORBIDDEN_GCODE_COMMANDS = {
    "G20": "Inch unit mode (G20) is prohibited; A1 Mini Pen Plotter requires millimeter mode (G21).",
    "G91": "Relative positioning (G91) is prohibited in plotting trajectories; use G90 absolute coordinates.",
    "G29": "Automatic bed leveling (G29) with a pen mounted risks crashing the pen tip into the build plate.",
    "G29.1": "Bambu Z-offset probing (G29.1) is unsafe with a physical pen installed.",
    "G29.2": "Bambu ABL state macro (G29.2) is unverified for pen plotting.",
    "M109": "Wait-for-hotend-heating (M109) is prohibited for cold pen plotting.",
    "M190": "Wait-for-bed-heating (M190) is prohibited for cold pen plotting.",
    "M1002": "Proprietary Bambu system macro (M1002) may trigger nozzle wiping or resonance vibration.",
    "M620": "Bambu AMS filament switch command (M620) is prohibited in pen plotting mode.",
    "M621": "Bambu AMS filament commit command (M621) is prohibited in pen plotting mode.",
}


class SafetyValidator:
    """Validates toolpath movements and generated G-code against machine and pen constraints."""

    def __init__(self, machine: MachineProfile, pen: PenProfile) -> None:
        self.machine = machine
        self.pen = pen

    def validate(
        self,
        moves: list[ToolpathMove],
        gcode_text: str = "",
    ) -> SafetyValidationReport:
        report = SafetyValidationReport()
        report.checked_movements = len(moves)

        # 1. Populate mandatory physical collision-risk warnings
        self._build_collision_risk_warnings(report)

        # 2. Validate Pen & Machine static configuration
        self._validate_configuration(report)

        # 3. Validate movement trajectory
        if not moves:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="EMPTY_TOOLPATH",
                    title="No Toolpath Movements Generated",
                    message="The current project contains no drawable toolpath movements.",
                )
            )
        else:
            self._validate_moves(moves, report)

        # 4. Validate raw G-code text if provided
        if gcode_text.strip():
            self._validate_gcode_lines(gcode_text, report)

        # 5. Compute overall status
        if any(i.severity == ValidationSeverity.CRITICAL for i in report.issues):
            report.overall_status = ValidationSeverity.CRITICAL
            report.can_export_executable = False
        elif any(i.severity == ValidationSeverity.WARNING for i in report.issues):
            report.overall_status = ValidationSeverity.WARNING
            report.can_export_executable = True
        else:
            report.overall_status = ValidationSeverity.VALID
            report.can_export_executable = True

        return report

    def _build_collision_risk_warnings(self, report: SafetyValidationReport) -> None:
        report.collision_risk_warnings.append(
            "Software validation checks numeric coordinates only and cannot detect physical obstructions "
            "(such as binder clips, raised tape edges, warped paper, or an improperly seated pen holder)."
        )
        if not self.pen.is_calibrated:
            report.collision_risk_warnings.append(
                f"Pen profile '{self.pen.name}' has not been marked as calibrated via the Calibration Wizard. "
                f"Verify that Drawing Z ({self.pen.drawing_z_mm:.2f} mm) matches your physical pen mount."
            )
        if self.pen.drawing_z_mm <= 0.5:
            report.collision_risk_warnings.append(
                f"Drawing Z is set very close to zero ({self.pen.drawing_z_mm:.2f} mm). Never assume Z=0 "
                "corresponds to paper contact—if the pen tip extends below the nozzle, the pen will crash "
                "before the nozzle reaches Z=0."
            )
        if abs(self.machine.pen_holder_offset_x_mm) > 0.01 or abs(self.machine.pen_holder_offset_y_mm) > 0.01:
            report.collision_risk_warnings.append(
                f"Pen holder offset ({self.machine.pen_holder_offset_x_mm:+.1f}, "
                f"{self.machine.pen_holder_offset_y_mm:+.1f} mm) shifts the physical toolhead carriage relative "
                "to the pen tip. Ensure the toolhead clears the X-axis purge wiper and Z-pillar."
            )

    def _validate_configuration(self, report: SafetyValidationReport) -> None:
        # Check Z heights ordering
        if self.pen.pen_up_z_mm <= self.pen.drawing_z_mm:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    code="INVALID_PEN_Z_ORDER",
                    title="Pen-Up Z Must Be Higher Than Drawing Z",
                    message=(
                        f"Pen-Up Z ({self.pen.pen_up_z_mm:.2f} mm) is less than or equal to "
                        f"Drawing Z ({self.pen.drawing_z_mm:.2f} mm). Travel movements would drag across the paper."
                    ),
                    coordinates=(0.0, 0.0, self.pen.pen_up_z_mm),
                )
            )

        if self.pen.drawing_z_mm < 0.0:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    code="NEGATIVE_DRAWING_Z",
                    title="Negative Drawing Z Height",
                    message=f"Drawing Z ({self.pen.drawing_z_mm:.2f} mm) is negative, risking severe bed collision.",
                    coordinates=(0.0, 0.0, self.pen.drawing_z_mm),
                )
            )
        elif self.pen.drawing_z_mm < self.machine.min_safe_z_mm:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    code="Z_BELOW_SAFE_MINIMUM",
                    title="Drawing Z Below Configured Safe Z Minimum",
                    message=(
                        f"Drawing Z ({self.pen.drawing_z_mm:.2f} mm) is below the machine's minimum safe Z "
                        f"({self.machine.min_safe_z_mm:.2f} mm)."
                    ),
                    coordinates=(0.0, 0.0, self.pen.drawing_z_mm),
                )
            )

        if self.pen.pen_up_z_mm > self.machine.max_safe_z_mm or self.machine.safe_z_mm > self.machine.max_safe_z_mm:
            bad_z = max(self.pen.pen_up_z_mm, self.machine.safe_z_mm)
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    code="Z_ABOVE_SAFE_MAXIMUM",
                    title="Z Height Exceeds Configured Maximum Safe Z",
                    message=(
                        f"Configured Z height ({bad_z:.2f} mm) exceeds the maximum safe Z "
                        f"({self.machine.max_safe_z_mm:.2f} mm)."
                    ),
                    coordinates=(0.0, 0.0, bad_z),
                )
            )

        if not self.pen.is_calibrated:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="UNCALIBRATED_PEN_PROFILE",
                    title="Pen Profile Not Yet Calibrated",
                    message=(
                        f"Pen profile '{self.pen.name}' uses default or unverified Z heights "
                        f"(Draw Z={self.pen.drawing_z_mm:.2f} mm, Up Z={self.pen.pen_up_z_mm:.2f} mm). "
                        "Run the Calibration Wizard to confirm physical contact height."
                    ),
                )
            )

    def _validate_moves(self, moves: list[ToolpathMove], report: SafetyValidationReport) -> None:
        min_x = float("inf")
        max_x = float("-inf")
        min_y = float("inf")
        max_y = float("-inf")
        min_z = float("inf")
        max_z = float("-inf")

        max_travel_feed = self.machine.max_travel_speed_mm_s * 60.0
        max_draw_feed = self.machine.max_draw_speed_mm_s * 60.0
        max_z_feed = self.machine.max_z_speed_mm_s * 60.0

        # Check initial move state
        first_move = moves[0]
        if first_move.move_type == MovementType.DRAW and first_move.start_z > self.pen.drawing_z_mm + 0.01:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    code="MISSING_INITIAL_PEN_TRANSITION",
                    title="Drawing Started Without Pen Lowering Transition",
                    message="First movement is a drawing move before a controlled pen-down Z transition occurred.",
                    line_number=first_move.gcode_line_number or 1,
                    command=first_move.gcode_command,
                    coordinates=(first_move.start_x, first_move.start_y, first_move.start_z),
                )
            )

        pen_is_down = False
        reported_codes_count: dict[str, int] = {}

        def add_issue_throttled(issue: ValidationIssue, max_per_code: int = 10) -> None:
            cnt = reported_codes_count.get(issue.code, 0)
            if cnt < max_per_code:
                report.issues.append(issue)
            reported_codes_count[issue.code] = cnt + 1

        for mv in moves:
            for x, y, z in ((mv.start_x, mv.start_y, mv.start_z), (mv.end_x, mv.end_y, mv.end_z)):
                if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                    add_issue_throttled(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="NON_FINITE_COORDINATE",
                            title="Invalid NaN/Infinite Coordinate",
                            message="Movement contains non-finite coordinate values.",
                            line_number=mv.gcode_line_number,
                            command=mv.gcode_command,
                            coordinates=(0.0, 0.0, 0.0),
                        )
                    )
                    continue
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                min_z = min(min_z, z)
                max_z = max(max_z, z)

            # Check negative coordinates
            if mv.end_x < -1e-4 or mv.end_y < -1e-4 or mv.end_z < -1e-4:
                add_issue_throttled(
                    ValidationIssue(
                        severity=ValidationSeverity.CRITICAL,
                        code="NEGATIVE_COORDINATE",
                        title="Negative Machine Coordinate Detected",
                        message=(
                            f"Movement targets negative coordinate "
                            f"X={mv.end_x:.3f}, Y={mv.end_y:.3f}, Z={mv.end_z:.3f} mm."
                        ),
                        line_number=mv.gcode_line_number,
                        command=mv.gcode_command,
                        coordinates=(mv.end_x, mv.end_y, mv.end_z),
                    )
                )

            # Check nominal machine boundaries (0 .. 180 mm)
            if mv.end_x > self.machine.nominal_x_mm + 1e-4 or mv.end_y > self.machine.nominal_y_mm + 1e-4:
                add_issue_throttled(
                    ValidationIssue(
                        severity=ValidationSeverity.CRITICAL,
                        code="OUTSIDE_MACHINE_BOUNDS",
                        title="Coordinate Exceeds A1 Mini Build Volume",
                        message=(
                            f"Target (X={mv.end_x:.2f}, Y={mv.end_y:.2f} mm) exceeds the nominal build plate "
                            f"({self.machine.nominal_x_mm:.0f} × {self.machine.nominal_y_mm:.0f} mm)."
                        ),
                        line_number=mv.gcode_line_number,
                        command=mv.gcode_command,
                        coordinates=(mv.end_x, mv.end_y, mv.end_z),
                    )
                )

            # Check configured usable safety margins for drawing moves
            if mv.move_type == MovementType.DRAW:
                if (
                    mv.end_x < self.machine.usable_min_x - 1e-3
                    or mv.end_x > self.machine.usable_max_x + 1e-3
                    or mv.end_y < self.machine.usable_min_y - 1e-3
                    or mv.end_y > self.machine.usable_max_y + 1e-3
                ):
                    add_issue_throttled(
                        ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            code="OUTSIDE_SAFETY_MARGIN",
                            title="Drawing Movement Enters Safety Margin",
                            message=(
                                f"Drawing coordinate (X={mv.end_x:.2f}, Y={mv.end_y:.2f} mm) is outside the "
                                f"configured usable area X[{self.machine.usable_min_x:.1f}..{self.machine.usable_max_x:.1f}], "
                                f"Y[{self.machine.usable_min_y:.1f}..{self.machine.usable_max_y:.1f}] mm."
                            ),
                            line_number=mv.gcode_line_number,
                            command=mv.gcode_command,
                            coordinates=(mv.end_x, mv.end_y, mv.end_z),
                        )
                    )

            # Check Z range on every move
            if mv.end_z < self.machine.min_safe_z_mm - 1e-3 or mv.end_z > self.machine.max_safe_z_mm + 1e-3:
                add_issue_throttled(
                    ValidationIssue(
                        severity=ValidationSeverity.CRITICAL,
                        code="Z_OUT_OF_SAFE_RANGE",
                        title="Movement Z Outside Configured Safe Range",
                        message=(
                            f"Movement Z={mv.end_z:.2f} mm is outside safe Z range "
                            f"[{self.machine.min_safe_z_mm:.2f} .. {self.machine.max_safe_z_mm:.2f}] mm."
                        ),
                        line_number=mv.gcode_line_number,
                        command=mv.gcode_command,
                        coordinates=(mv.end_x, mv.end_y, mv.end_z),
                    )
                )

            # Check Pen Transition State Machine
            if mv.move_type == MovementType.PEN_DOWN:
                pen_is_down = True
                if mv.feed_rate_mm_min > max_z_feed + 1.0:
                    add_issue_throttled(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="EXCESSIVE_Z_FEEDRATE",
                            title="Excessive Z Lowering Speed",
                            message=(
                                f"Z feed rate {mv.feed_rate_mm_min:.0f} mm/min exceeds limit "
                                f"{max_z_feed:.0f} mm/min ({self.machine.max_z_speed_mm_s:.1f} mm/s)."
                            ),
                            line_number=mv.gcode_line_number,
                            command=mv.gcode_command,
                            coordinates=(mv.end_x, mv.end_y, mv.end_z),
                        )
                    )
            elif mv.move_type == MovementType.PEN_UP:
                pen_is_down = False
                if mv.feed_rate_mm_min > max_z_feed + 1.0:
                    add_issue_throttled(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="EXCESSIVE_Z_FEEDRATE",
                            title="Excessive Z Lifting Speed",
                            message=(
                                f"Z feed rate {mv.feed_rate_mm_min:.0f} mm/min exceeds limit "
                                f"{max_z_feed:.0f} mm/min ({self.machine.max_z_speed_mm_s:.1f} mm/s)."
                            ),
                            line_number=mv.gcode_line_number,
                            command=mv.gcode_command,
                            coordinates=(mv.end_x, mv.end_y, mv.end_z),
                        )
                    )
            elif mv.move_type == MovementType.DRAW:
                if not pen_is_down:
                    add_issue_throttled(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="MISSING_PEN_DOWN_TRANSITION",
                            title="Missing Pen-Down Transition Before Drawing",
                            message="A drawing movement was executed while the pen state was lifted.",
                            line_number=mv.gcode_line_number,
                            command=mv.gcode_command,
                            coordinates=(mv.end_x, mv.end_y, mv.end_z),
                        )
                    )
                if mv.feed_rate_mm_min > max_draw_feed + 1.0:
                    add_issue_throttled(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="EXCESSIVE_DRAW_FEEDRATE",
                            title="Drawing Feed Rate Exceeds Machine Maximum",
                            message=(
                                f"Drawing feed rate {mv.feed_rate_mm_min:.0f} mm/min exceeds maximum "
                                f"{max_draw_feed:.0f} mm/min ({self.machine.max_draw_speed_mm_s:.1f} mm/s)."
                            ),
                            line_number=mv.gcode_line_number,
                            command=mv.gcode_command,
                            coordinates=(mv.end_x, mv.end_y, mv.end_z),
                        )
                    )
            elif mv.move_type == MovementType.TRAVEL:
                if pen_is_down or mv.end_z < self.pen.pen_up_z_mm - 0.05:
                    add_issue_throttled(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="TRAVEL_WITH_PEN_LOWERED",
                            title="Travel Movement With Pen Lowered",
                            message=(
                                f"Rapid travel movement at Z={mv.end_z:.2f} mm while pen is below "
                                f"Pen-Up Z ({self.pen.pen_up_z_mm:.2f} mm)."
                            ),
                            line_number=mv.gcode_line_number,
                            command=mv.gcode_command,
                            coordinates=(mv.end_x, mv.end_y, mv.end_z),
                        )
                    )
                if mv.feed_rate_mm_min > max_travel_feed + 1.0:
                    add_issue_throttled(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="EXCESSIVE_TRAVEL_FEEDRATE",
                            title="Travel Feed Rate Exceeds Machine Maximum",
                            message=(
                                f"Travel feed rate {mv.feed_rate_mm_min:.0f} mm/min exceeds maximum "
                                f"{max_travel_feed:.0f} mm/min ({self.machine.max_travel_speed_mm_s:.1f} mm/s)."
                            ),
                            line_number=mv.gcode_line_number,
                            command=mv.gcode_command,
                            coordinates=(mv.end_x, mv.end_y, mv.end_z),
                        )
                    )

        # Final positioning check: pen must be lifted at the end of the trajectory
        last_move = moves[-1]
        if pen_is_down or last_move.end_z < self.pen.pen_up_z_mm - 0.05:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    code="UNSAFE_FINAL_POSITION",
                    title="Toolpath Ends With Pen Lowered",
                    message=(
                        f"Final movement leaves the pen at Z={last_move.end_z:.2f} mm instead of "
                        f"lifting to Pen-Up Z ({self.pen.pen_up_z_mm:.2f} mm) or Safe Z."
                    ),
                    line_number=last_move.gcode_line_number,
                    command=last_move.gcode_command,
                    coordinates=(last_move.end_x, last_move.end_y, last_move.end_z),
                )
            )

        if min_x != float("inf"):
            report.min_x_found = min_x
            report.max_x_found = max_x
            report.min_y_found = min_y
            report.max_y_found = max_y
            report.min_z_found = min_z
            report.max_z_found = max_z

    def _validate_gcode_lines(self, gcode_text: str, report: SafetyValidationReport) -> None:
        lines = gcode_text.splitlines()
        report.checked_gcode_lines = len(lines)

        has_g21 = False
        has_g90 = False
        cur_x = 0.0
        cur_y = 0.0
        cur_z = self.machine.safe_z_mm

        param_pattern = re.compile(r"([A-Z])([-+]?\d*\.?\d+)")

        for idx, raw_line in enumerate(lines, start=1):
            # Strip comments
            code_part = raw_line.split(";", 1)[0].strip()
            if not code_part:
                continue

            tokens = code_part.split()
            cmd = tokens[0].upper()

            if cmd == "G21":
                has_g21 = True
            elif cmd == "G90":
                has_g90 = True

            # Check forbidden commands
            if cmd in FORBIDDEN_GCODE_COMMANDS:
                report.issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.CRITICAL,
                        code=f"FORBIDDEN_COMMAND_{cmd.replace('.', '_')}",
                        title=f"Prohibited G-Code Command ({cmd})",
                        message=FORBIDDEN_GCODE_COMMANDS[cmd],
                        line_number=idx,
                        command=raw_line.strip(),
                        coordinates=(cur_x, cur_y, cur_z),
                    )
                )
                continue

            # Check unknown/unsupported commands
            if cmd not in ALLOWED_GCODE_COMMANDS:
                report.issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.CRITICAL,
                        code="UNSUPPORTED_GCODE_COMMAND",
                        title=f"Unsupported or Unverified Command ({cmd})",
                        message=(
                            f"Command '{cmd}' is not in the verified A1 Mini Pen Plotter command set."
                        ),
                        line_number=idx,
                        command=raw_line.strip(),
                        coordinates=(cur_x, cur_y, cur_z),
                    )
                )
                continue

            params = {m.group(1): float(m.group(2)) for m in param_pattern.finditer(code_part[len(cmd):].upper())}

            # Check heater commands (M104 / M140) must have S0
            if cmd in ("M104", "M140"):
                temp = params.get("S", 0.0)
                if temp > 0.0:
                    report.issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="NON_ZERO_HEATER_COMMAND",
                            title="Active Heater Command in Pen Plotter G-code",
                            message=f"Command '{cmd} S{temp:.0f}' attempts to heat the printer during pen plotting.",
                            line_number=idx,
                            command=raw_line.strip(),
                            coordinates=(cur_x, cur_y, cur_z),
                        )
                    )

            # Check G0/G1 moves for extrusion 'E' parameter or out-of-range coordinates
            if cmd in ("G0", "G00", "G1", "G01"):
                if "E" in params and abs(params["E"]) > 1e-6:
                    report.issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.CRITICAL,
                            code="EXTRUSION_COMMAND_DETECTED",
                            title="Extrusion Axis (E) Command Detected",
                            message="G-code contains filament extrusion movement (E axis), which is invalid for pen plotting.",
                            line_number=idx,
                            command=raw_line.strip(),
                            coordinates=(cur_x, cur_y, cur_z),
                        )
                    )

                cur_x = params.get("X", cur_x)
                cur_y = params.get("Y", cur_y)
                cur_z = params.get("Z", cur_z)

        if not has_g21:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="MISSING_G21",
                    title="Missing Explicit Millimeter Unit Command (G21)",
                    message="G-code does not explicitly declare G21 (millimeter units) in its header.",
                    line_number=1,
                )
            )
        if not has_g90:
            report.issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    code="MISSING_G90",
                    title="Missing Explicit Absolute Positioning Command (G90)",
                    message="G-code must explicitly set G90 (absolute positioning) before executing movements.",
                    line_number=1,
                )
            )
