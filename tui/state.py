"""
LocalPodcastLLMStudio - Reactive State Model & Event System
Defines the centralized TUI state container, domain sub-states, typed event bus,
validation rules, and thread-safe mutation abstractions.
"""

from __future__ import annotations

import copy
import queue
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.ollama import ModelPullProgress
from core.parser import DialogueTurn

# ==============================================================================
# Domain Enumerations
# ==============================================================================


class SourceMode(str, Enum):
    """Input modality for podcast source content."""

    DOCUMENT = "document"
    PASTED_TEXT = "pasted_text"
    TOPIC_PROMPT = "topic_prompt"


class OllamaStatus(str, Enum):
    """Status of the local Ollama LLM service."""

    OFFLINE = "offline"
    CHECKING = "checking"
    STARTING = "starting"
    ONLINE = "online"
    PULLING = "pulling"
    ERROR = "error"


class GenerationStatus(str, Enum):
    """Status of dialogue script generation."""

    IDLE = "idle"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SynthesisStatus(str, Enum):
    """Status of Piper TTS speech synthesis and MP3 stitching."""

    IDLE = "idle"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlaybackMode(str, Enum):
    """Audio player playback state."""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    NOT_READY = "not_ready"


class ScreenMode(str, Enum):
    """Active full-screen view in TUI navigation."""

    DASHBOARD = "dashboard"
    INGESTION = "ingestion"
    OLLAMA = "ollama"
    CONFIG = "config"
    GENERATION = "generation"
    SCRIPT_STUDIO = "script_studio"
    PLAYER = "player"
    HELP = "help"


class ModalType(str, Enum):
    """Active modal overlay dialog."""

    NONE = "none"
    FILE_BROWSER = "file_browser"
    TEXT_ENTRY = "text_entry"
    MODEL_PULL = "model_pull"
    ERROR = "error"
    CONFIRMATION = "confirmation"
    ABOUT = "about"
    SHORTCUTS = "shortcuts"


class TUIEventType(str, Enum):
    """Typed events dispatched across workers, audio engine, and render loop."""

    # Ingestion Events
    INGESTION_MODE_CHANGED = "ingestion:mode_changed"
    INGESTION_FILE_SELECTED = "ingestion:file_selected"
    INGESTION_TEXT_CHANGED = "ingestion:text_changed"
    INGESTION_TOPIC_CHANGED = "ingestion:topic_changed"
    INGESTION_EXTRACTED = "ingestion:extracted"
    INGESTION_ERROR = "ingestion:error"

    # Ollama Events
    OLLAMA_PROBE_REQUESTED = "ollama:probe_requested"
    OLLAMA_STATUS_UPDATE = "ollama:status_update"
    OLLAMA_SERVICE_LAUNCHING = "ollama:service_launching"
    OLLAMA_SERVICE_STARTED = "ollama:service_started"
    OLLAMA_SERVICE_ERROR = "ollama:service_error"
    OLLAMA_MODELS_LOADED = "ollama:models_loaded"
    OLLAMA_MODEL_SELECTED = "ollama:model_selected"
    OLLAMA_PULL_START = "ollama:pull_start"
    OLLAMA_PULL_PROGRESS = "ollama:pull_progress"
    OLLAMA_PULL_DONE = "ollama:pull_done"
    OLLAMA_PULL_ERROR = "ollama:pull_error"
    OLLAMA_PULL_CANCELLED = "ollama:pull_cancelled"

    # Generation Config Events
    CONFIG_LANGUAGE_CHANGED = "config:language_changed"
    CONFIG_LENGTH_CHANGED = "config:length_changed"
    CONFIG_TONE_CHANGED = "config:tone_changed"
    CONFIG_GROUNDING_CHANGED = "config:grounding_changed"
    CONFIG_SPEED_CHANGED = "config:speed_changed"
    CONFIG_OUTPUT_DIR_CHANGED = "config:output_dir_changed"

    # Dialogue Generation Pipeline Events
    GEN_STARTED = "gen:started"
    GEN_ACT_PROGRESS = "gen:act_progress"
    GEN_TOKEN_STREAM = "gen:token_stream"  # nosec B105
    GEN_SCRIPT_PARSED = "gen:script_parsed"
    GEN_COMPLETED = "gen:completed"
    GEN_FAILED = "gen:failed"
    GEN_CANCELLED = "gen:cancelled"

    # TTS Synthesis & Assembly Events
    TTS_STARTED = "tts:started"
    TTS_TURN_PROGRESS = "tts:turn_progress"
    TTS_STITCH_STARTED = "tts:stitch_started"
    TTS_COMPLETED = "tts:completed"
    TTS_FAILED = "tts:failed"
    TTS_CANCELLED = "tts:cancelled"

    # Audio Player Events
    PLAYER_FILE_LOADED = "player:file_loaded"
    PLAYER_PLAY = "player:play"
    PLAYER_PAUSE = "player:pause"
    PLAYER_STOP = "player:stop"
    PLAYER_SEEK = "player:seek"
    PLAYER_POSITION_UPDATE = "player:position_update"
    PLAYER_VOLUME_CHANGED = "player:volume_changed"

    # UI & Navigation Events
    NAVIGATE_SCREEN = "ui:navigate_screen"
    OPEN_MODAL = "ui:open_modal"
    CLOSE_MODAL = "ui:close_modal"
    SET_STATUS_MESSAGE = "ui:status_message"
    SET_BUSY = "ui:set_busy"
    TERMINAL_RESIZE = "ui:terminal_resize"
    QUIT_REQUESTED = "ui:quit_requested"


# ==============================================================================
# Domain Sub-State Dataclasses
# ==============================================================================


@dataclass
class IngestionState:
    """Governs document file selection, pasted text, and scratch topic input."""

    source_mode: SourceMode = SourceMode.DOCUMENT
    file_path: str = ""
    raw_text: str = ""
    topic_prompt: str = ""
    extracted_text: str = ""
    extracted_preview: str = ""
    char_count: int = 0
    word_count: int = 0
    validation_error: str | None = None
    is_valid: bool = False

    def update_extracted(self, text: str) -> None:
        """Updates extracted text and recalculates derived counts and preview."""
        self.extracted_text = text.strip()
        self.char_count = len(self.extracted_text)
        self.word_count = len(self.extracted_text.split()) if self.extracted_text else 0
        if len(self.extracted_text) > 350:
            self.extracted_preview = self.extracted_text[:350].rsplit(" ", 1)[0] + "..."
        else:
            self.extracted_preview = self.extracted_text
        self.is_valid = self.char_count >= 10
        if self.is_valid:
            self.validation_error = None


@dataclass
class OllamaState:
    """Governs local Ollama server connectivity, model catalog, and downloading."""

    server_url: str = "http://localhost:11434"
    status: OllamaStatus = OllamaStatus.CHECKING
    is_online: bool = False
    daemon_running: bool = False
    available_models: list[str] = field(default_factory=list)
    selected_model: str = ""
    recommended_model: str = "llama3.1:8b"
    has_recommended: bool = False
    pull_model_name: str = ""
    pull_progress: ModelPullProgress | None = None
    error_message: str | None = None

    def auto_select_model(self, force: bool = False) -> None:
        """Applies priority ranking to select the most optimal model."""
        if not force and self.selected_model and self.selected_model in self.available_models:
            return

        # 1. Prefer llama3.1 variants
        for m in self.available_models:
            if "llama3.1" in m.lower():
                self.selected_model = m
                return

        # 2. Prefer qwen2.5 variants
        for m in self.available_models:
            if "qwen2.5" in m.lower():
                self.selected_model = m
                return

        # 3. Prefer mistral variants
        for m in self.available_models:
            if "mistral" in m.lower():
                self.selected_model = m
                return

        # 4. Fallback to first available model
        if self.available_models:
            self.selected_model = self.available_models[0]
        else:
            self.selected_model = ""


@dataclass
class PromptConfigState:
    """Configures LLM generation parameters, personas, presets, and output paths."""

    language: str = "nb-NO"
    length_preset: str = "standard"
    tone_preset: str = "casual"
    grounding_mode: str = "strict"
    output_dir: str = "./output"

    @property
    def host1_name(self) -> str:
        """Returns localized display persona name for Host 1."""
        return "Kari" if "nb" in self.language.lower() else "Jenny"

    @property
    def host2_name(self) -> str:
        """Returns localized display persona name for Host 2."""
        return "Ola" if "nb" in self.language.lower() else "Guy"


@dataclass
class GenerationState:
    """Tracks real-time LLM streaming, act progression, and parsed dialogue turns."""

    status: GenerationStatus = GenerationStatus.IDLE
    current_act: int = 0
    total_acts: int = 0
    act_title: str = ""
    streamed_tokens: str = ""
    turns: list[DialogueTurn] = field(default_factory=list)
    raw_json_script: str = ""
    script_json_path: str | None = None
    script_md_path: str | None = None
    generation_error: str | None = None
    elapsed_time_sec: float = 0.0
    tokens_per_sec: float = 0.0


@dataclass
class AudioSynthesisState:
    """Controls Piper neural voice engine, speed rate, turn progress, and MP3 assembly."""

    engine: str = "piper"
    host1_voice: str = "no_NO-torkil-medium"
    host2_voice: str = "no_NO-torkil-medium"
    speaking_speed: float = 0.0
    status: SynthesisStatus = SynthesisStatus.IDLE
    current_turn: int = 0
    total_turns: int = 0
    current_speaker: str = ""
    progress_pct: float = 0.0
    temp_turn_files: list[str] = field(default_factory=list)
    master_mp3_path: str | None = None
    synthesis_error: str | None = None


@dataclass
class PlayerState:
    """Tracks Windows MCI player playback status, timeline scrubber, and volume."""

    mode: PlaybackMode = PlaybackMode.STOPPED
    current_file: str | None = None
    position_ms: int = 0
    duration_ms: int = 0
    volume: int = 80
    is_seeking: bool = False
    is_loaded: bool = False

    @staticmethod
    def format_ms(ms: int) -> str:
        """Formats milliseconds into MM:SS string."""
        sec = max(0, int(ms / 1000))
        m = sec // 60
        s = sec % 60
        return f"{m:02d}:{s:02d}"

    @property
    def position_str(self) -> str:
        """Formatted current position string."""
        return self.format_ms(self.position_ms)

    @property
    def duration_str(self) -> str:
        """Formatted total duration string."""
        return self.format_ms(self.duration_ms)

    @property
    def scrubber_str(self) -> str:
        """Combined timeline string 'MM:SS / MM:SS'."""
        return f"{self.position_str} / {self.duration_str}"

    @property
    def scrubber_progress(self) -> float:
        """Normalized progress ratio in range [0.0, 1.0]."""
        if self.duration_ms <= 0:
            return 0.0
        return min(1.0, max(0.0, self.position_ms / self.duration_ms))


@dataclass
class UIState:
    """Tracks active screen, modal overlays, focus indices, and console geometry."""

    active_screen: ScreenMode = ScreenMode.DASHBOARD
    active_modal: ModalType = ModalType.NONE
    modal_data: dict[str, Any] = field(default_factory=dict)
    focus_index: int = 0
    status_message: str = "Ready"
    status_level: str = "info"
    is_busy: bool = False
    busy_task: str = ""
    selected_script_tab: str = "formatted"
    selected_turn_index: int = 0
    terminal_width: int = 120
    terminal_height: int = 35


# ==============================================================================
# Central Reactive State Container
# ==============================================================================


class TUIState:
    """
    Central reactive state container aggregating all domain sub-states with
    re-entrant thread locking, synchronization helpers, and validation rules.
    """

    def __init__(self) -> None:
        self.lock: threading.RLock = threading.RLock()
        self.ingestion: IngestionState = IngestionState()
        self.ollama: OllamaState = OllamaState()
        self.config: PromptConfigState = PromptConfigState()
        self.generation: GenerationState = GenerationState()
        self.audio: AudioSynthesisState = AudioSynthesisState()
        self.player: PlayerState = PlayerState()
        self.ui: UIState = UIState()

    def validate_can_generate(self) -> tuple[bool, str]:
        """
        Validates whether prerequisite conditions are met to initiate dialogue generation.

        Returns:
            Tuple[bool, str]: (is_valid, error_reason)
        """
        with self.lock:
            if self.ui.is_busy:
                return False, f"System is currently busy: {self.ui.busy_task}"
            if not self.ingestion.is_valid:
                return (
                    False,
                    "Input content is missing or too short (minimum 10 characters required).",
                )
            if not self.ollama.is_online:
                return False, "Ollama service is offline. Please start Ollama before generating."
            if not self.ollama.selected_model:
                return False, "No Ollama model selected. Please download or select an active model."
            return True, ""

    def validate_can_synthesize(self) -> tuple[bool, str]:
        """
        Validates whether prerequisite conditions are met to initiate TTS synthesis.

        Returns:
            Tuple[bool, str]: (is_valid, error_reason)
        """
        with self.lock:
            if self.ui.is_busy:
                return False, f"System is currently busy: {self.ui.busy_task}"
            if not self.generation.turns:
                return False, "No dialogue turns available. Generate or load a script first."
            return True, ""

    def validate_can_play(self) -> tuple[bool, str]:
        """
        Validates whether audio file is loaded and ready for playback.

        Returns:
            Tuple[bool, str]: (is_valid, error_reason)
        """
        with self.lock:
            if self.player.is_loaded or self.audio.master_mp3_path:
                return True, ""
            return False, "No audio file loaded or synthesized yet."

    def sync_voices_with_language(self) -> None:
        """Synchronizes default Piper voice selections with selected language."""
        with self.lock:
            if "nb" in self.config.language.lower():
                self.audio.host1_voice = "no_NO-torkil-medium"
                self.audio.host2_voice = "no_NO-torkil-medium"
            else:
                self.audio.host1_voice = "en_US-lessac-medium"
                self.audio.host2_voice = "en_US-ryan-medium"

    def sync_grounding_with_modality(self) -> None:
        """Synchronizes grounding mode preset with the selected input modality."""
        with self.lock:
            if self.ingestion.source_mode == SourceMode.TOPIC_PROMPT:
                self.config.grounding_mode = "open_topic"
            elif self.config.grounding_mode == "open_topic":
                self.config.grounding_mode = "strict"

    def reset_for_new_session(self) -> None:
        """Resets ingestion, generation, and audio synthesis for a clean session."""
        with self.lock:
            self.ingestion = IngestionState()
            self.generation = GenerationState()
            self.audio.temp_turn_files = []
            self.audio.master_mp3_path = None
            self.audio.progress_pct = 0.0
            self.audio.status = SynthesisStatus.IDLE
            self.audio.synthesis_error = None
            self.player.mode = PlaybackMode.STOPPED
            self.player.position_ms = 0
            self.player.duration_ms = 0
            self.player.is_loaded = False
            self.player.current_file = None
            self.ui.status_message = "Ready for new session"
            self.ui.status_level = "info"

    def reset_generation_state(self) -> None:
        """Clears streamed generation output and error state."""
        with self.lock:
            self.generation = GenerationState()

    def reset_audio_state(self) -> None:
        """Clears audio temporary files and synthesis state."""
        with self.lock:
            self.audio.status = SynthesisStatus.IDLE
            self.audio.current_turn = 0
            self.audio.total_turns = 0
            self.audio.progress_pct = 0.0
            self.audio.temp_turn_files.clear()
            self.audio.master_mp3_path = None
            self.audio.synthesis_error = None

    def snapshot(self) -> TUIState:
        """Creates an isolated deep-copy snapshot of state for safe rendering."""
        with self.lock:
            snap = TUIState()
            snap.ingestion = copy.deepcopy(self.ingestion)
            snap.ollama = copy.deepcopy(self.ollama)
            snap.config = copy.deepcopy(self.config)
            snap.generation = copy.deepcopy(self.generation)
            snap.audio = copy.deepcopy(self.audio)
            snap.player = copy.deepcopy(self.player)
            snap.ui = copy.deepcopy(self.ui)
            return snap


# ==============================================================================
# Typed Event Bus & Queue
# ==============================================================================


@dataclass(frozen=True)
class TUIEvent:
    """Strongly-typed event dispatched across worker threads and main render loop."""

    event_type: TUIEventType | str
    payload: Any = None
    error: str | None = None
    timestamp: float = field(default_factory=time.time)


class TUIEventQueue:
    """
    Thread-safe FIFO event queue and observer pub/sub bus for TUI state updates.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[TUIEvent] = queue.Queue()
        self._subscribers: dict[str, list[Callable[[TUIEvent], None]]] = defaultdict(list)
        self._lock: threading.Lock = threading.Lock()

    def post(self, event: TUIEvent) -> None:
        """Thread-safe enqueue of a typed TUI event."""
        self._queue.put_nowait(event)

    def post_event(
        self,
        event_type: TUIEventType | str,
        payload: Any = None,
        error: str | None = None,
    ) -> None:
        """Convenience method constructing and enqueuing a TUIEvent."""
        self.post(TUIEvent(event_type=event_type, payload=payload, error=error))

    def drain(self, max_batch_size: int = 50) -> list[TUIEvent]:
        """
        Drains and returns up to max_batch_size events without blocking.

        Args:
            max_batch_size: Maximum number of events to dequeue in one cycle.

        Returns:
            List[TUIEvent]: Dequeued events in FIFO arrival order.
        """
        events: list[TUIEvent] = []
        for _ in range(max_batch_size):
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def subscribe(
        self,
        event_type: TUIEventType | str,
        handler: Callable[[TUIEvent], None],
    ) -> None:
        """Subscribes a callback to an event type."""
        key = event_type.value if isinstance(event_type, Enum) else str(event_type)
        with self._lock:
            self._subscribers[key].append(handler)

    def dispatch(self, event: TUIEvent) -> None:
        """Dispatches an event directly to all registered subscriber callbacks."""
        key = (
            event.event_type.value if isinstance(event.event_type, Enum) else str(event.event_type)
        )
        with self._lock:
            handlers = list(self._subscribers.get(key, []))
            all_handlers = list(self._subscribers.get("*", []))

        for h in handlers + all_handlers:
            try:
                h(event)
            except Exception:  # nosec B110
                pass
