# 🎙️ LocalPodcastLLMStudio

> **Universal, 100% Local AI Podcast Desktop Studio**  
> Transform any document, article, raw text, or topic idea into an authentic, broadcast-quality two-host conversational podcast with **0.00 NOK / $0.00 cloud API costs**.

---

<p align="center">
  <a href="https://github.com/tordieltor/LocalPodcastLLMStudio/actions/workflows/ci.yml">
    <img src="https://github.com/tordieltor/LocalPodcastLLMStudio/actions/workflows/ci.yml/badge.svg" alt="CI Status" />
  </a>
  <a href="https://github.com/tordieltor/LocalPodcastLLMStudio/releases">
    <img src="https://img.shields.io/github/v/release/tordieltor/LocalPodcastLLMStudio?style=flat-square&color=blue" alt="Latest Release" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square" alt="License: MIT" />
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square" alt="Python 3.10+" />
  </a>
  <a href="https://github.com/astral-sh/ruff">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Code Style: Ruff" />
  </a>
  <a href="SECURITY.md">
    <img src="https://img.shields.io/badge/Security-Policy-green.svg?style=flat-square" alt="Security Policy" />
  </a>
  <a href="https://github.com/tordieltor/LocalPodcastLLMStudio">
    <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg?style=flat-square" alt="Platform: Windows" />
  </a>
</p>

---

## 🌟 Key Highlights

- **100% Offline & Private (Zero Cloud Data Sharing)**: Runs entirely on your local workstation utilizing local Ollama LLMs and local Piper TTS ONNX neural speech synthesis. Zero data is shared with the cloud or Microsoft.
- **Document-Agnostic Ingestion**: Ingests `.pdf`, `.md`, and `.txt` documents, clipboard text, or generates directly from a prompt with "Generate from Scratch".
- **Bilingual Two-Host Dialogue**:
  - 🇳🇴 **Norsk (Bokmål)**: **Kari** & **Ola** (`no_NO-torkil-medium` neural personas)
  - 🇬🇧 **English**: **Host 1** (`en_US-lessac-medium`) & **Host 2** (`en_US-ryan-medium`)
- **4 Episode Duration Presets**:
  - ⚡ **Quick Summary**: ~2–3 mins (6–8 dialogue turns)
  - 🎙️ **Standard Episode**: ~5–7 mins (12–16 dialogue turns)
  - 🔍 **Deep Dive**: ~10–15 mins (20–26 dialogue turns)
  - 📚 **Extended In-Depth**: ~25–30 mins (45–60 dialogue turns)
- **Tone & Style Controls**: Fine-tune conversation style (Casual & Lively, Analytical & Educational, Lively Debate).
- **Voice Pace Fine-Tuning**: Adjust speaking speed from -10% to +15% for optimal natural rhythm.
- **Interactive Tokyo Night TUI (`tui.py`)**: Full-screen, responsive terminal interface for Windows PowerShell and Command Prompt (CMD) with non-blocking workers and 8 specialized views.
- **Scriptable CLI Engine (`cli.py`)**: Run full unattended podcast generation pipelines from the command line, generate rapidly with just a topic (`--topic`), or chain modular subcommands (`extract`, `generate-script`, `synthesize-audio`, `stitch`).
- **Zero-FFmpeg Binary Stitching**: Native pure-Python MPEG audio frame stitcher seamlessly concatenates MP3 turns without external tools.
- **Interactive Script Review**: Inspect and edit dialogue turns prior to synthesis, or trigger one-click end-to-end generation.
- **Integrated Native Audio Player**: Play, pause, seek, and export generated audio directly inside the application.
- **Automated Self-Healing Setup**: Automated preflight diagnostic tool (`check_env.py`) and bootstrap scripts (`setup.ps1` / `setup.bat`).
- **One-Click Standalone Executable**: Single portable `.exe` bundle with zero console popups (`--noconsole`).

---

## 📋 System Architecture

```text
[ Input: Topic / TXT / MD / PDF ]
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Interface Layer                       │
│  ┌───────────────────────────┐ ┌──────────────────────────┐ │
│  │ CustomTkinter Desktop GUI │ │ Tokyo Night Terminal TUI │ │
│  │ (python app.py)           │ │ (python tui.py)          │ │
│  └───────────────────────────┘ └──────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │       Scriptable CLI Pipeline & Chaining Engine        │ │
│  │       (python cli.py pipeline --topic "..." / -f ...)   │ │
│  └────────────────────────────────────────────────────────┘ │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
                ▼                             ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐
│   1. Scriptwriter (Ollama)  │ │   2. Voice Synth (Piper TTS)│
│ - Local LLM REST API        │ │ - 100% Offline ONNX Models  │
│ - 2-Host Dynamic Dialogue   │ │ - Kari & Ola (NO)           │
│ - 6-Tier Resilient Parser   │ │ - Host 1 & Host 2 (EN)      │
│ - Script Review Panel       │ │ - Async Worker Pool & Cache │
└───────────────┬─────────────┘ └─────────────┬───────────────┘
                │                             │
                └──────────────┬──────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                   3. Assembly & Playback                    │
│ - Pure Python MP3 Frame Concatenation (Zero ffmpeg needed)  │
│ - Built-in Native Windows Media Player (MCI)                │
│ - Custom Destination Folder & "Save MP3 As..." Export       │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚡ Quick Download: Standalone Windows Executable

If you want to use LocalPodcastLLMStudio without installing Python or setting up virtual environments, download the pre-compiled standalone binary:

1. Go to the [Latest GitHub Release](https://github.com/tordieltor/LocalPodcastLLMStudio/releases/latest).
2. Download `LocalPodcastLLMStudio-Windows-x64.zip` (or `LocalPodcastLLMStudio.exe`).
3. Extract the ZIP archive to your preferred location.
4. Launch `LocalPodcastLLMStudio.exe`.

### Binary Integrity & SHA256 Verification

To verify the integrity of your downloaded executable against the official release checksum:

#### Using PowerShell:
```powershell
Get-FileHash -Algorithm SHA256 .\LocalPodcastLLMStudio.exe
```

#### Using Windows Command Prompt:
```bat
certutil -hashfile LocalPodcastLLMStudio.exe SHA256
```

Compare the computed hash string with `LocalPodcastLLMStudio-SHA256.txt` published on the release page.

---

## 🚀 Quick Start Guide (Running from Source)

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

Run the automated setup script for your shell:

**PowerShell:**
```powershell
.\setup.ps1
```

**Command Prompt / Batch:**
```bat
setup.bat
```

The setup script automatically:
1. Verifies Python 3.10+ on system PATH.
2. Creates the local virtual environment (`.venv`).
3. Installs all required runtime and development dependencies.
4. Runs `check_env.py` to diagnose Ollama connectivity and installed models.

### 3. Launching Your Preferred Interface

#### Option A: Desktop GUI (Windows 11 Fluent Dark)
```powershell
python app.py
```

#### Option B: Interactive Terminal TUI (PowerShell / CMD)
```powershell
# Launch interactive Tokyo Night TUI dashboard
python tui.py

# Pre-load document or rapid topic directly into TUI
python tui.py --topic "The Future of AI"
python tui.py --file "docs/paper.pdf" --model llama3.1:8b
```

#### Option C: Headless Scriptable CLI & Pipeline Chaining
```powershell
# Rapid Topic-Only Generation (Zero documents required)
python cli.py pipeline --topic "Quantum Computing in 2026" --length quick --outdir ./output

# Fine-Grained Document Generation
python cli.py pipeline --file "docs/paper.pdf" --grounding strict --model qwen2.5:7b --outdir ./output

# Modular Pipeline Chaining
python cli.py extract -f "document.pdf" > extracted.txt
python cli.py generate-script --text "$(Get-Content extracted.txt -Raw)" --json > dialogue.json
python cli.py synthesize-audio --dialogue-json dialogue.json --outdir ./output
python cli.py stitch --input-dir ./output --output ./output/podcast.mp3
```

---

## 🖥️ Desktop & Terminal Shortcuts

Run the shortcut creator to generate desktop launch icons for both the GUI and Terminal TUI:

```powershell
.\create_desktop_shortcut.ps1
```

This creates:
- `LocalPodcastLLMStudio.lnk` (Desktop GUI)
- `LocalPodcastLLMStudio (Terminal TUI).lnk` (Terminal TUI)

---

## 📦 One-Click Executable Compilation

To compile your own standalone, windowed Windows executable (`dist/LocalPodcastLLMStudio.exe`):

**PowerShell:**
```powershell
.\build_exe.ps1
```

**Batch:**
```bat
build_exe.bat
```

The script cleans previous artifacts, executes PyInstaller with `LocalPodcastLLMStudio.spec`, and verifies the compiled binary size.

---

## 🔍 Diagnostic Preflight Tool (`check_env.py`)

Run the preflight diagnostic tool at any time to verify system health and Ollama configuration:

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
LocalPodcastLLMStudio/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml             # Structured bug report issue form
│   │   ├── feature_request.yml        # Structured feature request issue form
│   │   └── config.yml                 # Issue configuration & security links
│   ├── workflows/
│   │   ├── ci.yml                     # Multi-OS CI matrix (lint, typecheck, bandit, pytest)
│   │   └── release.yml                # Tagged release build & checksum deployment
│   ├── CODE_OF_CONDUCT.md             # Contributor Covenant v2.1
│   ├── CONTRIBUTING.md                # Development, quality gates & PR process
│   └── pull_request_template.md       # PR checklist and change summary template
│
├── core/                              # Core processing engines
│   ├── extractor.py                   # Multi-format document parser (.pdf, .md, .txt, topics)
│   ├── prompts.py                     # Dynamic prompt engineering & duration presets
│   ├── parser.py                      # 6-tier resilient dialogue JSON parser
│   ├── pipeline.py                    # Headless podcast generator service
│   ├── ollama.py                      # Local Ollama REST client & turn generator
│   ├── tts.py                         # 100% Offline Piper TTS neural voice synthesizer
│   ├── mp3_stitcher.py                # Zero-dependency pure Python MP3 frame stitcher
│   └── player.py                      # Native Windows MCI audio player & exporter
│
├── ui/                                # Desktop GUI layer (CustomTkinter)
│   ├── theme.py                       # Fluent Dark styling, palette, typography
│   ├── widgets.py                     # Cards, headers, sliders, dialogue cards, error dialogs
│   ├── about_dialog.py                # About & diagnostic info dialog
│   └── main_window.py                 # Main GUI window & background worker queue loop
│
├── tui/                               # Terminal User Interface layer (PowerShell / CMD)
│   ├── terminal.py                    # Windows ANSI controller & VTP setup
│   ├── input.py                       # Non-blocking msvcrt keyboard input reader
│   ├── state.py                       # Reactive thread-safe TUI state container
│   ├── components.py                  # Cards, HotkeyBar, TimeSlider, tables, modals
│   ├── workers.py                     # Background worker threads for async operations
│   └── screens/                       # 8 interactive full-screen views
│
├── app.py                             # Desktop GUI main entry point
├── tui.py                             # Interactive Terminal User Interface launcher
├── cli.py                             # Scriptable CLI pipeline & chaining engine
├── check_env.py                       # Preflight environment diagnostics & model audit
├── create_desktop_shortcut.ps1 / .bat # Desktop shortcuts creation utility
├── setup.bat / setup.ps1              # Automated self-healing environment setup
├── build_exe.bat / build_exe.ps1      # One-click PyInstaller build pipeline
├── LocalPodcastLLMStudio.spec         # PyInstaller packaging specification
├── pyproject.toml                     # Centralized tooling configuration (ruff, mypy, pytest)
├── requirements.txt                   # Production runtime dependencies
├── requirements-dev.txt               # Development & build tools
├── LICENSE                            # MIT License
├── SECURITY.md                        # Security policy & vulnerability reporting
└── README.md                          # Project documentation
```

---

## 🛡️ Security & Privacy

LocalPodcastLLMStudio is designed with privacy and security as first-class constraints:
- **100% Local Inference**: Your documents and generated podcast scripts never leave your machine.
- **Zero API Telemetry**: No third-party analytics or tracking.
- **Strict Input Validation**: Document extractors enforce size boundaries and sanitization.

Please see [SECURITY.md](SECURITY.md) for our full security policy and vulnerability disclosure procedures.

---

## 🤝 Contributing

We welcome community contributions! Please read our [Contributing Guidelines](.github/CONTRIBUTING.md) and [Code of Conduct](.github/CODE_OF_CONDUCT.md) before submitting pull requests.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details. Free for personal and commercial use.
