"""
Comprehensive Unit & Integration Test Suite for TUI Asynchronous Workers:
- BaseWorker (tui/workers.py)
- ExtractionWorker (tui/workers.py)
- OllamaProbeWorker (tui/workers.py)
- OllamaLaunchWorker (tui/workers.py)
- ModelPullWorker (tui/workers.py)
- GenerationWorker (tui/workers.py)
- TTSSynthesisWorker (tui/workers.py)
"""

from __future__ import annotations

import os
import tempfile
import threading
from typing import Any
from unittest.mock import MagicMock, patch

from core.ollama import ModelPullProgress
from core.parser import DialogueTurn
from tui.state import (
    GenerationStatus,
    OllamaStatus,
    SynthesisStatus,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.workers import (
    BaseWorker,
    ExtractionWorker,
    GenerationWorker,
    ModelPullWorker,
    OllamaLaunchWorker,
    OllamaProbeWorker,
    TTSSynthesisWorker,
)

# ==============================================================================
# BaseWorker Tests
# ==============================================================================


class TestBaseWorker:
    """Verifies BaseWorker lifecycle, event queuing, and cancellation mechanics."""

    def test_base_worker_initialization_and_cancellation(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        cancel_evt = threading.Event()

        worker = BaseWorker(state=state, event_queue=events, cancel_event=cancel_evt)
        assert worker.daemon is True
        assert worker.is_cancelled() is False

        worker.cancel()
        assert worker.is_cancelled() is True
        assert cancel_evt.is_set() is True

    def test_base_worker_event_posting_and_busy_state(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        worker = BaseWorker(state=state, event_queue=events)

        worker.post_event(TUIEventType.SET_STATUS_MESSAGE, payload="Test Message")
        queued = events.drain(10)
        assert len(queued) == 1
        assert queued[0].event_type == TUIEventType.SET_STATUS_MESSAGE
        assert queued[0].payload == "Test Message"

        worker._set_busy(True, "Working on task")
        assert state.ui.is_busy is True
        assert state.ui.busy_task == "Working on task"

        busy_events = events.drain(10)
        assert len(busy_events) == 1
        assert busy_events[0].event_type == TUIEventType.SET_BUSY
        assert busy_events[0].payload["is_busy"] is True


# ==============================================================================
# ExtractionWorker Tests
# ==============================================================================


class TestExtractionWorker:
    """Verifies document, raw text, and topic prompt extraction workflows."""

    def test_extraction_worker_file_success(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        sample_text = "Dette er en omfattende testfil for podcast-generering på norsk med lokale språkmodeller."

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(sample_text)
            temp_path = f.name

        try:
            worker = ExtractionWorker(
                source=temp_path,
                is_raw_text=False,
                is_topic=False,
                state=state,
                event_queue=events,
            )
            worker.start()
            worker.join(timeout=3.0)

            assert state.ingestion.is_valid is True
            assert state.ingestion.extracted_text == sample_text
            assert state.ingestion.char_count == len(sample_text)
            assert state.ingestion.word_count == len(sample_text.split())

            queued = events.drain(10)
            types = [e.event_type for e in queued]
            assert TUIEventType.INGESTION_EXTRACTED in types
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_extraction_worker_raw_text_and_topic(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        raw_text = "Dette er råtekst som limes direkte inn i grensesnittet for podcast-generering."

        worker = ExtractionWorker(
            source=raw_text,
            is_raw_text=True,
            is_topic=False,
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.ingestion.is_valid is True
        assert state.ingestion.extracted_text == raw_text

        # Topic mode
        state2 = TUIState()
        events2 = TUIEventQueue()
        topic_text = "Fremtidens kunstige intelligens i helsesektoren og etiske utfordringer."

        worker2 = ExtractionWorker(
            source=topic_text,
            is_raw_text=False,
            is_topic=True,
            state=state2,
            event_queue=events2,
        )
        worker2.start()
        worker2.join(timeout=3.0)

        assert state2.ingestion.is_valid is True
        assert state2.ingestion.extracted_text == topic_text

    def test_extraction_worker_error_handling(self) -> None:
        state = TUIState()
        events = TUIEventQueue()

        worker = ExtractionWorker(
            source="C:/non_existent_folder_xyz/missing_file.pdf",
            is_raw_text=False,
            is_topic=False,
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.ingestion.is_valid is False
        assert state.ingestion.validation_error is not None

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.INGESTION_ERROR in types

    def test_extraction_worker_cancellation(self) -> None:
        state = TUIState()
        events = TUIEventQueue()
        cancel_evt = threading.Event()
        cancel_evt.set()  # Pre-cancelled

        worker = ExtractionWorker(
            source="Some text",
            is_raw_text=True,
            state=state,
            event_queue=events,
            cancel_event=cancel_evt,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.ingestion.is_valid is False
        assert len(events.drain(10)) == 0


# ==============================================================================
# OllamaProbeWorker Tests
# ==============================================================================


class TestOllamaProbeWorker:
    """Verifies Ollama server connectivity probe and model catalog detection."""

    @patch("tui.workers.OllamaClient")
    def test_probe_worker_online_with_models(self, mock_client_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.check_connection.return_value = True
        mock_instance.list_models.return_value = ["llama3.1:8b", "mistral-nemo", "qwen2.5:7b"]
        mock_client_cls.return_value = mock_instance

        state = TUIState()
        events = TUIEventQueue()

        worker = OllamaProbeWorker(
            server_url="http://localhost:11434",
            timeout=2.0,
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.ollama.status == OllamaStatus.ONLINE
        assert state.ollama.is_online is True
        assert state.ollama.available_models == ["llama3.1:8b", "mistral-nemo", "qwen2.5:7b"]
        assert state.ollama.selected_model == "llama3.1:8b"

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.OLLAMA_STATUS_UPDATE in types
        assert TUIEventType.OLLAMA_MODELS_LOADED in types

    @patch("tui.workers.OllamaClient")
    def test_probe_worker_offline(self, mock_client_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.check_connection.return_value = False
        mock_client_cls.return_value = mock_instance

        state = TUIState()
        events = TUIEventQueue()

        worker = OllamaProbeWorker(
            server_url="http://localhost:11434",
            timeout=2.0,
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.ollama.status == OllamaStatus.OFFLINE
        assert state.ollama.is_online is False
        assert len(state.ollama.available_models) == 0

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.OLLAMA_STATUS_UPDATE in types


# ==============================================================================
# OllamaLaunchWorker Tests
# ==============================================================================


class TestOllamaLaunchWorker:
    """Verifies detached Ollama background service launch worker."""

    @patch("tui.workers.start_ollama_service")
    @patch("tui.workers.OllamaClient")
    def test_launch_worker_success(self, mock_client_cls: MagicMock, mock_start: MagicMock) -> None:
        mock_start.return_value = (True, "Ollama service started successfully.")
        mock_instance = MagicMock()
        mock_instance.list_models.return_value = ["llama3.1:8b"]
        mock_client_cls.return_value = mock_instance

        state = TUIState()
        events = TUIEventQueue()

        worker = OllamaLaunchWorker(
            server_url="http://localhost:11434",
            timeout=5.0,
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.ollama.status == OllamaStatus.ONLINE
        assert state.ollama.is_online is True
        assert state.ollama.daemon_running is True
        assert state.ollama.selected_model == "llama3.1:8b"

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.OLLAMA_SERVICE_LAUNCHING in types
        assert TUIEventType.OLLAMA_SERVICE_STARTED in types
        assert TUIEventType.OLLAMA_MODELS_LOADED in types

    @patch("tui.workers.start_ollama_service")
    def test_launch_worker_failure(self, mock_start: MagicMock) -> None:
        mock_start.return_value = (False, "Ollama binary not found on system.")

        state = TUIState()
        events = TUIEventQueue()

        worker = OllamaLaunchWorker(
            server_url="http://localhost:11434",
            timeout=5.0,
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.ollama.status == OllamaStatus.ERROR
        assert state.ollama.is_online is False

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.OLLAMA_SERVICE_ERROR in types


# ==============================================================================
# ModelPullWorker Tests
# ==============================================================================


class TestModelPullWorker:
    """Verifies streaming model downloader worker and progress callbacks."""

    @patch("tui.workers.pull_model_stream")
    @patch("tui.workers.OllamaClient")
    def test_model_pull_worker_success(
        self, mock_client_cls: MagicMock, mock_pull: MagicMock
    ) -> None:
        def fake_pull(model, base_url, progress_callback, cancel_event, timeout):
            progress_callback(
                ModelPullProgress(
                    status="downloading",
                    completed=500,
                    total=1000,
                    percentage=0.5,
                    speed_bps=1024 * 1024,
                    speed_str="1.0 MB/s",
                    progress_str="500 MB / 1000 MB (50%)",
                    eta_str="00:30",
                    is_done=False,
                )
            )
            return True

        mock_pull.side_effect = fake_pull
        mock_instance = MagicMock()
        mock_instance.list_models.return_value = ["llama3.1:8b"]
        mock_client_cls.return_value = mock_instance

        state = TUIState()
        events = TUIEventQueue()

        worker = ModelPullWorker(
            model_name="llama3.1:8b",
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.ollama.status == OllamaStatus.ONLINE
        assert state.ollama.selected_model == "llama3.1:8b"
        assert state.ollama.pull_model_name == ""

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.OLLAMA_PULL_START in types
        assert TUIEventType.OLLAMA_PULL_PROGRESS in types
        assert TUIEventType.OLLAMA_PULL_DONE in types

    @patch("tui.workers.pull_model_stream")
    def test_model_pull_worker_cancellation(self, mock_pull: MagicMock) -> None:
        cancel_evt = threading.Event()

        def fake_pull(model, base_url, progress_callback, cancel_event, timeout):
            cancel_event.set()
            raise RuntimeError("Pull cancelled.")

        mock_pull.side_effect = fake_pull

        state = TUIState()
        events = TUIEventQueue()

        worker = ModelPullWorker(
            model_name="qwen2.5:7b",
            state=state,
            event_queue=events,
            cancel_event=cancel_evt,
        )
        worker.start()
        worker.join(timeout=3.0)

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.OLLAMA_PULL_CANCELLED in types


# ==============================================================================
# GenerationWorker Tests
# ==============================================================================


class TestGenerationWorker:
    """Verifies end-to-end multi-act dialogue generation, token streaming, and TTS synthesis."""

    @patch("tui.workers.stitch_mp3_files")
    @patch("tui.workers.synthesize_dialogue_audio")
    @patch("tui.workers.OllamaClient")
    def test_generation_worker_full_mode_success(
        self,
        mock_client_cls: MagicMock,
        mock_synth: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_instance = MagicMock()
        mock_dialogue_json = (
            "[\n"
            '  {"speaker": "Host 1", "text": "Hei og velkommen til podcasten!"},\n'
            '  {"speaker": "Host 2", "text": "Takk! I dag snakker vi om KI-modeller."}\n'
            "]"
        )

        def fake_generate(*args, **kwargs):
            cb = kwargs.get("callback")
            if cb:
                cb("Hei og velkommen")
                cb(" til podcasten!")
            return mock_dialogue_json

        mock_instance.generate.side_effect = fake_generate
        mock_client_cls.return_value = mock_instance

        mock_synth.return_value = ["/tmp/turn1.mp3", "/tmp/turn2.mp3"]

        state = TUIState()
        events = TUIEventQueue()
        state.ingestion.update_extracted(
            "Dette er en gyldig kildetekst med nok tegn til å generere."
        )

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Dette er en gyldig kildetekst med nok tegn til å generere.",
            language="nb-NO",
            model="llama3.1:8b",
            format_type="quick",
            output_dir=str(tmp_path),
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=5.0)

        assert state.generation.status == GenerationStatus.COMPLETED
        assert state.audio.status == SynthesisStatus.COMPLETED
        assert len(state.generation.turns) == 2
        assert state.generation.turns[0].speaker == "Host 1"
        assert state.generation.turns[1].speaker == "Host 2"
        assert state.audio.master_mp3_path is not None
        assert os.path.exists(state.generation.script_json_path or "")
        assert os.path.exists(state.generation.script_md_path or "")

        queued = events.drain(20)
        types = [e.event_type for e in queued]
        assert TUIEventType.GEN_STARTED in types
        assert TUIEventType.GEN_TOKEN_STREAM in types
        assert TUIEventType.GEN_SCRIPT_PARSED in types
        assert TUIEventType.TTS_STARTED in types
        assert TUIEventType.TTS_STITCH_STARTED in types
        assert TUIEventType.TTS_COMPLETED in types
        assert TUIEventType.GEN_COMPLETED in types

    @patch("tui.workers.OllamaClient")
    def test_generation_worker_script_only_mode(
        self,
        mock_client_cls: MagicMock,
        tmp_path: Any,
    ) -> None:
        mock_instance = MagicMock()
        mock_dialogue_json = (
            "[\n"
            '  {"speaker": "Host 1", "text": "Welcome to our quick tech summary."},\n'
            '  {"speaker": "Host 2", "text": "Glad to be here! Let us dive into the topic."}\n'
            "]"
        )
        mock_instance.generate.return_value = mock_dialogue_json
        mock_client_cls.return_value = mock_instance

        state = TUIState()
        events = TUIEventQueue()

        worker = GenerationWorker(
            mode="script_only",
            input_type="text",
            input_data="This is valid English source content for podcast generation.",
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
        assert state.audio.status == SynthesisStatus.IDLE
        assert len(state.generation.turns) == 2
        assert os.path.exists(state.generation.script_json_path or "")
        assert os.path.exists(state.generation.script_md_path or "")

        queued = events.drain(20)
        types = [e.event_type for e in queued]
        assert TUIEventType.GEN_STARTED in types
        assert TUIEventType.GEN_SCRIPT_PARSED in types
        assert TUIEventType.GEN_COMPLETED in types
        assert TUIEventType.TTS_STARTED not in types

    @patch("tui.workers.stitch_mp3_files")
    @patch("tui.workers.synthesize_dialogue_audio")
    def test_generation_worker_audio_from_script_mode(
        self,
        mock_synth: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        turns = [
            DialogueTurn(speaker="Host 1", text="Hei Kari her."),
            DialogueTurn(speaker="Host 2", text="Hei Ola her."),
        ]
        mock_synth.return_value = ["/tmp/t1.mp3", "/tmp/t2.mp3"]

        state = TUIState()
        events = TUIEventQueue()
        state.generation.turns = turns

        worker = GenerationWorker(
            mode="audio_from_script",
            input_type="dialogue",
            input_data=turns,
            language="nb-NO",
            output_dir=str(tmp_path),
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=5.0)

        assert state.audio.status == SynthesisStatus.COMPLETED
        assert state.audio.master_mp3_path is not None

        queued = events.drain(20)
        types = [e.event_type for e in queued]
        assert TUIEventType.TTS_STARTED in types
        assert TUIEventType.TTS_COMPLETED in types

    def test_generation_worker_empty_input_error(self, tmp_path: Any) -> None:
        state = TUIState()
        events = TUIEventQueue()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Short",  # < 10 characters
            output_dir=str(tmp_path),
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.generation.status == GenerationStatus.FAILED
        assert state.generation.generation_error is not None

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.GEN_FAILED in types

    @patch("tui.workers.OllamaClient")
    def test_generation_worker_cancellation(
        self,
        mock_client_cls: MagicMock,
        tmp_path: Any,
    ) -> None:
        cancel_evt = threading.Event()
        mock_instance = MagicMock()

        def fake_generate(*args, **kwargs):
            cancel_evt.set()
            raise RuntimeError("Generation cancelled by user.")

        mock_instance.generate.side_effect = fake_generate
        mock_client_cls.return_value = mock_instance

        state = TUIState()
        events = TUIEventQueue()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Valid content for podcast generation that takes a while.",
            output_dir=str(tmp_path),
            state=state,
            event_queue=events,
            cancel_event=cancel_evt,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.generation.status == GenerationStatus.CANCELLED

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.GEN_CANCELLED in types


# ==============================================================================
# TTSSynthesisWorker Tests
# ==============================================================================


class TestTTSSynthesisWorker:
    """Verifies standalone speech synthesis and MP3 assembly worker."""

    @patch("tui.workers.stitch_mp3_files")
    @patch("tui.workers.synthesize_dialogue_audio")
    def test_tts_synthesis_worker_success(
        self,
        mock_synth: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        turns = [
            DialogueTurn(speaker="Host 1", text="Første setning."),
            DialogueTurn(speaker="Host 2", text="Andre setning."),
        ]
        mock_synth.return_value = ["/tmp/t1.mp3", "/tmp/t2.mp3"]

        state = TUIState()
        events = TUIEventQueue()

        worker = TTSSynthesisWorker(
            dialogue=turns,
            language="nb-NO",
            output_dir=str(tmp_path),
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=5.0)

        assert state.audio.status == SynthesisStatus.COMPLETED
        assert state.audio.master_mp3_path is not None

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.TTS_STARTED in types
        assert TUIEventType.TTS_STITCH_STARTED in types
        assert TUIEventType.TTS_COMPLETED in types

    def test_tts_synthesis_worker_empty_dialogue(self, tmp_path: Any) -> None:
        state = TUIState()
        events = TUIEventQueue()

        worker = TTSSynthesisWorker(
            dialogue=[],
            output_dir=str(tmp_path),
            state=state,
            event_queue=events,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert state.audio.status == SynthesisStatus.FAILED
        assert state.audio.synthesis_error is not None

        queued = events.drain(10)
        types = [e.event_type for e in queued]
        assert TUIEventType.TTS_FAILED in types
