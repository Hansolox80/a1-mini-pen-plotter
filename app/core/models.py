"""Core data models for SVG elements, toolpaths, transformations, and project state."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import math
from typing import Any, Optional


class MovementType(str, Enum):
    """Types of physical toolhead movements."""
    TRAVEL = "travel"          # Pen lifted XY travel
    DRAW = "draw"              # Pen lowered XY drawing
    PEN_UP = "pen_up"          # Controlled Z lift transition
    PEN_DOWN = "pen_down"      # Controlled Z lower transition


class WorkflowMode(str, Enum):
    """Distinguishes G-code generation modes for transparency and safety."""
    STANDARD_GCODE = "standard_gcode"          # Generic 2D plotter G-code (G21/G90/G0/G1)
    BAMBU_SD_DIRECT = "bambu_sd_direct"        # A1 Mini cold-plotting G-code for MicroSD root execution
    BAMBU_STUDIO_3MF = "bambu_studio_3mf"      # Packaged .gcode.3mf container for Bambu Studio / Wi-Fi workflow


@dataclass
class BoundingBox:
    """Axis-aligned 2D bounding box in millimeters."""
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return max(0.0, self.max_x - self.min_x)

    @property
    def height(self) -> float:
        return max(0.0, self.max_y - self.min_y)

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) * 0.5

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) * 0.5

    @property
    def is_valid(self) -> bool:
        return (
            math.isfinite(self.min_x)
            and math.isfinite(self.min_y)
            and math.isfinite(self.max_x)
            and math.isfinite(self.max_y)
            and self.max_x >= self.min_x
            and self.max_y >= self.min_y
        )


@dataclass
class SvgWarning:
    """Warning or unsupported element notification produced during SVG import."""
    element_tag: str
    element_id: str
    message: str
    severity: str = "warning"  # "info", "warning", "error"


@dataclass
class SvgElement:
    """Represents a parsed graphic element from an SVG document in millimeter coordinates."""
    id: str
    element_type: str  # path, rect, circle, ellipse, line, polyline, polygon, text
    name: str
    layer: str
    polylines_mm: list[list[tuple[float, float]]]  # Flattened polylines in SVG millimeter space (Y-down before plate transform)
    is_closed: bool = False
    has_fill: bool = False
    fill_color: Optional[str] = None
    stroke_color: str = "#22C55E"
    stroke_width_mm: float = 0.4
    visible: bool = True
    locked: bool = False
    # Per-element transform adjustments in build-plate space (mm / degrees)
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_deg: float = 0.0
    fill_mode_override: Optional[str] = None  # None, "ignore", "outline", "hatch", "contour"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SvgElement:
        polylines = [
            [(float(pt[0]), float(pt[1])) for pt in poly]
            for poly in data.get("polylines_mm", [])
        ]
        return cls(
            id=str(data.get("id", "elem")),
            element_type=str(data.get("element_type", "path")),
            name=str(data.get("name", "Path")),
            layer=str(data.get("layer", "Layer 1")),
            polylines_mm=polylines,
            is_closed=bool(data.get("is_closed", False)),
            has_fill=bool(data.get("has_fill", False)),
            fill_color=data.get("fill_color"),
            stroke_color=str(data.get("stroke_color", "#22C55E")),
            stroke_width_mm=float(data.get("stroke_width_mm", 0.4)),
            visible=bool(data.get("visible", True)),
            locked=bool(data.get("locked", False)),
            offset_x=float(data.get("offset_x", 0.0)),
            offset_y=float(data.get("offset_y", 0.0)),
            scale_x=float(data.get("scale_x", 1.0)),
            scale_y=float(data.get("scale_y", 1.0)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            fill_mode_override=data.get("fill_mode_override"),
        )


@dataclass
class DocumentTransform:
    """Global placement and transformation of the imported SVG drawing on the build plate."""
    pos_x_mm: float = 20.0
    pos_y_mm: float = 20.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    lock_aspect: bool = True
    rotation_deg: float = 0.0
    mirror_x: bool = False
    mirror_y: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentTransform:
        return cls(
            pos_x_mm=float(data.get("pos_x_mm", 20.0)),
            pos_y_mm=float(data.get("pos_y_mm", 20.0)),
            scale_x=float(data.get("scale_x", 1.0)),
            scale_y=float(data.get("scale_y", 1.0)),
            lock_aspect=bool(data.get("lock_aspect", True)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            mirror_x=bool(data.get("mirror_x", False)),
            mirror_y=bool(data.get("mirror_y", False)),
        )


@dataclass
class FillSettings:
    """Configuration for converting filled SVG shapes into plotter paths."""
    mode: str = "outline"  # "ignore", "outline", "hatch", "contour"
    hatch_spacing_mm: float = 1.0
    hatch_angle_deg: float = 45.0
    cross_hatch: bool = False
    contour_spacing_mm: float = 0.8
    contour_max_rings: int = 25
    include_outline: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FillSettings:
        return cls(
            mode=str(data.get("mode", "outline")),
            hatch_spacing_mm=max(0.1, float(data.get("hatch_spacing_mm", 1.0))),
            hatch_angle_deg=float(data.get("hatch_angle_deg", 45.0)),
            cross_hatch=bool(data.get("cross_hatch", False)),
            contour_spacing_mm=max(0.1, float(data.get("contour_spacing_mm", 0.8))),
            contour_max_rings=max(1, int(data.get("contour_max_rings", 25))),
            include_outline=bool(data.get("include_outline", True)),
        )


@dataclass
class OptimizationSettings:
    """Configuration for toolpath generation and ordering optimization."""
    strategy: str = "nearest_neighbor"  # "original", "nearest_neighbor", "direction_only", "min_travel_2opt"
    allow_direction_reversal: bool = True
    curve_precision_mm: float = 0.08
    simplify_tolerance_mm: float = 0.02
    merge_threshold_mm: float = 0.08
    min_segment_length_mm: float = 0.01

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimizationSettings:
        return cls(
            strategy=str(data.get("strategy", "nearest_neighbor")),
            allow_direction_reversal=bool(data.get("allow_direction_reversal", True)),
            curve_precision_mm=max(0.005, float(data.get("curve_precision_mm", 0.08))),
            simplify_tolerance_mm=max(0.0, float(data.get("simplify_tolerance_mm", 0.02))),
            merge_threshold_mm=max(0.0, float(data.get("merge_threshold_mm", 0.08))),
            min_segment_length_mm=max(0.0, float(data.get("min_segment_length_mm", 0.01))),
        )


@dataclass
class ToolpathMove:
    """A single atomic movement in the generated 3D plotter trajectory."""
    index: int
    move_type: MovementType
    start_x: float
    start_y: float
    start_z: float
    end_x: float
    end_y: float
    end_z: float
    feed_rate_mm_min: float
    dwell_ms: int = 0
    layer: str = "Layer 1"
    element_id: str = ""
    path_index: int = 0
    gcode_line_number: int = 0
    gcode_command: str = ""

    @property
    def distance_xy(self) -> float:
        return math.hypot(self.end_x - self.start_x, self.end_y - self.start_y)

    @property
    def distance_xyz(self) -> float:
        return math.sqrt(
            (self.end_x - self.start_x) ** 2
            + (self.end_y - self.start_y) ** 2
            + (self.end_z - self.start_z) ** 2
        )

    @property
    def duration_seconds(self) -> float:
        speed_mm_s = max(0.1, self.feed_rate_mm_min / 60.0)
        move_time = self.distance_xyz / speed_mm_s
        return move_time + (self.dwell_ms / 1000.0)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["move_type"] = self.move_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolpathMove:
        return cls(
            index=int(data.get("index", 0)),
            move_type=MovementType(data.get("move_type", "travel")),
            start_x=float(data.get("start_x", 0.0)),
            start_y=float(data.get("start_y", 0.0)),
            start_z=float(data.get("start_z", 0.0)),
            end_x=float(data.get("end_x", 0.0)),
            end_y=float(data.get("end_y", 0.0)),
            end_z=float(data.get("end_z", 0.0)),
            feed_rate_mm_min=float(data.get("feed_rate_mm_min", 3000.0)),
            dwell_ms=int(data.get("dwell_ms", 0)),
            layer=str(data.get("layer", "Layer 1")),
            element_id=str(data.get("element_id", "")),
            path_index=int(data.get("path_index", 0)),
            gcode_line_number=int(data.get("gcode_line_number", 0)),
            gcode_command=str(data.get("gcode_command", "")),
        )


@dataclass
class ToolpathStats:
    """Summary metrics for a generated toolpath."""
    drawing_width_mm: float = 0.0
    drawing_height_mm: float = 0.0
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0
    num_paths: int = 0
    num_movements: int = 0
    num_pen_lifts: int = 0
    drawing_distance_mm: float = 0.0
    travel_distance_mm: float = 0.0
    total_distance_mm: float = 0.0
    unoptimized_travel_distance_mm: float = 0.0
    optimization_improvement_pct: float = 0.0
    estimated_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedSvgDocument:
    """Complete result of parsing an SVG file."""
    file_path: str
    width_mm: float
    height_mm: float
    viewbox: Optional[tuple[float, float, float, float]]
    original_units: str
    elements: list[SvgElement] = field(default_factory=list)
    warnings: list[SvgWarning] = field(default_factory=list)
    raw_svg_content: str = ""

    @property
    def layers(self) -> list[str]:
        seen: list[str] = []
        for el in self.elements:
            if el.layer not in seen:
                seen.append(el.layer)
        return seen if seen else ["Layer 1"]

    def compute_native_bounds(self) -> BoundingBox:
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")
        for el in self.elements:
            if not el.visible:
                continue
            for poly in el.polylines_mm:
                for x, y in poly:
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y
        if min_x == float("inf"):
            return BoundingBox(0.0, 0.0, 0.0, 0.0)
        return BoundingBox(min_x, min_y, max_x, max_y)
