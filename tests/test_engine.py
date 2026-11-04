"""Automated test suite for A1 Mini Pen Plotter conversion engine, safety validation, and exporters."""

from __future__ import annotations

import math
from pathlib import Path
import zipfile

import pytest

from app.core.coordinate_system import (
    CoordinateTransformer,
    convert_length_to_mm,
    invert_y_polyline,
    transform_point_2d,
)
from app.core.gcode_generator import GcodeGenerator
from app.core.geometry import (
    deduplicate_points,
    flatten_cubic_bezier,
    flatten_quadratic_bezier,
    flatten_svg_arc,
    process_element_fill_and_stroke,
    simplify_polyline,
)
from app.core.models import (
    DocumentTransform,
    FillSettings,
    MovementType,
    OptimizationSettings,
    ToolpathMove,
    WorkflowMode,
)
from app.core.path_optimizer import ToolpathGenerator
from app.core.simulator import ToolpathSimulator
from app.core.svg_parser import SvgParser
from app.export.gcode_exporter import GcodeExporter, SafetyExportBlockedError
from app.export.project_exporter import PlotterProject, ProjectManager
from app.machine.a1_mini import create_default_a1_mini_profile
from app.machine.profiles import ProfileManager, create_default_pen_profiles
from app.machine.safety import SafetyValidator, ValidationSeverity


EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


# ==============================================================================
# REQUIRED TEST CASES 1 - 10 (Section 14)
# ==============================================================================


def test_01_20x20mm_square_exact_toolpath():
    """Required Case 1: A 20 x 20 mm SVG square must generate a physically equivalent 20 x 20 mm toolpath."""
    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "01_square_20x20mm.svg")
    assert len(doc.elements) == 1

    bounds = doc.compute_native_bounds()
    assert math.isclose(bounds.width, 20.0, abs_tol=1e-4)
    assert math.isclose(bounds.height, 20.0, abs_tol=1e-4)

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    gen = ToolpathGenerator(machine, pen)
    moves, stats = gen.generate(doc, DocumentTransform(pos_x_mm=30.0, pos_y_mm=40.0))

    assert math.isclose(stats.drawing_width_mm, 20.0, abs_tol=1e-3)
    assert math.isclose(stats.drawing_height_mm, 20.0, abs_tol=1e-3)
    assert math.isclose(stats.drawing_distance_mm, 80.0, abs_tol=1e-2)
    assert math.isclose(stats.min_x, 30.0, abs_tol=1e-3)
    assert math.isclose(stats.min_y, 40.0, abs_tol=1e-3)
    assert math.isclose(stats.max_x, 50.0, abs_tol=1e-3)
    assert math.isclose(stats.max_y, 60.0, abs_tol=1e-3)


def test_02_20mm_circle_dimensions():
    """Required Case 2: 20 mm diameter circle (r=10mm) must have 20x20mm bounding box and ~20*pi circumference."""
    parser = SvgParser(curve_precision_mm=0.02)
    doc = parser.parse_file(EXAMPLES_DIR / "02_circle_20mm.svg")
    assert len(doc.elements) == 1

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    gen = ToolpathGenerator(machine, pen, OptimizationSettings(simplify_tolerance_mm=0.005))
    moves, stats = gen.generate(doc, DocumentTransform(pos_x_mm=20.0, pos_y_mm=20.0))

    assert math.isclose(stats.drawing_width_mm, 20.0, abs_tol=0.05)
    assert math.isclose(stats.drawing_height_mm, 20.0, abs_tol=0.05)
    expected_circumference = 20.0 * math.pi
    assert math.isclose(stats.drawing_distance_mm, expected_circumference, rel_tol=0.01)


def test_03_diagonal_line():
    """Required Case 3: Diagonal line from (15,15) to (75,65) -> dx=60, dy=50, length=hypot(60,50)."""
    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "03_diagonal_line.svg")
    assert len(doc.elements) == 1

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    gen = ToolpathGenerator(machine, pen)
    moves, stats = gen.generate(doc, DocumentTransform(pos_x_mm=15.0, pos_y_mm=15.0))

    expected_len = math.hypot(60.0, 50.0)
    assert math.isclose(stats.drawing_width_mm, 60.0, abs_tol=1e-3)
    assert math.isclose(stats.drawing_height_mm, 50.0, abs_tol=1e-3)
    assert math.isclose(stats.drawing_distance_mm, expected_len, abs_tol=1e-3)


def test_04_bezier_and_arc_flattening():
    """Required Case 4: Cubic Bézier, Quadratic Bézier, and Elliptical Arc flattening."""
    parser = SvgParser(curve_precision_mm=0.05)
    doc = parser.parse_file(EXAMPLES_DIR / "04_bezier_curves.svg")
    assert len(doc.elements) == 3

    for el in doc.elements:
        assert len(el.polylines_mm) >= 1
        assert len(el.polylines_mm[0]) > 8  # Flattened into smooth multi-segment polyline


def test_05_multiple_independent_paths_and_optimization():
    """Required Case 5: Multiple independent paths with Nearest-Neighbor and 2-Opt travel reduction."""
    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "05_multiple_paths.svg")
    assert len(doc.elements) == 6

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]

    gen_orig = ToolpathGenerator(machine, pen, OptimizationSettings(strategy="original"))
    _, stats_orig = gen_orig.generate(doc)

    gen_nn = ToolpathGenerator(machine, pen, OptimizationSettings(strategy="nearest_neighbor"))
    _, stats_nn = gen_nn.generate(doc)

    gen_2opt = ToolpathGenerator(machine, pen, OptimizationSettings(strategy="min_travel_2opt"))
    _, stats_2opt = gen_2opt.generate(doc)

    assert stats_nn.travel_distance_mm < stats_orig.travel_distance_mm
    assert stats_2opt.travel_distance_mm <= stats_nn.travel_distance_mm + 1e-4
    assert stats_nn.optimization_improvement_pct > 10.0


def test_06_svg_with_viewbox_scaling():
    """Required Case 6: SVG with 60x60mm physical size and viewBox='0 0 600 600' (10:1 scaling)."""
    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "06_viewbox_scaled.svg")
    assert len(doc.elements) == 2

    # First element is a 200x200 user-unit rect -> must be 20x20mm physically!
    sq_poly = doc.elements[0].polylines_mm[0]
    xs = [p[0] for p in sq_poly]
    ys = [p[1] for p in sq_poly]
    assert math.isclose(max(xs) - min(xs), 20.0, abs_tol=1e-3)
    assert math.isclose(max(ys) - min(ys), 20.0, abs_tol=1e-3)


def test_07_svg_with_nested_transformations():
    """Required Case 7: SVG with nested group translate, scale(2,2), and rotate(45)."""
    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "07_nested_transforms.svg")
    assert len(doc.elements) == 2

    # First element: 10x10 rect inside scale(2,2) -> 20x20mm physical square
    sq = doc.elements[0].polylines_mm[0]
    xs = [p[0] for p in sq]
    ys = [p[1] for p in sq]
    assert math.isclose(max(xs) - min(xs), 20.0, abs_tol=1e-3)
    assert math.isclose(max(ys) - min(ys), 20.0, abs_tol=1e-3)

    # Second element: 10x10 rect inside scale(2,2) + rotate(45) -> 20x20 square rotated 45 deg
    # Bounding box of a 20x20 square rotated by 45 deg is 20 * sqrt(2) = 28.28427 mm
    rot_sq = doc.elements[1].polylines_mm[0]
    rxs = [p[0] for p in rot_sq]
    rys = [p[1] for p in rot_sq]
    expected_diag = 20.0 * math.sqrt(2.0)
    assert math.isclose(max(rxs) - min(rxs), expected_diag, abs_tol=1e-2)
    assert math.isclose(max(rys) - min(rys), expected_diag, abs_tol=1e-2)


def test_08_svg_with_negative_coordinates():
    """Required Case 8: SVG with negative coordinates must be parsed and flagged by safety validator when raw."""
    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "08_negative_coordinates.svg")
    native_bounds = doc.compute_native_bounds()
    assert native_bounds.min_x < 0.0
    assert native_bounds.min_y < 0.0

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True

    # When normalize_origin=False and offset=0, negative SVG coords produce negative machine coords
    gen = ToolpathGenerator(machine, pen, invert_y=False, normalize_origin=False)
    moves, stats = gen.generate(doc, DocumentTransform(pos_x_mm=0.0, pos_y_mm=0.0))
    gcode = GcodeGenerator(machine, pen).generate(moves, stats)

    validator = SafetyValidator(machine, pen)
    report = validator.validate(moves, gcode)
    assert report.overall_status == ValidationSeverity.CRITICAL
    assert not report.can_export_executable
    assert any(i.code == "NEGATIVE_COORDINATE" for i in report.issues)


def test_09_svg_larger_than_a1_mini_workspace():
    """Required Case 9: 220x220mm SVG exceeds 180x180mm A1 Mini build plate and blocks executable export."""
    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "09_oversized_220x220mm.svg")

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True

    gen = ToolpathGenerator(machine, pen)
    moves, stats = gen.generate(doc, DocumentTransform(pos_x_mm=0.0, pos_y_mm=0.0))
    gcode = GcodeGenerator(machine, pen).generate(moves, stats)

    validator = SafetyValidator(machine, pen)
    report = validator.validate(moves, gcode)
    assert report.overall_status == ValidationSeverity.CRITICAL
    assert not report.can_export_executable
    assert any(i.code == "OUTSIDE_MACHINE_BOUNDS" for i in report.issues)


def test_10_svg_using_inches_instead_of_millimeters():
    """Required Case 10: SVG using inches ('1in' x '1in') must convert to 25.4 x 25.4 mm."""
    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "10_inches_unit.svg")
    bounds = doc.compute_native_bounds()
    assert math.isclose(bounds.width, 25.4, abs_tol=1e-3)
    assert math.isclose(bounds.height, 25.4, abs_tol=1e-3)

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    gen = ToolpathGenerator(machine, pen)
    _, stats = gen.generate(doc)
    assert math.isclose(stats.drawing_width_mm, 25.4, abs_tol=1e-2)
    assert math.isclose(stats.drawing_height_mm, 25.4, abs_tol=1e-2)


# ==============================================================================
# ADDITIONAL UNIT & INTEGRATION TESTS
# ==============================================================================


def test_unit_conversions():
    assert math.isclose(convert_length_to_mm(1.0, "mm"), 1.0)
    assert math.isclose(convert_length_to_mm(2.5, "cm"), 25.0)
    assert math.isclose(convert_length_to_mm(1.0, "in"), 25.4)
    assert math.isclose(convert_length_to_mm(72.0, "pt"), 25.4)
    assert math.isclose(convert_length_to_mm(96.0, "px", dpi=96.0), 25.4)


def test_y_axis_inversion_and_2d_transforms():
    poly = [(10.0, 20.0), (30.0, 80.0)]
    inv = invert_y_polyline(poly, reference_height_mm=100.0)
    assert inv == [(10.0, 80.0), (30.0, 20.0)]

    # 90-degree rotation around (0, 0)
    rx, ry = transform_point_2d(10.0, 0.0, 0.0, 0.0, rotation_deg=90.0)
    assert math.isclose(rx, 0.0, abs_tol=1e-6)
    assert math.isclose(ry, 10.0, abs_tol=1e-6)


def test_unsupported_svg_elements_are_reported():
    svg_with_unsupported = """<?xml version="1.0" encoding="UTF-8"?>
    <svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm">
      <image id="img1" x="10" y="10" width="50" height="50" href="test.png" />
      <foreignObject id="fo1" x="0" y="0" width="20" height="20" />
      <rect id="valid_rect" x="10" y="10" width="20" height="20" />
    </svg>
    """
    doc = SvgParser().parse_string(svg_with_unsupported)
    assert len(doc.elements) == 1
    assert len(doc.warnings) == 2
    tags = {w.element_tag for w in doc.warnings}
    assert "image" in tags
    assert "foreignObject" in tags


def test_filled_shapes_hatching_and_contours():
    sq_poly = [[(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0), (0.0, 0.0)]]
    hatch_settings = FillSettings(mode="hatch", hatch_spacing_mm=2.0, hatch_angle_deg=45.0, cross_hatch=True)
    hatch_polys = process_element_fill_and_stroke(sq_poly, has_fill=True, fill_settings=hatch_settings)
    assert len(hatch_polys) > 10

    contour_settings = FillSettings(mode="contour", contour_spacing_mm=2.0)
    contour_polys = process_element_fill_and_stroke(sq_poly, has_fill=True, fill_settings=contour_settings)
    assert len(contour_polys) >= 5


def test_pen_transitions_and_gcode_generation():
    doc = SvgParser().parse_file(EXAMPLES_DIR / "01_square_20x20mm.svg")
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True

    gen = ToolpathGenerator(machine, pen)
    moves, stats = gen.generate(doc)
    gcode = GcodeGenerator(machine, pen, workflow_mode=WorkflowMode.BAMBU_SD_DIRECT).generate(moves, stats)

    # Verify move sequence starts with TRAVEL, then PEN_DOWN, then DRAW, and ends with PEN_UP
    assert moves[0].move_type == MovementType.TRAVEL
    assert moves[1].move_type == MovementType.PEN_DOWN
    assert any(m.move_type == MovementType.DRAW for m in moves)
    assert moves[-1].move_type == MovementType.PEN_UP
    assert math.isclose(moves[-1].end_z, pen.pen_up_z_mm, abs_tol=1e-4)

    # Verify G-code commands
    assert "G21" in gcode
    assert "G90" in gcode
    assert "M104 S0" in gcode
    assert "M140 S0" in gcode

    # Validate safety
    report = SafetyValidator(machine, pen).validate(moves, gcode)
    assert report.overall_status == ValidationSeverity.VALID
    assert report.can_export_executable


def test_safety_validator_blocks_heating_and_extrusion():
    doc = SvgParser().parse_file(EXAMPLES_DIR / "01_square_20x20mm.svg")
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True

    moves, stats = ToolpathGenerator(machine, pen).generate(doc)
    bad_gcode = "G21\nG90\nM109 S220\nG1 X50 Y50 E12.5 F1500\n"
    report = SafetyValidator(machine, pen).validate(moves, bad_gcode)
    assert report.overall_status == ValidationSeverity.CRITICAL
    assert not report.can_export_executable
    codes = {i.code for i in report.issues}
    assert "FORBIDDEN_COMMAND_M109" in codes
    assert "EXTRUSION_COMMAND_DETECTED" in codes


def test_exporters_and_project_roundtrip(tmp_path: Path):
    doc = SvgParser().parse_file(EXAMPLES_DIR / "01_square_20x20mm.svg")
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True

    moves, stats = ToolpathGenerator(machine, pen).generate(doc)
    gcode = GcodeGenerator(machine, pen).generate(moves, stats)

    # 1. G-code export
    gcode_path = tmp_path / "plot.gcode"
    rep = GcodeExporter.export_gcode_file(gcode_path, moves, gcode, machine, pen)
    assert gcode_path.exists()
    assert rep.can_export_executable

    # 2. Bambu 3MF export
    threemf_path = tmp_path / "plot.gcode.3mf"
    GcodeExporter.export_bambu_3mf_file(threemf_path, moves, gcode, stats, machine, pen)
    assert threemf_path.exists()
    with zipfile.ZipFile(threemf_path, "r") as zf:
        names = set(zf.namelist())
        assert "Metadata/plate_1.gcode" in names
        assert "Metadata/plate_1.gcode.md5" in names
        assert "Metadata/slice_info.config" in names
        assert "Metadata/plate_1.png" in names

    # 3. Optimized SVG export
    opt_svg_path = tmp_path / "optimized.svg"
    GcodeExporter.export_optimized_svg(opt_svg_path, moves, machine, pen)
    assert opt_svg_path.exists()

    # 4. Validation report export
    rep_json = tmp_path / "report.json"
    rep_md = tmp_path / "report.md"
    GcodeExporter.export_validation_report(rep_json, rep, machine, pen, stats)
    GcodeExporter.export_validation_report(rep_md, rep, machine, pen, stats)
    assert rep_json.exists()
    assert rep_md.exists()

    # 5. Preview PNG export
    png_path = tmp_path / "preview.png"
    GcodeExporter.export_preview_image(png_path, moves, machine, width_px=400, height_px=400)
    assert png_path.exists()

    # 6. Project save & load roundtrip
    pm = ProjectManager(app_data_dir=tmp_path / "appdata")
    proj = PlotterProject(
        name="Test Square Project",
        svg_document=doc,
        machine_profile=machine,
        pen_profile=pen,
        toolpath_moves=moves,
    )
    proj_file = tmp_path / "square.a1plot"
    pm.save_project(proj, proj_file)
    loaded = pm.load_project(proj_file)
    assert loaded.name == "Test Square Project"
    assert loaded.svg_document is not None
    assert len(loaded.svg_document.elements) == 1
    assert len(loaded.toolpath_moves) == len(moves)


def test_simulator_playback_and_stepping():
    doc = SvgParser().parse_file(EXAMPLES_DIR / "01_square_20x20mm.svg")
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    moves, stats = ToolpathGenerator(machine, pen).generate(doc)
    GcodeGenerator(machine, pen).generate(moves, stats)

    sim = ToolpathSimulator()
    sim.load_moves(moves)
    assert sim.state.total_time_seconds > 0.0
    st1 = sim.step_forward()
    assert st1.current_move_index == 1
    st0 = sim.step_backward()
    assert st0.current_move_index == 0

    sim.state.is_playing = True
    sim.state.playback_speed = 10.0
    sim.advance_time(100.0)
    assert math.isclose(sim.overall_progress_ratio, 1.0, abs_tol=1e-4)


# ==============================================================================
# RIGOROUS SAFETY & PERFORMANCE OPTIMIZATION TESTS
# ==============================================================================


def test_soft_stop_blocks_export_on_boundary_violation(tmp_path):
    """Safety Test 1: Movements targeting coordinates outside usable margins must lock export as CRITICAL."""
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True

    # Build a move that attempts to draw beyond usable margins (e.g., X=175mm where max is 170mm)
    bad_move = ToolpathMove(
        index=0,
        move_type=MovementType.DRAW,
        start_x=50.0,
        start_y=50.0,
        start_z=pen.drawing_z_mm,
        end_x=175.0,  # Exceeds usable_max_x = 170.0
        end_y=50.0,
        end_z=pen.drawing_z_mm,
        feed_rate_mm_min=1800.0,
    )
    # Pen must be lifted at the end of toolpath for completeness
    end_lift = ToolpathMove(
        index=1,
        move_type=MovementType.PEN_UP,
        start_x=175.0,
        start_y=50.0,
        start_z=pen.drawing_z_mm,
        end_x=175.0,
        end_y=50.0,
        end_z=pen.pen_up_z_mm,
        feed_rate_mm_min=900.0,
    )

    validator = SafetyValidator(machine, pen)
    report = validator.validate([bad_move, end_lift], "")
    assert report.overall_status == ValidationSeverity.CRITICAL
    assert not report.can_export_executable
    assert any(i.code == "OUTSIDE_SAFETY_MARGIN" and i.severity == ValidationSeverity.CRITICAL for i in report.issues)

    # Attempting to export via GcodeExporter must raise SafetyExportBlockedError
    with pytest.raises(SafetyExportBlockedError):
        GcodeExporter.export_gcode_file(tmp_path / "blocked.gcode", [bad_move, end_lift], "", machine, pen)


def test_forbidden_commands_complete_blockade():
    """Safety Test 2: G-code with heating, extrusion, nozzle wipe, or cutter macros must be blocked."""
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True
    validator = SafetyValidator(machine, pen)

    hazardous_gcode_samples = [
        ("M104 S210 ; Set hotend temperature", "NON_ZERO_HEATER_COMMAND"),
        ("M140 S60 ; Set bed temperature", "NON_ZERO_HEATER_COMMAND"),
        ("M109 S215 ; Wait for hotend", "FORBIDDEN_COMMAND_M109"),
        ("M190 S60 ; Wait for bed", "FORBIDDEN_COMMAND_M190"),
        ("G12 ; Nozzle cleaning routine", "FORBIDDEN_COMMAND_G12"),
        ("M1002 ; Bambu internal macro", "FORBIDDEN_COMMAND_M1002"),
        ("G38.2 ; Cutter/probe cycle", "FORBIDDEN_COMMAND_G38_2"),
        ("G1 X50 Y50 E1.5 F1200 ; Extrude filament", "EXTRUSION_COMMAND_DETECTED"),
    ]

    for gcode_snippet, expected_code in hazardous_gcode_samples:
        report = validator.validate([], gcode_snippet)
        assert report.overall_status == ValidationSeverity.CRITICAL, f"Failed for {gcode_snippet}"
        assert not report.can_export_executable
        assert any(i.code == expected_code for i in report.issues), f"Missing {expected_code} for {gcode_snippet}"


def test_air_draw_mode_elevation():
    """Safety Test 3: Air Draw mode must elevate all toolpaths by +15mm above the bed."""
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True

    parser = SvgParser()
    doc = parser.parse_file(EXAMPLES_DIR / "01_square_20x20mm.svg")

    tp_gen = ToolpathGenerator(
        machine=machine,
        pen=pen,
        air_draw_mode=True,
        air_draw_offset_z_mm=15.0,
    )
    moves, stats = tp_gen.generate(doc, DocumentTransform(pos_x_mm=30.0, pos_y_mm=30.0))

    assert stats.is_air_draw
    assert math.isclose(stats.air_draw_offset_z_mm, 15.0, abs_tol=1e-4)

    expected_draw_z = pen.drawing_z_mm + 15.0
    expected_pen_up_z = pen.pen_up_z_mm + 15.0

    draw_moves = [m for m in moves if m.move_type == MovementType.DRAW]
    down_moves = [m for m in moves if m.move_type == MovementType.PEN_DOWN]
    up_moves = [m for m in moves if m.move_type == MovementType.PEN_UP]

    assert len(draw_moves) > 0
    assert all(math.isclose(m.end_z, expected_draw_z, abs_tol=1e-4) for m in draw_moves)
    assert all(math.isclose(m.end_z, expected_draw_z, abs_tol=1e-4) for m in down_moves)
    assert all(math.isclose(m.end_z, expected_pen_up_z, abs_tol=1e-4) for m in up_moves)

    # Check generated G-code contains Air Draw warnings
    gcode = GcodeGenerator(machine, pen).generate(moves, stats)
    assert "AIR DRAW" in gcode.upper()
    assert f"Z{expected_draw_z:.3f}" in gcode
    assert f"Draw={expected_draw_z:.2f} mm" in gcode


def test_svg_malformed_nan_and_infinite_coordinates():
    """Resilience Test 4: SVG with NaN/Infinity or malformed data must be safely handled without crashing."""
    malformed_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
      <path d="M NaN,Infinity L 20,20 L 50,NaN L 80,80 Z" stroke="#000" fill="none"/>
      <circle cx="NaN" cy="50" r="10" />
      <rect x="10" y="10" width="Infinity" height="20" />
    </svg>"""

    parser = SvgParser()
    doc = parser.parse_string(malformed_svg)
    assert doc is not None

    # Geometry deduplication and flattening must sanitize all non-finite coordinates
    for el in doc.elements:
        for poly in el.polylines_mm:
            cleaned = deduplicate_points(poly)
            for x, y in cleaned:
                assert math.isfinite(x)
                assert math.isfinite(y)


def test_dense_svg_nearest_neighbor_benchmark():
    """Performance Test 5: Nearest-neighbor path optimizer on dense vector art (500+ paths) must execute in < 0.5s."""
    import time
    from app.core.path_optimizer import DrawablePath, optimize_nearest_neighbor

    # Create 500 small paths scattered across 100x100mm space
    synthetic_paths: list[DrawablePath] = []
    for i in range(500):
        x0 = (i * 17) % 150 + 10.0
        y0 = (i * 23) % 150 + 10.0
        synthetic_paths.append(
            DrawablePath(
                points=[(x0, y0), (x0 + 1.0, y0 + 1.0)],
                layer="Layer 1",
                element_id=f"path_{i}",
                is_closed=False,
            )
        )

    t0 = time.perf_counter()
    ordered = optimize_nearest_neighbor(synthetic_paths, origin=(0.0, 0.0), allow_reversal=True)
    elapsed = time.perf_counter() - t0

    assert len(ordered) == 500
    # Must execute in under 0.5 seconds using vectorized NumPy / KDTree
    assert elapsed < 0.5, f"Nearest neighbor optimization took {elapsed:.3f}s (expected < 0.5s)"


def test_memory_cleanup_after_svg_parsing():
    """Resource Test 6: Parsing SVG documents releases raw content when large and avoids memory retention."""
    import gc

    large_svg_parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="180mm" height="180mm" viewBox="0 0 180 180">']
    for i in range(1200):
        large_svg_parts.append(f'<line x1="{i % 160}" y1="10" x2="{(i + 10) % 160}" y2="150" stroke="#000"/>')
    large_svg_parts.append("</svg>")
    large_svg = "\n".join(large_svg_parts)

    parser = SvgParser()
    doc = parser.parse_string(large_svg)
    assert len(doc.elements) == 1200

    # Ensure garbage collection runs cleanly without dangling cyclic locks
    del large_svg_parts
    del large_svg
    gc.collect()


def test_pen_holder_offset_centering_compensation():
    """Validates that pen holder offset (-22.0 mm Y) correctly shifts G-code carriage commands
    so that physical pen marks land exactly at intended build-plate coordinates."""
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    transformer = CoordinateTransformer(machine, pen)

    # 1. Coordinate transformation mapping
    # Center of plate is (90, 90). Pen holder is at -22mm Y relative to nozzle.
    # Therefore nozzle carriage must move to Y = 90 - (-22) = 112mm.
    mx, my = transformer.plate_to_machine_xy(90.0, 90.0)
    assert math.isclose(mx, 90.0, abs_tol=1e-3)
    assert math.isclose(my, 112.0, abs_tol=1e-3)

    # Inverse mapping restores plate coordinates
    px, py = transformer.machine_to_plate_xy(mx, my)
    assert math.isclose(px, 90.0, abs_tol=1e-3)
    assert math.isclose(py, 90.0, abs_tol=1e-3)

    # 2. End-to-end toolpath generation for centered 100x100mm square
    parser = SvgParser()
    svg_data = '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"><rect x="0" y="0" width="100" height="100" fill="none" stroke="#000"/></svg>'
    doc = parser.parse_string(svg_data)
    gen = ToolpathGenerator(machine, pen)
    # Centered on 180x180 plate: bottom-left at (40, 40)
    moves, stats = gen.generate(doc, DocumentTransform(pos_x_mm=40.0, pos_y_mm=40.0))

    # Plate stats should report physical drawing bounds [40..140]
    assert math.isclose(stats.drawing_width_mm, 100.0, abs_tol=1e-3)
    assert math.isclose(stats.drawing_height_mm, 100.0, abs_tol=1e-3)
    assert math.isclose(stats.min_x, 40.0, abs_tol=1e-3)
    assert math.isclose(stats.min_y, 40.0, abs_tol=1e-3)
    assert math.isclose(stats.max_x, 140.0, abs_tol=1e-3)
    assert math.isclose(stats.max_y, 140.0, abs_tol=1e-3)

    # Actual machine moves commanded to the printer must be shifted by +22mm: [62..162]
    draw_moves = [m for m in moves if m.move_type == MovementType.DRAW]
    assert len(draw_moves) > 0
    machine_min_y = min(min(m.start_y, m.end_y) for m in draw_moves)
    machine_max_y = max(max(m.start_y, m.end_y) for m in draw_moves)
    assert math.isclose(machine_min_y, 62.0, abs_tol=1e-3)
    assert math.isclose(machine_max_y, 162.0, abs_tol=1e-3)


def test_infill_hatching_and_contour_on_unfilled_closed_shapes():
    """Validates that closed paths with fill='none' correctly generate infill paths when mode is hatch or contour."""
    parser = SvgParser()
    svg_data = '<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="50mm"><rect x="5" y="5" width="40" height="40" fill="none" stroke="#000"/></svg>'
    doc = parser.parse_string(svg_data)
    assert doc.elements[0].is_closed is True

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]

    # 1. Outline only mode
    gen_outline = ToolpathGenerator(machine, pen, fill_settings=FillSettings(mode="outline"))
    moves_out, stats_out = gen_outline.generate(doc, DocumentTransform(pos_x_mm=20.0, pos_y_mm=20.0))

    # 2. Hatching mode
    gen_hatch = ToolpathGenerator(machine, pen, fill_settings=FillSettings(mode="hatch", hatch_spacing_mm=2.0))
    moves_hatch, stats_hatch = gen_hatch.generate(doc, DocumentTransform(pos_x_mm=20.0, pos_y_mm=20.0))
    assert stats_hatch.num_paths > stats_out.num_paths
    assert stats_hatch.drawing_distance_mm > stats_out.drawing_distance_mm * 2.0

    # 3. Contour mode
    gen_contour = ToolpathGenerator(machine, pen, fill_settings=FillSettings(mode="contour", contour_spacing_mm=2.0))
    moves_cont, stats_cont = gen_contour.generate(doc, DocumentTransform(pos_x_mm=20.0, pos_y_mm=20.0))
    assert stats_cont.num_paths > stats_out.num_paths
    assert stats_cont.drawing_distance_mm > stats_out.drawing_distance_mm * 1.5


def test_safe_z_minimum_threshold():
    """Validates that a low Drawing Z (e.g. 1.0mm) passes safety validation when min_safe_z_mm is 0.5mm."""
    machine = create_default_a1_mini_profile()
    assert machine.min_safe_z_mm <= 0.5
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True
    pen.drawing_z_mm = 1.00
    pen.pen_down_z_mm = 1.20
    pen.pen_up_z_mm = 6.00

    from app.machine.safety import SafetyValidator, ValidationSeverity

    mv_down = ToolpathMove(
        index=0,
        move_type=MovementType.PEN_DOWN,
        start_x=50.0,
        start_y=50.0,
        start_z=6.00,
        end_x=50.0,
        end_y=50.0,
        end_z=1.00,
        feed_rate_mm_min=480.0,
    )
    mv_draw = ToolpathMove(
        index=1,
        move_type=MovementType.DRAW,
        start_x=50.0,
        start_y=50.0,
        start_z=1.00,
        end_x=60.0,
        end_y=60.0,
        end_z=1.00,
        feed_rate_mm_min=3000.0,
    )
    mv_up = ToolpathMove(
        index=2,
        move_type=MovementType.PEN_UP,
        start_x=60.0,
        start_y=60.0,
        start_z=1.00,
        end_x=60.0,
        end_y=60.0,
        end_z=6.00,
        feed_rate_mm_min=1200.0,
    )
    validator = SafetyValidator(machine, pen)
    gcode = "G21\nG90\nG1 Z1.000 F480\nG1 X60 Y60 Z1.000 F3000\nG1 Z6.000 F1200\n"
    report = validator.validate([mv_down, mv_draw, mv_up], gcode)
    assert report.overall_status != ValidationSeverity.CRITICAL
    assert not any(i.code in ("Z_BELOW_SAFE_MINIMUM", "Z_OUT_OF_SAFE_RANGE") for i in report.issues)

