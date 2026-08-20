# -*- mode: python ; coding: utf-8 -*-
"""
PodcastStudio - PyInstaller Specification File
Universal 100% Local AI Podcast Desktop Application
Bundles CustomTkinter Fluent Dark GUI, Edge-TTS Neural Voice Engine,
PyPDF Document Parser, Zero-FFmpeg MP3 Stitcher, and Native MCI Audio Player.
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ---------------------------------------------------------------------------
# 1. Collect Data Assets & Resources
# ---------------------------------------------------------------------------
datas = []

# Collect themes, fonts, and icon assets for CustomTkinter
datas += collect_data_files('customtkinter')

# Collect bundled resources for Edge-TTS
datas += collect_data_files('edge_tts')

# Collect SSL CA certificates bundle from Certifi for secure Edge-TTS WebSockets
datas += collect_data_files('certifi')

# Collect encoding tables and data files for PyPDF
datas += collect_data_files('pypdf')

# Include local application assets folder if present
if os.path.exists('assets'):
    datas.append(('assets', 'assets'))

# ---------------------------------------------------------------------------
# 2. Collect Hidden Imports & Dynamic Submodules
# ---------------------------------------------------------------------------
hiddenimports = []

# Package submodules
hiddenimports += collect_submodules('customtkinter')
hiddenimports += collect_submodules('edge_tts')
hiddenimports += collect_submodules('pypdf')
hiddenimports += collect_submodules('requests')

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
    'ui.main_window',
]

# Networking, AsyncIO, and SSL dependencies
hiddenimports += [
    'aiohttp',
    'asyncio',
    'websockets',
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
    ['app.py'],
    pathex=['.'],
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
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PodcastStudio',
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
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)
