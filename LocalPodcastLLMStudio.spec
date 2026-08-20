# -*- mode: python ; coding: utf-8 -*-
"""
LocalPodcastLLMStudio - PyInstaller Specification File
Universal 100% Local AI Podcast Desktop Application
Bundles CustomTkinter Fluent Dark GUI, Edge-TTS Neural Voice Engine,
PyPDF Document Parser, Zero-FFmpeg MP3 Stitcher, and Native MCI Audio Player.
"""

import os
import sys
import importlib.util
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Increase recursion limit to handle deep AST graphs during CustomTkinter/aiohttp analysis
sys.setrecursionlimit(5000)

block_cipher = None

# Determine base directory reliably regardless of invocation method
spec_dir = os.path.abspath(
    SPECPATH if "SPECPATH" in globals()
    else os.path.dirname(__file__) if "__file__" in globals()
    else os.getcwd()
)

def safe_collect_data_files(package_name: str):
    """Safely collect data files if package is installed."""
    try:
        if importlib.util.find_spec(package_name) is not None:
            return collect_data_files(package_name)
    except Exception:
        pass
    return []

def safe_collect_submodules(package_name: str):
    """Safely collect submodules if package is installed."""
    try:
        if importlib.util.find_spec(package_name) is not None:
            return collect_submodules(package_name)
    except Exception:
        pass
    return []

# ---------------------------------------------------------------------------
# 1. Collect Data Assets & Resources
# ---------------------------------------------------------------------------
datas = []

# Collect themes, fonts, and icon assets for CustomTkinter
datas += safe_collect_data_files('customtkinter')

# Collect bundled resources for Edge-TTS
datas += safe_collect_data_files('edge_tts')

# Collect SSL CA certificates bundle from Certifi for secure Edge-TTS WebSockets
datas += safe_collect_data_files('certifi')

# Collect encoding tables and data files for PyPDF
datas += safe_collect_data_files('pypdf')

# Include local application assets folder if present
assets_path = os.path.join(spec_dir, 'assets')
if os.path.exists(assets_path):
    datas.append((assets_path, 'assets'))

# ---------------------------------------------------------------------------
# 2. Collect Hidden Imports & Dynamic Submodules
# ---------------------------------------------------------------------------
hiddenimports = []

# Package submodules
hiddenimports += safe_collect_submodules('customtkinter')
hiddenimports += safe_collect_submodules('edge_tts')
hiddenimports += safe_collect_submodules('pypdf')
hiddenimports += safe_collect_submodules('requests')

# Conditionally collect optional websockets submodule if present
if importlib.util.find_spec('websockets') is not None:
    hiddenimports += safe_collect_submodules('websockets')

# Core application modules
hiddenimports += [
    'core',
    'core.extractor',
    'core.prompts',
    'core.parser',
    'core.ollama',
    'core.tts',
    'core.mp3_stitcher',
    'core.player',
    'ui',
    'ui.theme',
    'ui.widgets',
    'ui.about_dialog',
    'ui.main_window',
]

# Networking, AsyncIO, and SSL dependencies
hiddenimports += [
    'aiohttp',
    'asyncio',
    'certifi',
    'requests',
    'urllib.request',
    'urllib.error',
    'urllib.parse',
    'http.client',
    'ssl',
    'socket',
]

# Windows system, threading, and runtime utilities
hiddenimports += [
    'ctypes',
    'ctypes.wintypes',
    'threading',
    'queue',
    'subprocess',
    'shutil',
    'tempfile',
    'uuid',
    'json',
    're',
    'struct',
    'math',
    'traceback',
    'time',
    'platform',
]

# ---------------------------------------------------------------------------
# 3. Analysis Configuration
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(spec_dir, 'app.py')],
    pathex=[spec_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'unittest',
        'test',
        'tests',
        'pytest',
        '_pytest',
        'IPython',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ---------------------------------------------------------------------------
# 4. Pure Python Archive (PYZ)
# ---------------------------------------------------------------------------
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# ---------------------------------------------------------------------------
# 5. Executable Target (Single-File Standalone Binary)
# ---------------------------------------------------------------------------
icon_file = os.path.join(spec_dir, 'assets', 'icon.ico')

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LocalPodcastLLMStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # False enables native Windows windowed mode (--noconsole)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file if os.path.exists(icon_file) else None,
)
