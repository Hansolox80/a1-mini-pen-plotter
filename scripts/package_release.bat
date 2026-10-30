@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0package_release.ps1"
if errorlevel 1 (
    echo [ERROR] Packaging failed.
    pause
    exit /b 1
)
