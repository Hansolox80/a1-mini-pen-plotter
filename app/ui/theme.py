"""Three-layer design token system and Qt Stylesheet (QSS) for commercial CAD/CAM dark engineering aesthetic."""

from __future__ import annotations


# Layer 1 & 2: Primitive & Semantic Tokens
TOKENS_DARK = {
    "bg_canvas": "#0E1013",
    "bg_window": "#14171C",
    "bg_panel": "#1A1E24",
    "bg_surface": "#22272F",
    "bg_surface_hover": "#2A303A",
    "bg_input": "#121519",
    "border_subtle": "#282E37",
    "border_default": "#323944",
    "border_focus": "#22C55E",
    "text_primary": "#F1F5F9",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",
    "accent_primary": "#22C55E",
    "accent_hover": "#16A34A",
    "accent_pressed": "#15803D",
    "accent_subtle": "rgba(34, 197, 94, 0.14)",
    "color_travel": "#38BDF8",
    "color_warning": "#F59E0B",
    "color_critical": "#EF4444",
}

TOKENS_SLATE = {
    "bg_canvas": "#14181F",
    "bg_window": "#1B2028",
    "bg_panel": "#222832",
    "bg_surface": "#2B323F",
    "bg_surface_hover": "#353E4D",
    "bg_input": "#161A22",
    "border_subtle": "#313947",
    "border_default": "#3D4758",
    "border_focus": "#22C55E",
    "text_primary": "#F8FAFC",
    "text_secondary": "#CBD5E1",
    "text_muted": "#94A3B8",
    "accent_primary": "#22C55E",
    "accent_hover": "#16A34A",
    "accent_pressed": "#15803D",
    "accent_subtle": "rgba(34, 197, 94, 0.16)",
    "color_travel": "#38BDF8",
    "color_warning": "#F59E0B",
    "color_critical": "#EF4444",
}


def build_stylesheet(theme_name: str = "graphite_dark") -> str:
    """Generates the complete Qt Stylesheet (QSS) from semantic design tokens."""
    t = TOKENS_SLATE if theme_name == "slate_engineering" else TOKENS_DARK

    return f"""
    /* Global Window & Typography */
    QMainWindow, QDialog {{
        background-color: {t['bg_window']};
        color: {t['text_primary']};
        font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif;
        font-size: 12px;
    }}

    QWidget {{
        color: {t['text_primary']};
        font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif;
        font-size: 12px;
        selection-background-color: {t['accent_primary']};
        selection-color: #090B0E;
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
        background-color: rgba(34, 197, 94, 0.15);
        color: {t['accent_primary']};
        border: 1px solid rgba(34, 197, 94, 0.35);
        border-radius: 3px;
        padding: 1px 6px;
        font-size: 10px;
        font-weight: 600;
    }}

    QLabel#MonoValueLabel {{
        font-family: "Cascadia Mono", "Consolas", monospace;
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
        border-color: #454F5E;
    }}

    QPushButton:pressed, QToolButton:pressed {{
        background-color: {t['bg_input']};
    }}

    QPushButton:checked, QToolButton:checked {{
        background-color: rgba(34, 197, 94, 0.18);
        border-color: {t['accent_primary']};
        color: #4ADE80;
    }}

    QPushButton:disabled, QToolButton:disabled {{
        background-color: {t['bg_panel']};
        color: {t['text_muted']};
        border-color: {t['border_subtle']};
    }}

    QPushButton#PrimaryButton {{
        background-color: {t['accent_primary']};
        color: #09110B;
        border: 1px solid {t['accent_hover']};
        font-weight: 600;
    }}

    QPushButton#PrimaryButton:hover {{
        background-color: #34D369;
        border-color: {t['accent_primary']};
    }}

    QPushButton#PrimaryButton:pressed {{
        background-color: {t['accent_pressed']};
        color: #FFFFFF;
    }}

    QPushButton#DangerButton {{
        background-color: rgba(239, 68, 68, 0.15);
        color: #FCA5A5;
        border: 1px solid rgba(239, 68, 68, 0.45);
    }}

    QPushButton#DangerButton:hover {{
        background-color: rgba(239, 68, 68, 0.28);
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
        font-family: "Cascadia Mono", "Consolas", monospace;
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
        selection-color: #09110B;
    }}

    /* Tab Widget */
    QTabWidget::pane {{
        border: 1px solid {t['border_subtle']};
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
        background-color: rgba(34, 197, 94, 0.20);
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
    }}

    QScrollBar::handle:vertical {{
        background: {t['border_default']};
        min-height: 24px;
        border-radius: 4px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #4B5565;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: {t['bg_panel']};
        height: 10px;
        margin: 0px;
    }}

    QScrollBar::handle:horizontal {{
        background: {t['border_default']};
        min-width: 24px;
        border-radius: 4px;
        margin: 2px;
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
    QSplitter::handle {{
        background-color: {t['border_subtle']};
    }}

    /* Status Bar */
    QStatusBar {{
        background-color: {t['bg_panel']};
        border-top: 1px solid {t['border_subtle']};
        color: {t['text_secondary']};
    }}
    """
