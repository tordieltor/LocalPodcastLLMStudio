# Original User Request

## 2026-08-20T16:39:17Z

Build a universal, 100% local (zero cloud API cost) Windows desktop application (`PodcastStudio.exe`) that converts raw text, Markdown, or PDF documents into a two-host audio podcast using local Ollama LLMs for dialogue generation and Edge-TTS for neural voice synthesis, with an automated self-healing environment setup and one-click PyInstaller build pipeline.

Working directory: .
Integrity mode: development

## Requirements

### R1. Prerequisite Diagnostics & Self-Healing Setup (`check_env.py`, `setup.bat`, `setup.ps1`)
- Verify Python 3.10+ and configure local virtual environment (`.venv`).
- Check and install required packages: `customtkinter`, `edge-tts`, `pypdf`, `pyinstaller`.
- Query Ollama service at `http://localhost:11434/api/tags`, detect installed models (`mistral-nemo:latest`, `qwen2.5:7b`, `llama3.1:8b`, etc.), and provide actionable instructions if Ollama is not running or no models are installed.

### R2. Universal Desktop Application (`app.py`)
- **Fluent Dark UI**: Modern Windows 11 style GUI with header, progress bar (0-100%), and real-time status labels.
- **Input Methods**: Multi-line text input plus "Load Document" file picker supporting `.txt`, `.md`, and `.pdf` (using `pypdf`).
- **Configuration**: Language selector (Norwegian Bokmål / English), dynamic Ollama model dropdown populated from API, and episode format selector (Short Overview: 8-10 turns vs. Deep Dive: 14-18 turns).
- **Asynchronous Processing**: Background worker threads (`threading.Thread`) keeping GUI completely responsive without freezing or "(Not Responding)" states.
- **Script Generation Engine**: Local Ollama dialogue generation between Host 1 (curious host / Kari / Jenny) and Host 2 (expert / Ola / Guy) with strict JSON output formatting and resilient parser/fallback.
- **Voice Synthesis & Assembly**: `edge-tts` async synthesis (`nb-NO-PernilleNeural`/`nb-NO-FinnNeural` for Norwegian, `en-US-JennyNeural`/`en-US-GuyNeural` for English) with direct MP3 binary stitching (zero external `ffmpeg` requirement).
- **Playback & Export**: Integrated playback trigger and "Save MP3 As..." export dialog.

### R3. One-Click Executable Compilation (`build_exe.bat`, `build_exe.ps1`)
- Single-click compilation script executing `pyinstaller --noconsole --onefile --name "PodcastStudio" --clean app.py`.
- Automated output check verifying `dist/PodcastStudio.exe` generation and reporting binary size.

### R4. Complete Project Documentation (`README.md`)
- Detailed instructions for setup, running from source, prerequisites (Ollama installation & model pull), and building the standalone executable.

## Acceptance Criteria

### Diagnostics & Environment
- [ ] `check_env.py` runs standalone and reports status of Python, packages, and Ollama connection.
- [ ] `setup.bat` / `setup.ps1` sets up virtual environment and installs dependencies cleanly.

### Application & Processing Pipeline
- [ ] GUI launches without errors and auto-detects Ollama models.
- [ ] Text extraction works reliably across `.txt`, `.md`, and `.pdf` files.
- [ ] Script generation parses structured 2-host JSON dialogues reliably even with LLM formatting quirks.
- [ ] Audio synthesis successfully stitches MP3 segments into a playable audio file without external ffmpeg binaries.
- [ ] Background thread architecture prevents UI freezing during script writing and audio generation.

### Packaging & Executable
- [ ] `build_exe.bat` / `build_exe.ps1` builds `dist/PodcastStudio.exe` without console popup (`--noconsole`).
- [ ] Standalone executable launches and runs the full generation workflow.

## Follow-up — 2026-08-20T16:41:01Z

The user has provided the following refined requirements for PodcastStudio:
1. Input Methods:
   - Must take file paths as direct text input as well as via "Browse" dialog (.txt, .md, .pdf).
   - Must support "Generate from Scratch" (generate podcast directly from a prompt/topic without requiring a document).
2. Workflow & Script Generation:
   - Provide a "Generate Script Only" feature (in addition to Full Generation) so the user can inspect, fine-tune, or save the dialogue script.
3. Output Directory:
   - Allow the user to select an output folder for saving generated scripts and audio files.
4. Voice & Style Fine-Tuning (Keep it simple):
   - Style/Tone selector (e.g., Casual & Lively, Analytical & Educational, Lively Debate).
   - Voice tuning (speaking rate/speed control, e.g. -10% to +15%).

Please ensure the team incorporates these capabilities into check_env.py, app.py, tests, and documentation.

## Follow-up — 2026-08-20T16:41:53Z

[USER CONFIRMATION - Language Selection]:
The user confirmed the language selection design:
- Norwegian Bokmål (`nb-NO-PernilleNeural` as Host 1 / Kari, `nb-NO-FinnNeural` as Host 2 / Ola)
- English (`en-US-JennyNeural` as Host 1 / Jenny, `en-US-GuyNeural` as Host 2 / Guy)
Switching the language dropdown will adapt both the Ollama prompt generation language and the Edge-TTS neural voice assignment.

## Follow-up — 2026-08-20T16:43:08Z

[USER UPDATE - Episode Length Presets]:
The user has specified 4 episode length options:
1. Quick Summary (~2-3 mins, 6-8 dialogue turns)
2. Standard Episode (~5-7 mins, 12-16 dialogue turns)
3. Deep Dive (~10-15 mins, 20-26 dialogue turns)
4. Extended In-Depth (~25-30 mins, 45-60 dialogue turns)

Please ensure the UI episode length dropdown and the LLM prompt generator support these 4 depth levels (generating appropriately sized turn counts and pacing).

