"""Context-sensitive Right Inspector Panel for dimensions, X/Y position, scale, rotation, fills, and optimization."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    BoundingBox,
    DocumentTransform,
    FillSettings,
    OptimizationSettings,
    ToolpathStats,
)
from app.machine.profiles import PenProfile
from app.ui.icons import make_icon


class RightInspectorPanel(QFrame):
    """Right-side engineering inspector for object placement, geometry fill, and toolpath optimization."""

    transform_changed = Signal(DocumentTransform)
    center_on_plate_requested = Signal()
    fit_to_safe_area_requested = Signal()
    align_origin_requested = Signal()
    resize_requested = Signal()
    fill_settings_changed = Signal(FillSettings)
    optimization_settings_changed = Signal(OptimizationSettings)
    coordinate_flags_changed = Signal(bool, bool)  # (invert_y, normalize_origin)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("InspectorContainer")
        self.setMinimumWidth(320)
        self.setMaximumWidth(370)

        self._updating_ui = False
        self._native_width_mm: float = 100.0
        self._native_height_mm: float = 100.0
        self._current_width_mm: float = 100.0
        self._current_height_mm: float = 100.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(8)

        # 1. Dimensions & Placement Card
        vbox.addWidget(self._build_dimensions_card(content))

        # 2. Scale & Rotation Card
        vbox.addWidget(self._build_transform_card(content))

        # 3. Stroke & Filled Shapes Card
        vbox.addWidget(self._build_fill_card(content))

        # 4. Path Optimization Card
        vbox.addWidget(self._build_optimization_card(content))

        # 5. Active Pen Quick Summary Card
        vbox.addWidget(self._build_pen_summary_card(content))

        vbox.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_dimensions_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        lbl = QLabel("OBJECT DIMENSIONS & POSITION", card)
        lbl.setObjectName("SectionHeader")
        layout.addWidget(lbl)

        self.lbl_bounds_readout = QLabel("Bounds: 0.00 × 0.00 mm", card)
        self.lbl_bounds_readout.setObjectName("MonoValueLabel")
        layout.addWidget(self.lbl_bounds_readout)

        form = QFormLayout()
        form.setSpacing(5)

        self.spn_pos_x = self._make_dspin(-500.0, 500.0, 20.0, " mm")
        self.spn_pos_y = self._make_dspin(-500.0, 500.0, 20.0, " mm")
        self.spn_width = self._make_dspin(0.1, 1000.0, 20.0, " mm")
        self.spn_height = self._make_dspin(0.1, 1000.0, 20.0, " mm")

        form.addRow("Position X:", self.spn_pos_x)
        form.addRow("Position Y:", self.spn_pos_y)
        form.addRow("Width (W):", self.spn_width)
        form.addRow("Height (H):", self.spn_height)
        layout.addLayout(form)

        grid_align = QGridLayout()
        grid_align.setSpacing(5)

        btn_center = QPushButton("Center Plate", card)
        btn_center.setToolTip("Center drawing on the 180×180 mm build plate")
        btn_center.clicked.connect(self.center_on_plate_requested.emit)
        grid_align.addWidget(btn_center, 0, 0)

        btn_origin = QPushButton("Safe Origin", card)
        btn_origin.setToolTip("Align drawing bottom-left to the safe area origin (15, 15 mm)")
        btn_origin.clicked.connect(self.align_origin_requested.emit)
        grid_align.addWidget(btn_origin, 0, 1)

        btn_fit_safe = QPushButton("Fit Safe", card)
        btn_fit_safe.setToolTip("Scale and center drawing to fit inside the safe margin area (150×150 mm)")
        btn_fit_safe.clicked.connect(self.fit_to_safe_area_requested.emit)
        grid_align.addWidget(btn_fit_safe, 1, 0)

        self.btn_resize = QPushButton("Resize...", card)
        self.btn_resize.setIcon(make_icon("resize", "#38BDF8", 14))
        self.btn_resize.setToolTip(
            "Open comprehensive drawing resize dialog (dimensions, percentage, presets) [Ctrl+R]"
        )
        self.btn_resize.setStyleSheet(
            "QPushButton { font-weight: 600; color: #38BDF8; border: 1px solid #0369A1; } "
            "QPushButton:hover { background-color: #0C4A6E; color: #7DD3FC; border-color: #38BDF8; }"
        )
        self.btn_resize.clicked.connect(self.resize_requested.emit)
        grid_align.addWidget(self.btn_resize, 1, 1)

        layout.addLayout(grid_align)

        self.spn_pos_x.valueChanged.connect(self._on_transform_spin_changed)
        self.spn_pos_y.valueChanged.connect(self._on_transform_spin_changed)
        self.spn_width.valueChanged.connect(self._on_width_edited)
        self.spn_height.valueChanged.connect(self._on_height_edited)

        return card

    def _build_transform_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        lbl = QLabel("SCALE, ROTATION & COORDINATES", card)
        lbl.setObjectName("SectionHeader")
        layout.addWidget(lbl)

        form = QFormLayout()
        form.setSpacing(5)

        self.spn_scale_x = self._make_dspin(0.01, 50.0, 1.0, "×")
        self.spn_scale_y = self._make_dspin(0.01, 50.0, 1.0, "×")
        self.chk_lock_aspect = QCheckBox("Lock Aspect Ratio", card)
        self.chk_lock_aspect.setChecked(True)
        self.spn_rotation = self._make_dspin(-360.0, 360.0, 0.0, "°")

        form.addRow("Scale X:", self.spn_scale_x)
        form.addRow("Scale Y:", self.spn_scale_y)
        form.addRow("", self.chk_lock_aspect)
        form.addRow("Rotation:", self.spn_rotation)
        layout.addLayout(form)

        row_rot = QHBoxLayout()
        btn_rot_m90 = QPushButton("-90°", card)
        btn_rot_m90.clicked.connect(lambda: self._step_rotation(-90.0))
        row_rot.addWidget(btn_rot_m90)

        btn_rot_45 = QPushButton("+45°", card)
        btn_rot_45.clicked.connect(lambda: self._step_rotation(45.0))
        row_rot.addWidget(btn_rot_45)

        btn_rot_90 = QPushButton("+90°", card)
        btn_rot_90.clicked.connect(lambda: self._step_rotation(90.0))
        row_rot.addWidget(btn_rot_90)

        btn_reset = QPushButton("Reset 1:1", card)
        btn_reset.clicked.connect(self._reset_scale_rotation)
        row_rot.addWidget(btn_reset)
        layout.addLayout(row_rot)

        row_mirror = QHBoxLayout()
        self.chk_mirror_x = QCheckBox("Mirror X", card)
        self.chk_mirror_y = QCheckBox("Mirror Y", card)
        row_mirror.addWidget(self.chk_mirror_x)
        row_mirror.addWidget(self.chk_mirror_y)
        layout.addLayout(row_mirror)

        self.chk_invert_y = QCheckBox("Invert SVG Y-Axis (Y-down → Y-up)", card)
        self.chk_invert_y.setChecked(True)
        layout.addWidget(self.chk_invert_y)

        self.chk_normalize_origin = QCheckBox("Normalize Bounding-Box to Position X/Y", card)
        self.chk_normalize_origin.setChecked(True)
        self.chk_normalize_origin.setToolTip(
            "When unchecked, raw SVG coordinates (including negative coordinates) map directly to machine coordinates."
        )
        layout.addWidget(self.chk_normalize_origin)

        self.spn_scale_x.valueChanged.connect(self._on_scale_x_changed)
        self.spn_scale_y.valueChanged.connect(self._on_scale_y_changed)
        self.chk_lock_aspect.toggled.connect(self._on_transform_spin_changed)
        self.spn_rotation.valueChanged.connect(self._on_transform_spin_changed)
        self.chk_mirror_x.toggled.connect(self._on_transform_spin_changed)
        self.chk_mirror_y.toggled.connect(self._on_transform_spin_changed)
        self.chk_invert_y.toggled.connect(self._emit_coord_flags)
        self.chk_normalize_origin.toggled.connect(self._emit_coord_flags)

        return card

    def _build_fill_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("SectionCard")
        form = QFormLayout(card)
        form.setContentsMargins(10, 8, 10, 8)
        form.setSpacing(5)

        lbl = QLabel("STROKE & FILLED SHAPES", card)
        lbl.setObjectName("SectionHeader")
        form.addRow(lbl)

        self.cmb_fill_mode = QComboBox(card)
        self.cmb_fill_mode.addItem("Draw Outlines Only", "outline")
        self.cmb_fill_mode.addItem("Ignore Fills", "ignore")
        self.cmb_fill_mode.addItem("Hatching Pattern Fill", "hatch")
        self.cmb_fill_mode.addItem("Concentric Contour Fill", "contour")

        self.spn_hatch_spacing = self._make_dspin(0.15, 20.0, 1.0, " mm")
        self.spn_hatch_angle = self._make_dspin(-180.0, 180.0, 45.0, "°")
        self.chk_cross_hatch = QCheckBox("Cross-Hatch (Dual Angle)", card)
        self.spn_contour_spacing = self._make_dspin(0.15, 20.0, 0.8, " mm")
        self.chk_include_outline = QCheckBox("Draw Perimeter Outline", card)
        self.chk_include_outline.setChecked(True)

        form.addRow("Fill Mode:", self.cmb_fill_mode)
        form.addRow("Hatch Spacing:", self.spn_hatch_spacing)
        form.addRow("Hatch Angle:", self.spn_hatch_angle)
        form.addRow("", self.chk_cross_hatch)
        form.addRow("Contour Step:", self.spn_contour_spacing)
        form.addRow("", self.chk_include_outline)

        self.cmb_fill_mode.currentIndexChanged.connect(self._emit_fill_changed)
        self.spn_hatch_spacing.valueChanged.connect(self._emit_fill_changed)
        self.spn_hatch_angle.valueChanged.connect(self._emit_fill_changed)
        self.chk_cross_hatch.toggled.connect(self._emit_fill_changed)
        self.spn_contour_spacing.valueChanged.connect(self._emit_fill_changed)
        self.chk_include_outline.toggled.connect(self._emit_fill_changed)

        return card

    def _build_optimization_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("SectionCard")
        form = QFormLayout(card)
        form.setContentsMargins(10, 8, 10, 8)
        form.setSpacing(5)

        lbl = QLabel("TOOLPATH & OPTIMIZATION", card)
        lbl.setObjectName("SectionHeader")
        form.addRow(lbl)

        self.cmb_opt_strategy = QComboBox(card)
        self.cmb_opt_strategy.addItem("Nearest-Neighbor Ordering", "nearest_neighbor")
        self.cmb_opt_strategy.addItem("Minimum Travel (NN + 2-Opt)", "min_travel_2opt")
        self.cmb_opt_strategy.addItem("Direction Optimization Only", "direction_only")
        self.cmb_opt_strategy.addItem("Original SVG Order", "original")

        self.chk_allow_reversal = QCheckBox("Allow Path Direction Reversal", card)
        self.chk_allow_reversal.setChecked(True)
        self.spn_curve_precision = self._make_dspin(0.01, 2.0, 0.08, " mm")
        self.spn_simplify_tol = self._make_dspin(0.0, 1.0, 0.02, " mm")
        self.spn_merge_gap = self._make_dspin(0.0, 2.0, 0.08, " mm")

        self.lbl_opt_gain = QLabel("Travel Reduction: 0.0%", card)
        self.lbl_opt_gain.setObjectName("AppBadgeLabel")

        form.addRow("Strategy:", self.cmb_opt_strategy)
        form.addRow("", self.chk_allow_reversal)
        form.addRow("Curve Precision:", self.spn_curve_precision)
        form.addRow("Simplify Tol:", self.spn_simplify_tol)
        form.addRow("Join Threshold:", self.spn_merge_gap)
        form.addRow("Optimization:", self.lbl_opt_gain)

        self.cmb_opt_strategy.currentIndexChanged.connect(self._emit_opt_changed)
        self.chk_allow_reversal.toggled.connect(self._emit_opt_changed)
        self.spn_curve_precision.valueChanged.connect(self._emit_opt_changed)
        self.spn_simplify_tol.valueChanged.connect(self._emit_opt_changed)
        self.spn_merge_gap.valueChanged.connect(self._emit_opt_changed)

        return card

    def _build_pen_summary_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("SectionCard")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(10, 8, 10, 8)
        vbox.setSpacing(4)

        lbl = QLabel("ACTIVE PEN SUMMARY", card)
        lbl.setObjectName("SectionHeader")
        vbox.addWidget(lbl)

        self.lbl_pen_summary = QLabel("Pen: Default Fineliner 0.4mm", card)
        self.lbl_pen_summary.setObjectName("MonoValueLabel")
        self.lbl_pen_summary.setWordWrap(True)
        vbox.addWidget(self.lbl_pen_summary)

        return card

    def _make_dspin(self, min_v: float, max_v: float, val: float, suffix: str) -> QDoubleSpinBox:
        spn = QDoubleSpinBox(self)
        spn.setRange(min_v, max_v)
        spn.setDecimals(2)
        spn.setSingleStep(0.5)
        spn.setSuffix(suffix)
        spn.setValue(val)
        return spn

    # ==========================================================================
    # Sync & Event Handlers
    # ==========================================================================

    def sync_from_state(
        self,
        doc_transform: DocumentTransform,
        drawing_bounds: BoundingBox,
        stats: ToolpathStats,
        pen: PenProfile,
        native_bounds: Optional[BoundingBox] = None,
    ) -> None:
        self._updating_ui = True
        if native_bounds and native_bounds.width > 1e-4 and native_bounds.height > 1e-4:
            self._native_width_mm = native_bounds.width
            self._native_height_mm = native_bounds.height

        self.spn_pos_x.setValue(doc_transform.pos_x_mm)
        self.spn_pos_y.setValue(doc_transform.pos_y_mm)
        self.spn_scale_x.setValue(doc_transform.scale_x)
        self.spn_scale_y.setValue(doc_transform.scale_y)
        self.chk_lock_aspect.setChecked(doc_transform.lock_aspect)
        self.spn_rotation.setValue(doc_transform.rotation_deg)
        self.chk_mirror_x.setChecked(doc_transform.mirror_x)
        self.chk_mirror_y.setChecked(doc_transform.mirror_y)

        if drawing_bounds.is_valid and drawing_bounds.width > 0:
            self._current_width_mm = drawing_bounds.width
            self._current_height_mm = drawing_bounds.height
            self.spn_width.setValue(drawing_bounds.width)
            self.spn_height.setValue(drawing_bounds.height)
            self.lbl_bounds_readout.setText(
                f"X[{drawing_bounds.min_x:.1f}..{drawing_bounds.max_x:.1f}]  "
                f"Y[{drawing_bounds.min_y:.1f}..{drawing_bounds.max_y:.1f}] mm"
            )
        else:
            self._current_width_mm = self._native_width_mm
            self._current_height_mm = self._native_height_mm
            self.lbl_bounds_readout.setText("Bounds: 0.00 × 0.00 mm")

        self.lbl_opt_gain.setText(
            f"Saved {stats.optimization_improvement_pct:.1f}% travel "
            f"({stats.travel_distance_mm:.0f} vs {stats.unoptimized_travel_distance_mm:.0f} mm)"
        )

        cal_str = "CALIBRATED" if pen.is_calibrated else "UNCALIBRATED (Check Z!)"
        self.lbl_pen_summary.setText(
            f"{pen.name}\n"
            f"Draw Z: {pen.drawing_z_mm:.2f} mm  |  Pen-Up Z: {pen.pen_up_z_mm:.2f} mm\n"
            f"Speed: {pen.draw_speed_mm_s:.0f} mm/s draw, {pen.travel_speed_mm_s:.0f} mm/s travel\n"
            f"Status: {cal_str}"
        )
        self._updating_ui = False

    def update_position_preview(self, pos_x: float, pos_y: float) -> None:
        """Updates position spinboxes without emitting transform_changed signal during drag."""
        self._updating_ui = True
        try:
            self.spn_pos_x.setValue(pos_x)
            self.spn_pos_y.setValue(pos_y)
        finally:
            self._updating_ui = False

    def current_transform(self) -> DocumentTransform:
        return DocumentTransform(
            pos_x_mm=self.spn_pos_x.value(),
            pos_y_mm=self.spn_pos_y.value(),
            scale_x=self.spn_scale_x.value(),
            scale_y=self.spn_scale_y.value(),
            lock_aspect=self.chk_lock_aspect.isChecked(),
            rotation_deg=self.spn_rotation.value(),
            mirror_x=self.chk_mirror_x.isChecked(),
            mirror_y=self.chk_mirror_y.isChecked(),
        )

    def _on_width_edited(self, new_w: float) -> None:
        if self._updating_ui or self._current_width_mm <= 1e-4:
            return
        ratio = max(0.001, new_w / self._current_width_mm)
        new_sx = max(0.01, round(self.spn_scale_x.value() * ratio, 4))
        self._updating_ui = True
        self.spn_scale_x.setValue(new_sx)
        if self.chk_lock_aspect.isChecked():
            new_sy = max(0.01, round(self.spn_scale_y.value() * ratio, 4))
            self.spn_scale_y.setValue(new_sy)
            self.spn_height.setValue(round(self._current_height_mm * ratio, 2))
        self._updating_ui = False
        self.transform_changed.emit(self.current_transform())

    def _on_height_edited(self, new_h: float) -> None:
        if self._updating_ui or self._current_height_mm <= 1e-4:
            return
        ratio = max(0.001, new_h / self._current_height_mm)
        new_sy = max(0.01, round(self.spn_scale_y.value() * ratio, 4))
        self._updating_ui = True
        self.spn_scale_y.setValue(new_sy)
        if self.chk_lock_aspect.isChecked():
            new_sx = max(0.01, round(self.spn_scale_x.value() * ratio, 4))
            self.spn_scale_x.setValue(new_sx)
            self.spn_width.setValue(round(self._current_width_mm * ratio, 2))
        self._updating_ui = False
        self.transform_changed.emit(self.current_transform())

    def _on_scale_x_changed(self, val: float) -> None:
        if self._updating_ui:
            return
        if self.chk_lock_aspect.isChecked():
            self._updating_ui = True
            self.spn_scale_y.setValue(val)
            self._updating_ui = False
        self.transform_changed.emit(self.current_transform())

    def _on_scale_y_changed(self, val: float) -> None:
        if self._updating_ui:
            return
        if self.chk_lock_aspect.isChecked():
            self._updating_ui = True
            self.spn_scale_x.setValue(val)
            self._updating_ui = False
        self.transform_changed.emit(self.current_transform())

    def _on_transform_spin_changed(self) -> None:
        if self._updating_ui:
            return
        self.transform_changed.emit(self.current_transform())

    def _step_rotation(self, delta: float) -> None:
        val = (self.spn_rotation.value() + delta) % 360.0
        if val > 180.0:
            val -= 360.0
        self.spn_rotation.setValue(val)

    def _reset_scale_rotation(self) -> None:
        self._updating_ui = True
        self.spn_scale_x.setValue(1.0)
        self.spn_scale_y.setValue(1.0)
        self.spn_rotation.setValue(0.0)
        self.chk_mirror_x.setChecked(False)
        self.chk_mirror_y.setChecked(False)
        self._updating_ui = False
        self.transform_changed.emit(self.current_transform())

    def _emit_fill_changed(self) -> None:
        if self._updating_ui:
            return
        fs = FillSettings(
            mode=str(self.cmb_fill_mode.currentData() or "outline"),
            hatch_spacing_mm=self.spn_hatch_spacing.value(),
            hatch_angle_deg=self.spn_hatch_angle.value(),
            cross_hatch=self.chk_cross_hatch.isChecked(),
            contour_spacing_mm=self.spn_contour_spacing.value(),
            include_outline=self.chk_include_outline.isChecked(),
        )
        self.fill_settings_changed.emit(fs)

    def _emit_opt_changed(self) -> None:
        if self._updating_ui:
            return
        os = OptimizationSettings(
            strategy=str(self.cmb_opt_strategy.currentData() or "nearest_neighbor"),
            allow_direction_reversal=self.chk_allow_reversal.isChecked(),
            curve_precision_mm=self.spn_curve_precision.value(),
            simplify_tolerance_mm=self.spn_simplify_tol.value(),
            merge_threshold_mm=self.spn_merge_gap.value(),
        )
        self.optimization_settings_changed.emit(os)

    def _emit_coord_flags(self) -> None:
        if self._updating_ui:
            return
        self.coordinate_flags_changed.emit(
            self.chk_invert_y.isChecked(),
            self.chk_normalize_origin.isChecked(),
        )
