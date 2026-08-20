# E2E Test Infra: LocalPodcastLLMStudio

## Test Philosophy
- **Opaque-Box & Requirement-Driven**: Tests are strictly derived from specifications and user journeys without coupling to internal design trivia.
- **5-Tier Empirical Hierarchy**: Feature Component Verification (Tier 1) + Boundary Value Analysis (Tier 2) + Cross-Feature Combinations (Tier 3) + Real-World Workloads (Tier 4) + Adversarial Challenger Hardening (Tier 5).
- **Zero-Flakiness Windows Resilience**: Safe file cleanup with exponential backoff for `WinError 32`, garbage collection, and deterministic mock adapters.

## Feature Inventory & Test Matrix
| # | Feature | Requirement Source | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 (Challenger) |
|---|---------|-------------------|:------:|:------:|:------:|:------:|:-------------------:|
| F1 | Real-time Prerequisite Detection | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ | ✓ |
| F2 | 1-Click Ollama Service Launcher | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ | ✓ |
| F3 | Streaming Model Downloader | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ | ✓ |
| F4 | Edge-TTS Network Probe | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ | ✓ |
| F5 | Strict Source-Only Grounding Mode | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ | ✓ |
| F6 | Creative Analogy & Synthesis Mode | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ | ✓ |
| F7 | Open Topic / Scratch Mode | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ | ✓ |
| F8 | Bilingual Grounding Prompts | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ | ✓ |
| F9 | Grounding Mode UI Selector | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ | ✓ | ✓ |
| F10| Model Status & 1-Click Actions | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ | ✓ | ✓ |
| F11| Dynamic Streaming Progress Bar | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ | ✓ | ✓ |
| F12| Thread-Safe UI Event Bus | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ | ✓ | ✓ |
| F13| Upgraded ActionableErrorDialog | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ | ✓ | ✓ |
| F14| Automated Testing & Quality Gate | ORIGINAL_REQUEST R4 | 5 | 5 | ✓ | ✓ | ✓ |

## Test Architecture & Runners
- **Primary Smart Runner**: `.venv\Scripts\python.exe run_tests.py`
  - `--quick` / `--mvp`: Rapid smoke battery (398 tests in ~3s).
  - `--full` / `--all`: Exhaustive 1,238-test multi-tier matrix with multi-core parallel execution via `pytest-xdist`.
- **Direct Pytest Runner**: `.venv\Scripts\python.exe -m pytest -v tests/`
- **Lint & Format Gate**: `.venv\Scripts\python.exe -m ruff check .` and `.venv\Scripts\python.exe -m ruff format --check .`
- **Pass/Fail Semantics**: Exit code 0, 100% test pass rate (1,238/1,238 passed), zero regressions, zero ruff violations.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Offline to Online Ollama Recovery & Model Pull Flow | F1, F2, F3, F10, F11, F12 | High |
| 2 | Strict Academic Document Podcast Generation in Norwegian | F5, F8, F9, F12, F14 | High |
| 3 | Creative Business Whitepaper Podcast Generation in English | F6, F8, F9, F12, F14 | High |
| 4 | Open Topic Tech Debate Synthesis (No Document) | F7, F8, F9, F12, F14 | Medium |
| 5 | Network Failure & Edge-TTS Offline Diagnostics Remediation | F1, F4, F10, F12, F13 | High |
| 6 | Interrupted Model Pull Cancellation and Resume Handling | F3, F11, F12, F13 | High |
| 7 | Full End-to-End Ingestion -> Grounded LLM -> Parser -> TTS Pipeline | F5, F6, F7, F8, F12, F14 | High |

## Coverage & Test Inventory
- **Tier 1 (Feature Verification)**: Component verification across all core modules.
- **Tier 2 (Boundary & Corner Cases)**: Multi-encoding fallbacks (`utf-8-sig`, `cp1252`, `latin-1`), corrupted headers, timeouts.
- **Tier 3 (Cross-Feature Combinations)**: Full combinatorial prompt matrices (2 Languages × 4 Lengths × 3 Tones × 3 Grounding Modes).
- **Tier 4 (Workloads & E2E Pipelines)**: Real-world document, scratch, and script-only pipeline journeys.
- **Tier 5 (Adversarial Challenger)**: Concurrency stress, prompt injection resistance, malformed stream salvaging.
- **Total Test Cases**: 1,647 passing tests across full empirical test suite.

## Cross-Platform Testing & Shell Invariants (Learnings & Guardrails)
1. **Windows Batch Scripting Invariant**:
   - Never nest unquoted/unescaped parentheses (such as `(.venv)` or `(build, dist)`) inside parenthesized `if ( ... )` or `for ( ... )` blocks in `.bat` scripts.
   - `cmd.exe` immediately parses the closing parenthesis `)` as the end of the `if` block, leaving subsequent tokens dangling (causing `... was unexpected at this time.` syntax errors).
   - Use plain descriptions (e.g. `in .venv`) or escape with caret `^( ... ^)`.

2. **Cross-Platform CTypes Mocking Invariant**:
   - `ctypes.windll` is only available on native Windows runtimes and does not exist in Python on Linux/macOS.
   - Never write `patch("ctypes.windll.dwmapi...")` as module resolution fails at import/patch time on POSIX runners.
   - Always instantiate a mock object and use `patch.object(ctypes, "windll", mock_windll, create=True)` with `patch("sys.platform", "win32")`.

3. **Cross-Platform Path Mocking Invariant**:
   - On Linux/macOS CI runners, `os.path.join` and `os.path.abspath` resolve using POSIX separators (`/`).
   - Mock predicates (such as `mock_isfile`) that test Windows paths must normalize separators before matching (`p.replace("\\", "/")`), avoiding hardcoded backslash comparisons that fail on POSIX runners.
   - Always explicitly patch `sys.platform == "win32"` in Windows-specific platform branch tests.
