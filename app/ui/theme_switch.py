"""Soft, smooth animated Dark / Light theme mode toggle switch for the top toolbar."""

from __future__ import annotations

import math

from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from app.ui.theme import get_theme_tokens


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(round(c1.red() + (c2.red() - c1.red()) * t)),
        int(round(c1.green() + (c2.green() - c1.green()) * t)),
        int(round(c1.blue() + (c2.blue() - c1.blue()) * t)),
        int(round(c1.alpha() + (c2.alpha() - c1.alpha()) * t)),
    )


class ThemeModeSwitch(QWidget):
    """Animated pill toggle switch that smoothly transitions between Dark (False) and Light (True) modes."""

    toggled_mode = Signal(bool)  # True = Light mode, False = Dark mode

    def __init__(self, is_light: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_light = bool(is_light)
        self._progress: float = 1.0 if self._is_light else 0.0
        self._hovered: bool = False

        self.setFixedSize(56, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName("Dark / Light Theme Mode Switch")

        self._anim = QPropertyAnimation(self, b"thumb_progress", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def sizeHint(self) -> QSize:
        return QSize(56, 26)

    def get_thumb_progress(self) -> float:
        return self._progress

    def set_thumb_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    thumb_progress = Property(float, get_thumb_progress, set_thumb_progress)

    def is_light_mode(self) -> bool:
        return self._is_light

    def set_light_mode(self, is_light: bool, animate: bool = True) -> None:
        """Programmatically syncs the switch state without emitting `toggled_mode`."""
        target_bool = bool(is_light)
        target_val = 1.0 if target_bool else 0.0
        self._is_light = target_bool
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._progress)
            self._anim.setEndValue(target_val)
            self._anim.start()
        else:
            self._progress = target_val
            self.update()

    def _toggle_by_user(self) -> None:
        self.set_light_mode(not self._is_light, animate=True)
        self.toggled_mode.emit(self._is_light)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self._toggle_by_user()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._toggle_by_user()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        t = get_theme_tokens()
        p = self._progress

        w = float(self.width())
        h = float(self.height())
        margin = 3.0
        knob_d = h - 2.0 * margin

        # Interpolate track & border colors smoothly
        accent_c = QColor(t["accent_primary"])
        surface_c = QColor(t["bg_surface"])
        input_c = QColor(t["bg_input"])
        border_c = QColor(t["border_default"])

        dark_track = _lerp_color(input_c, surface_c, 0.55)
        light_track = _lerp_color(surface_c, accent_c, 0.22)
        track_color = _lerp_color(dark_track, light_track, p)

        border_color = accent_c if self._hovered else _lerp_color(border_c, accent_c, p * 0.65)

        track_rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        radius = (h - 2.0) * 0.5

        painter.setPen(QPen(border_color, 1.25))
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, radius, radius)

        # Draw subtle background moon (left) and sun (right) glyphs
        moon_cx = margin + knob_d * 0.5
        sun_cx = w - margin - knob_d * 0.5
        cy = h * 0.5

        muted_c = QColor(t["text_secondary"])
        muted_c.setAlpha(int(140 * p + 60))
        self._draw_moon(painter, QPointF(moon_cx, cy), 4.6, muted_c)

        sun_bg_c = QColor(t["text_secondary"])
        sun_bg_c.setAlpha(int(140 * (1.0 - p) + 60))
        self._draw_sun(painter, QPointF(sun_cx, cy), 4.4, sun_bg_c)

        # Sliding circular thumb
        x_start = margin
        x_end = w - margin - knob_d
        knob_x = x_start + (x_end - x_start) * p
        knob_rect = QRectF(knob_x, margin, knob_d, knob_d)

        dark_knob = QColor(t["bg_surface_hover"])
        light_knob = accent_c
        knob_fill = _lerp_color(dark_knob, light_knob, p)

        painter.setPen(QPen(_lerp_color(border_c, accent_c, 0.55), 1.0))
        painter.setBrush(knob_fill)
        painter.drawEllipse(knob_rect)

        # Active icon inside thumb
        thumb_center = knob_rect.center()
        if p < 0.5:
            icon_c = QColor(t["accent_primary"])
            icon_c.setAlpha(int(255 * (1.0 - p * 2.0)))
            self._draw_moon(painter, thumb_center, 5.2, icon_c)
        else:
            icon_c = QColor(t["accent_contrast"])
            icon_c.setAlpha(int(255 * ((p - 0.5) * 2.0)))
            self._draw_sun(painter, thumb_center, 4.8, icon_c)

        painter.end()

    @staticmethod
    def _draw_moon(painter: QPainter, center: QPointF, radius: float, color: QColor) -> None:
        painter.save()
        outer = QPainterPath()
        outer.addEllipse(center, radius, radius)
        cutout = QPainterPath()
        cutout.addEllipse(QPointF(center.x() + radius * 0.42, center.y() - radius * 0.25), radius * 0.82, radius * 0.82)
        crescent = outer.subtracted(cutout)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(crescent)
        painter.restore()

    @staticmethod
    def _draw_sun(painter: QPainter, center: QPointF, radius: float, color: QColor) -> None:
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(center, radius * 0.48, radius * 0.48)
        ray_pen = QPen(color, 1.35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(ray_pen)
        r_in = radius * 0.72
        r_out = radius * 1.05
        for i in range(8):
            ang = i * math.pi / 4.0
            ca = math.cos(ang)
            sa = math.sin(ang)
            painter.drawLine(
                QPointF(center.x() + ca * r_in, center.y() + sa * r_in),
                QPointF(center.x() + ca * r_out, center.y() + sa * r_out),
            )
        painter.restore()
