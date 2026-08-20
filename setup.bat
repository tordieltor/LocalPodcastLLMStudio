@echo off
setlocal enabledelayedexpansion
title LocalPodcastLLMStudio - Automated Environment Setup

:: ---------------------------------------------------------------------------
:: Pin working directory to script location
:: ---------------------------------------------------------------------------
cd /d "%~dp0"

:: ---------------------------------------------------------------------------
:: Parse Arguments & CI Environment
:: ---------------------------------------------------------------------------
set "NO_PAUSE=0"
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"
if /i "%~1"=="-nopause" set "NO_PAUSE=1"
if /i "%~1"=="/nopause" set "NO_PAUSE=1"
if /i "%~1"=="-NoPause" set "NO_PAUSE=1"
if defined CI set "NO_PAUSE=1"
if defined GITHUB_ACTIONS set "NO_PAUSE=1"
if defined TF_BUILD set "NO_PAUSE=1"

echo =======================================================================
echo          LocalPodcastLLMStudio - Automated Self-Healing Setup Script
echo =======================================================================
echo.

:: ---------------------------------------------------------------------------
:: 1. Check Existing Virtual Environment (.venv) First
:: ---------------------------------------------------------------------------
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "FOUND_BASE_PY="
set "FOUND_BASE_ARGS="

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        echo [OK] Existing virtual environment verified: .venv\Scripts\python.exe
        goto :setup_venv_packages
    )
)

:: ---------------------------------------------------------------------------
:: 2. Discover Base Python 3.10+ Runtime to Create Virtual Environment
:: ---------------------------------------------------------------------------
echo Searching for Python 3.10+ runtime...

:: Check 'python' command
where python >nul 2>nul
if !ERRORLEVEL! equ 0 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        set "FOUND_BASE_PY=python"
        set "FOUND_BASE_ARGS="
        goto :found_python
    )
)

:: Check 'python3' command
where python3 >nul 2>nul
if !ERRORLEVEL! equ 0 (
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        set "FOUND_BASE_PY=python3"
        set "FOUND_BASE_ARGS="
        goto :found_python
    )
)

:: Check 'py -3' command
where py >nul 2>nul
if !ERRORLEVEL! equ 0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        set "FOUND_BASE_PY=py"
        set "FOUND_BASE_ARGS=-3"
        goto :found_python
    )
)

:: Check standard LocalAppData installations
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if !ERRORLEVEL! equ 0 (
            set "FOUND_BASE_PY=%%D\python.exe"
            set "FOUND_BASE_ARGS="
            goto :found_python
        )
    )
)

:: Check uv Python installations
for /d %%D in ("%APPDATA%\uv\python\*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if !ERRORLEVEL! equ 0 (
            set "FOUND_BASE_PY=%%D\python.exe"
            set "FOUND_BASE_ARGS="
            goto :found_python
        )
    )
)

:found_python
if "%FOUND_BASE_PY%"=="" (
    echo [ERROR] Python 3.10 or higher was not found on your system!
    echo.
    echo Please install Python 3.10+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Make sure to check "Add python.exe to PATH" during installation.
    echo.
    set "FINAL_CODE=1"
    goto safe_exit
)

echo [OK] Base Python runtime verified:
"%FOUND_BASE_PY%" %FOUND_BASE_ARGS% --version
echo.

:: ---------------------------------------------------------------------------
:: 3. Create Virtual Environment (.venv)
:: ---------------------------------------------------------------------------
if not exist "%VENV_PY%" (
    echo [1/4] Creating virtual environment in .venv...
    "%FOUND_BASE_PY%" %FOUND_BASE_ARGS% -m venv "%VENV_DIR%"
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to create virtual environment in .venv.
        echo Please ensure you have write permissions in this directory.
        echo.
        set "FINAL_CODE=1"
        goto safe_exit
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment in .venv already exists.
)
echo.

:setup_venv_packages
:: ---------------------------------------------------------------------------
:: 4. Upgrade pip inside Virtual Environment
:: ---------------------------------------------------------------------------
echo [2/4] Upgrading pip in virtual environment...
"%VENV_PY%" -m pip install --upgrade pip --quiet
echo [OK] Pip upgraded.
echo.

:: ---------------------------------------------------------------------------
:: 5. Install Dependencies inside Virtual Environment
:: ---------------------------------------------------------------------------
echo [3/4] Installing dependencies...
if exist "requirements.txt" (
    echo Installing runtime dependencies from requirements.txt...
    "%VENV_PY%" -m pip install -r requirements.txt
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to install runtime dependencies from requirements.txt.
        set "FINAL_CODE=1"
        goto safe_exit
    )
)

if exist "requirements-dev.txt" (
    echo Installing development and build dependencies from requirements-dev.txt...
    "%VENV_PY%" -m pip install -r requirements-dev.txt --quiet
    if !ERRORLEVEL! neq 0 (
        echo [WARN] Could not install all dev dependencies. Core runtime is still operational.
    )
)
echo [OK] Dependencies installed successfully.
echo.

:: ---------------------------------------------------------------------------
:: 6. Run Preflight Diagnostics
:: ---------------------------------------------------------------------------
echo [4/4] Running environment diagnostics...
echo -----------------------------------------------------------------------
"%VENV_PY%" check_env.py
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Preflight environment check reported errors.
    set "FINAL_CODE=1"
    goto safe_exit
)
echo -----------------------------------------------------------------------
echo.
echo =======================================================================
echo Setup complete!
echo To launch LocalPodcastLLMStudio at any time:
echo   1. Activate virtual environment:  .venv\Scripts\activate
echo   2. Start application:             python app.py
echo =======================================================================
echo.
set "FINAL_CODE=0"
goto safe_exit

:: ---------------------------------------------------------------------------
:: Helper Routine: Safe Exit with CI / Interactive Pause Handling
:: ---------------------------------------------------------------------------
:safe_exit
if "%FINAL_CODE%"=="" set "FINAL_CODE=0"
if "%NO_PAUSE%"=="0" (
    echo.
    pause
)
exit /b %FINAL_CODE%
