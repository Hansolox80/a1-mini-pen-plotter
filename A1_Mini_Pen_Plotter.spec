# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for A1 Mini Pen Plotter cross-platform distribution (Windows, Linux, macOS)."""

from pathlib import Path
import sys

block_cipher = None
project_root = Path(SPECPATH)

is_windows = sys.platform.startswith("win")
is_macos = sys.platform == "darwin"
is_linux = sys.platform.startswith("linux")

datas = [
    (str(project_root / "app" / "resources"), "app/resources"),
    (str(project_root / "profiles"), "profiles"),
    (str(project_root / "examples"), "examples"),
]

excludes = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtTest",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "scipy.signal",
    "scipy.fft",
    "scipy.integrate",
    "scipy.interpolate",
    "scipy.ndimage",
    "scipy.stats",
    "tkinter",
    "pytest",
    "unittest",
]

a = Analysis(
    [str(project_root / "app" / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtSvg",
        "PySide6.QtXml",
        "shapely",
        "svgpathtools",
        "numpy",
        "scipy",
        "PIL",
        "defusedxml",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

version_file = str(project_root / "scripts" / "version_info.txt") if is_windows else None
icon_file = str(project_root / "app" / "resources" / "icon.ico") if is_windows else str(project_root / "app" / "resources" / "icon.png")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="A1 Mini Pen Plotter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True if is_windows else False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_file,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True if is_windows else False,
    upx_exclude=[],
    name="A1 Mini Pen Plotter",
)

if is_macos:
    app = BUNDLE(
        coll,
        name="A1 Mini Pen Plotter.app",
        icon=icon_file,
        bundle_identifier="com.a1mini.penplotter",
        info_plist={
            "CFBundleShortVersionString": "3.10.2",
            "CFBundleVersion": "3.10.2",
            "NSHighResolutionCapable": "True",
            "LSMinimumSystemVersion": "10.15",
        },
    )
