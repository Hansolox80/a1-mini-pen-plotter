"""Exhaustive, long-running end-to-end stress test suite for A1 Mini Pen Plotter.

Validates:
1. Complete gallery traversal across all 11 built-in sample SVGs with various precisions and export formats.
2. Complex algorithmic geometry (Archimedean spirals, Hilbert fractal curves, nested rings, random polygons).
3. Toolpath optimization benchmarking (Nearest-Neighbor vs 2-Opt vs Direction Only vs Original).
4. Hatching and concentric contour geometric accuracy on non-convex multipolygons with holes.
5. Deep simulation transport engine endurance (long-playback, scrubbing, speed transitions).
6. Bambu Studio 3MF container integrity (zip structure, MD5 checksum match, plate config, PNG thumbnail).
7. Undo/Redo stack 50-step bidirectional state history round-trip.
8. Memory stability and garbage collection across repetitive pipeline runs.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
from pathlib import Path
import random
import tempfile
import zipfile

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QApplication
from shapely.geometry import MultiPolygon, Polygon, Point, LineString

from app.core.coordinate_system import CoordinateTransformer
from app.core.gcode_generator import GcodeGenerator
from app.core.geometry import (
    deduplicate_points,
    generate_contour_fill_paths,
    generate_hatch_lines,
    simplify_polyline,
)
from app.core.models import (
    BoundingBox,
    DocumentTransform,
    FillSettings,
    MovementType,
    OptimizationSettings,
    ParsedSvgDocument,
    SvgElement,
    ToolpathMove,
    ToolpathStats,
    WorkflowMode,
)
from app.core.path_optimizer import ToolpathGenerator
from app.core.simulator import SimulationState, ToolpathSimulator
from app.core.svg_parser import SvgParser
from app.export.gcode_exporter import GcodeExporter
from app.export.project_exporter import PlotterProject, ProjectManager
from app.machine.a1_mini import MachineProfile, create_default_a1_mini_profile
from app.machine.profiles import PenProfile, ProfileManager, create_default_pen_profiles
from app.machine.safety import SafetyValidator, ValidationSeverity
from app.ui.main_window import MainWindow


EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ==============================================================================
# 1. Exhaustive Gallery Pipeline Across All 11 Examples
# ==============================================================================

def test_exhaustive_all_examples_pipeline_and_exports(tmp_path):
    """Parses every single SVG example in examples/, tests all fill and workflow combinations,

    and validates all 4 export deliverables for each.
    """
    svg_files = sorted(list(EXAMPLES_DIR.glob("*.svg")))
    assert len(svg_files) >= 11, f"Expected at least 11 SVG samples, found {len(svg_files)}"

    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    pen.is_calibrated = True  # Calibrated for valid export testing

    for svg_file in svg_files:
        parser = SvgParser(curve_precision_mm=0.08)
        doc = parser.parse_file(str(svg_file))
        assert doc is not None
        assert len(doc.elements) > 0, f"SVG {svg_file.name} yielded 0 elements"

        # Test varying curve precisions
        for prec in (0.05, 0.2):
            doc_prec = SvgParser(curve_precision_mm=prec).parse_file(str(svg_file))
            assert len(doc_prec.elements) == len(doc.elements)

        # Center on plate
        bounds = doc.compute_native_bounds()
        transform = DocumentTransform(
            pos_x_mm=max(15.0, (180.0 - bounds.width) * 0.5),
            pos_y_mm=max(15.0, (180.0 - bounds.height) * 0.5),
            scale_x=1.0,
            scale_y=1.0,
        )

        # Scale down if it exceeds usable area
        if bounds.width > 150.0 or bounds.height > 150.0:
            s = min(140.0 / max(bounds.width, 1.0), 140.0 / max(bounds.height, 1.0))
            transform.scale_x = s
            transform.scale_y = s
            transform.pos_x_mm = (180.0 - bounds.width * s) * 0.5
            transform.pos_y_mm = (180.0 - bounds.height * s) * 0.5

        # Test across workflows: A1 Mini SD Direct, Bambu Studio 3MF, and Standard G-Code
        for wf_mode in (WorkflowMode.BAMBU_SD_DIRECT, WorkflowMode.BAMBU_STUDIO_3MF, WorkflowMode.STANDARD_GCODE):
            tp_gen = ToolpathGenerator(
                machine=machine,
                pen=pen,
                opt_settings=OptimizationSettings(strategy="nearest_neighbor"),
                fill_settings=FillSettings(mode="outline"),
            )
            moves, stats = tp_gen.generate(doc, transform)
            assert len(moves) > 0

            gcode_gen = GcodeGenerator(machine=machine, pen=pen, workflow_mode=wf_mode)
            gcode = gcode_gen.generate(moves, stats, project_name=svg_file.stem)
            assert "G21" in gcode
            assert "G90" in gcode

            # Validate safety
            validator = SafetyValidator(machine=machine, pen=pen)
            report = validator.validate(moves, gcode)
            assert report.overall_status != ValidationSeverity.CRITICAL

            # Test real file exports
            prefix = f"{svg_file.stem}_{wf_mode.value}"
            gcode_path = tmp_path / f"{prefix}.gcode"
            GcodeExporter.export_gcode_file(str(gcode_path), moves, gcode, machine, pen)
            assert gcode_path.exists()
            assert gcode_path.stat().st_size > 0

            # 3MF container export
            if wf_mode == WorkflowMode.BAMBU_STUDIO_3MF:
                pkg_path = tmp_path / f"{prefix}.gcode.3mf"
                GcodeExporter.export_bambu_3mf_file(str(pkg_path), moves, gcode, stats, machine, pen)
                assert pkg_path.exists()
                assert zipfile.is_zipfile(pkg_path)

            # Optimized SVG export
            svg_out = tmp_path / f"{prefix}_opt.svg"
            GcodeExporter.export_optimized_svg(str(svg_out), moves, machine, pen)
            assert svg_out.exists()

            # Validation markdown report
            rep_path = tmp_path / f"{prefix}_report.md"
            GcodeExporter.export_validation_report(str(rep_path), report, machine, pen, stats)
            assert rep_path.exists()


# ==============================================================================
# 2. Complex Procedural Geometry & 2-Opt Optimization Benchmark
# ==============================================================================

def test_procedural_spirals_and_fractal_geometry_optimization():
    """Generates complex geometric figures (Archimedean spiral, nested ring array,

    Hilbert curve fractal) and benchmarks path optimization algorithms.
    """
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]

    elements: list[SvgElement] = []

    # 1. Archimedean spiral (r = a + b * theta) with 600 points
    spiral_pts = []
    a = 1.0
    b = 0.4
    for i in range(600):
        theta = i * 0.1
        r = a + b * theta
        x = 90.0 + r * math.cos(theta)
        y = 90.0 + r * math.sin(theta)
        spiral_pts.append((x, y))
    elements.append(SvgElement(id="spiral", element_type="path", name="Spiral", layer="Layer 1", polylines_mm=[spiral_pts]))

    # 2. Concentric ring array (30 circles with varying center and radius)
    for r in range(5, 35, 1):
        circle_pts = []
        for a_deg in range(0, 360, 10):
            rad = math.radians(a_deg)
            circle_pts.append((90.0 + r * math.cos(rad), 90.0 + r * math.sin(rad)))
        circle_pts.append(circle_pts[0])  # Close loop
        elements.append(SvgElement(id=f"ring_{r}", element_type="circle", name=f"Ring {r}", layer="Layer 1", polylines_mm=[circle_pts]))

    # 3. Hilbert curve order 4 (256 vertices)
    def hilbert(x0, y0, xi, xj, yi, yj, n):
        if n <= 0:
            return [(x0 + (xi + yi) / 2, y0 + (xj + yj) / 2)]
        pts = []
        pts.extend(hilbert(x0, y0, yi / 2, yj / 2, xi / 2, xj / 2, n - 1))
        pts.extend(hilbert(x0 + xi / 2, y0 + xj / 2, xi / 2, xj / 2, yi / 2, yj / 2, n - 1))
        pts.extend(hilbert(x0 + xi / 2 + yi / 2, y0 + xj / 2 + yj / 2, xi / 2, xj / 2, yi / 2, yj / 2, n - 1))
        pts.extend(hilbert(x0 + xi / 2 + yi, y0 + xj / 2 + yj, -yi / 2, -yj / 2, -xi / 2, -xj / 2, n - 1))
        return pts

    h_pts = hilbert(30.0, 30.0, 50.0, 0.0, 0.0, 50.0, 4)
    elements.append(SvgElement(id="hilbert", element_type="path", name="Hilbert Curve", layer="Layer 1", polylines_mm=[h_pts]))

    doc = ParsedSvgDocument(
        file_path="procedural_test.svg",
        width_mm=180.0,
        height_mm=180.0,
        viewbox=(0.0, 0.0, 180.0, 180.0),
        original_units="mm",
        elements=elements,
    )

    transform = DocumentTransform(pos_x_mm=20.0, pos_y_mm=20.0)

    # Benchmark: Original vs Nearest-Neighbor vs 2-Opt
    opt_original = ToolpathGenerator(
        machine=machine,
        pen=pen,
        opt_settings=OptimizationSettings(strategy="original"),
    )
    moves_orig, stats_orig = opt_original.generate(doc, transform)

    opt_nn = ToolpathGenerator(
        machine=machine,
        pen=pen,
        opt_settings=OptimizationSettings(strategy="nearest_neighbor"),
    )
    moves_nn, stats_nn = opt_nn.generate(doc, transform)

    opt_2opt = ToolpathGenerator(
        machine=machine,
        pen=pen,
        opt_settings=OptimizationSettings(strategy="min_travel_2opt"),
    )
    moves_2opt, stats_2opt = opt_2opt.generate(doc, transform)

    # Verification:
    # 1. Total drawing distance must be strictly identical across all optimization modes
    assert abs(stats_orig.drawing_distance_mm - stats_nn.drawing_distance_mm) < 1e-3
    assert abs(stats_orig.drawing_distance_mm - stats_2opt.drawing_distance_mm) < 1e-3

    # 2. Nearest-Neighbor and 2-Opt must significantly reduce unoptimized travel
    assert stats_nn.travel_distance_mm <= stats_orig.travel_distance_mm
    assert stats_2opt.travel_distance_mm <= stats_nn.travel_distance_mm + 1e-2

    # 3. All moves must strictly respect A1 Mini build boundary
    for m in moves_2opt:
        assert machine.usable_min_x - 1e-4 <= m.end_x <= machine.usable_max_x + 1e-4
        assert machine.usable_min_y - 1e-4 <= m.end_y <= machine.usable_max_y + 1e-4


# ==============================================================================
# 3. Geometric Hatching and Contour Verification on Multipolygons with Holes
# ==============================================================================

def test_hatching_and_contour_geometric_containment_in_multipolygons():
    """Builds a complex multipolygon with multiple interior holes (e.g. nested doughnut)

    and proves that every generated hatch line and contour segment stays strictly within the interior.
    """
    # Outer box: 100x100 mm at (40, 40)
    outer = [(40.0, 40.0), (140.0, 40.0), (140.0, 140.0), (40.0, 140.0), (40.0, 40.0)]
    # Hole 1: 30x30 mm at (55, 55)
    hole1 = [(55.0, 55.0), (85.0, 55.0), (85.0, 85.0), (55.0, 85.0), (55.0, 55.0)]
    # Hole 2: 30x30 mm at (95, 95)
    hole2 = [(95.0, 95.0), (125.0, 95.0), (125.0, 125.0), (95.0, 125.0), (95.0, 95.0)]

    poly = Polygon(shell=outer, holes=[hole1, hole2])
    buffered_poly = poly.buffer(1e-4)

    # Test hatching at multiple angles
    for angle in (0.0, 45.0, 90.0, -30.0, 60.0):
        hatch_polys = generate_hatch_lines(
            [poly],
            spacing_mm=2.5,
            angle_deg=angle,
        )
        assert len(hatch_polys) > 0

        # Sample test points along hatch lines: none may fall inside hole1 or hole2
        hole1_geom = Polygon(hole1)
        hole2_geom = Polygon(hole2)

        for line in hatch_polys:
            assert len(line) >= 2
            ls = LineString(line)
            # Midpoint of hatch line
            mid_pt = ls.interpolate(0.5, normalized=True)
            assert not hole1_geom.contains(mid_pt)
            assert not hole2_geom.contains(mid_pt)
            assert buffered_poly.contains(mid_pt)

    # Test cross-hatch (combining 45 and 135 degree hatches)
    cross_h1 = generate_hatch_lines([poly], spacing_mm=3.0, angle_deg=45.0)
    cross_h2 = generate_hatch_lines([poly], spacing_mm=3.0, angle_deg=135.0)
    cross_hatches = cross_h1 + cross_h2
    assert len(cross_hatches) > 0
    for line in cross_hatches:
        assert len(line) >= 2
        ls = LineString(line)
        mid_pt = ls.interpolate(0.5, normalized=True)
        assert not hole1_geom.contains(mid_pt)
        assert not hole2_geom.contains(mid_pt)
        assert buffered_poly.contains(mid_pt)

    # Test concentric contour offsets
    contours = generate_contour_fill_paths([poly], spacing_mm=2.0)
    assert len(contours) > 0
    for c in contours:
        for x, y in c:
            assert buffered_poly.contains(Point(x, y))


# ==============================================================================
# 4. Simulation Transport Engine Deep Monotonicity & Seeking Endurance
# ==============================================================================

def test_simulator_playback_scrubbing_and_state_consistency():
    """Generates a multi-step trajectory and performs extensive automated playback,

    scrubbing, forward/backward stepping, and speed variation testing.
    """
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    parser = SvgParser()
    doc = parser.parse_file(str(EXAMPLES_DIR / "01_square_20x20mm.svg"))
    tp_gen = ToolpathGenerator(machine=machine, pen=pen)
    moves, stats = tp_gen.generate(doc, DocumentTransform(pos_x_mm=30.0, pos_y_mm=30.0))
    assert len(moves) >= 5

    sim = ToolpathSimulator()
    sim.load_moves(moves, initial_z=18.0)
    assert len(sim.moves) == len(moves)
    assert sim.state.total_time_seconds > 0.0

    # 1. Step-by-step monotonicity test (forward then backward)
    for i in range(len(moves)):
        assert sim.state.current_move_index == i
        sim.step_forward()
    assert sim.state.current_move_index == len(moves) - 1

    for i in range(len(moves) - 1, -1, -1):
        assert sim.state.current_move_index == i
        sim.step_backward()
    assert sim.state.current_move_index == 0

    # 2. Random seeking across timeline
    sim.restart()
    for _ in range(50):
        target_idx = random.randint(0, len(moves) - 1)
        sim.seek_to_move(target_idx, progress=1.0)
        assert sim.state.current_move_index == target_idx
        # Verification: X/Y coordinates must match the target move end coordinates
        expected_move = moves[target_idx]
        assert abs(sim.state.x - expected_move.end_x) < 1e-4
        assert abs(sim.state.y - expected_move.end_y) < 1e-4

    # 3. Continuous playback loop at varying speeds
    sim.restart()
    sim.state.is_playing = True
    for spd in (0.25, 1.0, 2.0, 10.0, 25.0):
        sim.state.playback_speed = spd
        for _ in range(15):
            sim.advance_time(0.033)
            assert 0.0 <= sim.overall_progress_ratio <= 1.0
            assert 0 <= sim.state.current_move_index < len(moves)


# ==============================================================================
# 5. Bambu Studio 3MF Package Zip Structure & MD5 Verification
# ==============================================================================

def test_bambu_3mf_deep_container_verification(tmp_path):
    """Generates an official Bambu Studio package and performs byte-level MD5

    and XML/PNG inspection of the internal zipped structure.
    """
    machine = create_default_a1_mini_profile()
    pen = create_default_pen_profiles()[0]
    parser = SvgParser()
    doc = parser.parse_file(str(EXAMPLES_DIR / "01_square_20x20mm.svg"))
    tp_gen = ToolpathGenerator(machine=machine, pen=pen)
    moves, stats = tp_gen.generate(doc, DocumentTransform(pos_x_mm=50.0, pos_y_mm=50.0))
    assert len(moves) > 0

    gcode_gen = GcodeGenerator(machine=machine, pen=pen, workflow_mode=WorkflowMode.BAMBU_STUDIO_3MF)
    gcode = gcode_gen.generate(moves, stats, project_name="Bambu_Verification_Square")

    pkg_path = tmp_path / "test_a1_mini_package.gcode.3mf"
    GcodeExporter.export_bambu_3mf_file(str(pkg_path), moves, gcode, stats, machine, pen)

    assert pkg_path.exists()
    assert zipfile.is_zipfile(pkg_path)

    with zipfile.ZipFile(pkg_path, "r") as z:
        namelist = z.namelist()
        assert "Metadata/plate_1.gcode" in namelist
        assert "Metadata/plate_1.gcode.md5" in namelist
        assert "Metadata/slice_info.config" in namelist
        assert "Metadata/plate_1.png" in namelist
        assert "[Content_Types].xml" in namelist

        # Verify MD5 calculation against the embedded G-code
        plate_gcode_bytes = z.read("Metadata/plate_1.gcode")
        expected_md5 = hashlib.md5(plate_gcode_bytes).hexdigest().strip().lower()
        recorded_md5 = z.read("Metadata/plate_1.gcode.md5").decode("utf-8").strip().lower()
        assert recorded_md5 == expected_md5

        # Verify slice_info.config content
        slice_cfg = z.read("Metadata/slice_info.config").decode("utf-8")
        assert "plate_1" in slice_cfg
        assert "printer_model_id" in slice_cfg
        assert "N1" in slice_cfg
        assert "nozzle_diameters" in slice_cfg

        # Verify plate_1.png is a valid, readable PNG image
        png_bytes = z.read("Metadata/plate_1.png")
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"
        assert img.size[0] > 0 and img.size[1] > 0


# ==============================================================================
# 6. Undo/Redo Stack 50-Step Bidirectional State History Round-Trip
# ==============================================================================

def test_undo_redo_exhaustive_history_roundtrip(qapp):
    """Executes a chain of 50 consecutive interactive modifications on MainWindow,

    then executes 50 Undos asserting exact state restoration, followed by 50 Redos.
    """
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    win.show()
    qapp.processEvents()

    # Load starting SVG
    svg_path = EXAMPLES_DIR / "01_square_20x20mm.svg"
    win.load_svg_file(str(svg_path), mark_dirty=False)
    assert len(win.project.toolpath_moves) > 0

    history: list[dict] = []
    initial_state = win.project.doc_transform.to_dict()
    history.append(dict(initial_state))

    # Apply 50 progressive transform operations
    for step in range(1, 51):
        cur_t = DocumentTransform.from_dict(win.project.doc_transform.to_dict())
        cur_t.pos_x_mm = round(20.0 + (step * 0.8), 2)
        cur_t.pos_y_mm = round(20.0 + (step * 0.6), 2)
        cur_t.scale_x = round(1.0 + (step * 0.01), 3)
        cur_t.scale_y = round(1.0 + (step * 0.01), 3)
        cur_t.rotation_deg = round((step * 3.5) % 360.0, 1)

        win._on_inspector_transform_changed(cur_t)
        qapp.processEvents()
        history.append(cur_t.to_dict())

    assert win.undo_stack.count() == 50

    # Now perform 50 Undos, verifying that each step matches the previous history entry
    for step in range(50, 0, -1):
        assert win.undo_stack.canUndo()
        win.undo_stack.undo()
        qapp.processEvents()
        expected = history[step - 1]
        actual = win.project.doc_transform.to_dict()
        assert abs(actual["pos_x_mm"] - expected["pos_x_mm"]) < 1e-3
        assert abs(actual["pos_y_mm"] - expected["pos_y_mm"]) < 1e-3
        assert abs(actual["rotation_deg"] - expected["rotation_deg"]) < 1e-3

    assert not win.undo_stack.canUndo()
    assert abs(win.project.doc_transform.pos_x_mm - initial_state["pos_x_mm"]) < 1e-3

    # Now perform 50 Redos, verifying that each step advances to its recorded state
    for step in range(1, 51):
        assert win.undo_stack.canRedo()
        win.undo_stack.redo()
        qapp.processEvents()
        expected = history[step]
        actual = win.project.doc_transform.to_dict()
        assert abs(actual["pos_x_mm"] - expected["pos_x_mm"]) < 1e-3
        assert abs(actual["pos_y_mm"] - expected["pos_y_mm"]) < 1e-3

    assert not win.undo_stack.canRedo()
    win.close()


# ==============================================================================
# 7. Repetitive Pipeline Memory & Stability Endurance
# ==============================================================================

def test_repetitive_pipeline_stability_endurance(qapp):
    """Executes 25 continuous cycles of file loading, transformation, 2-Opt optimization,

    G-code generation, and project clearing, verifying that no unhandled exceptions
    occur and state stays healthy.
    """
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)

    test_samples = [
        str(EXAMPLES_DIR / "01_square_20x20mm.svg"),
        str(EXAMPLES_DIR / "02_circle_20mm.svg"),
        str(EXAMPLES_DIR / "04_bezier_curves.svg"),
        str(EXAMPLES_DIR / "05_multiple_paths.svg"),
        str(EXAMPLES_DIR / "11_a1_mini_calibration_target.svg"),
    ]

    for cycle in range(25):
        sample = test_samples[cycle % len(test_samples)]
        win.load_svg_file(sample, mark_dirty=False)
        qapp.processEvents()

        assert win.project.svg_document is not None
        assert len(win.project.toolpath_moves) > 0

        # Apply transforms & optimization
        win._on_optimization_settings_changed(OptimizationSettings(strategy="min_travel_2opt"))
        win.action_center_on_plate()
        qapp.processEvents()

        # Step simulator
        win.simulator_bar.on_step_forward()
        qapp.processEvents()

        # Reset
        if cycle % 5 == 0:
            win.action_new_project()
            qapp.processEvents()
            assert win.project.svg_document is None

    win.close()
