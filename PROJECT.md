# Project: PodcastStudio

Universal, 100% local (zero cloud API cost) Windows desktop application (`PodcastStudio.exe`) converting text, Markdown, or PDF documents into two-host audio podcasts using local Ollama LLMs for dialogue generation and Edge-TTS for neural voice synthesis, with an automated self-healing environment setup and one-click PyInstaller build pipeline.

## Architecture

```
                                  +-------------------------------------------------+
                                  |            PodcastStudio Desktop App             |
                                  |    (app.py / ui/main_window.py - CustomTkinter) |
                                  +------------------------+------------------------+
                                                           |
                                 (Dispatches non-blocking  | Polling queue.Queue
                                  background thread)       | via root.after(50ms)
                                                           v
                                  +-------------------------------------------------+
                                  |             GenerationWorker Thread             |
                                  +----+-------------------+-------------------+----+
                                       |                   |                   |
                                       v                   v                   v
+------------------------+  +--------------------+  +--------------+  +---------------------+
|    Document Ingestion  |  |    Ollama Dialogue |  |   Edge-TTS   |  |   Zero-FFmpeg MP3   |
|   (core/extractor.py)  |  |   (core/ollama.py, |  |  Synthesis   |  |     Stitcher        |
| .txt, .md, .pdf (pypdf)|  |   core/prompts.py, |  | (core/tts.py)|  | (core/mp3_stitcher) |
| direct paste & topic   |  |   core/parser.py)  |  | nb-NO, en-US |  | ID3v2 strip & sync  |
+------------------------+  +--------------------+  +--------------+  +---------------------+
                                                                               |
                                                                               v
                                                                      +---------------------+
                                                                      |  Native MCI Player  |
                                                                      |   (core/player.py)  |
                                                                      | Play/Pause/Seek/Exp |
                                                                      +---------------------+
```

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Python & Venv Diagnostic | Standalone environment diagnostic checking Python >= 3.10 and .venv | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Package Dependency Check | Verifies `customtkinter`, `edge-tts`, `pypdf`, `pyinstaller`, `requests` | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Ollama API Tag Detection | Queries `http://localhost:11434/api/tags`, parses installed models and formats | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Windows Self-Healing Setup | `setup.bat` & `setup.ps1` to bootstrap .venv, install deps, and run diagnostics | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Document Ingestion (.txt/.md) | Multi-encoding fallback loader (UTF-8, UTF-8-BOM, CP1252, Latin-1) | M2 | ORIGINAL_REQUEST §R2 |
| 6 | PDF Extraction | `pypdf.PdfReader` with whitespace cleanup, de-hyphenation, and decrypt fallback | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Direct Text & Scratch Topic | Supports pasted raw text and "Generate from Scratch" from a prompt/topic | M2 | Follow-up 2026-08-20 |
| 8 | Bilingual Dialogue Prompts | Norwegian (Kari/Ola) and English (Jenny/Guy) system prompts with tone control | M2 | ORIGINAL_REQUEST §R2 & Follow-up |
| 9 | Episode Format Control | Short Overview (8-10 turns) vs Deep Dive (14-18 turns) dialogue length | M2 | ORIGINAL_REQUEST §R2 |
| 10 | Style & Tone Control | Casual & Lively, Analytical & Educational, Lively Debate options | M2 | Follow-up 2026-08-20 |
| 11 | 6-Tier Resilient Parser | Robust JSON extractor handling fences, bad quotes, trailing commas, plain-text | M2 | ORIGINAL_REQUEST §R2 |
| 12 | Edge-TTS Voice Synthesis | Async synthesis for `nb-NO-PernilleNeural`, `nb-NO-FinnNeural`, `en-US-JennyNeural`, `en-US-GuyNeural` | M2 | ORIGINAL_REQUEST §R2 |
| 13 | Voice Speaking Speed Control | Speed/rate adjustments from -10% to +15% via Edge-TTS rate parameter | M2 | Follow-up 2026-08-20 |
| 14 | Zero-FFmpeg MP3 Stitcher | Binary MP3 frame concatenation with ID3v2 stripping & silence frame injection | M2 | ORIGINAL_REQUEST §R2 |
| 15 | Native Windows Audio Player | `winmm.dll` MCI player with play, pause, resume, stop, seek, and export | M2 | ORIGINAL_REQUEST §R2 |
| 16 | Fluent Dark Modern UI | Windows 11 Fluent Dark CustomTkinter 2-column card layout with live status & progress | M3 | ORIGINAL_REQUEST §R2 |
| 17 | Non-Freezing Worker Thread | `threading.Thread(daemon=True)` with thread-safe `queue.Queue` message protocol | M3 | ORIGINAL_REQUEST §R2 |
| 18 | Dual Generation Workflow | "Generate Script Only" (editable transcript preview) vs "Generate Full Podcast" | M3 | Follow-up 2026-08-20 |
| 19 | Custom Output Folder | UI picker for custom destination directory for scripts and MP3 audio files | M3 | Follow-up 2026-08-20 |
| 20 | Dynamic Model Selector | Auto-fetches and displays available Ollama models with live refresh & status badge | M3 | ORIGINAL_REQUEST §R2 |
| 21 | Actionable Error Popups | User-friendly guidance for Ollama offline, missing models, network timeouts, invalid PDFs | M3 | ORIGINAL_REQUEST §R2 |
| 22 | PyInstaller Spec Configuration | `PodcastStudio.spec` collecting all CustomTkinter, Edge-TTS, certifi, pypdf assets | M4 | ORIGINAL_REQUEST §R3 |
| 23 | One-Click Build Scripts | `build_exe.bat` & `build_exe.ps1` with clean, compile, and binary validation | M4 | ORIGINAL_REQUEST §R3 |
| 24 | Complete Documentation | `README.md` covering prerequisites, setup, source run, compilation, troubleshooting | M5 | ORIGINAL_REQUEST §R4 |
| 25 | Comprehensive E2E Testing | Test suite covering Tiers 1-4 across all document, parser, LLM, TTS, and MP3 engines | M5 | Acceptance Criteria |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Diagnostics & Setup Environment | `check_env.py`, `setup.bat`, `setup.ps1`, `requirements.txt`, `requirements-dev.txt` | none | PLANNED |
| M2 | Core Engines & Audio Processing | `core/extractor.py`, `core/prompts.py`, `core/ollama.py`, `core/parser.py`, `core/tts.py`, `core/mp3_stitcher.py`, `core/player.py` | none | PLANNED |
| M3 | Desktop UI & Async Pipeline | `app.py`, `ui/main_window.py`, `ui/theme.py`, `ui/widgets.py` | M2 | PLANNED |
| M4 | One-Click Build & PyInstaller | `PodcastStudio.spec`, `build_exe.bat`, `build_exe.ps1`, binary validation | M1, M2, M3 | PLANNED |
| M5 | Documentation & Full E2E Test Suite | `README.md`, `tests/` test suite, Tiers 1-4 verification | M1, M2, M3, M4 | PLANNED |

## Interface Contracts

### 1. Document Extraction (`core/extractor.py`)
```python
def extract_text(source: str, is_raw_text: bool = False, is_topic: bool = False) -> str:
    """
    Extracts text from file path (.txt, .md, .pdf), raw pasted text, or topic prompt.
    Returns normalized UTF-8 string or raises DocumentExtractionError.
    """
```

### 2. Ollama Client & Dialogue Generator (`core/ollama.py`, `core/prompts.py`, `core/parser.py`)
```python
@dataclass
class DialogueTurn:
    speaker: str  # "Host 1" or "Host 2" (or "Kari"/"Ola" / "Jenny"/"Guy")
    text: str

def generate_podcast_script(
    content: str,
    language: str,        # "nb-NO" | "en-US"
    format_type: str,     # "short" (8-10 turns) | "deep_dive" (14-18 turns)
    tone_style: str,      # "casual" | "analytical" | "debate"
    model: str,
    ollama_url: str = "http://localhost:11434"
) -> List[DialogueTurn]:
    """Calls Ollama API, receives raw LLM output, and parses with resilient 6-tier parser."""
```

### 3. Voice Synthesis (`core/tts.py`)
```python
async def synthesize_turn(
    text: str,
    voice: str,           # 'nb-NO-PernilleNeural', 'nb-NO-FinnNeural', etc.
    rate: str = "+0%",    # "-10%" to "+15%"
    output_path: str = None
) -> bytes:
    """Synthesizes text using Edge-TTS Communicate and returns raw MP3 bytes."""
```

### 4. Zero-FFmpeg MP3 Stitcher (`core/mp3_stitcher.py`)
```python
def stitch_mp3_files(
    input_files_or_bytes: List[Union[str, bytes]],
    output_file_path: str,
    silence_duration_ms: int = 350
) -> str:
    """Strips ID3 tags, aligns MPEG audio frames, injects silence, and saves valid MP3."""
```

### 5. Native Windows MCI Player (`core/player.py`)
```python
class WindowsAudioPlayer:
    def open(self, file_path: str) -> bool: ...
    def play(self) -> bool: ...
    def pause(self) -> bool: ...
    def resume(self) -> bool: ...
    def stop(self) -> bool: ...
    def seek(self, position_ms: int) -> bool: ...
    def get_position(self) -> int: ...
    def get_length(self) -> int: ...
    def set_volume(self, volume_percent: int) -> bool: ...
```

### 6. Background Queue Protocol (`ui/main_window.py`)
```python
# Tuples sent from worker thread to queue.Queue:
("STATUS", message_str)
("PROGRESS", float_percentage_0_to_1)
("SCRIPT_READY", List[DialogueTurn])
("GENERATION_DONE", {"mp3_path": str, "script": List[DialogueTurn]})
("ERROR", error_message_str)
("CANCELLED", None)
("OLLAMA_STATUS", {"online": bool, "models": List[str]})
```

## Code Layout

```
epic-hubble/
├── check_env.py             # Prerequisite Diagnostics tool (M1)
├── setup.bat                # Windows Batch self-healing bootstrap (M1)
├── setup.ps1                # Windows PowerShell self-healing bootstrap (M1)
├── requirements.txt         # Runtime dependencies (M1)
├── requirements-dev.txt     # Test/build dependencies (M1)
├── app.py                   # Main Application Entry Point (M3)
├── PodcastStudio.spec       # PyInstaller bundling specification (M4)
├── build_exe.bat            # One-click Windows batch executable builder (M4)
├── build_exe.ps1            # One-click PowerShell executable builder (M4)
├── README.md                # Comprehensive documentation & user guide (M5)
├── core/                    # Core Subsystems (M2)
│   ├── __init__.py
│   ├── extractor.py         # .txt, .md, .pdf document & topic text extraction
│   ├── prompts.py           # System prompts, personas, format & tone definitions
│   ├── parser.py            # 6-tier resilient JSON/dialogue parser
│   ├── ollama.py            # Local Ollama client & model tag inspector
│   ├── tts.py               # Edge-TTS async neural voice synthesis engine
│   ├── mp3_stitcher.py      # Zero-FFmpeg binary MP3 frame stitcher
│   └── player.py            # Windows native MCI audio player
├── ui/                      # CustomTkinter User Interface (M3)
│   ├── __init__.py
│   ├── theme.py             # Windows 11 Fluent Dark palette & typography
│   ├── widgets.py           # Custom UI cards, badges, and progress indicators
│   └── main_window.py       # Main Application Window & async event coordinator
└── tests/                   # Test Suite (M5)
    ├── __init__.py
    ├── conftest.py          # Fixtures & sample files
    ├── test_extractor.py    # Unit tests for text & PDF extraction
    ├── test_prompts.py      # Unit tests for prompt templating
    ├── test_parser.py       # Unit tests for 6-tier JSON resilient parser
    ├── test_ollama.py       # Unit tests for Ollama client & model queries
    ├── test_tts.py          # Unit tests for Edge-TTS voice mapping & synthesis
    ├── test_mp3_stitcher.py # Unit tests for MP3 binary frame stitching
    ├── test_player.py       # Unit tests for MCI audio player
    ├── test_check_env.py    # Unit tests for diagnostic checks
    └── test_e2e_pipeline.py # Full integration & pipeline verification
```
