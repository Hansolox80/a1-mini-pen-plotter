<#
.SYNOPSIS
    Optional Windows User Installer for A1 Mini Pen Plotter.
    Copies the standalone build to %LOCALAPPDATA%\Programs\A1 Mini Pen Plotter
    and creates Desktop and Start Menu shortcuts.
#>
$ErrorActionPreference = "Stop"

$SourceDir = Join-Path $PSScriptRoot "..\dist\A1 Mini Pen Plotter"
if (-not (Test-Path "$SourceDir\A1 Mini Pen Plotter.exe")) {
    Write-Error "Compiled application not found at '$SourceDir'. Run build_windows.bat first."
    exit 1
}

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\A1 Mini Pen Plotter"
Write-Host "Installing A1 Mini Pen Plotter to $InstallDir ..."
if (Test-Path $InstallDir) {
    Remove-Item -Path $InstallDir -Recurse -Force
}
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path "$SourceDir\*" -Destination $InstallDir -Recurse -Force

$WshShell = New-Object -ComObject WScript.Shell

# Desktop Shortcut
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$DesktopShortcut = $WshShell.CreateShortcut((Join-Path $DesktopPath "A1 Mini Pen Plotter.lnk"))
$DesktopShortcut.TargetPath = Join-Path $InstallDir "A1 Mini Pen Plotter.exe"
$DesktopShortcut.WorkingDirectory = $InstallDir
$DesktopShortcut.IconLocation = Join-Path $InstallDir "resources\icon.ico"
$DesktopShortcut.Description = "A1 Mini Pen Plotter - SVG to G-Code Studio"
$DesktopShortcut.Save()

# Start Menu Shortcut
$StartMenuPath = [Environment]::GetFolderPath("Programs")
$StartShortcut = $WshShell.CreateShortcut((Join-Path $StartMenuPath "A1 Mini Pen Plotter.lnk"))
$StartShortcut.TargetPath = Join-Path $InstallDir "A1 Mini Pen Plotter.exe"
$StartShortcut.WorkingDirectory = $InstallDir
$StartShortcut.IconLocation = Join-Path $InstallDir "resources\icon.ico"
$StartShortcut.Description = "A1 Mini Pen Plotter - SVG to G-Code Studio"
$StartShortcut.Save()

Write-Host "Installation complete! Desktop and Start Menu shortcuts created."
