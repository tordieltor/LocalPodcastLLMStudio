# LocalPodcastLLMStudio - One-Click PowerShell Executable Builder
# Builds a standalone, single-file Windows executable (dist/LocalPodcastLLMStudio.exe)
#
# Usage:
#   .\build_exe.ps1
#   .\build_exe.ps1 -NoPause
#
# If execution policy prevents script execution:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\build_exe.ps1

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
    Write-Host "       LocalPodcastLLMStudio - PyInstaller One-Click Build Pipeline    " -ForegroundColor White
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
Set-Location -Path $ScriptDir

# ---------------------------------------------------------------------------
# 2. Resilient Multi-Candidate Python 3.10+ Discovery
# ---------------------------------------------------------------------------
function Find-Python3 {
    param([string]$ProjectDir)
    
    # 1. Check existing .venv
    $venvPy = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        try {
            $ver = & $venvPy -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) {
                return @{ Command = $venvPy; Args = @(); Version = $ver.Trim(); Source = "Local Virtual Environment (.venv)" }
            }
        } catch {}
    }

    # 2. Check alternative venv
    $altVenvPy = Join-Path $ProjectDir "venv\Scripts\python.exe"
    if (Test-Path $altVenvPy) {
        try {
            $ver = & $altVenvPy -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) {
                return @{ Command = $altVenvPy; Args = @(); Version = $ver.Trim(); Source = "Local Virtual Environment (venv)" }
            }
        } catch {}
    }

    # 3. Check candidate system commands
    $candidates = [System.Collections.Generic.List[hashtable]]::new()
    $candidates.Add(@{ Cmd = "python"; Args = @() })
    $candidates.Add(@{ Cmd = "python3"; Args = @() })
    $candidates.Add(@{ Cmd = "py"; Args = @("-3") })

    # 4. Check standard installation directories
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
                return @{ Command = $c.Cmd; Args = $c.Args; Version = $ver.Trim(); Source = $c.Cmd }
            }
        } catch {}
    }
    return $null
}

$PyRuntime = Find-Python3 -ProjectDir $ScriptDir
if (-not $PyRuntime) {
    Write-Host "[ERROR] Python 3.10+ runtime was not found on your system!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.10 or newer from:" -ForegroundColor Yellow
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "Ensure 'Add python.exe to PATH' is selected during installation." -ForegroundColor Yellow
    Write-Host ""
    if (-not $NoPause) { Read-Host "Press Enter to exit" }
    exit 1
}

$PyCmd = $PyRuntime.Command
$PyArgs = $PyRuntime.Args
Write-Host "[1/5] Using Python runtime: $PyCmd" -ForegroundColor Cyan
Write-Host "      Source: $($PyRuntime.Source) (Python $($PyRuntime.Version))" -ForegroundColor Gray
Write-Host "[OK] Python runtime verified: Python $($PyRuntime.Version)" -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------------------
# 3. Verify / Install PyInstaller
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
# 4. Clean Previous Build Artifacts & Guard Process Locks
# ---------------------------------------------------------------------------
Write-Host "[3/5] Cleaning previous build workspaces (build, dist)..." -ForegroundColor Cyan
$BuildPath = Join-Path $ScriptDir "build"
$DistPath = Join-Path $ScriptDir "dist"
$TargetExe = Join-Path $DistPath "LocalPodcastLLMStudio.exe"

# Guard against running application instances
$runningProcesses = Get-Process -Name "LocalPodcastLLMStudio" -ErrorAction SilentlyContinue
if ($runningProcesses) {
    Write-Host "[WARN] Found active LocalPodcastLLMStudio process (PID: $(($runningProcesses.Id) -join ', '))." -ForegroundColor Yellow
    Write-Host "Terminating running process to release file lock on $TargetExe..." -ForegroundColor Yellow
    Stop-Process -Name "LocalPodcastLLMStudio" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

if (Test-Path $TargetExe) {
    try {
        Remove-Item -Path $TargetExe -Force -ErrorAction Stop
    } catch {
        Write-Host "[ERROR] dist\LocalPodcastLLMStudio.exe is locked by another process and cannot be removed: $_" -ForegroundColor Red
        Write-Host "Please close any open instances and retry." -ForegroundColor Yellow
        if (-not $NoPause) { Read-Host "Press Enter to exit" }
        exit 1
    }
}

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
# 5. Execute PyInstaller Compilation
# ---------------------------------------------------------------------------
Write-Host "[4/5] Compiling standalone executable..." -ForegroundColor Cyan
$SpecFile = Join-Path $ScriptDir "LocalPodcastLLMStudio.spec"

Write-Host "-----------------------------------------------------------------------" -ForegroundColor DarkGray
if (Test-Path $SpecFile) {
    Write-Host "Executing: $PyCmd -m PyInstaller --clean $SpecFile" -ForegroundColor DarkCyan
    $buildArgs = $PyArgs + @("-m", "PyInstaller", "--clean", $SpecFile)
    & $PyCmd $buildArgs
} else {
    Write-Host "[WARN] LocalPodcastLLMStudio.spec not found, building with CLI flags..." -ForegroundColor Yellow
    $AppFile = Join-Path $ScriptDir "app.py"
    $buildArgs = $PyArgs + @(
        "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name", "LocalPodcastLLMStudio",
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
# 6. Post-Build Binary Validation & Sizing
# ---------------------------------------------------------------------------
Write-Host "[5/5] Performing post-build verification..." -ForegroundColor Cyan
$ExePath = Join-Path $DistPath "LocalPodcastLLMStudio.exe"

if (Test-Path $ExePath) {
    $ExeItem = Get-Item $ExePath
    $SizeBytes = $ExeItem.Length
    if ($SizeBytes -le 0) {
        Write-Host "[ERROR] Output binary $ExePath is empty (0 bytes)!" -ForegroundColor Red
        if (-not $NoPause) { Read-Host "Press Enter to exit" }
        exit 1
    }
    $SizeMB = [math]::Round($SizeBytes / 1MB, 2)
    $FileHash = (Get-FileHash -Path $ExePath -Algorithm SHA256).Hash

    Write-Host ""
    Write-Host "=======================================================================" -ForegroundColor Green
    Write-Host "                        BUILD SUCCESSFUL!                              " -ForegroundColor White
    Write-Host "=======================================================================" -ForegroundColor Green
    Write-Host "  Output Binary : $ExePath" -ForegroundColor White
    Write-Host "  Binary Size   : $SizeMB MB ($SizeBytes bytes)" -ForegroundColor Cyan
    Write-Host "  SHA256 Hash   : $FileHash" -ForegroundColor DarkCyan
    Write-Host "  Window Mode   : Standalone Windowed (--noconsole, Zero UI Freezing)" -ForegroundColor Gray
    Write-Host "=======================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "To launch the compiled application:" -ForegroundColor White
    Write-Host "  .\dist\LocalPodcastLLMStudio.exe" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "[ERROR] dist\LocalPodcastLLMStudio.exe was not created!" -ForegroundColor Red
    Write-Host "Expected binary path: $ExePath" -ForegroundColor Yellow
    Write-Host ""
    if (-not $NoPause) { Read-Host "Press Enter to exit" }
    exit 1
}

if (-not $NoPause) {
    Read-Host "Press Enter to close this window..."
}
