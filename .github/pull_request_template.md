## Summary of Changes

<!-- Provide a brief, high-level summary of what this pull request changes or adds. -->

## Type of Change

<!-- Please mark the relevant options with an 'x': -->
- [ ] 🐛 **Bug fix** (non-breaking change fixing an issue)
- [ ] ✨ **New feature** (non-breaking change adding functionality)
- [ ] 💥 **Breaking change** (fix or feature causing existing behavior to change)
- [ ] ♻️ **Refactor** (code cleanup, typing, or architecture improvements)
- [ ] 📝 **Documentation** (README, governance, or docstring updates)
- [ ] 🧪 **Tests** (adding missing tests or updating existing suites)
- [ ] 🚀 **Build / CI** (packaging, pyinstaller spec, or GitHub Actions workflows)
- [ ] 🔒 **Security** (vulnerability remediation or security hardening)

## Related Issue(s)

<!-- Closes #123, Fixes #456, etc. -->
Closes #

## Detailed Changes & Rationale

<!-- Describe the technical approach, key design decisions, and architectural impact. -->
- 

## Verification & Testing

### Automated Checks
<!-- Verify each command passes locally before submitting: -->
- [ ] `ruff check .` passes with **0 errors**
- [ ] `ruff format --check .` passes with **0 errors**
- [ ] `mypy core ui app.py check_env.py` passes with **0 errors**
- [ ] `bandit -r core ui app.py check_env.py -ll` passes with **0 issues**
- [ ] `pytest -v` passes with **100% success rate**
- [ ] `python check_env.py --json` verifies clean diagnostics

### Manual / Integration Verification
<!-- Describe manual verification steps performed (e.g. testing GUI, building .exe, testing Piper TTS generation): -->
- [ ] Verified GUI launches and remains responsive during background generation
- [ ] Tested script generation and JSON parsing with local Ollama model
- [ ] Tested Piper TTS synthesis and pure-Python MP3 binary stitching
- [ ] Tested document ingestion (.txt, .md, .pdf)

## Security & Privacy Checklist

- [ ] **Zero Secrets**: No hardcoded API keys, tokens, or credentials.
- [ ] **Zero Private Paths**: No absolute workstation paths (e.g. `C:\Users\<username>\...`) in tracked code.
- [ ] **Safe Input Handling**: File inputs and URLs are strictly validated and bounded.

## Screenshots / Demo (if applicable)

<!-- Add before/after screenshots or terminal captures for UI or visual changes. -->
