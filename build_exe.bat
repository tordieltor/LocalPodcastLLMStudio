@echo off
setlocal enabledelayedexpansion
title PodcastStudio - One-Click Executable Builder

echo =======================================================================
echo          PodcastStudio - PyInstaller One-Click Build Pipeline
echo =======================================================================
echo.

:: ---------------------------------------------------------------------------
:: 1. Discover Python Executable (.venv, venv, or system PATH)
:: ---------------------------------------------------------------------------
set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo [1/5] Using local virtual environment: .venv\Scripts\python.exe
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
    echo [1/5] Using local virtual environment: venv\Scripts\python.exe
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=py -3"
        echo [1/5] Using system Python Launcher (py -3)
    ) else (
        where python >nul 2>nul
        if %ERRORLEVEL% equ 0 (
            set "PYTHON_EXE=python"
            echo [1/5] Using system Python from PATH
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] No Python runtime could be found!
    echo.
    echo Please install Python 3.10 or newer from:
    echo   https://www.python.org/downloads/
    echo Ensure 'Add python.exe to PATH' is checked during installation.
    echo.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: 2. Verify Python Version >= 3.10
:: ---------------------------------------------------------------------------
%PYTHON_EXE% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 3.10+ is required to build PodcastStudio.
    echo Detected Python version:
    %PYTHON_EXE% --version
    echo.
    pause
    exit /b 1
)
echo [OK] Python runtime verified.
echo.

:: ---------------------------------------------------------------------------
:: 3. Verify / Install PyInstaller
:: ---------------------------------------------------------------------------
echo [2/5] Verifying PyInstaller installation...
%PYTHON_EXE% -c "import PyInstaller" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo PyInstaller is not installed in the target Python environment.
    echo Installing PyInstaller package...
    %PYTHON_EXE% -m pip install "pyinstaller>=6.4.0"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install PyInstaller.
        echo Please check your internet connection or install manually with:
        echo   pip install pyinstaller
        echo.
        pause
        exit /b 1
    )
    echo [OK] PyInstaller installed successfully.
) else (
    echo [OK] PyInstaller is available.
)
echo.

:: ---------------------------------------------------------------------------
:: 4. Clean Previous Build Artifacts
:: ---------------------------------------------------------------------------
echo [3/5] Cleaning previous build artifacts (build, dist)...
if exist "build" (
    rmdir /s /q "build"
    echo   Removed build directory.
)
if exist "dist" (
    rmdir /s /q "dist"
    echo   Removed dist directory.
)
echo [OK] Build workspace cleaned.
echo.

:: ---------------------------------------------------------------------------
:: 5. Execute PyInstaller Build
:: ---------------------------------------------------------------------------
echo [4/5] Compiling standalone executable with PyInstaller...
echo Executing: %PYTHON_EXE% -m PyInstaller --clean PodcastStudio.spec
echo -----------------------------------------------------------------------

if exist "PodcastStudio.spec" (
    %PYTHON_EXE% -m PyInstaller --clean PodcastStudio.spec
) else (
    echo [WARN] PodcastStudio.spec not found, falling back to CLI flags...
    %PYTHON_EXE% -m PyInstaller --noconsole --onefile --name "PodcastStudio" --clean --collect-all customtkinter --collect-all edge_tts --collect-all pypdf --collect-all certifi app.py
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo -----------------------------------------------------------------------
    echo [ERROR] PyInstaller build failed with exit code %ERRORLEVEL%.
    echo Please review the build errors printed above.
    echo -----------------------------------------------------------------------
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo -----------------------------------------------------------------------
echo [OK] PyInstaller compilation completed.
echo.

:: ---------------------------------------------------------------------------
:: 6. Validate Output Binary and Report Sizing
:: ---------------------------------------------------------------------------
echo [5/5] Validating output binary...

if exist "dist\PodcastStudio.exe" (
    for %%I in ("dist\PodcastStudio.exe") do set "EXE_BYTES=%%~zI"
    set /a "EXE_MB=!EXE_BYTES! / 1048576"
    
    echo.
    echo =======================================================================
    echo                     BUILD SUCCESSFUL!
    echo =======================================================================
    echo   Output Binary : dist\PodcastStudio.exe
    echo   File Size     : !EXE_MB! MB (!EXE_BYTES! bytes)
    echo   Mode          : Single-File Executable (--noconsole, Standalone)
    echo =======================================================================
    echo.
    echo PodcastStudio.exe is ready for distribution and local execution!
    echo To launch the application, run:
    echo   dist\PodcastStudio.exe
    echo.
) else (
    echo.
    echo [ERROR] dist\PodcastStudio.exe was not found after compilation!
    echo Build may have failed silently or generated in an unexpected location.
    echo.
    pause
    exit /b 1
)

echo.
pause
exit /b 0
