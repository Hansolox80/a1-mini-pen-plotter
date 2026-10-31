"""Main application window for A1 Mini Pen Plotter."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import __app_name__, __version__
from app.core.coordinate_system import CoordinateTransformer
from app.core.gcode_generator import GcodeGenerator
from app.core.models import (
    BoundingBox,
    DocumentTransform,
    FillSettings,
    OptimizationSettings,
    ParsedSvgDocument,
    ToolpathMove,
    ToolpathStats,
    WorkflowMode,
)
from app.core.path_optimizer import ToolpathGenerator
from app.core.pipeline_worker import PipelineWorker
from app.core.svg_parser import SvgParser
from app.export.gcode_exporter import GcodeExporter, SafetyExportBlockedError
from app.export.project_exporter import PlotterProject, ProjectManager
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile, ProfileManager
from app.machine.safety import SafetyValidationReport, SafetyValidator, ValidationSeverity
from app.ui.canvas import BuildPlateCanvas
from app.ui.dialogs.calibration_wizard import PenCalibrationWizard
from app.ui.dialogs.resize_dialog import ResizeDrawingDialog
from app.ui.dialogs.settings_dialog import AppSettings, SettingsDialog, SettingsManager
from app.ui.dialogs.validation_dialog import ValidationAndGcodeDialog
from app.ui.icons import make_icon
from app.ui.panels.left_sidebar import LeftSidebar
from app.ui.panels.right_inspector import RightInspectorPanel
from app.ui.panels.simulator_bar import SimulatorControlBar
from app.ui.theme import build_stylesheet
from app.ui.undo_commands import TransformChangeCommand

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Primary desktop window integrating Toolbar, Left Sidebar, Build Plate Canvas, Simulator, Inspector, and Status Bar."""

    def __init__(self, check_recovery: bool = True, synchronous_pipeline: bool = False) -> None:
        super().__init__()
        self.synchronous_pipeline = synchronous_pipeline
        self.thread_pool = QThreadPool.globalInstance()
        self._pipeline_task_id: int = 0
        self._active_worker: Optional[PipelineWorker] = None

        self.setWindowTitle(f"{__app_name__} v{__version__} — Bambu Lab A1 Mini SVG-to-G-Code Studio")
        self.resize(1460, 900)
        self.setMinimumSize(1120, 720)

        # Icon
        icon_path = Path(__file__).resolve().parent.parent / "resources" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Core Managers
        self.profile_manager = ProfileManager()
        self.settings_manager = SettingsManager()
        self.project_manager = ProjectManager()
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(300)

        # Active Project State
        self.project = PlotterProject(
            machine_profile=self.profile_manager.get_default_machine(),
            pen_profile=self.profile_manager.get_default_pen(),
        )
        self.current_stats = ToolpathStats()
        self.current_gcode: str = ""
        self.current_validation = SafetyValidationReport()
        self.current_drawing_bounds = BoundingBox(0, 0, 0, 0)

        # Apply Theme
        self.apply_settings(self.settings_manager.settings, initial=True)

        # Build UI Layout
        self._build_menu_bar()
        self._build_central_ui()
        self._build_status_bar()

        # Autosave Timer
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(max(15, self.settings_manager.settings.autosave_interval_sec) * 1000)
        self.autosave_timer.timeout.connect(self._on_autosave_tick)
        self.autosave_timer.start()

        # Load initial calibration target example so workspace is immediately alive and demonstrable
        default_sample = Path(__file__).resolve().parent.parent.parent / "examples" / "11_a1_mini_calibration_target.svg"
        if default_sample.exists():
            self.load_svg_file(str(default_sample), mark_dirty=False)

        if check_recovery and self.project_manager.has_recovery_file():
            QTimer.singleShot(300, self._prompt_crash_recovery)

    # ==========================================================================
    # UI Construction
    # ==========================================================================

    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        act_new = QAction("New Project", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self.action_new_project)
        file_menu.addAction(act_new)

        act_open_svg = QAction("Open SVG Drawing...", self)
        act_open_svg.setShortcut(QKeySequence.StandardKey.Open)
        act_open_svg.triggered.connect(self.action_open_svg)
        file_menu.addAction(act_open_svg)

        act_open_proj = QAction("Open Project (.a1plot)...", self)
        act_open_proj.setShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_O))
        act_open_proj.triggered.connect(self.action_open_project)
        file_menu.addAction(act_open_proj)

        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        act_save = QAction("Save Project", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self.action_save_project)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save Project As...", self)
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        act_save_as.triggered.connect(self.action_save_project_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_exp_gcode = QAction("Export G-Code (.gcode)...", self)
        act_exp_gcode.setShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_E))
        act_exp_gcode.triggered.connect(self.action_export_gcode)
        file_menu.addAction(act_exp_gcode)

        act_exp_3mf = QAction("Export Bambu Studio Package (.gcode.3mf)...", self)
        act_exp_3mf.triggered.connect(self.action_export_3mf)
        file_menu.addAction(act_exp_3mf)

        act_exp_svg = QAction("Export Optimized SVG (.svg)...", self)
        act_exp_svg.triggered.connect(self.action_export_optimized_svg)
        file_menu.addAction(act_exp_svg)

        file_menu.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        act_undo = self.undo_stack.createUndoAction(self, "Undo")
        act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(act_undo)

        act_redo = self.undo_stack.createRedoAction(self, "Redo")
        act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(act_redo)

        edit_menu.addSeparator()
        act_center = QAction("Center on Plate", self)
        act_center.setToolTip("Center drawing on the 180×180 mm build plate")
        act_center.triggered.connect(self.action_center_on_plate)
        edit_menu.addAction(act_center)

        act_origin = QAction("Align to Safe Origin", self)
        act_origin.setToolTip("Align drawing to bottom-left safe area origin (15, 15 mm)")
        act_origin.triggered.connect(self.action_align_safe_origin)
        edit_menu.addAction(act_origin)

        act_fit_safe = QAction("Fit to Safe Area", self)
        act_fit_safe.setToolTip("Scale and center drawing to fit inside safe margins (150×150 mm)")
        act_fit_safe.triggered.connect(self.action_fit_to_safe_area)
        edit_menu.addAction(act_fit_safe)

        act_resize = QAction(make_icon("resize", size=14), "Resize Drawing...", self)
        act_resize.setShortcut(QKeySequence("Ctrl+R"))
        act_resize.setToolTip("Open comprehensive drawing resize & scaling dialog [Ctrl+R]")
        act_resize.triggered.connect(self.action_open_resize_dialog)
        edit_menu.addAction(act_resize)

        edit_menu.addSeparator()
        act_settings = QAction("Settings...", self)
        act_settings.setShortcut(QKeySequence.StandardKey.Preferences)
        act_settings.triggered.connect(self.action_open_settings)
        edit_menu.addAction(act_settings)

        # Machine & Pen Menu
        machine_menu = menubar.addMenu("&Machine && Pen")
        act_cal = QAction("Pen Calibration Wizard (6 Steps)...", self)
        act_cal.triggered.connect(self.action_open_calibration_wizard)
        machine_menu.addAction(act_cal)

        act_val = QAction("Safety Validation & G-Code Inspector...", self)
        act_val.triggered.connect(lambda: self.action_open_validation_inspector(0))
        machine_menu.addAction(act_val)

    def _build_central_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Top Toolbar
        root_layout.addWidget(self._build_top_toolbar())

        # 2. Main 3-Column Splitter (Left Sidebar | Central Workspace + Simulator | Right Inspector)
        splitter = QSplitter(Qt.Orientation.Horizontal, root)
        splitter.setChildrenCollapsible(False)

        self.left_sidebar = LeftSidebar(self.profile_manager, splitter)
        splitter.addWidget(self.left_sidebar)

        # Center area: Build Plate Canvas + Bottom Simulator Control Bar
        center_container = QWidget(splitter)
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.canvas = BuildPlateCanvas(center_container)
        center_layout.addWidget(self.canvas, 1)

        self.simulator_bar = SimulatorControlBar(center_container)
        center_layout.addWidget(self.simulator_bar)

        splitter.addWidget(center_container)

        self.right_inspector = RightInspectorPanel(splitter)
        splitter.addWidget(self.right_inspector)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([335, 810, 315])

        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

        # Wire Signals
        self._connect_signals()

    def _build_top_toolbar(self) -> QFrame:
        bar = QFrame(self)
        bar.setObjectName("TopToolbar")
        bar.setFixedHeight(50)

        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(12, 6, 12, 6)
        hbox.setSpacing(8)

        # Brand Logo & Application Name
        logo_lbl = QLabel(bar)
        logo_path = Path(__file__).resolve().parent.parent / "resources" / "icon.png"
        if logo_path.exists():
            pix = QIcon(str(logo_path)).pixmap(QSize(26, 26))
            logo_lbl.setPixmap(pix)
        hbox.addWidget(logo_lbl)

        title_lbl = QLabel(__app_name__, bar)
        title_lbl.setObjectName("AppTitleLabel")
        hbox.addWidget(title_lbl)

        badge_lbl = QLabel("A1 MINI 180×180", bar)
        badge_lbl.setObjectName("AppBadgeLabel")
        hbox.addWidget(badge_lbl)

        hbox.addSpacing(10)

        # Action Buttons
        btn_new = QPushButton("New Project", bar)
        btn_new.setIcon(make_icon("file_plus", size=15))
        btn_new.clicked.connect(self.action_new_project)
        hbox.addWidget(btn_new)

        btn_open_svg = QPushButton("Open SVG", bar)
        btn_open_svg.setIcon(make_icon("folder_open", "#22C55E", size=15))
        btn_open_svg.clicked.connect(self.action_open_svg)
        hbox.addWidget(btn_open_svg)

        btn_save = QPushButton("Save Project", bar)
        btn_save.setIcon(make_icon("save", size=15))
        btn_save.clicked.connect(self.action_save_project)
        hbox.addWidget(btn_save)

        sep1 = QFrame(bar)
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #2B313B;")
        hbox.addWidget(sep1)

        self.btn_undo = QToolButton(bar)
        self.btn_undo.setIcon(make_icon("undo", size=15))
        self.btn_undo.setToolTip("Undo (Ctrl+Z)")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo_stack.undo)
        self.undo_stack.canUndoChanged.connect(self.btn_undo.setEnabled)
        hbox.addWidget(self.btn_undo)

        self.btn_redo = QToolButton(bar)
        self.btn_redo.setIcon(make_icon("redo", size=15))
        self.btn_redo.setToolTip("Redo (Ctrl+Y)")
        self.btn_redo.setEnabled(False)
        self.btn_redo.clicked.connect(self.undo_stack.redo)
        self.undo_stack.canRedoChanged.connect(self.btn_redo.setEnabled)
        hbox.addWidget(self.btn_redo)

        hbox.addStretch(1)

        # Calibration & Safety Status Buttons
        btn_cal = QPushButton("Pen Calibration", bar)
        btn_cal.setIcon(make_icon("wand", "#38BDF8", size=15))
        btn_cal.clicked.connect(self.action_open_calibration_wizard)
        hbox.addWidget(btn_cal)

        self.btn_safety_badge = QPushButton("Safety: Valid", bar)
        self.btn_safety_badge.setIcon(make_icon("shield_check", "#22C55E", size=15))
        self.btn_safety_badge.clicked.connect(lambda: self.action_open_validation_inspector(0))
        hbox.addWidget(self.btn_safety_badge)

        # Primary Export Button with Dropdown Menu
        btn_export = QPushButton("Export G-Code", bar)
        btn_export.setObjectName("PrimaryButton")
        btn_export.setIcon(make_icon("export", "#09110B", size=15))
        export_menu = QMenu(btn_export)
        export_menu.addAction("Export Plotter G-Code (.gcode)...", self.action_export_gcode)
        export_menu.addAction("Export Bambu Studio Package (.gcode.3mf)...", self.action_export_3mf)
        export_menu.addSeparator()
        export_menu.addAction("Export Optimized SVG (.svg)...", self.action_export_optimized_svg)
        export_menu.addAction("Export Safety Validation Report (.md)...", self.action_export_report)
        export_menu.addAction("Export Build Plate Preview (.png)...", self.action_export_preview_png)
        btn_export.setMenu(export_menu)
        hbox.addWidget(btn_export)

        btn_settings = QPushButton("Settings", bar)
        btn_settings.setIcon(make_icon("settings", size=15))
        btn_settings.clicked.connect(self.action_open_settings)
        hbox.addWidget(btn_settings)

        return bar

    def _build_status_bar(self) -> None:
        sb = QStatusBar(self)
        self.setStatusBar(sb)

        self.lbl_st_status = QLabel("Ready", sb)
        self.lbl_st_status.setObjectName("StatusLabel")
        sb.addWidget(self.lbl_st_status)

        self.lbl_st_dims = QLabel("  |  Dimensions: 0.0 × 0.0 mm", sb)
        self.lbl_st_dims.setObjectName("MonoValueLabel")
        sb.addWidget(self.lbl_st_dims)

        self.lbl_st_paths = QLabel("  |  Paths: 0", sb)
        self.lbl_st_paths.setObjectName("MonoValueLabel")
        sb.addWidget(self.lbl_st_paths)

        self.lbl_st_moves = QLabel("  |  Movements: 0", sb)
        self.lbl_st_moves.setObjectName("MonoValueLabel")
        sb.addWidget(self.lbl_st_moves)

        self.lbl_st_dist = QLabel("  |  Travel: 0.0 mm  Draw: 0.0 mm", sb)
        self.lbl_st_dist.setObjectName("MonoValueLabel")
        sb.addWidget(self.lbl_st_dist)

        self.lbl_st_time = QLabel("  |  Est. Time: 00:00", sb)
        self.lbl_st_time.setObjectName("MonoValueLabel")
        sb.addWidget(self.lbl_st_time)

        self.lbl_st_valid = QLabel("  |  Validation: VALID", sb)
        self.lbl_st_valid.setStyleSheet("color: #4ADE80; font-weight: 700;")
        sb.addPermanentWidget(self.lbl_st_valid)

        self.lbl_st_machine = QLabel("  |  Machine: Bambu Lab A1 Mini", sb)
        self.lbl_st_machine.setObjectName("MutedLabel")
        sb.addPermanentWidget(self.lbl_st_machine)

    def _connect_signals(self) -> None:
        # Left Sidebar signals
        self.left_sidebar.open_svg_requested.connect(self.action_open_svg)
        self.left_sidebar.load_example_requested.connect(lambda p: self.load_svg_file(p, mark_dirty=True))
        self.left_sidebar.element_visibility_changed.connect(self._on_element_visibility_changed)
        self.left_sidebar.element_selection_changed.connect(self._on_element_selected)
        self.left_sidebar.machine_profile_changed.connect(self._on_machine_changed)
        self.left_sidebar.pen_profile_changed.connect(self._on_pen_changed)
        self.left_sidebar.calibration_wizard_requested.connect(self.action_open_calibration_wizard)
        self.left_sidebar.workflow_mode_changed.connect(self._on_workflow_mode_changed)
        self.left_sidebar.air_draw_changed.connect(self._on_air_draw_changed)
        self.left_sidebar.export_gcode_requested.connect(self.action_export_gcode)
        self.left_sidebar.export_3mf_requested.connect(self.action_export_3mf)
        self.left_sidebar.export_svg_requested.connect(self.action_export_optimized_svg)
        self.left_sidebar.export_report_requested.connect(self.action_export_report)
        self.left_sidebar.export_preview_requested.connect(self.action_export_preview_png)
        self.left_sidebar.inspect_safety_requested.connect(lambda: self.action_open_validation_inspector(0))

        # Right Inspector signals
        self.right_inspector.transform_changed.connect(self._on_inspector_transform_changed)
        self.right_inspector.center_on_plate_requested.connect(self.action_center_on_plate)
        self.right_inspector.align_origin_requested.connect(self.action_align_safe_origin)
        self.right_inspector.fit_to_safe_area_requested.connect(self.action_fit_to_safe_area)
        self.right_inspector.resize_requested.connect(self.action_open_resize_dialog)
        self.right_inspector.fill_settings_changed.connect(self._on_fill_settings_changed)
        self.right_inspector.optimization_settings_changed.connect(self._on_optimization_settings_changed)
        self.right_inspector.coordinate_flags_changed.connect(self._on_coordinate_flags_changed)

        # Canvas signals
        self.canvas.transform_preview_changed.connect(self._on_canvas_transform_preview)
        self.canvas.transform_dragged.connect(self._on_canvas_transform_dragged)

        # Simulator signals
        self.simulator_bar.simulation_updated.connect(self.canvas.set_simulation_state)
        self.simulator_bar.inspect_gcode_requested.connect(lambda: self.action_open_validation_inspector(1))

    # ==========================================================================
    # Core Pipeline: Parse SVG -> Transform -> Generate Toolpath -> G-Code -> Validate
    # ==========================================================================

    def load_svg_file(self, file_path: str, mark_dirty: bool = True) -> None:
        try:
            precision = self.project.optimization_settings.curve_precision_mm
            parser = SvgParser(curve_precision_mm=precision)
            doc = parser.parse_file(file_path)
            self.project.svg_document = doc
            self.project.name = Path(file_path).stem
            self.project.dirty = mark_dirty
            self.undo_stack.clear()

            # Position cleanly inside safe area by default unless negative coordinates test SVG
            native_b = doc.compute_native_bounds()
            if native_b.min_x < 0 or native_b.min_y < 0:
                self.project.doc_transform = DocumentTransform(
                    pos_x_mm=max(self.project.machine_profile.usable_min_x, 20.0),
                    pos_y_mm=max(self.project.machine_profile.usable_min_y, 20.0),
                )
            else:
                # Center on plate if fits, else place at safe origin
                m = self.project.machine_profile
                cx = max(m.usable_min_x, (m.nominal_x_mm - native_b.width) * 0.5)
                cy = max(m.usable_min_y, (m.nominal_y_mm - native_b.height) * 0.5)
                self.project.doc_transform = DocumentTransform(
                    pos_x_mm=round(cx, 2),
                    pos_y_mm=round(cy, 2),
                )

            self.left_sidebar.populate_svg_document(doc)
            if any(w.severity == "critical" for w in doc.warnings):
                crit = next(w for w in doc.warnings if w.severity == "critical")
                self.lbl_st_status.setText(f"SVG Warning: {crit.message}")
            self.recompute_pipeline()
        except Exception as exc:
            logger.exception("Failed to load SVG file: %s", file_path)
            self.lbl_st_status.setText(f"SVG Error: {exc}")
            if not self.synchronous_pipeline:
                QMessageBox.critical(self, "SVG Import Error", f"Failed to parse SVG file:\n{file_path}\n\n{exc}")

    def recompute_pipeline(self, synchronous: Optional[bool] = None) -> None:
        """Runs the complete geometric transformation, toolpath optimization, G-code generation,

        and safety validation in a background QThreadPool worker to ensure the UI stays at 60 FPS.
        """
        doc = self.project.svg_document
        machine = self.project.machine_profile
        pen = self.project.pen_profile

        if doc is None:
            self.project.toolpath_moves = []
            self.current_stats = ToolpathStats()
            self.current_gcode = ""
            self.current_drawing_bounds = BoundingBox(0, 0, 0, 0)
            self.current_validation = SafetyValidator(machine, pen).validate([], "")
            self._update_all_views([])
            return

        is_sync = self.synchronous_pipeline if synchronous is None else synchronous

        self._pipeline_task_id += 1
        current_id = self._pipeline_task_id

        if self._active_worker is not None:
            self._active_worker.cancel()

        self.lbl_st_status.setText("Processing Toolpaths...")

        worker = PipelineWorker(
            task_id=current_id,
            doc=doc,
            doc_transform=self.project.doc_transform,
            machine=machine,
            pen=pen,
            opt_settings=self.project.optimization_settings,
            fill_settings=self.project.fill_settings,
            workflow_mode=self.project.workflow_mode,
            invert_y=self.project.invert_y,
            normalize_origin=self.project.normalize_origin,
            air_draw_mode=self.project.air_draw_mode,
            air_draw_offset_z_mm=self.project.air_draw_offset_z_mm,
            project_name=self.project.name,
        )
        self._active_worker = worker

        def on_completed(task_id: int, res: dict) -> None:
            if task_id != self._pipeline_task_id:
                return  # Outdated result from older task, ignore
            self.project.toolpath_moves = res["moves"]
            self.current_stats = res["stats"]
            self.current_gcode = res["gcode"]
            self.current_validation = res["validation"]
            self.current_drawing_bounds = res["drawing_bounds"]
            self._update_all_views(res["transformed_elements"])
            self._active_worker = None

        def on_error(task_id: int, err_msg: str) -> None:
            if task_id != self._pipeline_task_id:
                return
            logger.error("Background pipeline error: %s", err_msg)
            self.lbl_st_status.setText("Calculation Error")
            self._active_worker = None

        worker.signals.completed.connect(on_completed)
        worker.signals.error.connect(on_error)

        if is_sync:
            worker.run()
        else:
            self.thread_pool.start(worker)

    def _update_all_views(self, transformed_elements: list) -> None:
        doc = self.project.svg_document
        native_b = doc.compute_native_bounds() if doc else None

        self.canvas.update_workspace_data(
            machine=self.project.machine_profile,
            pen=self.project.pen_profile,
            svg_doc=doc,
            doc_transform=self.project.doc_transform,
            transformed_elements=transformed_elements,
            drawing_bounds=self.current_drawing_bounds,
            moves=self.project.toolpath_moves,
        )
        self.simulator_bar.load_moves(
            self.project.toolpath_moves,
            initial_z=self.project.pen_profile.pen_up_z_mm,
        )
        self.right_inspector.sync_from_state(
            doc_transform=self.project.doc_transform,
            drawing_bounds=self.current_drawing_bounds,
            stats=self.current_stats,
            pen=self.project.pen_profile,
            native_bounds=native_b,
        )
        self._update_status_and_safety_badges()

    def _update_status_and_safety_badges(self) -> None:
        self.lbl_st_status.setText("Ready")
        st = self.current_stats
        rep = self.current_validation

        self.lbl_st_dims.setText(f"Dimensions: {st.drawing_width_mm:.2f} × {st.drawing_height_mm:.2f} mm")
        self.lbl_st_paths.setText(f"  |  Paths: {st.num_paths}")
        self.lbl_st_moves.setText(f"  |  Movements: {st.num_movements}")
        self.lbl_st_dist.setText(
            f"  |  Draw: {st.drawing_distance_mm:.1f} mm  Travel: {st.travel_distance_mm:.1f} mm"
        )
        mins, secs = divmod(int(round(st.estimated_time_seconds)), 60)
        self.lbl_st_time.setText(f"  |  Est. Time: {mins:02d}:{secs:02d}")
        self.lbl_st_machine.setText(f"  |  Machine: {self.project.machine_profile.name}")

        if rep.overall_status == ValidationSeverity.CRITICAL:
            self.lbl_st_valid.setText(f"  |  Validation: CRITICAL ERROR ({rep.critical_count})")
            self.lbl_st_valid.setStyleSheet("color: #EF4444; font-weight: 700;")
            self.btn_safety_badge.setText(f"Safety: {rep.critical_count} Critical")
            self.btn_safety_badge.setIcon(make_icon("shield_alert", "#EF4444", size=15))
            self.btn_safety_badge.setStyleSheet("border-color: #EF4444; color: #FCA5A5;")
        elif rep.overall_status == ValidationSeverity.WARNING:
            self.lbl_st_valid.setText(f"  |  Validation: WARNING ({rep.warning_count})")
            self.lbl_st_valid.setStyleSheet("color: #F59E0B; font-weight: 700;")
            self.btn_safety_badge.setText(f"Safety: {rep.warning_count} Warning(s)")
            self.btn_safety_badge.setIcon(make_icon("shield_alert", "#F59E0B", size=15))
            self.btn_safety_badge.setStyleSheet("border-color: #F59E0B; color: #FDE68A;")
        else:
            self.lbl_st_valid.setText("  |  Validation: VALID")
            self.lbl_st_valid.setStyleSheet("color: #4ADE80; font-weight: 700;")
            self.btn_safety_badge.setText("Safety: Valid")
            self.btn_safety_badge.setIcon(make_icon("shield_check", "#22C55E", size=15))
            self.btn_safety_badge.setStyleSheet("")

    # ==========================================================================
    # Event Handlers & Undoable Transform Commands
    # ==========================================================================

    def _apply_transform_direct(self, new_t: DocumentTransform) -> None:
        self.project.doc_transform = DocumentTransform.from_dict(new_t.to_dict())
        self.project.dirty = True
        self.recompute_pipeline()

    def _on_canvas_transform_preview(self, new_t: DocumentTransform) -> None:
        self.project.doc_transform.pos_x_mm = new_t.pos_x_mm
        self.project.doc_transform.pos_y_mm = new_t.pos_y_mm
        self.right_inspector.update_position_preview(new_t.pos_x_mm, new_t.pos_y_mm)

    def _on_inspector_transform_changed(self, new_t: DocumentTransform) -> None:
        old_t = DocumentTransform.from_dict(self.project.doc_transform.to_dict())
        cmd = TransformChangeCommand(old_t, new_t, self._apply_transform_direct, "Modify Transform")
        self.undo_stack.push(cmd)

    def _on_canvas_transform_dragged(self, old_t: DocumentTransform, new_t: DocumentTransform) -> None:
        cmd = TransformChangeCommand(old_t, new_t, self._apply_transform_direct, "Move Drawing")
        self.undo_stack.push(cmd)

    def action_center_on_plate(self) -> None:
        if not self.current_drawing_bounds.is_valid:
            return
        m = self.project.machine_profile
        new_t = DocumentTransform.from_dict(self.project.doc_transform.to_dict())
        new_t.pos_x_mm = round((m.nominal_x_mm - self.current_drawing_bounds.width) * 0.5, 2)
        new_t.pos_y_mm = round((m.nominal_y_mm - self.current_drawing_bounds.height) * 0.5, 2)
        self._on_inspector_transform_changed(new_t)

    def action_align_safe_origin(self) -> None:
        m = self.project.machine_profile
        new_t = DocumentTransform.from_dict(self.project.doc_transform.to_dict())
        new_t.pos_x_mm = round(m.usable_min_x, 2)
        new_t.pos_y_mm = round(m.usable_min_y, 2)
        self._on_inspector_transform_changed(new_t)

    def action_fit_to_safe_area(self) -> None:
        doc = self.project.svg_document
        if doc is None:
            return
        nb = doc.compute_native_bounds()
        if nb.width <= 1e-4 or nb.height <= 1e-4:
            return
        m = self.project.machine_profile
        pad = 2.0
        avail_w = max(10.0, m.usable_width_mm - 2 * pad)
        avail_h = max(10.0, m.usable_height_mm - 2 * pad)
        scale = min(avail_w / nb.width, avail_h / nb.height)
        new_w = nb.width * scale
        new_h = nb.height * scale
        new_t = DocumentTransform.from_dict(self.project.doc_transform.to_dict())
        new_t.scale_x = round(scale, 4)
        new_t.scale_y = round(scale, 4)
        new_t.pos_x_mm = round(m.usable_min_x + (m.usable_width_mm - new_w) * 0.5, 2)
        new_t.pos_y_mm = round(m.usable_min_y + (m.usable_height_mm - new_h) * 0.5, 2)
        self._on_inspector_transform_changed(new_t)

    def action_open_resize_dialog(self) -> None:
        doc = self.project.svg_document
        if doc is None or not self.current_drawing_bounds.is_valid:
            QMessageBox.information(
                self,
                "No Drawing Loaded",
                "Please open or import an SVG drawing before resizing.",
            )
            return

        nb = doc.compute_native_bounds()
        if nb.width <= 1e-4 or nb.height <= 1e-4:
            QMessageBox.warning(
                self,
                "Invalid Bounds",
                "The current drawing has zero or invalid dimensions and cannot be resized.",
            )
            return

        dlg = ResizeDrawingDialog(
            current_bounds=self.current_drawing_bounds,
            native_bounds=nb,
            current_transform=self.project.doc_transform,
            machine=self.project.machine_profile,
            parent=self,
        )
        if dlg.exec():
            new_t = dlg.result_transform()
            self._on_inspector_transform_changed(new_t)
            self.statusBar().showMessage(
                f"Resized drawing to {dlg.target_width:.1f} × {dlg.target_height:.1f} mm",
                4000,
            )

    def _on_element_visibility_changed(self) -> None:
        self.left_sidebar.sync_visibility_to_document(self.project.svg_document)
        self.project.dirty = True
        self.recompute_pipeline()

    def _on_element_selected(self, element_id: str) -> None:
        self.canvas.selected_element_id = element_id
        self.canvas.update()

    def _on_machine_changed(self, machine: MachineProfile) -> None:
        self.project.machine_profile = machine
        self.project.dirty = True
        self.recompute_pipeline()

    def _on_pen_changed(self, pen: PenProfile) -> None:
        self.project.pen_profile = pen
        self.project.dirty = True
        self.recompute_pipeline()

    def _on_workflow_mode_changed(self, mode: WorkflowMode) -> None:
        self.project.workflow_mode = mode
        self.project.dirty = True
        self.recompute_pipeline()

    def _on_air_draw_changed(self, is_air_draw: bool, offset_z: float) -> None:
        self.project.air_draw_mode = is_air_draw
        self.project.air_draw_offset_z_mm = offset_z
        self.project.dirty = True
        self.recompute_pipeline()

    def _on_fill_settings_changed(self, fill_settings: FillSettings) -> None:
        self.project.fill_settings = fill_settings
        self.project.dirty = True
        self.recompute_pipeline()

    def _on_optimization_settings_changed(self, opt_settings: OptimizationSettings) -> None:
        self.project.optimization_settings = opt_settings
        self.project.dirty = True
        self.recompute_pipeline()

    def _on_coordinate_flags_changed(self, invert_y: bool, normalize_origin: bool) -> None:
        self.project.invert_y = invert_y
        self.project.normalize_origin = normalize_origin
        self.project.dirty = True
        self.recompute_pipeline()

    # ==========================================================================
    # Top-Level Actions: Project Management, Exports, Dialogs
    # ==========================================================================

    def action_new_project(self) -> None:
        self.project = PlotterProject(
            machine_profile=self.left_sidebar.current_machine_profile(),
            pen_profile=self.left_sidebar.current_pen_profile(),
        )
        self.undo_stack.clear()
        self.left_sidebar.populate_svg_document(None)
        self.recompute_pipeline()

    def action_open_svg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SVG File",
            "",
            "SVG Vector Drawings (*.svg);;All Files (*.*)",
        )
        if path:
            self.load_svg_file(path, mark_dirty=True)

    def action_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open A1 Mini Pen Plotter Project",
            "",
            "A1 Plotter Project (*.a1plot *.json);;All Files (*.*)",
        )
        if path:
            self._load_project_from_path(path)

    def _load_project_from_path(self, path: str) -> None:
        try:
            proj = self.project_manager.load_project(path)
            self.project = proj
            self.undo_stack.clear()
            self.left_sidebar.populate_svg_document(proj.svg_document)
            self.recompute_pipeline()
            self._rebuild_recent_menu()
        except Exception as exc:
            QMessageBox.critical(self, "Project Load Error", f"Could not open project file:\n{path}\n\n{exc}")

    def action_save_project(self) -> None:
        if self.project.file_path:
            self.project_manager.save_project(self.project, self.project.file_path)
            self._rebuild_recent_menu()
            self.statusBar().showMessage(f"Saved project to {self.project.file_path}", 4000)
        else:
            self.action_save_project_as()

    def action_save_project_as(self) -> None:
        default_name = f"{self.project.name}.a1plot"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            default_name,
            "A1 Plotter Project (*.a1plot);;JSON Files (*.json)",
        )
        if path:
            self.project_manager.save_project(self.project, path)
            self._rebuild_recent_menu()
            self.statusBar().showMessage(f"Saved project to {path}", 4000)

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        recents = self.project_manager.get_recent_projects()
        if not recents:
            act = self.recent_menu.addAction("No recent projects")
            act.setEnabled(False)
            return
        for r_path in recents:
            act = self.recent_menu.addAction(r_path)
            act.triggered.connect(lambda checked=False, p=r_path: self._load_project_from_path(p))

    def _check_calibration_before_export(self) -> bool:
        """Enforces Requirement 7: Block direct executable export if pen profile is uncalibrated."""
        if not self.project.pen_profile.is_calibrated and not self.project.air_draw_mode:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Export Blocked — Uncalibrated Pen Profile")
            box.setText(
                f"Pen profile '{self.project.pen_profile.name}' uses unverified default Z heights.\n\n"
                f"Current values (Drawing Z = {self.project.pen_profile.drawing_z_mm:.2f} mm, "
                f"Pen-Up Z = {self.project.pen_profile.pen_up_z_mm:.2f} mm) are theoretical presumptions "
                "and have NOT been physically calibrated on your Bambu Lab A1 Mini.\n\n"
                "Plotting with unverified Z risks driving the toolhead into the bed or crushing the pen tip.\n\n"
                "Please run the Pen Calibration Wizard to find real physical contact, "
                "or enable Air Draw Mode (+15 mm) to safely dry-run in the air."
            )
            btn_wizard = box.addButton("Launch Calibration Wizard...", QMessageBox.ButtonRole.ActionRole)
            btn_air = box.addButton("Enable Air Draw Mode (+15 mm)", QMessageBox.ButtonRole.ActionRole)
            btn_cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.exec()

            if box.clickedButton() == btn_wizard:
                self.action_open_calibration_wizard()
            elif box.clickedButton() == btn_air:
                self.project.air_draw_mode = True
                self.left_sidebar.chk_air_draw.setChecked(True)
                self.recompute_pipeline()
            return False
        return True

    def action_export_gcode(self) -> None:
        if not self.project.toolpath_moves:
            QMessageBox.warning(self, "Nothing to Export", "Load an SVG drawing to generate toolpaths before exporting.")
            return

        if not self._check_calibration_before_export():
            return

        if not self.current_validation.can_export_executable:
            QMessageBox.critical(
                self,
                "Export Blocked by Safety Validator",
                f"Cannot export execution-ready G-code because {self.current_validation.critical_count} "
                "CRITICAL safety validation error(s) were detected.\n\n"
                "Review the exact coordinates and commands in the Safety Validation Inspector.",
            )
            self.action_open_validation_inspector(0)
            return

        default_dir = self.settings_manager.settings.default_export_folder
        default_file = str(Path(default_dir) / f"{self.project.name}.gcode") if default_dir else f"{self.project.name}.gcode"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Plotter G-Code (.gcode)",
            default_file,
            "G-Code Files (*.gcode);;All Files (*.*)",
        )
        if not path:
            return

        try:
            GcodeExporter.export_gcode_file(
                output_path=path,
                moves=self.project.toolpath_moves,
                gcode_text=self.current_gcode,
                machine=self.project.machine_profile,
                pen=self.project.pen_profile,
            )
            QMessageBox.information(
                self,
                "G-Code Export Successful",
                f"Exported validated plotter G-code to:\n{path}\n\n"
                f"Workflow Mode: {self.project.workflow_mode.value}\n"
                "Remember to verify physical pen clearance manually before starting the plot.",
            )
        except SafetyExportBlockedError as err:
            QMessageBox.critical(self, "Safety Validation Blocked Export", str(err))
            self.action_open_validation_inspector(0)

    def action_export_3mf(self) -> None:
        if not self.project.toolpath_moves:
            QMessageBox.warning(self, "Nothing to Export", "Load an SVG drawing before exporting a .gcode.3mf package.")
            return

        if not self._check_calibration_before_export():
            return

        if not self.current_validation.can_export_executable:
            QMessageBox.critical(
                self,
                "3MF Export Blocked by Safety Validator",
                f"Cannot export execution-ready .gcode.3mf because {self.current_validation.critical_count} "
                "CRITICAL safety validation error(s) were detected.",
            )
            self.action_open_validation_inspector(0)
            return

        default_dir = self.settings_manager.settings.default_export_folder
        default_file = (
            str(Path(default_dir) / f"{self.project.name}.gcode.3mf")
            if default_dir
            else f"{self.project.name}.gcode.3mf"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Bambu Studio Package (.gcode.3mf)",
            default_file,
            "Bambu Studio Sliced 3MF (*.gcode.3mf *.3mf)",
        )
        if not path:
            return

        try:
            GcodeExporter.export_bambu_3mf_file(
                output_path=path,
                moves=self.project.toolpath_moves,
                gcode_text=self.current_gcode,
                stats=self.current_stats,
                machine=self.project.machine_profile,
                pen=self.project.pen_profile,
            )
            QMessageBox.information(
                self,
                "Bambu 3MF Package Exported",
                f"Exported Bambu Studio compatible package to:\n{path}\n\n"
                "Contains Metadata/plate_1.gcode, MD5 checksum, slice_info.config, and plate preview thumbnail.",
            )
        except SafetyExportBlockedError as err:
            QMessageBox.critical(self, "Safety Validation Blocked Export", str(err))

    def action_export_optimized_svg(self) -> None:
        if not self.project.toolpath_moves:
            QMessageBox.warning(self, "Nothing to Export", "Load an SVG drawing before exporting an optimized SVG.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Optimized SVG",
            f"{self.project.name}_optimized.svg",
            "SVG Files (*.svg)",
        )
        if path:
            GcodeExporter.export_optimized_svg(
                path,
                self.project.toolpath_moves,
                self.project.machine_profile,
                self.project.pen_profile,
            )
            QMessageBox.information(self, "Optimized SVG Exported", f"Saved optimized SVG to:\n{path}")

    def action_export_report(self) -> None:
        if not self.project.toolpath_moves:
            QMessageBox.warning(self, "Nothing to Export", "Load an SVG drawing before exporting a safety validation report.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Safety Validation Report",
            f"{self.project.name}_validation_report.md",
            "Markdown Report (*.md);;JSON Report (*.json);;Text Report (*.txt)",
        )
        if path:
            GcodeExporter.export_validation_report(
                path,
                self.current_validation,
                self.project.machine_profile,
                self.project.pen_profile,
                self.current_stats,
            )
            QMessageBox.information(self, "Validation Report Exported", f"Saved validation report to:\n{path}")

    def action_export_preview_png(self) -> None:
        if not self.project.toolpath_moves:
            QMessageBox.warning(self, "Nothing to Export", "Load an SVG drawing before exporting a preview image.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Build Plate Preview Image",
            f"{self.project.name}_preview.png",
            "PNG Image (*.png)",
        )
        if path:
            GcodeExporter.export_preview_image(
                path,
                self.project.toolpath_moves,
                self.project.machine_profile,
            )
            QMessageBox.information(self, "Preview Image Exported", f"Saved preview image to:\n{path}")

    def action_open_calibration_wizard(self) -> None:
        dlg = PenCalibrationWizard(
            pen=self.project.pen_profile,
            machine=self.project.machine_profile,
            parent=self,
        )
        if dlg.exec():
            cal_pen = dlg.calibrated_pen()
            self.profile_manager.save_pen(cal_pen)
            self.project.pen_profile = cal_pen
            self.left_sidebar.refresh_profiles_ui(select_pen_id=cal_pen.id)
            self.recompute_pipeline()

    def action_open_validation_inspector(self, initial_tab: int = 0) -> None:
        dlg = ValidationAndGcodeDialog(
            report=self.current_validation,
            gcode_text=self.current_gcode,
            initial_tab=initial_tab,
            parent=self,
        )
        dlg.exec()

    def action_open_settings(self) -> None:
        dlg = SettingsDialog(
            settings=self.settings_manager.settings,
            profile_manager=self.profile_manager,
            parent=self,
        )
        if dlg.exec():
            self.settings_manager.save(dlg.settings)
            self.apply_settings(dlg.settings, initial=False)

    def apply_settings(self, settings: AppSettings, initial: bool = False) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(settings.theme))
        if not initial:
            self.canvas.show_grid = settings.show_grid
            self.canvas.show_rulers = settings.show_rulers
            self.canvas.grid_major_mm = settings.grid_major_mm
            self.canvas.grid_minor_mm = settings.grid_minor_mm
            self.canvas.btn_toggle_grid.setChecked(settings.show_grid)
            self.project.optimization_settings.curve_precision_mm = settings.curve_precision_mm
            self.autosave_timer.setInterval(max(15, settings.autosave_interval_sec) * 1000)
            self.recompute_pipeline()

    def _on_autosave_tick(self) -> None:
        if self.project.dirty and self.project.svg_document is not None:
            self.project_manager.write_autosave(self.project)

    def _prompt_crash_recovery(self) -> None:
        ans = QMessageBox.question(
            self,
            "Autosave Recovery Available",
            "An unsaved project session was found from a previous closure.\nWould you like to recover it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            rec = self.project_manager.load_recovery_project()
            if rec is not None:
                self.project = rec
                self.left_sidebar.populate_svg_document(rec.svg_document)
                self.recompute_pipeline()
        else:
            self.project_manager.clear_autosave()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._active_worker is not None:
            self._active_worker.cancel()
        if hasattr(self, "autosave_timer") and self.autosave_timer is not None:
            self.autosave_timer.stop()
        if hasattr(self, "simulator_bar") and self.simulator_bar is not None:
            self.simulator_bar.timer.stop()
        if hasattr(self, "thread_pool") and self.thread_pool is not None:
            self.thread_pool.waitForDone(300)
        self.project_manager.clear_autosave()
        super().closeEvent(event)
