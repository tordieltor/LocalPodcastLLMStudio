# 🎙️ PodcastStudio

> **Universal, 100% Local AI Podcast Desktop Studio**  
> Transform any document, article, raw text, or topic idea into an authentic, broadcast-quality two-host conversational podcast with **0.00 NOK / $0.00 cloud API costs**.

---

## 🌟 Key Highlights

- **Zero Cloud API Costs**: Runs 100% locally on your machine with local Ollama LLMs and free Edge-TTS neural speech synthesis.
- **Document-Agnostic Ingestion**: Supports `.pdf`, `.md`, and `.txt` files as well as direct text paste and "Generate from Scratch" prompt mode.
- **Bilingual Two-Host Dialogue**:
  - 🇳🇴 **Norsk (Bokmål)**: **Kari** (`nb-NO-PernilleNeural`) & **Ola** (`nb-NO-FinnNeural`)
  - 🇬🇧 **English**: **Jenny** (`en-US-JennyNeural`) & **Guy** (`en-US-GuyNeural`)
- **4 Episode Duration Presets**:
  - ⚡ **Quick Summary**: ~2–3 mins (6–8 dialogue turns)
  - 🎙️ **Standard Episode**: ~5–7 mins (12–16 dialogue turns)
  - 🔍 **Deep Dive**: ~10–15 mins (20–26 dialogue turns)
  - 📚 **Extended In-Depth**: ~25–30 mins (45–60 dialogue turns)
- **Tone & Style Controls**: Casual & Lively, Analytical & Educational, or Lively Debate.
- **Voice Pace Modifier**: Fine-tune speaking speed (-10% to +15%) for natural rhythm.
- **Zero-FFmpeg Binary Stitching**: Pure Python MP3 frame concatenation removes headers and seamlessly joins audio chunks without external dependencies.
- **Interactive Script Review**: Inspect and edit dialogue turns before synthesis, or run one-click end-to-end generation.
- **Integrated Native Audio Player**: Play, pause, seek, and export generated audio directly inside the app.
- **Automated Self-Healing Setup**: Prerequisite diagnostic tool (`check_env.py`) and one-click bootstrap scripts (`setup.bat` / `setup.ps1`).
- **One-Click Standalone Executable**: Compile into a single `PodcastStudio.exe` with zero terminal popups.

---

## 📋 System Architecture

```text
[ Input: Topic / TXT / MD / PDF ]
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│          Desktop GUI (CustomTkinter Fluent Dark)            │
│  - Multi-Format File Picker / Scratch Prompt Box            │
│  - Dynamic Ollama Model Selector & Language Switcher        │
│  - Episode Length (Quick, Standard, Deep Dive, In-Depth)    │
│  - Style & Voice Rate Fine-Tuning                           │
│  - Live Step-by-Step Progress & Real-Time Status Bar        │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
                ▼                             ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐
│   1. Scriptwriter (Ollama)  │ │   2. Voice Synth (Edge-TTS) │
│ - Local LLM REST API        │ │ - Free HD Neural Voices     │
│ - 2-Host Dynamic Dialogue   │ │ - Pernille & Finn (NO)      │
│ - Multi-Tier JSON Parser    │ │ - Jenny & Guy (EN)          │
│ - Script Review Panel       │ │ - Async Worker Pool         │
└───────────────┬─────────────┘ └─────────────┬───────────────┘
                │                             │
                └──────────────┬──────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   3. Assembly & Playback                    │
│ - Pure Python MP3 Frame Concatenation (Zero ffmpeg needed)  │
│ - Built-in Native Windows Media Player                      │
│ - Custom Destination Folder & "Save MP3 As..." Export       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.10+** (ensure "Add python.exe to PATH" was selected during install).
- **Ollama**: Download and install from [ollama.com](https://ollama.com).
  - Recommended models:
    ```powershell
    ollama pull mistral-nemo:latest
    # or
    ollama pull llama3.1:8b
    # or
    ollama pull qwen2.5:7b
    ```

### 2. Automated Self-Healing Setup
Run the setup script for your shell:

**PowerShell:**
```powershell
.\setup.ps1
```

**Command Prompt / Batch:**
```bat
setup.bat
```

The setup script automatically:
1. Verifies Python 3.10+.
2. Creates the local virtual environment (`.venv`).
3. Installs all required runtime dependencies (`customtkinter`, `edge-tts`, `pypdf`, `requests`, `pyinstaller`).
4. Runs `check_env.py` to diagnose Ollama connectivity and installed models.

### 3. Run from Source
```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Launch application
python app.py
```

---

## 📦 One-Click Executable Compilation (`.exe`)

To compile a standalone, windowed Windows executable (`dist/PodcastStudio.exe`):

**PowerShell:**
```powershell
.\build_exe.ps1
```

**Batch:**
```bat
build_exe.bat
```

The resulting executable is located at `dist/PodcastStudio.exe`. It bundles Python, CustomTkinter assets, Edge-TTS, and all dependencies into a single file with `--noconsole` (no black terminal windows).

---

## 🔍 Diagnostic Preflight Tool (`check_env.py`)

Run the preflight diagnostic tool at any time to verify system health:

```powershell
# Formatted ANSI terminal report
python check_env.py

# Machine-readable JSON output
python check_env.py --json

# Silent returncode check (0 = OK, 1 = Issues detected)
python check_env.py --quiet
```

---

## 📂 Project Structure

```text
epic-hubble/
├── app.py                     # Main application entry point
├── check_env.py               # Preflight environment diagnostics & model audit
├── setup.bat / setup.ps1      # Automated self-healing environment setup
├── build_exe.bat / build_exe.ps1 # One-click PyInstaller build pipeline
├── PodcastStudio.spec         # PyInstaller spec configuration
├── requirements.txt           # Pinned production runtime dependencies
├── requirements-dev.txt       # Development & build tools
│
├── core/                      # Core processing engines
│   ├── extractor.py           # Multi-format document parser (.pdf, .md, .txt)
│   ├── prompts.py             # Prompt engineering, persona & duration presets
│   ├── parser.py              # 6-tier resilient dialogue JSON parser
│   ├── ollama.py              # Local Ollama REST client & turn generator
│   ├── tts.py                 # Async Edge-TTS neural speech synthesizer
│   ├── mp3_stitcher.py        # Zero-dependency pure Python MP3 frame stitcher
│   └── player.py              # Native Windows MCI audio player & exporter
│
├── ui/                        # User interface layer
│   ├── theme.py               # Fluent Dark styling, palette, typography
│   ├── widgets.py             # Cards, headers, sliders, dialogue cards, error dialogs
│   └── main_window.py         # Main UI window & background worker queue loop
│
└── tests/                     # Comprehensive test suite
    ├── conftest.py            # Fixtures & mock environments
    ├── test_check_env.py      # Diagnostic checker tests
    ├── test_extractor.py      # PDF, Markdown, and TXT parsing tests
    ├── test_prompts.py        # Bilingual & format preset tests
    ├── test_parser.py         # Resilient multi-tier JSON parser tests
    ├── test_ollama.py         # Ollama REST API mock tests
    ├── test_tts.py            # Edge-TTS synthesizer tests
    ├── test_mp3_stitcher.py   # Pure Python MP3 frame stitching tests
    ├── test_player.py         # Audio playback & export tests
    ├── test_ui.py             # CustomTkinter GUI lifecycle tests
    └── test_e2e_pipeline.py   # End-to-end integration tests
```

---

## 🛡️ Troubleshooting & Tips

- **Ollama Offline**: Start the Ollama desktop application or run `ollama serve` in a terminal.
- **No Models Found**: Pull a supported model with `ollama pull mistral-nemo:latest`.
- **Edge-TTS Connection**: Edge-TTS neural voices require active outbound HTTPS access (`speech.platform.bing.com:443`).
- **Antivirus Warnings**: If compiling with PyInstaller, whitelist `dist/PodcastStudio.exe` if your antivirus flags freshly generated binaries.

---

## 📄 License
MIT License. Free for personal and commercial use.
