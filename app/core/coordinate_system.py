"""Coordinate system transformations between SVG space (Y-down), Build Plate space (Y-up), and Machine G-code space."""

from __future__ import annotations

import math
from typing import Iterable

from app.core.models import (
    BoundingBox,
    DocumentTransform,
    ParsedSvgDocument,
    SvgElement,
)
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile


UNIT_TO_MM: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
    "pt": 25.4 / 72.0,
    "pc": 25.4 / 6.0,
    "px": 25.4 / 96.0,  # CSS/SVG2 standard 96 DPI (1px = 0.2645833333mm)
    "": 1.0,            # User units default to 1:1 mm when no unit suffix is specified
}


def convert_length_to_mm(value: float, unit: str = "mm", dpi: float = 96.0) -> float:
    """Converts a numeric length in the given SVG/CSS unit into physical millimeters."""
    u = unit.strip().lower()
    if u == "px" and abs(dpi - 96.0) > 1e-6:
        return float(value) * (25.4 / dpi)
    factor = UNIT_TO_MM.get(u, 1.0)
    return float(value) * factor


def invert_y_polyline(
    polyline: Iterable[tuple[float, float]],
    reference_height_mm: float,
) -> list[tuple[float, float]]:
    """Inverts the Y-axis from SVG coordinates (Y-down) to printer coordinates (Y-up)."""
    return [(float(x), float(reference_height_mm - y)) for x, y in polyline]


def transform_point_2d(
    x: float,
    y: float,
    center_x: float,
    center_y: float,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    rotation_deg: float = 0.0,
    mirror_x: bool = False,
    mirror_y: bool = False,
    translate_x: float = 0.0,
    translate_y: float = 0.0,
) -> tuple[float, float]:
    """Applies scale, mirror, rotation around (center_x, center_y), and translation to a 2D point."""
    dx = x - center_x
    dy = y - center_y

    if mirror_x:
        dx = -dx
    if mirror_y:
        dy = -dy

    dx *= scale_x
    dy *= scale_y

    if abs(rotation_deg) > 1e-9:
        rad = math.radians(rotation_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        rx = dx * cos_a - dy * sin_a
        ry = dx * sin_a + dy * cos_a
        dx, dy = rx, ry

    return (center_x + dx + translate_x, center_y + dy + translate_y)


class CoordinateTransformer:
    """Transforms parsed SVG elements into physical build-plate and machine G-code coordinates."""

    def __init__(
        self,
        machine: MachineProfile,
        pen: PenProfile,
        invert_y: bool = True,
        normalize_origin: bool = True,
    ) -> None:
        self.machine = machine
        self.pen = pen
        self.invert_y = invert_y
        self.normalize_origin = normalize_origin

    def transform_document_elements(
        self,
        doc: ParsedSvgDocument,
        doc_transform: DocumentTransform,
    ) -> list[ tuple[SvgElement, list[list[tuple[float, float]]]] ]:
        """Transforms all visible elements in `doc` to build-plate millimeter coordinates (Y-up).

        Returns a list of (SvgElement, transformed_polylines_mm) pairs.
        """
        visible_elements = [el for el in doc.elements if el.visible and el.polylines_mm]
        if not visible_elements:
            return []

        # Reference height for Y-axis inversion:
        # Use SVG canvas height if positive, otherwise native bounding box max_y.
        native_bounds = doc.compute_native_bounds()
        ref_height = doc.height_mm if doc.height_mm > 0 else native_bounds.max_y

        # Step 1: Apply Y-inversion and per-element local transforms
        intermediate: list[tuple[SvgElement, list[list[tuple[float, float]]]]] = []
        all_pts_x: list[float] = []
        all_pts_y: list[float] = []

        for el in visible_elements:
            el_polys: list[list[tuple[float, float]]] = []
            # Compute element local center after Y-inversion
            inverted_polys: list[list[tuple[float, float]]] = []
            el_xs: list[float] = []
            el_ys: list[float] = []
            for poly in el.polylines_mm:
                if not poly:
                    continue
                inv = invert_y_polyline(poly, ref_height) if self.invert_y else [(float(px), float(py)) for px, py in poly]
                inverted_polys.append(inv)
                for px, py in inv:
                    el_xs.append(px)
                    el_ys.append(py)

            if not inverted_polys:
                continue

            el_cx = (min(el_xs) + max(el_xs)) * 0.5
            el_cy = (min(el_ys) + max(el_ys)) * 0.5

            has_el_transform = (
                abs(el.scale_x - 1.0) > 1e-7
                or abs(el.scale_y - 1.0) > 1e-7
                or abs(el.rotation_deg) > 1e-7
                or abs(el.offset_x) > 1e-7
                or abs(el.offset_y) > 1e-7
            )

            for inv in inverted_polys:
                if has_el_transform:
                    t_poly = [
                        transform_point_2d(
                            px,
                            py,
                            el_cx,
                            el_cy,
                            scale_x=el.scale_x,
                            scale_y=el.scale_y,
                            rotation_deg=el.rotation_deg,
                            translate_x=el.offset_x,
                            translate_y=el.offset_y,
                        )
                        for px, py in inv
                    ]
                else:
                    t_poly = inv
                el_polys.append(t_poly)
                for px, py in t_poly:
                    all_pts_x.append(px)
                    all_pts_y.append(py)

            intermediate.append((el, el_polys))

        if not all_pts_x:
            return []

        min_x = min(all_pts_x)
        max_x = max(all_pts_x)
        min_y = min(all_pts_y)
        max_y = max(all_pts_y)
        doc_cx = (min_x + max_x) * 0.5
        doc_cy = (min_y + max_y) * 0.5

        # Step 2: Apply Document-level scale, mirror, and rotation around document center
        scaled_rotated: list[tuple[SvgElement, list[list[tuple[float, float]]]]] = []
        sr_xs: list[float] = []
        sr_ys: list[float] = []

        for el, polys in intermediate:
            new_polys: list[list[tuple[float, float]]] = []
            for poly in polys:
                t_poly = [
                    transform_point_2d(
                        px,
                        py,
                        doc_cx,
                        doc_cy,
                        scale_x=doc_transform.scale_x,
                        scale_y=doc_transform.scale_y,
                        rotation_deg=doc_transform.rotation_deg,
                        mirror_x=doc_transform.mirror_x,
                        mirror_y=doc_transform.mirror_y,
                    )
                    for px, py in poly
                ]
                new_polys.append(t_poly)
                for px, py in t_poly:
                    sr_xs.append(px)
                    sr_ys.append(py)
            scaled_rotated.append((el, new_polys))

        sr_min_x = min(sr_xs) if sr_xs else 0.0
        sr_min_y = min(sr_ys) if sr_ys else 0.0

        # Step 3: Position on build plate
        # If normalize_origin is True, (pos_x_mm, pos_y_mm) specifies the bottom-left corner of the bounding box.
        # If normalize_origin is False, (pos_x_mm, pos_y_mm) is added directly to the SVG origin coordinates.
        if self.normalize_origin:
            shift_x = doc_transform.pos_x_mm - sr_min_x
            shift_y = doc_transform.pos_y_mm - sr_min_y
        else:
            shift_x = doc_transform.pos_x_mm
            shift_y = doc_transform.pos_y_mm

        final_result: list[tuple[SvgElement, list[list[tuple[float, float]]]]] = []
        for el, polys in scaled_rotated:
            placed_polys = [
                [(px + shift_x, py + shift_y) for px, py in poly]
                for poly in polys
            ]
            final_result.append((el, placed_polys))

        return final_result

    def plate_to_machine_xy(self, plate_x: float, plate_y: float) -> tuple[float, float]:
        """Applies machine origin, coordinate offsets, and pen/holder offsets to a build-plate coordinate."""
        total_off_x = self.machine.pen_holder_offset_x_mm + self.pen.x_offset_mm
        total_off_y = self.machine.pen_holder_offset_y_mm + self.pen.y_offset_mm

        mx = plate_x + self.machine.coord_offset_x_mm - total_off_x
        my = plate_y + self.machine.coord_offset_y_mm - total_off_y

        if self.machine.origin_position == "center":
            mx += self.machine.nominal_x_mm * 0.5
            my += self.machine.nominal_y_mm * 0.5
        elif self.machine.origin_position == "back_left":
            my = self.machine.nominal_y_mm - my

        return (mx, my)

    def machine_to_plate_xy(self, mx: float, my: float) -> tuple[float, float]:
        """Converts machine G-code coordinates back to physical build-plate coordinates (where pen tip touches)."""
        if self.machine.origin_position == "center":
            mx -= self.machine.nominal_x_mm * 0.5
            my -= self.machine.nominal_y_mm * 0.5
        elif self.machine.origin_position == "back_left":
            my = self.machine.nominal_y_mm - my

        total_off_x = self.machine.pen_holder_offset_x_mm + self.pen.x_offset_mm
        total_off_y = self.machine.pen_holder_offset_y_mm + self.pen.y_offset_mm

        plate_x = mx - self.machine.coord_offset_x_mm + total_off_x
        plate_y = my - self.machine.coord_offset_y_mm + total_off_y

        return (plate_x, plate_y)

    @staticmethod
    def compute_bounds(
        transformed_elements: list[tuple[SvgElement, list[list[tuple[float, float]]]]]
    ) -> BoundingBox:
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")
        for _, polys in transformed_elements:
            for poly in polys:
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
