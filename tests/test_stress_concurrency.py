"""Stress and concurrency testing suite for PySide6 GUI, Simulator monkey testing, Undo/Redo exhaustion, and Worker cancellation."""

from __future__ import annotations

from pathlib import Path
import sys
import time

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from app.core.models import DocumentTransform
from app.ui.canvas import BuildPlateCanvas, CanvasTool
from app.ui.main_window import MainWindow
from app.ui.panels.simulator_bar import SimulatorControlBar
from app.ui.undo_commands import TransformChangeCommand


EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def test_simulator_rapid_monkey_testing(qapp):
    """Stress Test 1: Rapid clicking ('monkey testing') on simulator transport controls."""
    bar = SimulatorControlBar()
    bar.show()
    qapp.processEvents()

    # Load sample moves from MainWindow calibration file
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    moves = list(win.project.toolpath_moves)
    assert len(moves) > 0
    bar.load_moves(moves)

    # Frenetic playback controls toggling
    for i in range(120):
        action = i % 5
        if action == 0:
            bar.on_toggle_play()
        elif action == 1:
            bar.on_step_forward()
        elif action == 2:
            bar.on_step_backward()
        elif action == 3:
            bar.on_restart()
        elif action == 4:
            bar._on_slider_scrubbed(i % len(moves))

        if i % 10 == 0:
            # Randomly change speed
            bar.cmb_speed.setCurrentIndex(i % bar.cmb_speed.count())

        # Advance simulator time
        bar._on_timer_tick()

    assert bar.simulator.state.current_move_index >= 0
    assert bar.simulator.state.current_move_index < len(moves)
    assert bar.simulator.state.elapsed_time_seconds >= 0.0

    bar.on_exit_simulation_view()
    win.close()
    bar.close()


def test_canvas_frenetic_zoom_pan_and_tools(qapp):
    """Stress Test 2: Frenetic zoom and pan while rendering under different tools."""
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    canvas = win.canvas
    canvas.show()
    qapp.processEvents()

    center = QPointF(canvas.width() * 0.5, canvas.height() * 0.5)

    for i in range(100):
        # Alternating aggressive zoom in / zoom out
        factor = 1.35 if (i % 2 == 0) else 0.74
        canvas.zoom_by(factor, anchor_px=center)

        # Pan shift
        canvas.pan_offset_px = QPointF(
            canvas.pan_offset_px.x() + ((i % 7) - 3) * 15.0,
            canvas.pan_offset_px.y() + ((i % 5) - 2) * 12.0,
        )

        # Tool cycling
        tool = [CanvasTool.SELECT, CanvasTool.PAN, CanvasTool.MEASURE][i % 3]
        canvas.set_active_tool(tool)

        # Verify coordinate conversion safety
        mm_x, mm_y = canvas.screen_to_mm(center)
        scr = canvas.mm_to_screen(mm_x, mm_y)
        assert abs(scr.x() - center.x()) < 1.0
        assert abs(scr.y() - center.y()) < 1.0

        if i % 25 == 0:
            canvas.fit_plate_to_view()

    # Render canvas to pixmap to force paintEvent verification
    pix = QPixmap(canvas.size())
    canvas.render(pix)
    assert not pix.isNull()

    win.close()


def test_window_rapid_resizing_stress(qapp):
    """Stress Test 3: Rapid resizing of the main window through extreme viewports."""
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    win.show()
    qapp.processEvents()

    sizes = [
        (1120, 720),
        (1920, 1080),
        (1280, 800),
        (1600, 900),
        (1440, 900),
        (2560, 1440),
        (1366, 768),
        (1920, 1200),
    ]

    for w, h in sizes * 3:
        win.resize(w, h)
        qapp.processEvents()
        assert win.width() >= win.minimumWidth()
        assert win.height() >= win.minimumHeight()
        assert win.canvas.width() > 100
        assert win.canvas.height() > 100

    win.close()


def test_undo_redo_stack_exhaustion(qapp):
    """Stress Test 4: Deep Undo/Redo exhaustion with 100 consecutive transformations."""
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    win.show()
    qapp.processEvents()

    initial_x = win.project.doc_transform.pos_x_mm
    history_x: list[float] = [initial_x]

    # Perform 100 distinct transformations
    for i in range(1, 101):
        target_x = initial_x + float(i) * 0.25
        history_x.append(target_x)

        old_t = DocumentTransform.from_dict(win.project.doc_transform.to_dict())
        new_t = DocumentTransform.from_dict(old_t.to_dict())
        new_t.pos_x_mm = target_x
        cmd = TransformChangeCommand(old_t, new_t, win._apply_transform_direct)
        win.undo_stack.push(cmd)

    assert abs(win.project.doc_transform.pos_x_mm - history_x[-1]) < 1e-3
    assert win.undo_stack.canUndo()

    # Frenetic Undo all 100 steps
    for i in range(100):
        win.undo_stack.undo()
        expected_x = history_x[100 - (i + 1)]
        assert abs(win.project.doc_transform.pos_x_mm - expected_x) < 1e-3

    assert abs(win.project.doc_transform.pos_x_mm - initial_x) < 1e-3
    assert not win.undo_stack.canUndo()

    # Frenetic Redo all 100 steps
    for i in range(100):
        win.undo_stack.redo()
        expected_x = history_x[i + 1]
        assert abs(win.project.doc_transform.pos_x_mm - expected_x) < 1e-3

    assert abs(win.project.doc_transform.pos_x_mm - history_x[-1]) < 1e-3
    assert not win.undo_stack.canRedo()

    win.close()


def test_qthreadpool_rapid_task_cancellation_and_file_switching(qapp):
    """Stress Test 5: Rapid asynchronous background recalculations to test worker cancellation and race conditions."""
    win = MainWindow(check_recovery=False, synchronous_pipeline=False)
    win.show()
    qapp.processEvents()

    # Fire 30 rapid asynchronous recomputations with different offsets
    for i in range(30):
        win.project.doc_transform.pos_x_mm = 20.0 + (i % 10) * 2.0
        win.recompute_pipeline(synchronous=False)

    # Wait for background thread pool to finish cleanly
    success = win.thread_pool.waitForDone(5000)
    assert success
    qapp.processEvents()

    # Toolpath moves must match the last requested task without dangling threads
    assert len(win.project.toolpath_moves) > 0
    assert win._active_worker is None

    win.close()
