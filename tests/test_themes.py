"""Tests for the Theme Collection, Recommended Theme Selector, and Smooth Dark/Light Switch."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.machine.profiles import ProfileManager
from app.ui.dialogs.settings_dialog import AppSettings, SettingsDialog
from app.ui.main_window import MainWindow
from app.ui.theme import (
    DEFAULT_DARK_THEME,
    DEFAULT_LIGHT_THEME,
    THEMES,
    build_palette,
    build_stylesheet,
    is_light_theme,
    list_themes,
)
from app.ui.window_chrome import (
    CHROME_STYLES,
    DEFAULT_CHROME_STYLE,
    is_custom_chrome,
    list_chrome_styles,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


EXPECTED_THEMES = {
    "emerald_matrix": ("Dark", "#080D0A", "#111B14", "#1B3022", "#294333", "#E5F5E9", "#91A99A", "#00D878", "#35F59A", "#1B2920", "#111820", "#00D878", "#FF5252"),
    "arctic_blue": ("Dark", "#080F19", "#111E2D", "#1D344A", "#2A4056", "#E8F4FF", "#91A9BE", "#00BFFF", "#55D5FF", "#1A2B3D", "#101923", "#00BFFF", "#FF5C70"),
    "industrial_amber": ("Dark", "#101010", "#1B1B1B", "#303030", "#414141", "#F2F2F2", "#AAAAAA", "#FF9500", "#FFB340", "#292929", "#171717", "#FF9500", "#FF4545"),
    "crimson_night": ("Dark", "#100909", "#211010", "#391818", "#542727", "#F8EEEE", "#B99A9A", "#F04444", "#FF7777", "#2A1919", "#180F11", "#F04444", "#FF3030"),
    "deep_ocean": ("Dark", "#071211", "#102321", "#1A3835", "#28534D", "#E5F7F3", "#91B9B0", "#00C9B1", "#54E8D5", "#19312E", "#101D1D", "#00C9B1", "#FF6262"),
    "phosphor_crt": ("Dark", "#050805", "#101810", "#193019", "#294329", "#B5FFB8", "#6FAF75", "#35FF45", "#8AFF91", "#172517", "#080D08", "#35FF45", "#FF5555"),
    "midnight_purple": ("Dark", "#0D0B14", "#171322", "#241D35", "#39304D", "#F0EBFA", "#A69BB9", "#A879FF", "#C09AFF", "#252035", "#12101B", "#A879FF", "#FF5B70"),
    "slate_steel": ("Dark", "#171B20", "#222830", "#303944", "#414C58", "#E8EDF2", "#A1ACB8", "#7DA9D6", "#A2C6EA", "#303943", "#1C232B", "#7DA9D6", "#F06464"),
    "warm_paper": ("Light", "#F5F1E8", "#E8E0D0", "#FFFDF7", "#D5C9B5", "#30302D", "#82796B", "#8B6748", "#A67B56", "#DED6C8", "#FFFCF4", "#A67B56", "#D93636"),
    "platinum": ("Light", "#F7F8FA", "#E5E8EC", "#FFFFFF", "#CBD0D8", "#20252D", "#737C89", "#3478D4", "#5598F0", "#E1E5EA", "#FFFFFF", "#3478D4", "#D93636"),
    "solarized_light": ("Light", "#FDF6E3", "#EEE8D5", "#FFFAEB", "#D6CEB8", "#586E75", "#839496", "#268BD2", "#4AA3E0", "#E5DEC9", "#FFFCF2", "#268BD2", "#DC322F"),
}


def test_all_themes_registered_with_exact_tokens():
    for tid, vals in EXPECTED_THEMES.items():
        assert tid in THEMES, f"Missing theme {tid}"
        t = THEMES[tid]
        cat, bg_win, bg_pan, bg_surf, border, txt1, txt2, acc, acc_h, grid, canvas, sel, err = vals
        assert t["category"] == cat
        assert t["is_light"] == (cat == "Light")
        assert t["bg_window"] == bg_win
        assert t["bg_panel"] == bg_pan
        assert t["bg_surface"] == bg_surf
        assert t["border_default"] == border
        assert t["text_primary"] == txt1
        assert t["text_secondary"] == txt2
        assert t["accent_primary"] == acc
        assert t["accent_hover"] == acc_h
        assert t["bg_grid"] == grid
        assert t["bg_canvas"] == canvas
        assert t["color_selection"] == sel
        assert t["color_critical"] == err

    assert THEMES["emerald_matrix"]["recommended"] is True
    assert len(list_themes("Dark")) == 10  # 8 new + 2 classic
    assert len(list_themes("Light")) == 3


def test_build_stylesheet_succeeds_for_every_theme(qapp):
    for theme_id in THEMES:
        qss = build_stylesheet(theme_id)
        assert "QMainWindow" in qss
        assert "QMenuBar" in qss
        assert "QMenu" in qss
        assert THEMES[theme_id]["bg_window"] in qss
        assert THEMES[theme_id]["accent_primary"] in qss


def test_app_settings_theme_roundtrip():
    legacy = AppSettings.from_dict({"theme": "warm_paper"})
    assert legacy.theme == "warm_paper"
    assert legacy.last_light_theme == "warm_paper"
    assert legacy.last_dark_theme == DEFAULT_DARK_THEME

    modern = AppSettings.from_dict({
        "theme": "arctic_blue",
        "last_dark_theme": "arctic_blue",
        "last_light_theme": "solarized_light",
    })
    assert modern.theme == "arctic_blue"
    assert modern.last_dark_theme == "arctic_blue"
    assert modern.last_light_theme == "solarized_light"


def test_settings_dialog_theme_selector_and_category_filter(qapp):
    pm = ProfileManager()
    s = AppSettings(theme="crimson_night")
    dlg = SettingsDialog(s, pm)

    assert dlg.cmb_theme.count() == len(THEMES)
    assert dlg.cmb_theme.currentData() == "crimson_night"

    # Filter to Light themes
    idx_light = dlg.cmb_theme_category.findData("light")
    dlg.cmb_theme_category.setCurrentIndex(idx_light)
    assert dlg.cmb_theme.count() == 3

    # Pick Warm Paper and save
    idx_wp = dlg.cmb_theme.findData("warm_paper")
    assert idx_wp >= 0
    dlg.cmb_theme.setCurrentIndex(idx_wp)
    dlg._on_save()
    assert dlg.settings.theme == "warm_paper"
    assert dlg.settings.last_light_theme == "warm_paper"
    dlg.close()


def test_main_window_theme_switch_toggle(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.ui.dialogs.settings_dialog.get_user_app_data_dir",
        lambda: tmp_path,
    )
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    win.show()
    qapp.processEvents()

    # Initial is dark (graphite_dark default)
    assert not is_light_theme(win.settings_manager.settings.theme)
    assert win.theme_switch.is_light_mode() is False

    # Click switch -> transitions to Light mode (last_light_theme = platinum)
    QTest.mouseClick(win.theme_switch, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert win.theme_switch.is_light_mode() is True
    assert win.settings_manager.settings.theme == DEFAULT_LIGHT_THEME
    assert is_light_theme(win.settings_manager.settings.theme) is True

    # Click switch again -> transitions back to Dark mode (remembers graphite_dark)
    QTest.mouseClick(win.theme_switch, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert win.theme_switch.is_light_mode() is False
    assert win.settings_manager.settings.theme == "graphite_dark"

    # Apply every theme directly and repaint canvas to verify zero exceptions
    for theme_id in THEMES:
        win._apply_theme(theme_id)
        win.canvas.repaint()
        qapp.processEvents()

    win.close()


def test_build_palette_matches_theme_tokens(qapp):
    for theme_id, t in THEMES.items():
        pal = build_palette(theme_id)
        assert pal.color(QPalette.ColorRole.Window).name().upper() == t["bg_window"].upper()
        assert pal.color(QPalette.ColorRole.Base).name().upper() == t["bg_input"].upper()
        assert pal.color(QPalette.ColorRole.Text).name().upper() == t["text_primary"].upper()


def test_window_chrome_registry_and_settings():
    assert CHROME_STYLES["minimal_flat"]["recommended"] is True
    assert len(list_chrome_styles("Custom")) == 7
    assert len(list_chrome_styles("Native")) == 1
    assert is_custom_chrome("minimal_flat") is True
    assert is_custom_chrome("native") is False

    s_default = AppSettings.from_dict({})
    assert s_default.window_chrome == DEFAULT_CHROME_STYLE

    s_custom = AppSettings.from_dict({"window_chrome": "capsule_buttons"})
    assert s_custom.window_chrome == "capsule_buttons"

    s_invalid = AppSettings.from_dict({"window_chrome": "nonexistent_style"})
    assert s_invalid.window_chrome == DEFAULT_CHROME_STYLE


def test_settings_dialog_window_chrome_selector_and_preview(qapp):
    pm = ProfileManager()
    s = AppSettings(theme="emerald_matrix", window_chrome="capsule_buttons")
    dlg = SettingsDialog(s, pm)

    assert dlg.cmb_chrome.count() == len(CHROME_STYLES)
    assert dlg.cmb_chrome.currentData() == "capsule_buttons"

    idx_native = dlg.cmb_chrome_category.findData("native")
    dlg.cmb_chrome_category.setCurrentIndex(idx_native)
    assert dlg.cmb_chrome.count() == 1
    assert dlg.cmb_chrome.currentData() == "native"

    idx_custom = dlg.cmb_chrome_category.findData("custom")
    dlg.cmb_chrome_category.setCurrentIndex(idx_custom)
    assert dlg.cmb_chrome.count() == 7

    idx_traffic = dlg.cmb_chrome.findData("macos_traffic")
    assert idx_traffic >= 0
    dlg.cmb_chrome.setCurrentIndex(idx_traffic)
    dlg.chrome_preview.repaint()
    dlg._on_save()
    assert dlg.settings.window_chrome == "macos_traffic"
    dlg.close()


def test_main_window_switch_all_chrome_styles(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.ui.dialogs.settings_dialog.get_user_app_data_dir",
        lambda: tmp_path,
    )
    win = MainWindow(check_recovery=False, synchronous_pipeline=True)
    win.show()
    qapp.processEvents()

    for chrome_id in CHROME_STYLES:
        win._apply_window_chrome(chrome_id)
        win.window_chrome.repaint()
        qapp.processEvents()
        expected_frameless = is_custom_chrome(chrome_id)
        assert win._is_frameless is expected_frameless
        assert bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint) is expected_frameless
        assert win.menuBar() is win._menubar

    # Return to default custom chrome cleanly
    win._apply_window_chrome(DEFAULT_CHROME_STYLE)
    qapp.processEvents()
    win.close()
