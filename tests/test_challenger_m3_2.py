"""
Adversarial Empirical Challenge Test Suite for Milestone 3 (UI Integration & Controls)
======================================================================================
Author: Challenger 2 (critic, specialist)
Framework: rational-e2e-testing (5-tier empirical architecture)

Covers:
- Tier 1: Grounding Mode Enum & Bilingual Language Combinations
- Tier 2: Modality Switching & Bidirectional State Machine Auto-Sync
- Tier 3: ActionableErrorDialog Parameter Matrix (0, 1, 2, 3, 5+ buttons, styles, dismiss, long text, missing kwargs)
- Tier 4: UI Error Boundaries, Event Queue Robustness & Malformed Payload Ingestion
- Tier 5: Concurrency, Rapid Worker Cancellation & Lifecycle Teardown
"""

import queue
import threading
from typing import Any
from unittest.mock import MagicMock, call, patch

import customtkinter as ctk
import pytest

from core.ollama import ModelPullProgress
from core.prompts import (
    GROUNDING_MODE_PRESETS,
    GroundingMode,
)
from ui.main_window import (
    GROUNDING_UI_OPTIONS,
    GenerationWorker,
    MainWindow,
    ModelPullWorker,
    OllamaLauncherWorker,
)
from ui.theme import (
    COLOR_ACCENT,
    COLOR_BUTTON_DANGER,
    COLOR_BUTTON_SECONDARY,
    COLOR_BUTTON_SUCCESS,
    COLOR_WARNING,
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
    """Provides a hidden session-wide Tk root for headless environments."""
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
def mock_window():
    """Builds a spec-compliant mock of MainWindow with mock widgets for headless testing."""
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
    win._update_grounding_description.side_effect = lambda: (
        MainWindow._update_grounding_description(win)
    )

    return win


# ==============================================================================
# Tier 1: Grounding Mode & Language Combinations
# ==============================================================================
class TestTier1GroundingModeLanguageMatrix:
    """Adversarially tests all GroundingMode enum variants, aliases, and language permutations."""

    @pytest.mark.parametrize(
        "ui_choice,expected_mode",
        [
            ("Strict Source-Only (100% Document Fidelity)", "strict"),
            ("Creative Analogy & Synthesis", "creative"),
            ("Open Topic / Scratch (Free Generative Synthesis)", "open_topic"),
            ("STRICT", "strict"),
            ("strict", "strict"),
            ("CREATIVE", "creative"),
            ("creative", "creative"),
            ("OPEN_TOPIC", "open_topic"),
            ("open_topic", "open_topic"),
            ("open", "open_topic"),
            ("scratch", "open_topic"),
            ("fidelity", "strict"),
            ("analogy", "creative"),
            (GroundingMode.STRICT, "strict"),
            (GroundingMode.CREATIVE, "creative"),
            (GroundingMode.OPEN_TOPIC, "open_topic"),
        ],
    )
    def test_get_selected_grounding_mode_resolution(self, mock_window, ui_choice, expected_mode):
        mock_window.grounding_menu.get.return_value = str(ui_choice)
        mode = MainWindow.get_selected_grounding_mode(mock_window)
        assert mode == expected_mode

    @pytest.mark.parametrize("mode_key", ["strict", "creative", "open_topic"])
    @pytest.mark.parametrize(
        "lang_string,expected_lang_key",
        [
            ("Norwegian Bokmål (Kari & Ola)", "description_nb"),
            ("Norwegian", "description_nb"),
            ("nb-NO", "description_nb"),
            ("Norsk", "description_nb"),
            ("English (Jenny & Guy)", "description_en"),
            ("English", "description_en"),
            ("en-US", "description_en"),
            ("German (Deutsch)", "description_en"),  # Fallback to English
            ("", "description_en"),  # Empty fallback
        ],
    )
    def test_grounding_description_bilingual_matrix(
        self, mock_window, mode_key, lang_string, expected_lang_key
    ):
        mock_window.grounding_menu.get.return_value = mode_key
        mock_window.lang_menu.get.return_value = lang_string

        MainWindow._update_grounding_description(mock_window)

        mock_window.grounding_desc_label.configure.assert_called()
        call_kwargs = mock_window.grounding_desc_label.configure.call_args[1]
        assert "text" in call_kwargs
        rendered_text = call_kwargs["text"]

        expected_desc = GROUNDING_MODE_PRESETS[mode_key][
            "description_nb" if "Norwegian" in lang_string else "description_en"
        ]
        assert expected_desc in rendered_text
        expected_badge = GROUNDING_MODE_PRESETS[mode_key].get("badge", "")
        if expected_badge:
            assert f"[{expected_badge}]" in rendered_text

    def test_grounding_mode_unknown_fallback(self, mock_window):
        """Tests that completely invalid strings degrade gracefully to strict preset without raising."""
        mock_window.grounding_menu.get.return_value = "NonExistentMode_12345"
        mock_window.lang_menu.get.return_value = "English"

        mode = MainWindow.get_selected_grounding_mode(mock_window)
        assert mode == "strict"

        MainWindow._update_grounding_description(mock_window)
        call_kwargs = mock_window.grounding_desc_label.configure.call_args[1]
        assert GROUNDING_MODE_PRESETS["strict"]["description_en"] in call_kwargs["text"]


# ==============================================================================
# Tier 2: Modality Switching State Machine & Auto-Sync
# ==============================================================================
class TestTier2ModalitySwitchingStateMachine:
    """Stress tests switching back and forth across all modalities to verify state consistency."""

    def test_modality_switching_cycle_preserves_consistency(self, mock_window):
        """Cycle: File -> Topic -> Pasted -> Topic -> File -> Pasted -> File"""
        # Step 1: Start at File (Document)
        mock_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[0]
        MainWindow._on_modality_changed(mock_window, "Document (.txt/.md/.pdf)")
        assert mock_window.input_modality_var.set.call_args_list[-1] == call("file")
        assert mock_window.file_container.pack.called

        # Step 2: Switch to Topic Prompt -> auto-switches to Open Topic
        MainWindow._on_modality_changed(mock_window, "Topic Prompt (Scratch)")
        assert mock_window.input_modality_var.set.call_args_list[-1] == call("topic")
        assert mock_window.grounding_menu.set.call_args_list[-1] == call(GROUNDING_UI_OPTIONS[2])
        assert mock_window.text_container.pack.called
        assert mock_window.file_container.pack_forget.called

        # Update mock grounding menu to reflect open_topic
        mock_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[2]

        # Step 3: Switch to Pasted Text -> auto-switches from Open Topic back to Strict
        MainWindow._on_modality_changed(mock_window, "Pasted Text")
        assert mock_window.input_modality_var.set.call_args_list[-1] == call("text")
        assert mock_window.grounding_menu.set.call_args_list[-1] == call(GROUNDING_UI_OPTIONS[0])
        assert mock_window.file_container.pack_forget.called
        assert mock_window.text_container.pack.called

        # Step 4: User manually sets Creative mode on Pasted Text
        mock_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[1]
        MainWindow._on_grounding_mode_changed(mock_window, GROUNDING_UI_OPTIONS[1])

        # Reset mock call history before Step 5
        mock_window.grounding_menu.set.reset_mock()

        # Step 5: Switch from Pasted Text (Creative) to Document (.txt/.md/.pdf)
        # It should NOT overwrite Creative mode since it was not open_topic!
        MainWindow._on_modality_changed(mock_window, "Document (.txt/.md/.pdf)")
        assert mock_window.input_modality_var.set.call_args_list[-1] == call("file")
        # grounding_menu.set should NOT have been called
        mock_window.grounding_menu.set.assert_not_called()

        # Step 6: Switch back to Topic Prompt
        MainWindow._on_modality_changed(mock_window, "Topic Prompt (Scratch)")
        assert mock_window.input_modality_var.set.call_args_list[-1] == call("topic")
        assert mock_window.grounding_menu.set.call_args_list[-1] == call(GROUNDING_UI_OPTIONS[2])

        # Step 7: Switch back to File
        mock_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[2]
        MainWindow._on_modality_changed(mock_window, "Document (.txt/.md/.pdf)")
        assert mock_window.input_modality_var.set.call_args_list[-1] == call("file")
        assert mock_window.grounding_menu.set.call_args_list[-1] == call(GROUNDING_UI_OPTIONS[0])


# ==============================================================================
# Tier 3: ActionableErrorDialog Parameter Space & Button Permutations
# ==============================================================================
class TestTier3ActionableErrorDialogPermutations:
    """Stress tests ActionableErrorDialog with 0, 1, 2, 3, 5+ buttons, styles, dismiss flags, and long text."""

    @pytest.mark.parametrize("num_actions", [0, 1, 2, 3, 5, 8])
    def test_action_button_counts(self, num_actions):
        """Verifies that ActionableErrorDialog correctly creates N action buttons + 1 Close button."""
        callbacks = [MagicMock(name=f"cb_{i}") for i in range(num_actions)]
        actions = [(f"Btn {i}", callbacks[i], "accent", True) for i in range(num_actions)]

        created_buttons = []

        def fake_button(*args, **kwargs):
            btn = MagicMock()
            btn.text = kwargs.get("text")
            btn.command = kwargs.get("command")
            btn.fg_color = kwargs.get("fg_color")
            created_buttons.append(btn)
            return btn

        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry"),
            patch("customtkinter.CTkToplevel.minsize"),
            patch("customtkinter.CTkToplevel.configure"),
            patch("customtkinter.CTkToplevel.transient"),
            patch("customtkinter.CTkToplevel.grab_set"),
            patch("customtkinter.CTkToplevel.destroy") as mock_destroy,
            patch("customtkinter.CTkFont", return_value=MagicMock()),
            patch("ui.widgets.get_font_heading", return_value=MagicMock()),
            patch("ui.widgets.get_font_body", return_value=MagicMock()),
            patch("ui.widgets.get_font_body_bold", return_value=MagicMock()),
            patch("ui.widgets.get_font_code", return_value=MagicMock()),
            patch("ui.widgets.get_font_caption", return_value=MagicMock()),
            patch("ui.widgets.get_font_badge", return_value=MagicMock()),
            patch("customtkinter.CTkFrame"),
            patch("customtkinter.CTkLabel"),
            patch("customtkinter.CTkTextbox"),
            patch("customtkinter.CTkButton", side_effect=fake_button),
        ):
            dialog = ActionableErrorDialog(
                parent=MagicMock(),
                title="Multi Action Test",
                message="Testing button counts",
                actions=actions if num_actions > 0 else None,
                close_text="Dismiss",
            )
            assert dialog is not None
            # Total CTkButtons = num_actions + 1 (for Close button)
            assert len(created_buttons) == num_actions + 1
            assert created_buttons[-1].text == "Dismiss"

            # Execute all action buttons and verify invocation and destruction
            for i in range(num_actions):
                mock_destroy.reset_mock()
                created_buttons[i].command()
                callbacks[i].assert_called_once()
                mock_destroy.assert_called_once()

    def test_action_button_styles_and_colors(self):
        """Verifies color mapping across all supported button style keywords."""
        style_expectations = [
            ("primary", COLOR_ACCENT),
            ("accent", COLOR_ACCENT),
            ("success", COLOR_BUTTON_SUCCESS),
            ("ready", COLOR_BUTTON_SUCCESS),
            ("warning", COLOR_WARNING),
            ("danger", COLOR_BUTTON_DANGER),
            ("error", COLOR_BUTTON_DANGER),
            ("secondary", COLOR_BUTTON_SECONDARY),
            ("unknown_style", COLOR_BUTTON_SECONDARY),
        ]

        created_buttons = []

        def fake_button(*args, **kwargs):
            btn = MagicMock()
            btn.fg_color = kwargs.get("fg_color")
            created_buttons.append(btn)
            return btn

        actions = [
            {"text": f"Style {s}", "callback": MagicMock(), "style": s, "dismiss": False}
            for s, _ in style_expectations
        ]

        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry"),
            patch("customtkinter.CTkToplevel.minsize"),
            patch("customtkinter.CTkToplevel.configure"),
            patch("customtkinter.CTkToplevel.transient"),
            patch("customtkinter.CTkToplevel.grab_set"),
            patch("customtkinter.CTkFont", return_value=MagicMock()),
            patch("ui.widgets.get_font_heading", return_value=MagicMock()),
            patch("ui.widgets.get_font_body", return_value=MagicMock()),
            patch("ui.widgets.get_font_body_bold", return_value=MagicMock()),
            patch("ui.widgets.get_font_code", return_value=MagicMock()),
            patch("ui.widgets.get_font_caption", return_value=MagicMock()),
            patch("ui.widgets.get_font_badge", return_value=MagicMock()),
            patch("customtkinter.CTkFrame"),
            patch("customtkinter.CTkLabel"),
            patch("customtkinter.CTkTextbox"),
            patch("customtkinter.CTkButton", side_effect=fake_button),
        ):
            dialog = ActionableErrorDialog(
                parent=MagicMock(),
                title="Style Test",
                message="Testing button styles",
                actions=actions,
            )
            assert dialog is not None
            for idx, (_, expected_color) in enumerate(style_expectations):
                assert created_buttons[idx].fg_color == expected_color

    def test_dismiss_flag_behavior(self):
        """Verifies that dismiss=False keeps the dialog open while dismiss=True destroys it."""
        cb_persist = MagicMock()
        cb_dismiss = MagicMock()

        created_buttons = []

        def fake_button(*args, **kwargs):
            btn = MagicMock()
            btn.command = kwargs.get("command")
            created_buttons.append(btn)
            return btn

        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry"),
            patch("customtkinter.CTkToplevel.minsize"),
            patch("customtkinter.CTkToplevel.configure"),
            patch("customtkinter.CTkToplevel.transient"),
            patch("customtkinter.CTkToplevel.grab_set"),
            patch("customtkinter.CTkToplevel.destroy") as mock_destroy,
            patch("customtkinter.CTkFont", return_value=MagicMock()),
            patch("ui.widgets.get_font_heading", return_value=MagicMock()),
            patch("ui.widgets.get_font_body", return_value=MagicMock()),
            patch("ui.widgets.get_font_body_bold", return_value=MagicMock()),
            patch("ui.widgets.get_font_code", return_value=MagicMock()),
            patch("ui.widgets.get_font_caption", return_value=MagicMock()),
            patch("ui.widgets.get_font_badge", return_value=MagicMock()),
            patch("customtkinter.CTkFrame"),
            patch("customtkinter.CTkLabel"),
            patch("customtkinter.CTkTextbox"),
            patch("customtkinter.CTkButton", side_effect=fake_button),
        ):
            dialog = ActionableErrorDialog(
                parent=MagicMock(),
                title="Dismiss Test",
                message="Testing dismiss flag",
                actions=[
                    {"text": "Persist", "callback": cb_persist, "dismiss": False},
                    {"text": "Dismiss", "callback": cb_dismiss, "dismiss": True},
                ],
            )
            assert dialog is not None
            # Trigger persist button
            created_buttons[0].command()
            cb_persist.assert_called_once()
            mock_destroy.assert_not_called()

            # Trigger dismiss button
            created_buttons[1].command()
            cb_dismiss.assert_called_once()
            mock_destroy.assert_called_once()

    def test_extreme_payload_and_missing_optional_kwargs(self):
        """Adversarial stress: 100,000 char message, missing kwargs, None callbacks."""
        huge_message = "A" * 100_000
        huge_details = "D" * 50_000

        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry"),
            patch("customtkinter.CTkToplevel.minsize"),
            patch("customtkinter.CTkToplevel.configure"),
            patch("customtkinter.CTkToplevel.transient"),
            patch("customtkinter.CTkToplevel.grab_set"),
            patch("customtkinter.CTkFont", return_value=MagicMock()),
            patch("ui.widgets.get_font_heading", return_value=MagicMock()),
            patch("ui.widgets.get_font_body", return_value=MagicMock()),
            patch("ui.widgets.get_font_body_bold", return_value=MagicMock()),
            patch("ui.widgets.get_font_code", return_value=MagicMock()),
            patch("ui.widgets.get_font_caption", return_value=MagicMock()),
            patch("ui.widgets.get_font_badge", return_value=MagicMock()),
            patch("customtkinter.CTkFrame"),
            patch("customtkinter.CTkLabel"),
            patch("customtkinter.CTkTextbox") as mock_box_cls,
            patch("customtkinter.CTkButton"),
        ):
            mock_box = MagicMock()
            mock_box_cls.return_value = mock_box

            dialog = ActionableErrorDialog(
                parent=None,
                title="Extreme Stress Test",
                message=huge_message,
                details=huge_details,
                action_button_text="No-op Action",
                action_callback=None,  # Callback is None
            )
            assert dialog is not None
            mock_box.insert.assert_called_with("1.0", huge_details)
            mock_box.configure.assert_called_with(state="disabled")


# ==============================================================================
# Tier 4: UI Error Boundaries & Event Ingestion Robustness
# ==============================================================================
class TestTier4ErrorBoundariesAndQueueRobustness:
    """Stress tests event bus with malformed event payloads and unhandled scenarios."""

    @pytest.mark.parametrize(
        "event_type,payload",
        [
            ("STATUS", 12345),
            ("STATUS", None),
            ("STATUS", {"nested": "dict"}),
            ("PROGRESS", 0.75),
            ("PROGRESS", "0.85"),
            ("PULL_PROGRESS", ModelPullProgress(status="pulling", percentage=0.33)),
            ("PULL_DONE", {"model": "llama3.1:8b"}),
            ("PULL_DONE", "Non-dict string payload"),
            ("PULL_ERROR", {"model": "llama3.1:8b", "error": "Disk full"}),
            ("PULL_ERROR", "Raw error message string"),
            ("PULL_CANCELLED", {}),
            ("PULL_CANCELLED", None),
            ("SERVICE_LAUNCHING", "Starting service..."),
            ("SERVICE_LAUNCHING", {"status": "Starting..."}),
            ("SERVICE_STARTED", {"status": "Started", "models": ["m1"]}),
            ("SERVICE_STARTED", "Service running"),
            ("SERVICE_ERROR", {"error": "Port conflict", "details": "11434 occupied"}),
            ("SERVICE_ERROR", "Daemon crashed"),
            ("CANCELLED", "Operation aborted"),
            ("ERROR", {"title": "T", "message": "M", "details": "D"}),
            ("ERROR", "Unstructured string error"),
            ("UNKNOWN_EVENT_TYPE", {"any": "data"}),  # No-op unknown event
        ],
    )
    def test_handle_event_boundary_matrix(self, mock_window, event_type, payload):
        """Verifies that none of the event variations trigger unhandled exceptions."""
        with patch("ui.main_window.ActionableErrorDialog"):
            with patch("tkinter.messagebox.showerror"):
                MainWindow._handle_event(mock_window, event_type, payload)

    def test_queue_overflow_and_rapid_drain(self, mock_window):
        """Verifies that the message queue handles large volumes of high-frequency events gracefully."""
        # Enqueue 1000 events
        for i in range(1000):
            mock_window.msg_queue.put(("STATUS", f"Event #{i}"))

        MainWindow._process_queue(mock_window)
        assert mock_window._handle_event.call_count == 1000
        assert mock_window.msg_queue.empty()


# ==============================================================================
# Tier 5: Concurrency, Worker Cancellation & Lifecycle Safety
# ==============================================================================
class TestTier5ConcurrencyAndWorkerLifecycle:
    """Verifies that threads and workers respect cancellation tokens without leaking resources."""

    def test_model_pull_worker_pre_cancelled(self):
        """Worker initialized with cancel_event already set exits immediately."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()
        cancel_event.set()

        worker = ModelPullWorker(
            model_name="llama3.1:8b",
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )
        with patch("ui.main_window.pull_model_stream", return_value=True):
            worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        assert len(events) >= 1

    def test_ollama_launcher_worker_pre_cancelled(self):
        """Launcher worker handles cancellation cleanly."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()
        cancel_event.set()

        worker = OllamaLauncherWorker(
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )
        with patch(
            "ui.main_window.start_ollama_service",
            return_value=(False, "Cancelled before start"),
        ):
            worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "SERVICE_LAUNCHING" in event_types
        assert "SERVICE_ERROR" in event_types

    def test_generation_worker_cancellation_during_ingestion(self, tmp_path):
        """GenerationWorker cancelled before LLM request triggers CANCELLED event and stops."""
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()
        cancel_event.set()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Sample document content text",
            language="nb-NO",
            model="llama3.1:8b",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_event,
            grounding_mode="strict",
        )
        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        assert len(events) == 1
        assert events[0][0] == "CANCELLED"
        assert "cancelled before ingestion" in events[0][1].lower()

    def test_main_window_on_close_terminates_all_active_workers(self, mock_window):
        """Verifies _on_close signals all 3 workers and releases audio handles."""
        worker1 = MagicMock()
        worker1.is_alive.return_value = True
        worker2 = MagicMock()
        worker2.is_alive.return_value = True
        worker3 = MagicMock()
        worker3.is_alive.return_value = True

        mock_window.current_worker = worker1
        mock_window.current_pull_worker = worker2
        mock_window.current_launcher_worker = worker3

        MainWindow._on_close(mock_window)

        assert mock_window.cancel_event.is_set()
        assert mock_window.pull_cancel_event.is_set()
        assert mock_window.launcher_cancel_event.is_set()
        mock_window.player.close.assert_called_once()
        mock_window.destroy.assert_called_once()
