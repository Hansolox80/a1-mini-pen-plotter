"""Interactive 2D CAD-style Build Plate Workspace Canvas with Rulers, Grid, Selection, Measurement, and Live Simulator."""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    BoundingBox,
    DocumentTransform,
    MovementType,
    ParsedSvgDocument,
    ToolpathMove,
)
from app.core.platform_utils import get_mono_font_family, get_system_font_family
from app.core.simulator import SimulationState
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile
from app.ui.icons import make_icon


class CanvasTool(str):
    SELECT = "select"
    PAN = "pan"
    MEASURE = "measure"


class BuildPlateCanvas(QWidget):
    """Central top-down visual representation of the Bambu Lab A1 Mini 180x180mm build plate."""

    transform_dragged = Signal(DocumentTransform, DocumentTransform)  # (old_transform, new_transform)
    transform_preview_changed = Signal(DocumentTransform)
    element_selected = Signal(str)  # element_id or ""
    cursor_mm_changed = Signal(float, float)

    RULER_THICKNESS = 26

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(480, 420)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        # Data state
        self.machine: MachineProfile = MachineProfile()
        self.pen: PenProfile = PenProfile()
        self.svg_doc: Optional[ParsedSvgDocument] = None
        self.doc_transform: DocumentTransform = DocumentTransform()
        self.transformed_elements: list[tuple[object, list[list[tuple[float, float]]]]] = []
        self.drawing_bounds: BoundingBox = BoundingBox(0, 0, 0, 0)
        self.moves: list[ToolpathMove] = []
        self.sim_state: Optional[SimulationState] = None
        self.simulation_active: bool = False
        self.selected_element_id: str = ""

        # Visual toggles
        self.show_grid: bool = True
        self.show_rulers: bool = True
        self.show_safety_margins: bool = True
        self.show_travel_moves: bool = True
        self.show_svg_preview: bool = True
        self.show_toolpath_preview: bool = True
        self.grid_major_mm: float = 30.0
        self.grid_minor_mm: float = 10.0

        # Camera state (pixels per mm, and screen offset of plate origin (0,0) bottom-left)
        self.zoom_px_per_mm: float = 3.2
        self.pan_offset_px: QPointF = QPointF(80.0, 60.0)
        self._first_show: bool = True

        # Interaction state
        self.active_tool: str = CanvasTool.SELECT
        self._is_panning: bool = False
        self._pan_start_mouse: QPointF = QPointF()
        self._pan_start_offset: QPointF = QPointF()

        self._is_dragging_drawing: bool = False
        self._drag_start_mouse_mm: tuple[float, float] = (0.0, 0.0)
        self._drag_start_transform: Optional[DocumentTransform] = None
        self._drag_delta_mm: tuple[float, float] = (0.0, 0.0)

        self._is_measuring: bool = False
        self._measure_start_mm: Optional[tuple[float, float]] = None
        self._measure_end_mm: Optional[tuple[float, float]] = None

        self._cursor_mm: tuple[float, float] = (0.0, 0.0)

        self._build_overlay_hud()

    def _build_overlay_hud(self) -> None:
        """Creates floating CAD toolstrip and live coordinate readout over the canvas."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(self.RULER_THICKNESS + 10, self.RULER_THICKNESS + 10, 12, 12)

        top_row = QHBoxLayout()
        # Floating tool bar card
        tool_card = QFrame(self)
        tool_card.setObjectName("SectionCard")
        tc_layout = QHBoxLayout(tool_card)
        tc_layout.setContentsMargins(6, 4, 6, 4)
        tc_layout.setSpacing(4)

        self.btn_select = QToolButton(tool_card)
        self.btn_select.setIcon(make_icon("pointer"))
        self.btn_select.setToolTip("Select & Move Drawing (V)")
        self.btn_select.setCheckable(True)
        self.btn_select.setChecked(True)
        self.btn_select.clicked.connect(lambda: self.set_active_tool(CanvasTool.SELECT))
        tc_layout.addWidget(self.btn_select)

        self.btn_pan = QToolButton(tool_card)
        self.btn_pan.setIcon(make_icon("pan"))
        self.btn_pan.setToolTip("Pan Workspace (H or Middle Mouse Drag)")
        self.btn_pan.setCheckable(True)
        self.btn_pan.clicked.connect(lambda: self.set_active_tool(CanvasTool.PAN))
        tc_layout.addWidget(self.btn_pan)

        self.btn_measure = QToolButton(tool_card)
        self.btn_measure.setIcon(make_icon("ruler"))
        self.btn_measure.setToolTip("Point-to-Point Measurement Tool (M)")
        self.btn_measure.setCheckable(True)
        self.btn_measure.clicked.connect(lambda: self.set_active_tool(CanvasTool.MEASURE))
        tc_layout.addWidget(self.btn_measure)

        sep1 = QFrame(tool_card)
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #323944;")
        tc_layout.addWidget(sep1)

        self.btn_zoom_in = QToolButton(tool_card)
        self.btn_zoom_in.setIcon(make_icon("zoom_in"))
        self.btn_zoom_in.setToolTip("Zoom In (+)")
        self.btn_zoom_in.clicked.connect(lambda: self.zoom_by(1.25))
        tc_layout.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QToolButton(tool_card)
        self.btn_zoom_out.setIcon(make_icon("zoom_out"))
        self.btn_zoom_out.setToolTip("Zoom Out (-)")
        self.btn_zoom_out.clicked.connect(lambda: self.zoom_by(0.8))
        tc_layout.addWidget(self.btn_zoom_out)

        self.btn_fit = QToolButton(tool_card)
        self.btn_fit.setIcon(make_icon("fit_view"))
        self.btn_fit.setToolTip("Fit 180×180 mm Build Plate to View (F)")
        self.btn_fit.clicked.connect(self.fit_plate_to_view)
        tc_layout.addWidget(self.btn_fit)

        sep2 = QFrame(tool_card)
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #323944;")
        tc_layout.addWidget(sep2)

        self.btn_toggle_grid = QToolButton(tool_card)
        self.btn_toggle_grid.setIcon(make_icon("grid"))
        self.btn_toggle_grid.setToolTip("Toggle Millimeter Grid (G)")
        self.btn_toggle_grid.setCheckable(True)
        self.btn_toggle_grid.setChecked(True)
        self.btn_toggle_grid.toggled.connect(self._on_toggle_grid)
        tc_layout.addWidget(self.btn_toggle_grid)

        self.btn_toggle_travel = QToolButton(tool_card)
        self.btn_toggle_travel.setIcon(make_icon("route", "#38BDF8"))
        self.btn_toggle_travel.setToolTip("Toggle Pen-Up Travel Movements")
        self.btn_toggle_travel.setCheckable(True)
        self.btn_toggle_travel.setChecked(True)
        self.btn_toggle_travel.toggled.connect(self._on_toggle_travel)
        tc_layout.addWidget(self.btn_toggle_travel)

        top_row.addWidget(tool_card)
        top_row.addStretch(1)

        # Top-right coordinate & zoom badge
        coord_card = QFrame(self)
        coord_card.setObjectName("SectionCard")
        cc_layout = QHBoxLayout(coord_card)
        cc_layout.setContentsMargins(10, 4, 10, 4)
        cc_layout.setSpacing(10)

        self.lbl_cursor_xy = QLabel("X:   0.00 mm   Y:   0.00 mm", coord_card)
        self.lbl_cursor_xy.setObjectName("MonoValueLabel")
        cc_layout.addWidget(self.lbl_cursor_xy)

        self.lbl_zoom_pct = QLabel("100%", coord_card)
        self.lbl_zoom_pct.setObjectName("MutedLabel")
        cc_layout.addWidget(self.lbl_zoom_pct)

        top_row.addWidget(coord_card)
        main_layout.addLayout(top_row)
        main_layout.addStretch(1)

    def set_active_tool(self, tool: str) -> None:
        self.active_tool = tool
        self.btn_select.setChecked(tool == CanvasTool.SELECT)
        self.btn_pan.setChecked(tool == CanvasTool.PAN)
        self.btn_measure.setChecked(tool == CanvasTool.MEASURE)
        if tool == CanvasTool.PAN:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif tool == CanvasTool.MEASURE:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def _on_toggle_grid(self, checked: bool) -> None:
        self.show_grid = checked
        self.update()

    def _on_toggle_travel(self, checked: bool) -> None:
        self.show_travel_moves = checked
        self.update()

    # ==========================================================================
    # Coordinate Mapping: Build Plate (mm, Y-up) <-> Screen Widget (px, Y-down)
    # ==========================================================================

    def mm_to_screen(self, x_mm: float, y_mm: float) -> QPointF:
        """Converts build plate millimeter coordinate (0,0 at front-left) to widget pixel position."""
        sx = self.pan_offset_px.x() + x_mm * self.zoom_px_per_mm
        sy = self.height() - self.pan_offset_px.y() - y_mm * self.zoom_px_per_mm
        return QPointF(sx, sy)

    def screen_to_mm(self, pos: QPointF) -> tuple[float, float]:
        """Converts widget pixel position to build plate millimeter coordinate."""
        z = max(0.1, self.zoom_px_per_mm)
        x_mm = (pos.x() - self.pan_offset_px.x()) / z
        y_mm = (self.height() - self.pan_offset_px.y() - pos.y()) / z
        return (x_mm, y_mm)

    def fit_plate_to_view(self) -> None:
        """Centers and scales the 180x180mm build plate cleanly inside the viewport."""
        avail_w = max(100.0, self.width() - self.RULER_THICKNESS - 110.0)
        avail_h = max(100.0, self.height() - self.RULER_THICKNESS - 120.0)
        zx = avail_w / max(1.0, self.machine.nominal_x_mm)
        zy = avail_h / max(1.0, self.machine.nominal_y_mm)
        self.zoom_px_per_mm = max(0.5, min(zx, zy))

        plate_w_px = self.machine.nominal_x_mm * self.zoom_px_per_mm
        plate_h_px = self.machine.nominal_y_mm * self.zoom_px_per_mm

        left_px = self.RULER_THICKNESS + (self.width() - self.RULER_THICKNESS - plate_w_px) * 0.5
        bottom_px = (self.height() - self.RULER_THICKNESS - plate_h_px) * 0.5
        self.pan_offset_px = QPointF(left_px, max(45.0, bottom_px))
        self._update_zoom_label()
        self.update()

    def zoom_by(self, factor: float, anchor_px: Optional[QPointF] = None) -> None:
        if anchor_px is None:
            anchor_px = QPointF(self.width() * 0.5, self.height() * 0.5)
        mm_before = self.screen_to_mm(anchor_px)
        self.zoom_px_per_mm = max(0.4, min(40.0, self.zoom_px_per_mm * factor))
        new_screen = self.mm_to_screen(mm_before[0], mm_before[1])
        dx = anchor_px.x() - new_screen.x()
        dy = new_screen.y() - anchor_px.y()
        self.pan_offset_px = QPointF(self.pan_offset_px.x() + dx, self.pan_offset_px.y() + dy)
        self._update_zoom_label()
        self.update()

    def _update_zoom_label(self) -> None:
        pct = int(round((self.zoom_px_per_mm / 3.2) * 100.0))
        self.lbl_zoom_pct.setText(f"{pct}%")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._first_show and self.width() > 200 and self.height() > 200:
            self._first_show = False
            self.fit_plate_to_view()

    # ==========================================================================
    # Data Update Methods
    # ==========================================================================

    def update_workspace_data(
        self,
        machine: MachineProfile,
        pen: PenProfile,
        svg_doc: Optional[ParsedSvgDocument],
        doc_transform: DocumentTransform,
        transformed_elements: list[tuple[object, list[list[tuple[float, float]]]]],
        drawing_bounds: BoundingBox,
        moves: list[ToolpathMove],
    ) -> None:
        self.machine = machine
        self.pen = pen
        self.svg_doc = svg_doc
        self.doc_transform = doc_transform
        self.transformed_elements = transformed_elements
        self.drawing_bounds = drawing_bounds
        self.moves = moves
        self.update()

    def set_simulation_state(self, state: Optional[SimulationState], active: bool) -> None:
        self.sim_state = state
        self.simulation_active = active
        self.update()

    # ==========================================================================
    # Custom Paint Engine
    # ==========================================================================

    def _make_mono_font(self, point_size: int, bold: bool = False) -> QFont:
        font = QFont(get_mono_font_family(), point_size)
        font.setBold(bold)
        return font

    def _make_ui_font(self, point_size: int, bold: bool = False) -> QFont:
        font = QFont(get_system_font_family(), point_size)
        font.setBold(bold)
        return font

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 1. Backdrop fill
        painter.fillRect(self.rect(), QColor("#0E1013"))

        # 2. Draw Build Plate Surface & Hardware Details
        self._draw_build_plate(painter)

        # 3. Draw Millimeter Grid
        if self.show_grid:
            self._draw_grid(painter)

        # 4. Draw Safety Margins & Usable Area
        if self.show_safety_margins:
            self._draw_safety_margins(painter)

        # 5. Draw Coordinate Axes & Origin Marker
        self._draw_axes_and_origin(painter)

        # 6. Draw Toolpaths & SVG Preview + 7. Selection Gizmo
        has_drag_offset = self._is_dragging_drawing and (
            self._drag_delta_mm[0] != 0.0 or self._drag_delta_mm[1] != 0.0
        )
        if has_drag_offset:
            painter.save()
            sdx = self._drag_delta_mm[0] * self.zoom_px_per_mm
            sdy = -self._drag_delta_mm[1] * self.zoom_px_per_mm
            painter.translate(sdx, sdy)

        self._draw_trajectories(painter)

        if self.transformed_elements and not self.simulation_active:
            self._draw_selection_gizmo(painter)

        if has_drag_offset:
            painter.restore()

        # 8. Draw Simulator Toolhead Marker (when active or moves loaded)
        if self.sim_state is not None and self.moves:
            self._draw_simulator_toolhead(painter)

        # 9. Draw Measurement Overlay
        if self._measure_start_mm and self._measure_end_mm:
            self._draw_measurement_overlay(painter)

        # 10. Draw Top & Left Millimeter Rulers
        if self.show_rulers:
            self._draw_rulers(painter)

        painter.end()

    def _draw_build_plate(self, painter: QPainter) -> None:
        w_mm = self.machine.nominal_x_mm
        h_mm = self.machine.nominal_y_mm
        tl = self.mm_to_screen(0.0, h_mm)
        br = self.mm_to_screen(w_mm, 0.0)
        plate_rect = QRectF(tl, br)

        # Drop shadow
        shadow_rect = plate_rect.translated(0, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 110))
        painter.drawRoundedRect(shadow_rect, 10.0, 10.0)

        # Textured PEI build plate body
        painter.setPen(QPen(QColor("#38414E"), 2.0))
        painter.setBrush(QColor("#171A20"))
        painter.drawRoundedRect(plate_rect, 8.0, 8.0)

        # Front Bambu Lab PEI alignment tab lip
        tab_w = plate_rect.width() * 0.36
        tab_h = max(12.0, min(22.0, 7.0 * self.zoom_px_per_mm))
        tab_rect = QRectF(
            plate_rect.center().x() - tab_w * 0.5,
            plate_rect.bottom() - 2.0,
            tab_w,
            tab_h,
        )
        painter.setPen(QPen(QColor("#38414E"), 1.5))
        painter.setBrush(QColor("#1D222A"))
        painter.drawRoundedRect(tab_rect, 4.0, 4.0)

        # Plate silkscreen branding label
        if self.zoom_px_per_mm >= 1.2:
            font = self._make_ui_font(max(7, min(10, int(self.zoom_px_per_mm * 2.6))), bold=True)
            painter.setFont(font)
            painter.setPen(QColor("#475569"))
            painter.drawText(
                tab_rect,
                Qt.AlignmentFlag.AlignCenter,
                f"BAMBU LAB A1 MINI  •  {w_mm:.0f}×{h_mm:.0f} MM",
            )

    def _draw_grid(self, painter: QPainter) -> None:
        w_mm = self.machine.nominal_x_mm
        h_mm = self.machine.nominal_y_mm

        # Fine 1mm grid when zoomed in deeply
        if self.zoom_px_per_mm >= 8.0:
            pen_fine = QPen(QColor(255, 255, 255, 10), 1.0)
            painter.setPen(pen_fine)
            for x in range(1, int(w_mm)):
                if x % 10 == 0:
                    continue
                p0 = self.mm_to_screen(float(x), 0.0)
                p1 = self.mm_to_screen(float(x), h_mm)
                painter.drawLine(p0, p1)
            for y in range(1, int(h_mm)):
                if y % 10 == 0:
                    continue
                p0 = self.mm_to_screen(0.0, float(y))
                p1 = self.mm_to_screen(w_mm, float(y))
                painter.drawLine(p0, p1)

        # Minor 10mm grid
        minor_step = max(5, int(round(self.grid_minor_mm)))
        major_step = max(10, int(round(self.grid_major_mm)))

        pen_minor = QPen(QColor("#222730"), 1.0)
        pen_major = QPen(QColor("#2E3542"), 1.2)

        x = minor_step
        while x < int(w_mm):
            painter.setPen(pen_major if x % major_step == 0 else pen_minor)
            p0 = self.mm_to_screen(float(x), 0.0)
            p1 = self.mm_to_screen(float(x), h_mm)
            painter.drawLine(p0, p1)
            x += minor_step

        y = minor_step
        while y < int(h_mm):
            painter.setPen(pen_major if y % major_step == 0 else pen_minor)
            p0 = self.mm_to_screen(0.0, float(y))
            p1 = self.mm_to_screen(w_mm, float(y))
            painter.drawLine(p0, p1)
            y += minor_step

    def _draw_safety_margins(self, painter: QPainter) -> None:
        tl = self.mm_to_screen(self.machine.usable_min_x, self.machine.usable_max_y)
        br = self.mm_to_screen(self.machine.usable_max_x, self.machine.usable_min_y)
        safe_rect = QRectF(tl, br)

        pen_safe = QPen(QColor(245, 158, 11, 140), 1.2, Qt.PenStyle.DashLine)
        painter.setPen(pen_safe)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(safe_rect)

        if self.zoom_px_per_mm >= 1.8:
            font = self._make_mono_font(8)
            painter.setFont(font)
            painter.setPen(QColor(245, 158, 11, 160))
            painter.drawText(
                safe_rect.adjusted(6, 4, -6, -4),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                f"SAFE AREA ({self.machine.usable_width_mm:.0f}×{self.machine.usable_height_mm:.0f} mm)",
            )

    def _draw_axes_and_origin(self, painter: QPainter) -> None:
        origin_pt = self.mm_to_screen(0.0, 0.0)
        x_end = self.mm_to_screen(25.0, 0.0)
        y_end = self.mm_to_screen(0.0, 25.0)

        # +X Axis (Red)
        painter.setPen(QPen(QColor("#EF4444"), 2.2))
        painter.drawLine(origin_pt, x_end)
        # +Y Axis (Green)
        painter.setPen(QPen(QColor("#22C55E"), 2.2))
        painter.drawLine(origin_pt, y_end)

        # Origin (0,0) bullseye
        painter.setPen(QPen(QColor("#F8FAFC"), 1.5))
        painter.setBrush(QColor("#EF4444"))
        painter.drawEllipse(origin_pt, 5.0, 5.0)

        font = self._make_mono_font(8, bold=True)
        painter.setFont(font)
        painter.setPen(QColor("#94A3B8"))
        painter.drawText(origin_pt + QPointF(-28, 16), "(0,0)")

    def _draw_trajectories(self, painter: QPainter) -> None:
        # If moves are available, render toolpath moves (supporting progressive simulation mode)
        if self.moves and self.show_toolpath_preview:
            max_idx = len(self.moves) - 1
            prog_in_last = 1.0
            if self.simulation_active and self.sim_state is not None:
                max_idx = self.sim_state.current_move_index
                prog_in_last = self.sim_state.segment_progress

            pan_x = self.pan_offset_px.x()
            pan_y = self.pan_offset_px.y()
            h = self.height()
            z = self.zoom_px_per_mm

            # First pass: dimmed future moves when simulating
            if self.simulation_active and max_idx < len(self.moves) - 1:
                pen_future = QPen(QColor(148, 163, 184, 40), 1.2)
                future_lines: list[QLineF] = []
                for mv in self.moves[max_idx + 1 :]:
                    if mv.move_type == MovementType.DRAW:
                        p0 = QPointF(pan_x + mv.start_x * z, h - pan_y - mv.start_y * z)
                        p1 = QPointF(pan_x + mv.end_x * z, h - pan_y - mv.end_y * z)
                        future_lines.append(QLineF(p0, p1))
                if future_lines:
                    painter.setPen(pen_future)
                    painter.drawLines(future_lines)

            # Level of Detail (LOD) subsampling when zoomed far out and many moves exist
            lod_stride = 1
            if len(self.moves) > 3000 and self.zoom_px_per_mm < 2.0 and not self.simulation_active:
                lod_stride = 2 if self.zoom_px_per_mm >= 1.2 else 3

            # Second pass: Travel moves
            if self.show_travel_moves:
                pen_travel = QPen(QColor(56, 189, 248, 115), 1.0, Qt.PenStyle.DashLine)
                travel_lines: list[QLineF] = []
                for idx in range(0, max_idx + 1, lod_stride if not self.simulation_active else 1):
                    mv = self.moves[idx]
                    if mv.move_type == MovementType.TRAVEL:
                        p0 = QPointF(pan_x + mv.start_x * z, h - pan_y - mv.start_y * z)
                        if idx == max_idx and prog_in_last < 1.0:
                            ex = mv.start_x + (mv.end_x - mv.start_x) * prog_in_last
                            ey = mv.start_y + (mv.end_y - mv.start_y) * prog_in_last
                            p1 = QPointF(pan_x + ex * z, h - pan_y - ey * z)
                        else:
                            p1 = QPointF(pan_x + mv.end_x * z, h - pan_y - mv.end_y * z)
                        travel_lines.append(QLineF(p0, p1))
                if travel_lines:
                    painter.setPen(pen_travel)
                    painter.drawLines(travel_lines)

            # Third pass: Pen-down drawing moves (highlighting out-of-bounds moves in red!)
            stroke_px = max(1.6, self.pen.tip_diameter_mm * self.zoom_px_per_mm)
            pen_draw_ok = QPen(QColor(self.pen.color_hex or "#22C55E"), stroke_px)
            pen_draw_ok.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen_draw_err = QPen(QColor("#EF4444"), stroke_px + 0.6)
            pen_draw_err.setCapStyle(Qt.PenCapStyle.RoundCap)

            w_lim = self.machine.nominal_x_mm
            h_lim = self.machine.nominal_y_mm

            draw_ok_lines: list[QLineF] = []
            draw_err_lines: list[QLineF] = []

            for idx in range(0, max_idx + 1, lod_stride if not self.simulation_active else 1):
                mv = self.moves[idx]
                if mv.move_type == MovementType.DRAW:
                    p0 = QPointF(pan_x + mv.start_x * z, h - pan_y - mv.start_y * z)
                    if idx == max_idx and prog_in_last < 1.0:
                        ex = mv.start_x + (mv.end_x - mv.start_x) * prog_in_last
                        ey = mv.start_y + (mv.end_y - mv.start_y) * prog_in_last
                        p1 = QPointF(pan_x + ex * z, h - pan_y - ey * z)
                    else:
                        p1 = QPointF(pan_x + mv.end_x * z, h - pan_y - mv.end_y * z)

                    out_of_bounds = (
                        mv.start_x < 0.0
                        or mv.end_x < 0.0
                        or mv.start_y < 0.0
                        or mv.end_y < 0.0
                        or mv.start_x > w_lim
                        or mv.end_x > w_lim
                        or mv.start_y > h_lim
                        or mv.end_y > h_lim
                    )
                    if out_of_bounds:
                        draw_err_lines.append(QLineF(p0, p1))
                    else:
                        draw_ok_lines.append(QLineF(p0, p1))

            if draw_ok_lines:
                painter.setPen(pen_draw_ok)
                painter.drawLines(draw_ok_lines)
            if draw_err_lines:
                painter.setPen(pen_draw_err)
                painter.drawLines(draw_err_lines)

        # Also highlight selected individual SVG element if any
        if self.selected_element_id and self.transformed_elements:
            pen_sel = QPen(QColor("#FACC15"), 2.4)
            painter.setPen(pen_sel)
            for el, polys in self.transformed_elements:
                if getattr(el, "id", "") == self.selected_element_id:
                    for poly in polys:
                        if len(poly) >= 2:
                            qpoly = QPolygonF([self.mm_to_screen(px, py) for px, py in poly])
                            painter.drawPolyline(qpoly)

    def _draw_selection_gizmo(self, painter: QPainter) -> None:
        if not self.drawing_bounds.is_valid or (self.drawing_bounds.width == 0 and self.drawing_bounds.height == 0):
            return

        tl = self.mm_to_screen(self.drawing_bounds.min_x, self.drawing_bounds.max_y)
        br = self.mm_to_screen(self.drawing_bounds.max_x, self.drawing_bounds.min_y)
        box = QRectF(tl, br)

        painter.setPen(QPen(QColor(56, 189, 248, 180), 1.2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)

        # Corner handles
        painter.setPen(QPen(QColor("#0E1013"), 1.2))
        painter.setBrush(QColor("#38BDF8"))
        for pt in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
            painter.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))

        # Dimension badge below selection
        dim_text = f"{self.drawing_bounds.width:.2f} × {self.drawing_bounds.height:.2f} mm"
        font = self._make_mono_font(8, bold=True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(dim_text) + 12
        badge_rect = QRectF(box.center().x() - tw * 0.5, box.bottom() + 6, tw, 18)
        painter.setPen(QPen(QColor("#38BDF8"), 1.0))
        painter.setBrush(QColor(18, 21, 25, 220))
        painter.drawRoundedRect(badge_rect, 3.0, 3.0)
        painter.setPen(QColor("#E2E8F0"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, dim_text)

    def _draw_simulator_toolhead(self, painter: QPainter) -> None:
        if self.sim_state is None:
            return
        pt = self.mm_to_screen(self.sim_state.x, self.sim_state.y)

        if self.sim_state.is_pen_down:
            # Pen Down: Solid green glow
            painter.setPen(QPen(QColor("#FFFFFF"), 2.0))
            painter.setBrush(QColor(34, 197, 94, 230))
            painter.drawEllipse(pt, 7.0, 7.0)
            painter.setPen(QPen(QColor(34, 197, 94, 140), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(pt, 12.0, 12.0)
        else:
            # Pen Up: Cyan hollow ring
            painter.setPen(QPen(QColor("#38BDF8"), 2.2))
            painter.setBrush(QColor(14, 16, 19, 200))
            painter.drawEllipse(pt, 7.0, 7.0)

        # Toolhead coordinate tag
        if self.simulation_active:
            state_lbl = "PEN DOWN" if self.sim_state.is_pen_down else "PEN UP"
            tag = f"{state_lbl} ({self.sim_state.x:.1f}, {self.sim_state.y:.1f}, Z{self.sim_state.z:.1f})"
            font = self._make_mono_font(8, bold=True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(tag) + 12
            tag_rect = QRectF(pt.x() + 12, pt.y() - 22, tw, 18)
            painter.setPen(QPen(QColor("#22C55E" if self.sim_state.is_pen_down else "#38BDF8"), 1.0))
            painter.setBrush(QColor(18, 21, 25, 230))
            painter.drawRoundedRect(tag_rect, 3.0, 3.0)
            painter.setPen(QColor("#F8FAFC"))
            painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag)

    def _draw_measurement_overlay(self, painter: QPainter) -> None:
        if not self._measure_start_mm or not self._measure_end_mm:
            return
        x0, y0 = self._measure_start_mm
        x1, y1 = self._measure_end_mm
        p0 = self.mm_to_screen(x0, y0)
        p1 = self.mm_to_screen(x1, y1)

        painter.setPen(QPen(QColor("#FACC15"), 2.0, Qt.PenStyle.DashDotLine))
        painter.drawLine(p0, p1)
        painter.setBrush(QColor("#FACC15"))
        painter.drawEllipse(p0, 4.0, 4.0)
        painter.drawEllipse(p1, 4.0, 4.0)

        dx = x1 - x0
        dy = y1 - y0
        dist = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))
        label = f"D: {dist:.2f} mm  (ΔX: {dx:+.2f}, ΔY: {dy:+.2f} mm, {ang:.1f}°)"

        mid = (p0 + p1) * 0.5
        font = self._make_mono_font(9, bold=True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label) + 14
        rect = QRectF(mid.x() - tw * 0.5, mid.y() - 26, tw, 20)
        painter.setPen(QPen(QColor("#FACC15"), 1.2))
        painter.setBrush(QColor(18, 21, 25, 240))
        painter.drawRoundedRect(rect, 4.0, 4.0)
        painter.setPen(QColor("#FEF08A"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_rulers(self, painter: QPainter) -> None:
        rt = self.RULER_THICKNESS
        w = self.width()
        h = self.height()

        # Ruler backgrounds
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#181B21"))
        painter.drawRect(0, 0, w, rt)
        painter.drawRect(0, 0, rt, h)

        # Borders
        painter.setPen(QPen(QColor("#2B313B"), 1.0))
        painter.drawLine(rt, rt, w, rt)
        painter.drawLine(rt, rt, rt, h)

        font = self._make_mono_font(7)
        painter.setFont(font)

        # Top Horizontal Ruler (X mm)
        min_x_mm, _ = self.screen_to_mm(QPointF(rt, 0))
        max_x_mm, _ = self.screen_to_mm(QPointF(w, 0))
        start_x = int(math.floor(min_x_mm / 5.0) * 5)
        end_x = int(math.ceil(max_x_mm / 5.0) * 5)

        for x_mm in range(start_x, end_x + 1, 5):
            pt = self.mm_to_screen(float(x_mm), 0.0)
            sx = pt.x()
            if sx < rt:
                continue
            is_major = (x_mm % 20 == 0)
            tick_h = 10 if is_major else 5
            painter.setPen(QColor("#64748B" if is_major else "#475569"))
            painter.drawLine(int(sx), rt - tick_h, int(sx), rt)
            if is_major:
                painter.setPen(QColor("#94A3B8"))
                painter.drawText(int(sx) + 3, rt - 11, f"{x_mm}")

        # Left Vertical Ruler (Y mm)
        _, min_y_mm = self.screen_to_mm(QPointF(0, h))
        _, max_y_mm = self.screen_to_mm(QPointF(0, rt))
        start_y = int(math.floor(min_y_mm / 5.0) * 5)
        end_y = int(math.ceil(max_y_mm / 5.0) * 5)

        for y_mm in range(start_y, end_y + 1, 5):
            pt = self.mm_to_screen(0.0, float(y_mm))
            sy = pt.y()
            if sy < rt:
                continue
            is_major = (y_mm % 20 == 0)
            tick_w = 10 if is_major else 5
            painter.setPen(QColor("#64748B" if is_major else "#475569"))
            painter.drawLine(rt - tick_w, int(sy), rt, int(sy))
            if is_major:
                painter.setPen(QColor("#94A3B8"))
                painter.drawText(2, int(sy) - 2, f"{y_mm}")

        # Corner square
        painter.setPen(QPen(QColor("#2B313B"), 1.0))
        painter.setBrush(QColor("#14171C"))
        painter.drawRect(0, 0, rt, rt)
        painter.setPen(QColor("#22C55E"))
        painter.drawText(QRectF(0, 0, rt, rt), Qt.AlignmentFlag.AlignCenter, "mm")

        # Live cursor indicator ticks on rulers
        cur_pt = self.mm_to_screen(self._cursor_mm[0], self._cursor_mm[1])
        painter.setPen(QPen(QColor("#22C55E"), 1.5))
        if cur_pt.x() >= rt:
            painter.drawLine(int(cur_pt.x()), 0, int(cur_pt.x()), rt)
        if cur_pt.y() >= rt:
            painter.drawLine(0, int(cur_pt.y()), rt, int(cur_pt.y()))

    # ==========================================================================
    # Mouse & Keyboard Interaction
    # ==========================================================================

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        self.zoom_by(factor, anchor_px=event.position())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        mm_x, mm_y = self.screen_to_mm(pos)

        # Middle button or Right button or PAN tool -> start panning
        if (
            event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton)
            or (event.button() == Qt.MouseButton.LeftButton and self.active_tool == CanvasTool.PAN)
        ):
            self._is_panning = True
            self._pan_start_mouse = pos
            self._pan_start_offset = QPointF(self.pan_offset_px)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.active_tool == CanvasTool.MEASURE:
                self._is_measuring = True
                self._measure_start_mm = (mm_x, mm_y)
                self._measure_end_mm = (mm_x, mm_y)
                self.update()
                event.accept()
                return

            if self.active_tool == CanvasTool.SELECT and self.transformed_elements:
                # Check if user clicked inside or near the drawing bounds
                b = self.drawing_bounds
                pad_mm = 4.0 / max(0.5, self.zoom_px_per_mm)
                if (
                    b.is_valid
                    and (b.min_x - pad_mm) <= mm_x <= (b.max_x + pad_mm)
                    and (b.min_y - pad_mm) <= mm_y <= (b.max_y + pad_mm)
                ):
                    self._is_dragging_drawing = True
                    self._drag_start_mouse_mm = (mm_x, mm_y)
                    self._drag_delta_mm = (0.0, 0.0)
                    self._drag_start_transform = DocumentTransform.from_dict(self.doc_transform.to_dict())
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    event.accept()
                    return

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        mm_x, mm_y = self.screen_to_mm(pos)
        self._cursor_mm = (mm_x, mm_y)
        self.lbl_cursor_xy.setText(f"X: {mm_x:6.2f} mm   Y: {mm_y:6.2f} mm")
        self.cursor_mm_changed.emit(mm_x, mm_y)

        if self._is_panning:
            dx = pos.x() - self._pan_start_mouse.x()
            dy = self._pan_start_mouse.y() - pos.y()
            self.pan_offset_px = QPointF(
                self._pan_start_offset.x() + dx,
                self._pan_start_offset.y() + dy,
            )
            self.update()
            return

        if self._is_measuring:
            self._measure_end_mm = (mm_x, mm_y)
            self.update()
            return

        if self._is_dragging_drawing and self._drag_start_transform is not None:
            dx_mm = mm_x - self._drag_start_mouse_mm[0]
            dy_mm = mm_y - self._drag_start_mouse_mm[1]
            self._drag_delta_mm = (dx_mm, dy_mm)
            new_t = DocumentTransform.from_dict(self._drag_start_transform.to_dict())
            new_t.pos_x_mm = round(self._drag_start_transform.pos_x_mm + dx_mm, 2)
            new_t.pos_y_mm = round(self._drag_start_transform.pos_y_mm + dy_mm, 2)
            self.transform_preview_changed.emit(new_t)
            self.update()
            return

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            self._is_panning = False
            self.set_active_tool(self.active_tool)
            event.accept()
            return

        if self._is_measuring:
            self._is_measuring = False
            self.update()
            event.accept()
            return

        if self._is_dragging_drawing and self._drag_start_transform is not None:
            self._is_dragging_drawing = False
            self.set_active_tool(self.active_tool)
            old_t = self._drag_start_transform
            dx_mm, dy_mm = self._drag_delta_mm
            self._drag_delta_mm = (0.0, 0.0)
            self._drag_start_transform = None

            new_t = DocumentTransform.from_dict(old_t.to_dict())
            new_t.pos_x_mm = round(old_t.pos_x_mm + dx_mm, 2)
            new_t.pos_y_mm = round(old_t.pos_y_mm + dy_mm, 2)
            self.doc_transform = DocumentTransform.from_dict(new_t.to_dict())

            if (
                abs(old_t.pos_x_mm - new_t.pos_x_mm) > 1e-4
                or abs(old_t.pos_y_mm - new_t.pos_y_mm) > 1e-4
            ):
                self.transform_dragged.emit(old_t, new_t)
            self.update()
            event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_V:
            self.set_active_tool(CanvasTool.SELECT)
        elif key == Qt.Key.Key_H:
            self.set_active_tool(CanvasTool.PAN)
        elif key == Qt.Key.Key_M:
            self.set_active_tool(CanvasTool.MEASURE)
        elif key == Qt.Key.Key_F:
            self.fit_plate_to_view()
        elif key == Qt.Key.Key_G:
            self.btn_toggle_grid.toggle()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_by(1.25)
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.zoom_by(0.8)
        elif key == Qt.Key.Key_Escape:
            self._measure_start_mm = None
            self._measure_end_mm = None
            self.update()
        else:
            super().keyPressEvent(event)
