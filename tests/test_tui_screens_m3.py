"""
Unit and Integration Test Suite for Milestone M3 TUI Screens:
- GenerationScreen (tui/screens/generation.py)
- ScriptStudioScreen (tui/screens/script_studio.py)
"""

from __future__ import annotations

import io
import os
from typing import Any
from unittest.mock import MagicMock, patch

from rich.console import Console

from core.parser import DialogueTurn
from tui.screens.generation import GenerationScreen
from tui.screens.script_studio import ScriptStudioScreen
from tui.state import (
    GenerationStatus,
    ScreenMode,
    SynthesisStatus,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import TOKYO_NIGHT_THEME


def _render_to_string(renderable: object, width: int = 120, height: int = 40) -> str:
    """Helper that renders any Rich renderable to a string buffer."""
    buf = io.StringIO()
    console = Console(
        file=buf, width=width, height=height, theme=TOKYO_NIGHT_THEME, legacy_windows=False
    )
    console.print(renderable)
    return buf.getvalue()


# ==============================================================================
# GenerationScreen Tests
# ==============================================================================


class TestGenerationScreen:
    """Comprehensive test battery for GenerationScreen."""

    def test_initial_state_and_rendering(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = GenerationScreen(state=state, event_queue=events)

        assert screen.status_badge.status == "ready"
        assert state.generation.status == GenerationStatus.IDLE

        rendered = _render_to_string(screen)
        assert "Podcast Generation Studio" in rendered
        assert "Generation & Synthesis Pipeline" in rendered
        assert "Live Token Stream Buffer" in rendered
        assert "Standby (Not Generating)" in rendered

    def test_preconditions_validation_failure(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = GenerationScreen(state=state, event_queue=events)

        # Ingestion is invalid and Ollama is checking
        success, msg = screen.start_generation(mode="full")
        assert success is False
        assert screen.active_modal is not None

        modal_rendered = _render_to_string(screen)
        assert "Generation Precondition Failed" in modal_rendered

    @patch("tui.screens.generation.GenerationWorker")
    def test_start_generation_full_and_script_only(self, mock_worker_cls: MagicMock) -> None:
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = False
        mock_worker_cls.return_value = mock_worker

        state = TUIState()
        events = TUIEventQueue()
        state.ingestion.update_extracted("Dette er en gyldig testtekst på over 10 tegn.")
        state.ollama.is_online = True
        state.ollama.available_models = ["llama3.1:8b"]
        state.ollama.selected_model = "llama3.1:8b"

        screen = GenerationScreen(state=state, event_queue=events)

        # Full mode
        success, msg = screen.start_generation(mode="full")
        assert success is True
        assert state.generation.status == GenerationStatus.GENERATING
        assert state.ui.is_busy is True
        mock_worker.start.assert_called_once()

        # Script-only mode (simulate completion/reset of previous run)
        state.ui.is_busy = False
        mock_worker.is_alive.return_value = False
        success2, msg2 = screen.start_generation(mode="script_only")
        assert success2 is True

    @patch("tui.screens.generation.GenerationWorker")
    def test_cancel_and_reset_generation(self, mock_worker_cls: MagicMock) -> None:
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True
        mock_worker_cls.return_value = mock_worker

        state = TUIState()
        events = TUIEventQueue()
        state.ingestion.update_extracted("Gyldig kildetekst med nok tegn.")
        state.ollama.is_online = True
        state.ollama.selected_model = "llama3.1:8b"

        screen = GenerationScreen(state=state, event_queue=events)
        screen.start_generation(mode="full")

        # Cancel
        cancelled = screen.cancel_generation()
        assert cancelled is True
        mock_worker.cancel.assert_called_once()

        # Reset
        screen.reset_generation()
        assert state.generation.status == GenerationStatus.IDLE
        assert state.audio.status == SynthesisStatus.IDLE
        assert state.ui.is_busy is False

    def test_event_handling_flow(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = GenerationScreen(state=state, event_queue=events)

        # GEN_STARTED
        screen.handle_event(TUIEventType.GEN_STARTED, payload={"mode": "full"})
        assert "Generating Dialogue" in screen.status_badge.text

        # GEN_ACT_PROGRESS
        screen.handle_event(
            TUIEventType.GEN_ACT_PROGRESS,
            payload={"current_act": 1, "total_acts": 2, "act_title": "Intro"},
        )
        assert "Act 1/2: Intro" in screen.status_badge.text

        # GEN_TOKEN_STREAM
        screen.handle_event(
            TUIEventType.GEN_TOKEN_STREAM,
            payload={"tps": 24.5, "elapsed": 3.2},
        )
        assert "24.5 tok/s" in screen.status_message

        # GEN_SCRIPT_PARSED
        screen.handle_event(
            TUIEventType.GEN_SCRIPT_PARSED,
            payload={"count": 14},
        )
        assert "14 dialogue turns" in screen.status_message

        # TTS_STARTED
        screen.handle_event(TUIEventType.TTS_STARTED, payload={"total_turns": 14})
        assert "Synthesizing Speech" in screen.status_badge.text

        # TTS_TURN_PROGRESS
        screen.handle_event(
            TUIEventType.TTS_TURN_PROGRESS,
            payload={"current": 3, "total": 14, "speaker": "Host 1"},
        )
        assert "Turn 3/14" in screen.status_badge.text

        # TTS_STITCH_STARTED
        screen.handle_event(TUIEventType.TTS_STITCH_STARTED, payload={"turn_count": 14})
        assert "Stitching MP3" in screen.status_badge.text

        # GEN_COMPLETED
        screen.handle_event(TUIEventType.GEN_COMPLETED, payload={"mode": "full"})
        assert "Generation Complete" in screen.status_badge.text

        # GEN_FAILED
        screen.handle_event(TUIEventType.GEN_FAILED, payload={"error": "Connection timed out"})
        assert "Generation Failed" in screen.status_badge.text
        assert screen.active_modal is not None

    def test_key_handling_shortcuts(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        state.ingestion.update_extracted("Gyldig kildetekst med nok tegn.")
        state.ollama.is_online = True
        state.ollama.selected_model = "llama3.1:8b"

        screen = GenerationScreen(state=state, event_queue=events)

        # Test navigation keys
        assert screen.handle_key("v") is True
        queued = events.drain(10)
        assert len(queued) == 1
        assert queued[0].event_type == TUIEventType.NAVIGATE_SCREEN
        assert queued[0].payload["screen"] == ScreenMode.SCRIPT_STUDIO.value

        assert screen.handle_key("p") is True
        queued2 = events.drain(10)
        assert len(queued2) == 1
        assert queued2[0].payload["screen"] == ScreenMode.PLAYER.value

        # Scrolling keys
        assert screen.handle_key("down") is True
        assert screen.scroll_offset == 2
        assert screen.handle_key("up") is True
        assert screen.scroll_offset == 0

        # Reset key
        assert screen.handle_key("r") is True


# ==============================================================================
# ScriptStudioScreen Tests
# ==============================================================================


class TestScriptStudioScreen:
    """Comprehensive test battery for ScriptStudioScreen."""

    def test_initial_state_and_empty_rendering(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = ScriptStudioScreen(state=state, event_queue=events)

        assert screen.active_tab == ScriptStudioScreen.TAB_FORMATTED
        assert screen.selected_turn_index == 0
        assert len(screen.get_turns()) == 0

        rendered = _render_to_string(screen)
        assert "Interactive Script Studio" in rendered
        assert "Formatted Dialogue" in rendered
        assert "Raw JSON Editor" in rendered
        assert "No dialogue script available to inspect" in rendered

    def test_tab_switching(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = ScriptStudioScreen(state=state, event_queue=events)

        assert screen.active_tab == ScriptStudioScreen.TAB_FORMATTED
        screen.switch_tab()
        assert screen.active_tab == ScriptStudioScreen.TAB_RAW_JSON

        screen.switch_tab(ScriptStudioScreen.TAB_FORMATTED)
        assert screen.active_tab == ScriptStudioScreen.TAB_FORMATTED

    def test_turn_navigation_and_rendering_cards(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        turns = [
            DialogueTurn(speaker="Host 1", text="Hei Kari her. Velkommen til podcasten!"),
            DialogueTurn(speaker="Host 2", text="Hei Ola her. Takk Kari!"),
            DialogueTurn(speaker="Host 1", text="Hva skal vi snakke om i dag?"),
            DialogueTurn(speaker="Host 2", text="I dag skal vi snakke om språkmodeller."),
        ]
        screen = ScriptStudioScreen(state=state, event_queue=events)
        screen.set_turns(turns)

        assert len(screen.get_turns()) == 4
        assert screen.select_turn(1) == 1
        assert screen.next_turn() == 2
        assert screen.prev_turn() == 1

        rendered = _render_to_string(screen)
        assert "Kari" in rendered
        assert "Ola" in rendered
        assert "Turn #1/4" in rendered
        assert "Turn #2/4" in rendered

    def test_copy_script_to_clipboard(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = ScriptStudioScreen(state=state, event_queue=events)

        # Empty turns
        ok, msg = screen.copy_script_to_clipboard()
        assert ok is False

        # With turns
        turns = [DialogueTurn(speaker="Host 1", text="Test transcript line.")]
        screen.set_turns(turns)

        with patch("tui.screens.script_studio._copy_to_system_clipboard", return_value=True):
            ok2, msg2 = screen.copy_script_to_clipboard()
            assert ok2 is True
            assert "Copied 1 dialogue turns" in msg2

    def test_save_script_to_disk(self, tmp_path: Any) -> None:
        state = TUIState()
        events = TUIEventQueue()
        state.config.output_dir = str(tmp_path)
        screen = ScriptStudioScreen(state=state, event_queue=events)

        turns = [
            DialogueTurn(speaker="Host 1", text="Velkommen til episode 1."),
            DialogueTurn(speaker="Host 2", text="Takk for det!"),
        ]
        screen.set_turns(turns)

        ok, msg = screen.save_script_to_disk()
        assert ok is True
        assert os.path.exists(state.generation.script_json_path or "")
        assert os.path.exists(state.generation.script_md_path or "")

    def test_raw_json_editing_and_validation(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = ScriptStudioScreen(state=state, event_queue=events)

        # Valid JSON
        valid_json = (
            "[\n"
            '  {"speaker": "Host 1", "text": "Edited turn 1 text."},\n'
            '  {"speaker": "Host 2", "text": "Edited turn 2 text."}\n'
            "]"
        )
        screen.json_editor_prompt.set_value(valid_json)
        ok, msg = screen.apply_raw_json_edits()
        assert ok is True
        assert len(screen.get_turns()) == 2
        assert screen.get_turns()[0].text == "Edited turn 1 text."

        # Invalid JSON
        screen.json_editor_prompt.set_value("Invalid non-json text without structure")
        ok2, msg2 = screen.apply_raw_json_edits()
        assert ok2 is False
        assert screen.active_modal is not None

    @patch("tui.screens.script_studio.TTSSynthesisWorker")
    def test_synthesize_audio_from_script(self, mock_worker_cls: MagicMock) -> None:
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = False
        mock_worker_cls.return_value = mock_worker

        state = TUIState()
        events = TUIEventQueue()
        screen = ScriptStudioScreen(state=state, event_queue=events)

        # When no turns
        ok, msg = screen.synthesize_audio_from_script()
        assert ok is False
        assert screen.active_modal is not None

        # With turns
        turns = [DialogueTurn(speaker="Host 1", text="Lydsyntese test.")]
        screen.set_turns(turns)
        screen.active_modal = None

        ok2, msg2 = screen.synthesize_audio_from_script()
        assert ok2 is True
        mock_worker.start.assert_called_once()

    def test_script_studio_key_handlers(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        turns = [
            DialogueTurn(speaker="Host 1", text="Turn 1"),
            DialogueTurn(speaker="Host 2", text="Turn 2"),
            DialogueTurn(speaker="Host 1", text="Turn 3"),
        ]
        screen = ScriptStudioScreen(state=state, event_queue=events)
        screen.set_turns(turns)

        # Tab switch key
        assert screen.handle_key("tab") is True
        assert screen.active_tab == ScriptStudioScreen.TAB_RAW_JSON

        assert screen.handle_key("tab") is True
        assert screen.active_tab == ScriptStudioScreen.TAB_FORMATTED

        # Turn navigation keys
        assert screen.handle_key("down") is True
        assert screen.selected_turn_index == 1
        assert screen.handle_key("up") is True
        assert screen.selected_turn_index == 0
        assert screen.handle_key("end") is True
        assert screen.selected_turn_index == 2
        assert screen.handle_key("home") is True
        assert screen.selected_turn_index == 0

        # Screen navigation keys
        assert screen.handle_key("g") is True
        queued = events.drain(10)
        assert queued[0].payload["screen"] == ScreenMode.GENERATION.value

        assert screen.handle_key("p") is True
        queued2 = events.drain(10)
        assert queued2[0].payload["screen"] == ScreenMode.PLAYER.value
