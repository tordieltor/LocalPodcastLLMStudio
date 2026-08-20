# PodcastStudio - One-Click PowerShell Executable Builder
# Builds a standalone, single-file Windows executable (dist/PodcastStudio.exe)
#
# Usage:
#   .\build_exe.ps1
#
# If execution policy prevents script execution:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\build_exe.ps1

[CmdletBinding()]
param(
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

function Write-Banner {
    Write-Host "=======================================================================" -ForegroundColor Cyan
    Write-Host "          PodcastStudio - PyInstaller One-Click Build Pipeline         " -ForegroundColor White
    Write-Host "=======================================================================" -ForegroundColor Cyan
    Write-Host ""
}

Write-Banner

# ---------------------------------------------------------------------------
# 1. Resolve Script & Project Root Directory
# ---------------------------------------------------------------------------
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = (Get-Location).Path
}

# ---------------------------------------------------------------------------
# 2. Discover Python Runtime (.venv, venv, or system PATH)
# ---------------------------------------------------------------------------
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$AltVenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$PyCmd = $null
$PyArgs = @()

if (Test-Path $VenvPython) {
    Write-Host "[1/5] Using local virtual environment (.venv)..." -ForegroundColor Cyan
    Write-Host "      Path: $VenvPython" -ForegroundColor Gray
    $PyCmd = $VenvPython
} elseif (Test-Path $AltVenvPython) {
    Write-Host "[1/5] Using local virtual environment (venv)..." -ForegroundColor Cyan
    Write-Host "      Path: $AltVenvPython" -ForegroundColor Gray
    $PyCmd = $AltVenvPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    Write-Host "[1/5] Using system Python Launcher (py -3)..." -ForegroundColor Cyan
    $PyCmd = "py"
    $PyArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "[1/5] Using system Python from PATH..." -ForegroundColor Cyan
    $PyCmd = "python"
} else {
    Write-Host "[ERROR] Python 3.10+ runtime was not found on your system!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.10 or newer from:" -ForegroundColor Yellow
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "Ensure 'Add python.exe to PATH' is selected during installation." -ForegroundColor Yellow
    Write-Host ""
    if (-not $NoPause) { Read-Host "Press Enter to exit" }
    exit 1
}

# ---------------------------------------------------------------------------
# 3. Verify Python Version >= 3.10
# ---------------------------------------------------------------------------
try {
    $verCheckScript = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)"
    $fullVerArgs = $PyArgs + @("-c", $verCheckScript)
    $verOutput = & $PyCmd $fullVerArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Detected Python version ($verOutput) is incompatible. Python 3.10+ required." -ForegroundColor Red
        if (-not $NoPause) { Read-Host "Press Enter to exit" }
        exit 1
    }
    Write-Host "[OK] Python runtime verified: Python $verOutput" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "[ERROR] Failed to execute Python version check: $_" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "Press Enter to exit" }
    exit 1
}

# ---------------------------------------------------------------------------
# 4. Verify / Install PyInstaller
# ---------------------------------------------------------------------------
Write-Host "[2/5] Verifying PyInstaller installation..." -ForegroundColor Cyan
$checkPyInstArgs = $PyArgs + @("-c", "import PyInstaller; print(PyInstaller.__version__)")
$pyinstVer = $null

try {
    $pyinstVer = & $PyCmd $checkPyInstArgs 2>$null
} catch {
    $pyinstVer = $null
}

if (-not $pyinstVer -or $LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller not found in target Python environment." -ForegroundColor Yellow
    Write-Host "Installing PyInstaller package (pyinstaller>=6.4.0)..." -ForegroundColor Gray
    $installPyInstArgs = $PyArgs + @("-m", "pip", "install", "pyinstaller>=6.4.0")
    & $PyCmd $installPyInstArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install PyInstaller via pip." -ForegroundColor Red
        if (-not $NoPause) { Read-Host "Press Enter to exit" }
        exit 1
    }
    Write-Host "[OK] PyInstaller installed successfully." -ForegroundColor Green
} else {
    Write-Host "[OK] PyInstaller is available (version $pyinstVer)." -ForegroundColor Green
}
Write-Host ""

# ---------------------------------------------------------------------------
# 5. Clean Previous Build Artifacts
# ---------------------------------------------------------------------------
Write-Host "[3/5] Cleaning previous build workspaces (build, dist)..." -ForegroundColor Cyan
$BuildPath = Join-Path $ScriptDir "build"
$DistPath = Join-Path $ScriptDir "dist"

if (Test-Path $BuildPath) {
    Remove-Item -Path $BuildPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "      Removed build/ directory." -ForegroundColor Gray
}
if (Test-Path $DistPath) {
    Remove-Item -Path $DistPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "      Removed dist/ directory." -ForegroundColor Gray
}
Write-Host "[OK] Workspace cleaned." -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------------------
# 6. Execute PyInstaller Compilation
# ---------------------------------------------------------------------------
Write-Host "[4/5] Compiling standalone executable..." -ForegroundColor Cyan
$SpecFile = Join-Path $ScriptDir "PodcastStudio.spec"

Write-Host "-----------------------------------------------------------------------" -ForegroundColor DarkGray
if (Test-Path $SpecFile) {
    Write-Host "Executing: $PyCmd -m PyInstaller --clean $SpecFile" -ForegroundColor DarkCyan
    $buildArgs = $PyArgs + @("-m", "PyInstaller", "--clean", $SpecFile)
    & $PyCmd $buildArgs
} else {
    Write-Host "[WARN] PodcastStudio.spec not found, building with CLI flags..." -ForegroundColor Yellow
    $AppFile = Join-Path $ScriptDir "app.py"
    $buildArgs = $PyArgs + @(
        "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name", "PodcastStudio",
        "--clean",
        "--collect-all", "customtkinter",
        "--collect-all", "edge_tts",
        "--collect-all", "pypdf",
        "--collect-all", "certifi",
        $AppFile
    )
    & $PyCmd $buildArgs
}
$BuildExitCode = $LASTEXITCODE
Write-Host "-----------------------------------------------------------------------" -ForegroundColor DarkGray

if ($BuildExitCode -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] PyInstaller compilation failed with exit code $BuildExitCode!" -ForegroundColor Red
    Write-Host "Please check the compilation errors printed above." -ForegroundColor Yellow
    Write-Host ""
    if (-not $NoPause) { Read-Host "Press Enter to exit" }
    exit $BuildExitCode
}

Write-Host "[OK] PyInstaller compilation completed successfully." -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------------------
# 7. Post-Build Binary Validation & Sizing
# ---------------------------------------------------------------------------
Write-Host "[5/5] Performing post-build verification..." -ForegroundColor Cyan
$ExePath = Join-Path $DistPath "PodcastStudio.exe"

if (Test-Path $ExePath) {
    $ExeItem = Get-Item $ExePath
    $SizeBytes = $ExeItem.Length
    $SizeMB = [math]::Round($SizeBytes / 1MB, 2)

    Write-Host ""
    Write-Host "=======================================================================" -ForegroundColor Green
    Write-Host "                        BUILD SUCCESSFUL!                              " -ForegroundColor White
    Write-Host "=======================================================================" -ForegroundColor Green
    Write-Host "  Output Binary : $ExePath" -ForegroundColor White
    Write-Host "  Binary Size   : $SizeMB MB ($SizeBytes bytes)" -ForegroundColor Cyan
    Write-Host "  Window Mode   : Standalone Windowed (--noconsole, Zero UI Freezing)" -ForegroundColor Gray
    Write-Host "=======================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "To launch the compiled application:" -ForegroundColor White
    Write-Host "  .\dist\PodcastStudio.exe" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "[ERROR] dist\PodcastStudio.exe was not created!" -ForegroundColor Red
    Write-Host "Expected binary path: $ExePath" -ForegroundColor Yellow
    Write-Host ""
    if (-not $NoPause) { Read-Host "Press Enter to exit" }
    exit 1
}

if (-not $NoPause) {
    Write-Host "Press Enter to close this window..." -ForegroundColor DarkGray
    # Silent continue if running non-interactively
}
