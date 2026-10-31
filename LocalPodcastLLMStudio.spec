# -*- mode: python ; coding: utf-8 -*-
"""
LocalPodcastLLMStudio - PyInstaller Specification File
Universal 100% Local AI Podcast Desktop Application
Bundles CustomTkinter Fluent Dark GUI, Tokyo Night TUI, Headless CLI,
Local Piper TTS / SAPI5 Voice Engine, PyPDF Document Parser,
Zero-FFmpeg MP3/WAV Stitcher, and Native MCI Audio Player.
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

SPEC_ROOT = os.path.abspath(SPECPATH) if "SPECPATH" in globals() else os.path.abspath(os.getcwd())

# ---------------------------------------------------------------------------
# 1. Collect Data Assets & Resources
# ---------------------------------------------------------------------------
datas = []
binaries = []
hiddenimports = []

for pkg in ["customtkinter", "pypdf", "certifi", "requests", "rich"]:
    try:
        t_datas, t_binaries, t_hidden = collect_all(pkg)
        datas += t_datas
        binaries += t_binaries
        hiddenimports += t_hidden
    except Exception:
        datas += collect_data_files(pkg)
        hiddenimports += collect_submodules(pkg)

# Include local application assets and voice models if present
assets_dir = os.path.join(SPEC_ROOT, "assets")
models_dir = os.path.join(SPEC_ROOT, "models")
icon_path = os.path.join(assets_dir, "icon.ico")

if os.path.isdir(assets_dir):
    datas.append((assets_dir, "assets"))
if os.path.isdir(models_dir):
    datas.append((models_dir, "models"))

# Core application modules
hiddenimports += [
    "core",
    "core.exceptions",
    "core.io_utils",
    "core.logger",
    "core.extractor",
    "core.prompts",
    "core.parser",
    "core.ollama",
    "core.tts",
    "core.mp3_stitcher",
    "core.pipeline",
    "core.player",
    "ui",
    "ui.theme",
    "ui.about_dialog",
    "ui.widgets",
    "ui.main_window",
    "tui",
    "tui.__main__",
    "cli",
    "check_env",
    "asyncio",
    "certifi",
    "requests",
    "rich",
    "ctypes",
    "ctypes.wintypes",
]

# ---------------------------------------------------------------------------
# 2. Analysis Configuration
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(SPEC_ROOT, "app.py")],
    pathex=[SPEC_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter.test",
        "unittest",
        "test",
        "tests",
        "pytest",
        "_pytest",
        "IPython",
        "matplotlib",
        "scipy",
        "pandas",
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
    name="LocalPodcastLLMStudio",
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
    icon=icon_path if os.path.isfile(icon_path) else None,
)
