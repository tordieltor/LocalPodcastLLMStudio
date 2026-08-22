# LocalPodcastLLMStudio - Create Desktop Shortcuts
# Creates Windows Desktop shortcuts (.lnk) pointing to Desktop GUI and Terminal TUI.

$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
if (-not $ProjectDir) {
    $ProjectDir = (Get-Location).Path
}

$DesktopPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
if (-not (Test-Path $DesktopPath)) {
    Write-Host "[ERROR] Could not resolve Desktop folder path: $DesktopPath" -ForegroundColor Red
    exit 1
}

$WshShell = New-Object -ComObject WScript.Shell

$ExePath = Join-Path $ProjectDir "dist\LocalPodcastLLMStudio.exe"
$VenvPyw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$VenvPy = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$AppPy = Join-Path $ProjectDir "app.py"
$TuiPy = Join-Path $ProjectDir "tui.py"

# ==============================================================================
# 1. Primary & GUI Shortcut
# ==============================================================================
$GuiShortcutPath = Join-Path $DesktopPath "LocalPodcastLLMStudio.lnk"
$GuiShortcut = $WshShell.CreateShortcut($GuiShortcutPath)

if (Test-Path $ExePath) {
    $GuiShortcut.TargetPath = $ExePath
    $GuiShortcut.Arguments = ""
    $GuiShortcut.IconLocation = "$ExePath,0"
    Write-Host "Configuring GUI shortcut: Standalone Executable ($ExePath)" -ForegroundColor Cyan
} elseif ((Test-Path $VenvPyw) -and (Test-Path $AppPy)) {
    $GuiShortcut.TargetPath = $VenvPyw
    $GuiShortcut.Arguments = "`"$AppPy`""
    Write-Host "Configuring GUI shortcut: Virtual Environment ($VenvPyw app.py)" -ForegroundColor Cyan
} else {
    $GuiShortcut.TargetPath = "pythonw.exe"
    $GuiShortcut.Arguments = "`"$AppPy`""
    Write-Host "Configuring GUI shortcut: System Pythonw (app.py)" -ForegroundColor Yellow
}

$GuiShortcut.WorkingDirectory = $ProjectDir
$GuiShortcut.Description = "LocalPodcastLLMStudio - 100% Local AI Podcast Desktop Application"
$GuiShortcut.Save()

# ==============================================================================
# 2. Terminal TUI Shortcut
# ==============================================================================
$TuiShortcutPath = Join-Path $DesktopPath "LocalPodcastLLMStudio (Terminal TUI).lnk"
$TuiShortcut = $WshShell.CreateShortcut($TuiShortcutPath)

if ((Test-Path $VenvPy) -and (Test-Path $TuiPy)) {
    $TuiShortcut.TargetPath = $VenvPy
    $TuiShortcut.Arguments = "`"$TuiPy`""
    Write-Host "Configuring TUI shortcut: Virtual Environment ($VenvPy tui.py)" -ForegroundColor Cyan
} else {
    $TuiShortcut.TargetPath = "python.exe"
    $TuiShortcut.Arguments = "`"$TuiPy`""
    Write-Host "Configuring TUI shortcut: System Python ($TuiPy)" -ForegroundColor Yellow
}

$TuiShortcut.WorkingDirectory = $ProjectDir
$TuiShortcut.Description = "LocalPodcastLLMStudio - Interactive Tokyo Night Terminal User Interface"
$TuiShortcut.Save()

# ==============================================================================
# Verification
# ==============================================================================
Write-Host "=======================================================================" -ForegroundColor Green
Write-Host "  Desktop shortcuts created successfully for all features!" -ForegroundColor Green
Write-Host "  1. Desktop GUI : $GuiShortcutPath" -ForegroundColor White
Write-Host "  2. Terminal TUI: $TuiShortcutPath" -ForegroundColor White
Write-Host "=======================================================================" -ForegroundColor Green
