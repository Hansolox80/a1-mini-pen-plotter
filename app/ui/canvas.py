"""Interactive 2D CAD-style Build Plate Workspace Canvas with Rulers, Grid, Selection, Measurement, and Live Simulator."""

from __future__ import annotations

import math
import time
from typing import Optional

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
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
from app.core.coordinate_system import CoordinateTransformer
from app.core.platform_utils import get_mono_font_family, get_system_font_family
from app.core.simulator import SimulationState
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile
from app.ui.icons import make_icon


class CanvasTool(str):
    SELECT = "select"
    RESIZE = "resize"
    PAN = "pan"
    MEASURE = "measure"


class BuildPlateCanvas(QWidget):
    """Central top-down visual representation of the Bambu Lab A1 Mini 180x180mm build plate."""

    transform_dragged = Signal(DocumentTransform, DocumentTransform)  # (old_transform, new_transform)
    transform_preview_changed = Signal(DocumentTransform)
    scaling_mode_changed = Signal(bool)  # True = proportional (keep aspect), False = freeform stretch
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

        # Interactive Resize & Scaling tool state
        self.is_proportional_scale: bool = True
        self._is_resizing_drawing: bool = False
        self._resize_handle: Optional[str] = None
        self._resize_start_mouse_mm: tuple[float, float] = (0.0, 0.0)
        self._resize_start_bounds: Optional[BoundingBox] = None
        self._resize_start_transform: Optional[DocumentTransform] = None
        self._resize_preview_bounds: Optional[BoundingBox] = None
        self._hovered_handle: Optional[str] = None

        self._is_measuring: bool = False
        self._measure_start_mm: Optional[tuple[float, float]] = None
        self._measure_end_mm: Optional[tuple[float, float]] = None

        self._cursor_mm: tuple[float, float] = (0.0, 0.0)

        # Performance geometry caches (eliminates per-frame allocations & Python loops)
        self._cached_draw_ok_polys: list[QPolygonF] = []
        self._cached_draw_err_lines: list[QLineF] = []
        self._cached_travel_lines: list[QLineF] = []
        self._cached_grid_minor: list[QLineF] = []
        self._cached_grid_major: list[QLineF] = []
        self._cached_grid_fine: list[QLineF] = []
        self._cached_grid_w: float = 0.0
        self._cached_grid_h: float = 0.0
        self._last_cursor_label_text: str = ""
        self._last_preview_emitted_xy: Optional[tuple[float, float]] = None
        self._last_preview_time: float = 0.0
        self._font_ruler: Optional[QFont] = None
        self._font_mono_8_bold: Optional[QFont] = None
        self._font_cache: dict[tuple[int, bool, bool], QFont] = {}

        # Debounced continuous zoom with hardware texture scaling (250+ FPS)
        self._is_zooming_interactive: bool = False
        self._zoom_raster_timer = QTimer(self)
        self._zoom_raster_timer.setSingleShot(True)
        self._zoom_raster_timer.timeout.connect(self._on_zoom_raster_timeout)

        # Pre-vectorized simulation buffers (0 Python allocations per frame, 120+ FPS)
        self._sim_draw_lines: list[QLineF] = []
        self._sim_travel_lines: list[QLineF] = []
        self._sim_move_to_draw_count: list[int] = []
        self._sim_move_to_travel_count: list[int] = []

        # Two-layer display cache (Plate surface & SVG trajectory layers)
        self._plate_pixmap: Optional[QPixmap] = None
        self._plate_pixmap_zoom: float = 0.0
        self._drawing_pixmap: Optional[QPixmap] = None
        self._drawing_pixmap_red: Optional[QPixmap] = None
        self._drawing_pixmap_bounds: BoundingBox = BoundingBox(0, 0, 0, 0)
        self._drawing_pixmap_zoom: float = 0.0
        self._drawing_pad_px: float = 14.0
        self._plate_pad_px: float = 24.0

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

        self.btn_resize_tool = QToolButton(tool_card)
        self.btn_resize_tool.setIcon(make_icon("resize"))
        self.btn_resize_tool.setCheckable(True)
        self.btn_resize_tool.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.btn_resize_tool.clicked.connect(lambda: self.set_active_tool(CanvasTool.RESIZE))

        # Mode Selection Menu for Resize Tool
        self.menu_resize = QMenu(self.btn_resize_tool)
        self.act_prop_scale = QAction("Escala Proporcional (Manter Proporção)", self)
        self.act_prop_scale.setCheckable(True)
        self.act_prop_scale.setChecked(True)
        self.act_prop_scale.triggered.connect(lambda: self.set_proportional_scaling(True))

        self.act_free_scale = QAction("Ajuste Livre (Esticar X / Y Independentes)", self)
        self.act_free_scale.setCheckable(True)
        self.act_free_scale.setChecked(False)
        self.act_free_scale.triggered.connect(lambda: self.set_proportional_scaling(False))

        scale_group = QActionGroup(self)
        scale_group.addAction(self.act_prop_scale)
        scale_group.addAction(self.act_free_scale)
        scale_group.setExclusive(True)

        self.menu_resize.addAction(self.act_prop_scale)
        self.menu_resize.addAction(self.act_free_scale)
        self.btn_resize_tool.setMenu(self.menu_resize)
        self._update_resize_tool_tooltip()
        tc_layout.addWidget(self.btn_resize_tool)

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

    def _update_resize_tool_tooltip(self) -> None:
        mode_label = "Escala Proporcional (Manter Proporção)" if self.is_proportional_scale else "Ajuste Livre (Esticar X/Y)"
        self.btn_resize_tool.setToolTip(
            f"Ferramenta de Redimensionar / Escala (R)\n"
            f"Modo: {mode_label}\n"
            f"• Arraste os cantos ou bordas para redimensionar.\n"
            f"• Segure Shift para inverter o modo temporariamente.\n"
            f"• Clique na setinha do botão para alternar o modo padrão."
        )

    def set_proportional_scaling(self, proportional: bool) -> None:
        self.is_proportional_scale = proportional
        self.act_prop_scale.setChecked(proportional)
        self.act_free_scale.setChecked(not proportional)
        self._update_resize_tool_tooltip()
        self.scaling_mode_changed.emit(proportional)
        self.update()

    def set_active_tool(self, tool: str) -> None:
        self.active_tool = tool
        self.btn_select.setChecked(tool == CanvasTool.SELECT)
        self.btn_resize_tool.setChecked(tool == CanvasTool.RESIZE)
        self.btn_pan.setChecked(tool == CanvasTool.PAN)
        self.btn_measure.setChecked(tool == CanvasTool.MEASURE)
        if tool == CanvasTool.PAN:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif tool == CanvasTool.MEASURE:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == CanvasTool.RESIZE:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def _get_handles(self) -> dict[str, QPointF]:
        if not self.transformed_elements:
            return {}

        b = (
            self._resize_preview_bounds
            if (self._is_resizing_drawing and self._resize_preview_bounds is not None)
            else self.drawing_bounds
        )
        if not b.is_valid:
            return {}

        drag_dx = self._drag_delta_mm[0] if (self._is_dragging_drawing and not self._is_resizing_drawing) else 0.0
        drag_dy = self._drag_delta_mm[1] if (self._is_dragging_drawing and not self._is_resizing_drawing) else 0.0

        min_x = b.min_x + drag_dx
        min_y = b.min_y + drag_dy
        max_x = b.max_x + drag_dx
        max_y = b.max_y + drag_dy

        tl = self.mm_to_screen(min_x, max_y)
        tr = self.mm_to_screen(max_x, max_y)
        bl = self.mm_to_screen(min_x, min_y)
        br = self.mm_to_screen(max_x, min_y)

        tc = QPointF((tl.x() + tr.x()) * 0.5, tl.y())
        bc = QPointF((bl.x() + br.x()) * 0.5, bl.y())
        ml = QPointF(tl.x(), (tl.y() + bl.y()) * 0.5)
        mr = QPointF(tr.x(), (tr.y() + br.y()) * 0.5)

        return {
            "TL": tl,
            "TR": tr,
            "BL": bl,
            "BR": br,
            "TC": tc,
            "BC": bc,
            "ML": ml,
            "MR": mr,
        }

    def _hit_test_handle(self, screen_pos: QPointF) -> Optional[str]:
        handles = self._get_handles()
        if not handles:
            return None

        # Check corners first with 12px radius
        for h in ("TL", "TR", "BL", "BR"):
            pt = handles[h]
            dist_sq = (screen_pos.x() - pt.x()) ** 2 + (screen_pos.y() - pt.y()) ** 2
            if dist_sq <= 144.0:
                return h

        # Check edge handles with 10px radius
        for h in ("TC", "BC", "ML", "MR"):
            pt = handles[h]
            dist_sq = (screen_pos.x() - pt.x()) ** 2 + (screen_pos.y() - pt.y()) ** 2
            if dist_sq <= 100.0:
                return h

        return None

    def _cursor_for_handle(self, handle: str) -> Qt.CursorShape:
        if handle in ("TL", "BR"):
            return Qt.CursorShape.SizeFDiagCursor
        elif handle in ("TR", "BL"):
            return Qt.CursorShape.SizeBDiagCursor
        elif handle in ("ML", "MR"):
            return Qt.CursorShape.SizeHorCursor
        elif handle in ("TC", "BC"):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _invalidate_caches(self, plate: bool = True, drawing: bool = True) -> None:
        if plate:
            self._plate_pixmap = None
            self._plate_pixmap_zoom = 0.0
        if drawing:
            self._drawing_pixmap = None
            self._drawing_pixmap_red = None
            self._drawing_pixmap_zoom = 0.0

    def _on_toggle_grid(self, checked: bool) -> None:
        self.show_grid = checked
        self._invalidate_caches(plate=True, drawing=False)
        self.update()

    def _on_toggle_travel(self, checked: bool) -> None:
        self.show_travel_moves = checked
        self._invalidate_caches(plate=False, drawing=True)
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
        self._invalidate_caches(plate=True, drawing=True)
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

        # Instant GPU texture scaling during continuous zooming (maintains 200+ FPS)
        self._is_zooming_interactive = True
        self._zoom_raster_timer.start(100)
        self.update()

    def _on_zoom_raster_timeout(self) -> None:
        self._is_zooming_interactive = False
        self._invalidate_caches(plate=True, drawing=True)
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

    def _rebuild_cached_grid(self) -> None:
        w_mm = int(self.machine.nominal_x_mm)
        h_mm = int(self.machine.nominal_y_mm)
        if w_mm == self._cached_grid_w and h_mm == self._cached_grid_h and self._cached_grid_minor:
            return
        self._cached_grid_w = float(w_mm)
        self._cached_grid_h = float(h_mm)

        minor_step = max(5, int(round(self.grid_minor_mm)))
        major_step = max(10, int(round(self.grid_major_mm)))

        self._cached_grid_minor = []
        self._cached_grid_major = []
        self._cached_grid_fine = []

        x = minor_step
        while x < w_mm:
            line = QLineF(float(x), 0.0, float(x), float(h_mm))
            if x % major_step == 0:
                self._cached_grid_major.append(line)
            else:
                self._cached_grid_minor.append(line)
            x += minor_step

        y = minor_step
        while y < h_mm:
            line = QLineF(0.0, float(y), float(w_mm), float(y))
            if y % major_step == 0:
                self._cached_grid_major.append(line)
            else:
                self._cached_grid_minor.append(line)
            y += minor_step

    def _rebuild_cached_trajectories(self) -> None:
        self._cached_draw_ok_polys.clear()
        self._cached_draw_err_lines.clear()
        self._cached_travel_lines.clear()
        self._sim_draw_lines.clear()
        self._sim_travel_lines.clear()
        self._sim_move_to_draw_count.clear()
        self._sim_move_to_travel_count.clear()

        if not self.moves:
            return

        transformer = CoordinateTransformer(machine=self.machine, pen=self.pen)
        w_lim = self.machine.nominal_x_mm
        h_lim = self.machine.nominal_y_mm

        current_poly: list[QPointF] = []

        for mv in self.moves:
            psx, psy = transformer.machine_to_plate_xy(mv.start_x, mv.start_y)
            pex, pey = transformer.machine_to_plate_xy(mv.end_x, mv.end_y)

            if mv.move_type == MovementType.DRAW:
                self._sim_draw_lines.append(QLineF(psx, psy, pex, pey))
                oob = (
                    mv.start_x < 0.0
                    or mv.end_x < 0.0
                    or mv.start_y < 0.0
                    or mv.end_y < 0.0
                    or mv.start_x > w_lim
                    or mv.end_x > w_lim
                    or mv.start_y > h_lim
                    or mv.end_y > h_lim
                    or psx < 0.0
                    or pex < 0.0
                    or psy < 0.0
                    or pey < 0.0
                    or psx > w_lim
                    or pex > w_lim
                    or psy > h_lim
                    or pey > h_lim
                )
                if oob:
                    if current_poly:
                        if len(current_poly) >= 2:
                            self._cached_draw_ok_polys.append(QPolygonF(current_poly))
                        current_poly = []
                    self._cached_draw_err_lines.append(
                        QLineF(psx, psy, pex, pey)
                    )
                else:
                    if not current_poly:
                        current_poly.append(QPointF(psx, psy))
                    current_poly.append(QPointF(pex, pey))
            else:
                if current_poly:
                    if len(current_poly) >= 2:
                        self._cached_draw_ok_polys.append(QPolygonF(current_poly))
                    current_poly = []
                if mv.move_type == MovementType.TRAVEL:
                    line = QLineF(psx, psy, pex, pey)
                    self._cached_travel_lines.append(line)
                    self._sim_travel_lines.append(line)

            self._sim_move_to_draw_count.append(len(self._sim_draw_lines))
            self._sim_move_to_travel_count.append(len(self._sim_travel_lines))

        if current_poly and len(current_poly) >= 2:
            self._cached_draw_ok_polys.append(QPolygonF(current_poly))

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
        self._rebuild_cached_grid()
        self._rebuild_cached_trajectories()
        self._invalidate_caches(plate=True, drawing=True)
        self.update()

    def set_simulation_state(self, state: Optional[SimulationState], active: bool) -> None:
        self.sim_state = state
        self.simulation_active = active
        self.update()

    def _render_plate_cache(self) -> None:
        """Renders the physical build plate, grid, safety margins, and origin bullseye to a cached QPixmap."""
        z = self.zoom_px_per_mm
        w_mm = self.machine.nominal_x_mm
        h_mm = self.machine.nominal_y_mm
        pad = self._plate_pad_px

        plate_w_px = max(10, int(math.ceil(w_mm * z + pad * 2.0)))
        # Extra bottom padding for the front PEI alignment tab lip
        plate_h_px = max(10, int(math.ceil(h_mm * z + pad * 2.0 + 30.0)))

        pix = QPixmap(plate_w_px, plate_h_px)
        pix.fill(Qt.GlobalColor.transparent)

        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # In plate pixmap coordinates:
        # Build plate top-left (0, h_mm) is at (pad, pad)
        plate_rect = QRectF(pad, pad, w_mm * z, h_mm * z)

        # 1. Drop shadow
        shadow_rect = plate_rect.translated(0, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawRoundedRect(shadow_rect, 10.0, 10.0)

        # 2. Textured PEI build plate body
        p.setPen(QPen(QColor("#38414E"), 2.0))
        p.setBrush(QColor("#171A20"))
        p.drawRoundedRect(plate_rect, 8.0, 8.0)

        # 3. Front Bambu Lab PEI alignment tab lip
        tab_w = plate_rect.width() * 0.36
        tab_h = max(12.0, min(22.0, 7.0 * z))
        tab_rect = QRectF(
            plate_rect.center().x() - tab_w * 0.5,
            plate_rect.bottom() - 2.0,
            tab_w,
            tab_h,
        )
        p.setPen(QPen(QColor("#38414E"), 1.5))
        p.setBrush(QColor("#1D222A"))
        p.drawRoundedRect(tab_rect, 4.0, 4.0)

        # 4. Silkscreen branding
        if z >= 1.2:
            font = self._make_ui_font(max(7, min(10, int(z * 2.6))), bold=True)
            p.setFont(font)
            p.setPen(QColor("#475569"))
            p.drawText(
                tab_rect,
                Qt.AlignmentFlag.AlignCenter,
                f"BAMBU LAB A1 MINI  •  {w_mm:.0f}×{h_mm:.0f} MM",
            )

        # 5. Transform for plate internal geometry: (0, 0) at front-left
        p.save()
        p.translate(pad, pad + h_mm * z)
        p.scale(z, -z)

        # Millimeter Grid
        if self.show_grid:
            if not self._cached_grid_minor and not self._cached_grid_major:
                self._rebuild_cached_grid()

            if z >= 8.0 and self._cached_grid_fine:
                pen_fine = QPen(QColor(255, 255, 255, 10), 1.0)
                pen_fine.setCosmetic(True)
                p.setPen(pen_fine)
                p.drawLines(self._cached_grid_fine)

            pen_minor = QPen(QColor("#222730"), 1.0)
            pen_minor.setCosmetic(True)
            p.setPen(pen_minor)
            p.drawLines(self._cached_grid_minor)

            pen_major = QPen(QColor("#2E3542"), 1.2)
            pen_major.setCosmetic(True)
            p.setPen(pen_major)
            p.drawLines(self._cached_grid_major)

        # Safety Margins (in plate mm)
        if self.show_safety_margins:
            safe_rect = QRectF(
                self.machine.usable_min_x,
                self.machine.usable_min_y,
                self.machine.usable_width_mm,
                self.machine.usable_height_mm,
            )
            pen_safe = QPen(QColor(245, 158, 11, 140), 1.2, Qt.PenStyle.DashLine)
            pen_safe.setCosmetic(True)
            p.setPen(pen_safe)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(safe_rect)

        # Coordinate axes & Origin (0,0) bullseye
        p.setPen(QPen(QColor("#EF4444"), 2.2))
        p.drawLine(QLineF(0.0, 0.0, 25.0, 0.0))
        p.setPen(QPen(QColor("#22C55E"), 2.2))
        p.drawLine(QLineF(0.0, 0.0, 0.0, 25.0))
        p.setPen(QPen(QColor("#F8FAFC"), 1.5))
        p.setBrush(QColor("#EF4444"))
        p.drawEllipse(QPointF(0.0, 0.0), 3.0, 3.0)

        p.restore()

        # Origin text in screen space
        origin_pt = QPointF(pad, pad + h_mm * z)
        font = self._make_mono_font(8, bold=True)
        p.setFont(font)
        p.setPen(QColor("#94A3B8"))
        p.drawText(origin_pt + QPointF(-28, 16), "(0,0)")

        # Safe area label
        if self.show_safety_margins and z >= 1.8:
            safe_tl = QPointF(pad + self.machine.usable_min_x * z, pad + (h_mm - self.machine.usable_max_y) * z)
            safe_w = self.machine.usable_width_mm * z
            safe_h = self.machine.usable_height_mm * z
            safe_screen_rect = QRectF(safe_tl.x(), safe_tl.y(), safe_w, safe_h)
            font_safe = self._make_mono_font(8)
            p.setFont(font_safe)
            p.setPen(QColor(245, 158, 11, 160))
            p.drawText(
                safe_screen_rect.adjusted(6, 4, -6, -4),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                f"SAFE AREA ({self.machine.usable_width_mm:.0f}×{self.machine.usable_height_mm:.0f} mm)",
            )

        p.end()

        self._plate_pixmap = pix
        self._plate_pixmap_zoom = z

    def _render_drawing_cache(self) -> None:
        """Renders the SVG toolpath trajectories (polylines + travel lines) to a transparent cached QPixmap."""
        if not self.moves or not self.drawing_bounds.is_valid or (self.drawing_bounds.width <= 0 and self.drawing_bounds.height <= 0):
            self._drawing_pixmap = None
            self._drawing_pixmap_red = None
            self._drawing_pixmap_zoom = 0.0
            return

        b = self.drawing_bounds
        z = self.zoom_px_per_mm
        pad = self._drawing_pad_px

        w_px = max(10, int(math.ceil(b.width * z + pad * 2.0)))
        h_px = max(10, int(math.ceil(b.height * z + pad * 2.0)))

        stroke_px = max(1.6, self.pen.tip_diameter_mm * z)

        pen_draw_normal = QPen(QColor(self.pen.color_hex or "#22C55E"), stroke_px)
        pen_draw_normal.setCapStyle(Qt.PenCapStyle.RoundCap)
        use_fast_join = len(self._cached_draw_ok_polys) > 300
        pen_draw_normal.setJoinStyle(Qt.PenJoinStyle.BevelJoin if use_fast_join else Qt.PenJoinStyle.RoundJoin)
        pen_draw_normal.setCosmetic(True)

        pen_travel = QPen(QColor(56, 189, 248, 115), 1.0, Qt.PenStyle.DashLine)
        pen_travel.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen_travel.setCosmetic(True)

        # 1. Normal Color Pixmap (Rendered on GPU / RAM in a single pass)
        pix_normal = QPixmap(w_px, h_px)
        pix_normal.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix_normal)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.translate(pad - b.min_x * z, (h_px - pad) + b.min_y * z)
        p.scale(z, -z)

        if self.show_travel_moves and self._cached_travel_lines:
            p.setPen(pen_travel)
            p.drawLines(self._cached_travel_lines)

        p.setPen(pen_draw_normal)
        for poly in self._cached_draw_ok_polys:
            p.drawPolyline(poly)

        if self._cached_draw_err_lines:
            pen_err = QPen(QColor("#EF4444"), stroke_px + 0.6)
            pen_err.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen_err.setCosmetic(True)
            p.setPen(pen_err)
            p.drawLines(self._cached_draw_err_lines)
        p.end()

        self._drawing_pixmap = pix_normal
        self._drawing_pixmap_red = None  # Lazily generated via instant alpha-tint only if dragged out-of-bounds
        self._drawing_pixmap_bounds = BoundingBox(b.min_x, b.min_y, b.max_x, b.max_y)
        self._drawing_pixmap_zoom = z

    def _get_drawing_pixmap(self, is_oob: bool) -> Optional[QPixmap]:
        if not is_oob or self._drawing_pixmap is None:
            return self._drawing_pixmap
        if self._drawing_pixmap_red is not None:
            return self._drawing_pixmap_red
        # Instant alpha-channel red tint on GPU in 0.05ms (eliminates re-rendering thousands of polylines)
        pix_red = QPixmap(self._drawing_pixmap.size())
        pix_red.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix_red)
        p.drawPixmap(0, 0, self._drawing_pixmap)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(pix_red.rect(), QColor("#EF4444"))
        p.end()
        self._drawing_pixmap_red = pix_red
        return pix_red

    # ==========================================================================
    # Custom Paint Engine
    # ==========================================================================

    def _make_mono_font(self, point_size: int, bold: bool = False) -> QFont:
        key = (point_size, bold, True)
        if key not in self._font_cache:
            font = QFont(get_mono_font_family(), point_size)
            font.setBold(bold)
            self._font_cache[key] = font
        return self._font_cache[key]

    def _make_ui_font(self, point_size: int, bold: bool = False) -> QFont:
        key = (point_size, bold, False)
        if key not in self._font_cache:
            font = QFont(get_system_font_family(), point_size)
            font.setBold(bold)
            self._font_cache[key] = font
        return self._font_cache[key]

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 0. Fast-path: if repaint is restricted solely to the ruler strips (e.g. from mouse hover)
        rt = self.RULER_THICKNESS
        dirty = event.rect()
        if (
            self.show_rulers
            and dirty.isValid()
            and (
                (dirty.x() == 0 and dirty.y() == 0 and dirty.height() <= rt)
                or (dirty.x() == 0 and dirty.y() == 0 and dirty.width() <= rt)
            )
        ):
            self._draw_rulers(painter)
            painter.end()
            return

        # 1. Dark CAD Backdrop Fill
        painter.fillRect(self.rect(), QColor("#0E1013"))

        # 2. Draw Build Plate Layer from Cache (PEI bed, drop shadow, grid, safety margins, axes)
        if self._plate_pixmap is None or (self._plate_pixmap_zoom != self.zoom_px_per_mm and not self._is_zooming_interactive):
            self._render_plate_cache()

        pad_plate = self._plate_pad_px
        plate_tl = self.mm_to_screen(0.0, self.machine.nominal_y_mm)
        if self._plate_pixmap is not None:
            if self._plate_pixmap_zoom == self.zoom_px_per_mm or self._plate_pixmap_zoom <= 0:
                painter.drawPixmap(QPointF(plate_tl.x() - pad_plate, plate_tl.y() - pad_plate), self._plate_pixmap)
            else:
                # GPU Texture Scaling during continuous zooming
                s_plate = self.zoom_px_per_mm / self._plate_pixmap_zoom
                plate_target = QRectF(
                    plate_tl.x() - pad_plate * s_plate,
                    plate_tl.y() - pad_plate * s_plate,
                    self._plate_pixmap.width() * s_plate,
                    self._plate_pixmap.height() * s_plate,
                )
                painter.drawPixmap(plate_target, self._plate_pixmap, QRectF(self._plate_pixmap.rect()))

        # 3. Draw SVG Toolpath Trajectories Layer
        if self.moves and self.show_toolpath_preview:
            if self.simulation_active and self.sim_state is not None:
                self._draw_progressive_simulation(painter)
            else:
                if (
                    self._drawing_pixmap is None
                    or (self._drawing_pixmap_zoom != self.zoom_px_per_mm and not self._is_zooming_interactive)
                    or self._drawing_pixmap_bounds != self.drawing_bounds
                ):
                    self._render_drawing_cache()

                if self._drawing_pixmap is not None:
                    # Check if currently dragging outside plate limits
                    is_oob_drag = False
                    drag_dx = self._drag_delta_mm[0] if self._is_dragging_drawing else 0.0
                    drag_dy = self._drag_delta_mm[1] if self._is_dragging_drawing else 0.0

                    if self._is_dragging_drawing and self.drawing_bounds.is_valid:
                        cur_min_x = self.drawing_bounds.min_x + drag_dx
                        cur_min_y = self.drawing_bounds.min_y + drag_dy
                        cur_max_x = self.drawing_bounds.max_x + drag_dx
                        cur_max_y = self.drawing_bounds.max_y + drag_dy
                        if (
                            cur_min_x < 0.0
                            or cur_min_y < 0.0
                            or cur_max_x > self.machine.nominal_x_mm
                            or cur_max_y > self.machine.nominal_y_mm
                        ):
                            is_oob_drag = True

                    pix = self._get_drawing_pixmap(is_oob_drag)
                    pad_draw = self._drawing_pad_px

                    if self._is_resizing_drawing and self._resize_preview_bounds is not None:
                        pb = self._resize_preview_bounds
                        is_oob_resize = (
                            pb.min_x < 0.0
                            or pb.min_y < 0.0
                            or pb.max_x > self.machine.nominal_x_mm
                            or pb.max_y > self.machine.nominal_y_mm
                        )
                        pix = self._get_drawing_pixmap(is_oob_resize)

                        orig_w_px = max(1.0, self.drawing_bounds.width * self.zoom_px_per_mm)
                        orig_h_px = max(1.0, self.drawing_bounds.height * self.zoom_px_per_mm)
                        new_w_px = max(1.0, pb.width * self.zoom_px_per_mm)
                        new_h_px = max(1.0, pb.height * self.zoom_px_per_mm)
                        sx = new_w_px / orig_w_px
                        sy = new_h_px / orig_h_px

                        new_tl = self.mm_to_screen(pb.min_x, pb.max_y)
                        target_rect = QRectF(
                            new_tl.x() - pad_draw * sx,
                            new_tl.y() - pad_draw * sy,
                            new_w_px + 2.0 * pad_draw * sx,
                            new_h_px + 2.0 * pad_draw * sy,
                        )
                        painter.drawPixmap(target_rect, pix, QRectF(pix.rect()))
                    else:
                        draw_tl = self.mm_to_screen(self.drawing_bounds.min_x, self.drawing_bounds.max_y)
                        drag_px = QPointF(drag_dx * self.zoom_px_per_mm, -drag_dy * self.zoom_px_per_mm)
                        if self._drawing_pixmap_zoom == self.zoom_px_per_mm or self._drawing_pixmap_zoom <= 0:
                            painter.drawPixmap(QPointF(draw_tl.x() - pad_draw, draw_tl.y() - pad_draw) + drag_px, pix)
                        else:
                            # Hardware texture scaling during continuous zooming
                            s_draw = self.zoom_px_per_mm / self._drawing_pixmap_zoom
                            target_rect = QRectF(
                                draw_tl.x() - pad_draw * s_draw + drag_px.x(),
                                draw_tl.y() - pad_draw * s_draw + drag_px.y(),
                                pix.width() * s_draw,
                                pix.height() * s_draw,
                            )
                            painter.drawPixmap(target_rect, pix, QRectF(pix.rect()))

        # 4. Selection Gizmo (Borders & Handles)
        if self.transformed_elements and not self.simulation_active:
            self._draw_selection_gizmo(painter)

        # 5. Highlight individual selected SVG element if any
        if self.selected_element_id and self.transformed_elements:
            pen_sel = QPen(QColor("#FACC15"), 2.4)
            pen_sel.setCosmetic(True)
            painter.setPen(pen_sel)
            painter.save()
            painter.translate(self.pan_offset_px.x(), self.height() - self.pan_offset_px.y())
            painter.scale(self.zoom_px_per_mm, -self.zoom_px_per_mm)
            if self._is_dragging_drawing:
                painter.translate(self._drag_delta_mm[0], self._drag_delta_mm[1])
            for el, polys in self.transformed_elements:
                if getattr(el, "id", "") == self.selected_element_id:
                    for poly in polys:
                        if len(poly) >= 2:
                            qpoly = QPolygonF([QPointF(px, py) for px, py in poly])
                            painter.drawPolyline(qpoly)
            painter.restore()

        # 6. Simulator Toolhead Marker
        if self.sim_state is not None and self.moves:
            self._draw_simulator_toolhead(painter)

        # 7. Measurement Overlay
        if self._measure_start_mm and self._measure_end_mm:
            self._draw_measurement_overlay(painter)

        # 8. Top & Left Millimeter Rulers
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
        if not self._cached_grid_minor and not self._cached_grid_major:
            self._rebuild_cached_grid()

        painter.save()
        painter.translate(self.pan_offset_px.x(), self.height() - self.pan_offset_px.y())
        painter.scale(self.zoom_px_per_mm, -self.zoom_px_per_mm)

        # Fine 1mm grid when zoomed in deeply
        if self.zoom_px_per_mm >= 8.0:
            pen_fine = QPen(QColor(255, 255, 255, 10), 1.0)
            pen_fine.setCosmetic(True)
            painter.setPen(pen_fine)
            if not self._cached_grid_fine:
                w_mm = int(self.machine.nominal_x_mm)
                h_mm = int(self.machine.nominal_y_mm)
                self._cached_grid_fine = [
                    QLineF(float(x), 0.0, float(x), float(h_mm))
                    for x in range(1, w_mm)
                    if x % 10 != 0
                ] + [
                    QLineF(0.0, float(y), float(w_mm), float(y))
                    for y in range(1, h_mm)
                    if y % 10 != 0
                ]
            painter.drawLines(self._cached_grid_fine)

        pen_minor = QPen(QColor("#222730"), 1.0)
        pen_minor.setCosmetic(True)
        painter.setPen(pen_minor)
        painter.drawLines(self._cached_grid_minor)

        pen_major = QPen(QColor("#2E3542"), 1.2)
        pen_major.setCosmetic(True)
        painter.setPen(pen_major)
        painter.drawLines(self._cached_grid_major)

        painter.restore()

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

    def _draw_progressive_simulation(self, painter: QPainter) -> None:
        if not self.moves or self.sim_state is None:
            return

        max_idx = self.sim_state.current_move_index
        prog_in_last = self.sim_state.segment_progress

        draw_count = self._sim_move_to_draw_count[max_idx] if max_idx < len(self._sim_move_to_draw_count) else len(self._sim_draw_lines)
        travel_count = self._sim_move_to_travel_count[max_idx] if max_idx < len(self._sim_move_to_travel_count) else len(self._sim_travel_lines)

        painter.save()
        painter.translate(self.pan_offset_px.x(), self.height() - self.pan_offset_px.y())
        painter.scale(self.zoom_px_per_mm, -self.zoom_px_per_mm)

        # 1. Dimmed future moves (Vectorized batch draw in C++)
        if draw_count < len(self._sim_draw_lines):
            pen_future = QPen(QColor(148, 163, 184, 40), 1.2)
            pen_future.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen_future.setCosmetic(True)
            painter.setPen(pen_future)
            painter.drawLines(self._sim_draw_lines[draw_count:])

        # 2. Completed travel moves
        if self.show_travel_moves and travel_count > 0:
            pen_travel = QPen(QColor(56, 189, 248, 115), 1.0, Qt.PenStyle.DashLine)
            pen_travel.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen_travel.setCosmetic(True)
            painter.setPen(pen_travel)
            painter.drawLines(self._sim_travel_lines[:travel_count])

        # 3. Completed draw moves (Vectorized batch draw in C++)
        stroke_px = max(1.6, self.pen.tip_diameter_mm * self.zoom_px_per_mm)
        pen_draw = QPen(QColor(self.pen.color_hex or "#22C55E"), stroke_px)
        pen_draw.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_draw.setJoinStyle(Qt.PenJoinStyle.BevelJoin if draw_count > 300 else Qt.PenJoinStyle.RoundJoin)
        pen_draw.setCosmetic(True)

        if draw_count > 0:
            painter.setPen(pen_draw)
            painter.drawLines(self._sim_draw_lines[:draw_count])

        # 4. Active move currently in progress (sub-segment interpolation)
        if max_idx < len(self.moves) and prog_in_last < 1.0:
            mv = self.moves[max_idx]
            ex = mv.start_x + (mv.end_x - mv.start_x) * prog_in_last
            ey = mv.start_y + (mv.end_y - mv.start_y) * prog_in_last
            active_line = QLineF(mv.start_x, mv.start_y, ex, ey)
            if mv.move_type == MovementType.DRAW:
                painter.setPen(pen_draw)
                painter.drawLine(active_line)
            elif mv.move_type == MovementType.TRAVEL and self.show_travel_moves:
                pen_travel = QPen(QColor(56, 189, 248, 115), 1.0, Qt.PenStyle.DashLine)
                pen_travel.setCapStyle(Qt.PenCapStyle.FlatCap)
                pen_travel.setCosmetic(True)
                painter.setPen(pen_travel)
                painter.drawLine(active_line)

        painter.restore()

    def _draw_trajectories(self, painter: QPainter) -> None:
        if not self.moves or not self.show_toolpath_preview:
            return

        if self.simulation_active and self.sim_state is not None:
            self._draw_progressive_simulation(painter)
            return

        painter.save()
        painter.translate(self.pan_offset_px.x(), self.height() - self.pan_offset_px.y())
        painter.scale(self.zoom_px_per_mm, -self.zoom_px_per_mm)

        # 1. Travel moves
        if self.show_travel_moves and self._cached_travel_lines:
            pen_travel = QPen(QColor(56, 189, 248, 115), 1.0, Qt.PenStyle.DashLine)
            pen_travel.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen_travel.setCosmetic(True)
            painter.setPen(pen_travel)
            painter.drawLines(self._cached_travel_lines)

        # 2. In-bounds drawing polylines (using hardware-accelerated batch polyline calls)
        if self._cached_draw_ok_polys:
            stroke_px = max(1.6, self.pen.tip_diameter_mm * self.zoom_px_per_mm)

            # Check if dragging outside plate limits to tint whole drawing red
            is_oob_drag = False
            if self._is_dragging_drawing and self.drawing_bounds.is_valid:
                cur_min_x = self.drawing_bounds.min_x + self._drag_delta_mm[0]
                cur_min_y = self.drawing_bounds.min_y + self._drag_delta_mm[1]
                cur_max_x = self.drawing_bounds.max_x + self._drag_delta_mm[0]
                cur_max_y = self.drawing_bounds.max_y + self._drag_delta_mm[1]
                if (
                    cur_min_x < 0.0
                    or cur_min_y < 0.0
                    or cur_max_x > self.machine.nominal_x_mm
                    or cur_max_y > self.machine.nominal_y_mm
                ):
                    is_oob_drag = True

            pen_color = QColor("#EF4444") if is_oob_drag else QColor(self.pen.color_hex or "#22C55E")
            pen_draw_ok = QPen(pen_color, stroke_px)
            pen_draw_ok.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen_draw_ok.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen_draw_ok.setCosmetic(True)
            painter.setPen(pen_draw_ok)

            for poly in self._cached_draw_ok_polys:
                painter.drawPolyline(poly)

        # 3. Out-of-bounds drawing segments (if any)
        if self._cached_draw_err_lines:
            stroke_px = max(1.6, self.pen.tip_diameter_mm * self.zoom_px_per_mm)
            pen_draw_err = QPen(QColor("#EF4444"), stroke_px + 0.6)
            pen_draw_err.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen_draw_err.setCosmetic(True)
            painter.setPen(pen_draw_err)
            painter.drawLines(self._cached_draw_err_lines)

        painter.restore()

        # 4. Highlight individual selected SVG element if any
        if self.selected_element_id and self.transformed_elements:
            pen_sel = QPen(QColor("#FACC15"), 2.4)
            pen_sel.setCosmetic(True)
            painter.setPen(pen_sel)
            painter.save()
            painter.translate(self.pan_offset_px.x(), self.height() - self.pan_offset_px.y())
            painter.scale(self.zoom_px_per_mm, -self.zoom_px_per_mm)
            for el, polys in self.transformed_elements:
                if getattr(el, "id", "") == self.selected_element_id:
                    for poly in polys:
                        if len(poly) >= 2:
                            qpoly = QPolygonF([QPointF(px, py) for px, py in poly])
                            painter.drawPolyline(qpoly)
            painter.restore()

    def _draw_selection_gizmo(self, painter: QPainter) -> None:
        if not self.drawing_bounds.is_valid or (self.drawing_bounds.width == 0 and self.drawing_bounds.height == 0):
            return

        if self._is_resizing_drawing and self._resize_preview_bounds is not None:
            cur_min_x = self._resize_preview_bounds.min_x
            cur_min_y = self._resize_preview_bounds.min_y
            cur_max_x = self._resize_preview_bounds.max_x
            cur_max_y = self._resize_preview_bounds.max_y
        else:
            drag_dx = self._drag_delta_mm[0] if self._is_dragging_drawing else 0.0
            drag_dy = self._drag_delta_mm[1] if self._is_dragging_drawing else 0.0
            cur_min_x = self.drawing_bounds.min_x + drag_dx
            cur_min_y = self.drawing_bounds.min_y + drag_dy
            cur_max_x = self.drawing_bounds.max_x + drag_dx
            cur_max_y = self.drawing_bounds.max_y + drag_dy

        is_oob = False
        if (
            cur_min_x < 0.0
            or cur_min_y < 0.0
            or cur_max_x > self.machine.nominal_x_mm
            or cur_max_y > self.machine.nominal_y_mm
        ):
            is_oob = True

        tl = self.mm_to_screen(cur_min_x, cur_max_y)
        br = self.mm_to_screen(cur_max_x, cur_min_y)
        box = QRectF(tl, br)

        gizmo_color = QColor("#EF4444") if is_oob else QColor(56, 189, 248, 180)
        handle_color = QColor("#EF4444") if is_oob else QColor("#38BDF8")

        painter.setPen(QPen(gizmo_color, 1.2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)

        # Handles rendering (Corners & Edge midpoints)
        handles = self._get_handles()
        is_resize_tool = (self.active_tool == CanvasTool.RESIZE)
        corner_s = 10.0 if is_resize_tool else 8.0
        edge_s = 8.0 if is_resize_tool else 6.0

        for name, pt in handles.items():
            is_hovered = (name == self._hovered_handle) or (name == self._resize_handle)
            if name in ("TL", "TR", "BL", "BR"):
                rect = QRectF(pt.x() - corner_s * 0.5, pt.y() - corner_s * 0.5, corner_s, corner_s)
                if is_hovered:
                    painter.setPen(QPen(QColor("#FFFFFF"), 1.8))
                    painter.setBrush(QColor("#22C55E"))
                else:
                    painter.setPen(QPen(QColor("#0E1013"), 1.2))
                    painter.setBrush(handle_color)
                painter.drawRoundedRect(rect, 1.5, 1.5)
            else:
                rect = QRectF(pt.x() - edge_s * 0.5, pt.y() - edge_s * 0.5, edge_s, edge_s)
                if is_hovered:
                    painter.setPen(QPen(QColor("#FFFFFF"), 1.8))
                    painter.setBrush(QColor("#22C55E"))
                else:
                    painter.setPen(QPen(QColor("#0E1013"), 1.2))
                    painter.setBrush(QColor(handle_color.red(), handle_color.green(), handle_color.blue(), 180))
                painter.drawEllipse(rect)

        # Dimension badge below selection
        cur_w = cur_max_x - cur_min_x
        cur_h = cur_max_y - cur_min_y
        mode_str = " (Prop)" if self.is_proportional_scale else " (Livre)"
        dim_text = f"{cur_w:.2f} × {cur_h:.2f} mm{mode_str if is_resize_tool else ''}"
        font = self._make_mono_font(8, bold=True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(dim_text) + 12
        badge_rect = QRectF(box.center().x() - tw * 0.5, box.bottom() + 6, tw, 18)
        painter.setPen(QPen(handle_color, 1.0))
        painter.setBrush(QColor(18, 21, 25, 220))
        painter.drawRoundedRect(badge_rect, 3.0, 3.0)
        painter.setPen(QColor("#E2E8F0"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, dim_text)

    def _draw_simulator_toolhead(self, painter: QPainter) -> None:
        if self.sim_state is None:
            return
        transformer = CoordinateTransformer(machine=self.machine, pen=self.pen)
        px, py = transformer.machine_to_plate_xy(self.sim_state.x, self.sim_state.y)
        pt = self.mm_to_screen(px, py)

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
            tag = f"{state_lbl} ({px:.1f}, {py:.1f}, Z{self.sim_state.z:.1f})"
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

            # Check handle click first for both RESIZE and SELECT tools
            if self.transformed_elements and self.drawing_bounds.is_valid:
                handle = self._hit_test_handle(pos)
                if handle is not None:
                    self._is_resizing_drawing = True
                    self._resize_handle = handle
                    self._resize_start_mouse_mm = (mm_x, mm_y)
                    self._resize_start_bounds = BoundingBox(
                        self.drawing_bounds.min_x,
                        self.drawing_bounds.min_y,
                        self.drawing_bounds.max_x,
                        self.drawing_bounds.max_y,
                    )
                    self._resize_start_transform = DocumentTransform.from_dict(self.doc_transform.to_dict())
                    self._resize_preview_bounds = BoundingBox(
                        self.drawing_bounds.min_x,
                        self.drawing_bounds.min_y,
                        self.drawing_bounds.max_x,
                        self.drawing_bounds.max_y,
                    )
                    self.setCursor(self._cursor_for_handle(handle))
                    event.accept()
                    return

            if self.active_tool == CanvasTool.RESIZE and self.transformed_elements:
                b = self.drawing_bounds
                if b.is_valid and (b.min_x <= mm_x <= b.max_x) and (b.min_y <= mm_y <= b.max_y):
                    corners = [
                        ("TL", b.min_x, b.max_y),
                        ("TR", b.max_x, b.max_y),
                        ("BL", b.min_x, b.min_y),
                        ("BR", b.max_x, b.min_y),
                    ]
                    closest_h = min(corners, key=lambda c: (mm_x - c[1]) ** 2 + (mm_y - c[2]) ** 2)[0]
                    self._is_resizing_drawing = True
                    self._resize_handle = closest_h
                    self._resize_start_mouse_mm = (mm_x, mm_y)
                    self._resize_start_bounds = BoundingBox(b.min_x, b.min_y, b.max_x, b.max_y)
                    self._resize_start_transform = DocumentTransform.from_dict(self.doc_transform.to_dict())
                    self._resize_preview_bounds = BoundingBox(b.min_x, b.min_y, b.max_x, b.max_y)
                    self.setCursor(self._cursor_for_handle(closest_h))
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
                    self._last_preview_emitted_xy = None
                    self._drag_start_transform = DocumentTransform.from_dict(self.doc_transform.to_dict())
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    event.accept()
                    return

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        mm_x, mm_y = self.screen_to_mm(pos)
        self._cursor_mm = (mm_x, mm_y)

        # Update cursor HUD label only when formatted text changes
        lbl_text = f"X: {mm_x:6.2f} mm   Y: {mm_y:6.2f} mm"
        if lbl_text != self._last_cursor_label_text:
            self._last_cursor_label_text = lbl_text
            self.lbl_cursor_xy.setText(lbl_text)

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

        if self._is_resizing_drawing and self._resize_start_transform is not None:
            handle = self._resize_handle
            orig_b = self._resize_start_bounds
            orig_t = self._resize_start_transform
            if not orig_b or not orig_b.is_valid:
                return

            proportional = self.is_proportional_scale
            if bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                proportional = not proportional

            orig_w = max(0.1, orig_b.width)
            orig_h = max(0.1, orig_b.height)

            if handle == "TR":
                raw_w = mm_x - orig_b.min_x
                raw_h = mm_y - orig_b.min_y
            elif handle == "TL":
                raw_w = orig_b.max_x - mm_x
                raw_h = mm_y - orig_b.min_y
            elif handle == "BR":
                raw_w = mm_x - orig_b.min_x
                raw_h = orig_b.max_y - mm_y
            elif handle == "BL":
                raw_w = orig_b.max_x - mm_x
                raw_h = orig_b.max_y - mm_y
            elif handle == "MR":
                raw_w = mm_x - orig_b.min_x
                raw_h = orig_h
            elif handle == "ML":
                raw_w = orig_b.max_x - mm_x
                raw_h = orig_h
            elif handle == "TC":
                raw_w = orig_w
                raw_h = mm_y - orig_b.min_y
            elif handle == "BC":
                raw_w = orig_w
                raw_h = orig_b.max_y - mm_y
            else:
                raw_w, raw_h = orig_w, orig_h

            if proportional:
                aspect = orig_w / orig_h
                if handle in ("MR", "ML"):
                    new_w = max(1.0, raw_w)
                    new_h = new_w / aspect
                elif handle in ("TC", "BC"):
                    new_h = max(1.0, raw_h)
                    new_w = new_h * aspect
                else:
                    sx = raw_w / orig_w
                    sy = raw_h / orig_h
                    scale = max(0.02, (sx + sy) * 0.5)
                    new_w = max(1.0, orig_w * scale)
                    new_h = max(1.0, orig_h * scale)
            else:
                new_w = max(1.0, raw_w)
                new_h = max(1.0, raw_h)

            if handle in ("TR", "MR"):
                new_min_x = orig_b.min_x
                new_max_x = new_min_x + new_w
            elif handle in ("TL", "ML"):
                new_max_x = orig_b.max_x
                new_min_x = new_max_x - new_w
            else:
                new_min_x = orig_b.min_x
                new_max_x = new_min_x + new_w

            if handle in ("TR", "TL", "TC"):
                new_min_y = orig_b.min_y
                new_max_y = new_min_y + new_h
            elif handle in ("BR", "BL", "BC"):
                new_max_y = orig_b.max_y
                new_min_y = new_max_y - new_h
            else:
                new_min_y = orig_b.min_y
                new_max_y = new_min_y + new_h

            self._resize_preview_bounds = BoundingBox(new_min_x, new_min_y, new_max_x, new_max_y)

            native_b = self.svg_doc.compute_native_bounds() if self.svg_doc else None
            native_w = native_b.width if (native_b and native_b.is_valid and native_b.width > 0) else orig_w
            native_h = native_b.height if (native_b and native_b.is_valid and native_b.height > 0) else orig_h

            new_t = DocumentTransform.from_dict(orig_t.to_dict())
            new_t.scale_x = round(new_w / native_w, 4)
            new_t.scale_y = round(new_h / native_h, 4)
            new_t.pos_x_mm = round(new_min_x, 2)
            new_t.pos_y_mm = round(new_min_y, 2)

            now = time.perf_counter()
            cur_st = (new_t.scale_x, new_t.scale_y, new_t.pos_x_mm, new_t.pos_y_mm)
            if cur_st != self._last_preview_emitted_xy and (now - self._last_preview_time) >= 0.025:
                self._last_preview_time = now
                self._last_preview_emitted_xy = cur_st
                self.transform_preview_changed.emit(new_t)

            self.update()
            return

        if self._is_dragging_drawing and self._drag_start_transform is not None:
            dx_mm = mm_x - self._drag_start_mouse_mm[0]
            dy_mm = mm_y - self._drag_start_mouse_mm[1]
            self._drag_delta_mm = (dx_mm, dy_mm)
            new_t = DocumentTransform.from_dict(self._drag_start_transform.to_dict())
            new_t.pos_x_mm = round(self._drag_start_transform.pos_x_mm + dx_mm, 2)
            new_t.pos_y_mm = round(self._drag_start_transform.pos_y_mm + dy_mm, 2)

            # Throttle inspector spinbox updates during drag to 40 Hz to avoid event-loop clogging
            now = time.perf_counter()
            cur_xy = (new_t.pos_x_mm, new_t.pos_y_mm)
            if cur_xy != self._last_preview_emitted_xy and (now - self._last_preview_time) >= 0.025:
                self._last_preview_time = now
                self._last_preview_emitted_xy = cur_xy
                self.transform_preview_changed.emit(new_t)

            self.update()
            return

        if not self._is_panning and not self._is_dragging_drawing and not self._is_resizing_drawing:
            hovered = self._hit_test_handle(pos)
            if hovered != self._hovered_handle:
                self._hovered_handle = hovered
                self.update()
            if hovered:
                self.setCursor(self._cursor_for_handle(hovered))
            elif self.active_tool == CanvasTool.RESIZE:
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif self.active_tool == CanvasTool.SELECT:
                b = self.drawing_bounds
                pad_mm = 4.0 / max(0.5, self.zoom_px_per_mm)
                if (
                    b.is_valid
                    and (b.min_x - pad_mm) <= mm_x <= (b.max_x + pad_mm)
                    and (b.min_y - pad_mm) <= mm_y <= (b.max_y + pad_mm)
                ):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

        # Only invalidate the thin ruler strips for the cursor tick marks
        # Avoid full plate repaint to maintain 60+ FPS during mouse movement
        rt = self.RULER_THICKNESS
        self.update(0, 0, self.width(), rt)
        self.update(0, 0, rt, self.height())

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

        if self._is_resizing_drawing and self._resize_start_transform is not None:
            self._is_resizing_drawing = False
            old_t = self._resize_start_transform
            preview_b = self._resize_preview_bounds
            self._resize_preview_bounds = None
            self._resize_start_transform = None
            self._resize_start_bounds = None
            self._resize_handle = None

            if preview_b and preview_b.is_valid:
                new_w = preview_b.width
                new_h = preview_b.height
                native_b = self.svg_doc.compute_native_bounds() if self.svg_doc else None
                native_w = native_b.width if (native_b and native_b.is_valid and native_b.width > 0) else old_t.scale_x
                native_h = native_b.height if (native_b and native_b.is_valid and native_b.height > 0) else old_t.scale_y

                new_t = DocumentTransform.from_dict(old_t.to_dict())
                new_t.scale_x = round(new_w / native_w, 4)
                new_t.scale_y = round(new_h / native_h, 4)
                new_t.pos_x_mm = round(preview_b.min_x, 2)
                new_t.pos_y_mm = round(preview_b.min_y, 2)

                self.doc_transform = DocumentTransform.from_dict(new_t.to_dict())
                self.transform_preview_changed.emit(new_t)
                self._invalidate_caches(plate=False, drawing=True)

                if (
                    abs(old_t.scale_x - new_t.scale_x) > 1e-4
                    or abs(old_t.scale_y - new_t.scale_y) > 1e-4
                    or abs(old_t.pos_x_mm - new_t.pos_x_mm) > 1e-4
                    or abs(old_t.pos_y_mm - new_t.pos_y_mm) > 1e-4
                ):
                    self.transform_dragged.emit(old_t, new_t)

            self.set_active_tool(self.active_tool)
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

            # Ensure inspector reflects final coordinates
            self.transform_preview_changed.emit(new_t)
            self._invalidate_caches(plate=False, drawing=True)

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
        elif key in (Qt.Key.Key_R, Qt.Key.Key_S):
            self.set_active_tool(CanvasTool.RESIZE)
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
