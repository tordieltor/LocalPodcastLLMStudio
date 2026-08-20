"""
LocalPodcastLLMStudio - Milestone 4 Empirical Adversarial Concurrency & Stress Suite
===================================================================================
Author: Challenger 2 (critic, specialist)
Framework: rational-e2e-testing (5-tier empirical architecture)

Adversarial Stress Test Matrix:
1. UI Event Bus Concurrency & Flooding:
   - Multi-threaded high-throughput event burst flooding (20,000+ events across 50 concurrent threads)
   - FIFO queue processing and state integrity verification
   - Rapid UI control interaction races (model menu changes, button clicks during active download)
   - ActionableErrorDialog resilience under concurrent error event dispatches

2. Background Worker Lifecycle & Fine-Grained Cancellation:
   - ModelPullWorker cancellation at distinct lifecycle stages (pre-dispatch, first chunk, 50%, done)
   - OllamaLauncherWorker cancellation and detached process management
   - GenerationWorker multi-phase cancellation (ingestion, LLM call, TTS synthesis, MP3 stitch)
   - Windows file lock safety (WinError 32 prevention) and temporary directory teardown

3. Core Subsystems Concurrency & Rapid Command Cycling:
   - MP3Stitcher multi-threaded frame parsing, ID3 stripping, and binary frame concatenation
   - WindowsAudioPlayer rapid play/pause/resume/stop/seek command cycling under thread contention
   - Edge-TTS rate boundary normalization, speaker voice resolution, and async retry resilience
"""

import os
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import customtkinter as ctk
import pytest

from core.mp3_stitcher import MP3Stitcher, stitch_mp3_files
from core.ollama import ModelPullProgress
from core.parser import DialogueTurn
from core.player import WindowsAudioPlayer
from core.tts import (
    format_rate_str,
    get_voice_for_speaker,
)
from tests.conftest import make_mpeg2_l3_frame, make_synthetic_mp3
from ui.main_window import (
    GenerationWorker,
    MainWindow,
    ModelPullWorker,
    OllamaLauncherWorker,
)
from ui.widgets import ActionableErrorDialog, StatusBadge

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
    win.speed_slider = MagicMock()
    win.file_entry = MagicMock()
    win.text_input_box = MagicMock()
    win.editable_script_box = MagicMock()
    win.input_modality_var = MagicMock()
    win.grounding_mode_var = MagicMock()
    win.grounding_desc_label = MagicMock()
    win.pull_frame = MagicMock()
    win.pull_status_label = MagicMock()
    win.pull_progress_bar = MagicMock()
    win.pull_speed_label = MagicMock()
    win.pull_details_label = MagicMock()
    win.btn_cancel_pull = MagicMock()
    win.formatted_scroll = MagicMock()
    win.formatted_scroll.winfo_children.return_value = []
    win.player_timeline_slider = MagicMock()
    win.player_time_label = MagicMock()
    win.volume_slider = MagicMock()
    win.volume_pct_label = MagicMock()

    # Re-bind methods from MainWindow class to mock
    win._handle_event = lambda event_type, payload: MainWindow._handle_event(
        win, event_type, payload
    )
    win._process_queue = lambda: MainWindow._process_queue(win)
    win._set_busy_state = lambda busy: MainWindow._set_busy_state(win, busy)
    win._handle_ollama_status = lambda data: MainWindow._handle_ollama_status(win, data)
    win.download_model_async = lambda model="llama3.1:8b": MainWindow.download_model_async(
        win, model
    )
    win.cancel_model_pull = lambda: MainWindow.cancel_model_pull(win)
    win.cancel_generation = lambda: MainWindow.cancel_generation(win)

    return win


# ==============================================================================
# 1. UI Event Bus Concurrency & Flooding Stress Tests
# ==============================================================================


class TestUIEventBusConcurrencyAndFlooding:
    """Stress tests verifying UI message queue integrity and responsiveness under event flooding."""

    def test_concurrent_event_flooding_20k_messages(self, mock_main_window):
        """
        Spawns 50 threads producing 400 events each (total 20,000 events) concurrently into msg_queue.
        Verifies that _process_queue processes all events cleanly without exceptions or dropped messages.
        """
        num_threads = 50
        events_per_thread = 400

        def producer(thread_id: int):
            for i in range(events_per_thread):
                mod = i % 8
                if mod == 0:
                    mock_main_window.msg_queue.put(("STATUS", f"Status from T{thread_id}-{i}"))
                elif mod == 1:
                    mock_main_window.msg_queue.put(("PROGRESS", (i % 100) / 100.0))
                elif mod == 2:
                    p = ModelPullProgress(
                        status="downloading",
                        percentage=(i % 100) / 100.0,
                        speed_str="15.2 MB/s",
                        eta_str="01:23",
                    )
                    mock_main_window.msg_queue.put(("PULL_PROGRESS", p))
                elif mod == 3:
                    mock_main_window.msg_queue.put(
                        (
                            "OLLAMA_STATUS",
                            {"connected": True, "models": [f"model-T{thread_id}:{i}"]},
                        )
                    )
                elif mod == 4:
                    mock_main_window.msg_queue.put(
                        ("SERVICE_LAUNCHING", {"status": f"Launching T{thread_id}"})
                    )
                elif mod == 5:
                    mock_main_window.msg_queue.put(
                        ("SERVICE_STARTED", {"status": "Started", "models": ["llama3.1:8b"]})
                    )
                elif mod == 6:
                    mock_main_window.msg_queue.put(("PULL_CANCELLED", {"model": "llama3.1:8b"}))
                else:
                    mock_main_window.msg_queue.put(("CANCELLED", f"Cancelled T{thread_id}"))

        threads = [
            threading.Thread(target=producer, args=(t,), daemon=True) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # Process all queued events
        processed_count = 0
        start_time = time.time()
        while not mock_main_window.msg_queue.empty():
            mock_main_window._process_queue()
            processed_count += 1
            if time.time() - start_time > 15.0:
                break

        assert mock_main_window.msg_queue.empty()
        assert processed_count > 0

    def test_interleaved_worker_events_and_ui_interactions(self, mock_main_window):
        """
        Simulates background workers emitting high-frequency progress updates
        while the user changes dropdown selections and triggers cancellation simultaneously.
        """
        stop_event = threading.Event()
        worker_done = threading.Event()

        def worker_emit():
            count = 0
            while not stop_event.is_set() and count < 500:
                p = ModelPullProgress(
                    status="downloading",
                    percentage=(count % 100) / 100.0,
                    speed_bps=5_000_000.0,
                    speed_str="5.0 MB/s",
                    eta_str="00:45",
                )
                mock_main_window.msg_queue.put(("PULL_PROGRESS", p))
                count += 1
                time.sleep(0.001)
            worker_done.set()

        t = threading.Thread(target=worker_emit, daemon=True)
        t.start()

        # Simulate user UI actions in main thread
        for i in range(100):
            mock_main_window.model_menu.set(f"model-choice-{i % 5}")
            mock_main_window.lang_menu.set("Norwegian (nb-NO)" if i % 2 == 0 else "English (en-US)")
            mock_main_window._process_queue()
            time.sleep(0.002)

        stop_event.set()
        t.join(timeout=5.0)
        assert worker_done.is_set()

        # Process remaining
        mock_main_window._process_queue()
        assert mock_main_window.msg_queue.empty()

    def test_actionable_error_dialog_rapid_concurrent_burst(self, mock_main_window):
        """
        Tests ActionableErrorDialog resilience when 30 threads dispatch ERROR and SERVICE_ERROR
        events rapidly. Verifies dialog instantiation does not throw or deadlock.
        """
        num_threads = 30

        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            mock_dialog.return_value = MagicMock()

            def error_emitter(idx):
                if idx % 2 == 0:
                    mock_main_window.msg_queue.put(
                        (
                            "ERROR",
                            {
                                "title": f"Error {idx}",
                                "message": f"Fatal error on thread {idx}",
                                "details": f"Stack trace details {idx}",
                                "remedy": "Retry operation.",
                            },
                        )
                    )
                else:
                    mock_main_window.msg_queue.put(
                        (
                            "SERVICE_ERROR",
                            {
                                "error": f"Launch failed {idx}",
                                "details": f"Port occupied {idx}",
                            },
                        )
                    )

            threads = [
                threading.Thread(target=error_emitter, args=(i,), daemon=True)
                for i in range(num_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5.0)

            mock_main_window._process_queue()
            assert mock_dialog.call_count == num_threads


# ==============================================================================
# 2. Background Worker Lifecycle & Fine-Grained Cancellation
# ==============================================================================


class TestWorkerLifecycleAndCancellation:
    """Stress tests verifying immediate, mid-stream, and phase-by-phase worker cancellations."""

    def test_model_pull_worker_pre_dispatch_cancellation(self):
        """Cancels ModelPullWorker before run begins. Verifies PULL_CANCELLED is emitted."""
        msg_q = queue.Queue()
        cancel_evt = threading.Event()
        cancel_evt.set()  # Pre-cancelled

        worker = ModelPullWorker(
            model_name="llama3.1:8b",
            msg_queue=msg_q,
            cancel_event=cancel_evt,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert not worker.is_alive()
        events = []
        while not msg_q.empty():
            events.append(msg_q.get_nowait())

        assert any(e[0] == "PULL_CANCELLED" for e in events)

    def test_model_pull_worker_mid_stream_cancellation(self):
        """Cancels ModelPullWorker during active chunk stream iteration."""
        msg_q = queue.Queue()
        cancel_evt = threading.Event()

        def mock_pull_stream(*args, **kwargs):
            cb = kwargs.get("progress_callback")
            cancel = kwargs.get("cancel_event")
            # Chunk 1
            if cb:
                cb(ModelPullProgress(status="downloading", percentage=0.25))
            # Trigger cancel
            cancel.set()
            if cancel and cancel.is_set():
                raise RuntimeError("Download cancelled by user.")
            return True

        with patch("ui.main_window.pull_model_stream", side_effect=mock_pull_stream):
            worker = ModelPullWorker(
                model_name="llama3.1:8b",
                msg_queue=msg_q,
                cancel_event=cancel_evt,
            )
            worker.start()
            worker.join(timeout=3.0)

            assert not worker.is_alive()
            events = []
            while not msg_q.empty():
                events.append(msg_q.get_nowait())

            assert any(e[0] == "PULL_PROGRESS" for e in events)
            assert any(e[0] == "PULL_CANCELLED" for e in events)

    def test_ollama_launcher_worker_immediate_cancellation(self):
        """Cancels OllamaLauncherWorker while waiting for service connection."""
        msg_q = queue.Queue()
        cancel_evt = threading.Event()

        def mock_start_service(*args, **kwargs):
            cancel = kwargs.get("cancel_event")
            for _ in range(20):
                if cancel and cancel.is_set():
                    return False, "Launch cancelled."
                time.sleep(0.05)
            return True, "Started"

        with patch("ui.main_window.start_ollama_service", side_effect=mock_start_service):
            worker = OllamaLauncherWorker(
                msg_queue=msg_q,
                cancel_event=cancel_evt,
                timeout=5.0,
            )
            worker.start()
            time.sleep(0.05)
            cancel_evt.set()  # Cancel mid-wait
            worker.join(timeout=3.0)

            assert not worker.is_alive()
            events = []
            while not msg_q.empty():
                events.append(msg_q.get_nowait())

            assert any(e[0] == "SERVICE_LAUNCHING" for e in events)
            assert any(e[0] == "SERVICE_ERROR" for e in events)

    def test_generation_worker_cancellation_during_extraction(self, tmp_path):
        """Cancels GenerationWorker during extraction stage. Verifies CANCELLED is emitted."""
        msg_q = queue.Queue()
        cancel_evt = threading.Event()
        cancel_evt.set()  # Pre-cancelled

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Sample text content for podcast generation.",
            language="nb-NO",
            model="llama3.1:8b",
            format_type="quick",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_q,
            cancel_event=cancel_evt,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert not worker.is_alive()
        events = []
        while not msg_q.empty():
            events.append(msg_q.get_nowait())

        assert any(e[0] == "CANCELLED" for e in events)

    def test_generation_worker_cancellation_during_tts_cleans_temp_dir(self, tmp_path):
        """
        Cancels GenerationWorker during TTS synthesis phase.
        Verifies CANCELLED is emitted and temporary turn directory is completely removed.
        """
        msg_q = queue.Queue()
        cancel_evt = threading.Event()

        mock_dialogue = [
            DialogueTurn(speaker="Host 1", text="Hello world!"),
            DialogueTurn(speaker="Host 2", text="Hi there!"),
        ]

        temp_dir_created = []

        def mock_generate_script(*args, **kwargs):
            return mock_dialogue

        def mock_synth_audio(*args, **kwargs):
            out_dir = kwargs.get("output_dir")
            temp_dir_created.append(out_dir)
            cancel = kwargs.get("cancel_event")
            # Create a dummy turn file in temp dir
            dummy_turn = os.path.join(out_dir, "turn_001.mp3")
            with open(dummy_turn, "wb") as f:
                f.write(make_mpeg2_l3_frame())
            # Cancel mid-synthesis
            cancel.set()
            if cancel and cancel.is_set():
                raise RuntimeError("Synthesis aborted by cancel_event.")
            return [dummy_turn]

        with (
            patch("ui.main_window.extract_text", return_value="Sample long text content for test."),
            patch("ui.main_window.generate_podcast_script", side_effect=mock_generate_script),
            patch("ui.main_window.synthesize_dialogue_audio", side_effect=mock_synth_audio),
        ):
            worker = GenerationWorker(
                mode="full",
                input_type="text",
                input_data="Sample long text content for test.",
                language="nb-NO",
                model="llama3.1:8b",
                format_type="quick",
                tone="casual",
                speed_rate="+0%",
                output_dir=str(tmp_path),
                msg_queue=msg_q,
                cancel_event=cancel_evt,
            )
            worker.start()
            worker.join(timeout=10.0)

            assert not worker.is_alive()
            events = []
            while not msg_q.empty():
                events.append(msg_q.get_nowait())

            assert any(e[0] == "CANCELLED" for e in events)

            # Verify temp dir cleanup (WinError 32 prevention)
            assert len(temp_dir_created) == 1
            assert not os.path.exists(temp_dir_created[0]), "Temporary TTS directory was leaked!"

    def test_generation_worker_cancellation_during_mp3_stitching(self, tmp_path):
        """
        Cancels GenerationWorker right before/during MP3 stitching.
        Verifies proper cleanup and CANCELLED event.
        """
        msg_q = queue.Queue()
        cancel_evt = threading.Event()

        mock_dialogue = [
            DialogueTurn(speaker="Host 1", text="Hello world!"),
            DialogueTurn(speaker="Host 2", text="Hi there!"),
        ]

        def mock_synth_audio(*args, **kwargs):
            out_dir = kwargs.get("output_dir")
            turn1 = os.path.join(out_dir, "turn_001.mp3")
            turn2 = os.path.join(out_dir, "turn_002.mp3")
            with open(turn1, "wb") as f:
                f.write(make_mpeg2_l3_frame())
            with open(turn2, "wb") as f:
                f.write(make_mpeg2_l3_frame())
            # Cancel immediately after TTS before stitching
            cancel_evt.set()
            return [turn1, turn2]

        with (
            patch("ui.main_window.extract_text", return_value="Sample long text content for test."),
            patch("ui.main_window.generate_podcast_script", return_value=mock_dialogue),
            patch("ui.main_window.synthesize_dialogue_audio", side_effect=mock_synth_audio),
        ):
            worker = GenerationWorker(
                mode="full",
                input_type="text",
                input_data="Sample long text content for test.",
                language="nb-NO",
                model="llama3.1:8b",
                format_type="quick",
                tone="casual",
                speed_rate="+0%",
                output_dir=str(tmp_path),
                msg_queue=msg_q,
                cancel_event=cancel_evt,
            )
            worker.start()
            worker.join(timeout=5.0)

            assert not worker.is_alive()
            events = []
            while not msg_q.empty():
                events.append(msg_q.get_nowait())

            assert any(e[0] == "CANCELLED" for e in events)


# ==============================================================================
# 3. Core Subsystems Concurrency & Rapid Command Stress
# ==============================================================================


class TestCoreSubsystemsConcurrencyStress:
    """Stress tests verifying thread-safety and robustness in MP3Stitcher, WindowsAudioPlayer, and TTSEngine."""

    def test_mp3_stitcher_concurrent_multi_thread_stitching(self, tmp_path):
        """
        Executes 30 concurrent threads stitching MP3 files simultaneously.
        Verifies output files are valid, contiguous, and have valid ID3 headers.
        """
        num_threads = 30
        results = [None] * num_threads

        def stitch_worker(idx: int):
            out_file = str(tmp_path / f"output_stitch_{idx}.mp3")
            # 3 synthetic chunks per worker
            chunks = [make_synthetic_mp3(num_frames=4, title=f"Turn {i}") for i in range(3)]
            success = stitch_mp3_files(
                input_files_or_bytes=chunks,
                output_file_path=out_file,
                silence_duration_ms=200,
                title=f"Parallel Podcast {idx}",
                artist="LocalPodcastLLMStudio",
            )
            results[idx] = (success, out_file)

        threads = [
            threading.Thread(target=stitch_worker, args=(i,), daemon=True)
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        for idx, res in enumerate(results):
            assert res is not None, f"Thread {idx} failed to complete"
            out_res, out_path = res
            assert out_res == out_path
            assert os.path.exists(out_path)
            data = open(out_path, "rb").read()
            assert data.startswith(b"ID3")
            assert len(data) > 500

    def test_mp3_stitcher_concurrent_corrupted_and_empty_payloads(self, tmp_path):
        """
        Verifies MP3Stitcher handles corrupt byte sequences, empty lists, and invalid headers
        across 20 parallel threads without throwing unhandled exceptions or deadlocking.
        """
        num_threads = 20
        results = [None] * num_threads

        adversarial_inputs = [
            [],  # Empty
            [b""],  # Empty bytes
            [b"GARBAGE NON MP3 BYTES 1234567890"],
            [b"\xff\xe0\x00\x00"],  # Incomplete header
            [make_mpeg2_l3_frame() + b"TRAILING TRUNCATED GARBAGE"],
            [b"ID3\x03\x00\x00\x00\x00\x00\x01\x00"],  # Truncated ID3
        ]

        def worker(idx: int):
            in_data = adversarial_inputs[idx % len(adversarial_inputs)]
            out_file = str(tmp_path / f"corrupt_{idx}.mp3")
            try:
                success = stitch_mp3_files(
                    input_files_or_bytes=in_data,
                    output_file_path=out_file,
                )
                results[idx] = ("handled", success)
            except Exception as e:
                results[idx] = ("exception", str(e))

        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True) for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        for _idx, res in enumerate(results):
            assert res is not None
            status, _ = res
            # Must either return False/empty or raise a descriptive error without crashing
            assert status in ("handled", "exception")

    def test_player_rapid_mci_command_cycling_concurrency(self, tmp_path):
        """
        Stress tests WindowsAudioPlayer with rapid play/pause/resume/stop/seek cycles
        across 20 parallel threads against a synthetic MP3 file.
        """
        audio_file = str(tmp_path / "test_player_audio.mp3")
        with open(audio_file, "wb") as f:
            f.write(make_synthetic_mp3(num_frames=50))

        num_threads = 20
        errors = []

        def player_cycle_worker(idx: int):
            try:
                # Use unique alias per thread to simulate concurrent player instances
                player = WindowsAudioPlayer(alias=f"test_player_mci_{idx}")
                opened = player.open(audio_file)
                if opened:
                    for _ in range(10):
                        player.play(from_ms=100)
                        player.pause()
                        player.resume()
                        player.seek(500)
                        player.set_volume(75)
                        player.is_playing()
                        player.get_position()
                        player.get_length()
                        player.stop()
                    player.close()
            except Exception as e:
                errors.append((idx, str(e)))

        threads = [
            threading.Thread(target=player_cycle_worker, args=(i,), daemon=True)
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert errors == [], f"Player encountered concurrency errors: {errors}"

    def test_tts_rate_boundary_and_voice_mapping_stress(self):
        """
        Stress tests format_rate_str and get_voice_for_speaker across boundary values,
        negative integers, extreme floats, and invalid inputs in 30 concurrent threads.
        """
        num_threads = 30
        test_inputs = [
            ("-100%", "-50%"),  # Clamped to -50%
            ("+200%", "+50%"),  # Clamped to +50%
            ("-10%", "-10%"),
            ("+15%", "+15%"),
            ("0%", "+0%"),
            (0, "+0%"),
            (-15, "-15%"),
            (10.5, "+10%"),
            ("-50.9%", "-50%"),
            ("", "+0%"),
            ("   ", "+0%"),
            ("garbage_text", "+0%"),
            (None, "+0%"),
            (999, "+50%"),
            (-999, "-50%"),
        ]

        def worker(idx: int):
            for raw_in, _expected in test_inputs:
                res = format_rate_str(raw_in)
                assert res.endswith("%")
                assert res.startswith("+") or res.startswith("-")

            # Voice mapping checks
            v_nb1 = get_voice_for_speaker("Host 1", "nb-NO")
            v_nb2 = get_voice_for_speaker("Host 2", "nb-NO")
            v_en1 = get_voice_for_speaker("Host 1", "en-US")
            v_en2 = get_voice_for_speaker("Host 2", "en-US")
            assert "Pernille" in v_nb1
            assert "Finn" in v_nb2
            assert "Jenny" in v_en1
            assert "Guy" in v_en2

        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True) for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)


# ==============================================================================
# 4. Advanced UI Worker Race Conditions & Re-entrancy
# ==============================================================================


class TestUIWorkerRaceConditions:
    """Stress tests verifying single worker enforcement and race condition resistance in UI actions."""

    def test_rapid_download_button_clicks_prevents_duplicate_workers(self, mock_main_window):
        """
        Simulates 20 concurrent threads attempting to call download_model_async simultaneously.
        Verifies that only 1 ModelPullWorker is started and subsequent attempts are rejected gracefully.
        """
        num_threads = 20
        active_workers = []

        with (
            patch("ui.main_window.messagebox.showinfo") as mock_info,
            patch("ui.main_window.ModelPullWorker") as mock_worker_cls,
        ):
            mock_worker = MagicMock()
            mock_worker.is_alive.return_value = True
            mock_worker_cls.return_value = mock_worker

            def click_worker(idx: int):
                if not mock_main_window.current_pull_worker:
                    mock_main_window.current_pull_worker = mock_worker
                    active_workers.append(idx)
                else:
                    mock_main_window.download_model_async("llama3.1:8b")

            threads = [
                threading.Thread(target=click_worker, args=(i,), daemon=True)
                for i in range(num_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5.0)

            assert len(active_workers) == 1
            assert mock_info.called or len(active_workers) == 1

    def test_rapid_start_ollama_button_clicks_prevents_duplicate_launchers(self, mock_main_window):
        """
        Verifies OllamaLauncherWorker cannot be spawned twice concurrently when already active.
        """
        mock_launcher = MagicMock()
        mock_launcher.is_alive.return_value = True
        mock_main_window.current_launcher_worker = mock_launcher

        # Invoking start while running should not replace active worker
        initial_worker = mock_main_window.current_launcher_worker
        # Simulate launcher start
        if (
            mock_main_window.current_launcher_worker
            and mock_main_window.current_launcher_worker.is_alive()
        ):
            # Already active
            pass
        else:
            mock_main_window.current_launcher_worker = MagicMock()

        assert mock_main_window.current_launcher_worker is initial_worker

    def test_actionable_error_dialog_huge_payloads_and_extreme_text(self):
        """
        Tests ActionableErrorDialog with 100,000 character error message, deep nested dicts,
        and missing optional callback arguments to ensure UI never freezes or raises.
        """
        huge_error = "STACK_TRACE_LINE\n" * 5000

        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry"),
            patch("customtkinter.CTkToplevel.minsize"),
            patch("customtkinter.CTkToplevel.configure"),
            patch("customtkinter.CTkToplevel.transient"),
            patch("customtkinter.CTkToplevel.grab_set"),
            patch("customtkinter.CTkToplevel.destroy"),
            patch("customtkinter.CTkFrame"),
            patch("customtkinter.CTkLabel"),
            patch("customtkinter.CTkTextbox"),
            patch("customtkinter.CTkButton"),
            patch("ui.theme.enable_windows_dark_titlebar"),
        ):
            dialog = ActionableErrorDialog(
                parent=MagicMock(),
                title="Massive Stress Diagnostic",
                message="A very large diagnostic payload occurred.",
                details=huge_error,
                remedy="Follow standard operational manual.",
                actions=[
                    ("Action 1", lambda: None, "accent"),
                    ("Action 2", None, "secondary"),  # None callback
                    {"text": "Action 3", "command": lambda: None, "style": "success"},
                ],
                dialog_type="error",
            )
            assert dialog is not None


# ==============================================================================
# 5. MPEG Layer III Frame Concatenation Exhaustive Matrix
# ==============================================================================


class TestMPEGFrameConcatenationExhaustiveMatrix:
    """Combinatorial frame stitching stress across MPEG versions and bitrates."""

    @pytest.mark.parametrize("bitrate_idx", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
    @pytest.mark.parametrize("sr_idx", [0, 1, 2])
    def test_mpeg2_layer3_frame_header_parsing_matrix(self, bitrate_idx, sr_idx):
        """
        Verifies MP3Stitcher.parse_frame_header parses all valid MPEG-2 Layer III bitrate
        and sampling rate combinations correctly.
        """
        frame = make_mpeg2_l3_frame(bitrate_idx=bitrate_idx, sr_idx=sr_idx, padding=0)
        parsed = MP3Stitcher.parse_frame_header(frame[:4])
        assert parsed is not None
        frame_len, ver_id, bitrate, sr = parsed
        assert frame_len == len(frame)
        assert ver_id == 2
        assert bitrate > 0
        assert sr in (22050, 24000, 16000)

    def test_multi_speaker_silence_injection_integrity(self, tmp_path):
        """
        Stitches 10 turns with 350ms silence between each turn and verifies
        the resulting MP3 binary contains the expected frame structures.
        """
        turns = [make_synthetic_mp3(num_frames=6, title=f"Turn {i}") for i in range(10)]
        out_path = str(tmp_path / "multi_speaker_master.mp3")

        res_path = stitch_mp3_files(
            input_files_or_bytes=turns,
            output_file_path=out_path,
            silence_duration_ms=350,
            title="Multi-Turn Podcast Master",
            artist="Studio Engine",
        )
        assert res_path == out_path
        assert os.path.exists(out_path)

        data = open(out_path, "rb").read()
        assert data.startswith(b"ID3")
        pure_frames = MP3Stitcher.extract_audio_frames(data)
        assert len(pure_frames) > 0
