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
from app.core.platform_utils import get_user_app_data_dir
from app.machine.profiles import ProfileManager
from app.ui.theme import (
    DEFAULT_DARK_THEME,
    DEFAULT_LIGHT_THEME,
    THEMES,
    get_theme_tokens,
    is_light_theme,
    list_themes,
)
from app.ui.window_chrome import (
    CHROME_STYLES,
    DEFAULT_CHROME_STYLE,
    ChromePreviewWidget,
    get_chrome_style,
    list_chrome_styles,
)


@dataclass
class AppSettings:
    """Persistent user preferences across sessions."""
    theme: str = "graphite_dark"
    last_dark_theme: str = DEFAULT_DARK_THEME
    last_light_theme: str = DEFAULT_LIGHT_THEME
    window_chrome: str = DEFAULT_CHROME_STYLE
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
        theme = str(data.get("theme", "graphite_dark"))
        if theme not in THEMES:
            theme = "graphite_dark"
        default_dark = theme if not is_light_theme(theme) else DEFAULT_DARK_THEME
        default_light = theme if is_light_theme(theme) else DEFAULT_LIGHT_THEME
        last_dark = str(data.get("last_dark_theme", default_dark))
        if last_dark not in THEMES or is_light_theme(last_dark):
            last_dark = default_dark
        last_light = str(data.get("last_light_theme", default_light))
        if last_light not in THEMES or not is_light_theme(last_light):
            last_light = default_light
        window_chrome = str(data.get("window_chrome", DEFAULT_CHROME_STYLE))
        if window_chrome not in CHROME_STYLES:
            window_chrome = DEFAULT_CHROME_STYLE

        return cls(
            theme=theme,
            last_dark_theme=last_dark,
            last_light_theme=last_light,
            window_chrome=window_chrome,
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
            settings_path = get_user_app_data_dir() / "settings.json"
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
        self.resize(580, 520)

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

        theme_box = QVBoxLayout()
        theme_box.setSpacing(6)

        theme_top = QHBoxLayout()
        theme_top.setSpacing(6)

        self.cmb_theme_category = QComboBox(page)
        self.cmb_theme_category.setFixedWidth(96)
        self.cmb_theme_category.addItem("All", "all")
        self.cmb_theme_category.addItem("Dark", "dark")
        self.cmb_theme_category.addItem("Light", "light")
        self.cmb_theme_category.currentIndexChanged.connect(self._populate_theme_combo)
        theme_top.addWidget(self.cmb_theme_category)

        self.cmb_theme = QComboBox(page)
        self.cmb_theme.currentIndexChanged.connect(self._update_theme_preview)
        theme_top.addWidget(self.cmb_theme, 1)
        theme_box.addLayout(theme_top)

        self.lbl_theme_desc = QLabel(page)
        self.lbl_theme_desc.setObjectName("MutedLabel")
        self.lbl_theme_desc.setWordWrap(True)
        theme_box.addWidget(self.lbl_theme_desc)

        self._swatch_row = QHBoxLayout()
        self._swatch_row.setSpacing(4)
        self._swatch_labels: list[QLabel] = []
        for _ in range(7):
            sw = QLabel(page)
            sw.setFixedSize(22, 12)
            self._swatch_row.addWidget(sw)
            self._swatch_labels.append(sw)
        self._swatch_row.addStretch(1)
        theme_box.addLayout(self._swatch_row)

        self._populate_theme_combo(select_theme=self.settings.theme)

        # Window Chrome Selector (mirroring Theme Selector)
        chrome_box = QVBoxLayout()
        chrome_box.setSpacing(6)

        chrome_top = QHBoxLayout()
        chrome_top.setSpacing(6)

        self.cmb_chrome_category = QComboBox(page)
        self.cmb_chrome_category.setFixedWidth(96)
        self.cmb_chrome_category.addItem("All", "all")
        self.cmb_chrome_category.addItem("Custom", "custom")
        self.cmb_chrome_category.addItem("Native", "native")
        self.cmb_chrome_category.currentIndexChanged.connect(self._populate_chrome_combo)
        chrome_top.addWidget(self.cmb_chrome_category)

        self.cmb_chrome = QComboBox(page)
        self.cmb_chrome.currentIndexChanged.connect(self._update_chrome_preview)
        chrome_top.addWidget(self.cmb_chrome, 1)
        chrome_box.addLayout(chrome_top)

        self.lbl_chrome_desc = QLabel(page)
        self.lbl_chrome_desc.setObjectName("MutedLabel")
        self.lbl_chrome_desc.setWordWrap(True)
        chrome_box.addWidget(self.lbl_chrome_desc)

        self.chrome_preview = ChromePreviewWidget(page)
        chrome_box.addWidget(self.chrome_preview)

        self._populate_chrome_combo(select_chrome=self.settings.window_chrome)

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

        form.addRow("UI Appearance:", theme_box)
        form.addRow("Window Chrome:", chrome_box)
        form.addRow("Default Display Units:", self.cmb_units)
        form.addRow("Default Machine Profile:", self.cmb_def_machine)
        form.addRow("Default Pen Profile:", self.cmb_def_pen)
        form.addRow("Default Export Folder:", folder_row)
        return page

    def _populate_theme_combo(self, _index: int = 0, select_theme: Optional[str] = None) -> None:
        target = select_theme or str(self.cmb_theme.currentData() or self.settings.theme)
        cat_filter = str(self.cmb_theme_category.currentData() or "all")
        category_arg = None if cat_filter == "all" else cat_filter

        self.cmb_theme.blockSignals(True)
        self.cmb_theme.clear()
        for t in list_themes(category_arg):
            rec = " (Recommended)" if t.get("recommended") else ""
            label = f"{t['name']}{rec} — {t['category']}"
            self.cmb_theme.addItem(label, t["id"])

        idx_t = self.cmb_theme.findData(target)
        if idx_t >= 0:
            self.cmb_theme.setCurrentIndex(idx_t)
        elif self.cmb_theme.count() > 0:
            self.cmb_theme.setCurrentIndex(0)
        self.cmb_theme.blockSignals(False)
        self._update_theme_preview()

    def _update_theme_preview(self) -> None:
        theme_id = str(self.cmb_theme.currentData() or self.settings.theme)
        t = get_theme_tokens(theme_id)
        rec = " • Recommended" if t.get("recommended") else ""
        self.lbl_theme_desc.setText(f"[{t['category']}{rec}] {t['style_desc']}")
        swatch_keys = [
            ("bg_window", "Main Background"),
            ("bg_panel", "Panel Background"),
            ("bg_surface", "Elevated Surface"),
            ("accent_primary", "Accent"),
            ("bg_canvas", "Canvas"),
            ("color_selection", "Selection"),
            ("color_critical", "Error"),
        ]
        for lbl, (key, title) in zip(self._swatch_labels, swatch_keys):
            color_hex = str(t[key])
            lbl.setStyleSheet(
                f"background-color: {color_hex}; border: 1px solid {t['border_default']}; border-radius: 3px;"
            )
            lbl.setToolTip(f"{title}: {color_hex}")
        if hasattr(self, "chrome_preview"):
            self._update_chrome_preview()

    def _populate_chrome_combo(self, _index: int = 0, select_chrome: Optional[str] = None) -> None:
        target = select_chrome or str(self.cmb_chrome.currentData() or self.settings.window_chrome)
        cat_filter = str(self.cmb_chrome_category.currentData() or "all")
        category_arg = None if cat_filter == "all" else cat_filter

        self.cmb_chrome.blockSignals(True)
        self.cmb_chrome.clear()
        for c in list_chrome_styles(category_arg):
            rec = " (Recommended)" if c.get("recommended") else ""
            label = f"{c['name']}{rec} — {c['category']}"
            self.cmb_chrome.addItem(label, c["id"])

        idx_c = self.cmb_chrome.findData(target)
        if idx_c >= 0:
            self.cmb_chrome.setCurrentIndex(idx_c)
        elif self.cmb_chrome.count() > 0:
            self.cmb_chrome.setCurrentIndex(0)
        self.cmb_chrome.blockSignals(False)
        self._update_chrome_preview()

    def _update_chrome_preview(self) -> None:
        chrome_id = str(self.cmb_chrome.currentData() or self.settings.window_chrome)
        theme_id = str(self.cmb_theme.currentData() or self.settings.theme)
        c = get_chrome_style(chrome_id)
        rec = " • Recommended" if c.get("recommended") else ""
        self.lbl_chrome_desc.setText(f"[{c['category']}{rec}] {c['desc']}")
        self.chrome_preview.set_preview(chrome_id, theme_id)

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
        chosen_theme = str(self.cmb_theme.currentData() or "graphite_dark")
        self.settings.theme = chosen_theme
        if is_light_theme(chosen_theme):
            self.settings.last_light_theme = chosen_theme
        else:
            self.settings.last_dark_theme = chosen_theme
        self.settings.window_chrome = str(self.cmb_chrome.currentData() or DEFAULT_CHROME_STYLE)
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
