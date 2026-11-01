"""Left Sidebar with tabs for Project & Layers, Machine Config, Pen Setup, and Export Settings."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import ParsedSvgDocument, WorkflowMode
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile, ProfileManager
from app.ui.icons import make_icon


class LeftSidebar(QFrame):
    """Left engineering sidebar containing Project/Elements/Layers, Machine, Pen, and Export configuration."""

    # Signals
    open_svg_requested = Signal()
    load_example_requested = Signal(str)
    element_visibility_changed = Signal()
    element_selection_changed = Signal(str)
    machine_profile_changed = Signal(MachineProfile)
    pen_profile_changed = Signal(PenProfile)
    calibration_wizard_requested = Signal()
    workflow_mode_changed = Signal(WorkflowMode)
    air_draw_changed = Signal(bool, float)  # (is_air_draw, offset_z_mm)
    export_gcode_requested = Signal()
    export_3mf_requested = Signal()
    export_svg_requested = Signal()
    export_report_requested = Signal()
    export_preview_requested = Signal()
    inspect_safety_requested = Signal()

    def __init__(self, profile_manager: ProfileManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarContainer")
        self.setMinimumWidth(340)
        self.setMaximumWidth(400)

        self.profile_manager = profile_manager
        self._updating_ui = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setUsesScrollButtons(False)

        self.tab_project = self._build_project_layers_tab()
        self.tab_machine = self._build_machine_tab()
        self.tab_pen = self._build_pen_tab()
        self.tab_export = self._build_export_tab()

        self.tabs.addTab(self.tab_project, make_icon("file_svg", size=15), "Project")
        self.tabs.addTab(self.tab_machine, make_icon("cpu", size=15), "Machine")
        self.tabs.addTab(self.tab_pen, make_icon("pen_tool", size=15), "Pen")
        self.tabs.addTab(self.tab_export, make_icon("export", size=15), "Export")

        layout.addWidget(self.tabs)

        self.refresh_profiles_ui()

    # ==========================================================================
    # Tab 1: Project, SVG Elements & Layers
    # ==========================================================================

    def _build_project_layers_tab(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(6, 8, 6, 6)
        vbox.setSpacing(8)

        # Quick Load Sample SVG Card
        card_proj = QFrame(page)
        card_proj.setObjectName("SectionCard")
        cp_layout = QVBoxLayout(card_proj)
        cp_layout.setContentsMargins(10, 8, 10, 8)
        cp_layout.setSpacing(6)

        lbl_p = QLabel("PROJECT & SAMPLE LIBRARY", card_proj)
        lbl_p.setObjectName("SectionHeader")
        cp_layout.addWidget(lbl_p)

        self.lbl_svg_info = QLabel("No SVG file loaded", card_proj)
        self.lbl_svg_info.setObjectName("MutedLabel")
        self.lbl_svg_info.setWordWrap(True)
        cp_layout.addWidget(self.lbl_svg_info)

        row_sample = QHBoxLayout()
        self.cmb_examples = QComboBox(card_proj)
        self.cmb_examples.setToolTip("Load a built-in test or calibration SVG")
        examples_dir = Path(__file__).resolve().parent.parent.parent.parent / "examples"
        if examples_dir.exists():
            for f in sorted(examples_dir.glob("*.svg")):
                self.cmb_examples.addItem(f.stem.replace("_", " "), str(f))
        row_sample.addWidget(self.cmb_examples, 1)

        btn_load_sample = QPushButton("Load", card_proj)
        btn_load_sample.setToolTip("Load selected sample SVG into the workspace")
        btn_load_sample.clicked.connect(self._on_load_sample_clicked)
        row_sample.addWidget(btn_load_sample)
        cp_layout.addLayout(row_sample)

        btn_open_custom = QPushButton("Open SVG File...", card_proj)
        btn_open_custom.setIcon(make_icon("folder_open", "#22C55E", size=14))
        btn_open_custom.setToolTip("Open a custom SVG vector drawing from your computer")
        btn_open_custom.clicked.connect(self.open_svg_requested.emit)
        cp_layout.addWidget(btn_open_custom)

        vbox.addWidget(card_proj)

        # Layers & SVG Elements Tree
        card_tree = QFrame(page)
        card_tree.setObjectName("SectionCard")
        ct_layout = QVBoxLayout(card_tree)
        ct_layout.setContentsMargins(10, 8, 10, 8)
        ct_layout.setSpacing(6)

        hdr_row = QHBoxLayout()
        lbl_layers = QLabel("LAYERS & ELEMENTS", card_tree)
        lbl_layers.setObjectName("SectionHeader")
        hdr_row.addWidget(lbl_layers)
        hdr_row.addStretch(1)

        btn_all_on = QPushButton("All On", card_tree)
        btn_all_on.setFixedHeight(22)
        btn_all_on.clicked.connect(lambda: self._set_all_elements_visible(True))
        hdr_row.addWidget(btn_all_on)

        btn_all_off = QPushButton("All Off", card_tree)
        btn_all_off.setFixedHeight(22)
        btn_all_off.clicked.connect(lambda: self._set_all_elements_visible(False))
        hdr_row.addWidget(btn_all_off)
        ct_layout.addLayout(hdr_row)

        self.tree_elements = QTreeWidget(card_tree)
        self.tree_elements.setHeaderLabels(["Layer / Element", "Type", "Pts"])
        self.tree_elements.setColumnWidth(0, 155)
        self.tree_elements.setColumnWidth(1, 55)
        self.tree_elements.setColumnWidth(2, 40)
        self.tree_elements.itemChanged.connect(self._on_tree_item_changed)
        self.tree_elements.itemSelectionChanged.connect(self._on_tree_selection_changed)
        ct_layout.addWidget(self.tree_elements, 1)

        vbox.addWidget(card_tree, 1)

        # SVG Parser Warnings / Notices Card
        card_warn = QFrame(page)
        card_warn.setObjectName("SectionCard")
        cw_layout = QVBoxLayout(card_warn)
        cw_layout.setContentsMargins(10, 6, 10, 6)
        cw_layout.setSpacing(4)

        lbl_w = QLabel("IMPORT DIAGNOSTICS", card_warn)
        lbl_w.setObjectName("SectionHeader")
        cw_layout.addWidget(lbl_w)

        self.list_svg_warnings = QListWidget(card_warn)
        self.list_svg_warnings.setMaximumHeight(85)
        cw_layout.addWidget(self.list_svg_warnings)

        vbox.addWidget(card_warn)
        return page

    # ==========================================================================
    # Tab 2: Machine Configuration (Bambu Lab A1 Mini)
    # ==========================================================================

    def _build_machine_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(6, 8, 6, 8)
        vbox.setSpacing(8)

        # Machine Profile Selector Card
        card_sel = QFrame(content)
        card_sel.setObjectName("SectionCard")
        cs_layout = QVBoxLayout(card_sel)
        cs_layout.setContentsMargins(10, 8, 10, 8)
        cs_layout.setSpacing(6)

        lbl_m = QLabel("MACHINE PROFILE", card_sel)
        lbl_m.setObjectName("SectionHeader")
        cs_layout.addWidget(lbl_m)

        self.cmb_machine = QComboBox(card_sel)
        self.cmb_machine.currentIndexChanged.connect(self._on_machine_combo_changed)
        cs_layout.addWidget(self.cmb_machine)

        row_m_btns = QHBoxLayout()
        btn_dup_m = QPushButton("Duplicate", card_sel)
        btn_dup_m.clicked.connect(self._on_duplicate_machine)
        row_m_btns.addWidget(btn_dup_m)

        btn_ren_m = QPushButton("Rename", card_sel)
        btn_ren_m.clicked.connect(self._on_rename_machine)
        row_m_btns.addWidget(btn_ren_m)

        btn_del_m = QPushButton("Delete", card_sel)
        btn_del_m.setObjectName("DangerButton")
        btn_del_m.clicked.connect(self._on_delete_machine)
        row_m_btns.addWidget(btn_del_m)

        btn_save_m = QPushButton("Save Profile", card_sel)
        btn_save_m.setObjectName("PrimaryButton")
        btn_save_m.clicked.connect(self._on_save_machine)
        row_m_btns.addWidget(btn_save_m)
        cs_layout.addLayout(row_m_btns)
        vbox.addWidget(card_sel)

        # Workspace Dimensions & Safety Margins Card
        card_bounds = QFrame(content)
        card_bounds.setObjectName("SectionCard")
        form_b = QFormLayout(card_bounds)
        form_b.setContentsMargins(10, 8, 10, 8)
        form_b.setSpacing(6)

        lbl_b = QLabel("WORKSPACE & SAFETY MARGINS", card_bounds)
        lbl_b.setObjectName("SectionHeader")
        form_b.addRow(lbl_b)

        self.spn_nom_x = self._make_dspin(50.0, 500.0, 180.0, " mm")
        self.spn_nom_y = self._make_dspin(50.0, 500.0, 180.0, " mm")
        self.spn_margin_left = self._make_dspin(0.0, 60.0, 10.0, " mm")
        self.spn_margin_right = self._make_dspin(0.0, 60.0, 10.0, " mm")
        self.spn_margin_front = self._make_dspin(0.0, 60.0, 10.0, " mm")
        self.spn_margin_back = self._make_dspin(0.0, 60.0, 10.0, " mm")

        form_b.addRow("Nominal X:", self.spn_nom_x)
        form_b.addRow("Nominal Y:", self.spn_nom_y)
        form_b.addRow("Left Margin:", self.spn_margin_left)
        form_b.addRow("Right Margin:", self.spn_margin_right)
        form_b.addRow("Front Margin:", self.spn_margin_front)
        form_b.addRow("Back Margin:", self.spn_margin_back)
        vbox.addWidget(card_bounds)

        # Origin, Offsets & Speed Limits Card
        card_limits = QFrame(content)
        card_limits.setObjectName("SectionCard")
        form_l = QFormLayout(card_limits)
        form_l.setContentsMargins(10, 8, 10, 8)
        form_l.setSpacing(6)

        lbl_lim = QLabel("OFFSETS, SAFE Z & SPEED LIMITS", card_limits)
        lbl_lim.setObjectName("SectionHeader")
        form_l.addRow(lbl_lim)

        self.cmb_origin = QComboBox(card_limits)
        self.cmb_origin.addItem("Front-Left (0, 0)", "front_left")
        self.cmb_origin.addItem("Center (90, 90)", "center")
        self.cmb_origin.addItem("Back-Left (0, 180)", "back_left")

        self.spn_coord_off_x = self._make_dspin(-100.0, 100.0, 0.0, " mm")
        self.spn_coord_off_y = self._make_dspin(-100.0, 100.0, 0.0, " mm")
        self.spn_holder_off_x = self._make_dspin(-80.0, 80.0, 0.0, " mm")
        self.spn_holder_off_y = self._make_dspin(-80.0, 80.0, -22.0, " mm")
        self.spn_safe_z = self._make_dspin(2.0, 175.0, 22.0, " mm")
        self.spn_min_safe_z = self._make_dspin(0.5, 50.0, 2.0, " mm")
        self.spn_max_travel = self._make_dspin(10.0, 500.0, 200.0, " mm/s")
        self.spn_max_draw = self._make_dspin(5.0, 300.0, 80.0, " mm/s")

        form_l.addRow("Origin Position:", self.cmb_origin)
        form_l.addRow("Coord Offset X:", self.spn_coord_off_x)
        form_l.addRow("Coord Offset Y:", self.spn_coord_off_y)
        form_l.addRow("Holder Offset X:", self.spn_holder_off_x)
        form_l.addRow("Holder Offset Y:", self.spn_holder_off_y)
        form_l.addRow("Safe Clear Z:", self.spn_safe_z)
        form_l.addRow("Min Safe Z:", self.spn_min_safe_z)
        form_l.addRow("Max Travel Spd:", self.spn_max_travel)
        form_l.addRow("Max Draw Spd:", self.spn_max_draw)

        for w in (
            self.spn_nom_x,
            self.spn_nom_y,
            self.spn_margin_left,
            self.spn_margin_right,
            self.spn_margin_front,
            self.spn_margin_back,
            self.spn_coord_off_x,
            self.spn_coord_off_y,
            self.spn_holder_off_x,
            self.spn_holder_off_y,
            self.spn_safe_z,
            self.spn_min_safe_z,
            self.spn_max_travel,
            self.spn_max_draw,
        ):
            w.valueChanged.connect(self._emit_machine_updated)
        self.cmb_origin.currentIndexChanged.connect(self._emit_machine_updated)

        vbox.addWidget(card_limits)
        vbox.addStretch(1)
        scroll.setWidget(content)
        return scroll

    # ==========================================================================
    # Tab 3: Pen Configuration & Calibration Wizard
    # ==========================================================================

    def _build_pen_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(6, 8, 6, 8)
        vbox.setSpacing(8)

        # Pen Profile CRUD Card
        card_pen = QFrame(content)
        card_pen.setObjectName("SectionCard")
        cp_layout = QVBoxLayout(card_pen)
        cp_layout.setContentsMargins(10, 8, 10, 8)
        cp_layout.setSpacing(6)

        lbl_p = QLabel("PEN PROFILE MANAGEMENT", card_pen)
        lbl_p.setObjectName("SectionHeader")
        cp_layout.addWidget(lbl_p)

        self.cmb_pen = QComboBox(card_pen)
        self.cmb_pen.currentIndexChanged.connect(self._on_pen_combo_changed)
        cp_layout.addWidget(self.cmb_pen)

        row1 = QHBoxLayout()
        btn_new_pen = QPushButton("New", card_pen)
        btn_new_pen.setIcon(make_icon("plus", size=14))
        btn_new_pen.clicked.connect(self._on_new_pen)
        row1.addWidget(btn_new_pen)

        btn_dup_pen = QPushButton("Duplicate", card_pen)
        btn_dup_pen.setIcon(make_icon("copy", size=14))
        btn_dup_pen.clicked.connect(self._on_duplicate_pen)
        row1.addWidget(btn_dup_pen)

        btn_ren_pen = QPushButton("Rename", card_pen)
        btn_ren_pen.clicked.connect(self._on_rename_pen)
        row1.addWidget(btn_ren_pen)

        btn_del_pen = QPushButton("Delete", card_pen)
        btn_del_pen.setObjectName("DangerButton")
        btn_del_pen.clicked.connect(self._on_delete_pen)
        row1.addWidget(btn_del_pen)
        cp_layout.addLayout(row1)

        btn_cal = QPushButton("Launch 6-Step Pen Calibration Wizard...", card_pen)
        btn_cal.setIcon(make_icon("wand", "#09110B", size=15))
        btn_cal.setObjectName("PrimaryButton")
        btn_cal.clicked.connect(self.calibration_wizard_requested.emit)
        cp_layout.addWidget(btn_cal)

        self.lbl_pen_cal_status = QLabel(card_pen)
        self.lbl_pen_cal_status.setWordWrap(True)
        cp_layout.addWidget(self.lbl_pen_cal_status)

        vbox.addWidget(card_pen)

        # Pen Z Heights & Offsets Card
        card_z = QFrame(content)
        card_z.setObjectName("SectionCard")
        form_z = QFormLayout(card_z)
        form_z.setContentsMargins(10, 8, 10, 8)
        form_z.setSpacing(6)

        lbl_z = QLabel("Z HEIGHTS & OFFSETS (NEVER ASSUME Z=0)", card_z)
        lbl_z.setObjectName("SectionHeader")
        form_z.addRow(lbl_z)

        self.spn_pen_up_z = self._make_dspin(1.0, 160.0, 18.0, " mm")
        self.spn_pen_down_z = self._make_dspin(0.5, 160.0, 14.2, " mm")
        self.spn_drawing_z = self._make_dspin(0.5, 160.0, 14.0, " mm")
        self.spn_lift_height = self._make_dspin(0.5, 50.0, 4.0, " mm")
        self.spn_pen_tip = self._make_dspin(0.05, 10.0, 0.4, " mm")
        self.spn_pen_off_x = self._make_dspin(-50.0, 50.0, 0.0, " mm")
        self.spn_pen_off_y = self._make_dspin(-50.0, 50.0, 0.0, " mm")

        form_z.addRow("Pen-Up Z:", self.spn_pen_up_z)
        form_z.addRow("Pen-Down Z:", self.spn_pen_down_z)
        form_z.addRow("Drawing Z:", self.spn_drawing_z)
        form_z.addRow("Lift Height:", self.spn_lift_height)
        form_z.addRow("Tip Diameter:", self.spn_pen_tip)
        form_z.addRow("Pen X Offset:", self.spn_pen_off_x)
        form_z.addRow("Pen Y Offset:", self.spn_pen_off_y)
        vbox.addWidget(card_z)

        # Pen Speeds & Stabilization Card
        card_spd = QFrame(content)
        card_spd.setObjectName("SectionCard")
        form_s = QFormLayout(card_spd)
        form_s.setContentsMargins(10, 8, 10, 8)
        form_s.setSpacing(6)

        lbl_s = QLabel("PEN SPEEDS & STABILIZATION", card_spd)
        lbl_s.setObjectName("SectionHeader")
        form_s.addRow(lbl_s)

        self.spn_draw_speed = self._make_dspin(1.0, 250.0, 35.0, " mm/s")
        self.spn_travel_speed = self._make_dspin(5.0, 400.0, 120.0, " mm/s")
        self.spn_z_speed = self._make_dspin(1.0, 60.0, 12.0, " mm/s")
        self.spn_dwell_ms = QSpinBox(card_spd)
        self.spn_dwell_ms.setRange(0, 2000)
        self.spn_dwell_ms.setSingleStep(10)
        self.spn_dwell_ms.setSuffix(" ms")
        self.spn_dwell_ms.setValue(60)

        form_s.addRow("Drawing Speed:", self.spn_draw_speed)
        form_s.addRow("Travel Speed:", self.spn_travel_speed)
        form_s.addRow("Z Move Speed:", self.spn_z_speed)
        form_s.addRow("Stabilization:", self.spn_dwell_ms)

        btn_save_pen = QPushButton("Save Pen Changes", card_spd)
        btn_save_pen.clicked.connect(self._on_save_current_pen)
        form_s.addRow(btn_save_pen)

        for w in (
            self.spn_pen_up_z,
            self.spn_pen_down_z,
            self.spn_drawing_z,
            self.spn_lift_height,
            self.spn_pen_tip,
            self.spn_pen_off_x,
            self.spn_pen_off_y,
            self.spn_draw_speed,
            self.spn_travel_speed,
            self.spn_z_speed,
        ):
            w.valueChanged.connect(self._emit_pen_updated)
        self.spn_dwell_ms.valueChanged.connect(self._emit_pen_updated)

        vbox.addWidget(card_spd)
        vbox.addStretch(1)
        scroll.setWidget(content)
        return scroll

    # ==========================================================================
    # Tab 4: Export Settings & Workflow Compatibility
    # ==========================================================================

    def _build_export_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(6, 8, 6, 8)
        vbox.setSpacing(8)

        card_wf = QFrame(content)
        card_wf.setObjectName("SectionCard")
        cw_layout = QVBoxLayout(card_wf)
        cw_layout.setContentsMargins(10, 8, 10, 8)
        cw_layout.setSpacing(6)

        lbl_wf = QLabel("EXECUTION WORKFLOW MODE", card_wf)
        lbl_wf.setObjectName("SectionHeader")
        cw_layout.addWidget(lbl_wf)

        self.cmb_workflow = QComboBox(card_wf)
        self.cmb_workflow.addItem(
            "A1 Mini Direct MicroSD Execution (.gcode)",
            WorkflowMode.BAMBU_SD_DIRECT.value,
        )
        self.cmb_workflow.addItem(
            "Bambu Studio Package (.gcode.3mf)",
            WorkflowMode.BAMBU_STUDIO_3MF.value,
        )
        self.cmb_workflow.addItem(
            "Standard Generic Plotter (.gcode)",
            WorkflowMode.STANDARD_GCODE.value,
        )
        self.cmb_workflow.currentIndexChanged.connect(self._on_workflow_combo_changed)
        cw_layout.addWidget(self.cmb_workflow)

        self.lbl_workflow_desc = QLabel(
            "Generates cold-plotting G-code (M104 S0, M140 S0, G28) for direct execution from the root of the A1 Mini MicroSD card.",
            card_wf,
        )
        self.lbl_workflow_desc.setObjectName("MutedLabel")
        self.lbl_workflow_desc.setWordWrap(True)
        cw_layout.addWidget(self.lbl_workflow_desc)

        # Test Mode / Air Draw Card
        card_air = QFrame(content)
        card_air.setObjectName("SectionCard")
        cair_layout = QVBoxLayout(card_air)
        cair_layout.setContentsMargins(10, 8, 10, 8)
        cair_layout.setSpacing(6)

        lbl_air = QLabel("SAFETY AIR DRAW / TEST MODE", card_air)
        lbl_air.setObjectName("SectionHeader")
        cair_layout.addWidget(lbl_air)

        self.chk_air_draw = QCheckBox("Enable Air Draw Mode (Test in the Air)", card_air)
        self.chk_air_draw.setToolTip("Adds a safety elevation offset (+15mm) to all pen movements to test trajectories before touching paper.")
        cair_layout.addWidget(self.chk_air_draw)

        form_air = QFormLayout()
        self.spn_air_offset_z = self._make_dspin(5.0, 50.0, 15.0, " mm")
        form_air.addRow("Air Z Offset:", self.spn_air_offset_z)
        cair_layout.addLayout(form_air)

        lbl_air_note = QLabel("Allows watching full toolpath execution in the air safely without any risk of pen crash.", card_air)
        lbl_air_note.setObjectName("MutedLabel")
        lbl_air_note.setWordWrap(True)
        cair_layout.addWidget(lbl_air_note)
        vbox.addWidget(card_air)

        # Export Actions Card
        card_exp = QFrame(content)
        card_exp.setObjectName("SectionCard")
        ce_layout = QVBoxLayout(card_exp)
        ce_layout.setContentsMargins(10, 8, 10, 8)
        ce_layout.setSpacing(6)

        lbl_e = QLabel("EXPORT DELIVERABLES", card_exp)
        lbl_e.setObjectName("SectionHeader")
        ce_layout.addWidget(lbl_e)

        btn_exp_gcode = QPushButton("Export Plotter G-Code (.gcode)...", card_exp)
        btn_exp_gcode.setObjectName("PrimaryButton")
        btn_exp_gcode.setIcon(make_icon("export", "#09110B", size=15))
        btn_exp_gcode.clicked.connect(self.export_gcode_requested.emit)
        ce_layout.addWidget(btn_exp_gcode)

        btn_exp_3mf = QPushButton("Export Bambu Studio Container (.gcode.3mf)...", card_exp)
        btn_exp_3mf.clicked.connect(self.export_3mf_requested.emit)
        ce_layout.addWidget(btn_exp_3mf)

        btn_exp_svg = QPushButton("Export Optimized SVG (.svg)...", card_exp)
        btn_exp_svg.clicked.connect(self.export_svg_requested.emit)
        ce_layout.addWidget(btn_exp_svg)

        btn_exp_rep = QPushButton("Export Safety Validation Report (.md / .json)...", card_exp)
        btn_exp_rep.clicked.connect(self.export_report_requested.emit)
        ce_layout.addWidget(btn_exp_rep)

        btn_exp_png = QPushButton("Export Build Plate Preview Image (.png)...", card_exp)
        btn_exp_png.clicked.connect(self.export_preview_requested.emit)
        ce_layout.addWidget(btn_exp_png)

        btn_safety = QPushButton("Inspect Safety Validation Details...", card_exp)
        btn_safety.setIcon(make_icon("shield_check", "#22C55E", size=15))
        btn_safety.clicked.connect(self.inspect_safety_requested.emit)
        ce_layout.addWidget(btn_safety)

        self.chk_air_draw.toggled.connect(self._on_air_draw_changed)
        self.spn_air_offset_z.valueChanged.connect(self._on_air_draw_changed)

        vbox.addWidget(card_exp)
        vbox.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _on_air_draw_changed(self) -> None:
        self.air_draw_changed.emit(self.chk_air_draw.isChecked(), self.spn_air_offset_z.value())

    # ==========================================================================
    # Helper & Event Methods
    # ==========================================================================

    def _make_dspin(self, min_v: float, max_v: float, val: float, suffix: str) -> QDoubleSpinBox:
        spn = QDoubleSpinBox(self)
        spn.setRange(min_v, max_v)
        spn.setDecimals(2)
        spn.setSingleStep(0.5)
        spn.setSuffix(suffix)
        spn.setValue(val)
        return spn

    def _on_load_sample_clicked(self) -> None:
        path = self.cmb_examples.currentData()
        if path:
            self.load_example_requested.emit(str(path))

    def populate_svg_document(self, doc: Optional[ParsedSvgDocument]) -> None:
        self._updating_ui = True
        self.tree_elements.setUpdatesEnabled(False)
        self.tree_elements.clear()
        self.list_svg_warnings.clear()

        if doc is None:
            self.lbl_svg_info.setText("No SVG file loaded")
            self.tree_elements.setUpdatesEnabled(True)
            self._updating_ui = False
            return

        fname = Path(doc.file_path).name
        self.lbl_svg_info.setText(
            f"File: {fname}\nCanvas: {doc.width_mm:.1f} × {doc.height_mm:.1f} mm (Units: {doc.original_units})\n"
            f"Elements: {len(doc.elements)} across {len(doc.layers)} layer(s)"
        )

        layers_map: dict[str, QTreeWidgetItem] = {}
        for layer_name in doc.layers:
            l_item = QTreeWidgetItem(self.tree_elements, [layer_name, "Layer", ""])
            l_item.setFlags(l_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            l_item.setCheckState(0, Qt.CheckState.Checked)
            l_item.setData(0, Qt.ItemDataRole.UserRole, f"layer:{layer_name}")
            layers_map[layer_name] = l_item

        for el in doc.elements:
            parent_item = layers_map.get(el.layer) or self.tree_elements.invisibleRootItem()
            pts_count = sum(len(p) for p in el.polylines_mm)
            e_item = QTreeWidgetItem(parent_item, [el.name, el.element_type, str(pts_count)])
            e_item.setFlags(e_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            e_item.setCheckState(0, Qt.CheckState.Checked if el.visible else Qt.CheckState.Unchecked)
            e_item.setData(0, Qt.ItemDataRole.UserRole, el.id)

        if len(doc.elements) <= 250:
            self.tree_elements.expandAll()
        elif len(doc.elements) <= 500:
            for l_item in layers_map.values():
                l_item.setExpanded(True)
        else:
            for l_item in layers_map.values():
                l_item.setExpanded(False)
        self.tree_elements.setUpdatesEnabled(True)

        if not doc.warnings:
            item = QListWidgetItem("✓ All SVG elements parsed cleanly with zero warnings.")
            self.list_svg_warnings.addItem(item)
        else:
            for w in doc.warnings:
                prefix = "ℹ" if w.severity == "info" else "⚠"
                item = QListWidgetItem(f"{prefix} <{w.element_tag}>: {w.message}")
                self.list_svg_warnings.addItem(item)

        self._updating_ui = False

    def _on_tree_item_changed(self, item: QTreeWidgetItem, col: int) -> None:
        if self._updating_ui:
            return
        self._updating_ui = True
        tag_data = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        checked = item.checkState(0) == Qt.CheckState.Checked
        if tag_data.startswith("layer:"):
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._updating_ui = False
        self.element_visibility_changed.emit()

    def sync_visibility_to_document(self, doc: Optional[ParsedSvgDocument]) -> None:
        if doc is None:
            return
        vis_by_id: dict[str, bool] = {}
        root = self.tree_elements.invisibleRootItem()
        for i in range(root.childCount()):
            l_item = root.child(i)
            for j in range(l_item.childCount()):
                c_item = l_item.child(j)
                eid = str(c_item.data(0, Qt.ItemDataRole.UserRole) or "")
                vis_by_id[eid] = c_item.checkState(0) == Qt.CheckState.Checked
        for el in doc.elements:
            if el.id in vis_by_id:
                el.visible = vis_by_id[el.id]

    def _set_all_elements_visible(self, visible: bool) -> None:
        self._updating_ui = True
        state = Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
        root = self.tree_elements.invisibleRootItem()
        for i in range(root.childCount()):
            l_item = root.child(i)
            l_item.setCheckState(0, state)
            for j in range(l_item.childCount()):
                l_item.child(j).setCheckState(0, state)
        self._updating_ui = False
        self.element_visibility_changed.emit()

    def _on_tree_selection_changed(self) -> None:
        items = self.tree_elements.selectedItems()
        if not items:
            self.element_selection_changed.emit("")
            return
        data = str(items[0].data(0, Qt.ItemDataRole.UserRole) or "")
        if data.startswith("layer:"):
            self.element_selection_changed.emit("")
        else:
            self.element_selection_changed.emit(data)

    def refresh_profiles_ui(
        self,
        select_machine_id: Optional[str] = None,
        select_pen_id: Optional[str] = None,
    ) -> None:
        self._updating_ui = True

        # Machine combo
        self.cmb_machine.clear()
        for m_id, m_prof in self.profile_manager.machines.items():
            self.cmb_machine.addItem(m_prof.name, m_id)
        if select_machine_id:
            idx = self.cmb_machine.findData(select_machine_id)
            if idx >= 0:
                self.cmb_machine.setCurrentIndex(idx)

        # Pen combo
        self.cmb_pen.clear()
        for p_id, p_prof in self.profile_manager.pens.items():
            cal_tag = " [Calibrated]" if p_prof.is_calibrated else " [Uncalibrated]"
            self.cmb_pen.addItem(f"{p_prof.name}{cal_tag}", p_id)
        if select_pen_id:
            idx = self.cmb_pen.findData(select_pen_id)
            if idx >= 0:
                self.cmb_pen.setCurrentIndex(idx)

        self._updating_ui = False
        self._load_machine_into_spinboxes(self.current_machine_profile())
        self._load_pen_into_spinboxes(self.current_pen_profile())

    def current_machine_profile(self) -> MachineProfile:
        m_id = str(self.cmb_machine.currentData() or "bambu_a1_mini")
        return self.profile_manager.machines.get(m_id, self.profile_manager.get_default_machine())

    def current_pen_profile(self) -> PenProfile:
        p_id = str(self.cmb_pen.currentData() or "fineliner_04mm")
        return self.profile_manager.pens.get(p_id, self.profile_manager.get_default_pen())

    def _load_machine_into_spinboxes(self, m: MachineProfile) -> None:
        self._updating_ui = True
        self.spn_nom_x.setValue(m.nominal_x_mm)
        self.spn_nom_y.setValue(m.nominal_y_mm)
        self.spn_margin_left.setValue(m.margin_left_mm)
        self.spn_margin_right.setValue(m.margin_right_mm)
        self.spn_margin_front.setValue(m.margin_front_mm)
        self.spn_margin_back.setValue(m.margin_back_mm)
        orig_idx = self.cmb_origin.findData(m.origin_position)
        if orig_idx >= 0:
            self.cmb_origin.setCurrentIndex(orig_idx)
        self.spn_coord_off_x.setValue(m.coord_offset_x_mm)
        self.spn_coord_off_y.setValue(m.coord_offset_y_mm)
        self.spn_holder_off_x.setValue(m.pen_holder_offset_x_mm)
        self.spn_holder_off_y.setValue(m.pen_holder_offset_y_mm)
        self.spn_safe_z.setValue(m.safe_z_mm)
        self.spn_min_safe_z.setValue(m.min_safe_z_mm)
        self.spn_max_travel.setValue(m.max_travel_speed_mm_s)
        self.spn_max_draw.setValue(m.max_draw_speed_mm_s)
        self._updating_ui = False

    def _load_pen_into_spinboxes(self, p: PenProfile) -> None:
        self._updating_ui = True
        self.spn_pen_up_z.setValue(p.pen_up_z_mm)
        self.spn_pen_down_z.setValue(p.pen_down_z_mm)
        self.spn_drawing_z.setValue(p.drawing_z_mm)
        self.spn_lift_height.setValue(p.lift_height_mm)
        self.spn_pen_tip.setValue(p.tip_diameter_mm)
        self.spn_pen_off_x.setValue(p.x_offset_mm)
        self.spn_pen_off_y.setValue(p.y_offset_mm)
        self.spn_draw_speed.setValue(p.draw_speed_mm_s)
        self.spn_travel_speed.setValue(p.travel_speed_mm_s)
        self.spn_z_speed.setValue(p.z_speed_mm_s)
        self.spn_dwell_ms.setValue(p.stabilization_delay_ms)
        if hasattr(self, "lbl_pen_cal_status"):
            if p.is_calibrated:
                self.lbl_pen_cal_status.setText(
                    f"✅ <b>PHYSICALLY CALIBRATED</b><br>"
                    f"<span style='color: #94A3B8; font-size: 11px;'>Contact Z = {p.drawing_z_mm:.2f} mm | Up Z = {p.pen_up_z_mm:.2f} mm</span>"
                )
                self.lbl_pen_cal_status.setStyleSheet(
                    "background-color: rgba(34, 197, 94, 0.12); color: #22C55E; "
                    "border: 1px solid rgba(34, 197, 94, 0.35); border-radius: 4px; padding: 6px;"
                )
            else:
                self.lbl_pen_cal_status.setText(
                    f"⚠️ <b>NOT CALIBRATED (Default Presumptions)</b><br>"
                    f"<span style='color: #FBBF24; font-size: 11px;'>Values are theoretical. Run Calibration Wizard to measure real contact Z on your A1 Mini.</span>"
                )
                self.lbl_pen_cal_status.setStyleSheet(
                    "background-color: rgba(245, 158, 11, 0.12); color: #F59E0B; "
                    "border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 4px; padding: 6px;"
                )
        self._updating_ui = False

    def _on_machine_combo_changed(self) -> None:
        if self._updating_ui:
            return
        m = self.current_machine_profile()
        self._load_machine_into_spinboxes(m)
        self.machine_profile_changed.emit(m)

    def _emit_machine_updated(self) -> None:
        if self._updating_ui:
            return
        m = self.current_machine_profile()
        m.nominal_x_mm = self.spn_nom_x.value()
        m.nominal_y_mm = self.spn_nom_y.value()
        m.margin_left_mm = self.spn_margin_left.value()
        m.margin_right_mm = self.spn_margin_right.value()
        m.margin_front_mm = self.spn_margin_front.value()
        m.margin_back_mm = self.spn_margin_back.value()
        m.origin_position = str(self.cmb_origin.currentData() or "front_left")
        m.coord_offset_x_mm = self.spn_coord_off_x.value()
        m.coord_offset_y_mm = self.spn_coord_off_y.value()
        m.pen_holder_offset_x_mm = self.spn_holder_off_x.value()
        m.pen_holder_offset_y_mm = self.spn_holder_off_y.value()
        m.safe_z_mm = self.spn_safe_z.value()
        m.min_safe_z_mm = self.spn_min_safe_z.value()
        m.max_travel_speed_mm_s = self.spn_max_travel.value()
        m.max_draw_speed_mm_s = self.spn_max_draw.value()
        self.machine_profile_changed.emit(m)

    def _on_duplicate_machine(self) -> None:
        cur = self.current_machine_profile()
        new_m = self.profile_manager.duplicate_machine(cur.id)
        self.refresh_profiles_ui(select_machine_id=new_m.id)
        self.machine_profile_changed.emit(new_m)

    def _on_save_machine(self) -> None:
        m = self.current_machine_profile()
        self.profile_manager.save_machine(m)
        QMessageBox.information(self, "Machine Profile Saved", f"Saved configuration for '{m.name}'.")

    def _on_rename_machine(self) -> None:
        cur = self.current_machine_profile()
        name, ok = QInputDialog.getText(self, "Rename Machine Profile", "New Name:", text=cur.name)
        if ok and name.strip():
            self.profile_manager.rename_machine(cur.id, name.strip())
            self.refresh_profiles_ui(select_machine_id=cur.id)
            self.machine_profile_changed.emit(cur)

    def _on_delete_machine(self) -> None:
        cur = self.current_machine_profile()
        if cur.id == "bambu_a1_mini" or cur.is_builtin:
            QMessageBox.warning(self, "Cannot Delete", "The default Bambu Lab A1 Mini machine profile cannot be deleted.")
            return
        if len(self.profile_manager.machines) <= 1:
            QMessageBox.warning(self, "Cannot Delete", "At least one machine profile must remain.")
            return
        if self.profile_manager.delete_machine(cur.id):
            self.refresh_profiles_ui()
            self.machine_profile_changed.emit(self.current_machine_profile())

    def _on_pen_combo_changed(self) -> None:
        if self._updating_ui:
            return
        p = self.current_pen_profile()
        self._load_pen_into_spinboxes(p)
        self.pen_profile_changed.emit(p)

    def _emit_pen_updated(self) -> None:
        if self._updating_ui:
            return
        p = self.current_pen_profile()
        p.pen_up_z_mm = self.spn_pen_up_z.value()
        p.pen_down_z_mm = self.spn_pen_down_z.value()
        p.drawing_z_mm = self.spn_drawing_z.value()
        p.lift_height_mm = self.spn_lift_height.value()
        p.tip_diameter_mm = self.spn_pen_tip.value()
        p.x_offset_mm = self.spn_pen_off_x.value()
        p.y_offset_mm = self.spn_pen_off_y.value()
        p.draw_speed_mm_s = self.spn_draw_speed.value()
        p.travel_speed_mm_s = self.spn_travel_speed.value()
        p.z_speed_mm_s = self.spn_z_speed.value()
        p.stabilization_delay_ms = self.spn_dwell_ms.value()
        self.pen_profile_changed.emit(p)

    def _on_new_pen(self) -> None:
        name, ok = QInputDialog.getText(self, "New Pen Profile", "Enter Pen Profile Name:", text="Custom Technical Pen")
        if ok and name.strip():
            new_p = self.profile_manager.create_pen(name.strip())
            self.refresh_profiles_ui(select_pen_id=new_p.id)
            self.pen_profile_changed.emit(new_p)

    def _on_duplicate_pen(self) -> None:
        cur = self.current_pen_profile()
        dup = self.profile_manager.duplicate_pen(cur.id)
        self.refresh_profiles_ui(select_pen_id=dup.id)
        self.pen_profile_changed.emit(dup)

    def _on_rename_pen(self) -> None:
        cur = self.current_pen_profile()
        name, ok = QInputDialog.getText(self, "Rename Pen Profile", "New Name:", text=cur.name)
        if ok and name.strip():
            self.profile_manager.rename_pen(cur.id, name.strip())
            self.refresh_profiles_ui(select_pen_id=cur.id)
            self.pen_profile_changed.emit(cur)

    def _on_delete_pen(self) -> None:
        cur = self.current_pen_profile()
        if len(self.profile_manager.pens) <= 1:
            QMessageBox.warning(self, "Cannot Delete", "At least one pen profile must remain.")
            return
        if self.profile_manager.delete_pen(cur.id):
            self.refresh_profiles_ui()
            self.pen_profile_changed.emit(self.current_pen_profile())

    def _on_save_current_pen(self) -> None:
        p = self.current_pen_profile()
        self.profile_manager.save_pen(p)
        QMessageBox.information(self, "Pen Profile Saved", f"Saved pen profile '{p.name}'.")

    def _on_workflow_combo_changed(self) -> None:
        val = str(self.cmb_workflow.currentData() or WorkflowMode.BAMBU_SD_DIRECT.value)
        mode = WorkflowMode(val)
        if mode == WorkflowMode.BAMBU_SD_DIRECT:
            self.lbl_workflow_desc.setText(
                "Generates cold-plotting G-code (M104 S0, M140 S0, G28) for direct execution from the root of the A1 Mini MicroSD card."
            )
        elif mode == WorkflowMode.BAMBU_STUDIO_3MF:
            self.lbl_workflow_desc.setText(
                "Packages verified G-code, MD5 hash, slice_info.config, and preview thumbnail into a .gcode.3mf container for Bambu Studio."
            )
        else:
            self.lbl_workflow_desc.setText(
                "Generates standard generic 2D plotter G-code (G21/G90/G0/G1) without machine-specific homing macros."
            )
        self.workflow_mode_changed.emit(mode)
