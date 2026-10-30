@echo off
setlocal enabledelayedexpansion

echo ============================================================================
echo   A1 Mini Pen Plotter - Automated Windows Build ^& Verification Pipeline
echo ============================================================================

cd /d "%~dp0"

:: Step 1: Create or activate virtual environment
echo.
echo [1/5] Checking Python virtual environment (.venv)...
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv --system-site-packages
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        exit /b 1
    )
)
call ".venv\Scripts\activate.bat"

:: Step 2: Install dependencies
echo.
echo [2/5] Installing and verifying dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies from requirements.txt.
    exit /b 1
)

:: Generate icon and profile assets
".venv\Scripts\python.exe" scripts\generate_assets.py
if errorlevel 1 (
    echo ERROR: Asset generation failed.
    exit /b 1
)

:: Step 3: Run automated tests
echo.
echo [3/5] Running automated pytest suite...
".venv\Scripts\python.exe" -m pytest -v
if errorlevel 1 (
    echo ERROR: Automated tests failed! Aborting build.
    exit /b 1
)

:: Step 4: Build standalone Windows executable with PyInstaller
echo.
echo [4/5] Building standalone Windows executable via PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean A1_Mini_Pen_Plotter.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

:: Populate top-level resources, profiles, and examples inside dist\A1 Mini Pen Plotter\
if not exist "dist\A1 Mini Pen Plotter\resources" mkdir "dist\A1 Mini Pen Plotter\resources"
xcopy /Y /E /Q "app\resources\*" "dist\A1 Mini Pen Plotter\resources\" >nul
if not exist "dist\A1 Mini Pen Plotter\profiles" mkdir "dist\A1 Mini Pen Plotter\profiles"
xcopy /Y /E /Q "profiles\*" "dist\A1 Mini Pen Plotter\profiles\" >nul
if not exist "dist\A1 Mini Pen Plotter\examples" mkdir "dist\A1 Mini Pen Plotter\examples"
xcopy /Y /E /Q "examples\*" "dist\A1 Mini Pen Plotter\examples\" >nul

:: Step 5: Verify output structure and executable startup
echo.
echo [5/5] Verifying distribution output...
if not exist "dist\A1 Mini Pen Plotter\A1 Mini Pen Plotter.exe" (
    echo ERROR: Executable "dist\A1 Mini Pen Plotter\A1 Mini Pen Plotter.exe" was not found!
    exit /b 1
)
if not exist "dist\A1 Mini Pen Plotter\_internal" (
    echo ERROR: Directory "dist\A1 Mini Pen Plotter\_internal" was not found!
    exit /b 1
)
if not exist "dist\A1 Mini Pen Plotter\resources\icon.ico" (
    echo ERROR: Directory "dist\A1 Mini Pen Plotter\resources" is incomplete!
    exit /b 1
)

:: Smoke-test the compiled .exe by rendering a verification screenshot
"dist\A1 Mini Pen Plotter\A1 Mini Pen Plotter.exe" --screenshot "dist\A1 Mini Pen Plotter\resources\exe_verified.png"
if not exist "dist\A1 Mini Pen Plotter\resources\exe_verified.png" (
    echo ERROR: Compiled executable smoke test did not produce verification image!
    exit /b 1
)

echo.
echo ============================================================================
echo   BUILD SUCCESSFUL!
echo   Output: dist\A1 Mini Pen Plotter\A1 Mini Pen Plotter.exe
echo ============================================================================
exit /b 0
