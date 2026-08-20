# Project: LocalPodcastLLMStudio — Prerequisite Management & Multi-Tier Grounding Engine

## Architecture

LocalPodcastLLMStudio is a 100% local, two-host AI podcast generator desktop application built with Python 3.10+, CustomTkinter (Fluent Dark theme), Ollama LLMs, Microsoft Edge-TTS neural speech synthesis, zero-FFmpeg binary MP3 stitching, and native Windows MCI audio playback.

```
+---------------------------------------------------------------------------------------------------------+
|                                        APPLICATION ARCHITECTURE                                         |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|  [CustomTkinter UI Layer] (Main GUI Thread)                                                             |
|  ├── ui/main_window.py (MainWindow, Grounding Selector, Model Actions, Streaming Progress, Queue Loop)  |
|  ├── ui/widgets.py     (StatusBadge, Upgraded ActionableErrorDialog with multi-action buttons)          |
|  └── ui/theme.py       (Fluent Dark Theme, Tokyo Night Palette, Typography)                             |
|                                         ▲                             │                                 |
|                        Events via Queue │ (50ms Polling Loop)         │ Dispatches Background Tasks     |
|                                         │                             ▼                                 |
|  [Background Async Workers] ──────────────────────────────────────────────────────────────────────────  |
|  ├── GenerationWorker      (Full generation pipeline: Ingestion -> LLM -> Parser -> TTS -> Stitch)     |
|  ├── ModelPullWorker       (Streaming Ollama /api/pull NDJSON parser with speed & percentage)           |
|  └── OllamaLauncherWorker  (Detached Windows process launcher for ollama.exe with health polling)       |
|                                                                                                         |
|  [Core Domain Subsystems]                                                                               |
|  ├── core/prompts.py       (GroundingMode enum, nb-NO/en-US directives, negative constraints, acts)     |
|  ├── core/ollama.py        (OllamaClient, streaming pull, process launcher, socket Edge-TTS probe)     |
|  ├── core/extractor.py     (Document & topic extraction, validation, format normalization)              |
|  ├── core/parser.py        (6-tier resilient JSON/markdown dialogue parser)                             |
|  ├── core/tts.py           (Edge-TTS neural voice synthesis with rate & pitch controls)                 |
|  ├── core/mp3_stitcher.py  (Zero-FFmpeg binary MPEG frame concatenation)                                |
|  └── core/player.py        (Native Windows MCI audio playback with timeline tracking)                   |
|                                                                                                         |
|  [Verification & Quality Gate]                                                                          |
|  └── tests/                (4-tier test architecture: Unit, Boundary, Combinatorial, E2E Integration)   |
+---------------------------------------------------------------------------------------------------------+
```

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Real-time Prerequisite Detection | Detect Ollama offline, 0 models installed, Edge-TTS reachability | M2 | ORIGINAL_REQUEST R1 |
| F2 | 1-Click Ollama Service Launcher | Windows detached background process launch (`ollama serve`) with polling | M2 | ORIGINAL_REQUEST R1 |
| F3 | Streaming Model Downloader | Interface with `/api/pull` streaming NDJSON with live % / MB/s / ETA | M2 | ORIGINAL_REQUEST R1 |
| F4 | Edge-TTS Network Probe | Lightweight standard-library socket connection check to `speech.platform.bing.com:443` | M2 | ORIGINAL_REQUEST R1 |
| F5 | Strict Source-Only Grounding Mode | 100% document fidelity, strict negative anti-hallucination constraints | M1 | ORIGINAL_REQUEST R2 |
| F6 | Creative Analogy & Synthesis Mode | Document-anchored core insights with illustrative real-world analogies | M1 | ORIGINAL_REQUEST R2 |
| F7 | Open Topic / Scratch Mode | Free generative synthesis from topic prompt without document constraints | M1 | ORIGINAL_REQUEST R2 |
| F8 | Bilingual Grounding Prompts | Specialized system/user/act prompt templates in Norwegian (`nb-NO`) & English (`en-US`) | M1 | ORIGINAL_REQUEST R2 |
| F9 | Grounding Mode UI Selector | UI dropdown in Section 2 with dynamic caption helper & modality auto-sync | M3 | ORIGINAL_REQUEST R3 |
| F10| Model Status & 1-Click Action Buttons | Header & dialog action buttons ("Start Ollama", "Download Model") | M3 | ORIGINAL_REQUEST R3 |
| F11| Dynamic Streaming Progress Bar | Real-time UI progress bar, speed readout, and cancel action for model pull | M3 | ORIGINAL_REQUEST R3 |
| F12| Thread-Safe UI Event Bus | Message queue events (`PULL_PROGRESS`, `PULL_DONE`, `PULL_ERROR`, `SERVICE_*`) | M3 | ORIGINAL_REQUEST R3 |
| F13| Upgraded ActionableErrorDialog | Multi-action buttons and remediation triggers for diagnostic errors | M3 | ORIGINAL_REQUEST R3 |
| F14| Automated Testing & Ruff Quality Gate | 100% test pass rate with pytest, zero warnings with ruff check / format | M4 | ORIGINAL_REQUEST R4 |

---

## Milestones

| # | Milestone Name | Scope & Deliverables | Dependencies | Status |
|---|----------------|----------------------|--------------|--------|
| **M1** | Core Grounding Engine & Prompt Engineering | `core/prompts.py`, `core/ollama.py` grounding parameter propagation, negative anti-hallucination constraints in `nb-NO` and `en-US`, 72-permutation combinatorial matrix | none | DONE |
| **M2** | Prerequisite Manager, Windows Launcher & Streaming Model Downloader | `core/ollama.py` Windows binary resolver, detached `ollama serve` launcher, streaming `/api/pull` NDJSON parser with speed/ETA math, `check_edge_tts_reachability` socket probe | none | DONE |
| **M3** | UI Integration, Controls & Responsive Feedback | `ui/widgets.py` (upgraded `ActionableErrorDialog`, `StatusBadge`), `ui/main_window.py` (Grounding Mode dropdown, Model Status 1-click actions, streaming progress bar, event queue handler) | M1, M2 | IN_PROGRESS |
| **M4** | Comprehensive E2E Testing, Adversarial Verification & Quality Assurance | Opaque-box E2E test suite (Tiers 1-4), adversarial test hardening (Tier 5), fix extractor mock test gap, 100% pytest pass rate, zero ruff errors | M1, M2, M3 | PLANNED |

---

## Interface Contracts

### 1. `core/prompts.py`
```python
from enum import Enum
from typing import Dict, Any, List, Optional

class GroundingMode(str, Enum):
    STRICT = "strict"
    CREATIVE = "creative"
    OPEN_TOPIC = "open_topic"

GROUNDING_MODE_PRESETS: Dict[str, Dict[str, Any]]
GROUNDING_DIRECTIVES_NB: Dict[str, str]
GROUNDING_DIRECTIVES_EN: Dict[str, str]

def normalize_grounding_mode(mode: str) -> str: ...

def build_system_prompt(
    language: str = "nb-NO",
    format_type: str = "standard",
    tone_style: str = "casual",
    grounding_mode: str = "strict"
) -> str: ...

def build_user_prompt(
    content: str,
    language: str = "nb-NO",
    grounding_mode: str = "strict",
    is_topic: bool = False
) -> str: ...

def build_act_system_prompt(
    act: Dict[str, Any],
    total_acts: int,
    language: str = "nb-NO",
    tone_style: str = "casual",
    grounding_mode: str = "strict",
    next_speaker: str = "Host 1"
) -> str: ...

def build_act_user_prompt(
    content: str,
    prev_turns: List[Dict[str, str]],
    language: str = "nb-NO",
    grounding_mode: str = "strict",
    is_topic: bool = False
) -> str: ...
```

### 2. `core/ollama.py`
```python
from dataclasses import dataclass
import threading
from typing import Optional, Callable, List, Tuple

@dataclass
class ModelPullProgress:
    status: str
    digest: str = ""
    total: int = 0
    completed: int = 0
    percentage: float = 0.0       # 0.0 to 1.0
    speed_bps: float = 0.0
    speed_str: str = ""           # e.g., "14.2 MB/s"
    progress_str: str = ""        # e.g., "1.20 GB / 4.70 GB (25.5%)"
    eta_str: str = ""             # e.g., "02:45"
    is_done: bool = False
    error: Optional[str] = None

@dataclass
class PrerequisiteStatus:
    ollama_binary_found: bool
    ollama_binary_path: Optional[str]
    ollama_online: bool
    installed_models: List[str]
    has_recommended_model: bool
    recommended_model_name: str
    edge_tts_online: bool
    all_ready: bool
    remediation_hints: List[str]

def find_ollama_binary() -> Optional[str]: ...

def start_ollama_service(
    timeout: float = 10.0,
    base_url: str = "http://localhost:11434",
    cancel_event: Optional[threading.Event] = None
) -> Tuple[bool, str]: ...

def pull_model_stream(
    model: str,
    base_url: str = "http://localhost:11434",
    progress_callback: Optional[Callable[[ModelPullProgress], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    timeout: float = 3600.0
) -> bool: ...

def check_edge_tts_reachability(timeout: float = 3.0) -> Tuple[bool, str]: ...

def generate_podcast_script(
    content: str,
    language: str = "nb-NO",
    format_type: str = "standard",
    tone_style: str = "casual",
    grounding_mode: str = "strict",
    model: str = "llama3.1:8b",
    ollama_url: str = "http://localhost:11434",
    is_topic: bool = False,
    timeout: float = 300.0,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[str], None]] = None
) -> List[DialogueTurn]: ...
```

### 3. UI Queue Event Protocol (`ui/main_window.py`)
```python
# Event Tuples: (event_type: str, payload: Any)
("OLLAMA_STATUS", {"connected": bool, "models": List[str], "error": Optional[str]})
("SERVICE_LAUNCHING", {"status": str})
("SERVICE_STARTED", {"status": str, "models": List[str]})
("SERVICE_ERROR", {"error": str, "details": str})
("PULL_PROGRESS", ModelPullProgress)
("PULL_DONE", {"model": str, "message": str})
("PULL_ERROR", {"model": str, "error": str})
```

---

## Code Layout

- `core/prompts.py` — Prompt templates, GroundingMode enum, anti-hallucination directives.
- `core/ollama.py` — Ollama client, streaming pull parser, process launcher, Edge-TTS probe.
- `core/extractor.py` — Text extraction & normalization.
- `ui/widgets.py` — CustomTkinter UI widgets (`StatusBadge`, `ActionableErrorDialog`).
- `ui/main_window.py` — Main application window, controls, queue event poller, worker threads.
- `tests/test_prompts.py` — Unit & combinatorial prompt tests.
- `tests/test_ollama.py` — Ollama client, pull stream, and launcher tests.
- `tests/test_ui.py` — UI component and queue integration tests.
- `tests/test_extractor.py` — Extractor unit tests with patched fixtures.
- `tests/test_e2e_pipeline.py` — End-to-end pipeline and recovery tests.
