"""Automated UI integration tests for MainWindow, Canvas, Sidebar, Inspector, Simulator, and Dialogs."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core.models import DocumentTransform, FillSettings, OptimizationSettings, WorkflowMode
from app.ui.dialogs.calibration_wizard import PenCalibrationWizard
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.dialogs.validation_dialog import ValidationAndGcodeDialog
from app.ui.main_window import MainWindow


EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def test_main_window_startup_and_pipeline(qapp):
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    win.show()
    qapp.processEvents()

    # Default calibration target should be loaded
    assert win.project.svg_document is not None
    assert len(win.project.toolpath_moves) > 0
    assert "G21" in win.current_gcode
    assert "G90" in win.current_gcode

    # Test loading 20x20mm square via UI method
    win.load_svg_file(str(EXAMPLES_DIR / "01_square_20x20mm.svg"), mark_dirty=False)
    assert abs(win.current_stats.drawing_width_mm - 20.0) < 1e-2
    assert abs(win.current_stats.drawing_height_mm - 20.0) < 1e-2

    # Test Undo / Redo on Transform
    old_x = win.project.doc_transform.pos_x_mm
    new_t = DocumentTransform.from_dict(win.project.doc_transform.to_dict())
    new_t.pos_x_mm = 55.0
    win._on_inspector_transform_changed(new_t)
    assert abs(win.project.doc_transform.pos_x_mm - 55.0) < 1e-3
    assert win.undo_stack.canUndo()

    win.undo_stack.undo()
    assert abs(win.project.doc_transform.pos_x_mm - old_x) < 1e-3

    win.undo_stack.redo()
    assert abs(win.project.doc_transform.pos_x_mm - 55.0) < 1e-3

    # Test Center on Plate & Fit Safe Area buttons
    win.action_center_on_plate()
    assert abs(win.project.doc_transform.pos_x_mm - 80.0) < 1e-2
    win.action_align_safe_origin()
    assert abs(win.project.doc_transform.pos_x_mm - win.project.machine_profile.usable_min_x) < 1e-2

    # Test Fill Mode & Optimization changes
    win._on_fill_settings_changed(FillSettings(mode="hatch", hatch_spacing_mm=2.0))
    win._on_optimization_settings_changed(OptimizationSettings(strategy="min_travel_2opt"))
    win._on_workflow_mode_changed(WorkflowMode.STANDARD_GCODE)
    assert len(win.project.toolpath_moves) > 0

    # Test Simulator Bar controls
    win.simulator_bar.on_step_forward()
    assert win.simulator_bar.simulator.state.current_move_index == 1
    win.simulator_bar.on_restart()
    assert win.simulator_bar.simulator.state.current_move_index == 0
    win.simulator_bar.on_exit_simulation_view()

    win.close()


def test_dialogs_instantiation_and_logic(qapp):
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)

    # 1. Pen Calibration Wizard (6 steps)
    wiz = PenCalibrationWizard(win.project.pen_profile, win.project.machine_profile, win)
    assert wiz.stack.count() == 6
    for step_idx in range(5):
        assert wiz.stack.currentIndex() == step_idx
        wiz._go_next()
    assert wiz.stack.currentIndex() == 5
    wiz.spn_draw_z.setValue(14.5)
    wiz.spn_up_z.setValue(19.0)
    wiz._go_next()  # Step 6 -> accept and mark calibrated
    cal_pen = wiz.calibrated_pen()
    assert cal_pen.is_calibrated
    assert abs(cal_pen.drawing_z_mm - 14.5) < 1e-3

    # 2. Safety Validation & G-Code Inspector Dialog
    val_dlg = ValidationAndGcodeDialog(win.current_validation, win.current_gcode, initial_tab=0, parent=win)
    assert val_dlg.report is not None
    val_dlg.close()

    # 3. Settings Dialog
    set_dlg = SettingsDialog(win.settings_manager.settings, win.profile_manager, parent=win)
    set_dlg.cmb_theme.setCurrentIndex(1)
    set_dlg._on_save()
    assert set_dlg.settings.theme == "slate_engineering"
    set_dlg.close()

    win.close()


def test_ui_comprehensive_button_and_shortcut_behavior(qapp, monkeypatch):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QMessageBox

    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    win.show()
    qapp.processEvents()

    # 1. Canvas keyboard zooming shortcuts (+, -, =)
    initial_zoom = win.canvas.zoom_px_per_mm
    evt_plus = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Plus, Qt.KeyboardModifier.NoModifier)
    win.canvas.keyPressEvent(evt_plus)
    assert win.canvas.zoom_px_per_mm > initial_zoom

    evt_minus = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Minus, Qt.KeyboardModifier.NoModifier)
    win.canvas.keyPressEvent(evt_minus)
    assert abs(win.canvas.zoom_px_per_mm - initial_zoom) < 1e-2

    evt_equal = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Equal, Qt.KeyboardModifier.NoModifier)
    win.canvas.keyPressEvent(evt_equal)
    assert win.canvas.zoom_px_per_mm > initial_zoom

    # 2. Machine Profile CRUD (Duplicate, Rename, Delete protection)
    sb = win.left_sidebar
    orig_count = len(win.profile_manager.machines)
    sb._on_duplicate_machine()
    assert len(win.profile_manager.machines) == orig_count + 1
    dup_m = sb.current_machine_profile()
    assert "(Copy)" in dup_m.name

    # Rename
    win.profile_manager.rename_machine(dup_m.id, "Custom Mini Unit 2")
    sb.refresh_profiles_ui(select_machine_id=dup_m.id)
    assert sb.current_machine_profile().name == "Custom Mini Unit 2"

    # Delete custom machine
    sb._on_delete_machine()
    assert len(win.profile_manager.machines) == orig_count

    # Verify default bambu_a1_mini cannot be deleted
    default_m = win.profile_manager.get_default_machine()
    assert not win.profile_manager.delete_machine(default_m.id)

    # 3. Simulator Control Bar states on empty project
    win.action_new_project()
    qapp.processEvents()
    assert not win.simulator_bar.btn_play_pause.isEnabled()
    assert not win.simulator_bar.slider_progress.isEnabled()
    assert not win.simulator_bar.btn_restart.isEnabled()

    # 4. Safe warning on exports when project has no toolpaths
    warn_calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, msg: warn_calls.append(title))

    win.action_export_gcode()
    win.action_export_3mf()
    win.action_export_optimized_svg()
    win.action_export_report()
    win.action_export_preview_png()

    assert len(warn_calls) == 5
    assert all("Nothing to Export" in t for t in warn_calls)

    # 5. Right Inspector proportional width/height editing
    win.load_svg_file(str(EXAMPLES_DIR / "01_square_20x20mm.svg"), mark_dirty=False)
    insp = win.right_inspector
    old_w = insp.spn_width.value()
    insp._on_width_edited(40.0)
    assert abs(insp.spn_scale_x.value() - 2.0) < 1e-2
    assert abs(insp.spn_scale_y.value() - 2.0) < 1e-2

    win.close()

