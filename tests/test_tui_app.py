"""
Unit and Integration Test Suite for Milestone M4 TUI Application & Screens:
- AudioPlayerScreen (tui/screens/player.py)
- HelpScreen (tui/screens/help.py)
- DashboardScreen (tui/screens/dashboard.py)
- TUIApplication (tui/app.py)
- TUI Launcher (tui.py)
"""

from __future__ import annotations

import importlib.util
import io
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from rich.console import Console

from core.parser import DialogueTurn
from tui.app import TUIApplication
from tui.input import MockInputReader, QueueInputReader
from tui.screens.dashboard import DashboardScreen
from tui.screens.help import HelpScreen
from tui.screens.player import AudioPlayerScreen
from tui.state import (
    ModalType,
    PlaybackMode,
    ScreenMode,
    SourceMode,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import TOKYO_NIGHT_THEME

_tui_py_path = Path(__file__).resolve().parent.parent / "tui.py"
_spec = importlib.util.spec_from_file_location("tui_launcher", str(_tui_py_path))
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load tui.py from {_tui_py_path}")
tui_launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tui_launcher)


def _render_to_string(renderable: object, width: int = 120, height: int = 40) -> str:
    """Helper that renders any Rich renderable to a string buffer."""
    buf = io.StringIO()
    console = Console(
        file=buf, width=width, height=height, theme=TOKYO_NIGHT_THEME, legacy_windows=False
    )
    console.print(renderable)
    return buf.getvalue()


# ==============================================================================
# AudioPlayerScreen Tests
# ==============================================================================


class TestAudioPlayerScreen:
    """Comprehensive test battery for AudioPlayerScreen."""

    def test_initial_state_and_rendering(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        mock_player = MagicMock()
        mock_player.get_length.return_value = 0
        mock_player.get_mode.return_value = "stopped"
        mock_player.get_position.return_value = 0

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)

        assert screen.status_badge.status == "offline"
        assert state.player.mode == PlaybackMode.STOPPED

        rendered = _render_to_string(screen)
        assert "Audio Player & Timeline Scrubber" in rendered
        assert "No Audio File Loaded" in rendered
        assert "Master Volume" in rendered

    def test_load_and_play_file(self, tmp_path: Any) -> None:
        state = TUIState()
        events = TUIEventQueue()
        dummy_mp3 = tmp_path / "test_podcast.mp3"
        dummy_mp3.write_bytes(b"\xff\xfb\x90\x44" * 100)

        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 45000
        mock_player.play.return_value = True
        mock_player.get_mode.return_value = "playing"
        mock_player.get_position.return_value = 1000

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)

        # Load file
        success = screen.load_file(str(dummy_mp3))
        assert success is True
        assert state.player.is_loaded is True
        assert state.player.duration_ms == 45000

        # Play file
        play_success = screen.play()
        assert play_success is True
        assert state.player.mode == PlaybackMode.PLAYING
        mock_player.play.assert_called_once()

    def test_pause_resume_stop_and_seek(self, tmp_path: Any) -> None:
        state = TUIState()
        events = TUIEventQueue()
        dummy_mp3 = tmp_path / "test.mp3"
        dummy_mp3.write_bytes(b"\xff\xfb\x90\x44" * 50)

        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 60000
        mock_player.pause.return_value = True
        mock_player.resume.return_value = True
        mock_player.stop.return_value = True
        mock_player.seek.return_value = True
        mock_player.get_position.return_value = 5000

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)
        screen.load_file(str(dummy_mp3))

        # Pause
        assert screen.pause() is True
        assert state.player.mode == PlaybackMode.PAUSED

        # Resume
        assert screen.resume() is True
        assert state.player.mode == PlaybackMode.PLAYING

        # Toggle play/pause
        assert screen.toggle_play_pause() is True  # currently playing -> pauses
        assert state.player.mode == PlaybackMode.PAUSED

        # Seek absolute & relative
        pos = screen.seek(15000)
        assert pos == 15000
        assert state.player.position_ms == 15000

        pos2 = screen.seek_relative(5000)
        assert pos2 == 20000
        assert state.player.position_ms == 20000

        # Stop
        assert screen.stop() is True
        assert state.player.mode == PlaybackMode.STOPPED
        assert state.player.position_ms == 0

    def test_volume_adjustment(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        mock_player = MagicMock()
        mock_player.set_volume.return_value = True

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)

        vol = screen.set_volume(85)
        assert vol == 85
        assert state.player.volume == 85

        vol2 = screen.adjust_volume(+10)
        assert vol2 == 95
        assert state.player.volume == 95

        vol3 = screen.adjust_volume(-20)
        assert vol3 == 75

    def test_export_audio_and_open_folder(self, tmp_path: Any) -> None:
        state = TUIState()
        events = TUIEventQueue()
        dummy_mp3 = tmp_path / "source.mp3"
        dummy_mp3.write_bytes(b"\xff\xfb\x90\x44" * 10)

        dest_mp3 = tmp_path / "exported.mp3"

        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 10000

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)
        screen.load_file(str(dummy_mp3))

        # Export
        ok, msg = screen.export_audio(str(dest_mp3))
        assert ok is True
        assert os.path.exists(dest_mp3)

        # Open folder
        with patch("os.startfile", create=True) as mock_startfile:
            assert screen.open_containing_folder() is True
            if sys.platform == "win32":
                mock_startfile.assert_called_once()

    def test_player_key_handlers(self, tmp_path: Any) -> None:
        state = TUIState()
        events = TUIEventQueue()
        dummy_mp3 = tmp_path / "keys.mp3"
        dummy_mp3.write_bytes(b"\xff\xfb\x90\x44" * 10)

        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 30000
        mock_player.play.return_value = True
        mock_player.pause.return_value = True
        mock_player.stop.return_value = True
        mock_player.seek.return_value = True

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)
        screen.load_file(str(dummy_mp3))

        # Space key toggles play/pause
        assert screen.handle_key("space") is True
        assert state.player.mode == PlaybackMode.PLAYING

        # S stops
        assert screen.handle_key("s") is True
        assert state.player.mode == PlaybackMode.STOPPED

        # Arrow keys seek
        assert screen.handle_key("right") is True
        assert screen.handle_key("left") is True
        assert screen.handle_key("page_up") is True
        assert screen.handle_key("page_down") is True
        assert screen.handle_key("home") is True
        assert screen.handle_key("end") is True

        # Volume keys
        assert screen.handle_key("up") is True
        assert screen.handle_key("down") is True

        # Navigation shortcuts
        assert screen.handle_key("g") is True
        assert screen.handle_key("v") is True

        queued = events.drain(50)
        screens_queued = [
            e.payload.get("screen") for e in queued if e.event_type == TUIEventType.NAVIGATE_SCREEN
        ]
        assert ScreenMode.GENERATION.value in screens_queued
        assert ScreenMode.SCRIPT_STUDIO.value in screens_queued


# ==============================================================================
# HelpScreen Tests
# ==============================================================================


class TestHelpScreen:
    """Comprehensive test battery for HelpScreen."""

    def test_initial_state_and_rendering(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = HelpScreen(state=state, event_queue=events)

        assert screen.active_tab == HelpScreen.TAB_SHORTCUTS

        rendered = _render_to_string(screen)
        assert "Help & Reference" in rendered
        assert "Keyboard Shortcuts" in rendered
        assert "Global Navigation" in rendered

    def test_tab_switching_and_all_views(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = HelpScreen(state=state, event_queue=events)

        # Tab 1: Shortcuts
        assert screen.active_tab == HelpScreen.TAB_SHORTCUTS
        r1 = _render_to_string(screen)
        assert "Keyboard Shortcuts" in r1

        # Tab 2: Workflow
        screen.switch_tab(HelpScreen.TAB_WORKFLOW)
        assert screen.active_tab == HelpScreen.TAB_WORKFLOW
        r2 = _render_to_string(screen)
        assert "Workflow" in r2
        assert "Source Ingestion" in r2

        # Tab 3: Tech Stack
        screen.switch_tab(HelpScreen.TAB_TECH_STACK)
        assert screen.active_tab == HelpScreen.TAB_TECH_STACK
        r3 = _render_to_string(screen)
        assert "Technical Architecture" in r3
        assert "Piper ONNX" in r3

    def test_key_handling_navigation(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = HelpScreen(state=state, event_queue=events)

        assert screen.handle_key("tab") is True
        assert screen.active_tab == HelpScreen.TAB_WORKFLOW

        assert screen.handle_key("3") is True
        assert screen.active_tab == HelpScreen.TAB_TECH_STACK

        assert screen.handle_key("1") is True
        assert screen.active_tab == HelpScreen.TAB_SHORTCUTS

        # Exit to dashboard
        assert screen.handle_key("escape") is True
        queued = events.drain(10)
        assert len(queued) == 1
        assert queued[0].payload["screen"] == ScreenMode.DASHBOARD.value


# ==============================================================================
# DashboardScreen Tests
# ==============================================================================


class TestDashboardScreen:
    """Comprehensive test battery for DashboardScreen."""

    def test_dashboard_rendering_and_cards(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        state.ingestion.update_extracted("Dette er en kildetekst for podcasten.")
        state.ollama.is_online = True
        state.ollama.selected_model = "llama3.1:8b"
        state.generation.turns = [
            DialogueTurn(speaker="Host 1", text="Hei og velkommen!"),
            DialogueTurn(speaker="Host 2", text="Takk for det!"),
        ]

        screen = DashboardScreen(state=state, event_queue=events)
        rendered = _render_to_string(screen)

        assert "Autonomous AI Podcast Station" in rendered
        assert "[1] Source Content Ingestion" in rendered
        assert "[2] Ollama Local LLM Engine" in rendered
        assert "[3] Podcast Settings & Personas" in rendered
        assert "[4] Generation Pipeline & Studio" in rendered
        assert "[5] Script Studio & Dialogue Turns" in rendered
        assert "[6] Master Audio & MCI Player" in rendered

    def test_dashboard_key_handlers(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        screen = DashboardScreen(state=state, event_queue=events)

        assert screen.handle_key("1") is True
        assert screen.handle_key("i") is True
        assert screen.handle_key("2") is True
        assert screen.handle_key("o") is True
        assert screen.handle_key("3") is True
        assert screen.handle_key("c") is True
        assert screen.handle_key("4") is True
        assert screen.handle_key("5") is True
        assert screen.handle_key("s") is True
        assert screen.handle_key("6") is True
        assert screen.handle_key("p") is True
        assert screen.handle_key("?") is True
        assert screen.handle_key("f1") is True
        assert screen.handle_key("g") is True
        assert screen.handle_key("r") is True

        queued = events.drain(30)
        destinations = [
            e.payload.get("screen") for e in queued if e.event_type == TUIEventType.NAVIGATE_SCREEN
        ]
        assert ScreenMode.INGESTION.value in destinations
        assert ScreenMode.OLLAMA.value in destinations
        assert ScreenMode.CONFIG.value in destinations
        assert ScreenMode.GENERATION.value in destinations
        assert ScreenMode.SCRIPT_STUDIO.value in destinations
        assert ScreenMode.PLAYER.value in destinations
        assert ScreenMode.HELP.value in destinations
        assert any(e.event_type == TUIEventType.OLLAMA_PROBE_REQUESTED for e in queued)


# ==============================================================================
# TUIApplication Integration Tests
# ==============================================================================


class TestTUIApplication:
    """Integration test battery for TUIApplication lifecycle, event routing, and screens."""

    def test_app_initialization_and_registry(self) -> None:
        state = TUIState()
        input_reader = MockInputReader([])
        app = TUIApplication(state=state, input_reader=input_reader, auto_probe_ollama=False)

        assert len(app.screens) == 8
        assert app.state.ui.active_screen == ScreenMode.DASHBOARD
        assert app.get_active_screen_instance() == app.dashboard_screen

    def test_navigation_and_modal_push(self) -> None:
        state = TUIState()
        app = TUIApplication(state=state, auto_probe_ollama=False)

        app.navigate_to(ScreenMode.INGESTION)
        assert app.state.ui.active_screen == ScreenMode.INGESTION
        assert app.get_active_screen_instance() == app.ingestion_screen

        app.navigate_to(ScreenMode.PLAYER)
        assert app.state.ui.active_screen == ScreenMode.PLAYER
        assert app.get_active_screen_instance() == app.player_screen

        # Modal open & close
        app.open_modal(ModalType.ERROR, {"title": "Test Error", "message": "Something went wrong"})
        assert app.state.ui.active_modal == ModalType.ERROR

        rendered_modal = _render_to_string(app.render())
        assert "Test Error" in rendered_modal

        app.close_modal()
        assert app.state.ui.active_modal == ModalType.NONE

    def test_step_execution_with_mock_inputs(self) -> None:
        state = TUIState()
        input_reader = QueueInputReader()
        app = TUIApplication(state=state, input_reader=input_reader, auto_probe_ollama=False)

        # Step without input
        app.step()
        assert app.state.ui.terminal_width >= 20

        # Step with function keys navigation
        app.step(key="f2")
        assert app.state.ui.active_screen == ScreenMode.INGESTION

        app.step(key="f4")
        assert app.state.ui.active_screen == ScreenMode.CONFIG

        app.step(key="f5")
        assert app.state.ui.active_screen == ScreenMode.GENERATION

        app.step(key="f6")
        assert app.state.ui.active_screen == ScreenMode.SCRIPT_STUDIO

        app.step(key="f7")
        assert app.state.ui.active_screen == ScreenMode.PLAYER

        app.step(key="f8")
        assert app.state.ui.active_screen == ScreenMode.HELP

        app.step(key="f1")
        assert app.state.ui.active_screen == ScreenMode.DASHBOARD

    def test_event_queue_processing(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        app = TUIApplication(state=state, event_queue=events, auto_probe_ollama=False)

        events.post_event(
            TUIEventType.NAVIGATE_SCREEN,
            payload={"screen": ScreenMode.OLLAMA.value},
        )

        app.step()
        assert app.state.ui.active_screen == ScreenMode.OLLAMA

    def test_quit_lifecycle(self) -> None:
        state = TUIState()
        app = TUIApplication(state=state, auto_probe_ollama=False)
        app._is_running = True

        app.step(key="q")
        assert app._is_running is False

        app.shutdown()


# ==============================================================================
# TUI Launcher (tui.py) CLI Tests
# ==============================================================================


class TestTUILauncher:
    """Test suite for tui.py command line bootstrapping."""

    def test_arg_parser_defaults(self) -> None:
        parser = tui_launcher.build_arg_parser()
        args = parser.parse_args([])
        assert args.file == ""
        assert args.topic == ""
        assert args.url == "http://localhost:11434"
        assert args.screen == "dashboard"

    def test_bootstrap_state_topic_only(self) -> None:
        parser = tui_launcher.build_arg_parser()
        args = parser.parse_args(
            [
                "--topic",
                "Quantum Computing in 2026",
                "--model",
                "qwen2.5:7b",
                "--lang",
                "en-US",
                "--length",
                "deep_dive",
                "--tone",
                "analytical",
                "--speed",
                "+5.0",
                "--outdir",
                "./custom_out",
            ]
        )

        state = tui_launcher.bootstrap_state(args)

        assert state.ingestion.source_mode == SourceMode.TOPIC_PROMPT
        assert state.ingestion.topic_prompt == "Quantum Computing in 2026"
        assert state.ollama.selected_model == "qwen2.5:7b"
        assert state.config.language == "en-US"
        assert state.config.length_preset == "deep_dive"
        assert state.config.tone_preset == "analytical"
        assert state.config.grounding_mode == "open_topic"
        assert state.config.output_dir == "./custom_out"
        assert state.audio.speaking_speed == 5.0

    def test_bootstrap_state_document_file(self, tmp_path: Any) -> None:
        doc = tmp_path / "doc.txt"
        doc.write_text("Dette er en tekstfil for testing av dokumentlasting.", encoding="utf-8")

        parser = tui_launcher.build_arg_parser()
        args = parser.parse_args(["--file", str(doc)])

        state = tui_launcher.bootstrap_state(args)
        assert state.ingestion.source_mode == SourceMode.DOCUMENT
        assert state.ingestion.file_path == str(doc)
        assert state.ingestion.char_count > 10
        assert state.ingestion.is_valid is True
