# Project: LocalPodcastLLMStudio 4-Pillar Code Audit and Optimization

## Architecture
- **Desktop GUI**: CustomTkinter Fluent Dark Windows 11 UI on main thread (`ui/main_window.py`, `ui/widgets.py`, `ui/theme.py`, `ui/about_dialog.py`).
- **Core Processing Pipeline**:
  - `core/extractor.py`: Multi-format document text extraction & normalization (PDF, Markdown, plain text).
  - `core/prompts.py`: Bilingual prompt engineering, GroundingMode directives (Strict Source, Creative Analogy, Open Topic).
  - `core/ollama.py`: Ollama HTTP API client, streaming pull parser, process launcher, and network reachability diagnostics.
  - `core/parser.py`: 6-tier resilient dialogue parser (JSON, markdown blocks, salvage regexes).
  - `core/tts.py`: 100% offline neural voice synthesis with Piper ONNX runtime, model caching, and optional Edge-TTS fallback.
  - `core/mp3_stitcher.py`: Zero-FFmpeg binary MPEG frame parsing, ID3v2 tagger, inter-turn pause injection.
  - `core/player.py`: Native Windows MCI audio playback engine with position polling.
- **Concurrency Model**: Worker threads (`threading.Thread(daemon=True)`) communicating via thread-safe `queue.Queue` with 50 ms UI polling loop.

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
| 14 | Deliverable AUDIT_REPORT.md | Complete structured report covering all 4 pillars and findings | M4 | ORIGINAL_REQUEST Deliverables |
| 15 | 100% Test & Ruff Verification | Zero linter errors, 100% test pass rate on full test matrix | M5 | ORIGINAL_REQUEST Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Speed Optimization (R1) | TTS ONNX cache, fast MP3 frame scanning, precompiled regexes, player ctypes | none | COMPLETED |
| M2 | Reliability & Atomic I/O (R2) | Specific exception narrowing (31 sites), atomic file writes, queue error handling | M1 | COMPLETED |
| M3 | Stability & Resource Lifecycle (R3) | Tkinter `after_cancel` timers, MCI open status verification, temp dir cleanup | M2 | COMPLETED |
| M4 | Safety Triage & AUDIT_REPORT (R4) | Bandit triage, input validation checks, AUDIT_REPORT.md synthesis | M3 | COMPLETED |
| M5 | Test Matrix & Integrity Gate | Full 1,649-test suite pass, zero ruff errors, multi-agent adversarial gate | M4 | COMPLETED |

## Interface Contracts
### `core.tts` ↔ `ui.main_window`
- `TTSEngine.synthesize_turn_bytes(turn: DialogueTurn, voice: str | None = None) -> bytes`: Uses in-memory cached ONNX model instance when available. Thread-safe.
- `TTSEngine.synthesize_dialogue_audio(dialogue: list[DialogueTurn], output_dir: str | None = None) -> tuple[str, list[str]]`: Cleans up temporary directory on failure.

### `core.mp3_stitcher` ↔ `ui.main_window`
- `stitch_mp3_files(audio_files: list[str | bytes], output_file: str, ...) -> str`: Uses fast frame search and writes atomically to output path via staging temporary file.

### `core.player` ↔ `ui.main_window`
- `WindowsAudioPlayer.open(filepath: str) -> bool`: Returns `True` only if MCI device opened successfully with return code 0.
- `WindowsAudioPlayer.close() -> None`: Closes device and clears `_is_opened = False`. Registered with `atexit`.

### `ui.main_window`
- `MainWindow._on_close()`: Cancels scheduled `after()` timers (`_queue_poll_id`, `_player_poll_id`), signals cancellation events to active workers, performs bounded worker joins, closes audio player, and destroys window safely.

## Code Layout
- `core/`:
  - `extractor.py`: Document text extractors with size limits and precompiled regexes
  - `mp3_stitcher.py`: MP3 frame scanner and atomic stitcher
  - `ollama.py`: Ollama client with explicit timeouts and process launcher
  - `parser.py`: 6-tier resilient dialogue parser with precompiled patterns
  - `player.py`: MCI Windows audio player with handle validation
  - `prompts.py`: Bilingual anti-hallucination prompt generator
  - `tts.py`: Piper ONNX voice synthesizer with model cache and cleanup
- `ui/`:
  - `about_dialog.py`: Application metadata dialog
  - `main_window.py`: Main GUI window with lifecycle and queue safety
  - `theme.py`: Fluent dark theme styling
  - `widgets.py`: Status badges, ActionableErrorDialog, TimeSlider
- `app.py`: Application entry point
- `check_env.py`: Preflight environment diagnostic utility
- `tests/`: 22 test files covering 5 empirical test tiers (1,649 total tests)
- `AUDIT_REPORT.md`: Comprehensive audit report deliverable
