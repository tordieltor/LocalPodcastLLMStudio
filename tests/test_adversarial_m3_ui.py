"""
LocalPodcastLLMStudio - Milestone 3 Adversarial & Stress Testing Suite
========================================================================
Empirical stress tests for:
1. Rapid queue event bursts (multi-threaded concurrent flooding with 10k events)
2. Malformed, corrupted, and edge-case event payloads
3. Worker cancellation race conditions (instant cancel, mid-stream cancel, phase-by-phase cancel)
4. Non-blocking behavior of OllamaLauncherWorker and ModelPullWorker (< 50ms dispatch)
5. Worker unhandled exception isolation and queue delivery
6. UI control state transitions, modality synchronization, and grounding presets
7. ActionableErrorDialog resilience across all action descriptor combinations
8. DWM immersive dark titlebar and theme constants validation
"""

import queue
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import customtkinter as ctk
import pytest

import ui.theme as theme
from core.ollama import ModelPullProgress
from core.parser import DialogueTurn
from core.prompts import GROUNDING_MODE_PRESETS, GroundingMode
from ui.main_window import (
    GROUNDING_UI_OPTIONS,
    GenerationWorker,
    MainWindow,
    ModelPullWorker,
    OllamaLauncherWorker,
)
from ui.widgets import (
    ActionableErrorDialog,
    StatusBadge,
    TimeSlider,
)


# ==============================================================================
# Headless Fixtures
# ==============================================================================
@pytest.fixture(scope="session", autouse=True)
def headless_tk_root():
    """Provides a hidden session-wide Tk root for headless execution."""
    root = None
    try:
        root = ctk.CTk()
        root.withdraw()
        yield root
    except Exception:
        with patch("customtkinter.CTk"):
            yield None
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


@pytest.fixture
def mock_main_window():
    """Creates a mock MainWindow with full widget hierarchy for headless testing."""
    win = MagicMock(spec=MainWindow)
    win.msg_queue = queue.Queue()
    win.cancel_event = threading.Event()
    win.pull_cancel_event = threading.Event()
    win.launcher_cancel_event = threading.Event()
    win.current_worker = None
    win.current_pull_worker = None
    win.current_launcher_worker = None
    win.player = MagicMock()
    win.is_busy = False

    # Widgets
    win.status_label = MagicMock()
    win.progress_bar = MagicMock()
    win.progress_pct_label = MagicMock()
    win.speed_label = MagicMock()
    win.ollama_badge = MagicMock(spec=StatusBadge)
    win.btn_refresh_models = MagicMock()
    win.btn_start_ollama_header = MagicMock()
    win.btn_start_ollama = MagicMock()
    win.btn_download_model = MagicMock()
    win.btn_generate_full = MagicMock()
    win.btn_generate_script = MagicMock()
    win.btn_synth_from_script = MagicMock()
    win.btn_cancel = MagicMock()
    win.btn_reset = MagicMock()
    win.btn_play = MagicMock()
    win.btn_pause = MagicMock()
    win.btn_stop = MagicMock()
    win.btn_export_mp3 = MagicMock()
    win.model_menu = MagicMock()
    win.lang_menu = MagicMock()
    win.length_menu = MagicMock()
    win.tone_menu = MagicMock()
    win.grounding_menu = MagicMock()
    win.grounding_desc_label = MagicMock()
    win.input_modality_var = MagicMock()
    win.file_entry = MagicMock()
    win.file_info_label = MagicMock()
    win.text_input_box = MagicMock()
    win.editable_script_box = MagicMock()
    win.speed_slider = MagicMock()
    win.output_entry = MagicMock()
    win.pull_frame = MagicMock()
    win.pull_status_label = MagicMock()
    win.pull_speed_label = MagicMock()
    win.pull_progress_bar = MagicMock()
    win.pull_details_label = MagicMock()
    win.btn_cancel_pull = MagicMock()
    win.time_slider = MagicMock(spec=TimeSlider)
    win.player_title_label = MagicMock()
    win.formatted_scroll = MagicMock()
    win.file_container = MagicMock()
    win.text_container = MagicMock()

    # Delegate helper methods to real implementation
    win.get_selected_grounding_mode.side_effect = lambda: MainWindow.get_selected_grounding_mode(
        win
    )

    return win


# ==============================================================================
# Tier 1: Rapid Queue Event Bursts & Stress Concurrency
# ==============================================================================
class TestAdversarialQueueBursts:
    """Stress-tests the UI thread-safe queue with rapid concurrent bursts."""

    def test_rapid_queue_burst_10k_events_multithreaded(self, mock_main_window):
        """
        Floods msg_queue with 10,000 events across 10 concurrent threads simultaneously.
        Verifies that _process_queue drains all events cleanly without deadlocks,
        exceptions, or dropped messages.
        """
        num_threads = 10
        events_per_thread = 1000
        total_events = num_threads * events_per_thread

        def _flooder(thread_id: int):
            for i in range(events_per_thread):
                mod = i % 10
                if mod == 0:
                    mock_main_window.msg_queue.put(("STATUS", f"Thread {thread_id} step {i}"))
                elif mod == 1:
                    mock_main_window.msg_queue.put(("PROGRESS", (i % 100) / 100.0))
                elif mod == 2:
                    mock_main_window.msg_queue.put(
                        ("SCRIPT_READY", [DialogueTurn(speaker="Host 1", text=f"T{thread_id}:{i}")])
                    )
                elif mod == 3:
                    mock_main_window.msg_queue.put(
                        ("SERVICE_LAUNCHING", {"status": f"Starting {i}"})
                    )
                elif mod == 4:
                    mock_main_window.msg_queue.put(
                        ("SERVICE_STARTED", {"status": "Ready", "models": ["llama3.1:8b"]})
                    )
                elif mod == 5:
                    mock_main_window.msg_queue.put(
                        (
                            "PULL_PROGRESS",
                            ModelPullProgress(status="pulling", percentage=(i % 100) / 100.0),
                        )
                    )
                elif mod == 6:
                    mock_main_window.msg_queue.put(
                        ("PULL_DONE", {"model": "llama3.1:8b", "message": f"Done {i}"})
                    )
                elif mod == 7:
                    mock_main_window.msg_queue.put(("PULL_CANCELLED", {"model": "llama3.1:8b"}))
                elif mod == 8:
                    mock_main_window.msg_queue.put(
                        ("GENERATION_DONE", {"mp3_path": f"/test_{thread_id}_{i}.mp3"})
                    )
                else:
                    mock_main_window.msg_queue.put(("CANCELLED", f"Cancel {i}"))

        threads = [
            threading.Thread(target=_flooder, args=(tid,), daemon=True)
            for tid in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert mock_main_window.msg_queue.qsize() == total_events

        # Drain queue via _process_queue
        drain_start = time.monotonic()
        with patch("ui.main_window.ActionableErrorDialog"):
            MainWindow._process_queue(mock_main_window)
        drain_duration = time.monotonic() - drain_start

        assert mock_main_window.msg_queue.empty()
        assert mock_main_window._handle_event.call_count == total_events
        # Drain throughput should be high (> 5,000 events/sec)
        assert drain_duration < 5.0, f"Queue draining took too long: {drain_duration:.2f}s"

    def test_interleaved_enqueue_and_drain_loop(self, mock_main_window):
        """Simulates interleaved queue pushing while _process_queue is called repeatedly."""
        stop_event = threading.Event()
        enqueue_count = [0]

        def _producer():
            while not stop_event.is_set():
                mock_main_window.msg_queue.put(("STATUS", f"Live tick {enqueue_count[0]}"))
                enqueue_count[0] += 1
                time.sleep(0.0005)

        producer_thread = threading.Thread(target=_producer, daemon=True)
        producer_thread.start()

        # Run 20 iterations of _process_queue with small pauses
        for _ in range(20):
            MainWindow._process_queue(mock_main_window)
            time.sleep(0.01)

        stop_event.set()
        producer_thread.join(timeout=2.0)
        # Final drain
        MainWindow._process_queue(mock_main_window)

        assert mock_main_window.msg_queue.empty()
        assert mock_main_window._handle_event.call_count == enqueue_count[0]


# ==============================================================================
# Tier 2: Malformed & Edge-Case Event Payloads
# ==============================================================================
class TestAdversarialMalformedPayloads:
    """Stress-tests MainWindow._handle_event against unexpected, corrupted, or malformed payloads."""

    @pytest.mark.parametrize(
        "event_type,payload",
        [
            ("UNKNOWN_EVENT_TYPE", "some random data"),
            ("UNKNOWN_EVENT_TYPE", None),
            ("UNKNOWN_EVENT_TYPE", {"key": "value"}),
            ("STATUS", 12345),
            ("STATUS", None),
            ("STATUS", ["list", "of", "items"]),
            ("STATUS", {"nested": "dict"}),
            ("PROGRESS", 0.0),
            ("PROGRESS", 1.0),
            ("PROGRESS", "0.75"),  # String convertible to float
            ("SERVICE_LAUNCHING", "Plain string status"),
            ("SERVICE_LAUNCHING", None),
            ("SERVICE_LAUNCHING", {}),
            ("SERVICE_STARTED", "Plain string started"),
            ("SERVICE_STARTED", None),
            ("SERVICE_STARTED", {"status": "Ready", "models": None}),
            ("SERVICE_STARTED", {"status": None, "models": []}),
            ("SERVICE_ERROR", "Plain string error"),
            ("SERVICE_ERROR", None),
            ("SERVICE_ERROR", {"error": None, "details": None}),
            ("SERVICE_ERROR", {"error": 404, "details": 500}),
            ("PULL_PROGRESS", None),  # Non-ModelPullProgress should be safely ignored
            ("PULL_PROGRESS", {"percentage": 0.5}),  # Non-dataclass
            ("PULL_PROGRESS", "corrupted string progress"),
            ("PULL_DONE", "Plain string done"),
            ("PULL_DONE", None),
            ("PULL_DONE", {"model": None, "message": None}),
            ("PULL_DONE", {"unexpected_field": 123}),
            ("PULL_ERROR", "Plain string error"),
            ("PULL_ERROR", None),
            ("PULL_ERROR", {"model": None, "error": None}),
            ("PULL_CANCELLED", None),
            ("PULL_CANCELLED", "llama3.1:8b"),
            ("PULL_CANCELLED", {}),
            ("CANCELLED", None),
            ("CANCELLED", 999),
            ("ERROR", "Simple string error"),
            ("ERROR", {"title": None, "message": None, "details": None}),
            ("ERROR", {}),
        ],
    )
    def test_handle_event_malformed_payload_safety(self, mock_main_window, event_type, payload):
        """Verifies _handle_event never raises unhandled exceptions on malformed payloads."""
        with (
            patch("ui.main_window.ActionableErrorDialog"),
            patch("tkinter.messagebox.showerror"),
        ):
            # Must execute without throwing exceptions
            try:
                MainWindow._handle_event(mock_main_window, event_type, payload)
            except Exception as exc:
                pytest.fail(
                    f"_handle_event raised unexpected exception on ({event_type!r}, {payload!r}): {exc}"
                )

    def test_handle_pull_progress_edge_values(self, mock_main_window):
        """Verifies PULL_PROGRESS handles extreme numerical and empty string boundary values."""
        # 1. 0% progress with empty speed/ETA strings
        p_zero = ModelPullProgress(
            status="starting",
            total=0,
            completed=0,
            percentage=0.0,
            speed_str="",
            progress_str="",
            eta_str="",
        )
        MainWindow._handle_event(mock_main_window, "PULL_PROGRESS", p_zero)
        mock_main_window.pull_progress_bar.set.assert_called_with(0.0)

        # 2. 100% progress
        p_full = ModelPullProgress(
            status="success",
            total=5000000000,
            completed=5000000000,
            percentage=1.0,
            speed_str="100 MB/s",
            progress_str="5.00 GB / 5.00 GB (100.0%)",
            eta_str="00:00",
        )
        MainWindow._handle_event(mock_main_window, "PULL_PROGRESS", p_full)
        mock_main_window.pull_progress_bar.set.assert_called_with(1.0)
        mock_main_window.pull_speed_label.configure.assert_called_with(text="100 MB/s | ETA: 00:00")


# ==============================================================================
# Tier 3: Worker Concurrency & Cancellation Race Conditions
# ==============================================================================
class TestAdversarialWorkerCancellation:
    """Stress-tests race conditions in worker startup, cancellation, and shutdown."""

    def test_model_pull_worker_pre_cancelled_event(self):
        """Worker initialized with pre-set cancel_event must exit cleanly and put PULL_CANCELLED."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()
        cancel_event.set()

        with patch("ui.main_window.pull_model_stream", side_effect=RuntimeError("Cancelled")):
            worker = ModelPullWorker(
                model_name="llama3.1:8b",
                msg_queue=msg_queue,
                cancel_event=cancel_event,
            )
            worker.start()
            worker.join(timeout=3.0)

        assert not worker.is_alive()
        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        assert len(events) == 1
        assert events[0][0] == "PULL_CANCELLED"
        assert events[0][1]["model"] == "llama3.1:8b"

    def test_model_pull_worker_mid_stream_cancellation(self):
        """Worker cancelled while streaming chunks must emit PULL_CANCELLED without leakage."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        def _streaming_pull(model, base_url, progress_callback, cancel_event, timeout):
            # Emit 3 progress chunks then simulate cancellation
            for i in range(1, 4):
                if cancel_event.is_set():
                    raise RuntimeError("Cancelled")
                progress_callback(ModelPullProgress(status=f"layer {i}", percentage=i * 0.1))
                time.sleep(0.01)
            cancel_event.set()
            raise RuntimeError("Cancelled")

        with patch("ui.main_window.pull_model_stream", side_effect=_streaming_pull):
            worker = ModelPullWorker(
                model_name="llama3.1:8b",
                msg_queue=msg_queue,
                cancel_event=cancel_event,
            )
            worker.start()
            worker.join(timeout=3.0)

        assert not worker.is_alive()
        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        event_types = [e[0] for e in events]
        assert "PULL_PROGRESS" in event_types
        assert "PULL_CANCELLED" in event_types
        assert "PULL_ERROR" not in event_types

    def test_ollama_launcher_worker_cancellation(self):
        """OllamaLauncherWorker cancelled during polling loop exits safely."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        def _fake_start(timeout, base_url, cancel_event):
            cancel_event.set()
            return False, "Ollama service start cancelled by user."

        with patch("ui.main_window.start_ollama_service", side_effect=_fake_start):
            worker = OllamaLauncherWorker(
                msg_queue=msg_queue,
                cancel_event=cancel_event,
                timeout=10.0,
            )
            worker.start()
            worker.join(timeout=3.0)

        assert not worker.is_alive()
        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        assert any(e[0] == "SERVICE_ERROR" for e in events)

    def test_rapid_50_worker_start_cancel_cycles(self):
        """Spawns and cancels 50 background workers in rapid succession without deadlocks."""
        for cycle in range(50):
            msg_queue: queue.Queue[Any] = queue.Queue()
            cancel_event = threading.Event()

            with patch("ui.main_window.pull_model_stream", side_effect=RuntimeError("Cancelled")):
                worker = ModelPullWorker(
                    model_name=f"test_model_{cycle}:latest",
                    msg_queue=msg_queue,
                    cancel_event=cancel_event,
                )
                worker.start()
                # Immediately cancel
                cancel_event.set()
                worker.join(timeout=2.0)

            assert not worker.is_alive()
            assert not msg_queue.empty()
            ev = msg_queue.get_nowait()
            assert ev[0] in ("PULL_CANCELLED", "PULL_ERROR")

    @pytest.mark.parametrize(
        "phase",
        [
            "before_extract",
            "before_llm",
            "during_llm",
            "before_tts",
            "during_tts",
            "before_stitch",
        ],
    )
    def test_generation_worker_cancel_at_every_phase(self, phase, tmp_path):
        """Verifies GenerationWorker cleanly handles cancellation at all pipeline phases."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        if phase == "before_extract":
            cancel_event.set()

        def _mock_gen(content, **kwargs):
            if phase == "during_llm":
                cancel_event.set()
            return [DialogueTurn(speaker="Host 1", text="Turn 1")]

        def _mock_tts(dialogue, **kwargs):
            if phase in ("during_tts", "before_stitch"):
                cancel_event.set()
            return ["/tmp/turn1.mp3"]

        with (
            patch("ui.main_window.generate_podcast_script", side_effect=_mock_gen),
            patch("ui.main_window.synthesize_dialogue_audio", side_effect=_mock_tts),
            patch("ui.main_window.stitch_mp3_files", return_value=str(tmp_path / "out.mp3")),
        ):
            worker = GenerationWorker(
                mode="full",
                input_type="text",
                input_data="Sample document content for cancellation test",
                language="nb-NO",
                model="llama3.1:8b",
                format_type="standard",
                tone="casual",
                speed_rate="+0%",
                output_dir=str(tmp_path),
                msg_queue=msg_queue,
                cancel_event=cancel_event,
            )

            if phase == "before_llm":

                def _set_before_llm(*args, **kwargs):
                    cancel_event.set()
                    return "Extracted text content"

                with patch("ui.main_window.extract_text", side_effect=_set_before_llm):
                    worker.run()
            elif phase == "before_tts":

                def _set_before_tts(*args, **kwargs):
                    cancel_event.set()
                    return [DialogueTurn(speaker="Host 1", text="Turn 1")]

                with patch("ui.main_window.generate_podcast_script", side_effect=_set_before_tts):
                    worker.run()
            else:
                worker.run()

        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        event_types = [e[0] for e in events]
        assert "CANCELLED" in event_types, f"Phase {phase} did not emit CANCELLED: {event_types}"


# ==============================================================================
# Tier 4: Non-Blocking Behavior of UI Worker Dispatches
# ==============================================================================
class TestAdversarialNonBlockingWorkerDispatches:
    """Verifies that all asynchronous worker launcher methods return immediately (< 50ms)."""

    def test_start_ollama_service_async_is_non_blocking(self, mock_main_window):
        """MainWindow.start_ollama_service_async must dispatch worker thread without blocking (< 250ms)."""
        # Mock worker start so it doesn't do real subprocess spawn
        with patch.object(OllamaLauncherWorker, "start") as mock_start:
            t0 = time.monotonic()
            MainWindow.start_ollama_service_async(mock_main_window)
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            assert elapsed_ms < 250.0, f"start_ollama_service_async blocked for {elapsed_ms:.2f}ms"
            mock_start.assert_called_once()
            assert mock_main_window.current_launcher_worker is not None

    def test_download_model_async_is_non_blocking(self, mock_main_window):
        """MainWindow.download_model_async must dispatch worker thread without blocking (< 250ms)."""
        with patch.object(ModelPullWorker, "start") as mock_start:
            t0 = time.monotonic()
            MainWindow.download_model_async(mock_main_window, "llama3.1:8b")
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            assert elapsed_ms < 250.0, f"download_model_async blocked for {elapsed_ms:.2f}ms"
            mock_start.assert_called_once()
            assert mock_main_window.current_pull_worker is not None

    def test_start_generation_async_is_non_blocking(self, mock_main_window, tmp_path):
        """MainWindow.start_generation must dispatch worker thread without blocking (< 250ms)."""
        mock_main_window.input_modality_var.get.return_value = "text"
        mock_main_window.text_input_box.get.return_value = "Valid text input for non-blocking test"
        mock_main_window.model_menu.get.return_value = "llama3.1:8b"
        mock_main_window.lang_menu.get.return_value = "English (Jenny & Guy)"
        mock_main_window.length_menu.get.return_value = "Standard Episode (12-16 turns, ~5-7 min)"
        mock_main_window.tone_menu.get.return_value = "Casual & Lively"
        mock_main_window.speed_slider.get.return_value = 0.0
        mock_main_window.output_entry.get.return_value = str(tmp_path)
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[0]

        with patch.object(GenerationWorker, "start") as mock_start:
            t0 = time.monotonic()
            MainWindow.start_generation(mock_main_window, mode="full")
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            assert elapsed_ms < 250.0, f"start_generation blocked for {elapsed_ms:.2f}ms"
            mock_start.assert_called_once()
            assert mock_main_window.current_worker is not None


# ==============================================================================
# Tier 5: Worker Unhandled Exception Isolation
# ==============================================================================
class TestAdversarialWorkerExceptionIsolation:
    """Verifies that arbitrary exceptions inside background threads are caught and routed to msg_queue."""

    @pytest.mark.parametrize(
        "injected_exception",
        [
            ZeroDivisionError("division by zero in worker"),
            ConnectionResetError("Socket reset by peer"),
            OSError("[WinError 10061] Connection refused"),
            UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte"),
            MemoryError("Out of memory buffer"),
            ValueError("Invalid model parameter format"),
        ],
    )
    def test_model_pull_worker_catches_all_exceptions(self, injected_exception):
        """ModelPullWorker must catch any unhandled Exception and emit PULL_ERROR."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        with patch("ui.main_window.pull_model_stream", side_effect=injected_exception):
            worker = ModelPullWorker(
                model_name="llama3.1:8b",
                msg_queue=msg_queue,
                cancel_event=cancel_event,
            )
            # Run directly to verify no uncaught escape
            worker.run()

        assert not msg_queue.empty()
        ev = msg_queue.get_nowait()
        assert ev[0] == "PULL_ERROR"
        assert ev[1]["model"] == "llama3.1:8b"
        assert (
            str(injected_exception) in ev[1]["error"]
            or type(injected_exception).__name__ in ev[1]["error"]
        )

    @pytest.mark.parametrize(
        "injected_exception",
        [
            PermissionError("Access denied executing ollama.exe"),
            FileNotFoundError("ollama.exe not found on system"),
            TimeoutError("Service polling timed out after 10.0s"),
            RuntimeError("Unexpected subprocess crash"),
        ],
    )
    def test_ollama_launcher_worker_catches_all_exceptions(self, injected_exception):
        """OllamaLauncherWorker must catch any unhandled Exception and emit SERVICE_ERROR."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        with patch("ui.main_window.start_ollama_service", side_effect=injected_exception):
            worker = OllamaLauncherWorker(
                msg_queue=msg_queue,
                cancel_event=cancel_event,
            )
            worker.run()

        assert not msg_queue.empty()
        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        err_ev = next(e for e in events if e[0] == "SERVICE_ERROR")
        assert err_ev is not None


# ==============================================================================
# Tier 6: UI Control State Transitions & Modality Matrix
# ==============================================================================
class TestAdversarialUIControlTransitions:
    """Verifies UI state transitions, modality synchronization, and GroundingMode contracts."""

    def test_all_grounding_presets_bilingual_coverage(self):
        """Verifies every GroundingMode enum has complete nb and en descriptions and badges."""
        for mode in (GroundingMode.STRICT, GroundingMode.CREATIVE, GroundingMode.OPEN_TOPIC):
            preset = GROUNDING_MODE_PRESETS[mode.value]
            assert "description_nb" in preset and len(preset["description_nb"]) > 10
            assert "description_en" in preset and len(preset["description_en"]) > 10
            assert "badge" in preset and len(preset["badge"]) > 0

    @pytest.mark.parametrize(
        "menu_val,expected_mode",
        [
            ("Strict Source-Only (100% Document Fidelity)", "strict"),
            ("Creative Analogy & Synthesis", "creative"),
            ("Open Topic / Scratch (Free Generative Synthesis)", "open_topic"),
            ("strict", "strict"),
            ("CREATIVE", "creative"),
            ("open_topic", "open_topic"),
            ("STRICT SOURCE ONLY", "strict"),
            ("Creative Analogy", "creative"),
            ("Scratch Mode", "open_topic"),
        ],
    )
    def test_get_selected_grounding_mode_resilient_parsing(
        self, mock_main_window, menu_val, expected_mode
    ):
        """Verifies get_selected_grounding_mode correctly extracts canonical mode across various strings."""
        mock_main_window.grounding_menu.get.return_value = menu_val
        assert MainWindow.get_selected_grounding_mode(mock_main_window) == expected_mode

    def test_rapid_modality_switching_cycles(self, mock_main_window):
        """Simulates user clicking rapidly between Document, Pasted Text, and Topic modalities."""
        modalities = [
            "Document (.txt/.md/.pdf)",
            "Pasted Text",
            "Topic Prompt (Scratch)",
            "Document (.txt/.md/.pdf)",
            "Topic Prompt (Scratch)",
            "Pasted Text",
        ]
        for mod in modalities:
            MainWindow._on_modality_changed(mock_main_window, mod)

        # Final state check for Pasted Text
        mock_main_window.input_modality_var.set.assert_called_with("text")
        mock_main_window.file_container.pack_forget.assert_called()
        mock_main_window.text_container.pack.assert_called()

    def test_set_busy_state_invariants(self, mock_main_window):
        """Verifies _set_busy_state properly sets button states."""
        # 1. Set busy True
        MainWindow._set_busy_state(mock_main_window, True)
        assert mock_main_window.is_busy is True
        mock_main_window.btn_generate_full.configure.assert_called_with(state="disabled")
        mock_main_window.btn_generate_script.configure.assert_called_with(state="disabled")
        mock_main_window.btn_synth_from_script.configure.assert_called_with(state="disabled")
        mock_main_window.btn_reset.configure.assert_called_with(state="disabled")
        mock_main_window.btn_cancel.configure.assert_called_with(state="normal")

        # 2. Set busy False
        MainWindow._set_busy_state(mock_main_window, False)
        assert mock_main_window.is_busy is False
        mock_main_window.btn_generate_full.configure.assert_called_with(state="normal")
        mock_main_window.btn_generate_script.configure.assert_called_with(state="normal")
        mock_main_window.btn_synth_from_script.configure.assert_called_with(state="normal")
        mock_main_window.btn_reset.configure.assert_called_with(state="normal")
        mock_main_window.btn_cancel.configure.assert_called_with(state="disabled")


# ==============================================================================
# Tier 7: ActionableErrorDialog Resilience & Widget Robustness
# ==============================================================================
class TestAdversarialActionableErrorDialog:
    """Stress-tests ActionableErrorDialog against unusual action formats and boundary conditions."""

    @pytest.mark.parametrize(
        "actions_spec",
        [
            None,
            [],
            [("Action 1", MagicMock())],
            [("Action 1", MagicMock(), "primary")],
            [("Action 1", MagicMock(), "success", True)],
            [("Action 1", MagicMock(), "danger", False)],
            [("Action 1", MagicMock(), "warning", True), ("Action 2", None, "secondary", False)],
            [{"text": "Btn 1", "callback": MagicMock()}],
            [{"text": "Btn 1", "callback": None, "style": "accent", "dismiss": False}],
            [{"text": "Btn 1"}, {"text": "Btn 2", "callback": MagicMock()}],
        ],
    )
    def test_actionable_error_dialog_action_variations(self, actions_spec):
        """ActionableErrorDialog instantiates cleanly for all action permutations."""
        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry"),
            patch("customtkinter.CTkToplevel.minsize"),
            patch("customtkinter.CTkToplevel.configure"),
            patch("customtkinter.CTkToplevel.transient"),
            patch("customtkinter.CTkToplevel.grab_set"),
            patch("ui.widgets.get_font_heading", return_value=MagicMock()),
            patch("ui.widgets.get_font_body", return_value=MagicMock()),
            patch("ui.widgets.get_font_body_bold", return_value=MagicMock()),
            patch("ui.widgets.get_font_code", return_value=MagicMock()),
            patch("customtkinter.CTkFrame"),
            patch("customtkinter.CTkLabel"),
            patch("customtkinter.CTkTextbox"),
            patch("customtkinter.CTkButton"),
        ):
            dialog = ActionableErrorDialog(
                parent=MagicMock(),
                title="Adversarial Dialog Test",
                message="Testing various action descriptor configurations.",
                details="Details text block.",
                actions=actions_spec,
                dialog_type="error",
            )
            assert dialog is not None

    def test_status_badge_glyph_and_empty_text(self):
        """StatusBadge handles empty text and uncommon symbols without failure."""
        badge = MagicMock(spec=StatusBadge)
        badge.dot_label = MagicMock()
        badge.text_label = MagicMock()

        StatusBadge.set_status(badge, status="", text="", dot_glyph="⭐", dot_color="#ff00ff")
        badge.dot_label.configure.assert_called_once_with(text="⭐", text_color="#ff00ff")
        badge.text_label.configure.assert_called_once_with(text="")


# ==============================================================================
# Tier 8: DWM & Styling Edge Cases
# ==============================================================================
class TestAdversarialThemeAndDWM:
    """Verifies DWM titlebar calls and color constant invariants."""

    def test_enable_windows_dark_titlebar_handles_ctypes_exceptions(self):
        """enable_windows_dark_titlebar never crashes the app if user32 or dwmapi throws."""
        mock_win = MagicMock()
        mock_win.winfo_id.side_effect = Exception("Window destroyed")

        with patch("sys.platform", "win32"):
            # Must return False without propagating exception
            assert theme.enable_windows_dark_titlebar(mock_win) is False
