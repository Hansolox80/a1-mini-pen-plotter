"""Captures application screenshots for documentation and generates sample output files in examples/output/."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core.models import FillSettings
from app.export.gcode_exporter import GcodeExporter
from app.ui.dialogs.calibration_wizard import PenCalibrationWizard
from app.ui.dialogs.validation_dialog import ValidationAndGcodeDialog
from app.ui.main_window import MainWindow


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv[:1])

    screenshots_dir = ROOT_DIR / "docs" / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    out_dir = ROOT_DIR / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    win = MainWindow(check_recovery=False)
    win.show()
    app.processEvents()
    win.canvas.fit_plate_to_view()
    app.processEvents()

    # 1. Main Workspace Screenshot
    win.grab().save(str(screenshots_dir / "main_workspace.png"), "PNG")

    # Save sample output files from the loaded Calibration Target
    win.project.pen_profile.is_calibrated = True
    win.recompute_pipeline()
    GcodeExporter.export_gcode_file(
        out_dir / "11_a1_mini_calibration_target.gcode",
        win.project.toolpath_moves,
        win.current_gcode,
        win.project.machine_profile,
        win.project.pen_profile,
    )
    GcodeExporter.export_bambu_3mf_file(
        out_dir / "11_a1_mini_calibration_target.gcode.3mf",
        win.project.toolpath_moves,
        win.current_gcode,
        win.current_stats,
        win.project.machine_profile,
        win.project.pen_profile,
    )
    GcodeExporter.export_validation_report(
        out_dir / "11_a1_mini_calibration_target_report.md",
        win.current_validation,
        win.project.machine_profile,
        win.project.pen_profile,
        win.current_stats,
    )

    # 2. Active Simulation + Hatching Fill Screenshot
    win.right_inspector.cmb_fill_mode.setCurrentIndex(2)  # Hatching Pattern Fill
    win._on_fill_settings_changed(FillSettings(mode="hatch", hatch_spacing_mm=1.2, hatch_angle_deg=45.0, cross_hatch=True))
    app.processEvents()
    mid_move = len(win.project.toolpath_moves) // 2
    win.simulator_bar.simulator.seek_to_move(mid_move, progress=0.6)
    win.simulator_bar._sim_active = True
    win.simulator_bar._sync_ui_from_state()
    win.canvas.set_simulation_state(win.simulator_bar.simulator.state, True)
    app.processEvents()
    win.grab().save(str(screenshots_dir / "simulation_active.png"), "PNG")

    # 3. Pen Calibration Wizard Screenshot
    wiz = PenCalibrationWizard(win.project.pen_profile, win.project.machine_profile, win)
    wiz.stack.setCurrentIndex(2)  # Step 3: Contact Z
    wiz._update_step_header()
    wiz.show()
    app.processEvents()
    wiz.grab().save(str(screenshots_dir / "calibration_wizard.png"), "PNG")
    wiz.close()

    # 4. Safety Validation & G-Code Inspector Screenshot
    val_dlg = ValidationAndGcodeDialog(win.current_validation, win.current_gcode, initial_tab=0, parent=win)
    val_dlg.show()
    app.processEvents()
    val_dlg.grab().save(str(screenshots_dir / "safety_inspector.png"), "PNG")
    val_dlg.close()

    win.close()
    print("Captured 4 screenshots and generated sample outputs in examples/output/.")


if __name__ == "__main__":
    main()
