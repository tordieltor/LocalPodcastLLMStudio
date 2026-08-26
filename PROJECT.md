# Project: LocalPodcastLLMStudio Enhancement

## Architecture
LocalPodcastLLMStudio is a local-first, privacy-focused podcast and audio essay generation studio. The architecture comprises:
- **`core/extractor.py` & `core/exceptions.py`**: Safe document and website extraction engine with protocol allowlisting, DNS/SSRF defense, streaming download size limits, redirect protection, HTML boilerplate stripping, and MarkItDown conversion with resilient fallback.
- **`core/prompts.py`**: Bilingual (Norwegian Bokmål and English) prompt engineering engine supporting two-host dialogue and single-host monologue/audio essay formats across 4 duration presets (`quick`, `standard`, `deep_dive`, `extended`), 3 grounding modes, and 3 tone styles with multi-act narrative arcs.
- **`core/parser.py`**: 6-tier resilient JSON/markdown/plain-text LLM response parser and serializer ensuring robust transcript parsing.
- **`core/tts.py` & `core/mp3_stitcher.py`**: Local/edge neural TTS synthesis engine and zero-FFmpeg MP3 frame stitcher with natural inter-turn/inter-paragraph silence.
- **`core/pipeline.py` & `core/ollama.py`**: 5-stage lifecycle podcast generator service (`PodcastGeneratorService`) orchestrating extraction -> LLM script generation -> TTS synthesis -> master audio assembly with fine-grained progress callbacks.
- **`cli.py`**: Rich headless command-line interface supporting `extract`, `generate-script`, `synthesize-audio`, `stitch`, and `pipeline` with live stage transition indicators.
- **`ui/main_window.py` & `ui/widgets.py`**: CustomTkinter desktop application with multi-modal input tabs (Document, Pasted Text, Topic Prompt, Website URL with extraction preview), Episode Style selector (Dialogue vs Monologue with Solo Voice picker), and `StageProgressTracker` visual stage indicator.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | SSRF Defense & URL Validation | Protocol allowlist (http/https), DNS resolution, IP blocking (loopback, private subnets, cloud metadata/link-local, IPv4-mapped IPv6), 5-redirect ceiling with hop target re-validation | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Safe Fetcher & Download Cap | Streaming download chunking with strict 5 MB cap, 10s timeout, aborting on oversized content | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Boilerplate & Clutter Stripping | Primary container extraction (`<article>`, `<main>`, `#mw-content-text`, `.post-content`), noise element removal (nav, footer, sidebars, cookie banners, ads, Wikipedia citation `[1]` and edit `[edit]` markers) | M1 | ORIGINAL_REQUEST §R1 |
| 4 | MarkItDown Conversion & Fallback | Structured Markdown conversion preserving headings, lists, blockquotes, paragraphs via `markitdown` with internal `html.parser` fallback | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Extractor Routing & Security Errors | `extract_text_from_url`, `extract_text(..., is_url=...)`, URL auto-detection, `SecurityError` and `DocumentExtractionError` hierarchy | M1 | ORIGINAL_REQUEST §R1 |
| 6 | Monologue System Prompts | Bilingual (`nb-NO` and `en-US`) single-host audio essay / monologue system prompts across tones and grounding modes | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Monologue Multi-Act Chapter Specs | 4-chapter narrative arc (Hook & Intro, Exploration & Context, In-Depth Analysis & Dilemmas, Conclusion & Sign-Off) across 4 duration presets (`quick`, `standard`, `deep_dive`, `extended`) in NB and EN | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Monologue Turn & Parser Compatibility | Compatibility with `DialogueParser` 6-tier parsing (pure JSON, markdown code fence, substring, syntax fixes, regex, plain text transcript), `normalize_speaker` mapping solo host to `Host 1` | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Monologue Audio Synthesis & Stitching | `TTSEngine` synthesis using solo host voice, `stitch_mp3_files` inserting natural 350ms inter-paragraph breathing silence | M2 | ORIGINAL_REQUEST §R2 |
| 10 | 5-Stage Lifecycle Progress Model | Structured 5-stage enum (`URL_INGESTION`, `CONTENT_EXTRACTION`, `SCRIPT_GENERATION`, `TTS_SYNTHESIS`, `AUDIO_ASSEMBLY`) and stage status enum (`PENDING`, `IN_ACTION`, `COMPLETED`, `FAILED`, `CANCELLED`) in `core/pipeline.py` | M3 | ORIGINAL_REQUEST §R3 |
| 11 | Granular Multi-Act & TTS Turn Progress | Real-time generation progress (Act X of N, current turn count, token streaming) and TTS progress (Turn X of Y, percentage, active speaker voice) | M3 | ORIGINAL_REQUEST §R3 |
| 12 | CLI Formatted Stage Transitions | `CLILogger.stage` with stderr formatted stage transitions, `--url`, `--host-mode`, and `--solo-voice` across CLI subcommands | M3 | ORIGINAL_REQUEST §R3, §R4 |
| 13 | UI Website URL Input & Preview Tab | CustomTkinter URL input tab in `ui/main_window.py` with asynchronous "Extract & Preview" displaying converted Markdown | M4 | ORIGINAL_REQUEST §R4 |
| 14 | UI Episode Style & Solo Voice Picker | Toggle between "Two Hosts (Dialogue)" and "Solo Host (Monologue)" with dynamic solo voice dropdown and highway profile indicator | M4 | ORIGINAL_REQUEST §R4 |
| 15 | UI StageProgressTracker Widget | Visual stage indicator widget in `ui/widgets.py` displaying Completed (`[✓]`), In Action (`[●]`), and Upcoming (`[⏳]`) stages in real time | M4 | ORIGINAL_REQUEST §R3 |
| 16 | Full CI Verification & Quality Gates | Comprehensive test suite, zero warnings/errors on `ruff check`, `ruff format`, `mypy`, `bandit`, `pytest` | M5 | ORIGINAL_REQUEST §R5, GEMINI.md |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Safe Website Ingestion with MarkItDown & SSRF Defense | `core/exceptions.py`, `core/extractor.py`, `core/__init__.py`, `tests/test_extractor.py` | none | DONE |
| M2 | Monologue Style Episode Generation & Audio Synthesis | `core/prompts.py`, `core/parser.py`, `core/tts.py`, `core/ollama.py`, `tests/test_prompts.py`, `tests/test_parser.py`, `tests/test_tts.py` | none | DONE |
| M3 | Granular Real-Time Stage & Progress Tracking & CLI | `core/pipeline.py`, `cli.py`, `tests/test_pipeline.py`, `tests/test_cli.py` | M1, M2 | DONE |
| M4 | CustomTkinter Desktop UI Integration | `ui/widgets.py`, `ui/main_window.py`, `tests/test_ui.py` | M3 | DONE |
| M5 | Dual-Track E2E Testing, Adversarial Verification & CI Quality Gate | `tests/test_e2e_pipeline.py`, `tests/test_adversarial_*.py`, full verification battery | M1, M2, M3, M4 | DONE |

## Interface Contracts

### `core/extractor.py` ↔ Consumers (`core/pipeline.py`, `cli.py`, `ui/main_window.py`)
- `extract_text_from_url(url: str, timeout: float = 10.0, max_size_bytes: int = 5_242_880, max_redirects: int = 5, progress_callback: Callable[[str], None] | None = None) -> str`
- `extract_text(source: str, is_raw_text: bool = False, is_topic: bool = False, is_url: bool = False, timeout: float = 10.0, max_size_bytes: int = 5_242_880, max_redirects: int = 5, progress_callback: Callable[[str], None] | None = None) -> str`
- Exceptions: `SecurityError(DocumentIngestionError)` raised on invalid IP, blocked subnet, loopback, cloud metadata, or redirect violation. `DocumentExtractionError` raised on download failure, size limit exceeded, or unparseable HTML.

### `core/prompts.py` & `core/parser.py` ↔ `core/ollama.py` & `core/pipeline.py`
- `HostMode` enum: `DIALOGUE = "dialogue"`, `MONOLOGUE = "monologue"`. `normalize_host_mode(mode: str) -> str`.
- `build_system_prompt(language, format_type, tone_style, grounding_mode, host_mode="dialogue") -> str`
- `build_user_prompt(content, language, grounding_mode, is_topic=False, host_mode="dialogue") -> str`
- `get_act_specs(format_type, language, host_mode="dialogue") -> list[dict[str, Any]]`
- `build_act_system_prompt(act, total_acts, language, tone_style, grounding_mode, next_speaker="Host 1", host_mode="dialogue") -> str`
- `build_act_user_prompt(content, prev_turns, language, grounding_mode, is_topic, host_mode="dialogue") -> str`
- `DialogueTurn(speaker="Host 1", text="...")` — all monologue turns use `speaker="Host 1"`.
- `normalize_speaker(raw_speaker: str) -> str` resolves `"host"`, `"narrator"`, `"speaker"`, `"presenter"`, `"kari"`, `"jenny"`, `"host 1"` to `"Host 1"`.

### `core/pipeline.py` ↔ CLI & UI
- `PipelineStage(IntEnum)`: `URL_INGESTION = 1`, `CONTENT_EXTRACTION = 2`, `SCRIPT_GENERATION = 3`, `TTS_SYNTHESIS = 4`, `AUDIO_ASSEMBLY = 5`.
- `StageStatus(str, Enum)`: `PENDING = "pending"`, `IN_ACTION = "in_action"`, `COMPLETED = "completed"`, `FAILED = "failed"`, `CANCELLED = "cancelled"`.
- `StageProgressCallback = Callable[[PipelineStage, StageStatus, float, str], None]`.
- `GenerationOptions`:
  ```python
  @dataclass
  class GenerationOptions:
      content: str
      language: str = "nb-NO"
      model: str = "llama3.1:8b"
      format_type: str = "standard"
      tone_style: str = "casual"
      speed_rate: str = "+0%"
      grounding_mode: str = "strict"
      output_dir: str = "./output"
      is_topic: bool = False
      is_raw_text: bool = False
      is_url: bool = False
      host_mode: str = "dialogue"
      solo_voice: str | None = None
  ```

## Code Layout
- `core/exceptions.py`: `StudioError`, `DocumentIngestionError`, `DocumentExtractionError`, `SecurityError`, `OllamaConnectionError`, `OllamaModelError`, `AudioSynthesisError`.
- `core/extractor.py`: SSRF validation, safe streaming fetch, boilerplate stripping, MarkItDown conversion, file & text extraction.
- `core/prompts.py`: Bilingual dialogue & monologue system prompts, 4-act chapter specs, format presets, prompt builders.
- `core/parser.py`: 6-tier dialogue/monologue turn parser, speaker normalizer, JSON & Markdown serializers.
- `core/tts.py`: Neural voice mapping, turn synthesis, audio pipeline generation.
- `core/mp3_stitcher.py`: MPEG Layer III sync word parser, ID3 tag handling, silence frame injection.
- `core/pipeline.py`: `PodcastGeneratorService`, `PipelineStage`, `StageStatus`, `GenerationOptions`.
- `core/ollama.py`: Ollama API client, script generation with live streaming and act callbacks.
- `cli.py`: Command-line interface with `CLILogger.stage`, subcommands `extract`, `generate-script`, `synthesize-audio`, `stitch`, `pipeline`.
- `ui/widgets.py`: CustomTkinter components (`StageProgressTracker`, `CardFrame`, `DialogueTurnCard`, etc.).
- `ui/main_window.py`: Desktop application window, event loop, modality selector, website extraction preview, episode style selector.
- `tests/`: Pytest test suite covering unit, integration, UI, CLI, and adversarial test tiers.
