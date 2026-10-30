"""Fuzzing and corrupted input test suite for SvgParser, Geometry engine, and Pipeline."""

from __future__ import annotations

import math
from pathlib import Path
import pytest

from app.core.coordinate_system import CoordinateTransformer
from app.core.gcode_generator import GcodeGenerator
from app.core.geometry import (
    flatten_cubic_bezier,
    flatten_quadratic_bezier,
    flatten_svg_arc,
)
from app.core.models import DocumentTransform, FillSettings, OptimizationSettings, WorkflowMode
from app.core.path_optimizer import ToolpathGenerator
from app.core.svg_parser import (
    SvgParser,
    apply_matrix_to_polyline,
    matrix_max_scale,
    parse_transform_matrix,
)
from app.machine.a1_mini import create_default_a1_mini_profile
from app.machine.profiles import create_default_pen_profiles
from app.machine.safety import SafetyValidator


@pytest.fixture
def machine():
    return create_default_a1_mini_profile()


@pytest.fixture
def pen():
    p = create_default_pen_profiles()[0]
    p.is_calibrated = True
    return p


def test_fuzz_corrupted_xml_and_empty_inputs(machine, pen):
    """Verifies that empty, non-XML, truncated, and malformed inputs never raise unhandled exceptions."""
    parser = SvgParser()
    malformed_samples = [
        "",
        "   \n\t  ",
        "This is not XML at all",
        "<html><body><h1>Not SVG</h1></body></html>",
        "<svg><path d='M 10 10 L 20 20'",  # Unclosed XML tag
        "<svg><g><path d='M 0 0'</g></svg>",  # Malformed tag syntax
        "<?xml version='1.0'?><svg><![CDATA[unclosed cdata",
        "\x00\x01\x02\x03\xff\xfe\xfd",  # Binary junk
        "<svg><defs><style>/* unclosed comment </style></defs></svg>",
        "<svg viewBox='0 0 100 100'><path d=''></path></svg>",  # Empty path
    ]

    for sample in malformed_samples:
        doc = parser.parse_string(sample)
        assert doc is not None
        assert doc.file_path == "<memory>"
        # Must execute cleanly through transformer and validator without crashing
        transformer = CoordinateTransformer(machine, pen)
        transformed = transformer.transform_document_elements(doc, DocumentTransform())
        assert isinstance(transformed, list)

        tg = ToolpathGenerator(machine, pen)
        moves, stats = tg.generate(doc, DocumentTransform())
        assert isinstance(moves, list)

        gcode = GcodeGenerator(machine, pen).generate(moves, stats)
        assert isinstance(gcode, str)

        rep = SafetyValidator(machine, pen).validate(moves, gcode)
        assert rep is not None


def test_fuzz_non_finite_coordinates(machine, pen):
    """Tests SVG elements containing NaN, Infinity, -Infinity, and extreme scientific notation."""
    parser = SvgParser()
    fuzzed_svgs = [
        # NaN in path coordinates
        "<svg viewBox='0 0 100 100'><path d='M NaN NaN L 20 20 C NaN 10 20 NaN 50 50 Z'/></svg>",
        # Infinity in path coordinates
        "<svg viewBox='0 0 100 100'><path d='M Infinity -Infinity L 10 10'/></svg>",
        # Extreme scientific notations: 1e30, -1e-15, 1e200, -1e200
        "<svg viewBox='0 0 100 100'><path d='M 1e30 1e30 L -1e-15 -1e-15 C 1e200 0 0 1e200 20 20 Z'/></svg>",
        # Primitives with NaN / negative dimensions
        "<svg><rect x='NaN' y='10' width='-50' height='NaN'/><circle cx='Infinity' cy='0' r='-10'/></svg>",
        # Line and polygon with non-finite points
        "<svg><line x1='NaN' y1='0' x2='10' y2='Infinity'/><polygon points='NaN,0 10,Infinity 0,0'/></svg>",
        # Viewbox with NaN and negative bounds
        "<svg viewBox='NaN 0 -100 Infinity'><rect width='20' height='20'/></svg>",
    ]

    for svg_str in fuzzed_svgs:
        doc = parser.parse_string(svg_str)
        assert doc is not None
        tg = ToolpathGenerator(machine, pen)
        moves, stats = tg.generate(doc, DocumentTransform())
        gcode = GcodeGenerator(machine, pen).generate(moves, stats)
        rep = SafetyValidator(machine, pen).validate(moves, gcode)
        assert rep is not None


def test_fuzz_degenerate_beziers():
    """Tests cubic and quadratic Béziers with degenerate control points."""
    cases = [
        # All control points identical (zero length)
        ((10.0, 10.0), (10.0, 10.0), (10.0, 10.0), (10.0, 10.0)),
        # Collinear points
        ((0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)),
        # NaN in control points
        ((float("nan"), 0.0), (0.0, 0.0), (0.0, 0.0), (10.0, 10.0)),
        # Infinity in control points
        ((0.0, 0.0), (float("inf"), 0.0), (0.0, float("-inf")), (10.0, 10.0)),
        # Astronomical values (1e250)
        ((0.0, 0.0), (1e250, 0.0), (0.0, 1e250), (10.0, 10.0)),
    ]

    for p0, p1, p2, p3 in cases:
        pts = flatten_cubic_bezier(p0, p1, p2, p3, tolerance_mm=0.08)
        assert len(pts) >= 1
        for x, y in pts:
            assert math.isfinite(x)
            assert math.isfinite(y)

        # Quadratic delegation
        q_pts = flatten_quadratic_bezier(p0, p1, p3, tolerance_mm=0.08)
        assert len(q_pts) >= 1
        for x, y in q_pts:
            assert math.isfinite(x)
            assert math.isfinite(y)


def test_fuzz_degenerate_arcs():
    """Tests SVG arcs with degenerate radii, non-finite values, and singularities."""
    cases = [
        # Zero radii
        ((0.0, 0.0), 0.0, 0.0, 0.0, False, False, (10.0, 10.0)),
        # Negative radii
        ((0.0, 0.0), -15.0, -25.0, 0.0, False, True, (10.0, 10.0)),
        # End point coincident with start point
        ((10.0, 10.0), 5.0, 5.0, 0.0, False, False, (10.0, 10.0)),
        # NaN in rotation and radii
        ((0.0, 0.0), float("nan"), 10.0, float("nan"), False, False, (10.0, 10.0)),
        # Astronomical radius
        ((0.0, 0.0), 1e200, 1e200, 45.0, True, True, (20.0, 20.0)),
        # Infinity in endpoints
        ((float("inf"), 0.0), 10.0, 10.0, 0.0, False, False, (10.0, float("-inf"))),
    ]

    for p0, rx, ry, rot, large, sweep, p1 in cases:
        pts = flatten_svg_arc(p0, rx, ry, rot, large, sweep, p1, tolerance_mm=0.08)
        assert len(pts) >= 1
        for x, y in pts:
            assert math.isfinite(x)
            assert math.isfinite(y)


def test_fuzz_singular_and_extreme_transforms():
    """Tests affine matrices with zero determinant, singular values, and extreme scales."""
    cases = [
        "matrix(0 0 0 0 0 0)",
        "matrix(0,0,0,0,10,20)",
        "scale(0 0)",
        "scale(0.0000000001)",
        "scale(1e30 1e30)",
        "skewX(90)",   # tan(90 deg) singular
        "skewY(90)",
        "skewX(270)",
        "rotate(NaN)",
        "matrix(nan nan nan nan nan nan)",
        "matrix(inf 0 0 inf 0 0)",
    ]

    poly = [(0.0, 0.0), (10.0, 10.0), (20.0, 0.0)]
    for t_str in cases:
        mat = parse_transform_matrix(t_str)
        assert mat is not None
        assert mat.shape == (3, 3)

        s = matrix_max_scale(mat)
        assert math.isfinite(s)
        assert s > 0.0

        transformed = apply_matrix_to_polyline(poly, mat)
        for x, y in transformed:
            assert math.isfinite(x)
            assert math.isfinite(y)
            assert abs(x) <= 1e7
            assert abs(y) <= 1e7
