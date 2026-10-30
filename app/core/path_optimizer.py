"""Toolpath generation and trajectory ordering optimization engine."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from app.core.coordinate_system import CoordinateTransformer
from app.core.geometry import (
    deduplicate_points,
    process_element_fill_and_stroke,
    simplify_polyline,
)
from app.core.models import (
    DocumentTransform,
    FillSettings,
    MovementType,
    OptimizationSettings,
    ParsedSvgDocument,
    ToolpathMove,
    ToolpathStats,
)
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile


@dataclass
class DrawablePath:
    """A continuous 2D polyline in machine millimeter coordinates ready for ordering."""
    points: list[tuple[float, float]]
    layer: str
    element_id: str
    is_closed: bool = False

    @property
    def start(self) -> tuple[float, float]:
        return self.points[0]

    @property
    def end(self) -> tuple[float, float]:
        return self.points[-1]

    @property
    def length(self) -> float:
        total = 0.0
        for i in range(len(self.points) - 1):
            total += math.hypot(
                self.points[i + 1][0] - self.points[i][0],
                self.points[i + 1][1] - self.points[i][1],
            )
        return total

    def reversed(self) -> DrawablePath:
        return DrawablePath(
            points=list(reversed(self.points)),
            layer=self.layer,
            element_id=self.element_id,
            is_closed=self.is_closed,
        )


def compute_sequence_travel_distance(
    paths: Sequence[DrawablePath],
    origin: tuple[float, float] = (0.0, 0.0),
    merge_threshold_mm: float = 0.08,
) -> float:
    """Computes total XY travel distance for a sequence of DrawablePaths starting from `origin`."""
    if not paths:
        return 0.0
    total = 0.0
    cur = origin
    for p in paths:
        d = math.hypot(p.start[0] - cur[0], p.start[1] - cur[1])
        if d > merge_threshold_mm:
            total += d
        cur = p.end
    return total


def optimize_direction_only(
    paths: list[DrawablePath],
    origin: tuple[float, float] = (0.0, 0.0),
) -> list[DrawablePath]:
    """Preserves original path index order, flipping individual path directions when it shortens travel."""
    result: list[DrawablePath] = []
    cur = origin
    for p in paths:
        if p.is_closed:
            result.append(p)
            cur = p.end
            continue
        d_fwd = math.hypot(p.start[0] - cur[0], p.start[1] - cur[1])
        d_rev = math.hypot(p.end[0] - cur[0], p.end[1] - cur[1])
        if d_rev + 1e-6 < d_fwd:
            rp = p.reversed()
            result.append(rp)
            cur = rp.end
        else:
            result.append(p)
            cur = p.end
    return result


def optimize_nearest_neighbor(
    paths: list[DrawablePath],
    origin: tuple[float, float] = (0.0, 0.0),
    allow_reversal: bool = True,
) -> list[DrawablePath]:
    """Greedy nearest-neighbor path ordering with optional start/end direction reversal."""
    if len(paths) <= 1:
        return list(paths)

    remaining = list(paths)
    ordered: list[DrawablePath] = []
    cur_x, cur_y = origin

    while remaining:
        best_idx = 0
        best_dist = float("inf")
        best_reverse = False

        for i, p in enumerate(remaining):
            sx, sy = p.start
            d_start = (sx - cur_x) ** 2 + (sy - cur_y) ** 2
            if d_start < best_dist:
                best_dist = d_start
                best_idx = i
                best_reverse = False

            if allow_reversal and not p.is_closed:
                ex, ey = p.end
                d_end = (ex - cur_x) ** 2 + (ey - cur_y) ** 2
                if d_end < best_dist:
                    best_dist = d_end
                    best_idx = i
                    best_reverse = True

        chosen = remaining.pop(best_idx)
        if best_reverse:
            chosen = chosen.reversed()
        ordered.append(chosen)
        cur_x, cur_y = chosen.end

    return ordered


def optimize_min_travel_2opt(
    paths: list[DrawablePath],
    origin: tuple[float, float] = (0.0, 0.0),
    allow_reversal: bool = True,
    max_iterations: int = 40,
) -> list[DrawablePath]:
    """Nearest-neighbor initialization followed by 2-Opt local search to minimize total travel distance."""
    ordered = optimize_nearest_neighbor(paths, origin=origin, allow_reversal=allow_reversal)
    n = len(ordered)
    if n < 3 or n > 600:
        return ordered

    def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    for _ in range(max_iterations):
        improved = False
        for i in range(n - 1):
            prev_pt = origin if i == 0 else ordered[i - 1].end
            for j in range(i + 1, n):
                next_pt = ordered[j + 1].start if j + 1 < n else None

                # Current cost of edges entering i and leaving j
                old_cost = dist(prev_pt, ordered[i].start)
                for k in range(i, j):
                    old_cost += dist(ordered[k].end, ordered[k + 1].start)
                if next_pt is not None:
                    old_cost += dist(ordered[j].end, next_pt)

                # Candidate: reverse subsequence i..j (and reverse each path inside if allow_reversal)
                if allow_reversal:
                    cand_sub = [p.reversed() if not p.is_closed else p for p in reversed(ordered[i : j + 1])]
                else:
                    cand_sub = list(reversed(ordered[i : j + 1]))

                new_cost = dist(prev_pt, cand_sub[0].start)
                for k in range(len(cand_sub) - 1):
                    new_cost += dist(cand_sub[k].end, cand_sub[k + 1].start)
                if next_pt is not None:
                    new_cost += dist(cand_sub[-1].end, next_pt)

                if new_cost + 1e-4 < old_cost:
                    ordered[i : j + 1] = cand_sub
                    improved = True
        if not improved:
            break

    return ordered


def merge_contiguous_paths(
    paths: list[DrawablePath],
    merge_threshold_mm: float = 0.08,
) -> list[DrawablePath]:
    """Joins consecutive paths whose end and start points lie within `merge_threshold_mm` to eliminate unnecessary pen lifts."""
    if not paths or merge_threshold_mm <= 0.0:
        return list(paths)

    merged: list[DrawablePath] = [
        DrawablePath(
            points=list(paths[0].points),
            layer=paths[0].layer,
            element_id=paths[0].element_id,
            is_closed=paths[0].is_closed,
        )
    ]

    for nxt in paths[1:]:
        cur = merged[-1]
        gap = math.hypot(nxt.start[0] - cur.end[0], nxt.start[1] - cur.end[1])
        if gap <= merge_threshold_mm and cur.layer == nxt.layer:
            if gap < 1e-6:
                cur.points.extend(nxt.points[1:])
            else:
                cur.points.extend(nxt.points)
            cur.is_closed = math.hypot(
                cur.points[0][0] - cur.points[-1][0],
                cur.points[0][1] - cur.points[-1][1],
            ) < 1e-4
        else:
            merged.append(
                DrawablePath(
                    points=list(nxt.points),
                    layer=nxt.layer,
                    element_id=nxt.element_id,
                    is_closed=nxt.is_closed,
                )
            )

    return merged


class ToolpathGenerator:
    """Generates complete 3D movement trajectories and statistics from a `ParsedSvgDocument`."""

    def __init__(
        self,
        machine: MachineProfile,
        pen: PenProfile,
        opt_settings: OptimizationSettings | None = None,
        fill_settings: FillSettings | None = None,
        invert_y: bool = True,
        normalize_origin: bool = True,
    ) -> None:
        self.machine = machine
        self.pen = pen
        self.opt_settings = opt_settings or OptimizationSettings()
        self.fill_settings = fill_settings or FillSettings()
        self.invert_y = invert_y
        self.normalize_origin = normalize_origin

    def generate(
        self,
        doc: ParsedSvgDocument,
        doc_transform: DocumentTransform | None = None,
    ) -> tuple[list[ToolpathMove], ToolpathStats]:
        if doc_transform is None:
            doc_transform = DocumentTransform()

        transformer = CoordinateTransformer(
            machine=self.machine,
            pen=self.pen,
            invert_y=self.invert_y,
            normalize_origin=self.normalize_origin,
        )

        transformed_elements = transformer.transform_document_elements(doc, doc_transform)
        raw_paths: list[DrawablePath] = []

        for el, plate_polylines in transformed_elements:
            processed_polys = process_element_fill_and_stroke(
                polylines=plate_polylines,
                has_fill=el.has_fill,
                fill_settings=self.fill_settings,
                mode_override=el.fill_mode_override,
            )

            for poly in processed_polys:
                cleaned = deduplicate_points(poly, min_dist_mm=self.opt_settings.min_segment_length_mm)
                if self.opt_settings.simplify_tolerance_mm > 0:
                    cleaned = simplify_polyline(cleaned, tolerance_mm=self.opt_settings.simplify_tolerance_mm)
                if len(cleaned) < 2:
                    continue

                machine_pts = [transformer.plate_to_machine_xy(px, py) for px, py in cleaned]
                is_closed = (
                    math.hypot(
                        machine_pts[0][0] - machine_pts[-1][0],
                        machine_pts[0][1] - machine_pts[-1][1],
                    )
                    < 1e-3
                )
                raw_paths.append(
                    DrawablePath(
                        points=machine_pts,
                        layer=el.layer,
                        element_id=el.id,
                        is_closed=is_closed,
                    )
                )

        if not raw_paths:
            return ([], ToolpathStats())

        # Compute unoptimized travel distance for comparison
        unoptimized_travel = compute_sequence_travel_distance(
            raw_paths,
            origin=(0.0, 0.0),
            merge_threshold_mm=self.opt_settings.merge_threshold_mm,
        )

        strategy = self.opt_settings.strategy.lower()
        if strategy == "original":
            ordered_paths = list(raw_paths)
        elif strategy == "direction_only":
            ordered_paths = optimize_direction_only(raw_paths, origin=(0.0, 0.0))
        elif strategy == "min_travel_2opt":
            ordered_paths = optimize_min_travel_2opt(
                raw_paths,
                origin=(0.0, 0.0),
                allow_reversal=self.opt_settings.allow_direction_reversal,
            )
        else:  # "nearest_neighbor"
            ordered_paths = optimize_nearest_neighbor(
                raw_paths,
                origin=(0.0, 0.0),
                allow_reversal=self.opt_settings.allow_direction_reversal,
            )

        # Merge contiguous paths within threshold to avoid unnecessary pen lifts
        final_paths = merge_contiguous_paths(
            ordered_paths,
            merge_threshold_mm=self.opt_settings.merge_threshold_mm,
        )

        # Build atomic 3D movements (TRAVEL, PEN_DOWN, DRAW, PEN_UP)
        moves: list[ToolpathMove] = []
        pen_up_z = float(self.pen.pen_up_z_mm)
        draw_z = float(self.pen.drawing_z_mm)
        travel_feed = float(self.pen.travel_speed_mm_s) * 60.0
        draw_feed = float(self.pen.draw_speed_mm_s) * 60.0
        z_feed = float(self.pen.z_speed_mm_s) * 60.0
        dwell_ms = int(self.pen.stabilization_delay_ms)

        cur_x, cur_y, cur_z = 0.0, 0.0, pen_up_z
        move_idx = 0
        pen_lifts = 0
        draw_dist = 0.0
        travel_dist = 0.0
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        for path_idx, dpath in enumerate(final_paths):
            sx, sy = dpath.start
            # 1. Travel move to path start (with pen lifted)
            dist_to_start = math.hypot(sx - cur_x, sy - cur_y)
            if dist_to_start > 1e-5 or move_idx == 0:
                mv_travel = ToolpathMove(
                    index=move_idx,
                    move_type=MovementType.TRAVEL,
                    start_x=cur_x,
                    start_y=cur_y,
                    start_z=pen_up_z,
                    end_x=sx,
                    end_y=sy,
                    end_z=pen_up_z,
                    feed_rate_mm_min=travel_feed,
                    layer=dpath.layer,
                    element_id=dpath.element_id,
                    path_index=path_idx,
                )
                moves.append(mv_travel)
                travel_dist += mv_travel.distance_xy
                move_idx += 1
                cur_x, cur_y, cur_z = sx, sy, pen_up_z

            # 2. Controlled Pen-Down transition
            mv_down = ToolpathMove(
                index=move_idx,
                move_type=MovementType.PEN_DOWN,
                start_x=cur_x,
                start_y=cur_y,
                start_z=cur_z,
                end_x=cur_x,
                end_y=cur_y,
                end_z=draw_z,
                feed_rate_mm_min=z_feed,
                dwell_ms=dwell_ms,
                layer=dpath.layer,
                element_id=dpath.element_id,
                path_index=path_idx,
            )
            moves.append(mv_down)
            move_idx += 1
            cur_z = draw_z

            # 3. Drawing segments
            for pt in dpath.points[1:]:
                nx, ny = pt
                min_x = min(min_x, cur_x, nx)
                max_x = max(max_x, cur_x, nx)
                min_y = min(min_y, cur_y, ny)
                max_y = max(max_y, cur_y, ny)

                mv_draw = ToolpathMove(
                    index=move_idx,
                    move_type=MovementType.DRAW,
                    start_x=cur_x,
                    start_y=cur_y,
                    start_z=draw_z,
                    end_x=nx,
                    end_y=ny,
                    end_z=draw_z,
                    feed_rate_mm_min=draw_feed,
                    layer=dpath.layer,
                    element_id=dpath.element_id,
                    path_index=path_idx,
                )
                moves.append(mv_draw)
                draw_dist += mv_draw.distance_xy
                move_idx += 1
                cur_x, cur_y = nx, ny

            # 4. Controlled Pen-Up transition
            mv_up = ToolpathMove(
                index=move_idx,
                move_type=MovementType.PEN_UP,
                start_x=cur_x,
                start_y=cur_y,
                start_z=cur_z,
                end_x=cur_x,
                end_y=cur_y,
                end_z=pen_up_z,
                feed_rate_mm_min=z_feed,
                layer=dpath.layer,
                element_id=dpath.element_id,
                path_index=path_idx,
            )
            moves.append(mv_up)
            move_idx += 1
            pen_lifts += 1
            cur_z = pen_up_z

        if min_x == float("inf"):
            min_x = max_x = min_y = max_y = 0.0

        improvement_pct = 0.0
        if unoptimized_travel > 1e-3 and unoptimized_travel >= travel_dist:
            improvement_pct = ((unoptimized_travel - travel_dist) / unoptimized_travel) * 100.0

        est_time = sum(m.duration_seconds for m in moves)

        stats = ToolpathStats(
            drawing_width_mm=max(0.0, max_x - min_x),
            drawing_height_mm=max(0.0, max_y - min_y),
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
            num_paths=len(final_paths),
            num_movements=len(moves),
            num_pen_lifts=pen_lifts,
            drawing_distance_mm=draw_dist,
            travel_distance_mm=travel_dist,
            total_distance_mm=draw_dist + travel_dist,
            unoptimized_travel_distance_mm=unoptimized_travel,
            optimization_improvement_pct=improvement_pct,
            estimated_time_seconds=est_time,
        )

        return (moves, stats)
