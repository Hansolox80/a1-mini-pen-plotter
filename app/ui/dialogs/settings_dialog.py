"""Application Settings Window with persistent session storage (Section 13)."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import __app_name__, __author__, __version__
from app.machine.profiles import ProfileManager


@dataclass
class AppSettings:
    """Persistent user preferences across sessions."""
    theme: str = "graphite_dark"  # "graphite_dark" or "slate_engineering"
    default_units: str = "mm"
    default_machine_id: str = "bambu_a1_mini"
    default_pen_id: str = "fineliner_04mm"
    default_export_folder: str = ""
    show_grid: bool = True
    show_rulers: bool = True
    grid_major_mm: float = 30.0
    grid_minor_mm: float = 10.0
    default_sim_speed: float = 1.0
    show_travel_in_sim: bool = True
    curve_precision_mm: float = 0.08
    autosave_interval_sec: int = 60

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        return cls(
            theme=str(data.get("theme", "graphite_dark")),
            default_units=str(data.get("default_units", "mm")),
            default_machine_id=str(data.get("default_machine_id", "bambu_a1_mini")),
            default_pen_id=str(data.get("default_pen_id", "fineliner_04mm")),
            default_export_folder=str(data.get("default_export_folder", "")),
            show_grid=bool(data.get("show_grid", True)),
            show_rulers=bool(data.get("show_rulers", True)),
            grid_major_mm=float(data.get("grid_major_mm", 30.0)),
            grid_minor_mm=float(data.get("grid_minor_mm", 10.0)),
            default_sim_speed=float(data.get("default_sim_speed", 1.0)),
            show_travel_in_sim=bool(data.get("show_travel_in_sim", True)),
            curve_precision_mm=float(data.get("curve_precision_mm", 0.08)),
            autosave_interval_sec=int(data.get("autosave_interval_sec", 60)),
        )


class SettingsManager:
    """Loads and saves `AppSettings` to JSON in the user's app data directory."""

    def __init__(self, settings_path: Optional[Path] = None) -> None:
        if settings_path is None:
            settings_path = Path.home() / ".a1_mini_pen_plotter" / "settings.json"
        self.settings_path = Path(settings_path)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = self.load()

    def load(self) -> AppSettings:
        if self.settings_path.exists():
            try:
                data = json.loads(self.settings_path.read_text(encoding="utf-8"))
                return AppSettings.from_dict(data)
            except Exception:
                pass
        return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.settings = settings
        try:
            self.settings_path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
        except Exception:
            pass


class SettingsDialog(QDialog):
    """Comprehensive preferences dialog covering Appearance, Defaults, Grid, Simulation, Performance, and About."""

    def __init__(
        self,
        settings: AppSettings,
        profile_manager: ProfileManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{__app_name__} — Settings")
        self.resize(560, 440)

        self.settings = AppSettings.from_dict(settings.to_dict())
        self.profile_manager = profile_manager

        self._build_ui()

    def _build_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(14, 14, 14, 14)
        vbox.setSpacing(10)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_general_tab(), "Appearance & Defaults")
        tabs.addTab(self._build_grid_sim_tab(), "Grid, Simulation & Performance")
        tabs.addTab(self._build_about_tab(), "Application Info")
        vbox.addWidget(tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        btn_save = QPushButton("Save Settings", self)
        btn_save.setObjectName("PrimaryButton")
        btn_save.clicked.connect(self._on_save)
        footer.addWidget(btn_save)
        vbox.addLayout(footer)

    def _build_general_tab(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        form = QFormLayout(page)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(8)

        self.cmb_theme = QComboBox(page)
        self.cmb_theme.addItem("Graphite Dark (Default CAD Theme)", "graphite_dark")
        self.cmb_theme.addItem("Slate Engineering Dark", "slate_engineering")
        idx_t = self.cmb_theme.findData(self.settings.theme)
        if idx_t >= 0:
            self.cmb_theme.setCurrentIndex(idx_t)

        self.cmb_units = QComboBox(page)
        self.cmb_units.addItem("Millimeters (mm)", "mm")
        self.cmb_units.addItem("Inches (in → converted to mm)", "in")
        idx_u = self.cmb_units.findData(self.settings.default_units)
        if idx_u >= 0:
            self.cmb_units.setCurrentIndex(idx_u)

        self.cmb_def_machine = QComboBox(page)
        for mid, mp in self.profile_manager.machines.items():
            self.cmb_def_machine.addItem(mp.name, mid)
        idx_m = self.cmb_def_machine.findData(self.settings.default_machine_id)
        if idx_m >= 0:
            self.cmb_def_machine.setCurrentIndex(idx_m)

        self.cmb_def_pen = QComboBox(page)
        for pid, pp in self.profile_manager.pens.items():
            self.cmb_def_pen.addItem(pp.name, pid)
        idx_p = self.cmb_def_pen.findData(self.settings.default_pen_id)
        if idx_p >= 0:
            self.cmb_def_pen.setCurrentIndex(idx_p)

        folder_row = QHBoxLayout()
        self.edt_export_dir = QLineEdit(self.settings.default_export_folder, page)
        folder_row.addWidget(self.edt_export_dir, 1)
        btn_browse = QPushButton("Browse...", page)
        btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(btn_browse)

        form.addRow("UI Appearance:", self.cmb_theme)
        form.addRow("Default Display Units:", self.cmb_units)
        form.addRow("Default Machine Profile:", self.cmb_def_machine)
        form.addRow("Default Pen Profile:", self.cmb_def_pen)
        form.addRow("Default Export Folder:", folder_row)
        return page

    def _build_grid_sim_tab(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        form = QFormLayout(page)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(8)

        self.chk_grid = QCheckBox("Show Millimeter Workspace Grid", page)
        self.chk_grid.setChecked(self.settings.show_grid)

        self.chk_rulers = QCheckBox("Show Horizontal & Vertical Millimeter Rulers", page)
        self.chk_rulers.setChecked(self.settings.show_rulers)

        self.spn_grid_major = QDoubleSpinBox(page)
        self.spn_grid_major.setRange(10.0, 100.0)
        self.spn_grid_major.setSuffix(" mm")
        self.spn_grid_major.setValue(self.settings.grid_major_mm)

        self.spn_grid_minor = QDoubleSpinBox(page)
        self.spn_grid_minor.setRange(5.0, 50.0)
        self.spn_grid_minor.setSuffix(" mm")
        self.spn_grid_minor.setValue(self.settings.grid_minor_mm)

        self.spn_sim_speed = QDoubleSpinBox(page)
        self.spn_sim_speed.setRange(0.25, 25.0)
        self.spn_sim_speed.setSuffix("×")
        self.spn_sim_speed.setValue(self.settings.default_sim_speed)

        self.spn_precision = QDoubleSpinBox(page)
        self.spn_precision.setRange(0.01, 1.0)
        self.spn_precision.setDecimals(3)
        self.spn_precision.setSuffix(" mm")
        self.spn_precision.setValue(self.settings.curve_precision_mm)

        self.spn_autosave = QSpinBox(page)
        self.spn_autosave.setRange(15, 600)
        self.spn_autosave.setSuffix(" sec")
        self.spn_autosave.setValue(self.settings.autosave_interval_sec)

        form.addRow("", self.chk_grid)
        form.addRow("", self.chk_rulers)
        form.addRow("Major Grid Spacing:", self.spn_grid_major)
        form.addRow("Minor Grid Spacing:", self.spn_grid_minor)
        form.addRow("Default Playback Speed:", self.spn_sim_speed)
        form.addRow("Curve Flattening Precision:", self.spn_precision)
        form.addRow("Autosave Interval:", self.spn_autosave)
        return page

    def _build_about_tab(self) -> QWidget:
        page = QFrame()
        page.setObjectName("SectionCard")
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(8)

        lbl = QLabel(
            f"{__app_name__} v{__version__}\n"
            f"Author: {__author__}\n\n"
            "Dedicated native Windows desktop SVG-to-G-code preparation application "
            "for using the Bambu Lab A1 Mini (180 × 180 mm) as a precision 2D pen plotter.\n\n"
            "Supported Workflows:\n"
            "• Direct MicroSD Execution (.gcode with cold-plotting safety protection)\n"
            "• Bambu Studio Container (.gcode.3mf with MD5 checksum & slice metadata)\n"
            "• Generic 2D Plotter G-Code (.gcode)",
            page,
        )
        lbl.setWordWrap(True)
        vbox.addWidget(lbl)
        vbox.addStretch(1)
        return page

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Default Export Folder", self.edt_export_dir.text())
        if folder:
            self.edt_export_dir.setText(folder)

    def _on_save(self) -> None:
        self.settings.theme = str(self.cmb_theme.currentData() or "graphite_dark")
        self.settings.default_units = str(self.cmb_units.currentData() or "mm")
        self.settings.default_machine_id = str(self.cmb_def_machine.currentData() or "bambu_a1_mini")
        self.settings.default_pen_id = str(self.cmb_def_pen.currentData() or "fineliner_04mm")
        self.settings.default_export_folder = self.edt_export_dir.text().strip()
        self.settings.show_grid = self.chk_grid.isChecked()
        self.settings.show_rulers = self.chk_rulers.isChecked()
        self.settings.grid_major_mm = self.spn_grid_major.value()
        self.settings.grid_minor_mm = self.spn_grid_minor.value()
        self.settings.default_sim_speed = self.spn_sim_speed.value()
        self.settings.curve_precision_mm = self.spn_precision.value()
        self.settings.autosave_interval_sec = self.spn_autosave.value()
        self.accept()
