"""Cross-platform Custom Window Chrome system for Windows, macOS, and Linux."""

from __future__ import annotations

import sys
from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import get_theme_tokens


CHROME_STYLES: dict[str, dict[str, Any]] = {
    "minimal_flat": {
        "id": "minimal_flat",
        "name": "Minimal Flat",
        "category": "Custom",
        "recommended": True,
        "layout": "stacked",
        "controls_side": "right",
        "title_align": "left",
        "button_shape": "flat",
        "close_always_red": False,
        "top_accent_bar": False,
        "height": 32,
        "desc": "Clean flat titlebar with crisp monochrome glyphs and subtle hover highlight",
    },
    "modern_red_pill": {
        "id": "modern_red_pill",
        "name": "Modern Pill Close",
        "category": "Custom",
        "recommended": False,
        "layout": "stacked",
        "controls_side": "right",
        "title_align": "left",
        "button_shape": "pill_hover",
        "close_always_red": True,
        "top_accent_bar": False,
        "height": 34,
        "desc": "Modern rounded-pill close highlight with soft rounded window controls",
    },
    "capsule_buttons": {
        "id": "capsule_buttons",
        "name": "Capsule Control Tiles",
        "category": "Custom",
        "recommended": False,
        "layout": "stacked",
        "controls_side": "right",
        "title_align": "left",
        "button_shape": "capsule",
        "close_always_red": True,
        "top_accent_bar": False,
        "height": 36,
        "desc": "Elevated capsule control tiles with a permanent crimson close button",
    },
    "macos_traffic": {
        "id": "macos_traffic",
        "name": "macOS Traffic Lights",
        "category": "Custom",
        "recommended": False,
        "layout": "stacked",
        "controls_side": "left",
        "title_align": "center",
        "button_shape": "traffic",
        "close_always_red": True,
        "top_accent_bar": False,
        "height": 34,
        "desc": "Left-aligned circular traffic-light buttons with centered title (cross-platform)",
    },
    "cad_unified": {
        "id": "cad_unified",
        "name": "CAD Unified Studio",
        "category": "Custom",
        "recommended": False,
        "layout": "unified",
        "controls_side": "right",
        "title_align": "center",
        "button_shape": "pill_hover",
        "close_always_red": False,
        "top_accent_bar": False,
        "height": 36,
        "desc": "Single-row header integrating menu bar, centered title, and controls to maximize canvas",
    },
    "cyber_accent": {
        "id": "cyber_accent",
        "name": "Accent Edge Strip",
        "category": "Custom",
        "recommended": False,
        "layout": "stacked",
        "controls_side": "right",
        "title_align": "left",
        "button_shape": "sharp",
        "close_always_red": False,
        "top_accent_bar": True,
        "height": 34,
        "desc": "Technical CAD header with 2px top accent strip and crisp geometric controls",
    },
    "floating_glass": {
        "id": "floating_glass",
        "name": "Soft Circular Floating",
        "category": "Custom",
        "recommended": False,
        "layout": "stacked",
        "controls_side": "right",
        "title_align": "center",
        "button_shape": "circle",
        "close_always_red": False,
        "top_accent_bar": False,
        "height": 36,
        "desc": "Spacious centered titlebar with soft circular window control buttons",
    },
    "native": {
        "id": "native",
        "name": "System Native OS Frame",
        "category": "Native",
        "recommended": False,
        "layout": "native",
        "controls_side": "right",
        "title_align": "left",
        "button_shape": "flat",
        "close_always_red": False,
        "top_accent_bar": False,
        "height": 0,
        "desc": "Standard OS window frame & titlebar (Windows DWM / macOS Aqua / Linux WM)",
    },
}

DEFAULT_CHROME_STYLE = "minimal_flat"


def get_chrome_style(chrome_id: str | None = None) -> dict[str, Any]:
    if chrome_id and chrome_id in CHROME_STYLES:
        return CHROME_STYLES[chrome_id]
    return CHROME_STYLES[DEFAULT_CHROME_STYLE]


def list_chrome_styles(category: str | None = None) -> list[dict[str, Any]]:
    items = list(CHROME_STYLES.values())
    if category:
        cat_l = category.lower()
        items = [c for c in items if c["category"].lower() == cat_l]
    return items


def is_custom_chrome(chrome_id: str | None) -> bool:
    return get_chrome_style(chrome_id)["id"] != "native"


def _draw_chrome_glyph(
    painter: QPainter,
    rect: QRectF,
    kind: str,
    color: QColor,
    stroke_w: float = 1.35,
) -> None:
    """Draws pixel-crisp vector window control glyphs independent of OS fonts."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color, stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    cx = rect.center().x()
    cy = rect.center().y()
    r = min(rect.width(), rect.height()) * 0.22

    if kind == "minimize":
        painter.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
    elif kind == "maximize":
        box = QRectF(cx - r, cy - r, r * 2.0, r * 2.0)
        painter.drawRoundedRect(box, 1.0, 1.0)
    elif kind == "restore":
        off = r * 0.34
        s = r * 1.55
        back = QRectF(cx - r + off, cy - r, s, s)
        front = QRectF(cx - r, cy - r + off, s, s)
        painter.drawLine(QPointF(back.left(), back.top() + off), QPointF(back.left(), back.top()))
        painter.drawLine(QPointF(back.left(), back.top()), QPointF(back.right(), back.top()))
        painter.drawLine(QPointF(back.right(), back.top()), QPointF(back.right(), back.bottom()))
        painter.drawLine(QPointF(back.right(), back.bottom()), QPointF(front.right(), back.bottom()))
        painter.drawRoundedRect(front, 0.8, 0.8)
    elif kind == "close":
        painter.drawLine(QPointF(cx - r, cy - r), QPointF(cx + r, cy + r))
        painter.drawLine(QPointF(cx + r, cy - r), QPointF(cx - r, cy + r))
    elif kind == "traffic_plus":
        pr = r * 0.85
        painter.drawLine(QPointF(cx - pr, cy), QPointF(cx + pr, cy))
        painter.drawLine(QPointF(cx, cy - pr), QPointF(cx, cy + pr))

    painter.restore()


class _ChromeControlButton(QPushButton):
    """Cross-platform painted window control button supporting multiple chrome designs."""

    def __init__(self, kind: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.kind = kind  # "minimize", "maximize", "close"
        self.is_maximized_state = False
        self._hovered = False
        self._pressed = False
        self._style_id = DEFAULT_CHROME_STYLE
        self._group_hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.apply_chrome_style(DEFAULT_CHROME_STYLE)

    def apply_chrome_style(self, style_id: str) -> None:
        self._style_id = style_id
        cfg = get_chrome_style(style_id)
        shape = cfg["button_shape"]
        if shape == "traffic":
            self.setFixedSize(20, 20)
        elif shape == "capsule":
            self.setFixedSize(36, 24)
        elif shape == "circle":
            self.setFixedSize(26, 26)
        elif shape == "pill_hover":
            self.setFixedSize(36, 24)
        else:
            self.setFixedSize(40, 28)
        self.update()

    def set_group_hovered(self, hovered: bool) -> None:
        if self._group_hovered != hovered:
            self._group_hovered = hovered
            self.update()

    def set_maximized_state(self, is_max: bool) -> None:
        if self.is_maximized_state != is_max:
            self.is_maximized_state = is_max
            self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cfg = get_chrome_style(self._style_id)
        shape = cfg["button_shape"]
        t = get_theme_tokens()
        rect = QRectF(self.rect())

        if shape == "traffic":
            colors = {
                "close": ("#FF5F57", "#E0443E", "#4D0000"),
                "minimize": ("#FEBC2E", "#D89E24", "#5A3D00"),
                "maximize": ("#28C840", "#1FA734", "#004D0E"),
            }
            base_hex, press_hex, glyph_hex = colors.get(self.kind, ("#94A3B8", "#64748B", "#0F172A"))
            dot_rect = rect.adjusted(3.5, 3.5, -3.5, -3.5)
            fill_c = QColor(press_hex if self._pressed else base_hex)
            painter.setPen(QPen(fill_c.darker(118), 1.0))
            painter.setBrush(fill_c)
            painter.drawEllipse(dot_rect)
            if self._hovered or self._group_hovered:
                glyph_kind = "traffic_plus" if self.kind == "maximize" else self.kind
                _draw_chrome_glyph(painter, dot_rect, glyph_kind, QColor(glyph_hex), stroke_w=1.25)
            painter.end()
            return

        # Rectangular / pill / capsule / circle styles
        is_close = self.kind == "close"
        always_red = bool(cfg["close_always_red"]) and is_close

        bg_color = QColor(0, 0, 0, 0)
        border_color = QColor(0, 0, 0, 0)
        fg_color = QColor(t["text_primary"])

        if shape == "capsule":
            inner = rect.adjusted(2.0, 2.0, -2.0, -2.0)
            radius = 7.0
            if is_close:
                bg_color = QColor("#B91C1C" if self._pressed else ("#DC2626" if self._hovered else "#C42B1C"))
                border_color = QColor("#EF4444" if self._hovered else "#991B1B")
                fg_color = QColor("#FFFFFF")
            else:
                base_tile = QColor(t["bg_surface_hover"] if self._hovered else t["bg_surface"])
                if self._pressed:
                    base_tile = QColor(t["bg_input"])
                bg_color = base_tile
                border_color = QColor(t["border_hover"] if self._hovered else t["border_default"])
        elif shape == "pill_hover":
            inner = rect.adjusted(2.0, 2.0, -2.0, -2.0)
            radius = 7.0
            if always_red or (is_close and self._hovered):
                if self._pressed:
                    bg_color = QColor("#991B1B")
                elif self._hovered or always_red:
                    bg_color = QColor("#DC2626" if self._hovered else "#C42B1C")
                fg_color = QColor("#FFFFFF")
            elif self._pressed:
                bg_color = QColor(t["bg_input"])
            elif self._hovered:
                bg_color = QColor(t["bg_surface_hover"])
        elif shape == "circle":
            inner = rect.adjusted(2.0, 2.0, -2.0, -2.0)
            radius = inner.height() * 0.5
            if is_close and (self._hovered or self._pressed):
                bg_color = QColor("#991B1B" if self._pressed else "#DC2626")
                fg_color = QColor("#FFFFFF")
            elif self._pressed:
                bg_color = QColor(t["bg_input"])
            elif self._hovered:
                bg_color = QColor(t["bg_surface_hover"])
                border_color = QColor(t["border_default"])
        else:  # "flat" or "sharp"
            inner = rect.adjusted(0.5, 0.5, -0.5, -0.5)
            radius = 0.0 if shape == "sharp" else 4.0
            if is_close and (self._hovered or self._pressed):
                bg_color = QColor("#991B1B" if self._pressed else "#DC2626")
                fg_color = QColor("#FFFFFF")
            elif self._pressed:
                bg_color = QColor(t["bg_input"])
            elif self._hovered:
                bg_color = QColor(t["bg_surface_hover"])

        if bg_color.alpha() > 0 or border_color.alpha() > 0:
            painter.setPen(QPen(border_color, 1.0) if border_color.alpha() > 0 else Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            if radius > 0:
                painter.drawRoundedRect(inner, radius, radius)
            else:
                painter.drawRect(inner)

        glyph_kind = "restore" if (self.kind == "maximize" and self.is_maximized_state) else self.kind
        _draw_chrome_glyph(painter, inner, glyph_kind, fg_color, stroke_w=1.35)
        painter.end()


class _TrafficGroupWidget(QWidget):
    """Groups window control buttons so macOS traffic lights can show glyphs on group hover."""

    def __init__(self, buttons: list[_ChromeControlButton], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._buttons = buttons
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, event) -> None:
        for b in self._buttons:
            b.set_group_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        for b in self._buttons:
            b.set_group_hovered(False)
        super().leaveEvent(event)


class FramelessResizeFilter(QObject):
    """Cross-platform 8-edge resize handler for frameless QMainWindow (Windows, macOS, Linux)."""

    RESIZE_MARGIN = 6

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._win = window
        self._enabled = False
        self._resizing = False
        self._resize_edges = Qt.Edge(0)
        self._press_global = QPoint()
        self._press_geo = window.geometry()
        self._cursor_overridden = False

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled and self._cursor_overridden:
            self._win.unsetCursor()
            self._cursor_overridden = False

    def _detect_edges(self, global_pos: QPoint) -> Qt.Edge:
        if not self._enabled or self._win.isMaximized() or self._win.isFullScreen():
            return Qt.Edge(0)
        geo = self._win.frameGeometry()
        if not geo.contains(global_pos):
            return Qt.Edge(0)
        m = self.RESIZE_MARGIN
        edges = Qt.Edge(0)
        if global_pos.x() - geo.left() <= m:
            edges |= Qt.Edge.LeftEdge
        elif geo.right() - global_pos.x() <= m:
            edges |= Qt.Edge.RightEdge
        if global_pos.y() - geo.top() <= m:
            edges |= Qt.Edge.TopEdge
        elif geo.bottom() - global_pos.y() <= m:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for_edges(edges: Qt.Edge) -> Optional[Qt.CursorShape]:
        if edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in (Qt.Edge.RightEdge | Qt.Edge.TopEdge, Qt.Edge.LeftEdge | Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeBDiagCursor
        if edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            return Qt.CursorShape.SizeHorCursor
        if edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeVerCursor
        return None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self._enabled:
            return False
        etype = event.type()
        if etype not in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
        ):
            return False

        if not isinstance(watched, QWidget) or watched.window() is not self._win:
            return False

        if etype == QEvent.Type.MouseButtonRelease:
            if self._resizing:
                self._resizing = False
                self._resize_edges = Qt.Edge(0)
                return True
            return False

        global_pos = QCursor.pos()

        if self._resizing and etype == QEvent.Type.MouseMove:
            delta = global_pos - self._press_global
            g = self._press_geo
            min_w = max(400, self._win.minimumWidth())
            min_h = max(300, self._win.minimumHeight())
            left, top, right, bottom = g.left(), g.top(), g.right(), g.bottom()

            if self._resize_edges & Qt.Edge.LeftEdge:
                left = min(right - min_w + 1, g.left() + delta.x())
            if self._resize_edges & Qt.Edge.RightEdge:
                right = max(left + min_w - 1, g.right() + delta.x())
            if self._resize_edges & Qt.Edge.TopEdge:
                top = min(bottom - min_h + 1, g.top() + delta.y())
            if self._resize_edges & Qt.Edge.BottomEdge:
                bottom = max(top + min_h - 1, g.bottom() + delta.y())

            self._win.setGeometry(left, top, right - left + 1, bottom - top + 1)
            return True

        edges = self._detect_edges(global_pos)
        if etype == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton and edges != Qt.Edge(0):
                wh = self._win.windowHandle()
                if wh is not None and hasattr(wh, "startSystemResize") and wh.startSystemResize(edges):
                    return True
                # Manual fallback if OS/QPA doesn't support startSystemResize
                self._resizing = True
                self._resize_edges = edges
                self._press_global = global_pos
                self._press_geo = self._win.geometry()
                return True

        if etype in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            cursor_shape = self._cursor_for_edges(edges)
            if cursor_shape is not None:
                self._win.setCursor(cursor_shape)
                self._cursor_overridden = True
            elif self._cursor_overridden:
                self._win.unsetCursor()
                self._cursor_overridden = False

        return False


class CustomWindowChrome(QFrame):
    """Cross-platform custom titlebar + integrated menu bar container for QMainWindow."""

    def __init__(self, main_window: QMainWindow, menubar: QMenuBar, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WindowChromeRoot")
        self._win = main_window
        self.menubar = menubar
        self._chrome_style = DEFAULT_CHROME_STYLE
        self._dragging = False
        self._drag_offset = QPoint()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Optional 2px top accent bar (used by cyber_accent style)
        self._accent_strip = QFrame(self)
        self._accent_strip.setFixedHeight(2)
        self._accent_strip.setVisible(False)
        outer.addWidget(self._accent_strip)

        # Title bar row
        self.title_bar = QFrame(self)
        self.title_bar.setObjectName("WindowTitleBar")
        self._tb_layout = QHBoxLayout(self.title_bar)
        self._tb_layout.setContentsMargins(10, 0, 6, 0)
        self._tb_layout.setSpacing(6)
        outer.addWidget(self.title_bar)

        # App Icon & Title Label
        self._icon_lbl = QLabel(self.title_bar)
        self._icon_lbl.setFixedSize(18, 18)
        self._tb_layout.addWidget(self._icon_lbl)

        self._title_lbl = QLabel(main_window.windowTitle(), self.title_bar)
        self._title_lbl.setObjectName("WindowTitleText")
        self._tb_layout.addWidget(self._title_lbl)

        # Window Control Buttons
        self.btn_minimize = _ChromeControlButton("minimize")
        self.btn_maximize = _ChromeControlButton("maximize")
        self.btn_close = _ChromeControlButton("close")

        self.btn_minimize.setToolTip("Minimize")
        self.btn_maximize.setToolTip("Maximize / Restore")
        self.btn_close.setToolTip("Close")

        self.btn_minimize.clicked.connect(self._win.showMinimized)
        self.btn_maximize.clicked.connect(self._toggle_maximize)
        self.btn_close.clicked.connect(self._win.close)

        self._controls_group = _TrafficGroupWidget(
            [self.btn_minimize, self.btn_maximize, self.btn_close],
            self.title_bar,
        )
        cg_layout = QHBoxLayout(self._controls_group)
        cg_layout.setContentsMargins(0, 0, 0, 0)
        cg_layout.setSpacing(4)
        cg_layout.addWidget(self.btn_minimize)
        cg_layout.addWidget(self.btn_maximize)
        cg_layout.addWidget(self.btn_close)
        self._cg_layout = cg_layout

        # Separate row for MenuBar (used by stacked chrome styles & native mode)
        self._menubar_row = QFrame(self)
        self._menubar_row_layout = QHBoxLayout(self._menubar_row)
        self._menubar_row_layout.setContentsMargins(0, 0, 0, 0)
        self._menubar_row_layout.setSpacing(0)
        self._menubar_row_layout.addWidget(self.menubar)
        outer.addWidget(self._menubar_row)

        self.apply_chrome(DEFAULT_CHROME_STYLE)

    def set_window_icon(self, icon: QIcon) -> None:
        if not icon.isNull():
            self._icon_lbl.setPixmap(icon.pixmap(QSize(16, 16)))

    def set_window_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def sync_window_state(self) -> None:
        self.btn_maximize.set_maximized_state(self._win.isMaximized())

    def apply_chrome(self, style_id: str) -> None:
        self._chrome_style = get_chrome_style(style_id)["id"]
        cfg = get_chrome_style(self._chrome_style)
        t = get_theme_tokens()

        is_native = cfg["id"] == "native"
        self.title_bar.setVisible(not is_native)
        self._accent_strip.setVisible(bool(cfg["top_accent_bar"]) and not is_native)
        self._accent_strip.setStyleSheet(f"background-color: {t['accent_primary']}; border: none;")

        if sys.platform == "darwin":
            self.menubar.setNativeMenuBar(is_native)
        else:
            self.menubar.setNativeMenuBar(False)

        if is_native:
            self.menubar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if self.menubar.parent() is not self._menubar_row:
                self._menubar_row_layout.addWidget(self.menubar)
            self._menubar_row.setVisible(sys.platform != "darwin")
            self.setStyleSheet("QFrame#WindowChromeRoot { background: transparent; border: none; }")
            return

        self.setStyleSheet("")
        self.title_bar.setFixedHeight(int(cfg["height"]))

        # Clear _tb_layout without deleting child widgets
        while self._tb_layout.count():
            self._tb_layout.takeAt(0)

        # Reorder buttons inside _controls_group (left traffic: close, min, max; right: min, max, close)
        while self._cg_layout.count():
            self._cg_layout.takeAt(0)

        if cfg["controls_side"] == "left":
            self._cg_layout.setSpacing(6)
            self._cg_layout.addWidget(self.btn_close)
            self._cg_layout.addWidget(self.btn_minimize)
            self._cg_layout.addWidget(self.btn_maximize)
        else:
            spacing = 5 if cfg["button_shape"] in ("capsule", "circle", "pill_hover") else 2
            self._cg_layout.setSpacing(spacing)
            self._cg_layout.addWidget(self.btn_minimize)
            self._cg_layout.addWidget(self.btn_maximize)
            self._cg_layout.addWidget(self.btn_close)

        for btn in (self.btn_minimize, self.btn_maximize, self.btn_close):
            btn.apply_chrome_style(self._chrome_style)

        if cfg["layout"] == "unified":
            # Single-row unified bar: [Icon] [MenuBar] [Stretch] [Title] [Stretch] [Controls]
            self._menubar_row.setVisible(False)
            self._tb_layout.setContentsMargins(10, 0, 8, 0)
            self._tb_layout.addWidget(self._icon_lbl)
            self.menubar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            self._tb_layout.addWidget(self.menubar)
            self.menubar.setStyleSheet("QMenuBar { border-bottom: none; background: transparent; }")
            self._tb_layout.addStretch(1)
            self._tb_layout.addWidget(self._title_lbl)
            self._tb_layout.addStretch(1)
            self._tb_layout.addWidget(self._controls_group)
        else:
            # Stacked 2-row layout: TitleBar on top, MenuBar below
            self.menubar.setStyleSheet("")
            self.menubar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if self.menubar.parent() is not self._menubar_row:
                self._menubar_row_layout.addWidget(self.menubar)
            self._menubar_row.setVisible(True)
            self._tb_layout.setContentsMargins(10, 0, 8, 0)

            if cfg["controls_side"] == "left":
                self._tb_layout.addWidget(self._controls_group)
                self._tb_layout.addStretch(1)
                self._tb_layout.addWidget(self._icon_lbl)
                self._tb_layout.addWidget(self._title_lbl)
                self._tb_layout.addStretch(1)
            elif cfg["title_align"] == "center":
                self._tb_layout.addWidget(self._icon_lbl)
                self._tb_layout.addStretch(1)
                self._tb_layout.addWidget(self._title_lbl)
                self._tb_layout.addStretch(1)
                self._tb_layout.addWidget(self._controls_group)
            else:
                self._tb_layout.addWidget(self._icon_lbl)
                self._tb_layout.addWidget(self._title_lbl)
                self._tb_layout.addStretch(1)
                self._tb_layout.addWidget(self._controls_group)

        self.sync_window_state()
        self.update()

    def _toggle_maximize(self) -> None:
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()
        self.sync_window_state()

    def _is_interactive_child(self, pos: QPoint) -> bool:
        child = self.childAt(pos)
        if child is None:
            return False
        return isinstance(child, (QPushButton, QMenuBar))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and is_custom_chrome(self._chrome_style):
            p = event.position().toPoint()
            if not self._is_interactive_child(p) and self.title_bar.geometry().contains(p):
                # Do not intercept the outer resize border
                if p.y() > FramelessResizeFilter.RESIZE_MARGIN:
                    wh = self._win.windowHandle()
                    if wh is not None and hasattr(wh, "startSystemMove") and wh.startSystemMove():
                        event.accept()
                        return
                    self._dragging = True
                    self._drag_offset = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            if self._win.isMaximized():
                self._win.showNormal()
            self._win.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and is_custom_chrome(self._chrome_style):
            p = event.position().toPoint()
            if not self._is_interactive_child(p) and self.title_bar.geometry().contains(p):
                self._toggle_maximize()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)


class ChromePreviewWidget(QWidget):
    """Live miniature preview of a Custom Window Chrome design rendered with active theme tokens."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._style_id = DEFAULT_CHROME_STYLE
        self._theme_id: Optional[str] = None
        self.setFixedHeight(42)

    def set_preview(self, style_id: str, theme_id: Optional[str] = None) -> None:
        self._style_id = get_chrome_style(style_id)["id"]
        self._theme_id = theme_id
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cfg = get_chrome_style(self._style_id)
        t = get_theme_tokens(self._theme_id)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)

        # Mini window frame
        painter.setPen(QPen(QColor(t["border_default"]), 1.0))
        painter.setBrush(QColor(t["bg_window"]))
        painter.drawRoundedRect(rect, 6.0, 6.0)

        # Header bar
        header_h = 26.0
        header_rect = QRectF(rect.left(), rect.top(), rect.width(), header_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t["bg_panel"]))
        painter.drawRoundedRect(header_rect, 5.0, 5.0)
        painter.drawRect(QRectF(header_rect.left(), header_rect.bottom() - 5.0, header_rect.width(), 5.0))

        # Divider
        painter.setPen(QPen(QColor(t["border_subtle"]), 1.0))
        painter.drawLine(QPointF(rect.left(), header_rect.bottom()), QPointF(rect.right(), header_rect.bottom()))

        # Top accent strip
        if cfg["top_accent_bar"]:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["accent_primary"]))
            painter.drawRect(QRectF(rect.left() + 2.0, rect.top() + 1.0, rect.width() - 4.0, 2.0))

        # Title / Unified menu text preview
        painter.setPen(QColor(t["text_secondary"]))
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)

        if cfg["id"] == "native":
            painter.drawText(header_rect.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "OS Native Titlebar")
        elif cfg["layout"] == "unified":
            painter.drawText(header_rect.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "File  Edit  Machine & Pen")
            painter.drawText(header_rect.adjusted(10, 0, -100, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, "A1 Mini Studio")
        elif cfg["title_align"] == "center":
            painter.drawText(header_rect, Qt.AlignmentFlag.AlignCenter, "A1 Mini Pen Plotter")
        else:
            painter.drawText(header_rect.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "A1 Mini Pen Plotter")

        # Mini window controls
        if cfg["button_shape"] == "traffic":
            cy = header_rect.center().y()
            for idx, hex_c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
                cx = rect.left() + 14.0 + idx * 14.0
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(hex_c))
                painter.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
        else:
            btn_w = 24.0
            btn_h = 16.0
            cy = header_rect.center().y()
            kinds = ["minimize", "maximize", "close"]
            for i, kind in enumerate(kinds):
                bx = rect.right() - (3 - i) * (btn_w + 3.0) - 5.0
                b_rect = QRectF(bx, cy - btn_h * 0.5, btn_w, btn_h)
                is_close = kind == "close"
                if cfg["button_shape"] == "capsule":
                    fill = QColor("#C42B1C") if is_close else QColor(t["bg_surface"])
                    border = QColor("#EF4444") if is_close else QColor(t["border_default"])
                    painter.setPen(QPen(border, 1.0))
                    painter.setBrush(fill)
                    painter.drawRoundedRect(b_rect, 4.5, 4.5)
                    fg = QColor("#FFFFFF") if is_close else QColor(t["text_primary"])
                elif is_close and cfg["close_always_red"]:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor("#C42B1C"))
                    painter.drawRoundedRect(b_rect, 4.5, 4.5)
                    fg = QColor("#FFFFFF")
                else:
                    fg = QColor(t["text_primary"])
                _draw_chrome_glyph(painter, b_rect, kind, fg, stroke_w=1.15)

        painter.end()
