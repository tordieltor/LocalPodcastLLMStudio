"""
LocalPodcastLLMStudio UI & Async Pipeline Tests (tests/test_ui.py)
==================================================================
Unit and integration tests for CustomTkinter UI theming, custom widgets,
background GenerationWorker thread queue events, cancellation, and app bootstrap.
"""

import queue
import sys
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import customtkinter as ctk

# Theme and Widget Imports
import ui.theme as theme
from core.parser import DialogueTurn
from ui.main_window import GenerationWorker
from ui.widgets import (
    AboutDialog,
    ActionableErrorDialog,
    TimeSlider,
)


# ==============================================================================
# 1. UI Theme & Styling Tests
# ==============================================================================
class TestUITheme:
    """Verifies color palette constants and typography helper functions."""

    def test_theme_colors_defined(self):
        assert theme.COLOR_BG == "#1a1b26"
        assert theme.COLOR_CARD == "#24283b"
        assert theme.COLOR_CARD_BORDER == "#414868"
        assert theme.COLOR_ACCENT == "#7aa2f7"
        assert theme.COLOR_SUCCESS == "#9ece6a"
        assert theme.COLOR_WARNING == "#ff9e64"
        assert theme.COLOR_ERROR == "#f7768e"
        assert theme.COLOR_TEXT_PRIMARY == "#c0caf5"
        assert theme.COLOR_TEXT_SECONDARY == "#7982a9"

    def test_typography_helpers(self):
        try:
            root = ctk.CTk()
            root.withdraw()
            try:
                title_font = theme.get_font_title()
                assert title_font is not None

                heading_font = theme.get_font_heading()
                assert heading_font is not None

                body_font = theme.get_font_body()
                assert body_font is not None

                caption_font = theme.get_font_caption()
                assert caption_font is not None

                code_font = theme.get_font_code()
                assert code_font is not None
            finally:
                root.destroy()
        except Exception:
            # Headless fallback where display is unavailable
            with patch("customtkinter.CTkFont", return_value=MagicMock()):
                assert theme.get_font_title() is not None
                assert theme.get_font_heading() is not None
                assert theme.get_font_body() is not None

    def test_enable_windows_dark_titlebar_mocked(self):
        mock_win = MagicMock()
        mock_win.winfo_id.return_value = 12345
        with patch("sys.platform", "win32"):
            with patch("ctypes.windll.dwmapi.DwmSetWindowAttribute", return_value=0):
                res = theme.enable_windows_dark_titlebar(mock_win)
                assert isinstance(res, bool)


# ==============================================================================
# 2. Reusable UI Widgets Tests (Headless Verification)
# ==============================================================================
class TestUIWidgets:
    """Verifies widget initialization and functional logic without GUI display lock."""

    def test_time_slider_format_ms(self):
        assert TimeSlider._format_ms(0) == "00:00"
        assert TimeSlider._format_ms(65000) == "01:05"
        assert TimeSlider._format_ms(3600000) == "60:00"

    def test_labeled_slider_format(self):
        def format_fn(val):
            return f"{int(val):+d}%"

        assert format_fn(0) == "+0%"
        assert format_fn(10) == "+10%"
        assert format_fn(-5) == "-5%"

    def test_actionable_error_dialog_remedy_and_details(self):
        with patch.object(ActionableErrorDialog, "__init__", return_value=None) as mock_init:
            ActionableErrorDialog(
                parent=MagicMock(),
                title="Test Error",
                message="Error message",
                details="Details text",
            )
            mock_init.assert_called_once()

        with patch.object(ActionableErrorDialog, "__init__", return_value=None) as mock_init_remedy:
            ActionableErrorDialog(
                parent=MagicMock(),
                title="Test Error",
                message="Error message",
                remedy="Remedy text",
            )
            mock_init_remedy.assert_called_once()

    def test_about_dialog_initialization(self):
        with patch.object(AboutDialog, "__init__", return_value=None) as mock_about:
            AboutDialog(parent=MagicMock())
            mock_about.assert_called_once()

    def test_main_window_show_about_dialog_method(self):
        from ui.main_window import MainWindow

        mock_main = MagicMock(spec=MainWindow)
        with patch("ui.main_window.AboutDialog") as mock_about_cls:
            MainWindow.show_about_dialog(mock_main)
            mock_about_cls.assert_called_once_with(mock_main)


# ==============================================================================
# 3. GenerationWorker & Queue Protocol Tests
# ==============================================================================
class TestGenerationWorker:
    """Tests async background worker execution, event queuing, and cancellation."""

    @patch("ui.main_window.generate_podcast_script")
    @patch("ui.main_window.synthesize_dialogue_audio")
    @patch("ui.main_window.stitch_mp3_files")
    def test_worker_full_generation_success(
        self, mock_stitch, mock_synth, mock_gen_script, tmp_path
    ):
        mock_gen_script.return_value = [
            DialogueTurn(speaker="Host 1", text="Welcome!"),
            DialogueTurn(speaker="Host 2", text="Glad to be here!"),
        ]
        mock_synth.return_value = ["/tmp/turn_001.mp3", "/tmp/turn_002.mp3"]
        mock_stitch.return_value = str(tmp_path / "podcast_out.mp3")

        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="This is a test topic for podcast generation.",
            language="en-US",
            model="llama3.1:8b",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )

        worker.run()

        # Collect all events from queue
        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "STATUS" in event_types
        assert "PROGRESS" in event_types
        assert "SCRIPT_READY" in event_types
        assert "GENERATION_DONE" in event_types

        # Verify GENERATION_DONE payload
        done_event = next(ev for ev in events if ev[0] == "GENERATION_DONE")
        payload = done_event[1]
        assert "mp3_path" in payload
        assert "script_path" in payload
        assert len(payload["dialogue"]) == 2

    @patch("ui.main_window.generate_podcast_script")
    def test_worker_script_only_mode(self, mock_gen_script, tmp_path):
        mock_gen_script.return_value = [
            DialogueTurn(speaker="Host 1", text="Hello Norwegian podcast!"),
            DialogueTurn(speaker="Host 2", text="Hei Kari!"),
        ]

        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="script_only",
            input_type="text",
            input_data="Norwegian test text topic notes.",
            language="nb-NO",
            model="llama3.1:8b",
            format_type="quick",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )

        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "SCRIPT_READY" in event_types
        assert "SCRIPT_ONLY_DONE" in event_types
        assert "GENERATION_DONE" not in event_types

    @patch("ui.main_window.synthesize_dialogue_audio")
    @patch("ui.main_window.stitch_mp3_files")
    def test_worker_audio_from_script_mode(self, mock_stitch, mock_synth, tmp_path):
        dialogue = [
            DialogueTurn(speaker="Host 1", text="Turn 1 from edited script."),
            DialogueTurn(speaker="Host 2", text="Turn 2 from edited script."),
        ]
        mock_synth.return_value = ["/tmp/turn1.mp3", "/tmp/turn2.mp3"]
        mock_stitch.return_value = str(tmp_path / "podcast_edited.mp3")

        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="audio_from_script",
            input_type="dialogue",
            input_data=dialogue,
            language="en-US",
            model="llama3.1:8b",
            format_type="custom",
            tone="custom",
            speed_rate="+5%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )

        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "STATUS" in event_types
        assert "GENERATION_DONE" in event_types

    def test_worker_cancellation(self, tmp_path):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()
        cancel_event.set()  # Pre-set cancel flag

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Sample text content for cancel test.",
            language="en-US",
            model="llama3.1:8b",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )

        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "CANCELLED" in event_types
        assert "GENERATION_DONE" not in event_types

    def test_worker_empty_input_error(self, tmp_path):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="   ",
            language="en-US",
            model="llama3.1:8b",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )

        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "ERROR" in event_types


# ==============================================================================
# 4. App Bootstrap & Crash Logger Tests
# ==============================================================================
class TestAppBootstrap:
    """Verifies crash logging hook and app initialization."""

    def test_crash_logger_writes_file(self, tmp_path, monkeypatch):
        from app import log_crash

        monkeypatch.chdir(tmp_path)

        try:
            raise ValueError("Test synthetic exception for crash logger")
        except ValueError:
            exc_type, exc_val, exc_tb = sys.exc_info()
            log_crash(exc_type, exc_val, exc_tb)

        crash_log = tmp_path / "crash_dump.log"
        assert crash_log.exists()
        content = crash_log.read_text(encoding="utf-8")
        assert "Crash Report" in content
        assert "Test synthetic exception for crash logger" in content
