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

- **Zero Cloud API Costs**: Runs 100% locally on your machine utilizing local Ollama LLMs and Microsoft Edge-TTS neural voice synthesis.
- **Document-Agnostic Ingestion**: Ingests `.pdf`, `.md`, and `.txt` documents, clipboard text, or generates directly from a prompt with "Generate from Scratch".
- **Bilingual Two-Host Dialogue**:
  - 🇳🇴 **Norsk (Bokmål)**: **Kari** (`nb-NO-PernilleNeural`) & **Ola** (`nb-NO-FinnNeural`)
  - 🇬🇧 **English**: **Jenny** (`en-US-JennyNeural`) & **Guy** (`en-US-GuyNeural`)
- **4 Episode Duration Presets**:
  - ⚡ **Quick Summary**: ~2–3 mins (6–8 dialogue turns)
  - 🎙️ **Standard Episode**: ~5–7 mins (12–16 dialogue turns)
  - 🔍 **Deep Dive**: ~10–15 mins (20–26 dialogue turns)
  - 📚 **Extended In-Depth**: ~25–30 mins (45–60 dialogue turns)
- **Tone & Style Controls**: Fine-tune conversation style (Casual & Lively, Analytical & Educational, Lively Debate).
- **Voice Pace Fine-Tuning**: Adjust speaking speed from -10% to +15% for optimal natural rhythm.
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
│ - 6-Tier Resilient Parser   │ │ - Jenny & Guy (EN)          │
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

### 3. Launch the Application

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Launch application
python app.py
```

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
│   ├── extractor.py                   # Multi-format document parser (.pdf, .md, .txt)
│   ├── prompts.py                     # Dynamic prompt engineering & duration presets
│   ├── parser.py                      # 6-tier resilient dialogue JSON parser
│   ├── ollama.py                      # Local Ollama REST client & turn generator
│   ├── tts.py                         # Async Edge-TTS neural speech synthesizer
│   ├── mp3_stitcher.py                # Zero-dependency pure Python MP3 frame stitcher
│   └── player.py                      # Native Windows MCI audio player & exporter
│
├── ui/                                # User interface layer
│   ├── theme.py                       # Fluent Dark styling, palette, typography
│   ├── widgets.py                     # Cards, headers, sliders, dialogue cards, error dialogs
│   └── main_window.py                 # Main GUI window & background worker queue loop
│
├── tests/                             # Comprehensive test suite
│   ├── conftest.py                    # Fixtures & mock environments
│   ├── test_check_env.py              # Diagnostic checker tests
│   ├── test_extractor.py              # Document extraction tests
│   ├── test_prompts.py                # Bilingual prompt preset tests
│   ├── test_parser.py                 # Resilient JSON parser tests
│   ├── test_ollama.py                 # Ollama REST API mock tests
│   ├── test_tts.py                    # Edge-TTS synthesizer tests
│   ├── test_mp3_stitcher.py           # Pure Python MP3 frame stitching tests
│   ├── test_player.py                 # Audio playback & export tests
│   ├── test_ui.py                     # CustomTkinter GUI lifecycle tests
│   └── test_e2e_pipeline.py           # End-to-end integration tests
│
├── app.py                             # Main application entry point
├── check_env.py                       # Preflight environment diagnostics & model audit
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
