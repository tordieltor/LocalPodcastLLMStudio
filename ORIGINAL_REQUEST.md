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

## Follow-up — 2026-08-20T17:56:01Z

Harden and standardize the `LocalPodcastStudio` repository by conducting a comprehensive security audit, enforcing strict static analysis / linting / testing standards, adding open-source governance (MIT license, security and contribution policies), and configuring production-ready GitHub Actions CI/CD workflows for automated testing, linting, security scanning, and PyInstaller Windows release deployments.

Working directory: c:\Users\torpr\Documents\antigravity\epic-hubble
Integrity mode: development

## Requirements

### R1. Comprehensive Security & Dependency Audit
- Conduct a security scan using static security analysis tools (e.g. `bandit`, `pip-audit`) to detect and remediate potential vulnerabilities or insecure dependencies.
- Verify safe handling and validation for input files (`.pdf`, `.txt`, `.md`) and external process/subprocess calls.
- Confirm zero hardcoded secrets, private credentials, or personal system paths across all files and git history.
- Add a formal `SECURITY.md` defining the vulnerability disclosure policy and supported versions.

### R2. Strict Code Quality, Static Typing & Formatting
- Introduce a centralized `pyproject.toml` configuration enforcing strict code quality with modern linters and formatters (e.g., `ruff` for linting/formatting and `mypy` for static type checking).
- Refactor and clean up any detected code smells, dead code, type warnings, or inconsistencies across `core/`, `ui/`, `app.py`, and test suites.
- Ensure 100% test pass rate with coverage verification across all unit and integration tests.

### R3. GitHub Governance & Community Standards
- Add an official `LICENSE` file (MIT License).
- Create repository governance templates in `.github/`:
  - `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`
  - `.github/pull_request_template.md`
  - Issue templates (`.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/feature_request.yml`)
- Update `README.md` with CI build badges, security status, and clear contribution and release guidelines.

### R4. Automated CI/CD Workflows & GitHub Release Deployment
- **CI Pipeline (`.github/workflows/ci.yml`)**: Automated pipeline triggered on push and pull requests to `main` that runs linting (`ruff`), type checking (`mypy`), security scanning (`bandit`), and unit/e2e test suites on Windows and Ubuntu environments.
- **Release Pipeline (`.github/workflows/release.yml`)**: Automated release pipeline triggered on semantic version tags (`v*.*.*`) that builds the standalone Windows executable (`PodcastStudio.exe` via PyInstaller), computes SHA256 checksums, and publishes the binary and checksum assets to a new GitHub Release.

## Acceptance Criteria

### Security & Governance
- [ ] Security scanners (`bandit`, `pip-audit`) report 0 high or critical vulnerabilities.
- [ ] No personal workstation paths, tokens, or credentials exist in the tracked repository.
- [ ] `LICENSE` (MIT), `SECURITY.md`, `CONTRIBUTING.md`, and GitHub issue/PR templates are present and properly structured.

### Strict Code Quality & Testing
- [ ] `pyproject.toml` is configured with strict linting, formatting, and typing rules.
- [ ] `ruff check .` and `ruff format --check .` execute with 0 errors or warnings.
- [ ] All tests in `tests/` pass with 100% success rate under `pytest`.
- [ ] Build scripts (`build_exe.bat`, `build_exe.ps1`, `setup.bat`, `setup.ps1`) run cleanly without deprecated syntax.

### GitHub Deployment Automation
- [ ] `.github/workflows/ci.yml` is valid YAML and includes linting, type-checking, and test jobs.
- [ ] `.github/workflows/release.yml` is valid YAML and includes PyInstaller compilation and GitHub Release asset creation.
- [ ] Project documentation (`README.md`) reflects updated architecture, CI badges, and release instructions.

## Follow-up — 2026-08-20T18:09:03Z

Implement an in-app 1-click prerequisite management system (automated Ollama service launcher and streaming model downloader with UI progress) and a configurable multi-tier document grounding engine (Strict Source-Only, Creative Analogy, and Open Topic) for the PodcastStudio desktop application.

Working directory: c:\Users\torpr\Documents\antigravity\epic-hubble
Integrity mode: development

## Requirements

### R1. In-App 1-Click Prerequisite Manager & Model Downloader
- Detect missing or offline prerequisites in real time (Ollama offline, no models installed, Edge-TTS reachability).
- Provide a 1-click "Start Ollama Service" button in diagnostic dialogs / model status panel that attempts to launch the local Ollama background process on Windows.
- Provide a 1-click "Install Recommended Model" action (e.g. `llama3.1:8b` or `qwen2.5:7b`) that interfaces with the Ollama `/api/pull` streaming API to report real-time download percentage, download speed/bytes, and completion state.
- Ensure all prerequisite operations run in asynchronous non-blocking worker threads so the CustomTkinter UI stays responsive with interactive progress bars.

### R2. Multi-Tier Grounding & Anti-Hallucination Engine
- Define 3 distinct grounding modes configurable via UI:
  1. **Strict Source-Only**: Strict adherence to the provided document. Strictly forbids inventing external facts, unmentioned statistics, or fabricated claims. If a detail is missing, hosts explicitly acknowledge the document does not mention it.
  2. **Creative Analogy & Synthesis**: Grounds core insights in the document while allowing relatable real-world analogies, metaphors, and conversational illustrative examples.
  3. **Open Topic / Scratch**: Free generative synthesis from a topic prompt without document constraints.
- Implement specialized system and user prompt engineering in `core/prompts.py` supporting both Norwegian Bokmål (`nb-NO`) and English (`en-US`) across all 3 grounding modes and all 4 episode lengths.

### R3. UI Integration, Controls & Responsive Feedback
- Add a Grounding Mode selector (dropdown or segmented card) to the PodcastStudio configuration panel in `ui/main_window.py`.
- Upgrade the Model Status section and `ActionableErrorDialog` with interactive action buttons ("Start Ollama", "Download Model") and a dynamic progress bar for model downloads.
- Connect background events (`PULL_PROGRESS`, `PULL_DONE`, `PULL_ERROR`) to the thread-safe UI message queue.

### R4. Automated Testing & Verification
- Unit and integration tests in `tests/` verifying:
  - Streaming model pull parser and callback handling in `core/ollama.py`.
  - Grounding prompt generation and negative constraint verification across languages in `core/prompts.py`.
  - UI state transitions, queue messaging, and error dialog actions.
- Ensure 100% test pass rate with `pytest` and clean linting with `ruff check .`.

## Acceptance Criteria

### Prerequisite Management
- [ ] If Ollama is offline, the UI shows a "Start Ollama" action that can launch the service process.
- [ ] If no models exist or when requested, "Install Recommended Model" pulls a model via Ollama `/api/pull` streaming API, displaying dynamic download progress (0-100%) in the UI without freezing.
- [ ] Model dropdown auto-refreshes and selects the newly installed model upon download completion.

### Grounding & Factual Integrity
- [ ] Grounding mode is selectable in the UI ("Strict Source-Only", "Creative Analogy", "Open Topic").
- [ ] In Strict Grounding mode, generated system prompts contain explicit negative constraints forbidding hallucinated facts/data outside the provided text.
- [ ] Bilingual support (Norwegian Kari/Ola and English Jenny/Guy) works seamlessly across all grounding modes and format lengths.

### Code Quality & Test Suite
- [ ] `pytest tests/` passes with 100% success rate across all new and existing test suites.
- [ ] `ruff check .` and `ruff format --check .` execute with zero errors or warnings.

## Follow-up — 2026-08-20T21:28:00Z

Perform a comprehensive code audit of **LocalPodcastLLMStudio** — a 100% local, Windows-only, two-host AI podcast generator desktop application written in Python. The codebase uses CustomTkinter (GUI), Ollama LLMs, Piper TTS, zero-FFmpeg binary MP3/WAV stitching, and native Windows MCI audio playback. The audit must produce concrete, actionable findings and fixes across four pillars: **Speed, Reliability, Stability, and Safety**.

Working directory: `c:\Users\torpr\Documents\antigravity\epic-hubble`

Integrity mode: development

---

## Codebase Map

Key source files:
- `core/ollama.py` — Ollama HTTP client, streaming pull parser, process launcher, Edge-TTS probe (~40 KB)
- `core/prompts.py` — Prompt templates, GroundingMode enum, anti-hallucination directives (~41 KB)
- `core/tts.py` — Piper TTS neural voice synthesis (~14 KB)
- `core/mp3_stitcher.py` — Zero-FFmpeg binary MPEG/WAV frame concatenation (~15 KB)
- `core/extractor.py` — Document text extraction & normalization (~11 KB)
- `core/parser.py` — 6-tier resilient JSON/markdown dialogue parser (~13 KB)
- `core/player.py` — Native Windows MCI audio playback (~9 KB)
- `ui/main_window.py` — Main application window, queue event poller, background workers (~81 KB)
- `ui/widgets.py` — StatusBadge, ActionableErrorDialog (~20 KB)
- `ui/theme.py` — Fluent Dark theme, Tokyo Night palette (~7 KB)
- `app.py` — Entry point
- `check_env.py` — Environment prerequisite checker (~19 KB)
- `tests/` — 27 test files across unit, boundary, combinatorial, E2E, and adversarial tiers

Architecture notes:
- GUI runs on the main thread; background work is delegated to worker threads communicating via a `queue.Queue` with 50 ms polling
- Concurrency model: Python `threading`, no `asyncio` in core logic
- Target platform: Windows only; uses WinAPI (`MCI`, detached process spawning)

---

## Requirements

### R1. Speed Audit
Identify and fix performance bottlenecks across the full pipeline: LLM call latency management, TTS synthesis throughput, MP3 stitching efficiency, UI responsiveness, and startup time. Measure before/after where feasible (or provide concrete estimates based on code analysis). Look specifically for:
- Redundant or sequential operations that could be parallelized or pipelined
- Inefficient data structures, string building loops, or unnecessary copies
- Blocking calls on the GUI thread
- Missing streaming / chunked processing opportunities
- Suboptimal polling intervals or busy-wait patterns

### R2. Reliability Audit
Identify and fix failure modes that could silently corrupt output or leave the application in a broken state. Look specifically for:
- Unhandled exceptions or bare `except` clauses that swallow errors
- Race conditions and thread-safety gaps in shared state
- Incomplete cleanup on cancellation or early exit
- Network timeout handling completeness (Ollama HTTP, Edge-TTS socket probe)
- File I/O error handling (incomplete writes, missing `finally` blocks, no atomic writes)
- Queue event handling gaps (dropped events, unbounded queue growth)

### R3. Stability Audit
Identify and fix long-running session issues and resource leaks. Look specifically for:
- Thread lifecycle management (daemon threads, zombie threads, threads not joined)
- Memory leaks (accumulating buffers, growing collections, unreleased file handles)
- Windows MCI resource cleanup in `core/player.py`
- Tkinter widget lifecycle and after() callback cleanup
- Log/temp file accumulation in long sessions
- Missing `__del__` or context-manager patterns where resources are held

### R4. Safety Audit
Identify and fix security and correctness risks. Look specifically for:
- Shell injection or unsafe subprocess usage (process spawning for `ollama.exe`)
- Path traversal or unsafe file operations
- Untrusted input passed to LLM prompts without sanitization
- Hardcoded secrets, credentials, or unsafe defaults
- Bandit static analysis findings (run `bandit -r core/ ui/ app.py` and triage all findings)
- Dependency vulnerability scan (run `pip-audit` and triage findings)
- Type safety gaps that could cause runtime AttributeErrors or TypeErrors on malformed data

---

## Acceptance Criteria

### Speed
- [ ] At least 3 concrete, code-level performance improvements identified and implemented (not just noted)
- [ ] No blocking I/O or sleep() calls on the main GUI thread remain after fixes
- [ ] Any identified parallelization opportunities are either implemented or documented with a clear rationale for deferral

### Reliability
- [ ] Zero bare `except:` or `except Exception: pass` clauses remain in `core/` and `ui/` after fixes
- [ ] Every network call (Ollama HTTP, socket probe) has explicit timeout handling and communicates failure to the caller
- [ ] Cancellation paths verified: cancelling a model pull or generation mid-flight leaves no orphaned threads or locked state
- [ ] All file write operations either use atomic patterns or have `finally` cleanup

### Stability
- [ ] All threads have documented lifecycle (daemon flag justified, join strategy stated)
- [ ] `core/player.py` MCI handles are closed in all code paths (verified by inspection or test)
- [ ] No unbounded collection growth identified without a cap or eviction strategy
- [ ] `after()` callbacks in the UI are cancelled on window close

### Safety
- [ ] `bandit -r core/ ui/ app.py` produces zero HIGH severity findings after fixes
- [ ] `pip-audit` output reviewed; all HIGH/CRITICAL CVEs addressed or explicitly documented as accepted risk with rationale
- [ ] No shell=True subprocess usage remains unless unavoidable, and any remaining instances are documented
- [ ] All external inputs (file paths, user text, LLM responses) are validated before use

### Deliverables
- [ ] `AUDIT_REPORT.md` produced in the working directory summarising all findings (one entry per finding: file, line, category, severity, description, fix applied or deferred)
- [ ] All fixes applied directly to source files — no "suggested" changes left as comments
- [ ] Existing test suite still passes after all fixes (`pytest tests/ -x -q`)
- [ ] `ruff check core/ ui/ app.py` passes with zero errors after all fixes

