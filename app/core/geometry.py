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
    """Adaptively flattens a cubic Bézier curve into a polyline within `tolerance_mm`."""
    tol = max(0.002, float(tolerance_mm))
    pts: list[tuple[float, float]] = [p0]

    def subdivide(
        a0: tuple[float, float],
        a1: tuple[float, float],
        a2: tuple[float, float],
        a3: tuple[float, float],
        depth: int,
    ) -> None:
        if depth > 12:
            pts.append(a3)
            return

        # Estimate flatness using control point distance from baseline a0->a3
        dx = a3[0] - a0[0]
        dy = a3[1] - a0[1]
        d2 = abs((a1[0] - a3[0]) * dy - (a1[1] - a3[1]) * dx)
        d3 = abs((a2[0] - a3[0]) * dy - (a2[1] - a3[1]) * dx)
        chord_len_sq = dx * dx + dy * dy

        if (d2 + d3) ** 2 <= tol * tol * chord_len_sq or (chord_len_sq < tol * tol and d2 + d3 < tol):
            pts.append(a3)
            return

        # De Casteljau midpoint split
        m01 = ((a0[0] + a1[0]) * 0.5, (a0[1] + a1[1]) * 0.5)
        m12 = ((a1[0] + a2[0]) * 0.5, (a1[1] + a2[1]) * 0.5)
        m23 = ((a2[0] + a3[0]) * 0.5, (a2[1] + a3[1]) * 0.5)
        m012 = ((m01[0] + m12[0]) * 0.5, (m01[1] + m12[1]) * 0.5)
        m123 = ((m12[0] + m23[0]) * 0.5, (m12[1] + m23[1]) * 0.5)
        mid = ((m012[0] + m123[0]) * 0.5, (m012[1] + m123[1]) * 0.5)

        subdivide(a0, m01, m012, mid, depth + 1)
        subdivide(mid, m123, m23, a3, depth + 1)

    subdivide(p0, p1, p2, p3, 0)
    return pts


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
    x1, y1 = p0
    x2, y2 = p1
    if math.hypot(x2 - x1, y2 - y1) < 1e-9:
        return [p0]

    rx = abs(rx)
    ry = abs(ry)
    if rx < 1e-9 or ry < 1e-9:
        return [p0, p1]

    phi = math.radians(x_axis_rotation_deg % 360.0)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx2 = (x1 - x2) * 0.5
    dy2 = (y1 - y2) * 0.5
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    # Ensure radii are large enough
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
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
        if mag < 1e-12:
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
    tol = max(0.005, float(tolerance_mm))
    if max_r > tol:
        step_angle = 2.0 * math.acos(max(0.0, 1.0 - tol / max_r))
        step_angle = max(0.02, min(step_angle, math.pi / 8.0))
    else:
        step_angle = math.pi / 8.0

    steps = max(4, int(math.ceil(abs(dtheta) / step_angle)))
    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = theta1 + dtheta * (i / steps)
        ct = math.cos(t)
        st = math.sin(t)
        px = cos_phi * rx * ct - sin_phi * ry * st + cx
        py = sin_phi * rx * ct + cos_phi * ry * st + cy
        pts.append((px, py))

    pts[0] = p0
    pts[-1] = p1
    return pts


def deduplicate_points(
    polyline: Sequence[tuple[float, float]],
    min_dist_mm: float = 0.005,
) -> list[tuple[float, float]]:
    """Removes consecutive duplicate or near-duplicate points within `min_dist_mm`."""
    if not polyline:
        return []
    result: list[tuple[float, float]] = [polyline[0]]
    min_d = max(1e-6, float(min_dist_mm))
    for pt in polyline[1:]:
        prev = result[-1]
        if math.hypot(pt[0] - prev[0], pt[1] - prev[1]) >= min_d:
            result.append(pt)
    # If original had >=2 points and collapsed to 1, preserve endpoint if distinct
    if len(result) == 1 and len(polyline) >= 2:
        if math.hypot(polyline[-1][0] - result[0][0], polyline[-1][1] - result[0][1]) > 1e-7:
            result.append(polyline[-1])
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
) -> list[Polygon]:
    """Converts closed polylines (including compound paths with holes) into valid Shapely Polygons."""
    rings: list[Polygon] = []
    for poly in polylines:
        if len(poly) < 3:
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
    """Generates clipped linear hatch paths across a list of Shapely Polygons."""
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
    hatch_polylines: list[list[tuple[float, float]]] = []

    for row_idx, y_val in enumerate(y_values):
        scan_line = LineString([(min_x - pad, float(y_val)), (max_x + pad, float(y_val))])
        clipped = rotated.intersection(scan_line)
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
        if row_idx % 2 == 1:
            segments.reverse()

        for seg in segments:
            if seg.length < 0.05:
                continue
            unrotated = shapely_rotate(seg, angle_deg, origin=(cx, cy), use_radians=False)
            coords = [(float(x), float(y)) for x, y in unrotated.coords]
            if row_idx % 2 == 1:
                coords.reverse()
            hatch_polylines.append(coords)

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
) -> list[list[tuple[float, float]]]:
    """Applies configured fill mode (ignore, outline, hatch, contour) to element polylines."""
    mode = (mode_override or fill_settings.mode).lower()

    if not has_fill or mode == "outline":
        return polylines

    if mode == "ignore":
        # Still keep outlines if include_outline is True, otherwise return outlines as standard stroke
        return polylines

    polygons = _polylines_to_shapely_polygons(polylines)
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
