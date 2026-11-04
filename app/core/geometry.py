"""Geometric operations: curve flattening, simplification, deduplication, hatching, and contour offsetting."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from shapely.affinity import rotate as shapely_rotate
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.ops import unary_union

from app.core.models import FillSettings


def flatten_cubic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    tolerance_mm: float = 0.08,
) -> list[tuple[float, float]]:
    """Adaptively flattens a cubic Bézier curve into a polyline within `tolerance_mm` using vectorized NumPy evaluation."""
    tol = max(0.002, float(tolerance_mm)) if math.isfinite(tolerance_mm) else 0.08

    # Defensively sanitize input control points against non-finite or astronomical coordinates
    safe_pts = []
    for p in (p0, p1, p2, p3):
        try:
            x, y = float(p[0]), float(p[1])
            if not math.isfinite(x) or abs(x) > 1e12:
                x = 0.0
            if not math.isfinite(y) or abs(y) > 1e12:
                y = 0.0
            safe_pts.append((x, y))
        except (ValueError, TypeError, IndexError):
            safe_pts.append((0.0, 0.0))

    sp0, sp1, sp2, sp3 = safe_pts
    pt0 = np.array(sp0, dtype=np.float64)
    pt1 = np.array(sp1, dtype=np.float64)
    pt2 = np.array(sp2, dtype=np.float64)
    pt3 = np.array(sp3, dtype=np.float64)

    try:
        d1 = float(np.linalg.norm(pt0 - 2.0 * pt1 + pt2))
        d2 = float(np.linalg.norm(pt1 - 2.0 * pt2 + pt3))
        max_d = max(d1, d2)
    except Exception:
        max_d = 0.0

    # If practically straight collinear line segment or degenerate zero-length, return endpoints immediately
    if not math.isfinite(max_d) or max_d < 1e-7:
        return [sp0, sp3]

    # Wang's formula for Bézier subdivision steps within tolerance (protected against float overflow)
    try:
        val = np.sqrt((3.0 * max_d) / (4.0 * tol))
        if not math.isfinite(val) or val > 64:
            steps = 64
        else:
            steps = int(np.ceil(val))
    except (OverflowError, ValueError):
        steps = 64
    steps = max(2, min(steps, 64))

    t = np.linspace(0.0, 1.0, steps + 1, dtype=np.float64)[:, np.newaxis]
    t_inv = 1.0 - t

    # Vectorized cubic Bernstein polynomials: B(t) = (1-t)^3*P0 + 3(1-t)^2*t*P1 + 3(1-t)*t^2*P2 + t^3*P3
    b0 = t_inv ** 3
    b1 = 3.0 * (t_inv ** 2) * t
    b2 = 3.0 * t_inv * (t ** 2)
    b3 = t ** 3

    curve_pts = b0 * pt0 + b1 * pt1 + b2 * pt2 + b3 * pt3
    result: list[tuple[float, float]] = []
    for x, y in curve_pts:
        fx, fy = float(x), float(y)
        if math.isfinite(fx) and math.isfinite(fy):
            result.append((fx, fy))
    return result if result else [sp0, sp3]


def flatten_quadratic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    tolerance_mm: float = 0.08,
) -> list[tuple[float, float]]:
    """Elevates a quadratic Bézier curve to cubic and flattens it."""
    c1 = (p0[0] + (2.0 / 3.0) * (p1[0] - p0[0]), p0[1] + (2.0 / 3.0) * (p1[1] - p0[1]))
    c2 = (p2[0] + (2.0 / 3.0) * (p1[0] - p2[0]), p2[1] + (2.0 / 3.0) * (p1[1] - p2[1]))
    return flatten_cubic_bezier(p0, c1, c2, p2, tolerance_mm=tolerance_mm)


def flatten_svg_arc(
    p0: tuple[float, float],
    rx: float,
    ry: float,
    x_axis_rotation_deg: float,
    large_arc_flag: bool,
    sweep_flag: bool,
    p1: tuple[float, float],
    tolerance_mm: float = 0.08,
) -> list[tuple[float, float]]:
    """Flattens an SVG elliptical arc (W3C SVG 1.1 F.6) into a polyline."""
    # Defensively sanitize endpoints
    try:
        x1 = float(p0[0]) if math.isfinite(p0[0]) and abs(p0[0]) < 1e12 else 0.0
        y1 = float(p0[1]) if math.isfinite(p0[1]) and abs(p0[1]) < 1e12 else 0.0
        x2 = float(p1[0]) if math.isfinite(p1[0]) and abs(p1[0]) < 1e12 else 0.0
        y2 = float(p1[1]) if math.isfinite(p1[1]) and abs(p1[1]) < 1e12 else 0.0
    except (ValueError, TypeError, IndexError):
        return [(0.0, 0.0)]

    p0_safe = (x1, y1)
    p1_safe = (x2, y2)

    dist = math.hypot(x2 - x1, y2 - y1)
    if not math.isfinite(dist) or dist < 1e-9:
        return [p0_safe]

    rx = abs(float(rx)) if math.isfinite(rx) else 0.0
    ry = abs(float(ry)) if math.isfinite(ry) else 0.0
    if rx < 1e-9 or ry < 1e-9 or rx > 1e12 or ry > 1e12:
        return [p0_safe, p1_safe]

    rot_deg = float(x_axis_rotation_deg) if math.isfinite(x_axis_rotation_deg) else 0.0
    phi = math.radians(rot_deg % 360.0)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx2 = (x1 - x2) * 0.5
    dy2 = (y1 - y2) * 0.5
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    # Ensure radii are large enough
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if not math.isfinite(lam):
        return [p0_safe, p1_safe]
    if lam > 1.0:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    rx_sq = rx * rx
    ry_sq = ry * ry
    x1p_sq = x1p * x1p
    y1p_sq = y1p * y1p

    num = max(0.0, rx_sq * ry_sq - rx_sq * y1p_sq - ry_sq * x1p_sq)
    den = rx_sq * y1p_sq + ry_sq * x1p_sq
    factor = math.sqrt(num / den) if den > 1e-12 else 0.0
    if large_arc_flag == sweep_flag:
        factor = -factor

    cxp = factor * (rx * y1p / ry)
    cyp = factor * (-ry * x1p / rx)

    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) * 0.5
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) * 0.5

    def vec_angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        mag = math.hypot(ux, uy) * math.hypot(vx, vy)
        if mag < 1e-12 or not math.isfinite(mag):
            return 0.0
        cos_val = max(-1.0, min(1.0, dot / mag))
        ang = math.acos(cos_val)
        if ux * vy - uy * vx < 0:
            ang = -ang
        return ang

    v1x = (x1p - cxp) / rx
    v1y = (y1p - cyp) / ry
    v2x = (-x1p - cxp) / rx
    v2y = (-y1p - cyp) / ry

    theta1 = vec_angle(1.0, 0.0, v1x, v1y)
    dtheta = vec_angle(v1x, v1y, v2x, v2y)

    if not sweep_flag and dtheta > 0:
        dtheta -= 2.0 * math.pi
    elif sweep_flag and dtheta < 0:
        dtheta += 2.0 * math.pi

    max_r = max(rx, ry)
    tol = max(0.005, float(tolerance_mm)) if math.isfinite(tolerance_mm) else 0.08
    if max_r > tol and math.isfinite(max_r):
        ratio = max(0.0, min(1.0, 1.0 - tol / max_r))
        step_angle = 2.0 * math.acos(ratio)
        step_angle = max(0.02, min(step_angle, math.pi / 8.0))
    else:
        step_angle = math.pi / 8.0

    try:
        val = abs(dtheta) / step_angle
        if not math.isfinite(val) or val > 128:
            steps = 128
        else:
            steps = max(4, int(math.ceil(val)))
    except (OverflowError, ValueError):
        steps = 128

    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = theta1 + dtheta * (i / steps)
        ct = math.cos(t)
        st = math.sin(t)
        px = cos_phi * rx * ct - sin_phi * ry * st + cx
        py = sin_phi * rx * ct + cos_phi * ry * st + cy
        if math.isfinite(px) and math.isfinite(py):
            pts.append((px, py))

    if not pts:
        return [p0_safe, p1_safe]
    pts[0] = p0_safe
    pts[-1] = p1_safe
    return pts


def deduplicate_points(
    polyline: Sequence[tuple[float, float]],
    min_dist_mm: float = 0.005,
) -> list[tuple[float, float]]:
    """Removes consecutive duplicate or near-duplicate points and sanitizes non-finite coordinates within `min_dist_mm`."""
    if not polyline:
        return []
    # Strip any NaN or Inf coordinates defensively
    sanitized: list[tuple[float, float]] = []
    for pt in polyline:
        try:
            x, y = float(pt[0]), float(pt[1])
            if math.isfinite(x) and math.isfinite(y):
                sanitized.append((x, y))
        except (ValueError, TypeError, IndexError):
            continue
    if not sanitized:
        return []

    result: list[tuple[float, float]] = [sanitized[0]]
    min_d = max(1e-6, float(min_dist_mm))
    for pt in sanitized[1:]:
        prev = result[-1]
        if math.hypot(pt[0] - prev[0], pt[1] - prev[1]) >= min_d:
            result.append(pt)
    # If original had >=2 points and collapsed to 1, preserve endpoint if distinct
    if len(result) == 1 and len(sanitized) >= 2:
        if math.hypot(sanitized[-1][0] - result[0][0], sanitized[-1][1] - result[0][1]) > 1e-7:
            result.append(sanitized[-1])
    return result


def simplify_polyline(
    polyline: Sequence[tuple[float, float]],
    tolerance_mm: float = 0.02,
) -> list[tuple[float, float]]:
    """Simplifies a polyline while preserving geometric shape and closed-loop topology."""
    cleaned = deduplicate_points(polyline)
    if len(cleaned) < 3 or tolerance_mm <= 1e-6:
        return cleaned

    is_closed = math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) < 1e-4
    # Avoid over-simplifying circles/curves with many short segments unless tolerance is safely small
    line = LineString(cleaned)
    simplified = line.simplify(float(tolerance_mm), preserve_topology=True)
    coords = [(float(x), float(y)) for x, y in simplified.coords]
    if is_closed and len(coords) >= 3 and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords if len(coords) >= 2 else cleaned


def _polylines_to_shapely_polygons(
    polylines: list[list[tuple[float, float]]],
    is_closed_hint: bool = False,
) -> list[Polygon]:
    """Converts closed polylines (including compound paths with holes) into valid Shapely Polygons."""
    rings: list[Polygon] = []
    for poly in polylines:
        if len(poly) < 3:
            continue
        dist = math.hypot(poly[0][0] - poly[-1][0], poly[0][1] - poly[-1][1])
        if not is_closed_hint and dist > 1.5:
            continue
        pts = list(poly)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        if len(pts) < 4:
            continue
        try:
            p = Polygon(pts)
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty:
                if isinstance(p, Polygon):
                    rings.append(p)
                elif isinstance(p, MultiPolygon):
                    rings.extend(list(p.geoms))
        except Exception:
            continue

    if not rings:
        return []

    # Sort by area descending to handle even-odd / interior hole nesting
    rings.sort(key=lambda g: g.area, reverse=True)
    result: list[Polygon] = []
    for ring in rings:
        placed_as_hole = False
        for idx, outer in enumerate(result):
            if outer.contains(ring):
                diff = outer.difference(ring)
                if isinstance(diff, Polygon):
                    result[idx] = diff
                elif isinstance(diff, MultiPolygon) and len(diff.geoms) > 0:
                    result[idx] = diff.geoms[0]
                    result.extend(diff.geoms[1:])
                placed_as_hole = True
                break
        if not placed_as_hole:
            result.append(ring)

    return [p for p in result if not p.is_empty and p.area > 1e-4]


def generate_hatch_lines(
    polygons: list[Polygon],
    spacing_mm: float = 1.0,
    angle_deg: float = 45.0,
) -> list[list[tuple[float, float]]]:
    """Generates clipped linear hatch paths across a list of Shapely Polygons with vectorized rotation."""
    step = max(0.15, float(spacing_mm))
    merged = unary_union(polygons)
    if merged.is_empty:
        return []

    centroid = merged.centroid
    cx, cy = centroid.x, centroid.y

    # Rotate geometry by -angle_deg so hatch lines are horizontal
    rotated = shapely_rotate(merged, -angle_deg, origin=(cx, cy), use_radians=False)
    min_x, min_y, max_x, max_y = rotated.bounds
    pad = step * 2.0

    y_values = np.arange(min_y + step * 0.5, max_y, step)
    if len(y_values) == 0:
        return []

    # Fast trigonometry for inverse rotation (pure arithmetic, avoids heavy GEOS object allocations)
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    # Batch create scan lines and intersect via Shapely
    lines = [LineString([(min_x - pad, float(y_val)), (max_x + pad, float(y_val))]) for y_val in y_values]
    import shapely
    clipped_lines = shapely.intersection(lines, rotated)

    hatch_polylines: list[list[tuple[float, float]]] = []

    for row_idx, clipped in enumerate(clipped_lines):
        if clipped.is_empty:
            continue

        segments: list[LineString] = []
        if isinstance(clipped, LineString):
            segments.append(clipped)
        elif isinstance(clipped, MultiLineString):
            segments.extend(list(clipped.geoms))
        else:
            for g in getattr(clipped, "geoms", []):
                if isinstance(g, LineString):
                    segments.append(g)

        # Alternate scan direction on odd rows to reduce pen travel
        reverse_row = (row_idx % 2 == 1)
        if reverse_row:
            segments.reverse()

        for seg in segments:
            if seg.length < 0.05:
                continue
            coords = list(seg.coords)
            if reverse_row:
                coords.reverse()

            # Vectorized unrotation of points around centroid (cx, cy)
            unrotated = [
                (cx + (x - cx) * cos_a - (y - cy) * sin_a, cy + (x - cx) * sin_a + (y - cy) * cos_a)
                for x, y in coords
            ]
            hatch_polylines.append(unrotated)

    return hatch_polylines


def generate_contour_fill_paths(
    polygons: list[Polygon],
    spacing_mm: float = 0.8,
    max_rings: int = 25,
) -> list[list[tuple[float, float]]]:
    """Generates concentric inward-offset contour paths for filled polygons."""
    step = max(0.15, float(spacing_mm))
    merged = unary_union(polygons)
    if merged.is_empty:
        return []

    contours: list[list[tuple[float, float]]] = []
    for ring_idx in range(1, max_rings + 1):
        inset = merged.buffer(-ring_idx * step)
        if inset.is_empty:
            break

        poly_list: list[Polygon] = []
        if isinstance(inset, Polygon):
            poly_list.append(inset)
        elif isinstance(inset, MultiPolygon):
            poly_list.extend(list(inset.geoms))

        for p in poly_list:
            if p.exterior and len(p.exterior.coords) >= 3:
                contours.append([(float(x), float(y)) for x, y in p.exterior.coords])
            for interior in p.interiors:
                if len(interior.coords) >= 3:
                    contours.append([(float(x), float(y)) for x, y in interior.coords])

    return contours


def process_element_fill_and_stroke(
    polylines: list[list[tuple[float, float]]],
    has_fill: bool,
    fill_settings: FillSettings,
    mode_override: str | None = None,
    is_closed: bool = False,
) -> list[list[tuple[float, float]]]:
    """Applies configured fill mode (ignore, outline, hatch, contour) to element polylines."""
    mode = (mode_override or fill_settings.mode).lower()

    if mode == "outline" or mode == "ignore":
        return polylines

    polygons = _polylines_to_shapely_polygons(polylines, is_closed_hint=(is_closed or has_fill))
    if not polygons:
        return polylines

    result: list[list[tuple[float, float]]] = []
    if fill_settings.include_outline:
        result.extend(polylines)

    if mode == "hatch":
        result.extend(
            generate_hatch_lines(
                polygons,
                spacing_mm=fill_settings.hatch_spacing_mm,
                angle_deg=fill_settings.hatch_angle_deg,
            )
        )
        if fill_settings.cross_hatch:
            result.extend(
                generate_hatch_lines(
                    polygons,
                    spacing_mm=fill_settings.hatch_spacing_mm,
                    angle_deg=fill_settings.hatch_angle_deg + 90.0,
                )
            )
    elif mode == "contour":
        result.extend(
            generate_contour_fill_paths(
                polygons,
                spacing_mm=fill_settings.contour_spacing_mm,
                max_rings=fill_settings.contour_max_rings,
            )
        )

    return result if result else polylines
