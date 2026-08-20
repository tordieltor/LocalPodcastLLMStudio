# LocalPodcastLLMStudio - Automated Environment Setup for PowerShell
# Usage:
#   .\setup.ps1
#   .\setup.ps1 -NoPause
#
# If execution policy prevents running scripts in your current session, run:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup.ps1

[CmdletBinding()]
param(
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

# Auto-detect non-interactive CI environments
if ($env:CI -eq "true" -or $env:GITHUB_ACTIONS -eq "true" -or $env:TF_BUILD -eq "True") {
    $NoPause = $true
}

function Write-Banner {
    Write-Host "=======================================================================" -ForegroundColor Cyan
    Write-Host "     LocalPodcastLLMStudio - Automated Self-Healing Setup Script       " -ForegroundColor White
    Write-Host "=======================================================================" -ForegroundColor Cyan
    Write-Host ""
}

Write-Banner

# 1. Resolve Script & Project Root Directory
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = (Get-Location).Path
}
Set-Location -Path $ScriptDir

$VenvDir = Join-Path $ScriptDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

# 2. Resilient Python Discovery Function
function Find-Python3 {
    param([string]$ProjectDir)
    
    # 1. Check existing .venv
    $vPy = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    if (Test-Path $vPy) {
        try {
            $ver = & $vPy -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) {
                return @{ Command = $vPy; Args = @(); Version = $ver.Trim(); Source = "Local Virtual Environment (.venv)"; IsVenv = $true }
            }
        } catch {}
    }

    # 2. Check candidate commands
    $candidates = [System.Collections.Generic.List[hashtable]]::new()
    $candidates.Add(@{ Cmd = "python"; Args = @() })
    $candidates.Add(@{ Cmd = "python3"; Args = @() })
    $candidates.Add(@{ Cmd = "py"; Args = @("-3") })

    # 3. Check standard installation directories
    $searchPatterns = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:ProgramFiles\Python3*\python.exe",
        "${env:ProgramFiles(x86)}\Python3*\python.exe",
        "$env:APPDATA\uv\python\*\python.exe"
    )
    foreach ($pattern in $searchPatterns) {
        if ($pattern) {
            $matches = Resolve-Path $pattern -ErrorAction SilentlyContinue
            if ($matches) {
                foreach ($m in $matches) {
                    $candidates.Add(@{ Cmd = $m.Path; Args = @() })
                }
            }
        }
    }

    foreach ($c in $candidates) {
        try {
            if (-not (Get-Command $c.Cmd -ErrorAction SilentlyContinue) -and -not (Test-Path $c.Cmd)) {
                continue
            }
            $fullArgs = $c.Args + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)")
            $ver = & $c.Cmd $fullArgs 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) {
                return @{ Command = $c.Cmd; Args = $c.Args; Version = $ver.Trim(); Source = $c.Cmd; IsVenv = $false }
            }
        } catch {}
    }
    return $null
}

$PyRuntime = Find-Python3 -ProjectDir $ScriptDir
if (-not $PyRuntime) {
    Write-Host "[ERROR] Python 3.10+ runtime was not found on your system!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.10 or higher from:" -ForegroundColor Yellow
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "IMPORTANT: Ensure 'Add python.exe to PATH' is checked during installation." -ForegroundColor Yellow
    Write-Host ""
    if (-not $NoPause) { Read-Host "Press Enter to exit" }
    exit 1
}

Write-Host "[OK] Python runtime detected: $($PyRuntime.Command)" -ForegroundColor Green
Write-Host "     Version: Python $($PyRuntime.Version)" -ForegroundColor Gray
Write-Host ""

# 3. Create Virtual Environment (.venv) if missing
if (-not (Test-Path $VenvPython)) {
    Write-Host "[1/4] Creating virtual environment (.venv)..." -ForegroundColor Cyan
    $createVenvArgs = $PyRuntime.Args + @("-m", "venv", $VenvDir)
    & $PyRuntime.Command $createVenvArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
        if (-not $NoPause) { Read-Host "Press Enter to exit" }
        exit 1
    }
    Write-Host "[OK] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "[OK] Virtual environment (.venv) already exists." -ForegroundColor Green
}
Write-Host ""

# 4. Upgrade pip in Virtual Environment
Write-Host "[2/4] Upgrading pip package manager..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] pip upgraded successfully." -ForegroundColor Green
}
Write-Host ""

# 5. Install Dependencies in Virtual Environment
Write-Host "[3/4] Installing dependencies..." -ForegroundColor Cyan
$ReqFile = Join-Path $ScriptDir "requirements.txt"
$ReqDevFile = Join-Path $ScriptDir "requirements-dev.txt"

if (Test-Path $ReqFile) {
    Write-Host "Installing runtime dependencies from requirements.txt..." -ForegroundColor Gray
    & $VenvPython -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install runtime dependencies." -ForegroundColor Red
        if (-not $NoPause) { Read-Host "Press Enter to exit" }
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

# 6. Run Preflight Diagnostics
Write-Host "[4/4] Running environment diagnostics..." -ForegroundColor Cyan
Write-Host "-----------------------------------------------------------------------" -ForegroundColor DarkGray
$CheckScript = Join-Path $ScriptDir "check_env.py"
& $VenvPython $CheckScript
Write-Host "-----------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "To launch LocalPodcastLLMStudio at any time:" -ForegroundColor White
Write-Host "  1. Activate virtual environment:  .venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "  2. Start application:             python app.py" -ForegroundColor Yellow
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

if (-not $NoPause) {
    Read-Host "Press Enter to close this window..."
}
