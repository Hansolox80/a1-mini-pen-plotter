"""Cross-platform system utilities, path resolvers, font fallbacks, and OS abstractions."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def is_windows() -> bool:
    return sys.platform.startswith("win") or os.name == "nt"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux") or "bsd" in sys.platform


def get_user_app_data_dir() -> Path:
    """Returns the standard, OS-compliant user application data directory."""
    if is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = Path(appdata) / "A1MiniPenPlotter"
        else:
            path = Path.home() / ".a1_mini_pen_plotter"
    elif is_macos():
        path = Path.home() / "Library" / "Application Support" / "A1MiniPenPlotter"
    else:
        # Linux / XDG standard
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            path = Path(xdg_config) / "a1_mini_pen_plotter"
        else:
            path = Path.home() / ".config" / "a1_mini_pen_plotter"

    # Backward compatibility: if ~/.a1_mini_pen_plotter already exists with data, prefer it
    legacy_dir = Path.home() / ".a1_mini_pen_plotter"
    if legacy_dir.exists() and (legacy_dir / "settings.json").exists() and not path.exists():
        return legacy_dir

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_cache_dir() -> Path:
    """Returns the standard cache directory for logs and temporary files."""
    if is_windows():
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            path = Path(local_appdata) / "A1MiniPenPlotter" / "Cache"
        else:
            path = get_user_app_data_dir() / "cache"
    elif is_macos():
        path = Path.home() / "Library" / "Caches" / "A1MiniPenPlotter"
    else:
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            path = Path(xdg_cache) / "a1_mini_pen_plotter"
        else:
            path = Path.home() / ".cache" / "a1_mini_pen_plotter"

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_system_font_family() -> str:
    """Returns standard native font family chain for clean typography across OS platforms."""
    if is_macos():
        return '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif'
    elif is_linux():
        return 'Ubuntu, "DejaVu Sans", "Liberation Sans", Cantarell, Arial, sans-serif'
    else:
        return '"Segoe UI Variable Text", "Segoe UI", "Inter", Arial, sans-serif'


def get_mono_font_family() -> str:
    """Returns native monospace font family chain for G-code and numeric readouts."""
    if is_macos():
        return '"SF Mono", Menlo, "Courier New", monospace'
    elif is_linux():
        return '"Ubuntu Mono", "DejaVu Sans Mono", "Liberation Mono", monospace'
    else:
        return '"Cascadia Code", Consolas, "Courier New", monospace'


def get_primary_modifier_key() -> str:
    """Returns 'Cmd' on macOS and 'Ctrl' on Windows/Linux."""
    return "Cmd" if is_macos() else "Ctrl"
