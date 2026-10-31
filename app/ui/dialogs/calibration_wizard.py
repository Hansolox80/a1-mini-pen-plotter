"""6-Step Pen Calibration Wizard for the Bambu Lab A1 Mini (Section 6)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile


class PenCalibrationWizard(QDialog):
    """Guides the user step-by-step through physical pen mounting, Z contact height, lift height, test plot, and saving."""

    def __init__(
        self,
        pen: PenProfile,
        machine: MachineProfile,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("A1 Mini Pen Calibration Wizard (6 Steps)")
        self.resize(660, 520)

        self.pen = PenProfile.from_dict(pen.to_dict())
        self.machine = machine

        self._build_ui()
        self._update_step_header()

    def _build_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(12)

        # Header Banner
        hdr_card = QFrame(self)
        hdr_card.setObjectName("SectionCard")
        h_layout = QVBoxLayout(hdr_card)
        h_layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_step_title = QLabel("Step 1 of 6 — Install Physical Pen Holder", hdr_card)
        self.lbl_step_title.setObjectName("AppTitleLabel")
        h_layout.addWidget(self.lbl_step_title)

        self.lbl_safety_banner = QLabel(
            "CRITICAL SAFETY RULE: Never assume Z = 0.00 mm corresponds to paper contact! "
            "Actual pen holder geometry and physical clearances must be verified manually on your A1 Mini.",
            hdr_card,
        )
        self.lbl_safety_banner.setStyleSheet("color: #F59E0B; font-weight: 600;")
        self.lbl_safety_banner.setWordWrap(True)
        h_layout.addWidget(self.lbl_safety_banner)
        vbox.addWidget(hdr_card)

        # 6-Step Stack
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self._build_step1_mount())
        self.stack.addWidget(self._build_step2_tip_position())
        self.stack.addWidget(self._build_step3_contact_z())
        self.stack.addWidget(self._build_step4_lifted_z())
        self.stack.addWidget(self._build_step5_test_move())
        self.stack.addWidget(self._build_step6_save())
        vbox.addWidget(self.stack, 1)

        # Footer Navigation
        nav = QHBoxLayout()
        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        nav.addWidget(btn_cancel)
        nav.addStretch(1)

        self.btn_back = QPushButton("← Previous Step", self)
        self.btn_back.clicked.connect(self._go_prev)
        nav.addWidget(self.btn_back)

        self.btn_next = QPushButton("Next Step →", self)
        self.btn_next.setObjectName("PrimaryButton")
        self.btn_next.clicked.connect(self._go_next)
        nav.addWidget(self.btn_next)

        vbox.addLayout(nav)

    def _build_step1_mount(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(10)

        lbl = QLabel(
            "1. Installing the Physical Pen Holder\n\n"
            "• Unload any filament from the Bambu Lab A1 Mini extruder and ensure the nozzle and bed are completely cold (0 °C).\n"
            "• Attach your A1 Mini pen holder bracket securely to the toolhead housing.\n"
            "• Tape a flat sheet of paper onto the 180 × 180 mm PEI build plate using low-profile painter's tape "
            "(avoid thick binder clips that could collide with the X-axis gantry or purge wiper).\n"
            "• Home the printer axes on the A1 Mini touchscreen (Control → Home) BEFORE inserting the pen low into the clamp.",
            page,
        )
        lbl.setWordWrap(True)
        vbox.addWidget(lbl)

        self.chk_step1_done = QCheckBox(
            "I have unloaded filament, attached the pen mount, and verified build plate clearance.",
            page,
        )
        self.chk_step1_done.setChecked(True)
        vbox.addWidget(self.chk_step1_done)
        vbox.addStretch(1)
        return page

    def _build_step2_tip_position(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(10)

        lbl = QLabel(
            "2. Checking the Pen Tip Position & XY Offset\n\n"
            "• Raise Z on the printer screen to at least Z = 35 mm.\n"
            "• Insert the pen into the mount so that the pen tip extends below the hotend nozzle (typically 4–8 mm lower than the nozzle tip) "
            "so the nozzle never scrapes the paper.\n"
            "• Measure or verify the horizontal X/Y offset from the nozzle to the pen tip:",
            page,
        )
        lbl.setWordWrap(True)
        vbox.addWidget(lbl)

        form = QFormLayout()
        self.spn_tip_diam = QDoubleSpinBox(page)
        self.spn_tip_diam.setRange(0.05, 10.0)
        self.spn_tip_diam.setDecimals(2)
        self.spn_tip_diam.setSuffix(" mm")
        self.spn_tip_diam.setValue(self.pen.tip_diameter_mm)

        self.spn_off_x = QDoubleSpinBox(page)
        self.spn_off_x.setRange(-60.0, 60.0)
        self.spn_off_x.setDecimals(2)
        self.spn_off_x.setSuffix(" mm")
        self.spn_off_x.setValue(self.pen.x_offset_mm)

        self.spn_off_y = QDoubleSpinBox(page)
        self.spn_off_y.setRange(-60.0, 60.0)
        self.spn_off_y.setDecimals(2)
        self.spn_off_y.setSuffix(" mm")
        self.spn_off_y.setValue(self.pen.y_offset_mm)

        form.addRow("Pen Tip Diameter:", self.spn_tip_diam)
        form.addRow("Fine Pen X Offset:", self.spn_off_x)
        form.addRow("Fine Pen Y Offset:", self.spn_off_y)
        vbox.addLayout(form)
        vbox.addStretch(1)
        return page

    def _build_step3_contact_z(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(10)

        lbl = QLabel(
            "3. Finding the Correct Contact Height (Drawing Z)\n\n"
            "• Move the toolhead to the center of the build plate (X = 90 mm, Y = 90 mm) via the printer touchscreen.\n"
            "• Slowly jog the Z-axis downward in 1.0 mm steps, then 0.1 mm steps, while gently sliding the paper slightly.\n"
            "• Stop as soon as the pen tip makes clean ink contact with the paper (or compresses a spring-loaded holder by ~0.5–1.0 mm).\n"
            "• Read the exact Z value shown on the A1 Mini screen and enter it below (NEVER assume Z = 0):",
            page,
        )
        lbl.setWordWrap(True)
        vbox.addWidget(lbl)

        form = QFormLayout()
        self.spn_draw_z = QDoubleSpinBox(page)
        self.spn_draw_z.setRange(0.5, 150.0)
        self.spn_draw_z.setDecimals(2)
        self.spn_draw_z.setSingleStep(0.1)
        self.spn_draw_z.setSuffix(" mm")
        self.spn_draw_z.setValue(self.pen.drawing_z_mm)
        self.spn_draw_z.valueChanged.connect(self._on_draw_z_changed)

        self.spn_pen_down_z = QDoubleSpinBox(page)
        self.spn_pen_down_z.setRange(0.5, 150.0)
        self.spn_pen_down_z.setDecimals(2)
        self.spn_pen_down_z.setSingleStep(0.1)
        self.spn_pen_down_z.setSuffix(" mm")
        self.spn_pen_down_z.setValue(self.pen.pen_down_z_mm)

        form.addRow("Measured Drawing Contact Z:", self.spn_draw_z)
        form.addRow("Initial Touchdown Z:", self.spn_pen_down_z)
        vbox.addLayout(form)
        vbox.addStretch(1)
        return page

    def _build_step4_lifted_z(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(10)

        lbl = QLabel(
            "4. Finding a Safe Lifted Height (Pen-Up Z)\n\n"
            "• Set the Pen-Up Z height high enough that rapid travel moves completely clear the paper, tape edges, and any slight sheet curl "
            "(recommended: 3.0 to 5.0 mm above Drawing Z).\n"
            "• Configure Z lift/lower speed and pen stabilization delay:",
            page,
        )
        lbl.setWordWrap(True)
        vbox.addWidget(lbl)

        form = QFormLayout()
        self.spn_lift_h = QDoubleSpinBox(page)
        self.spn_lift_h.setRange(1.0, 50.0)
        self.spn_lift_h.setDecimals(2)
        self.spn_lift_h.setSuffix(" mm")
        self.spn_lift_h.setValue(self.pen.lift_height_mm)
        self.spn_lift_h.valueChanged.connect(self._on_lift_h_changed)

        self.spn_up_z = QDoubleSpinBox(page)
        self.spn_up_z.setRange(1.5, 160.0)
        self.spn_up_z.setDecimals(2)
        self.spn_up_z.setSuffix(" mm")
        self.spn_up_z.setValue(self.pen.pen_up_z_mm)

        self.spn_z_spd = QDoubleSpinBox(page)
        self.spn_z_spd.setRange(1.0, 50.0)
        self.spn_z_spd.setDecimals(1)
        self.spn_z_spd.setSuffix(" mm/s")
        self.spn_z_spd.setValue(self.pen.z_speed_mm_s)

        self.spn_dwell = QSpinBox(page)
        self.spn_dwell.setRange(0, 1000)
        self.spn_dwell.setSuffix(" ms")
        self.spn_dwell.setValue(self.pen.stabilization_delay_ms)

        form.addRow("Clearance Lift Height (ΔZ):", self.spn_lift_h)
        form.addRow("Resulting Pen-Up Z:", self.spn_up_z)
        form.addRow("Z Movement Speed:", self.spn_z_spd)
        form.addRow("Pen Stabilization Dwell:", self.spn_dwell)
        vbox.addLayout(form)
        vbox.addStretch(1)
        return page

    def _build_step5_test_move(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(8)

        lbl = QLabel(
            "5. Testing a Short Drawing Movement\n\n"
            "Inspect the generated 20 × 20 mm calibration test square G-code below. "
            "You can export this test file to your MicroSD card to verify line quality and Z clearance on paper.",
            page,
        )
        lbl.setWordWrap(True)
        vbox.addWidget(lbl)

        self.txt_test_gcode = QPlainTextEdit(page)
        self.txt_test_gcode.setReadOnly(True)
        self.txt_test_gcode.setStyleSheet('font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11px;')
        vbox.addWidget(self.txt_test_gcode, 1)

        btn_export_test = QPushButton("Export Calibration Test Square (.gcode)...", page)
        btn_export_test.clicked.connect(self._export_test_gcode)
        vbox.addWidget(btn_export_test)
        return page

    def _build_step6_save(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(10)

        lbl = QLabel(
            "6. Saving the Calibrated Pen Profile\n\n"
            "Review your calibrated parameters below and save the profile. "
            "Saving marks this profile as Calibrated for safety validation.",
            page,
        )
        lbl.setWordWrap(True)
        vbox.addWidget(lbl)

        form = QFormLayout()
        self.edt_prof_name = QLineEdit(self.pen.name, page)
        self.spn_draw_spd = QDoubleSpinBox(page)
        self.spn_draw_spd.setRange(2.0, 200.0)
        self.spn_draw_spd.setSuffix(" mm/s")
        self.spn_draw_spd.setValue(self.pen.draw_speed_mm_s)

        self.spn_trav_spd = QDoubleSpinBox(page)
        self.spn_trav_spd.setRange(10.0, 350.0)
        self.spn_trav_spd.setSuffix(" mm/s")
        self.spn_trav_spd.setValue(self.pen.travel_speed_mm_s)

        self.lbl_final_summary = QLabel("", page)
        self.lbl_final_summary.setObjectName("MonoValueLabel")

        form.addRow("Pen Profile Name:", self.edt_prof_name)
        form.addRow("Drawing Speed:", self.spn_draw_spd)
        form.addRow("Travel Speed:", self.spn_trav_spd)
        form.addRow("Calibrated Heights:", self.lbl_final_summary)
        vbox.addLayout(form)
        vbox.addStretch(1)
        return page

    def _on_draw_z_changed(self, val: float) -> None:
        self.spn_pen_down_z.setValue(round(val + 0.2, 2))
        self.spn_up_z.setValue(round(val + self.spn_lift_h.value(), 2))

    def _on_lift_h_changed(self, val: float) -> None:
        self.spn_up_z.setValue(round(self.spn_draw_z.value() + val, 2))

    def _generate_short_test_gcode(self) -> str:
        dz = self.spn_draw_z.value()
        uz = self.spn_up_z.value()
        zf = self.spn_z_spd.value() * 60.0
        df = self.spn_draw_spd.value() * 60.0
        tf = self.spn_trav_spd.value() * 60.0
        dw = self.spn_dwell.value()
        return (
            "; === A1 Mini Pen Plotter - 20x20mm Calibration Test ===\n"
            "G21 ; Millimeters\n"
            "G90 ; Absolute coordinates\n"
            "M104 S0 ; Hotend OFF\n"
            "M140 S0 ; Bed OFF\n"
            "G28 ; Home axes safely\n"
            f"G0 Z{uz:.3f} F{zf:.0f} ; 1. Pure vertical lift to calibrated Pen-Up Z\n"
            f"G0 X80.000 Y80.000 F{tf:.0f} ; 2. Rapid XY travel (pen elevated)\n"
            f"G1 Z{dz:.3f} F{zf:.0f} ; 3. Controlled vertical descent to Drawing Z\n"
            f"G4 P{dw} ; 4. Stabilization dwell\n"
            f"G1 X100.000 Y80.000 F{df:.0f} ; Draw 20mm bottom edge\n"
            f"G1 X100.000 Y100.000 F{df:.0f} ; Draw 20mm right edge\n"
            f"G1 X80.000 Y100.000 F{df:.0f} ; Draw 20mm top edge\n"
            f"G1 X80.000 Y80.000 F{df:.0f} ; Close 20x20mm square\n"
            f"G0 Z{uz:.3f} F{zf:.0f} ; 5. Pure vertical lift to Pen-Up Z\n"
            f"G0 X0.000 Y170.000 F{tf:.0f} ; 6. Move bed forward to present drawing\n"
            "M84 ; Motors off\n"
        )

    def _export_test_gcode(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Calibration Test G-code",
            "a1_mini_calibration_test_20mm.gcode",
            "G-Code Files (*.gcode)",
        )
        if path:
            Path(path).write_text(self._generate_short_test_gcode(), encoding="utf-8")
            QMessageBox.information(self, "Exported", f"Calibration test G-code saved to:\n{path}")

    def _update_step_header(self) -> None:
        idx = self.stack.currentIndex()
        titles = [
            "Step 1 of 6 — Install Physical Pen Holder",
            "Step 2 of 6 — Check Pen Tip Position & Offsets",
            "Step 3 of 6 — Find Correct Contact Height (Drawing Z)",
            "Step 4 of 6 — Configure Safe Lifted Height (Pen-Up Z)",
            "Step 5 of 6 — Test Short Drawing Movement",
            "Step 6 of 6 — Save Calibrated Pen Profile",
        ]
        self.lbl_step_title.setText(titles[idx])
        self.btn_back.setEnabled(idx > 0)
        self.btn_next.setText("Save Calibrated Profile" if idx == 5 else "Next Step →")

        if idx == 4:
            self.txt_test_gcode.setPlainText(self._generate_short_test_gcode())
        elif idx == 5:
            self.lbl_final_summary.setText(
                f"Drawing Z = {self.spn_draw_z.value():.2f} mm  |  "
                f"Pen-Up Z = {self.spn_up_z.value():.2f} mm  |  "
                f"Lift ΔZ = {self.spn_lift_h.value():.2f} mm"
            )

    def _go_prev(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_step_header()

    def _go_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 3 and self.spn_up_z.value() <= self.spn_draw_z.value():
            QMessageBox.critical(
                self,
                "Invalid Z Heights",
                "Pen-Up Z must be strictly greater than Drawing Z so the pen lifts clear of the paper.",
            )
            return

        if idx < 5:
            self.stack.setCurrentIndex(idx + 1)
            self._update_step_header()
        else:
            # Finalize calibrated pen profile
            self.pen.name = self.edt_prof_name.text().strip() or self.pen.name
            self.pen.tip_diameter_mm = self.spn_tip_diam.value()
            self.pen.x_offset_mm = self.spn_off_x.value()
            self.pen.y_offset_mm = self.spn_off_y.value()
            self.pen.drawing_z_mm = self.spn_draw_z.value()
            self.pen.pen_down_z_mm = self.spn_pen_down_z.value()
            self.pen.lift_height_mm = self.spn_lift_h.value()
            self.pen.pen_up_z_mm = self.spn_up_z.value()
            self.pen.z_speed_mm_s = self.spn_z_spd.value()
            self.pen.stabilization_delay_ms = self.spn_dwell.value()
            self.pen.draw_speed_mm_s = self.spn_draw_spd.value()
            self.pen.travel_speed_mm_s = self.spn_trav_spd.value()
            self.pen.is_calibrated = True
            self.accept()

    def calibrated_pen(self) -> PenProfile:
        return self.pen
