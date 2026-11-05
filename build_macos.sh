#!/usr/bin/env bash
# ==============================================================================
# A1 Mini Pen Plotter — macOS Build & Packaging Automation Script (.app & .dmg)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================================"
echo "  A1 Mini Pen Plotter — macOS Distribution Build"
echo "================================================================================"

# 1. Detect Architecture
ARCH=$(uname -m)
echo "[INFO] Target Architecture: $ARCH"

# 2. Verify Python 3
PYTHON_BIN=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_BIN="$cmd"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] Python 3 was not found on PATH. Please install Python 3.10 or newer (via brew or python.org)."
    exit 1
fi

echo "[INFO] Using Python: $($PYTHON_BIN --version)"

# 3. Virtual Environment Setup
VENV_DIR=".venv_macos"
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creating virtual environment in $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Activate virtualenv
source "$VENV_DIR/bin/activate"

# 4. Install & Upgrade Dependencies
echo "[INFO] Installing requirements and PyInstaller..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install pyinstaller pytest

# 5. Generate Resource Assets if needed
if [ -f "scripts/generate_assets.py" ]; then
    echo "[INFO] Verifying application assets..."
    python scripts/generate_assets.py
fi

# 6. Run Automated Tests
echo "[INFO] Running automated test suites with pytest..."
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
pytest -v -q

# 7. Build macOS .app Bundle with PyInstaller
echo "[INFO] Building macOS Application Bundle with PyInstaller..."
rm -rf build dist/"A1 Mini Pen Plotter.app" dist/"A1 Mini Pen Plotter"
pyinstaller --noconfirm --clean A1_Mini_Pen_Plotter.spec

# 8. Package Distribution (DMG & ZIP)
VERSION=$(python -c "import re; m = re.search(r'__version__\s*=\s*[\"\'\']([^\"\'\']+)[\"\'\']', open('app/__init__.py').read()); print(m.group(1) if m else '3.11.2')")
APP_PATH="dist/A1 Mini Pen Plotter.app"
ZIP_NAME="dist/A1-Mini-Pen-Plotter-v${VERSION}-macos-${ARCH}.zip"
DMG_NAME="dist/A1-Mini-Pen-Plotter-v${VERSION}-macos-${ARCH}.dmg"

if [ -d "$APP_PATH" ]; then
    echo "[INFO] Creating ZIP archive: $ZIP_NAME..."
    ditto -c -k --keepParent "$APP_PATH" "$ZIP_NAME"

    # Create DMG disk image if hdiutil is available
    if command -v hdiutil &>/dev/null; then
        echo "[INFO] Creating Apple Disk Image (DMG): $DMG_NAME..."
        rm -f "$DMG_NAME"
        hdiutil create -volname "A1 Mini Pen Plotter" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_NAME"
    fi

    echo "[SUCCESS] macOS build completed successfully!"
    echo "  Bundle:  $APP_PATH"
    echo "  ZIP:     $ZIP_NAME"
    if [ -f "$DMG_NAME" ]; then
        echo "  DMG:     $DMG_NAME"
    fi
else
    echo "[ERROR] macOS .app bundle was not found at $APP_PATH."
    exit 1
fi
