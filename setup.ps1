# PodcastStudio - Automated Environment Setup for PowerShell
# Usage: .\setup.ps1
#
# If execution policy prevents running scripts in your current session, run:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup.ps1

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Write-Banner {
    Write-Host "=======================================================================" -ForegroundColor Cyan
    Write-Host "         PodcastStudio - Automated Self-Healing Setup Script           " -ForegroundColor White
    Write-Host "=======================================================================" -ForegroundColor Cyan
    Write-Host ""
}

Write-Banner

# 1. Detect Python Command
$PythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
    $PythonArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
    $PythonArgs = @()
} else {
    Write-Host "[ERROR] Python was not found in your system PATH!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.10 or higher from:" -ForegroundColor Yellow
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "IMPORTANT: Ensure 'Add python.exe to PATH' is checked during installation." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# 2. Verify Python Version >= 3.10
try {
    $versionCheckScript = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)"
    $fullArgs = $PythonArgs + @("-c", $versionCheckScript)
    $versionOutput = & $PythonCmd $fullArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Python version ($versionOutput) is incompatible. PodcastStudio requires Python 3.10+." -ForegroundColor Red
        Write-Host "Please install Python 3.10 or newer from https://www.python.org/downloads/" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "[OK] Python runtime verified: Python $versionOutput" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "[ERROR] Failed to execute Python version check: $_" -ForegroundColor Red
    exit 1
}

# 3. Virtual Environment Path Resolution
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = (Get-Location).Path
}

$VenvDir = Join-Path $ScriptDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
$ActivatePs1 = Join-Path $VenvDir "Scripts\Activate.ps1"

# 4. Create Virtual Environment if Missing
if (-not (Test-Path $VenvPython)) {
    Write-Host "[1/4] Creating virtual environment (.venv)..." -ForegroundColor Cyan
    $createVenvArgs = $PythonArgs + @("-m", "venv", $VenvDir)
    & $PythonCmd $createVenvArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "[OK] Virtual environment (.venv) already exists." -ForegroundColor Green
}
Write-Host ""

# 5. Upgrade pip
Write-Host "[2/4] Upgrading pip package manager..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] pip upgraded successfully." -ForegroundColor Green
}
Write-Host ""

# 6. Install Dependencies
Write-Host "[3/4] Installing dependencies..." -ForegroundColor Cyan
$ReqFile = Join-Path $ScriptDir "requirements.txt"
$ReqDevFile = Join-Path $ScriptDir "requirements-dev.txt"

if (Test-Path $ReqFile) {
    Write-Host "Installing runtime dependencies from requirements.txt..." -ForegroundColor Gray
    & $VenvPython -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install runtime dependencies." -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Runtime dependencies installed." -ForegroundColor Green
}

if (Test-Path $ReqDevFile) {
    Write-Host "Installing development and build dependencies from requirements-dev.txt..." -ForegroundColor Gray
    & $VenvPython -m pip install -r $ReqDevFile --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Development dependencies installed." -ForegroundColor Green
    }
}
Write-Host ""

# 7. Run Preflight Diagnostics
Write-Host "[4/4] Running environment diagnostics..." -ForegroundColor Cyan
Write-Host "-----------------------------------------------------------------------" -ForegroundColor DarkGray
$CheckScript = Join-Path $ScriptDir "check_env.py"
& $VenvPython $CheckScript
Write-Host "-----------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "To launch PodcastStudio at any time:" -ForegroundColor White
Write-Host "  1. Activate virtual environment:  .venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "  2. Start application:             python app.py" -ForegroundColor Yellow
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""
