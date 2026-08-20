@echo off
setlocal enabledelayedexpansion
title PodcastStudio - Automated Environment Setup

echo =======================================================================
echo          PodcastStudio - Automated Self-Healing Setup Script
echo =======================================================================
echo.

:: 1. Detect Python Command
set "PY_CMD="
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PY_CMD=python"
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python was not found in your PATH!
    echo.
    echo Please install Python 3.10 or higher from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Make sure to check "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Verify Python Version >= 3.10
%PY_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Incompatible Python version detected.
    echo PodcastStudio requires Python 3.10 or newer.
    echo Detected version:
    %PY_CMD% --version
    echo.
    echo Please download and install Python 3.10+ from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [OK] Python runtime verified:
%PY_CMD% --version
echo.

:: 3. Create Virtual Environment (.venv) if missing
if not exist ".venv\Scripts\activate.bat" (
    echo [1/4] Creating virtual environment (.venv)...
    %PY_CMD% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment in .venv.
        echo Please ensure you have write permissions in this directory.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment (.venv) already exists.
)
echo.

:: 4. Activate Virtual Environment
echo [2/4] Activating virtual environment...
call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo [OK] Virtual environment activated.
echo.

:: 5. Upgrade pip
echo [3/4] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo.

:: 6. Install Dependencies
echo [4/4] Installing dependencies...
if exist "requirements.txt" (
    echo Installing runtime dependencies from requirements.txt...
    pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install requirements.txt.
        pause
        exit /b 1
    )
)

if exist "requirements-dev.txt" (
    echo Installing development and build dependencies from requirements-dev.txt...
    pip install -r requirements-dev.txt --quiet
)
echo.

:: 7. Run Preflight Diagnostics
echo Running environment diagnostics...
echo -----------------------------------------------------------------------
python check_env.py
echo -----------------------------------------------------------------------
echo.
echo =======================================================================
echo Setup complete!
echo To launch PodcastStudio at any time:
echo   1. Activate virtual environment:  .venv\Scripts\activate
echo   2. Start application:             python app.py
echo =======================================================================
echo.
pause
