<#
.SYNOPSIS
    Packages the compiled standalone Windows distribution into a clean release ZIP
    with SHA-256 and MD5 checksums for GitHub Releases.
#>
$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistDir = Join-Path $ProjectRoot "dist"
$AppDir = Join-Path $DistDir "A1 Mini Pen Plotter"
$ExePath = Join-Path $AppDir "A1 Mini Pen Plotter.exe"

if (-not (Test-Path $ExePath)) {
    Write-Error "Compiled executable not found at '$ExePath'. Please run 'build_windows.bat' first."
    exit 1
}

$ZipName = "A1-Mini-Pen-Plotter-v1.1.0-windows-x64.zip"
$ZipPath = Join-Path $DistDir $ZipName

if (Test-Path $ZipPath) {
    Remove-Item -Path $ZipPath -Force
}

Write-Host "Creating release archive: $ZipPath ..."
Compress-Archive -Path "$AppDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal

$sha256 = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash
$md5 = (Get-FileHash -Path $ZipPath -Algorithm MD5).Hash
$sizeMb = [math]::Round(((Get-Item $ZipPath).Length / 1MB), 2)

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "  RELEASE PACKAGE CREATED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "Archive:  $ZipPath"
Write-Host "Size:     $sizeMb MB"
Write-Host "SHA-256:  $sha256"
Write-Host "MD5:      $md5"
Write-Host ""
Write-Host "You can now attach '$ZipName' directly to your GitHub Release."
