# Contributing to LocalPodcastLLMStudio

Thank you for your interest in contributing to **LocalPodcastLLMStudio**! We are building a universal, 100% local, zero-cloud-cost desktop application that empowers anyone to generate studio-quality two-host conversational podcasts from raw text, Markdown, and PDF documents.

We welcome contributions of all kinds: bug fixes, new features, UI improvements, prompt refinements, documentation enhancements, and test coverage additions.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it to ensure a welcoming and productive environment for all contributors.

---

## Getting Started

### 1. Prerequisites

- **Python 3.10+** (Python 3.11 or 3.12 recommended; 64-bit required).
- **Git** installed on your system.
- **Ollama** installed locally from [ollama.com](https://ollama.com) (optional for running unit tests with mocks, required for live generation).
  - Recommended models:
    ```bash
    ollama pull mistral-nemo:latest
    ollama pull llama3.1:8b
    ollama pull qwen2.5:7b
    ```

### 2. Fork and Clone the Repository

```bash
git clone https://github.com/tordieltor/LocalPodcastLLMStudio.git
cd LocalPodcastLLMStudio
```

### 3. Create a Local Virtual Environment

#### On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### On Windows (Command Prompt):
```bat
python -m venv .venv
.\.venv\Scripts\activate.bat
```

#### On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies

Install runtime dependencies along with all developer tooling:

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 5. Run Preflight Diagnostics

Verify that your development environment is correctly configured:

```bash
python check_env.py
```

---

## Development Workflow & Code Quality Standards

We enforce strict automated quality gates across formatting, linting, static typing, security scanning, and test coverage. All pull requests must pass these checks in CI.

### 1. Code Formatting & Linting (`ruff`)

We use [Ruff](https://github.com/astral-sh/ruff) for blazing-fast linting and code formatting:

```bash
# Check for lint issues and import sorting
ruff check .

# Check code formatting compliance
ruff format --check .

# Automatically apply safe fixes and format
ruff check --fix .
ruff format .
```

### 2. Static Type Checking (`mypy`)

We use [Mypy](https://github.com/python/mypy) for strict static type safety:

```bash
mypy core ui app.py check_env.py
```

All code in `core/` and `ui/` should include proper type hints for function arguments, return types, and module-level interfaces.

### 3. Security Scanning (`bandit` & `pip-audit`)

Ensure code and dependencies meet security standards:

```bash
# Static Application Security Testing (SAST)
bandit -r core ui app.py check_env.py -ll

# Dependency Vulnerability Audit
pip-audit -r requirements.txt
```

### 4. Running the Test Suite (`pytest`)

We maintain a 100% test pass rate with unit, integration, and UI lifecycle tests:

```bash
# Run all tests with duration breakdown
pytest -v --durations=10

# Run specific test modules
pytest tests/test_extractor.py
pytest tests/test_parser.py
pytest tests/test_mp3_stitcher.py
pytest tests/test_prompts.py
pytest tests/test_ollama.py
pytest tests/test_tts.py
pytest tests/test_player.py
pytest tests/test_ui.py
pytest tests/test_check_env.py
pytest tests/test_e2e_pipeline.py
```

*(Note: On headless Linux environments, run tests using `xvfb-run -a pytest` to support CustomTkinter / Tkinter GUI test fixtures).*

---

## Architecture Guidelines

When adding or modifying components, adhere to the established architectural boundaries:

1. **`core/extractor.py`**:
   - Ingests `.pdf`, `.md`, and `.txt` files.
   - Enforce bounded memory ingestion (default 50 MB file size guard, 200 page PDF limit).
   - Use encoding fallback chains (`utf-8` → `cp1252` → `latin-1`).
2. **`core/prompts.py`**:
   - Manages bilingual prompt engineering (Norwegian Bokmål / English).
   - Manages the 4 duration presets: Quick Summary, Standard Episode, Deep Dive, Extended In-Depth.
   - Manages tone and pacing styles.
3. **`core/parser.py`**:
   - 6-tier resilient JSON parsing pipeline for LLM dialogue turns.
   - Resilient against markdown fences, unescaped quotes, missing brackets, trailing commas, and single-turn dialogues.
4. **`core/ollama.py`**:
   - Communicates with local Ollama HTTP REST API (`http://localhost:11434`).
   - Validates URLs against scheme whitelist (`http://`, `https://`) and localhost bindings.
5. **`core/tts.py`**:
   - Asynchronous synthesis using Microsoft Edge-TTS neural voices.
   - Voice mappings:
     - 🇳🇴 Norwegian: `nb-NO-PernilleNeural` (Host 1 / Kari), `nb-NO-FinnNeural` (Host 2 / Ola)
     - 🇬🇧 English: `en-US-JennyNeural` (Host 1 / Jenny), `en-US-GuyNeural` (Host 2 / Guy)
6. **`core/mp3_stitcher.py`**:
   - Zero-dependency pure Python MP3 frame stitcher.
   - Strips ID3v2 tags and joins MPEG audio frames smoothly without requiring `ffmpeg` binaries.
7. **`core/player.py`**:
   - Native Windows MCI audio playback and export engine.
8. **`ui/` (`theme.py`, `widgets.py`, `main_window.py`)**:
   - Fluent Dark mode CustomTkinter GUI.
   - Always offload heavy tasks (Ollama REST queries, TTS synthesis, audio stitching) to background threads (`threading.Thread`) with UI status callbacks to ensure zero UI freezes.
   - Use `ActionableErrorDialog` for actionable error handling.

---

## Git Commit Guidelines

We adhere to the [Conventional Commits](https://www.conventionalcommits.org/) specification. Format your commit messages as:

```text
<type>(<scope>): <short summary>

[optional body explaining rationale]

[optional footer(s), e.g., Closes #123]
```

### Allowed Types:
- `feat`: A new user-facing feature or enhancement.
- `fix`: A bug fix.
- `docs`: Documentation updates (README, docstrings, governance).
- `style`: Code style, formatting, or white-space changes (no code logic changes).
- `refactor`: Code restructuring without changing behavior or adding features.
- `perf`: Performance optimization.
- `test`: Adding or correcting tests.
- `build`: Changes that affect the build system or packaging (`LocalPodcastLLMStudio.spec`, `build_exe.ps1`).
- `ci`: Changes to CI/CD workflows (`.github/workflows/`).
- `chore`: Maintenance tasks, dependency bumps, or tool configurations.

### Examples:
```text
feat(prompts): add extended in-depth dialogue duration preset
fix(parser): repair trailing comma edge cases in JSON extraction
docs(readme): add standalone executable SHA256 verification guide
ci(workflows): add multi-OS test matrix for Python 3.10-3.12
```

---

## Submitting a Pull Request

1. **Create a Feature Branch**:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. **Commit Your Changes**:
   Make clear, atomic commits following the commit guidelines above.
3. **Run All Quality Gates Locally**:
   ```bash
   ruff check .
   ruff format --check .
   mypy core ui app.py check_env.py
   bandit -r core ui app.py check_env.py -ll
   pytest -v
   ```
4. **Push to Your Fork**:
   ```bash
   git push origin feat/your-feature-name
   ```
5. **Open a Pull Request**:
   - Open a PR against the `main` branch.
   - Fill out the provided [Pull Request Template](pull_request_template.md).
   - Ensure all automated GitHub Actions CI checks pass.
   - A maintainer will review your PR and provide feedback.

---

## Questions and Support

- For bug reports and feature requests, use our [GitHub Issues](https://github.com/tordieltor/LocalPodcastLLMStudio/issues).
- For security vulnerabilities, follow the process in [SECURITY.md](../SECURITY.md).
