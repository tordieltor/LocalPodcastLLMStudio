@echo off
setlocal enabledelayedexpansion
title LocalPodcastLLMStudio - Create Desktop Shortcut
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1"

if %ERRORLEVEL% equ 0 (
    echo.
    echo Desktop shortcut ready!
) else (
    echo.
    echo [ERROR] Failed to create desktop shortcut.
)

if /i not "%~1"=="--no-pause" (
    echo.
    pause
)
