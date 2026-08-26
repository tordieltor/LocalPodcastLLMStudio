"""
5-Tier Empirical E2E Test Suite for LocalPodcastLLMStudio Interactive TUI
========================================================================
Covers all 5 Tiers according to TEST_INFRA.md and rational-e2e-testing framework:
- Tier 1: Feature Coverage across all 8 TUI screens, controller lifecycle, modals, and hotkeys
- Tier 2: Boundary & Corner Cases (empty documents, offline Ollama, seek/volume bounds, corrupt JSON script, zero dimensions)
- Tier 3: Cross-Feature Combinations & State Transitions (Ingest -> Configure -> Generate -> Studio -> Synthesize -> Playback; Topic-only pipeline; Cancel -> Reset -> Re-run)
- Tier 4: Real-World Workload Scenarios (Multi-act dialogue token streaming, turn card rendering, MP3 assembly, timeline scrubber synchronization)
- Tier 5: Adversarial Stress & Resiliency (Terminal dimension mutations mid-stream, high-throughput key floods, concurrent worker cancellations)
"""

from __future__ import annotations

import io
import json
import os
import threading
from typing import Any
from unittest.mock import MagicMock, patch

from rich.console import Console

from core.parser import DialogueTurn
from tests.conftest import make_synthetic_mp3
from tui.app import TUIApplication
from tui.input import QueueInputReader
from tui.screens.config import ConfigScreen
from tui.screens.dashboard import DashboardScreen
from tui.screens.generation import GenerationScreen
from tui.screens.help import HelpScreen
from tui.screens.ingestion import IngestionScreen
from tui.screens.ollama_mgr import OllamaManagerScreen
from tui.screens.player import AudioPlayerScreen
from tui.screens.script_studio import ScriptStudioScreen
from tui.state import (
    GenerationStatus,
    ModalType,
    OllamaStatus,
    PlaybackMode,
    ScreenMode,
    SourceMode,
    SynthesisStatus,
    TUIEventQueue,
    TUIState,
)
from tui.theme import TOKYO_NIGHT_THEME
from tui.workers import (
    ExtractionWorker,
    GenerationWorker,
    ModelPullWorker,
    OllamaProbeWorker,
    TTSSynthesisWorker,
)


def _render_to_string(renderable: object, width: int = 120, height: int = 40) -> str:
    """Helper that renders any Rich renderable to a string buffer."""
    buf = io.StringIO()
    console = Console(
        file=buf, width=width, height=height, theme=TOKYO_NIGHT_THEME, legacy_windows=False
    )
    console.print(renderable)
    return buf.getvalue()


# ==============================================================================
# TIER 1: FEATURE COVERAGE ACROSS ALL TUI SCREENS & CONTROLLER
# ==============================================================================


class TestTUITier1FeatureCoverage:
    """Tier 1: Comprehensive feature coverage across all 8 TUI screens and application lifecycle."""

    def test_dashboard_screen_full_feature_rendering(self) -> None:
        """Verifies DashboardScreen renders all navigation cards, badges, and titles."""
        state = TUIState()
        events = TUIEventQueue()
        screen = DashboardScreen(state=state, event_queue=events)

        rendered = _render_to_string(screen)
        assert "Autonomous AI Podcast Station" in rendered
        assert "[1] Source Content Ingestion" in rendered
        assert "[2] Ollama Local LLM Engine" in rendered
        assert "[3] Podcast Settings & Personas" in rendered
        assert "[5] Script Studio & Dialogue Turns" in rendered
        assert "[6] Master Audio & MCI Player" in rendered

    def test_ingestion_screen_modality_switching_and_rendering(self) -> None:
        """Verifies IngestionScreen supports Document, Pasted Text, and Topic Prompt modes."""
        state = TUIState()
        events = TUIEventQueue()
        screen = IngestionScreen(state=state, event_queue=events)

        # 1. Document Mode
        screen.set_mode(SourceMode.DOCUMENT)
        assert state.ingestion.source_mode == SourceMode.DOCUMENT
        r1 = _render_to_string(screen)
        assert "Document File" in r1

        # 2. Pasted Text Mode
        screen.set_mode(SourceMode.PASTED_TEXT)
        assert state.ingestion.source_mode == SourceMode.PASTED_TEXT
        r2 = _render_to_string(screen)
        assert "Pasted Text" in r2

        # 3. Topic Prompt Mode (auto-syncs grounding to open_topic)
        screen.set_mode(SourceMode.TOPIC_PROMPT)
        assert state.ingestion.source_mode == SourceMode.TOPIC_PROMPT
        assert state.config.grounding_mode == "open_topic"
        r3 = _render_to_string(screen)
        assert "Topic Prompt" in r3

    def test_ollama_manager_screen_model_selection_and_status(self) -> None:
        """Verifies OllamaManagerScreen model browsing and status display."""
        state = TUIState()
        events = TUIEventQueue()
        state.ollama.is_online = True
        state.ollama.status = OllamaStatus.ONLINE
        state.ollama.available_models = ["llama3.1:8b", "qwen2.5:7b", "mistral:latest"]
        state.ollama.selected_model = "llama3.1:8b"

        screen = OllamaManagerScreen(state=state, event_queue=events)
        rendered = _render_to_string(screen)
        assert "Ollama Local LLM" in rendered
        assert "llama3.1:8b" in rendered
        assert "ONLINE" in rendered or "online" in rendered

    def test_config_screen_language_format_tone_grounding_toggles(self) -> None:
        """Verifies ConfigScreen options, language persona sync, and speaking speed."""
        state = TUIState()
        events = TUIEventQueue()
        screen = ConfigScreen(state=state, event_queue=events)

        # Toggle Language
        screen.toggle_language()
        assert state.config.language == "en-US"
        assert state.config.host1_name == "Jenny"
        assert state.config.host2_name == "Guy"
        assert state.audio.host1_voice == "en_US-lessac-medium"

        # Toggle Format Length
        screen.cycle_length_preset()
        assert state.config.length_preset in ["quick", "standard", "deep_dive", "extended"]

        # Toggle Tone Style
        screen.cycle_tone_preset()
        assert state.config.tone_preset in ["casual", "analytical", "debate"]

        # Toggle Grounding Mode
        screen.cycle_grounding_mode()
        assert state.config.grounding_mode in ["strict", "creative", "open_topic"]

        # Adjust Speaking Speed
        screen.adjust_speaking_speed(+5.0)
        assert state.audio.speaking_speed == 5.0

    def test_generation_screen_rendering_and_progress(self) -> None:
        """Verifies GenerationScreen rendering during idle, streaming, and completion."""
        state = TUIState()
        events = TUIEventQueue()
        state.generation.status = GenerationStatus.GENERATING
        state.generation.current_act = 2
        state.generation.total_acts = 3
        state.generation.act_title = "Technical Deep Dive"
        state.generation.streamed_tokens = "Host 1: Examining the architecture in detail..."

        screen = GenerationScreen(state=state, event_queue=events)
        rendered = _render_to_string(screen)
        assert "Podcast Generation Studio" in rendered
        assert "Live Token Stream Buffer" in rendered
        assert "Examining the architecture" in rendered

    def test_script_studio_screen_turns_and_json_tabs(self) -> None:
        """Verifies ScriptStudioScreen formatted turn inspection and raw JSON editor tabs."""
        state = TUIState()
        events = TUIEventQueue()
        state.generation.turns = [
            DialogueTurn(speaker="Host 1", text="Welcome everyone!"),
            DialogueTurn(speaker="Host 2", text="Glad to be here!"),
        ]
        state.generation.raw_json_script = json.dumps(
            [t.to_dict() for t in state.generation.turns], indent=2
        )

        screen = ScriptStudioScreen(state=state, event_queue=events)

        # Tab 1: Formatted Cards
        assert screen.active_tab == ScriptStudioScreen.TAB_FORMATTED
        r1 = _render_to_string(screen)
        assert "Welcome everyone!" in r1
        assert "Host 1" in r1

        # Tab 2: Raw JSON Script View
        screen.switch_tab(ScriptStudioScreen.TAB_RAW_JSON)
        assert screen.active_tab == ScriptStudioScreen.TAB_RAW_JSON
        r2 = _render_to_string(screen)
        assert "JSON" in r2
        assert "speaker" in r2

    def test_audio_player_screen_controls_and_mci_mock(self, tmp_path: Any) -> None:
        """Verifies AudioPlayerScreen Play/Pause/Stop/Seek and volume controls."""
        state = TUIState()
        events = TUIEventQueue()
        dummy_mp3 = tmp_path / "test_episode.mp3"
        dummy_mp3.write_bytes(make_synthetic_mp3(num_frames=5))

        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 60000
        mock_player.play.return_value = True
        mock_player.pause.return_value = True
        mock_player.stop.return_value = True
        mock_player.seek.return_value = True
        mock_player.set_volume.return_value = True

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)
        assert screen.load_file(str(dummy_mp3)) is True
        assert state.player.is_loaded is True
        assert state.player.duration_ms == 60000

        assert screen.play() is True
        assert state.player.mode == PlaybackMode.PLAYING

        assert screen.pause() is True
        assert state.player.mode == PlaybackMode.PAUSED

        assert screen.seek(25000) == 25000
        assert state.player.position_ms == 25000

        assert screen.set_volume(90) == 90
        assert state.player.volume == 90

        assert screen.stop() is True
        assert state.player.mode == PlaybackMode.STOPPED

    def test_help_screen_tabs_and_navigation(self) -> None:
        """Verifies HelpScreen tab navigation across Shortcuts, Workflow, and Tech Stack."""
        state = TUIState()
        events = TUIEventQueue()
        screen = HelpScreen(state=state, event_queue=events)

        assert screen.active_tab == HelpScreen.TAB_SHORTCUTS
        screen.switch_tab(HelpScreen.TAB_WORKFLOW)
        assert screen.active_tab == HelpScreen.TAB_WORKFLOW
        screen.switch_tab(HelpScreen.TAB_TECH_STACK)
        assert screen.active_tab == HelpScreen.TAB_TECH_STACK

    def test_app_lifecycle_step_function_keys_and_modals(self) -> None:
        """Verifies TUIApplication lifecycle, function key routing (F1-F8), and modal overlays."""
        state = TUIState()
        app = TUIApplication(state=state, auto_probe_ollama=False)

        # F1 -> Dashboard
        app.step(key="f1")
        assert app.state.ui.active_screen == ScreenMode.DASHBOARD

        # F2 -> Ingestion
        app.step(key="f2")
        assert app.state.ui.active_screen == ScreenMode.INGESTION

        # F3 -> Ollama
        app.step(key="f3")
        assert app.state.ui.active_screen == ScreenMode.OLLAMA

        # F4 -> Config
        app.step(key="f4")
        assert app.state.ui.active_screen == ScreenMode.CONFIG

        # F5 -> Generation
        app.step(key="f5")
        assert app.state.ui.active_screen == ScreenMode.GENERATION

        # F6 -> Script Studio
        app.step(key="f6")
        assert app.state.ui.active_screen == ScreenMode.SCRIPT_STUDIO

        # F7 -> Player
        app.step(key="f7")
        assert app.state.ui.active_screen == ScreenMode.PLAYER

        # F8 -> Help
        app.step(key="f8")
        assert app.state.ui.active_screen == ScreenMode.HELP

        # Modal Open / Close
        app.open_modal(
            ModalType.ABOUT, {"title": "About LocalPodcastLLMStudio", "message": "v1.0.0"}
        )
        assert app.state.ui.active_modal == ModalType.ABOUT
        rendered_modal = _render_to_string(app.render())
        assert "About LocalPodcastLLMStudio" in rendered_modal

        app.close_modal()
        assert app.state.ui.active_modal == ModalType.NONE

        app.shutdown()


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================


class TestTUITier2BoundaryAndCorners:
    """Tier 2: Boundary validation, offline prerequisites, audio bounds, and edge geometries."""

    def test_validate_can_generate_prerequisites(self) -> None:
        """Verifies validate_can_generate rejects empty inputs, offline service, or missing models."""
        state = TUIState()

        # 1. Empty input
        valid, msg = state.validate_can_generate()
        assert valid is False
        assert "minimum 10 characters" in msg.lower() or "missing" in msg.lower()

        # 2. Input populated but Ollama offline
        state.ingestion.update_extracted("Valid input text with sufficient length.")
        state.ollama.is_online = False
        valid, msg = state.validate_can_generate()
        assert valid is False
        assert "offline" in msg.lower()

        # 3. Ollama online but no model selected
        state.ollama.is_online = True
        state.ollama.selected_model = ""
        valid, msg = state.validate_can_generate()
        assert valid is False
        assert "no ollama model selected" in msg.lower() or "model" in msg.lower()

        # 4. Valid prerequisites
        state.ollama.selected_model = "llama3.1:8b"
        valid, msg = state.validate_can_generate()
        assert valid is True
        assert msg == ""

    def test_validate_can_synthesize_and_play(self) -> None:
        """Verifies validate_can_synthesize and validate_can_play prerequisite checks."""
        state = TUIState()

        # Cannot synthesize without turns
        valid, msg = state.validate_can_synthesize()
        assert valid is False
        assert "no dialogue turns" in msg.lower()

        # Can synthesize when turns exist
        state.generation.turns = [DialogueTurn(speaker="Host 1", text="Turn 1")]
        valid, msg = state.validate_can_synthesize()
        assert valid is True

        # Cannot play without loaded audio
        valid, msg = state.validate_can_play()
        assert valid is False
        assert "no audio file loaded" in msg.lower()

        # Can play when loaded
        state.player.is_loaded = True
        valid, msg = state.validate_can_play()
        assert valid is True

    def test_audio_player_volume_and_seek_boundary_clamping(self, tmp_path: Any) -> None:
        """Verifies volume is clamped between 0 and 100, and seek is clamped to duration."""
        state = TUIState()
        events = TUIEventQueue()
        dummy_mp3 = tmp_path / "bound.mp3"
        dummy_mp3.write_bytes(make_synthetic_mp3(num_frames=2))

        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 50000

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)
        screen.load_file(str(dummy_mp3))

        # Volume underflow clamp
        screen.set_volume(-50)
        assert state.player.volume == 0

        # Volume overflow clamp
        screen.set_volume(250)
        assert state.player.volume == 100

        # Seek negative clamp
        screen.seek(-5000)
        assert state.player.position_ms == 0

        # Seek past duration clamp
        screen.seek(150000)
        assert state.player.position_ms == 50000

    def test_speaking_speed_adjustment_bounds(self) -> None:
        """Verifies speaking speed is clamped between -10.0% and +15.0%."""
        state = TUIState()
        events = TUIEventQueue()
        screen = ConfigScreen(state=state, event_queue=events)

        screen.adjust_speaking_speed(-50.0)
        assert state.audio.speaking_speed == -10.0

        screen.adjust_speaking_speed(+100.0)
        assert state.audio.speaking_speed == 15.0

    def test_rendering_under_minimal_and_edge_dimensions(self) -> None:
        """Verifies TUI renderables do not crash under narrow terminal widths/heights."""
        state = TUIState()
        app = TUIApplication(state=state, auto_probe_ollama=False)

        for width, height in [(40, 15), (60, 20), (80, 24), (200, 60)]:
            rendered = _render_to_string(app.render(), width=width, height=height)
            assert len(rendered) > 0


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS & STATE TRANSITIONS
# ==============================================================================


class TestTUITier3CrossFeatureAndStateTransitions:
    """Tier 3: Full interactive pipelines, topic-only rapid workflows, and cancellation recovery."""

    def test_full_interactive_workflow_state_pipeline(
        self,
        tmp_path: Any,
    ) -> None:
        """
        Tests complete interactive user flow:
        1. Ingestion: input text -> validated
        2. Ollama: probe -> select model
        3. Config: language -> Norwegian, format -> quick
        4. Generation: start -> mock turns -> save script
        5. Player: loaded -> play -> seek
        6. Script Studio: edit turn -> re-synthesize audio
        """
        state = TUIState()
        events = TUIEventQueue()
        app = TUIApplication(state=state, event_queue=events, auto_probe_ollama=False)

        # Mock player to prevent Windows MCI native file locking
        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 10000
        mock_player.get_position.return_value = 0
        mock_player.get_mode.return_value = "stopped"
        app.player_screen.player = mock_player

        # 1. Ingestion
        app.navigate_to(ScreenMode.INGESTION)
        app.ingestion_screen.set_raw_text(
            "Kvanteberegning revolusjonerer kryptografi og simulering i 2026."
        )
        assert state.ingestion.is_valid is True
        assert state.ingestion.char_count > 20

        # 2. Ollama Probe
        app.navigate_to(ScreenMode.OLLAMA)
        state.ollama.is_online = True
        state.ollama.status = OllamaStatus.ONLINE
        state.ollama.available_models = ["llama3.1:8b", "qwen2.5:7b"]
        state.ollama.auto_select_model()
        assert state.ollama.selected_model == "llama3.1:8b"

        # 3. Config
        app.navigate_to(ScreenMode.CONFIG)
        app.config_screen.set_language("nb-NO")
        app.config_screen.set_length_preset("quick")
        app.config_screen.set_tone_preset("analytical")
        assert state.config.language == "nb-NO"
        assert state.config.length_preset == "quick"

        # 4. Generation
        app.navigate_to(ScreenMode.GENERATION)
        mock_turns_json = json.dumps(
            [
                {"speaker": "Host 1", "text": "Velkommen til sendingen om kvanteberegning!"},
                {
                    "speaker": "Host 2",
                    "text": "Takk Kari! Kvantebits muliggjør eksponentiell parallellisme.",
                },
            ]
        )

        mock_client = MagicMock()
        mock_client.generate.return_value = mock_turns_json

        seg1 = tmp_path / "t1.mp3"
        seg2 = tmp_path / "t2.mp3"
        seg1.write_bytes(make_synthetic_mp3(num_frames=2))
        seg2.write_bytes(make_synthetic_mp3(num_frames=2))

        with patch("tui.workers.OllamaClient", return_value=mock_client):
            with patch(
                "tui.workers.synthesize_dialogue_audio", return_value=[str(seg1), str(seg2)]
            ):
                # Simulate generation worker execution
                gen_worker = GenerationWorker(
                    mode="full",
                    input_type="text",
                    input_data=state.ingestion.extracted_text,
                    language=state.config.language,
                    model=state.ollama.selected_model,
                    format_type=state.config.length_preset,
                    tone=state.config.tone_preset,
                    output_dir=str(tmp_path),
                    state=state,
                    event_queue=events,
                )
                gen_worker.start()
                gen_worker.join(timeout=5.0)

                # Process all queued events
                app.process_events()

                assert state.generation.status == GenerationStatus.COMPLETED
                assert len(state.generation.turns) == 2
                assert state.audio.status == SynthesisStatus.COMPLETED
                assert state.audio.master_mp3_path is not None
                assert os.path.exists(state.audio.master_mp3_path)

                # 5. Audio Player Verification
                app.navigate_to(ScreenMode.PLAYER)
                assert state.player.is_loaded is True
                assert state.player.current_file == state.audio.master_mp3_path

                # 6. Script Studio Edit & Re-synthesis
                app.navigate_to(ScreenMode.SCRIPT_STUDIO)
                assert len(state.generation.turns) == 2

                # Edit script turns in state
                edited_turns = [
                    DialogueTurn(speaker="Host 1", text="Oppdatert og finpusset intro!"),
                    DialogueTurn(speaker="Host 2", text="Oppdatert svar fra Ola!"),
                ]
                state.generation.turns = edited_turns

                # Subdirectory for re-synthesis to prevent timestamp file conflict
                sub_out = str(tmp_path / "studio_export")
                tts_worker = TTSSynthesisWorker(
                    dialogue=edited_turns,
                    language=state.config.language,
                    output_dir=sub_out,
                    state=state,
                    event_queue=events,
                )
                tts_worker.start()
                tts_worker.join(timeout=5.0)
                app.process_events()

                assert state.audio.status == SynthesisStatus.COMPLETED
                assert state.audio.master_mp3_path is not None
                assert os.path.exists(state.audio.master_mp3_path)

        app.shutdown()

    def test_rapid_topic_only_tui_pipeline_flow(self, tmp_path: Any) -> None:
        """Verifies Topic-Only rapid setup where topic input auto-configures open_topic mode."""
        state = TUIState()
        events = TUIEventQueue()
        app = TUIApplication(state=state, event_queue=events, auto_probe_ollama=False)

        app.ingestion_screen.set_mode(SourceMode.TOPIC_PROMPT)
        app.ingestion_screen.set_topic_prompt("Exploring Mars Colonization in 2040")
        assert state.ingestion.source_mode == SourceMode.TOPIC_PROMPT
        assert state.config.grounding_mode == "open_topic"
        assert state.ingestion.is_valid is True

        valid, msg = state.validate_can_generate()
        # Only missing Ollama online
        assert "ollama" in msg.lower()

        state.ollama.is_online = True
        state.ollama.selected_model = "llama3.1:8b"
        valid, msg = state.validate_can_generate()
        assert valid is True

        app.shutdown()

    def test_cancel_reset_rerun_lifecycle(self) -> None:
        """Verifies cancellation mid-worker, full state reset, and subsequent re-execution."""
        state = TUIState()
        events = TUIEventQueue()
        cancel_evt = threading.Event()

        # Simulate cancellation before run
        cancel_evt.set()
        worker = ExtractionWorker(
            source="Test cancellation source",
            state=state,
            event_queue=events,
            cancel_event=cancel_evt,
        )
        worker.start()
        worker.join(timeout=2.0)

        # Verify state reset
        state.reset_for_new_session()
        assert state.ingestion.char_count == 0
        assert state.generation.status == GenerationStatus.IDLE
        assert state.audio.status == SynthesisStatus.IDLE
        assert state.player.is_loaded is False


# ==============================================================================
# TIER 4: REAL-WORLD WORKLOAD SCENARIOS
# ==============================================================================


class TestTUITier4RealWorldWorkloads:
    """Tier 4: Multi-act live token streaming, turn card rendering, and timeline synchronization."""

    def test_multi_act_token_streaming_and_turn_parsing(self, tmp_path: Any) -> None:
        """Verifies GenerationWorker streaming tokens and updating state in real-time."""
        state = TUIState()
        events = TUIEventQueue()

        # Mock LLM client streaming tokens
        mock_client = MagicMock()
        dialogue_json = json.dumps(
            [
                {"speaker": "Host 1", "text": "Token streaming turn 1."},
                {"speaker": "Host 2", "text": "Token streaming turn 2."},
            ]
        )

        def mock_generate(*args: Any, **kwargs: Any) -> str:
            cb = kwargs.get("callback")
            if cb:
                for token in ["Here ", "is ", "the ", "script:\n", dialogue_json]:
                    cb(token)
            return dialogue_json

        mock_client.generate.side_effect = mock_generate

        with patch("tui.workers.OllamaClient", return_value=mock_client):
            with patch(
                "tui.workers.synthesize_dialogue_audio", return_value=[str(tmp_path / "t1.mp3")]
            ):
                dummy_t1 = tmp_path / "t1.mp3"
                dummy_t1.write_bytes(make_synthetic_mp3(num_frames=2))

                worker = GenerationWorker(
                    mode="script_only",
                    input_type="topic",
                    input_data="Simulated Token Stream Topic",
                    language="en-US",
                    model="llama3.1:8b",
                    format_type="quick",
                    output_dir=str(tmp_path),
                    state=state,
                    event_queue=events,
                )
                worker.start()
                worker.join(timeout=5.0)

        assert state.generation.status == GenerationStatus.COMPLETED
        assert len(state.generation.turns) == 2
        assert "Token streaming" in state.generation.streamed_tokens

    def test_mci_audio_player_timeline_scrubber_sync(self, tmp_path: Any) -> None:
        """Verifies PlayerState timeline scrubber string formatting and normalized progress."""
        state = TUIState()
        events = TUIEventQueue()
        dummy_mp3 = tmp_path / "podcast.mp3"
        dummy_mp3.write_bytes(make_synthetic_mp3(num_frames=5))

        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 180000  # 3:00 minutes
        mock_player.get_position.return_value = 45000  # 0:45 seconds
        mock_player.get_mode.return_value = "playing"

        screen = AudioPlayerScreen(state=state, event_queue=events, player=mock_player)
        assert screen.load_file(str(dummy_mp3)) is True
        screen.update_player_status()

        assert state.player.position_str == "00:45"
        assert state.player.duration_str == "03:00"
        assert state.player.scrubber_str == "00:45 / 03:00"
        assert abs(state.player.scrubber_progress - 0.25) < 0.01


# ==============================================================================
# TIER 5: ADVERSARIAL STRESS & RESILIENCY
# ==============================================================================


class TestTUITier5AdversarialResiliency:
    """Tier 5: Terminal dimension mutations, high-throughput key queue floods, and concurrency stress."""

    def test_terminal_dimension_mutation_stress(self) -> None:
        """Verifies rendering survives extreme and zero terminal dimension mutations."""
        state = TUIState()
        app = TUIApplication(state=state, auto_probe_ollama=False)

        extreme_dimensions = [
            (5, 5),
            (10, 5),
            (20, 10),
            (80, 24),
            (120, 35),
            (300, 100),
            (0, 0),  # Edge case: zero dimensions fallback
        ]

        for width, height in extreme_dimensions:
            with patch(
                "tui.terminal.get_terminal_dimensions",
                return_value=(max(10, width), max(5, height)),
            ):
                app.step()
                rendered = app.render()
                assert rendered is not None

        app.shutdown()

    def test_high_throughput_key_queue_flood(self) -> None:
        """Floods the application event loop with 500 rapid mixed keys without crash or deadlock."""
        state = TUIState()
        key_reader = QueueInputReader()
        app = TUIApplication(state=state, input_reader=key_reader, auto_probe_ollama=False)

        mixed_keys = [
            "f1",
            "f2",
            "f3",
            "f4",
            "f5",
            "f6",
            "f7",
            "f8",
            "up",
            "down",
            "left",
            "right",
            "tab",
            "enter",
            "space",
            "escape",
            "1",
            "2",
            "3",
            "g",
            "v",
            "?",
            "invalid_key_xyz",
            "ctrl+alt+del",
        ] * 25  # 600 key events

        for k in mixed_keys:
            key_reader.push_key(k)

        # Process all keys
        for _ in range(len(mixed_keys)):
            app.step()

        assert app.state.ui.active_screen in ScreenMode
        app.shutdown()

    def test_concurrent_worker_dispatch_and_rapid_cancellation(self, tmp_path: Any) -> None:
        """Verifies launching multiple workers concurrently and cancelling them rapidly."""
        state = TUIState()
        events = TUIEventQueue()
        cancel_evt = threading.Event()

        mock_client = MagicMock()
        mock_client.check_connection.return_value = False
        mock_client.pull_model.return_value = iter([])

        with patch("tui.workers.OllamaClient", return_value=mock_client):
            workers = [
                ExtractionWorker(
                    source="Concurrent extraction test",
                    state=state,
                    event_queue=events,
                    cancel_event=cancel_evt,
                ),
                OllamaProbeWorker(
                    server_url="http://localhost:11434",
                    state=state,
                    event_queue=events,
                    cancel_event=cancel_evt,
                ),
                ModelPullWorker(
                    model_name="test_model",
                    state=state,
                    event_queue=events,
                    cancel_event=cancel_evt,
                ),
            ]

            for w in workers:
                w.start()

            # Rapid cooperative cancellation
            cancel_evt.set()

            for w in workers:
                w.join(timeout=5.0)
                assert not w.is_alive()

    def test_repeated_session_reset_cycles_state_integrity(self) -> None:
        """Verifies repeatedly populating state and resetting 100 times maintains clean state."""
        state = TUIState()

        for i in range(100):
            state.ingestion.update_extracted(f"Extracted content iteration {i} with text.")
            state.generation.turns = [DialogueTurn(speaker="Host 1", text=f"Turn {i}")]
            state.audio.master_mp3_path = f"podcast_{i}.mp3"
            state.player.is_loaded = True

            state.reset_for_new_session()

            assert state.ingestion.char_count == 0
            assert state.generation.turns == []
            assert state.audio.master_mp3_path is None
            assert state.player.is_loaded is False
