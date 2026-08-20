# LocalPodcastLLMStudio - Create Desktop Shortcut
# Creates a Windows Desktop shortcut (.lnk) pointing to LocalPodcastLLMStudio.

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

$ShortcutPath = Join-Path $DesktopPath "LocalPodcastLLMStudio.lnk"
$ExePath = Join-Path $ProjectDir "dist\LocalPodcastLLMStudio.exe"
$VenvPyw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$AppPy = Join-Path $ProjectDir "app.py"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)

if (Test-Path $ExePath) {
    $Shortcut.TargetPath = $ExePath
    $Shortcut.Arguments = ""
    $Shortcut.IconLocation = "$ExePath,0"
    Write-Host "Configuring shortcut target: Standalone Executable ($ExePath)" -ForegroundColor Cyan
} elseif ((Test-Path $VenvPyw) -and (Test-Path $AppPy)) {
    $Shortcut.TargetPath = $VenvPyw
    $Shortcut.Arguments = "`"$AppPy`""
    Write-Host "Configuring shortcut target: Virtual Environment Pythonw ($VenvPyw app.py)" -ForegroundColor Cyan
} else {
    $Shortcut.TargetPath = "pythonw.exe"
    $Shortcut.Arguments = "`"$AppPy`""
    Write-Host "Configuring shortcut target: System Pythonw (app.py)" -ForegroundColor Yellow
}

$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description = "LocalPodcastLLMStudio - 100% Local AI Podcast Desktop Application"
$Shortcut.Save()

if (Test-Path $ShortcutPath) {
    Write-Host "=======================================================================" -ForegroundColor Green
    Write-Host "  Desktop shortcut created successfully!" -ForegroundColor Green
    Write-Host "  Location: $ShortcutPath" -ForegroundColor White
    Write-Host "  Target  : $($Shortcut.TargetPath)" -ForegroundColor Gray
    Write-Host "=======================================================================" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Failed to verify created shortcut at $ShortcutPath" -ForegroundColor Red
    exit 1
}
