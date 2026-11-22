"""Three-layer design token system and Qt Stylesheet (QSS) for A1 Mini Pen Plotter."""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor, QPalette

from app.core.platform_utils import get_mono_font_family, get_system_font_family


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (34, 197, 94)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    a = max(0.0, min(1.0, alpha))
    return f"rgba({r}, {g}, {b}, {a:.2f})"


def _blend(hex_a: str, hex_b: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(hex_a)
    r2, g2, b2 = _hex_to_rgb(hex_b)
    t = max(0.0, min(1.0, t))
    r = int(round(r1 + (r2 - r1) * t))
    g = int(round(g1 + (g2 - g1) * t))
    b = int(round(b1 + (b2 - b1) * t))
    return f"#{r:02X}{g:02X}{b:02X}"


def _relative_luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def _contrast_text(bg_hex: str) -> str:
    """Returns dark or light foreground color with high contrast against bg_hex."""
    return "#09110B" if _relative_luminance(bg_hex) > 0.50 else "#FFFFFF"


def _make_theme(
    theme_id: str,
    name: str,
    category: str,
    style_desc: str,
    *,
    bg_window: str,
    bg_panel: str,
    bg_surface: str,
    border: str,
    text_primary: str,
    text_secondary: str,
    accent: str,
    accent_hover: str,
    bg_grid: str,
    bg_canvas: str,
    selection: str,
    error: str,
    recommended: bool = False,
) -> dict[str, Any]:
    is_light = category.lower() == "light"
    if is_light:
        bg_surface_hover = _blend(bg_surface, bg_panel, 0.45)
        bg_input = bg_surface
        border_subtle = _blend(border, bg_panel, 0.35)
        text_muted = _blend(text_secondary, bg_panel, 0.25)
        accent_pressed = _blend(accent, "#000000", 0.22)
        color_travel = "#0284C7"
        color_warning = "#D97706"
        grid_major = _blend(bg_grid, border, 0.45)
        plate_bg = bg_surface
        plate_tab = bg_panel
        plate_border = border
        ruler_bg = bg_panel
        badge_bg = _rgba(accent, 0.14)
        badge_border = _rgba(accent, 0.35)
        danger_bg = _rgba(error, 0.12)
        danger_hover = _rgba(error, 0.22)
        danger_text = error
    else:
        bg_surface_hover = _blend(bg_surface, text_primary, 0.08)
        bg_input = _blend(bg_window, "#000000", 0.22)
        border_subtle = _blend(border, bg_panel, 0.35)
        text_muted = _blend(text_secondary, bg_panel, 0.35)
        accent_pressed = _blend(accent, "#000000", 0.25)
        color_travel = "#38BDF8"
        color_warning = "#F59E0B"
        grid_major = _blend(bg_grid, text_secondary, 0.18)
        plate_bg = _blend(bg_canvas, bg_panel, 0.35)
        plate_tab = bg_panel
        plate_border = border
        ruler_bg = bg_panel
        badge_bg = _rgba(accent, 0.15)
        badge_border = _rgba(accent, 0.35)
        danger_bg = _rgba(error, 0.16)
        danger_hover = _rgba(error, 0.28)
        danger_text = _blend(error, "#FFFFFF", 0.35)

    return {
        "id": theme_id,
        "name": name,
        "category": category,
        "recommended": recommended,
        "style_desc": style_desc,
        "is_light": is_light,
        "bg_canvas": bg_canvas,
        "bg_grid": bg_grid,
        "bg_grid_major": grid_major,
        "plate_bg": plate_bg,
        "plate_tab": plate_tab,
        "plate_border": plate_border,
        "ruler_bg": ruler_bg,
        "bg_window": bg_window,
        "bg_panel": bg_panel,
        "bg_surface": bg_surface,
        "bg_surface_hover": bg_surface_hover,
        "bg_input": bg_input,
        "border_subtle": border_subtle,
        "border_default": border,
        "border_hover": _blend(border, text_secondary, 0.35),
        "border_focus": accent,
        "text_primary": text_primary,
        "text_secondary": text_secondary,
        "text_muted": text_muted,
        "accent_primary": accent,
        "accent_hover": accent_hover,
        "accent_pressed": accent_pressed,
        "accent_contrast": _contrast_text(accent),
        "accent_subtle": _rgba(accent, 0.16),
        "accent_checked_bg": _rgba(accent, 0.20),
        "accent_checked_text": accent_hover if not is_light else accent,
        "badge_bg": badge_bg,
        "badge_border": badge_border,
        "color_selection": selection,
        "color_travel": color_travel,
        "color_warning": color_warning,
        "color_critical": error,
        "danger_bg": danger_bg,
        "danger_hover": danger_hover,
        "danger_border": _rgba(error, 0.45),
        "danger_text": danger_text,
    }


THEMES: dict[str, dict[str, Any]] = {
    "emerald_matrix": _make_theme(
        "emerald_matrix",
        "Emerald Matrix",
        "Dark",
        "Futuristic, technological, terminal-inspired",
        bg_window="#080D0A",
        bg_panel="#111B14",
        bg_surface="#1B3022",
        border="#294333",
        text_primary="#E5F5E9",
        text_secondary="#91A99A",
        accent="#00D878",
        accent_hover="#35F59A",
        bg_grid="#1B2920",
        bg_canvas="#111820",
        selection="#00D878",
        error="#FF5252",
        recommended=True,
    ),
    "arctic_blue": _make_theme(
        "arctic_blue",
        "Arctic Blue",
        "Dark",
        "Modern industrial, futuristic, clean",
        bg_window="#080F19",
        bg_panel="#111E2D",
        bg_surface="#1D344A",
        border="#2A4056",
        text_primary="#E8F4FF",
        text_secondary="#91A9BE",
        accent="#00BFFF",
        accent_hover="#55D5FF",
        bg_grid="#1A2B3D",
        bg_canvas="#101923",
        selection="#00BFFF",
        error="#FF5C70",
    ),
    "industrial_amber": _make_theme(
        "industrial_amber",
        "Industrial Amber",
        "Dark",
        "Industrial machinery, CNC equipment, engineering tools",
        bg_window="#101010",
        bg_panel="#1B1B1B",
        bg_surface="#303030",
        border="#414141",
        text_primary="#F2F2F2",
        text_secondary="#AAAAAA",
        accent="#FF9500",
        accent_hover="#FFB340",
        bg_grid="#292929",
        bg_canvas="#171717",
        selection="#FF9500",
        error="#FF4545",
    ),
    "crimson_night": _make_theme(
        "crimson_night",
        "Crimson Night",
        "Dark",
        "Aggressive, sophisticated, dark",
        bg_window="#100909",
        bg_panel="#211010",
        bg_surface="#391818",
        border="#542727",
        text_primary="#F8EEEE",
        text_secondary="#B99A9A",
        accent="#F04444",
        accent_hover="#FF7777",
        bg_grid="#2A1919",
        bg_canvas="#180F11",
        selection="#F04444",
        error="#FF3030",
    ),
    "deep_ocean": _make_theme(
        "deep_ocean",
        "Deep Ocean",
        "Dark",
        "Minimalist, elegant, modern technology",
        bg_window="#071211",
        bg_panel="#102321",
        bg_surface="#1A3835",
        border="#28534D",
        text_primary="#E5F7F3",
        text_secondary="#91B9B0",
        accent="#00C9B1",
        accent_hover="#54E8D5",
        bg_grid="#19312E",
        bg_canvas="#101D1D",
        selection="#00C9B1",
        error="#FF6262",
    ),
    "phosphor_crt": _make_theme(
        "phosphor_crt",
        "Phosphor CRT",
        "Dark",
        "Retro computing, vintage terminals, monochrome",
        bg_window="#050805",
        bg_panel="#101810",
        bg_surface="#193019",
        border="#294329",
        text_primary="#B5FFB8",
        text_secondary="#6FAF75",
        accent="#35FF45",
        accent_hover="#8AFF91",
        bg_grid="#172517",
        bg_canvas="#080D08",
        selection="#35FF45",
        error="#FF5555",
    ),
    "midnight_purple": _make_theme(
        "midnight_purple",
        "Midnight Purple",
        "Dark",
        "Premium, futuristic, sophisticated",
        bg_window="#0D0B14",
        bg_panel="#171322",
        bg_surface="#241D35",
        border="#39304D",
        text_primary="#F0EBFA",
        text_secondary="#A69BB9",
        accent="#A879FF",
        accent_hover="#C09AFF",
        bg_grid="#252035",
        bg_canvas="#12101B",
        selection="#A879FF",
        error="#FF5B70",
    ),
    "slate_steel": _make_theme(
        "slate_steel",
        "Slate Steel",
        "Dark",
        "Professional CAD, mechanical engineering, industrial design",
        bg_window="#171B20",
        bg_panel="#222830",
        bg_surface="#303944",
        border="#414C58",
        text_primary="#E8EDF2",
        text_secondary="#A1ACB8",
        accent="#7DA9D6",
        accent_hover="#A2C6EA",
        bg_grid="#303943",
        bg_canvas="#1C232B",
        selection="#7DA9D6",
        error="#F06464",
    ),
    "warm_paper": _make_theme(
        "warm_paper",
        "Warm Paper",
        "Light",
        "Traditional technical drawing, paper, blueprint design",
        bg_window="#F5F1E8",
        bg_panel="#E8E0D0",
        bg_surface="#FFFDF7",
        border="#D5C9B5",
        text_primary="#30302D",
        text_secondary="#82796B",
        accent="#8B6748",
        accent_hover="#A67B56",
        bg_grid="#DED6C8",
        bg_canvas="#FFFCF4",
        selection="#A67B56",
        error="#D93636",
    ),
    "platinum": _make_theme(
        "platinum",
        "Platinum",
        "Light",
        "Professional, minimalist, clean industrial software",
        bg_window="#F7F8FA",
        bg_panel="#E5E8EC",
        bg_surface="#FFFFFF",
        border="#CBD0D8",
        text_primary="#20252D",
        text_secondary="#737C89",
        accent="#3478D4",
        accent_hover="#5598F0",
        bg_grid="#E1E5EA",
        bg_canvas="#FFFFFF",
        selection="#3478D4",
        error="#D93636",
    ),
    "solarized_light": _make_theme(
        "solarized_light",
        "Solarized Light",
        "Light",
        "Classic developer environment, balanced, low contrast",
        bg_window="#FDF6E3",
        bg_panel="#EEE8D5",
        bg_surface="#FFFAEB",
        border="#D6CEB8",
        text_primary="#586E75",
        text_secondary="#839496",
        accent="#268BD2",
        accent_hover="#4AA3E0",
        bg_grid="#E5DEC9",
        bg_canvas="#FFFCF2",
        selection="#268BD2",
        error="#DC322F",
    ),
    "graphite_dark": _make_theme(
        "graphite_dark",
        "Graphite Dark",
        "Dark",
        "Classic CAD dark engineering theme",
        bg_window="#14171C",
        bg_panel="#1A1E24",
        bg_surface="#22272F",
        border="#323944",
        text_primary="#F1F5F9",
        text_secondary="#94A3B8",
        accent="#22C55E",
        accent_hover="#34D369",
        bg_grid="#222730",
        bg_canvas="#0E1013",
        selection="#22C55E",
        error="#EF4444",
    ),
    "slate_engineering": _make_theme(
        "slate_engineering",
        "Slate Engineering",
        "Dark",
        "Classic slate engineering dark theme",
        bg_window="#1B2028",
        bg_panel="#222832",
        bg_surface="#2B323F",
        border="#3D4758",
        text_primary="#F8FAFC",
        text_secondary="#CBD5E1",
        accent="#22C55E",
        accent_hover="#34D369",
        bg_grid="#252C37",
        bg_canvas="#14181F",
        selection="#22C55E",
        error="#EF4444",
    ),
}

# Preserve existing alias references if imported anywhere
TOKENS_DARK = THEMES["graphite_dark"]
TOKENS_SLATE = THEMES["slate_engineering"]

DEFAULT_DARK_THEME = "emerald_matrix"
DEFAULT_LIGHT_THEME = "platinum"

_ACTIVE_THEME_NAME: str = "graphite_dark"


def get_theme_tokens(theme_name: str | None = None) -> dict[str, Any]:
    """Returns semantic token dictionary for the requested or active theme."""
    key = theme_name or _ACTIVE_THEME_NAME
    return THEMES.get(key, THEMES["graphite_dark"])


def set_active_theme(theme_name: str) -> dict[str, Any]:
    """Sets the module-level active theme key and returns its token dictionary."""
    global _ACTIVE_THEME_NAME
    if theme_name in THEMES:
        _ACTIVE_THEME_NAME = theme_name
    else:
        _ACTIVE_THEME_NAME = "graphite_dark"
    return THEMES[_ACTIVE_THEME_NAME]


def get_active_theme_name() -> str:
    return _ACTIVE_THEME_NAME


def is_light_theme(theme_name: str | None = None) -> bool:
    return bool(get_theme_tokens(theme_name)["is_light"])


def list_themes(category: str | None = None) -> list[dict[str, Any]]:
    """Returns theme definitions optionally filtered by 'Dark' or 'Light'."""
    items = list(THEMES.values())
    if category:
        cat_lower = category.lower()
        items = [t for t in items if t["category"].lower() == cat_lower]
    return items


def build_palette(theme_name: str = "graphite_dark") -> QPalette:
    """Builds a full QPalette from semantic theme tokens to eliminate OS light/dark bleed-through."""
    t = get_theme_tokens(theme_name)
    pal = QPalette()

    bg_win = QColor(t["bg_window"])
    bg_panel = QColor(t["bg_panel"])
    bg_surface = QColor(t["bg_surface"])
    bg_input = QColor(t["bg_input"])
    txt_1 = QColor(t["text_primary"])
    txt_2 = QColor(t["text_secondary"])
    txt_muted = QColor(t["text_muted"])
    accent = QColor(t["accent_primary"])
    accent_contrast = QColor(t["accent_contrast"])
    border = QColor(t["border_default"])

    pal.setColor(QPalette.ColorRole.Window, bg_win)
    pal.setColor(QPalette.ColorRole.WindowText, txt_1)
    pal.setColor(QPalette.ColorRole.Base, bg_input)
    pal.setColor(QPalette.ColorRole.AlternateBase, bg_panel)
    pal.setColor(QPalette.ColorRole.ToolTipBase, bg_surface)
    pal.setColor(QPalette.ColorRole.ToolTipText, txt_1)
    pal.setColor(QPalette.ColorRole.Text, txt_1)
    pal.setColor(QPalette.ColorRole.Button, bg_surface)
    pal.setColor(QPalette.ColorRole.ButtonText, txt_1)
    pal.setColor(QPalette.ColorRole.BrightText, QColor(t["accent_hover"]))
    pal.setColor(QPalette.ColorRole.Highlight, accent)
    pal.setColor(QPalette.ColorRole.HighlightedText, accent_contrast)
    pal.setColor(QPalette.ColorRole.PlaceholderText, txt_muted)
    pal.setColor(QPalette.ColorRole.Link, accent)
    pal.setColor(QPalette.ColorRole.Light, bg_surface)
    pal.setColor(QPalette.ColorRole.Midlight, bg_panel)
    pal.setColor(QPalette.ColorRole.Mid, border)
    pal.setColor(QPalette.ColorRole.Dark, bg_win)
    pal.setColor(QPalette.ColorRole.Shadow, QColor(0, 0, 0))

    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, txt_muted)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, txt_muted)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, txt_muted)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, border)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, txt_2)
    return pal


def build_stylesheet(theme_name: str = "graphite_dark") -> str:
    """Generates the complete Qt Stylesheet (QSS) from semantic design tokens."""
    t = set_active_theme(theme_name)
    sys_font = get_system_font_family()
    mono_font = get_mono_font_family()

    return f"""
    /* Global Window & Typography */
    QMainWindow, QDialog {{
        background-color: {t['bg_window']};
        color: {t['text_primary']};
        font-family: {sys_font};
        font-size: 12px;
    }}

    QMainWindow::separator {{
        background-color: {t['border_subtle']};
        width: 1px;
        height: 1px;
    }}

    QWidget {{
        color: {t['text_primary']};
        font-family: {sys_font};
        font-size: 12px;
        selection-background-color: {t['accent_primary']};
        selection-color: {t['accent_contrast']};
    }}

    QWidget#CentralRoot, QWidget#CenterContainer {{
        background-color: {t['bg_window']};
    }}

    QToolTip {{
        background-color: {t['bg_surface']};
        color: {t['text_primary']};
        border: 1px solid {t['border_default']};
        padding: 4px 6px;
        border-radius: 4px;
    }}

    /* Custom Window Chrome */
    QFrame#WindowChromeRoot {{
        background-color: {t['bg_panel']};
        border-bottom: 1px solid {t['border_subtle']};
    }}

    QFrame#WindowTitleBar {{
        background-color: {t['bg_panel']};
    }}

    QLabel#WindowTitleText {{
        color: {t['text_secondary']};
        font-size: 12px;
        font-weight: 600;
    }}

    /* Scroll Areas (prevent OS light viewport bleed-through) */
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}

    QScrollArea > QWidget > QWidget {{
        background-color: transparent;
    }}

    QAbstractScrollArea::corner {{
        background-color: {t['bg_panel']};
    }}

    /* Top Toolbar */
    QFrame#TopToolbar {{
        background-color: {t['bg_panel']};
        border-bottom: 1px solid {t['border_subtle']};
    }}

    /* Sidebars & Inspector Containers */
    QFrame#SidebarContainer, QFrame#InspectorContainer, QFrame#SimulatorBar {{
        background-color: {t['bg_panel']};
        border: 1px solid {t['border_subtle']};
    }}

    QFrame#SectionCard {{
        background-color: {t['bg_surface']};
        border: 1px solid {t['border_subtle']};
        border-radius: 5px;
    }}

    QLabel#SectionHeader {{
        color: {t['text_secondary']};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.4px;
        padding: 2px 0px;
    }}

    QLabel#AppTitleLabel {{
        color: {t['text_primary']};
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.2px;
    }}

    QLabel#AppBadgeLabel {{
        background-color: {t['badge_bg']};
        color: {t['accent_primary']};
        border: 1px solid {t['badge_border']};
        border-radius: 3px;
        padding: 1px 6px;
        font-size: 10px;
        font-weight: 600;
    }}

    QLabel#MonoValueLabel {{
        font-family: {mono_font};
        font-size: 12px;
        color: {t['text_primary']};
    }}

    QLabel#MutedLabel {{
        color: {t['text_secondary']};
        font-size: 11px;
    }}

    /* Buttons */
    QPushButton, QToolButton {{
        background-color: {t['bg_surface']};
        color: {t['text_primary']};
        border: 1px solid {t['border_default']};
        border-radius: 4px;
        padding: 4px 8px;
        font-weight: 500;
        min-height: 18px;
    }}

    QPushButton:hover, QToolButton:hover {{
        background-color: {t['bg_surface_hover']};
        border-color: {t['border_hover']};
    }}

    QPushButton:pressed, QToolButton:pressed {{
        background-color: {t['bg_input']};
    }}

    QPushButton:checked, QToolButton:checked {{
        background-color: {t['accent_checked_bg']};
        border-color: {t['accent_primary']};
        color: {t['accent_checked_text']};
    }}

    QPushButton:disabled, QToolButton:disabled {{
        background-color: {t['bg_panel']};
        color: {t['text_muted']};
        border-color: {t['border_subtle']};
    }}

    QPushButton#PrimaryButton {{
        background-color: {t['accent_primary']};
        color: {t['accent_contrast']};
        border: 1px solid {t['accent_hover']};
        font-weight: 600;
    }}

    QPushButton#PrimaryButton:hover {{
        background-color: {t['accent_hover']};
        border-color: {t['accent_primary']};
    }}

    QPushButton#PrimaryButton:pressed {{
        background-color: {t['accent_pressed']};
        color: #FFFFFF;
    }}

    QPushButton#DangerButton {{
        background-color: {t['danger_bg']};
        color: {t['danger_text']};
        border: 1px solid {t['danger_border']};
    }}

    QPushButton#DangerButton:hover {{
        background-color: {t['danger_hover']};
    }}

    /* Inputs, SpinBoxes, ComboBoxes */
    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background-color: {t['bg_input']};
        color: {t['text_primary']};
        border: 1px solid {t['border_default']};
        border-radius: 4px;
        padding: 4px 7px;
        min-height: 18px;
    }}

    QDoubleSpinBox, QSpinBox {{
        font-family: {mono_font};
    }}

    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {t['border_focus']};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {t['bg_surface']};
        color: {t['text_primary']};
        border: 1px solid {t['border_default']};
        selection-background-color: {t['accent_primary']};
        selection-color: {t['accent_contrast']};
    }}

    /* Tab Widget */
    QTabWidget {{
        background-color: {t['bg_panel']};
    }}

    QTabWidget::pane {{
        border: 1px solid {t['border_subtle']};
        background-color: {t['bg_panel']};
    }}

    QTabWidget::tab-bar {{
        alignment: left;
        background-color: {t['bg_panel']};
    }}

    QTabBar {{
        background-color: {t['bg_panel']};
    }}

    QTabBar::tab {{
        background-color: {t['bg_window']};
        color: {t['text_secondary']};
        border: 1px solid {t['border_subtle']};
        border-bottom: none;
        padding: 5px 6px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        font-size: 11px;
        font-weight: 500;
    }}

    QTabBar::tab:hover {{
        color: {t['text_primary']};
        background-color: {t['bg_surface']};
    }}

    QTabBar::tab:selected {{
        background-color: {t['bg_panel']};
        color: {t['accent_primary']};
        border-top: 2px solid {t['accent_primary']};
        font-weight: 600;
    }}

    /* Trees, Lists, Tables */
    QTreeWidget, QListWidget, QTableWidget {{
        background-color: {t['bg_input']};
        border: 1px solid {t['border_subtle']};
        border-radius: 4px;
        alternate-background-color: {t['bg_panel']};
        outline: none;
    }}

    QTreeWidget::item, QListWidget::item {{
        padding: 4px 6px;
        border-radius: 3px;
    }}

    QTreeWidget::item:selected, QListWidget::item:selected {{
        background-color: {t['accent_checked_bg']};
        color: {t['text_primary']};
    }}

    QTreeWidget::item:hover, QListWidget::item:hover {{
        background-color: {t['bg_surface']};
    }}

    QHeaderView::section {{
        background-color: {t['bg_surface']};
        color: {t['text_secondary']};
        border: none;
        border-bottom: 1px solid {t['border_default']};
        padding: 5px 8px;
        font-weight: 600;
    }}

    /* Sliders & Progress Bars */
    QSlider::groove:horizontal {{
        height: 4px;
        background: {t['bg_input']};
        border: 1px solid {t['border_subtle']};
        border-radius: 2px;
    }}

    QSlider::sub-page:horizontal {{
        background: {t['accent_primary']};
        border-radius: 2px;
    }}

    QSlider::handle:horizontal {{
        background: {t['text_primary']};
        border: 2px solid {t['accent_primary']};
        width: 12px;
        height: 12px;
        margin: -5px 0;
        border-radius: 7px;
    }}

    /* ScrollBars */
    QScrollBar:vertical {{
        background: {t['bg_panel']};
        width: 10px;
        margin: 0px;
        border: none;
    }}

    QScrollBar::handle:vertical {{
        background: {t['border_default']};
        min-height: 24px;
        border-radius: 4px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {t['border_hover']};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
        border: none;
        background: transparent;
    }}

    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: {t['bg_panel']};
    }}

    QScrollBar:horizontal {{
        background: {t['bg_panel']};
        height: 10px;
        margin: 0px;
        border: none;
    }}

    QScrollBar::handle:horizontal {{
        background: {t['border_default']};
        min-width: 24px;
        border-radius: 4px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {t['border_hover']};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
        border: none;
        background: transparent;
    }}

    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: {t['bg_panel']};
    }}

    /* CheckBox */
    QCheckBox {{
        spacing: 6px;
        color: {t['text_primary']};
    }}

    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border-radius: 3px;
        border: 1px solid {t['border_default']};
        background-color: {t['bg_input']};
    }}

    QCheckBox::indicator:checked {{
        background-color: {t['accent_primary']};
        border-color: {t['accent_primary']};
    }}

    /* Splitter */
    QSplitter {{
        background-color: {t['bg_window']};
    }}

    QSplitter::handle {{
        background-color: {t['border_subtle']};
    }}

    QSplitter::handle:hover {{
        background-color: {t['accent_primary']};
    }}

    /* Status Bar */
    QStatusBar {{
        background-color: {t['bg_panel']};
        border-top: 1px solid {t['border_subtle']};
        color: {t['text_secondary']};
    }}

    /* Menu Bar & Dropdown Menus */
    QMenuBar {{
        background-color: {t['bg_panel']};
        color: {t['text_primary']};
        border-bottom: 1px solid {t['border_subtle']};
    }}

    QMenuBar::item:selected {{
        background-color: {t['bg_surface_hover']};
    }}

    QMenu {{
        background-color: {t['bg_surface']};
        color: {t['text_primary']};
        border: 1px solid {t['border_default']};
    }}

    QMenu::item {{
        padding: 5px 24px 5px 12px;
    }}

    QMenu::item:selected {{
        background-color: {t['accent_primary']};
        color: {t['accent_contrast']};
    }}

    QMenu::item:disabled {{
        color: {t['text_muted']};
    }}

    QMenu::separator {{
        height: 1px;
        background: {t['border_subtle']};
        margin: 4px 8px;
    }}
    """
