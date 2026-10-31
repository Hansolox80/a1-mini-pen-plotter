"""Professional Drawing Resize, Scaling, and Framing Dialog for A1 Mini Pen Plotter."""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.models import BoundingBox, DocumentTransform
from app.core.platform_utils import get_mono_font_family, get_system_font_family
from app.machine.a1_mini import MachineProfile
from app.ui.icons import make_icon


# Standard plotter and paper presets (width_mm, height_mm, label)
STANDARD_PRESETS: list[tuple[float, float, str]] = [
    (150.0, 150.0, "Bambu Lab Safe Area (150 × 150 mm)"),
    (76.0, 76.0, "Post-it / Sticky Note (76 × 76 mm)"),
    (105.0, 148.0, "A6 Postcard / Card (105 × 148 mm)"),
    (105.0, 150.0, "A5 Sheet Fitted (105 × 150 mm)"),
    (85.6, 54.0, "Business / ID Card (85.6 × 54 mm)"),
    (127.0, 76.2, 'Index Card 3×5" (127 × 76.2 mm)'),
    (90.0, 90.0, "Round Coaster Target (90 × 90 mm)"),
    (50.0, 50.0, "Square 50 mm (50 × 50 mm)"),
    (80.0, 80.0, "Square 80 mm (80 × 80 mm)"),
    (100.0, 100.0, "Square 100 mm (100 × 100 mm)"),
    (120.0, 120.0, "Square 120 mm (120 × 120 mm)"),
    (180.0, 180.0, "Maximum Bed Surface (180 × 180 mm)"),
]


class ResizeDrawingDialog(QDialog):
    """Complete CAD-style dialog for exact millimeter resizing, percentage scaling,

    preset framing, and anchor-point positioning.
    """

    def __init__(
        self,
        current_bounds: BoundingBox,
        native_bounds: BoundingBox,
        current_transform: DocumentTransform,
        machine: MachineProfile,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resize & Frame Drawing")
        self.setMinimumWidth(520)
        self.setModal(True)

        self.current_bounds = current_bounds
        self.native_bounds = native_bounds
        self.initial_transform = DocumentTransform.from_dict(current_transform.to_dict())
        self.machine = machine

        self._updating = False
        self._target_w: float = max(0.1, current_bounds.width if current_bounds.is_valid else 50.0)
        self._target_h: float = max(0.1, current_bounds.height if current_bounds.is_valid else 50.0)
        self._native_w: float = max(0.1, native_bounds.width if native_bounds.is_valid else self._target_w)
        self._native_h: float = max(0.1, native_bounds.height if native_bounds.is_valid else self._target_h)
        self._aspect_ratio: float = self._target_w / max(0.001, self._target_h)

        self._init_ui()
        self._sync_to_dimensions(self._target_w, self._target_h)
        self._recalculate_preview()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header Card with Current Metrics
        header_card = QFrame(self)
        header_card.setObjectName("SectionCard")
        hc_layout = QHBoxLayout(header_card)
        hc_layout.setContentsMargins(12, 10, 12, 10)
        hc_layout.setSpacing(12)

        lbl_icon = QLabel(header_card)
        lbl_icon.setPixmap(make_icon("resize", "#38BDF8", 28).pixmap(28, 28))
        hc_layout.addWidget(lbl_icon)

        v_head = QVBoxLayout()
        v_head.setSpacing(2)
        lbl_title = QLabel("RESIZE & SCALE DRAWING", header_card)
        lbl_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #F1F5F9; letter-spacing: 0.5px;")
        v_head.addWidget(lbl_title)

        cur_text = (
            f"Current Size: {self.current_bounds.width:.2f} × {self.current_bounds.height:.2f} mm   "
            f"(Native: {self._native_w:.1f} × {self._native_h:.1f} mm)   "
            f"Aspect: {self._aspect_ratio:.2f}:1"
        )
        self.lbl_current_metrics = QLabel(cur_text, header_card)
        self.lbl_current_metrics.setObjectName("MutedLabel")
        v_head.addWidget(self.lbl_current_metrics)
        hc_layout.addLayout(v_head)
        hc_layout.addStretch(1)
        main_layout.addWidget(header_card)

        # 2. Main Mode Tabs (Exact mm, Percentage, Presets)
        self.tabs = QTabWidget(self)

        # --- TAB 1: Exact Millimeters ---
        tab_dim = QWidget()
        td_layout = QVBoxLayout(tab_dim)
        td_layout.setContentsMargins(12, 12, 12, 12)
        td_layout.setSpacing(10)

        form_dim = QFormLayout()
        form_dim.setSpacing(8)

        self.spn_width = QDoubleSpinBox(tab_dim)
        self.spn_width.setRange(0.5, 300.0)
        self.spn_width.setDecimals(2)
        self.spn_width.setSuffix(" mm")
        self.spn_width.setValue(self._target_w)
        self.spn_width.valueChanged.connect(self._on_width_changed)
        form_dim.addRow("Target Width (W):", self.spn_width)

        self.spn_height = QDoubleSpinBox(tab_dim)
        self.spn_height.setRange(0.5, 300.0)
        self.spn_height.setDecimals(2)
        self.spn_height.setSuffix(" mm")
        self.spn_height.setValue(self._target_h)
        self.spn_height.valueChanged.connect(self._on_height_changed)
        form_dim.addRow("Target Height (H):", self.spn_height)

        self.chk_lock_aspect = QCheckBox("Lock Aspect Ratio (Proportional Scaling)", tab_dim)
        self.chk_lock_aspect.setChecked(True)
        form_dim.addRow("", self.chk_lock_aspect)
        td_layout.addLayout(form_dim)

        # Quick size chips inside dimensions tab
        row_chips = QHBoxLayout()
        row_chips.setSpacing(6)
        btn_chip_150 = QPushButton("150 mm (Safe)", tab_dim)
        btn_chip_150.clicked.connect(lambda: self._apply_quick_dimension(150.0))
        row_chips.addWidget(btn_chip_150)

        btn_chip_100 = QPushButton("100 mm", tab_dim)
        btn_chip_100.clicked.connect(lambda: self._apply_quick_dimension(100.0))
        row_chips.addWidget(btn_chip_100)

        btn_chip_76 = QPushButton("76 mm (Post-it)", tab_dim)
        btn_chip_76.clicked.connect(lambda: self._apply_quick_dimension(76.0))
        row_chips.addWidget(btn_chip_76)

        btn_chip_50 = QPushButton("50 mm", tab_dim)
        btn_chip_50.clicked.connect(lambda: self._apply_quick_dimension(50.0))
        row_chips.addWidget(btn_chip_50)

        btn_chip_reset = QPushButton("Reset 1:1", tab_dim)
        btn_chip_reset.clicked.connect(self._reset_to_native)
        row_chips.addWidget(btn_chip_reset)
        td_layout.addLayout(row_chips)

        self.tabs.addTab(tab_dim, "By Dimensions (mm)")

        # --- TAB 2: Percentage Scaling (%) ---
        tab_pct = QWidget()
        tp_layout = QVBoxLayout(tab_pct)
        tp_layout.setContentsMargins(12, 12, 12, 12)
        tp_layout.setSpacing(10)

        form_pct = QFormLayout()
        form_pct.setSpacing(8)

        self.spn_pct_uniform = QDoubleSpinBox(tab_pct)
        self.spn_pct_uniform.setRange(1.0, 1000.0)
        self.spn_pct_uniform.setDecimals(1)
        self.spn_pct_uniform.setSuffix(" %")
        self.spn_pct_uniform.setValue(100.0)
        self.spn_pct_uniform.valueChanged.connect(self._on_pct_uniform_changed)
        form_pct.addRow("Uniform Scale:", self.spn_pct_uniform)

        self.chk_non_uniform = QCheckBox("Independent X / Y Scaling (Stretch)", tab_pct)
        self.chk_non_uniform.setChecked(False)
        self.chk_non_uniform.toggled.connect(self._on_non_uniform_toggled)
        form_pct.addRow("", self.chk_non_uniform)

        self.spn_pct_x = QDoubleSpinBox(tab_pct)
        self.spn_pct_x.setRange(1.0, 1000.0)
        self.spn_pct_x.setDecimals(1)
        self.spn_pct_x.setSuffix(" %")
        self.spn_pct_x.setValue(100.0)
        self.spn_pct_x.setEnabled(False)
        self.spn_pct_x.valueChanged.connect(self._on_pct_xy_changed)
        form_pct.addRow("Scale X:", self.spn_pct_x)

        self.spn_pct_y = QDoubleSpinBox(tab_pct)
        self.spn_pct_y.setRange(1.0, 1000.0)
        self.spn_pct_y.setDecimals(1)
        self.spn_pct_y.setSuffix(" %")
        self.spn_pct_y.setValue(100.0)
        self.spn_pct_y.setEnabled(False)
        self.spn_pct_y.valueChanged.connect(self._on_pct_xy_changed)
        form_pct.addRow("Scale Y:", self.spn_pct_y)
        tp_layout.addLayout(form_pct)

        # Quick percentage buttons
        row_pct_buttons = QHBoxLayout()
        row_pct_buttons.setSpacing(4)
        for pct_val in [25.0, 50.0, 75.0, 100.0, 150.0, 200.0]:
            btn_p = QPushButton(f"{pct_val:.0f}%", tab_pct)
            btn_p.clicked.connect(lambda checked=False, val=pct_val: self.spn_pct_uniform.setValue(val))
            row_pct_buttons.addWidget(btn_p)
        tp_layout.addLayout(row_pct_buttons)

        self.tabs.addTab(tab_pct, "By Percentage (%)")

        # --- TAB 3: Standard Media Presets ---
        tab_presets = QWidget()
        tpr_layout = QVBoxLayout(tab_presets)
        tpr_layout.setContentsMargins(12, 12, 12, 12)
        tpr_layout.setSpacing(10)

        form_pre = QFormLayout()
        form_pre.setSpacing(8)

        self.cmb_presets = QComboBox(tab_presets)
        for w, h, lbl in STANDARD_PRESETS:
            self.cmb_presets.addItem(lbl, (w, h))
        self.cmb_presets.currentIndexChanged.connect(self._on_preset_selected)
        form_pre.addRow("Target Preset Media:", self.cmb_presets)

        self.rad_fit_contain = QRadioButton("Proportional Fit (Contain - best for art, no distortion)", tab_presets)
        self.rad_fit_contain.setChecked(True)
        self.rad_fit_contain.toggled.connect(self._on_preset_selected)
        form_pre.addRow("Fit Strategy:", self.rad_fit_contain)

        self.rad_fit_fill = QRadioButton("Exact Stretch (Fill width and height)", tab_presets)
        self.rad_fit_fill.toggled.connect(self._on_preset_selected)
        form_pre.addRow("", self.rad_fit_fill)

        tpr_layout.addLayout(form_pre)
        tpr_layout.addStretch(1)

        btn_apply_preset = QPushButton("Apply Selected Preset Dimensions", tab_presets)
        btn_apply_preset.clicked.connect(self._on_preset_selected)
        tpr_layout.addWidget(btn_apply_preset)

        self.tabs.addTab(tab_presets, "Media && Paper Presets")
        main_layout.addWidget(self.tabs)

        # 3. Anchor Point Selection & Alignment Options
        opt_card = QFrame(self)
        opt_card.setObjectName("SectionCard")
        oc_layout = QHBoxLayout(opt_card)
        oc_layout.setContentsMargins(12, 10, 12, 10)
        oc_layout.setSpacing(16)

        # Anchor Origin Group
        v_anchor = QVBoxLayout()
        v_anchor.setSpacing(4)
        lbl_anchor = QLabel("SCALE ANCHOR ORIGIN", opt_card)
        lbl_anchor.setObjectName("SectionHeader")
        v_anchor.addWidget(lbl_anchor)

        grid_anchor = QGridLayout()
        grid_anchor.setSpacing(4)
        self.anchor_group = QButtonGroup(self)

        anchors = [
            ("TL", 0, 0, "Top-Left"),
            ("TC", 0, 1, "Top-Center"),
            ("TR", 0, 2, "Top-Right"),
            ("ML", 1, 0, "Middle-Left"),
            ("C", 1, 1, "Center"),
            ("MR", 1, 2, "Middle-Right"),
            ("BL", 2, 0, "Bottom-Left"),
            ("BC", 2, 1, "Bottom-Center"),
            ("BR", 2, 2, "Bottom-Right"),
        ]
        for name, r, c, tip in anchors:
            btn_a = QPushButton(name, opt_card)
            btn_a.setCheckable(True)
            btn_a.setFixedSize(38, 26)
            btn_a.setToolTip(f"Scale from {tip}")
            self.anchor_group.addButton(btn_a)
            grid_anchor.addWidget(btn_a, r, c)
            if name == "C":
                btn_a.setChecked(True)

        self.anchor_group.buttonClicked.connect(lambda _: self._recalculate_preview())
        v_anchor.addLayout(grid_anchor)
        oc_layout.addLayout(v_anchor)

        # Separator line
        sep = QFrame(opt_card)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #282E37;")
        oc_layout.addWidget(sep)

        # Positioning Checkboxes
        v_pos = QVBoxLayout()
        v_pos.setSpacing(6)
        lbl_pos = QLabel("PLACEMENT & BOUNDS", opt_card)
        lbl_pos.setObjectName("SectionHeader")
        v_pos.addWidget(lbl_pos)

        self.chk_center_on_bed = QCheckBox("Center drawing on 180×180 mm plate after resize", opt_card)
        self.chk_center_on_bed.setChecked(True)
        self.chk_center_on_bed.toggled.connect(self._recalculate_preview)
        v_pos.addWidget(self.chk_center_on_bed)

        self.chk_clamp_safe = QCheckBox("Soft-clamp position inside 150×150 mm Safe Area", opt_card)
        self.chk_clamp_safe.setChecked(True)
        self.chk_clamp_safe.toggled.connect(self._recalculate_preview)
        v_pos.addWidget(self.chk_clamp_safe)

        v_pos.addStretch(1)
        oc_layout.addLayout(v_pos)
        main_layout.addWidget(opt_card)

        # 4. Live Calculation & Safety Validation Badge Card
        self.preview_card = QFrame(self)
        self.preview_card.setObjectName("SectionCard")
        pv_layout = QVBoxLayout(self.preview_card)
        pv_layout.setContentsMargins(12, 10, 12, 10)
        pv_layout.setSpacing(4)

        row_stat = QHBoxLayout()
        self.lbl_new_size = QLabel("New Size: 0.00 × 0.00 mm", self.preview_card)
        self.lbl_new_size.setStyleSheet("font-weight: 700; color: #F8FAFC;")
        row_stat.addWidget(self.lbl_new_size)

        self.lbl_new_pos = QLabel("Position: X: 0.00 mm, Y: 0.00 mm", self.preview_card)
        self.lbl_new_pos.setObjectName("MonoValueLabel")
        row_stat.addWidget(self.lbl_new_pos)
        pv_layout.addLayout(row_stat)

        row_badge = QHBoxLayout()
        self.lbl_scale_info = QLabel("Scale: 1.000×   Bed Occupancy: 0.0%", self.preview_card)
        self.lbl_scale_info.setObjectName("MutedLabel")
        row_badge.addWidget(self.lbl_scale_info)

        row_badge.addStretch(1)

        self.lbl_safety_badge = QLabel("✅ FITS INSIDE SAFE AREA", self.preview_card)
        self.lbl_safety_badge.setStyleSheet(
            "background: #14532D; color: #86EFAC; font-weight: 700; font-size: 11px; padding: 2px 8px; border-radius: 4px;"
        )
        row_badge.addWidget(self.lbl_safety_badge)
        pv_layout.addLayout(row_badge)

        main_layout.addWidget(self.preview_card)

        # 5. Dialog Buttons
        btn_box = QDialogButtonBox(self)
        self.btn_apply = QPushButton("Apply Resize", self)
        self.btn_apply.setIcon(make_icon("resize", "#0F172A", 16))
        self.btn_apply.setStyleSheet("background: #22C55E; color: #0F172A; font-weight: 700; padding: 6px 18px;")
        btn_box.addButton(self.btn_apply, QDialogButtonBox.ButtonRole.AcceptRole)

        btn_cancel = QPushButton("Cancel", self)
        btn_box.addButton(btn_cancel, QDialogButtonBox.ButtonRole.RejectRole)

        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    # ==========================================================================
    # Synchronization & Event Handlers
    # ==========================================================================

    def _sync_to_dimensions(self, w: float, h: float) -> None:
        self._target_w = max(0.1, round(w, 2))
        self._target_h = max(0.1, round(h, 2))

        self._updating = True
        try:
            self.spn_width.setValue(self._target_w)
            self.spn_height.setValue(self._target_h)

            pct_x = (self._target_w / self._native_w) * 100.0
            pct_y = (self._target_h / self._native_h) * 100.0

            if not self.chk_non_uniform.isChecked():
                self.spn_pct_uniform.setValue(round(pct_x, 1))
            self.spn_pct_x.setValue(round(pct_x, 1))
            self.spn_pct_y.setValue(round(pct_y, 1))
        finally:
            self._updating = False

    def _on_width_changed(self, val: float) -> None:
        if self._updating:
            return
        self._target_w = max(0.1, val)
        if self.chk_lock_aspect.isChecked():
            self._target_h = max(0.1, round(self._target_w / self._aspect_ratio, 2))
            self._updating = True
            self.spn_height.setValue(self._target_h)
            self._updating = False
        self._sync_to_dimensions(self._target_w, self._target_h)
        self._recalculate_preview()

    def _on_height_changed(self, val: float) -> None:
        if self._updating:
            return
        self._target_h = max(0.1, val)
        if self.chk_lock_aspect.isChecked():
            self._target_w = max(0.1, round(self._target_h * self._aspect_ratio, 2))
            self._updating = True
            self.spn_width.setValue(self._target_w)
            self._updating = False
        self._sync_to_dimensions(self._target_w, self._target_h)
        self._recalculate_preview()

    def _apply_quick_dimension(self, target_max_dim: float) -> None:
        if self._aspect_ratio >= 1.0:
            w = target_max_dim
            h = w / self._aspect_ratio
        else:
            h = target_max_dim
            w = h * self._aspect_ratio
        self._sync_to_dimensions(w, h)
        self._recalculate_preview()

    def _reset_to_native(self) -> None:
        self._sync_to_dimensions(self._native_w, self._native_h)
        self._recalculate_preview()

    def _on_pct_uniform_changed(self, pct: float) -> None:
        if self._updating:
            return
        ratio = max(0.001, pct / 100.0)
        w = self._native_w * ratio
        h = self._native_h * ratio
        self._sync_to_dimensions(w, h)
        self._recalculate_preview()

    def _on_pct_xy_changed(self) -> None:
        if self._updating or not self.chk_non_uniform.isChecked():
            return
        rx = max(0.001, self.spn_pct_x.value() / 100.0)
        ry = max(0.001, self.spn_pct_y.value() / 100.0)
        w = self._native_w * rx
        h = self._native_h * ry
        self._sync_to_dimensions(w, h)
        self._recalculate_preview()

    def _on_non_uniform_toggled(self, checked: bool) -> None:
        self.spn_pct_x.setEnabled(checked)
        self.spn_pct_y.setEnabled(checked)
        self.spn_pct_uniform.setEnabled(not checked)
        if not checked:
            self.chk_lock_aspect.setChecked(True)
            self._on_pct_uniform_changed(self.spn_pct_uniform.value())
        else:
            self.chk_lock_aspect.setChecked(False)

    def _on_preset_selected(self, *args: object, **kwargs: object) -> None:
        idx = self.cmb_presets.currentIndex()
        if idx < 0 or idx >= len(STANDARD_PRESETS):
            return
        target_box_w, target_box_h, _ = STANDARD_PRESETS[idx]

        if self.rad_fit_contain.isChecked():
            scale = min(target_box_w / self._native_w, target_box_h / self._native_h)
            new_w = self._native_w * scale
            new_h = self._native_h * scale
        else:
            new_w = target_box_w
            new_h = target_box_h

        self._sync_to_dimensions(new_w, new_h)
        self._recalculate_preview()

    # ==========================================================================
    # Preview Calculation & Final Transform
    # ==========================================================================

    def _recalculate_preview(self) -> None:
        new_t = self.result_transform()
        w = self._target_w
        h = self._target_h

        self.lbl_new_size.setText(f"New Size: {w:.2f} × {h:.2f} mm")
        self.lbl_new_pos.setText(f"Position: X: {new_t.pos_x_mm:.2f} mm, Y: {new_t.pos_y_mm:.2f} mm")

        sx = w / self._native_w
        sy = h / self._native_h
        safe_area = self.machine.usable_width_mm * self.machine.usable_height_mm
        occupancy = ((w * h) / max(1.0, safe_area)) * 100.0
        self.lbl_scale_info.setText(f"Scale: {sx:.3f}× / {sy:.3f}×   Safe Bed Occupancy: {occupancy:.1f}%")

        # Validate bounding containment inside safe area
        m = self.machine
        out_of_bounds = (
            new_t.pos_x_mm < m.usable_min_x
            or new_t.pos_y_mm < m.usable_min_y
            or (new_t.pos_x_mm + w) > m.usable_max_x
            or (new_t.pos_y_mm + h) > m.usable_max_y
        )
        if out_of_bounds:
            self.lbl_safety_badge.setText("⚠️ EXCEEDS SAFE AREA MARGINS")
            self.lbl_safety_badge.setStyleSheet(
                "background: #7F1D1D; color: #FCA5A5; font-weight: 700; font-size: 11px; padding: 2px 8px; border-radius: 4px;"
            )
        else:
            self.lbl_safety_badge.setText("✅ FITS INSIDE SAFE AREA")
            self.lbl_safety_badge.setStyleSheet(
                "background: #14532D; color: #86EFAC; font-weight: 700; font-size: 11px; padding: 2px 8px; border-radius: 4px;"
            )

    def result_transform(self) -> DocumentTransform:
        """Computes the final DocumentTransform reflecting target scale, anchor position, and centering."""
        new_t = DocumentTransform.from_dict(self.initial_transform.to_dict())

        # Scale factors relative to native SVG bounds
        new_t.scale_x = round(self._target_w / self._native_w, 4)
        new_t.scale_y = round(self._target_h / self._native_h, 4)

        if self.chk_center_on_bed.isChecked():
            # Automatically center on the 180×180 mm build plate
            new_t.pos_x_mm = round((self.machine.nominal_x_mm - self._target_w) * 0.5, 2)
            new_t.pos_y_mm = round((self.machine.nominal_y_mm - self._target_h) * 0.5, 2)
        else:
            # Anchor-relative repositioning
            btn = self.anchor_group.checkedButton()
            anchor_name = btn.text() if btn else "C"

            cur_b = self.current_bounds
            old_w = cur_b.width if cur_b.is_valid else self._target_w
            old_h = cur_b.height if cur_b.is_valid else self._target_h
            old_x = new_t.pos_x_mm
            old_y = new_t.pos_y_mm

            # Determine fixed anchor point coordinate in mm
            if "L" in anchor_name:
                fixed_x = old_x
            elif "R" in anchor_name:
                fixed_x = old_x + old_w
            else:  # Center
                fixed_x = old_x + old_w * 0.5

            if "B" in anchor_name:
                fixed_y = old_y
            elif "T" in anchor_name:
                fixed_y = old_y + old_h
            else:  # Center
                fixed_y = old_y + old_h * 0.5

            # Calculate new bottom-left pos_x_mm, pos_y_mm based on fixed anchor
            if "L" in anchor_name:
                new_x = fixed_x
            elif "R" in anchor_name:
                new_x = fixed_x - self._target_w
            else:
                new_x = fixed_x - self._target_w * 0.5

            if "B" in anchor_name:
                new_y = fixed_y
            elif "T" in anchor_name:
                new_y = fixed_y - self._target_h
            else:
                new_y = fixed_y - self._target_h * 0.5

            if self.chk_clamp_safe.isChecked():
                new_x = max(self.machine.usable_min_x, min(self.machine.usable_max_x - self._target_w, new_x))
                new_y = max(self.machine.usable_min_y, min(self.machine.usable_max_y - self._target_h, new_y))

            new_t.pos_x_mm = round(new_x, 2)
            new_t.pos_y_mm = round(new_y, 2)

        return new_t

    @property
    def target_width(self) -> float:
        return self._target_w

    @property
    def target_height(self) -> float:
        return self._target_h

