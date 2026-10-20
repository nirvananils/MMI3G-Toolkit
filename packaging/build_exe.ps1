<#
.SYNOPSIS
    Build the standalone Windows .exe for the MMI3G-Toolkit GUI builder.

.DESCRIPTION
    Installs PyInstaller if missing, then builds a single-file executable from
    packaging/mmi3g-gui.spec. Run from anywhere; the script cd's to the repo
    root itself. Output lands in dist/MMI3G-Toolkit-Builder.exe.

.EXAMPLE
    ./packaging/build_exe.ps1
#>
[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

# Repo root = parent of this script's folder.
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot
Write-Host "Repo root: $repoRoot"

# Read the version for a friendly log line (the .exe name stays constant).
$version = (& $Python -c "import sys; sys.path.insert(0,'builder'); import version; print(version.__version__)").Trim()
Write-Host "Building MMI3G-Toolkit-Builder v$version"

# Ensure PyInstaller is available.
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller not found - installing..."
    & $Python -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
}

# Clean previous output for a reproducible build.
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist")  { Remove-Item "dist"  -Recurse -Force }

& $Python -m PyInstaller "packaging/mmi3g-gui.spec" --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$exe = Join-Path $repoRoot "dist/MMI3G-Toolkit-Builder.exe"
if (Test-Path $exe) {
    $sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "Built: $exe ($sizeMb MB)"
} else {
    throw "Expected $exe but it was not produced"
}
