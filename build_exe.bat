@echo off
setlocal enabledelayedexpansion
title LocalPodcastLLMStudio - One-Click Executable Builder

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
echo          LocalPodcastLLMStudio - PyInstaller One-Click Build Pipeline
echo =======================================================================
echo.

:: ---------------------------------------------------------------------------
:: 1. Discover Python Executable (.venv, venv, or system PATH)
:: ---------------------------------------------------------------------------
set "PY_BIN="
set "PY_ARGS="

if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=%~dp0.venv\Scripts\python.exe"
    set "PY_ARGS="
    echo [1/5] Using local virtual environment: .venv\Scripts\python.exe
) else if exist "venv\Scripts\python.exe" (
    set "PY_BIN=%~dp0venv\Scripts\python.exe"
    set "PY_ARGS="
    echo [1/5] Using local virtual environment: venv\Scripts\python.exe
) else (
    :: Test python command
    where python >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if !ERRORLEVEL! equ 0 (
            set "PY_BIN=python"
            set "PY_ARGS="
            echo [1/5] Using system Python from PATH
        )
    )
    
    :: Test python3 command if python failed
    if "!PY_BIN!"=="" (
        where python3 >nul 2>nul
        if !ERRORLEVEL! equ 0 (
            python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
            if !ERRORLEVEL! equ 0 (
                set "PY_BIN=python3"
                set "PY_ARGS="
                echo [1/5] Using system Python3 from PATH
            )
        )
    )
    
    :: Test py -3 command if python/python3 failed
    if "!PY_BIN!"=="" (
        where py >nul 2>nul
        if !ERRORLEVEL! equ 0 (
            py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
            if !ERRORLEVEL! equ 0 (
                set "PY_BIN=py"
                set "PY_ARGS=-3"
                echo [1/5] Using system Python Launcher (py -3)
            )
        )
    )
)

if "!PY_BIN!"=="" (
    echo [ERROR] No compatible Python 3.10+ runtime could be found!
    echo.
    echo Please install Python 3.10 or newer from:
    echo   https://www.python.org/downloads/
    echo Ensure 'Add python.exe to PATH' is checked during installation.
    echo.
    set "FINAL_CODE=1"
    goto safe_exit
)

:: ---------------------------------------------------------------------------
:: 2. Verify Python Version >= 3.10
:: ---------------------------------------------------------------------------
"%PY_BIN%" %PY_ARGS% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Python 3.10+ is required to build LocalPodcastLLMStudio.
    echo Detected Python version:
    "%PY_BIN%" %PY_ARGS% --version
    echo.
    set "FINAL_CODE=1"
    goto safe_exit
)
echo [OK] Python runtime verified.
echo.

:: ---------------------------------------------------------------------------
:: 3. Verify / Install PyInstaller
:: ---------------------------------------------------------------------------
echo [2/5] Verifying PyInstaller installation...
"%PY_BIN%" %PY_ARGS% -c "import PyInstaller" >nul 2>nul
if !ERRORLEVEL! neq 0 (
    echo PyInstaller is not installed in the target Python environment.
    echo Installing PyInstaller package...
    "%PY_BIN%" %PY_ARGS% -m pip install "pyinstaller>=6.4.0"
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to install PyInstaller.
        echo Please check your internet connection or install manually with:
        echo   pip install pyinstaller
        echo.
        set "FINAL_CODE=1"
        goto safe_exit
    )
    echo [OK] PyInstaller installed successfully.
) else (
    echo [OK] PyInstaller is available.
)
echo.

:: ---------------------------------------------------------------------------
:: 4. Clean Previous Build Artifacts & Check Process Locks
:: ---------------------------------------------------------------------------
echo [3/5] Cleaning previous build artifacts (build, dist)...

if exist "dist\LocalPodcastLLMStudio.exe" (
    taskkill /f /im LocalPodcastLLMStudio.exe >nul 2>nul
    del /f /q "dist\LocalPodcastLLMStudio.exe" >nul 2>nul
    if exist "dist\LocalPodcastLLMStudio.exe" (
        timeout /t 1 /nobreak >nul 2>nul
        del /f /q "dist\LocalPodcastLLMStudio.exe" >nul 2>nul
    )
    if exist "dist\LocalPodcastLLMStudio.exe" (
        echo [ERROR] dist\LocalPodcastLLMStudio.exe is currently locked by a running process!
        echo Please close all running instances of LocalPodcastLLMStudio and retry.
        echo.
        set "FINAL_CODE=1"
        goto safe_exit
    )
)

if exist "build" (
    rmdir /s /q "build" >nul 2>nul
    if not exist "build" echo   Removed build directory.
)
if exist "dist" (
    rmdir /s /q "dist" >nul 2>nul
    if not exist "dist" echo   Removed dist directory.
)
echo [OK] Build workspace cleaned.
echo.

:: ---------------------------------------------------------------------------
:: 5. Execute PyInstaller Build
:: ---------------------------------------------------------------------------
echo [4/5] Compiling standalone executable with PyInstaller...
echo Executing: "%PY_BIN%" %PY_ARGS% -m PyInstaller --clean LocalPodcastLLMStudio.spec
echo -----------------------------------------------------------------------

if exist "LocalPodcastLLMStudio.spec" (
    "%PY_BIN%" %PY_ARGS% -m PyInstaller --clean LocalPodcastLLMStudio.spec
    if errorlevel 1 (
        echo.
        echo -----------------------------------------------------------------------
        echo [ERROR] PyInstaller build failed with exit code %ERRORLEVEL%.
        echo Please review the build errors printed above.
        echo -----------------------------------------------------------------------
        echo.
        set "FINAL_CODE=1"
        goto safe_exit
    )
) else (
    echo [WARN] LocalPodcastLLMStudio.spec not found, falling back to CLI flags...
    "%PY_BIN%" %PY_ARGS% -m PyInstaller --noconsole --onefile --name "LocalPodcastLLMStudio" --clean --collect-all customtkinter --collect-all edge_tts --collect-all pypdf --collect-all certifi app.py
    if errorlevel 1 (
        echo.
        echo -----------------------------------------------------------------------
        echo [ERROR] PyInstaller build failed with exit code %ERRORLEVEL%.
        echo Please review the build errors printed above.
        echo -----------------------------------------------------------------------
        echo.
        set "FINAL_CODE=1"
        goto safe_exit
    )
)

echo -----------------------------------------------------------------------
echo [OK] PyInstaller compilation completed.
echo.

:: ---------------------------------------------------------------------------
:: 6. Validate Output Binary and Report Sizing
:: ---------------------------------------------------------------------------
echo [5/5] Validating output binary...

if not exist "dist\LocalPodcastLLMStudio.exe" (
    echo.
    echo [ERROR] dist\LocalPodcastLLMStudio.exe was not found after compilation!
    echo Build may have failed silently or generated in an unexpected location.
    echo.
    set "FINAL_CODE=1"
    goto safe_exit
)

for %%I in ("dist\LocalPodcastLLMStudio.exe") do set "EXE_BYTES=%%~zI"
set /a "EXE_MB=EXE_BYTES / 1048576"

echo.
echo =======================================================================
echo                     BUILD SUCCESSFUL
echo =======================================================================
echo   Output Binary : dist\LocalPodcastLLMStudio.exe
echo   File Size     : !EXE_MB! MB (!EXE_BYTES! bytes)
echo   Mode          : Single-File Executable (--noconsole, Standalone)
echo =======================================================================
echo.
echo LocalPodcastLLMStudio.exe is ready for distribution and local execution
echo To launch the application, run:
echo   dist\LocalPodcastLLMStudio.exe
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
