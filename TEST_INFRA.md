# PodcastStudio - Test Infrastructure Specification

**Document Version**: 1.0.0  
**Target Environment**: Windows 10/11 x64, Python 3.10+  
**Test Framework**: `pytest` >= 7.4.0, `pytest-mock` >= 3.12.0  
**Test Runner Command**: `pytest -v tests/`

---

## 1. Executive Summary

PodcastStudio is a 100% local, zero-cloud-cost desktop application for Windows that converts text, Markdown, and PDF documents (or prompt-based topics) into studio-grade two-host conversational podcasts. The test infrastructure provides end-to-end verification across 4 distinct testing tiers, ensuring high reliability, zero-defect parsing, fault-tolerant network communication, and precise binary MP3 manipulation without external binary dependencies (no `ffmpeg`).

---

## 2. 4-Tier Testing Methodology

```
+-----------------------------------------------------------------------------------+
|                        PODCASTSTUDIO TEST TIER PYRAMID                            |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  [TIER 4: Real-World Workloads & E2E Integration]                                 |
|  - Full pipeline: Ingestion -> LLM Script -> Parser -> TTS -> MP3 Stitch -> Export|
|  - Document-driven & Scratch Topic workflows in Norwegian & English               |
|                                                                                   |
|  [TIER 3: Cross-Feature & Combinatorial Matrix]                                   |
|  - 2 Languages (nb-NO, en-US) x 4 Episode Lengths x 3 Tone Presets Matrix         |
|  - Ingestion types (.txt, .md, .pdf, raw, topic) x Speed rates (-10% to +15%)     |
|                                                                                   |
|  [TIER 2: Boundary, Adversarial & Error Cascades]                                 |
|  - Multi-encoding fallbacks (UTF-8, UTF-8-BOM, CP1252, Latin-1)                    |
|  - 6-Tier Parser resilience (malformed JSON, code fences, trailing commas, regex) |
|  - Network drops, HTTP timeouts, missing Ollama models, corrupt PDF handling      |
|  - ID3 synchsafe stripping, damaged MPEG sync words, variable bitrates            |
|                                                                                   |
|  [TIER 1: Unit & Feature Component Verification]                                  |
|  - Extractor, Prompts, Parser, Ollama Client, TTS Engine, MP3 Stitcher, Player,   |
|    and Diagnostic Environment Checker                                             |
+-----------------------------------------------------------------------------------+
```

### Tier 1: Feature Component Verification
Unit tests isolating each individual module and function:
- `test_extractor.py`: Plain text, markdown, PDF extraction with `pypdf`, direct paste, and topic prompt mode.
- `test_prompts.py`: Prompt generation for Norwegian Bokmål and English, persona assignments (Kari/Ola, Jenny/Guy), and system instructions.
- `test_parser.py`: Basic JSON array parsing and `DialogueTurn` normalization.
- `test_ollama.py`: REST API tag querying (`/api/tags`), model listing, and payload formatting.
- `test_tts.py`: Voice mapping and rate string formatting.
- `test_mp3_stitcher.py`: MPEG sync word header detection and basic frame concatenation.
- `test_player.py`: Windows MCI command generation (`open`, `play`, `pause`, `stop`, `seek`, `set_volume`).
- `test_check_env.py`: Python version, package imports, Ollama connectivity checks, and JSON output mode.

### Tier 2: Boundary & Corner Cases
Adversarial test cases designed to test fault tolerance and robustness:
- **Encoding & Unicode**: Files with UTF-8-BOM, Windows CP1252, ISO-8859-1 (Latin-1), Norwegian special characters (`æ`, `ø`, `å`), and zero-width characters.
- **Malformed LLM Responses**: JSON embedded in markdown fences, unescaped newlines/quotes, trailing commas before `}` or `]`, broken outer brackets salvaged via regex, and plain text transcripts (`Host 1: ...`).
- **Network Resilience**: HTTP connection refused, socket timeouts, 500 internal server errors from Ollama, Edge-TTS WebSocket disconnects with retry logic.
- **Binary MPEG Handling**: Stream with leading ID3v2.3 tags (with synchsafe sizes), trailing ID3v1 tags (`TAG`), corrupted non-sync bytes, dynamic silence frame insertion.
- **Audio Player State Transitions**: Calling `play` before `load`, seeking out of bounds, volume clamped to 0-100%.

### Tier 3: Cross-Feature Combinations
Combinatorial testing across configuration dimensions:
- **2 Languages**: Norwegian Bokmål (`nb-NO`) and English (`en-US`).
- **4 Episode Formats**:
  1. Quick Summary (6–8 turns)
  2. Standard Episode (12–16 turns)
  3. Deep Dive (20–26 turns)
  4. Extended In-Depth (45–60 turns)
- **3 Dialogue Tones**: Casual & Lively, Analytical & Educational, Lively Debate.
- **2 Generation Modes**: Document-driven vs. Scratch Topic mode.
- **Speaking Speed Range**: `-10%` to `+15%`.

### Tier 4: Real-World Workloads & E2E Verification
Full integration pipeline tests simulating end-to-end user workflows:
1. Document ingestion (.txt / .md / .pdf) -> Prompt assembly -> Mock Ollama generation -> 6-tier resilient parser -> Mock Edge-TTS synthesis -> MP3 binary stitching -> MCI player loading -> File export.
2. "Generate from Scratch" topic workflow -> Full bilingual synthesis -> Final verified MP3 binary output.
3. "Generate Script Only" workflow -> Inspect script -> Synthesize audio from modified script.

---

## 3. Feature Inventory to Test Mapping

| Feature # | Feature Description | Milestone | Primary Test File | Test Tiers Covered |
|---|---|---|---|---|
| F01 | Python & Venv Diagnostic | M1 | `test_check_env.py` | Tier 1, Tier 2 |
| F02 | Package Dependency Check | M1 | `test_check_env.py` | Tier 1, Tier 2 |
| F03 | Ollama API Tag Detection | M1 | `test_check_env.py`, `test_ollama.py` | Tier 1, Tier 2 |
| F04 | Windows Self-Healing Setup | M1 | `test_check_env.py` | Tier 1 |
| F05 | Document Ingestion (.txt/.md) | M2 | `test_extractor.py` | Tier 1, Tier 2 |
| F06 | PDF Document Extraction | M2 | `test_extractor.py` | Tier 1, Tier 2 |
| F07 | Direct Text & Scratch Topic | M2 | `test_extractor.py` | Tier 1, Tier 3 |
| F08 | Bilingual Dialogue Prompts | M2 | `test_prompts.py` | Tier 1, Tier 3 |
| F09 | 4-Preset Episode Format Control | M2 | `test_prompts.py` | Tier 1, Tier 3 |
| F10 | Style & Tone Control (3 Tones) | M2 | `test_prompts.py` | Tier 1, Tier 3 |
| F11 | 6-Tier Resilient JSON Parser | M2 | `test_parser.py` | Tier 1, Tier 2 |
| F12 | Edge-TTS Voice Synthesis | M2 | `test_tts.py` | Tier 1, Tier 2 |
| F13 | Voice Speaking Speed Control | M2 | `test_tts.py` | Tier 1, Tier 3 |
| F14 | Zero-FFmpeg MP3 Stitcher | M2 | `test_mp3_stitcher.py` | Tier 1, Tier 2 |
| F15 | Native Windows MCI Audio Player | M2 | `test_player.py` | Tier 1, Tier 2 |
| F16 | Full End-to-End Pipeline | M5 | `test_e2e_pipeline.py` | Tier 3, Tier 4 |

---

## 4. Test Suite Architecture & Directory Layout

```
tests/
├── __init__.py              # Package marker
├── conftest.py              # Shared fixtures, synthetic MP3 generators, mock LLM/TTS
├── test_extractor.py        # Ingestion tests (.txt, .md, .pdf, UTF-encodings, topic)
├── test_prompts.py          # Prompt generation (bilingual, 4 lengths, 3 tones)
├── test_parser.py           # 6-tier resilient parser (valid, fences, broken JSON, salvage)
├── test_ollama.py           # Ollama client (API tags, generate, timeouts, retries)
├── test_tts.py              # Edge-TTS synthesis (voice map, rates, async turns)
├── test_mp3_stitcher.py     # Binary MP3 stitcher (ID3 strip, MPEG frames, silence)
├── test_player.py           # Native Windows MCI player (open, play, pause, seek, vol)
├── test_check_env.py        # Environment diagnostic preflight checks
└── test_e2e_pipeline.py     # Comprehensive end-to-end integration workflows
```

---

## 5. Test Execution Instructions

### Running All Tests
```bash
pytest -v tests/
```

### Running Specific Test Modules
```bash
pytest -v tests/test_extractor.py
pytest -v tests/test_prompts.py
pytest -v tests/test_parser.py
pytest -v tests/test_ollama.py
pytest -v tests/test_tts.py
pytest -v tests/test_mp3_stitcher.py
pytest -v tests/test_player.py
pytest -v tests/test_check_env.py
pytest -v tests/test_e2e_pipeline.py
```

### Running with Code Coverage
```bash
pytest -v --cov=core --cov=check_env tests/
```
