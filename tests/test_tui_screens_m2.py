"""
Unit and integration test suite for Milestone M2 TUI Screens:
- IngestionScreen (tui/screens/ingestion.py)
- OllamaManagerScreen (tui/screens/ollama_mgr.py)
- ConfigScreen (tui/screens/config.py)
"""

from __future__ import annotations

import io
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch

from rich.console import Console

from core.ollama import ModelPullProgress, OllamaClient
from tui.screens.config import ConfigScreen
from tui.screens.ingestion import IngestionScreen
from tui.screens.ollama_mgr import OllamaManagerScreen, sort_models_by_preference
from tui.state import (
    OllamaStatus,
    SourceMode,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import TOKYO_NIGHT_THEME


def _render_to_string(renderable: object, width: int = 100, height: int = 40) -> str:
    """Helper that renders any Rich renderable to a string buffer."""
    buf = io.StringIO()
    console = Console(
        file=buf, width=width, height=height, theme=TOKYO_NIGHT_THEME, legacy_windows=False
    )
    console.print(renderable)
    return buf.getvalue()


# ==============================================================================
# IngestionScreen Unit & Validation Tests
# ==============================================================================


class TestIngestionScreen:
    """Comprehensive test battery for IngestionScreen."""

    def test_initial_state_and_modality_switching(self) -> None:
        """Verifies default ingestion state and modality switching with grounding sync."""
        state = TUIState()
        events = TUIEventQueue()
        screen = IngestionScreen(state=state, event_queue=events)

        assert state.ingestion.source_mode == SourceMode.DOCUMENT
        assert state.config.grounding_mode == "strict"

        # Switch to Pasted Text
        screen.set_mode(SourceMode.PASTED_TEXT)
        assert state.ingestion.source_mode == SourceMode.PASTED_TEXT
        assert state.config.grounding_mode == "strict"

        # Switch to Topic Prompt (should auto-sync grounding mode to open_topic)
        screen.set_mode(SourceMode.TOPIC_PROMPT)
        assert state.ingestion.source_mode == SourceMode.TOPIC_PROMPT
        assert state.config.grounding_mode == "open_topic"

        # Switch back to Document (should auto-sync grounding mode back to strict)
        screen.set_mode(SourceMode.DOCUMENT)
        assert state.ingestion.source_mode == SourceMode.DOCUMENT
        assert state.config.grounding_mode == "strict"

        # Check drained events
        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.INGESTION_MODE_CHANGED in types
        assert TUIEventType.CONFIG_GROUNDING_CHANGED in types

    def test_document_extraction_success_and_metrics(self) -> None:
        """Verifies text extraction from valid document file and metrics updates."""
        state = TUIState()
        events = TUIEventQueue()
        screen = IngestionScreen(state=state, event_queue=events)

        sample_text = (
            "Velkommen til denne podcast-episoden om kunstig intelligens og lokale språkmodeller. "
            "Her diskuterer vi hvordan man kan generere lydopptak på norsk."
        )

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(sample_text)
            temp_path = f.name

        try:
            success, msg = screen.set_file_path(temp_path, auto_extract=True)
            assert success is True
            assert state.ingestion.is_valid is True
            assert state.ingestion.char_count == len(sample_text)
            assert state.ingestion.word_count == len(sample_text.split())
            assert "podcast" in state.ingestion.extracted_text

            queued = events.drain(10)
            types = [e.event_type for e in queued]
            assert TUIEventType.INGESTION_FILE_SELECTED in types
            assert TUIEventType.INGESTION_EXTRACTED in types
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_document_extraction_errors_and_bounding(self) -> None:
        """Verifies error handling for non-existent, unsupported, and oversized files."""
        state = TUIState()
        events = TUIEventQueue()
        screen = IngestionScreen(state=state, event_queue=events, max_file_size_mb=1)

        # 1. Non-existent file
        success, msg = screen.set_file_path("non_existent_document_12345.pdf")
        assert success is False
        assert state.ingestion.is_valid is False
        assert state.ingestion.validation_error is not None
        assert (
            "not found" in state.ingestion.validation_error.lower()
            or "not exist" in state.ingestion.validation_error.lower()
        )

        # 2. Unsupported extension
        with tempfile.NamedTemporaryFile("w", suffix=".exe", delete=False) as f:
            f.write("Binary content")
            exe_path = f.name

        try:
            success, msg = screen.set_file_path(exe_path)
            assert success is False
            assert state.ingestion.is_valid is False
            assert "unsupported" in msg.lower()
        finally:
            if os.path.exists(exe_path):
                os.remove(exe_path)

        # 3. Oversized file (exceeds max_file_size_mb)
        with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as f:
            f.write(b"x" * (2 * 1024 * 1024))  # 2MB > 1MB limit
            large_path = f.name

        try:
            success, msg = screen.set_file_path(large_path)
            assert success is False
            assert state.ingestion.is_valid is False
            assert "exceeds" in msg.lower()
        finally:
            if os.path.exists(large_path):
                os.remove(large_path)

    def test_pasted_text_validation_and_normalization(self) -> None:
        """Verifies pasted text input, minimum length rules, and normalization."""
        state = TUIState()
        screen = IngestionScreen(state=state)
        screen.set_mode(SourceMode.PASTED_TEXT)

        # Too short text (< 5 chars)
        success, msg = screen.set_raw_text("Hi")
        assert success is False
        assert state.ingestion.is_valid is False

        # Valid text
        valid_text = "Dette er en fyldig tekst med nok tegn til å generere en god samtale."
        success, msg = screen.set_raw_text(valid_text)
        assert success is True
        assert state.ingestion.is_valid is True
        assert state.ingestion.char_count == len(valid_text)

    def test_topic_prompt_validation_and_grounding_sync(self) -> None:
        """Verifies topic prompt validation and auto-sync to Open Topic mode."""
        state = TUIState()
        screen = IngestionScreen(state=state)
        screen.set_mode(SourceMode.TOPIC_PROMPT)

        assert state.config.grounding_mode == "open_topic"

        # Too short topic (< 3 chars)
        success, msg = screen.set_topic_prompt("AI")
        assert success is False
        assert state.ingestion.is_valid is False

        # Valid topic prompt
        success, msg = screen.set_topic_prompt(
            "Hvordan bygge en to-personers podcast med lokal LLM?"
        )
        assert success is True
        assert state.ingestion.is_valid is True
        assert "podcast" in state.ingestion.extracted_text

    def test_interactive_key_handling(self) -> None:
        """Verifies hotkey navigation and inline text editing via TextInputPrompt."""
        state = TUIState()
        screen = IngestionScreen(state=state)

        # Modality keys
        assert screen.handle_key("2") == "mode:pasted_text"
        assert state.ingestion.source_mode == SourceMode.PASTED_TEXT

        assert screen.handle_key("3") == "mode:topic_prompt"
        assert state.ingestion.source_mode == SourceMode.TOPIC_PROMPT

        assert screen.handle_key("1") == "mode:document"
        assert state.ingestion.source_mode == SourceMode.DOCUMENT

        # Tab cycling
        assert screen.handle_key("tab") == "mode:pasted_text"
        assert screen.handle_key("tab") == "mode:topic_prompt"
        assert screen.handle_key("tab") == "mode:document"

        # Edit mode
        assert screen.handle_key("e") == "editing:started"
        assert screen.is_editing is True

        # Type into prompt: "a", "b", "c", enter
        screen.handle_key("a")
        screen.handle_key("b")
        screen.handle_key("c")
        action = screen.handle_key("enter")
        assert action == "input:submitted"
        assert screen.is_editing is False

        # Exit key
        assert screen.handle_key("escape") == "navigate:dashboard"

    def test_clear_functionality(self) -> None:
        """Verifies clear() resets all fields and invalidates state."""
        state = TUIState()
        screen = IngestionScreen(state=state)
        screen.set_mode(SourceMode.PASTED_TEXT)
        screen.set_raw_text("En meningsfull tekst for testen.")
        assert state.ingestion.is_valid is True

        screen.clear()
        assert state.ingestion.raw_text == ""
        assert state.ingestion.extracted_text == ""
        assert state.ingestion.char_count == 0
        assert state.ingestion.is_valid is False

    def test_rich_rendering_under_various_dimensions(self) -> None:
        """Verifies visual rendering and card layouts across console dimensions."""
        state = TUIState()
        screen = IngestionScreen(state=state)
        screen.set_mode(SourceMode.DOCUMENT)
        screen.set_file_path("example.txt", auto_extract=False)

        for width in [60, 100, 160]:
            out = _render_to_string(screen, width=width)
            assert "Ingestion" in out
            assert "Document File" in out
            assert "Extraction Status" in out


# ==============================================================================
# OllamaManagerScreen Unit & Integration Tests
# ==============================================================================


class TestOllamaManagerScreen:
    """Comprehensive test battery for OllamaManagerScreen."""

    def test_model_preference_sorting(self) -> None:
        """Verifies sort_models_by_preference ranks llama3.1, mistral-nemo, qwen2.5 correctly."""
        raw_models = ["gemma:2b", "qwen2.5:7b", "llama3.1:8b", "phi3:medium", "mistral:latest"]
        sorted_m = sort_models_by_preference(raw_models)

        assert sorted_m[0] == "llama3.1:8b"
        assert sorted_m[1] == "qwen2.5:7b"
        assert sorted_m[2] == "mistral:latest"

    def test_url_configuration_and_probing(self) -> None:
        """Verifies server URL normalization and connection probing."""
        state = TUIState()
        events = TUIEventQueue()
        screen = OllamaManagerScreen(state=state, event_queue=events)

        with (
            patch.object(OllamaClient, "check_connection", return_value=True),
            patch.object(OllamaClient, "list_models", return_value=["llama3.1:8b"]),
        ):
            success, msg = screen.set_server_url("http://127.0.0.1:11434", probe=True)
            assert success is True
            assert state.ollama.server_url == "http://127.0.0.1:11434"
            assert state.ollama.is_online is True

        # Invalid URL schema
        success, msg = screen.set_server_url("ftp://invalid-host", probe=False)
        assert success is False
        assert "scheme" in msg.lower()

    def test_model_refresh_and_selection(self) -> None:
        """Verifies model catalog retrieval, smart auto-selection, and next/prev cycling."""
        state = TUIState()
        events = TUIEventQueue()
        screen = OllamaManagerScreen(state=state, event_queue=events)

        mock_models = ["llama3:8b", "llama3.1:8b", "mistral-nemo:latest"]

        with patch.object(screen.client, "list_models", return_value=mock_models):
            models = screen.refresh_models()
            assert len(models) == 3
            assert state.ollama.available_models[0] == "llama3.1:8b"
            assert state.ollama.selected_model == "llama3.1:8b"
            assert state.ollama.has_recommended is True

        # Select specific model
        assert screen.select_model("mistral-nemo:latest") is True
        assert state.ollama.selected_model == "mistral-nemo:latest"

        # Select invalid model
        assert screen.select_model("non_existent_model") is False

        # Next / Prev cycling
        next_m = screen.select_next_model()
        assert next_m in state.ollama.available_models

    def test_start_service_success_and_failure(self) -> None:
        """Verifies 1-click background launcher execution and error reporting."""
        state = TUIState()
        events = TUIEventQueue()
        screen = OllamaManagerScreen(state=state, event_queue=events)

        # 1. Successful start
        with patch(
            "tui.screens.ollama_mgr.start_ollama_service", return_value=(True, "Service active")
        ):
            with patch.object(screen.client, "list_models", return_value=["llama3.1:8b"]):
                success, msg = screen.start_service(async_launch=False)
                assert success is True
                assert state.ollama.is_online is True
                assert state.ollama.status == OllamaStatus.ONLINE

        # 2. Failed start
        with patch(
            "tui.screens.ollama_mgr.start_ollama_service", return_value=(False, "Binary not found")
        ):
            success, msg = screen.start_service(async_launch=False)
            assert success is False
            assert state.ollama.is_online is False
            assert state.ollama.status == OllamaStatus.ERROR

    def test_pull_model_streaming_progress_and_cancel(self) -> None:
        """Verifies streaming pull progress tracking and cancellation handling."""
        state = TUIState()
        events = TUIEventQueue()
        screen = OllamaManagerScreen(state=state, event_queue=events)

        def _mock_pull_stream(
            model: str, base_url: str, progress_callback: Any, cancel_event: Any, timeout: float
        ) -> bool:
            # Simulate 2 progress updates
            if progress_callback:
                progress_callback(
                    ModelPullProgress(
                        status="downloading layer",
                        completed=500_000_000,
                        total=1_000_000_000,
                        percentage=0.5,
                        speed_str="15.0 MB/s",
                        eta_str="00:33",
                    )
                )
            return True

        with patch("tui.screens.ollama_mgr.pull_model_stream", side_effect=_mock_pull_stream):
            with patch.object(screen.client, "list_models", return_value=["llama3.1:8b"]):
                success = screen.pull_model("llama3.1:8b", async_pull=False)
                assert success is True
                assert state.ollama.status == OllamaStatus.ONLINE
                assert state.ollama.selected_model == "llama3.1:8b"

        # Test cancel pull
        screen.pull_cancel_event = MagicMock()
        screen.cancel_pull()
        screen.pull_cancel_event.set.assert_called_once()

    def test_interactive_key_handling_ollama(self) -> None:
        """Verifies hotkey navigation in Ollama manager."""
        state = TUIState()
        screen = OllamaManagerScreen(state=state)

        with patch.object(screen, "refresh_models"):
            assert screen.handle_key("r") == "action:refresh"

        with patch.object(screen, "start_service"):
            assert screen.handle_key("s") == "action:start_service"

        assert screen.handle_key("u") == "url:prompt"
        assert screen.is_editing_url is True
        screen.handle_key("escape")
        assert screen.is_editing_url is False

        assert screen.handle_key("p") == "pull:prompt"
        assert screen.is_editing_pull is True
        screen.handle_key("escape")
        assert screen.is_editing_pull is False

        assert screen.handle_key("escape") == "navigate:dashboard"

    def test_rich_rendering_ollama_manager(self) -> None:
        """Verifies visual rendering of Ollama Manager Screen under online, offline, and pull states."""
        state = TUIState()
        screen = OllamaManagerScreen(state=state)

        # Offline state
        state.ollama.is_online = False
        state.ollama.status = OllamaStatus.OFFLINE
        out_offline = _render_to_string(screen)
        assert "Ollama" in out_offline
        assert "Offline" in out_offline

        # Online state with models
        state.ollama.is_online = True
        state.ollama.status = OllamaStatus.ONLINE
        state.ollama.available_models = ["llama3.1:8b", "qwen2.5:7b"]
        state.ollama.selected_model = "llama3.1:8b"
        out_online = _render_to_string(screen)
        assert "Online" in out_online
        assert "llama3.1:8b" in out_online

        # Pulling state
        state.ollama.status = OllamaStatus.PULLING
        state.ollama.pull_model_name = "llama3.1:8b"
        state.ollama.pull_progress = ModelPullProgress(
            status="downloading sha256:abc",
            completed=250000000,
            total=1000000000,
            percentage=0.25,
            speed_str="12.5 MB/s",
            eta_str="01:00",
        )
        out_pull = _render_to_string(screen)
        assert "Pulling model" in out_pull
        assert "12.5 MB/s" in out_pull


# ==============================================================================
# ConfigScreen Unit & Integration Tests
# ==============================================================================


class TestConfigScreen:
    """Comprehensive test battery for ConfigScreen."""

    def test_language_toggle_and_voice_sync(self) -> None:
        """Verifies language toggle synchronizes persona names and default Piper voices."""
        state = TUIState()
        events = TUIEventQueue()
        screen = ConfigScreen(state=state, event_queue=events)

        # Default: nb-NO
        assert state.config.language == "nb-NO"
        assert state.config.host1_name == "Kari"
        assert state.config.host2_name == "Ola"
        assert "no_NO" in state.audio.host1_voice

        # Toggle to English
        screen.toggle_language()
        assert state.config.language == "en-US"
        assert state.config.host1_name == "Jenny"
        assert state.config.host2_name == "Guy"
        assert "en_US" in state.audio.host1_voice
        assert "en_US" in state.audio.host2_voice

        # Toggle back to Norwegian
        screen.toggle_language()
        assert state.config.language == "nb-NO"
        assert state.config.host1_name == "Kari"
        assert state.config.host2_name == "Ola"

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.CONFIG_LANGUAGE_CHANGED in types

    def test_all_length_presets_and_cycling(self) -> None:
        """Verifies all 4 episode length presets (Quick, Standard, Deep Dive, Extended)."""
        state = TUIState()
        events = TUIEventQueue()
        screen = ConfigScreen(state=state, event_queue=events)

        assert screen.set_length_preset("quick") == "quick"
        assert state.config.length_preset == "quick"

        assert screen.set_length_preset("standard") == "standard"
        assert state.config.length_preset == "standard"

        assert screen.set_length_preset("deep_dive") == "deep_dive"
        assert state.config.length_preset == "deep_dive"

        assert screen.set_length_preset("extended") == "extended"
        assert state.config.length_preset == "extended"

        # Cycling
        assert screen.cycle_length_preset() == "quick"
        assert screen.cycle_length_preset() == "standard"

    def test_tone_presets_and_cycling(self) -> None:
        """Verifies all 3 tone presets (Casual, Analytical, Debate)."""
        state = TUIState()
        screen = ConfigScreen(state=state)

        assert screen.set_tone_preset("analytical") == "analytical"
        assert state.config.tone_preset == "analytical"

        assert screen.set_tone_preset("debate") == "debate"
        assert state.config.tone_preset == "debate"

        assert screen.set_tone_preset("casual") == "casual"
        assert state.config.tone_preset == "casual"

        # Cycling
        assert screen.cycle_tone_preset() == "analytical"
        assert screen.cycle_tone_preset() == "debate"
        assert screen.cycle_tone_preset() == "casual"

    def test_grounding_modes_and_localized_descriptions(self) -> None:
        """Verifies 3 grounding modes and localized explainer banners."""
        state = TUIState()
        screen = ConfigScreen(state=state)

        # Strict
        assert screen.set_grounding_mode("strict") == "strict"
        assert state.config.grounding_mode == "strict"
        desc_strict = screen.get_grounding_description()
        assert "forankring" in desc_strict.lower() or "adherence" in desc_strict.lower()

        # Creative
        assert screen.set_grounding_mode("creative") == "creative"
        assert state.config.grounding_mode == "creative"
        desc_creative = screen.get_grounding_description()
        assert "analogi" in desc_creative.lower() or "metaphor" in desc_creative.lower()

        # Open Topic
        assert screen.set_grounding_mode("open_topic") == "open_topic"
        assert state.config.grounding_mode == "open_topic"
        desc_open = screen.get_grounding_description()
        assert "fri" in desc_open.lower() or "generative" in desc_open.lower()

    def test_temperature_and_speed_adjustments(self) -> None:
        """Verifies temperature [0.0..1.0] and speaking speed [-10%..+15%] tuning and clamping."""
        state = TUIState()
        screen = ConfigScreen(state=state)

        # Temperature tuning & clamping
        assert screen.set_temperature(0.85) == 0.85
        assert screen.adjust_temperature(+0.10) == 0.95
        assert screen.set_temperature(1.5) == 1.0
        assert screen.set_temperature(-0.5) == 0.0

        # Speaking speed tuning & clamping
        assert screen.set_speaking_speed(5.0) == 5.0
        assert state.audio.speaking_speed == 5.0
        assert screen.adjust_speaking_speed(+2.5) == 7.5
        assert screen.set_speaking_speed(30.0) == 15.0  # Clamped to +15%
        assert screen.set_speaking_speed(-30.0) == -10.0  # Clamped to -10%

    def test_custom_persona_names_and_system_prompts(self) -> None:
        """Verifies custom host persona names and custom system prompt overrides."""
        state = TUIState()
        screen = ConfigScreen(state=state)

        screen.set_host_names("Astrid", "Magnus")
        assert screen.get_host1_name() == "Astrid"
        assert screen.get_host2_name() == "Magnus"

        # Generated active prompt
        active_prompt = screen.get_active_system_prompt()
        assert "JSON" in active_prompt
        assert "Host 1" in active_prompt

        # Custom override
        custom_p = "You are a custom AI podcast host."
        screen.set_custom_system_prompt(custom_p)
        assert screen.get_active_system_prompt() == custom_p

    def test_output_directory_and_reset(self) -> None:
        """Verifies output directory configuration and full reset to defaults."""
        state = TUIState()
        screen = ConfigScreen(state=state)

        screen.set_output_dir("./custom_podcasts")
        assert state.config.output_dir == "./custom_podcasts"

        screen.reset_to_defaults()
        assert state.config.language == "nb-NO"
        assert state.config.length_preset == "standard"
        assert state.config.tone_preset == "casual"
        assert state.config.grounding_mode == "strict"
        assert state.config.output_dir == "./output"
        assert state.audio.speaking_speed == 0.0
        assert screen.temperature == 0.70

    def test_interactive_key_handling_config(self) -> None:
        """Verifies hotkey shortcuts on ConfigScreen."""
        state = TUIState()
        screen = ConfigScreen(state=state)

        assert screen.handle_key("l") == "config:language"
        assert screen.handle_key("1") == "config:length:quick"
        assert screen.handle_key("2") == "config:length:standard"
        assert screen.handle_key("3") == "config:length:deep_dive"
        assert screen.handle_key("4") == "config:length:extended"
        assert screen.handle_key("t") == "config:tone:cycle"
        assert screen.handle_key("g") == "config:grounding:cycle"
        assert screen.handle_key("+") == "config:temp:up"
        assert screen.handle_key("-") == "config:temp:down"
        assert screen.handle_key("]") == "config:speed:up"
        assert screen.handle_key("[") == "config:speed:down"
        assert screen.handle_key("r") == "config:reset"
        assert screen.handle_key("escape") == "navigate:dashboard"

    def test_rich_rendering_config_screen(self) -> None:
        """Verifies visual rendering of ConfigScreen across configurations."""
        state = TUIState()
        screen = ConfigScreen(state=state)

        out = _render_to_string(screen)
        assert "Settings" in out
        assert "Norwegian Bokmål" in out
        assert "Episode Length" in out
        assert "Grounding" in out
        assert "Temperature" in out
