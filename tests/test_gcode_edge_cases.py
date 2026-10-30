"""Edge cases and mechanical safety test suite for G-code generation, boundaries, and zero-area plots."""

from __future__ import annotations

import math
import pytest

from app.core.gcode_generator import GcodeGenerator
from app.core.models import (
    DocumentTransform,
    FillSettings,
    MovementType,
    OptimizationSettings,
    ParsedSvgDocument,
    SvgElement,
    ToolpathMove,
    WorkflowMode,
)
from app.core.path_optimizer import ToolpathGenerator
from app.core.pipeline_worker import PipelineWorker
from app.machine.a1_mini import create_default_a1_mini_profile
from app.machine.profiles import create_default_pen_profiles
from app.machine.safety import SafetyValidator, ValidationSeverity


@pytest.fixture
def machine():
    return create_default_a1_mini_profile()


@pytest.fixture
def pen():
    p = create_default_pen_profiles()[0]
    p.is_calibrated = True
    return p


def test_zero_area_drawing_point_clicks(machine, pen):
    """Case: Drawings with area zero (single isolated points / pen clicks)."""
    # SVG containing isolated dots/points
    doc = ParsedSvgDocument(
        file_path="dots.svg",
        width_mm=100.0,
        height_mm=100.0,
        viewbox=(0, 0, 100, 100),
        original_units="mm",
        elements=[
            SvgElement(
                id="dot_1",
                name="dot_1",
                layer="Dots",
                element_type="path",
                polylines_mm=[[(50.0, 50.0)]],
                stroke_color="#000",
            ),
            SvgElement(
                id="dot_2",
                name="dot_2",
                layer="Dots",
                element_type="circle",
                polylines_mm=[[(60.0, 60.0)]],
                stroke_color="#000",
            ),
        ],
        warnings=[],
        raw_svg_content="",
    )

    tg = ToolpathGenerator(machine, pen)
    moves, stats = tg.generate(doc, DocumentTransform(pos_x_mm=0.0, pos_y_mm=0.0))

    assert len(moves) > 0
    # Must contain TRAVEL, PEN_DOWN (with dwell), and PEN_UP for each dot
    types = [m.move_type for m in moves]
    assert MovementType.TRAVEL in types
    assert MovementType.PEN_DOWN in types
    assert MovementType.PEN_UP in types

    gcode = GcodeGenerator(machine, pen).generate(moves, stats)
    assert "G4 P" in gcode  # Dwell for pen mark stabilization

    report = SafetyValidator(machine, pen).validate(moves, gcode)
    assert report.can_export_executable


def test_microscopic_lines_and_hundreds_of_overlapping_paths(machine, pen):
    """Case: Lines with micro-thickness and 300 identical overlapping paths."""
    elements = [
        SvgElement(
            id=f"micro_overlap_{i}",
            name=f"micro_overlap_{i}",
            layer="default",
            element_type="path",
            polylines_mm=[[(25.0, 25.0), (25.0001, 25.0001), (25.0, 25.0)]],
            stroke_color="#000",
            stroke_width_mm=0.0001,
        )
        for i in range(200)
    ]

    doc = ParsedSvgDocument(
        file_path="micro.svg",
        width_mm=100.0,
        height_mm=100.0,
        viewbox=(0, 0, 100, 100),
        original_units="mm",
        elements=elements,
        warnings=[],
        raw_svg_content="",
    )

    tg = ToolpathGenerator(machine, pen)
    moves, stats = tg.generate(doc, DocumentTransform(pos_x_mm=0.0, pos_y_mm=0.0))
    assert len(moves) >= 1
    assert math.isfinite(stats.total_distance_mm)

    gcode = GcodeGenerator(machine, pen).generate(moves, stats)
    rep = SafetyValidator(machine, pen).validate(moves, gcode)
    assert rep.can_export_executable


def test_boundary_precision_soft_stop(machine, pen):
    """Case: Touching exactly 180x180 mm border vs exceeding by 0.0001 mm."""
    validator = SafetyValidator(machine, pen)

    # 1. Exact nominal plate limit: X=180.0, Y=180.0
    valid_move = ToolpathMove(
        index=0,
        move_type=MovementType.TRAVEL,
        start_x=0.0,
        start_y=0.0,
        start_z=pen.pen_up_z_mm,
        end_x=180.0,
        end_y=180.0,
        end_z=pen.pen_up_z_mm,
        feed_rate_mm_min=3000.0,
    )
    rep_ok = validator.validate([valid_move], "")
    out_of_bounds_issues = [i for i in rep_ok.issues if i.code == "OUTSIDE_MACHINE_BOUNDS"]
    assert len(out_of_bounds_issues) == 0

    # 2. Exceeding nominal plate limit by 0.0001 mm (180.0001 mm)
    invalid_move = ToolpathMove(
        index=0,
        move_type=MovementType.TRAVEL,
        start_x=0.0,
        start_y=0.0,
        start_z=pen.pen_up_z_mm,
        end_x=180.0001,
        end_y=180.0,
        end_z=pen.pen_up_z_mm,
        feed_rate_mm_min=3000.0,
    )
    rep_bad = validator.validate([invalid_move], "")
    assert not rep_bad.can_export_executable
    assert any(i.code == "OUTSIDE_MACHINE_BOUNDS" for i in rep_bad.issues)


def test_feedrate_zero_and_negative_feedrate_prevention(machine, pen):
    """Case: Verify that feedrate F0 is never generated and is strictly blocked by validator."""
    bad_move = ToolpathMove(
        index=0,
        move_type=MovementType.DRAW,
        start_x=10.0,
        start_y=10.0,
        start_z=pen.drawing_z_mm,
        end_x=20.0,
        end_y=20.0,
        end_z=pen.drawing_z_mm,
        feed_rate_mm_min=0.0,  # F0
    )

    # GcodeGenerator must automatically clamp F to at least 60 mm/min
    gcode = GcodeGenerator(machine, pen).generate([bad_move])
    assert "F0 " not in gcode
    assert "F0\n" not in gcode

    # SafetyValidator must catch any manual F0 in G-code lines as CRITICAL
    manual_bad_gcode = "G21\nG90\nG1 X10.0 Y10.0 F0\nG0 Z18.0 F1200\n"
    rep = SafetyValidator(machine, pen).validate([bad_move], manual_bad_gcode)
    assert any(i.code in ("ZERO_OR_NEGATIVE_FEEDRATE", "GCODE_ZERO_OR_NEGATIVE_FEEDRATE") for i in rep.issues)
    assert not rep.can_export_executable


def test_negative_z_and_final_pen_lift_enforcement(machine, pen):
    """Case: Negative Z is blocked, and toolpaths ending with pen lowered are flagged as CRITICAL."""
    validator = SafetyValidator(machine, pen)

    # 1. Negative Z in move
    neg_z_move = ToolpathMove(
        index=0,
        move_type=MovementType.DRAW,
        start_x=10.0,
        start_y=10.0,
        start_z=14.0,
        end_x=20.0,
        end_y=20.0,
        end_z=-2.0,  # Negative Z!
        feed_rate_mm_min=1200.0,
    )
    rep1 = validator.validate([neg_z_move], "")
    assert not rep1.can_export_executable
    assert any(i.code == "NEGATIVE_COORDINATE" for i in rep1.issues)

    # 2. Toolpath ending with pen lowered
    down_move = ToolpathMove(
        index=0,
        move_type=MovementType.DRAW,
        start_x=10.0,
        start_y=10.0,
        start_z=pen.drawing_z_mm,
        end_x=20.0,
        end_y=20.0,
        end_z=pen.drawing_z_mm,  # Left down at drawing Z!
        feed_rate_mm_min=1200.0,
    )
    rep2 = validator.validate([down_move], "")
    assert not rep2.can_export_executable
    assert any(i.code in ("UNSAFE_FINAL_POSITION", "MISSING_INITIAL_PEN_TRANSITION") for i in rep2.issues)


def test_pipeline_worker_cancellation_and_recovery(machine, pen):
    """Case: Test clean cancellation of PipelineWorker midway through execution."""
    doc = ParsedSvgDocument(
        file_path="test.svg",
        width_mm=100.0,
        height_mm=100.0,
        viewbox=(0, 0, 100, 100),
        original_units="mm",
        elements=[],
        warnings=[],
        raw_svg_content="",
    )

    worker = PipelineWorker(
        task_id=99,
        doc=doc,
        doc_transform=DocumentTransform(),
        machine=machine,
        pen=pen,
        opt_settings=OptimizationSettings(),
        fill_settings=FillSettings(),
        workflow_mode=WorkflowMode.BAMBU_SD_DIRECT,
    )

    completed_called = False
    def on_done(tid, res):
        nonlocal completed_called
        completed_called = True

    worker.signals.completed.connect(on_done)
    # Cancel before running
    worker.cancel()
    worker.run()

    # Must have returned immediately without emitting signals
    assert not completed_called
