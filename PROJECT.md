# Project: LocalPodcastLLMStudio Architecture & Optimization

## Architecture
- **Desktop GUI**: CustomTkinter Fluent Dark Windows 11 UI on main thread (`ui/main_window.py`, `ui/widgets.py`, `ui/theme.py`, `ui/about_dialog.py`).
- **Terminal User Interface (TUI)**: Tokyo Night Terminal Interface for PowerShell and Command Prompt (`tui.py`, `tui/terminal.py`, `tui/input.py`, `tui/state.py`, `tui/components.py`, `tui/workers.py`, `tui/screens/`).
- **Scriptable CLI Engine**: Headless unattended pipeline and modular stage chaining engine (`cli.py`) supporting rapid topic-only execution (`--topic`) and pipe integration.
- **Core Processing Pipeline**:
  - `core/extractor.py`: Multi-format document text extraction & normalization (PDF, Markdown, plain text, topics).
  - `core/prompts.py`: Bilingual prompt engineering, GroundingMode directives (Strict Source, Creative Analogy, Open Topic).
  - `core/ollama.py`: Ollama HTTP API client, streaming pull parser, process launcher, and network reachability diagnostics.
  - `core/parser.py`: 6-tier resilient dialogue parser (JSON, markdown blocks, salvage regexes).
  - `core/tts.py`: 100% offline neural voice synthesis with Piper ONNX runtime, model caching, and optional Edge-TTS fallback.
  - `core/mp3_stitcher.py`: Zero-FFmpeg binary MPEG frame parsing, ID3v2 tagger, inter-turn pause injection.
  - `core/player.py`: Native Windows MCI audio playback engine with position polling.
- **Concurrency Model**: Worker threads (`threading.Thread(daemon=True)`) communicating via thread-safe `queue.Queue` with non-blocking UI event loops in both GUI and TUI runtimes.

## Feature Inventory
| # | Feature / Objective | Description | Milestone | Source |
|---|---------------------|-------------|-----------|--------|
| 1 | R1.1 TTS Voice Model Caching | In-memory cache `_VOICE_MODEL_CACHE` for loaded Piper ONNX voice instances | M1 | ORIGINAL_REQUEST §R1 |
| 2 | R1.2 Fast MP3 Frame Sync | C-level `find(b"\xff")` byte scanning and streaming frame buffer | M1 | ORIGINAL_REQUEST §R1 |
| 3 | R1.3 Precompiled Regexes | Module-level precompilation of parser and extractor regex patterns | M1 | ORIGINAL_REQUEST §R1 |
| 4 | R1.4 Player Poller Optimization | Module-level `ctypes` bindings avoiding repeated dynamic imports | M1 | ORIGINAL_REQUEST §R1 |
| 5 | R2.1 Narrow Exception Clauses | Replace all 31 generic `except:`/`except Exception:` with specific tuples | M2 | ORIGINAL_REQUEST §R2 |
| 6 | R2.2 Atomic File Writes | Atomic write staging (`.tmp` + `os.replace`) for JSON, MD, MP3 outputs | M2 | ORIGINAL_REQUEST §R2 |
| 7 | R2.3 Event Queue Safety | Robust event loop error boundary and `task_done()` guarantee | M2 | ORIGINAL_REQUEST §R2 |
| 8 | R3.1 Tkinter Timer Teardown | Track and cancel `after()` polling callbacks on window close | M3 | ORIGINAL_REQUEST §R3 |
| 9 | R3.2 MCI Driver Hardening | Verify `mciSendStringW` open code, ensure clean close on failure/exit | M3 | ORIGINAL_REQUEST §R3 |
| 10 | R3.3 Temp Dir Cleanup | Comprehensive teardown of temporary synthesis directories on error | M3 | ORIGINAL_REQUEST §R3 |
| 11 | R3.4 Worker Thread Join | Graceful bounded join on worker thread exit in `_on_close` | M3 | ORIGINAL_REQUEST §R3 |
| 12 | R4.1 Bandit & Pip-Audit Triage | 0 HIGH findings, triaged low items, 0 CVEs in dependencies | M4 | ORIGINAL_REQUEST §R4 |
| 13 | R4.2 Subprocess & Input Safety | Strict array-bound arguments, input size limits, prompt boundary fences | M4 | ORIGINAL_REQUEST §R4 |
| 14 | Interactive Tokyo Night TUI | 8-screen full-featured interactive terminal application (`tui.py`, `tui/`) | M6 | ORIGINAL_REQUEST TUI |
| 15 | Scriptable CLI Pipeline Engine | Headless pipeline, modular stage subcommands, topic-only mode (`cli.py`) | M6 | ORIGINAL_REQUEST CLI |
| 16 | 100% Test & Quality Gate | 2,032 passing tests, zero ruff violations, zero mypy errors | M6 | Quality Gate |

## Code Layout
- `core/`:
  - `extractor.py`: Document text extractors with size limits and precompiled regexes
  - `mp3_stitcher.py`: MP3 frame scanner and atomic stitcher
  - `ollama.py`: Ollama client with explicit timeouts and process launcher
  - `parser.py`: 6-tier resilient dialogue parser with precompiled patterns
  - `pipeline.py`: Headless podcast generator service
  - `player.py`: MCI Windows audio player with handle validation
  - `prompts.py`: Bilingual anti-hallucination prompt generator
  - `tts.py`: Piper ONNX voice synthesizer with model cache and cleanup
- `ui/`:
  - `about_dialog.py`: Application metadata dialog
  - `main_window.py`: Main GUI window with lifecycle and queue safety
  - `theme.py`: Fluent dark theme styling
  - `widgets.py`: Status badges, ActionableErrorDialog, TimeSlider
- `tui/`:
  - `terminal.py`: Windows CMD / PowerShell ANSI controller and VTP management
  - `input.py`: Windows non-blocking `msvcrt` keyboard reader
  - `state.py`: Reactive thread-safe TUI state container
  - `components.py`: CardFrame, HotkeyBar, TimeSlider, tables, and modal dialogs
  - `workers.py`: Background worker threads for Ollama, TTS, stitching, and pulling
  - `screens/`: 8 full-screen views (Dashboard, Ingestion, Ollama, Config, Generation, Script Studio, Player, Help)
- `app.py`: Desktop GUI entry point
- `tui.py`: Interactive Terminal User Interface entry point
- `cli.py`: Scriptable CLI pipeline and chaining engine
- `check_env.py`: Preflight environment diagnostic utility
- `tests/`: 24 test modules covering unit, integration, UI, TUI, and E2E tiers (2,032 total tests)
