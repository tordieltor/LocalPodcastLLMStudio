"""
Unit tests for tui/state.py: Central reactive state container, sub-states, validations, and event queue.
"""

from __future__ import annotations

from core.parser import DialogueTurn
from tui.state import (
    AudioSynthesisState,
    GenerationState,
    GenerationStatus,
    IngestionState,
    ModalType,
    OllamaState,
    OllamaStatus,
    PlaybackMode,
    PlayerState,
    PromptConfigState,
    ScreenMode,
    SourceMode,
    SynthesisStatus,
    TUIEvent,
    TUIEventQueue,
    TUIEventType,
    TUIState,
    UIState,
)


def test_substate_initialization() -> None:
    """Verifies default values and types for all sub-states."""
    state = TUIState()
    assert isinstance(state.ingestion, IngestionState)
    assert isinstance(state.ollama, OllamaState)
    assert isinstance(state.config, PromptConfigState)
    assert isinstance(state.generation, GenerationState)
    assert isinstance(state.audio, AudioSynthesisState)
    assert isinstance(state.player, PlayerState)
    assert isinstance(state.ui, UIState)

    assert state.ingestion.source_mode == SourceMode.DOCUMENT
    assert state.ollama.status == OllamaStatus.CHECKING
    assert state.config.language == "nb-NO"
    assert state.generation.status == GenerationStatus.IDLE
    assert state.audio.status == SynthesisStatus.IDLE
    assert state.player.mode == PlaybackMode.STOPPED
    assert state.ui.active_screen == ScreenMode.DASHBOARD
    assert state.ui.active_modal == ModalType.NONE


def test_ingestion_state_update_extracted() -> None:
    """Verifies update_extracted calculates character count, word count, preview, and validity."""
    ing = IngestionState()
    ing.update_extracted("Short")
    assert ing.char_count == 5
    assert ing.word_count == 1
    assert ing.is_valid is False  # Requires >= 10 chars

    long_text = "Word " * 100
    ing.update_extracted(long_text)
    assert ing.char_count == len(long_text.strip())
    assert ing.word_count == 100
    assert ing.is_valid is True
    assert ing.extracted_preview.endswith("...")
    assert len(ing.extracted_preview) <= 360


def test_ollama_state_auto_selection() -> None:
    """Verifies model auto-selection prioritization (llama3.1 > qwen2.5 > mistral > first)."""
    ollama = OllamaState()

    # Empty
    ollama.auto_select_model()
    assert ollama.selected_model == ""

    # Arbitrary models
    ollama.available_models = ["phi3:mini", "gemma2:9b"]
    ollama.auto_select_model()
    assert ollama.selected_model == "phi3:mini"

    # When selection is already valid, auto_select_model without force leaves it
    ollama.available_models = ["phi3:mini", "mistral:7b-instruct", "gemma2:9b"]
    ollama.auto_select_model()
    assert ollama.selected_model == "phi3:mini"

    # With force=True, prefers mistral over phi3
    ollama.auto_select_model(force=True)
    assert ollama.selected_model == "mistral:7b-instruct"

    # Qwen present with force=True
    ollama.available_models = ["phi3:mini", "mistral:7b", "qwen2.5:7b-instruct"]
    ollama.auto_select_model(force=True)
    assert ollama.selected_model == "qwen2.5:7b-instruct"

    # Llama 3.1 present with force=True
    ollama.available_models = ["phi3:mini", "mistral:7b", "llama3.1:8b", "qwen2.5:7b"]
    ollama.auto_select_model(force=True)
    assert ollama.selected_model == "llama3.1:8b"


def test_prompt_config_personas() -> None:
    """Verifies host persona naming logic for Norwegian and English."""
    cfg = PromptConfigState(language="nb-NO")
    assert cfg.host1_name == "Kari"
    assert cfg.host2_name == "Ola"

    cfg.language = "en-US"
    assert cfg.host1_name == "Jenny"
    assert cfg.host2_name == "Guy"


def test_player_state_scrubber_and_formatting() -> None:
    """Verifies PlayerState MM:SS formatting and scrubber progress ratios."""
    player = PlayerState()
    assert player.position_str == "00:00"
    assert player.duration_str == "00:00"
    assert player.scrubber_progress == 0.0

    player.position_ms = 75000  # 1m 15s
    player.duration_ms = 150000  # 2m 30s
    assert player.position_str == "01:15"
    assert player.duration_str == "02:30"
    assert player.scrubber_str == "01:15 / 02:30"
    assert player.scrubber_progress == 0.5


def test_state_validation_rules() -> None:
    """Verifies validate_can_generate, validate_can_synthesize, and validate_can_play."""
    state = TUIState()

    # Initial state cannot generate
    can_gen, reason = state.validate_can_generate()
    assert can_gen is False
    assert "missing or too short" in reason

    state.ingestion.update_extracted("Valid test podcast content with enough length.")
    can_gen, reason = state.validate_can_generate()
    assert can_gen is False
    assert "offline" in reason

    state.ollama.is_online = True
    can_gen, reason = state.validate_can_generate()
    assert can_gen is False
    assert "No Ollama model selected" in reason

    state.ollama.selected_model = "llama3.1:8b"
    can_gen, reason = state.validate_can_generate()
    assert can_gen is True
    assert reason == ""

    # Busy flag blocks generation
    state.ui.is_busy = True
    state.ui.busy_task = "Downloading model"
    can_gen, reason = state.validate_can_generate()
    assert can_gen is False
    assert "busy" in reason
    state.ui.is_busy = False

    # Synthesis validation
    can_synth, synth_reason = state.validate_can_synthesize()
    assert can_synth is False

    state.generation.turns = [DialogueTurn(speaker="Host 1", text="Hello world")]
    can_synth, synth_reason = state.validate_can_synthesize()
    assert can_synth is True

    # Play validation
    can_play, play_reason = state.validate_can_play()
    assert can_play is False
    state.audio.master_mp3_path = "output/podcast.mp3"
    can_play, play_reason = state.validate_can_play()
    assert can_play is True


def test_sync_helpers_and_session_reset() -> None:
    """Verifies voice sync, grounding sync, and clean session reset."""
    state = TUIState()

    # Voice sync
    state.config.language = "en-US"
    state.sync_voices_with_language()
    assert state.audio.host1_voice == "en_US-lessac-medium"
    assert state.audio.host2_voice == "en_US-ryan-medium"

    state.config.language = "nb-NO"
    state.sync_voices_with_language()
    assert state.audio.host1_voice == "no_NO-torkil-medium"
    assert state.audio.host2_voice == "no_NO-torkil-medium"

    # Grounding sync
    state.ingestion.source_mode = SourceMode.TOPIC_PROMPT
    state.sync_grounding_with_modality()
    assert state.config.grounding_mode == "open_topic"

    # Reset
    state.ingestion.update_extracted("Some text")
    state.generation.turns = [DialogueTurn(speaker="Host 1", text="Hello")]
    state.audio.master_mp3_path = "out.mp3"
    state.reset_for_new_session()

    assert state.ingestion.extracted_text == ""
    assert state.generation.turns == []
    assert state.audio.master_mp3_path is None


def test_state_snapshot_isolation() -> None:
    """Verifies that snapshot creates an independent copy."""
    state = TUIState()
    state.ingestion.update_extracted("Original text")
    snap = state.snapshot()

    assert snap.ingestion.extracted_text == "Original text"
    state.ingestion.update_extracted("Modified text")
    assert snap.ingestion.extracted_text == "Original text"


def test_event_queue_and_pubsub() -> None:
    """Verifies thread-safe TUIEventQueue posting, draining, and event subscription."""
    eq = TUIEventQueue()

    received_events: list[TUIEvent] = []

    def handler(ev: TUIEvent) -> None:
        received_events.append(ev)

    eq.subscribe(TUIEventType.INGESTION_FILE_SELECTED, handler)

    ev1 = TUIEvent(
        event_type=TUIEventType.INGESTION_FILE_SELECTED,
        payload={"file_path": "doc.pdf"},
    )
    eq.post(ev1)
    eq.post_event(TUIEventType.OLLAMA_STATUS_UPDATE, payload={"status": "online"})

    drained = eq.drain(max_batch_size=10)
    assert len(drained) == 2
    assert drained[0].event_type == TUIEventType.INGESTION_FILE_SELECTED
    assert drained[1].event_type == TUIEventType.OLLAMA_STATUS_UPDATE

    # Dispatch to subscribers
    eq.dispatch(ev1)
    assert len(received_events) == 1
    assert received_events[0].payload == {"file_path": "doc.pdf"}
