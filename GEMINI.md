# Project Guardrails & Verification Rules

## Pre-Commit & Pre-Push Quality Gate

Before committing or pushing any code changes, always run the full local verification battery matching CI (`ci.yml`):

1. **Linting & Code Style**:
   - Run linter: `.venv/Scripts/python.exe -m ruff check .`
   - Run format checker: `.venv/Scripts/python.exe -m ruff format --check .`
   - *Note*: Always verify **both** `ruff check` and `ruff format`. If formatting violations exist, run `.venv/Scripts/python.exe -m ruff format <path>` to resolve before committing.

2. **Type Checking**:
   - Run type checker: `.venv/Scripts/python.exe -m mypy core ui app.py check_env.py`

3. **Security Analysis (if modifying dependencies or external processes)**:
   - Run bandit: `.venv/Scripts/python.exe -m bandit -r core ui`

4. **Automated Tests**:
   - Run tests: `.venv/Scripts/python.exe -m pytest tests -v`
