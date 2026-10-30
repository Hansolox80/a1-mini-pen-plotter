#!/usr/bin/env bash
# ==============================================================================
# A1 Mini Pen Plotter — Linux Build & Packaging Automation Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================================"
echo "  A1 Mini Pen Plotter — Linux Distribution Build"
echo "================================================================================"

# 1. Verify Python 3
PYTHON_BIN=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_BIN="$cmd"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] Python 3 was not found on PATH. Please install Python 3.10 or newer."
    exit 1
fi

echo "[INFO] Using Python: $($PYTHON_BIN --version)"

# 2. Virtual Environment Setup
VENV_DIR=".venv_linux"
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creating virtual environment in $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Activate virtualenv
source "$VENV_DIR/bin/activate"

# 3. Install & Upgrade Dependencies
echo "[INFO] Upgrading pip and installing requirements..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install pyinstaller pytest

# 4. Generate Resource Assets if needed
if [ -f "scripts/generate_assets.py" ]; then
    echo "[INFO] Verifying application assets..."
    python scripts/generate_assets.py
fi

# 5. Run Automated Tests
echo "[INFO] Running automated test suites with pytest..."
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
pytest -v -q

# 6. Build Standalone Linux Executable with PyInstaller
echo "[INFO] Building standalone Linux application with PyInstaller..."
rm -rf build dist/"A1 Mini Pen Plotter"
pyinstaller --noconfirm --clean A1_Mini_Pen_Plotter.spec

# 7. Package Distribution Tarball
VERSION="1.10.1"
DIST_DIR="dist/A1 Mini Pen Plotter"
ARCHIVE_NAME="dist/A1-Mini-Pen-Plotter-v${VERSION}-linux-x64.tar.gz"

if [ -d "$DIST_DIR" ]; then
    echo "[INFO] Packaging tarball: $ARCHIVE_NAME..."
    tar -czf "$ARCHIVE_NAME" -C dist "A1 Mini Pen Plotter"
    echo "[SUCCESS] Linux build completed successfully!"
    echo "  Binary:  dist/A1 Mini Pen Plotter/A1 Mini Pen Plotter"
    echo "  Archive: $ARCHIVE_NAME"
else
    echo "[ERROR] Distribution folder was not created."
    exit 1
fi
