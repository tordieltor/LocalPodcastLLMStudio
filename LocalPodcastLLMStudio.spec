# -*- mode: python ; coding: utf-8 -*-
"""
LocalPodcastLLMStudio - PyInstaller Specification File
Universal 100% Local AI Podcast Desktop Application
Bundles CustomTkinter Fluent Dark GUI, Edge-TTS Neural Voice Engine,
PyPDF Document Parser, Zero-FFmpeg MP3 Stitcher, and Native MCI Audio Player.
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

block_cipher = None

# Ensure build working directories exist
os.makedirs('build/LocalPodcastLLMStudio', exist_ok=True)
os.makedirs('dist', exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Collect Data Assets & Resources
# ---------------------------------------------------------------------------
datas = []
binaries = []
hiddenimports = []

for pkg in ['customtkinter', 'pypdf', 'certifi', 'requests']:
    try:
        t_datas, t_binaries, t_hidden = collect_all(pkg)
        datas += t_datas
        binaries += t_binaries
        hiddenimports += t_hidden
    except Exception:
        datas += collect_data_files(pkg)
        hiddenimports += collect_submodules(pkg)

# Include local application assets and voice models if present
if os.path.exists('assets'):
    datas.append(('assets', 'assets'))
if os.path.exists('models'):
    datas.append(('models', 'models'))

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
    'aiohttp',
    'asyncio',
    'certifi',
    'requests',
    'ctypes',
    'ctypes.wintypes',
]

# ---------------------------------------------------------------------------
# 2. Analysis Configuration
# ---------------------------------------------------------------------------
a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
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
# 3. Pure Python Archive (PYZ)
# ---------------------------------------------------------------------------
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# ---------------------------------------------------------------------------
# 4. Executable Target (Single-File Standalone Binary)
# ---------------------------------------------------------------------------
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
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)
