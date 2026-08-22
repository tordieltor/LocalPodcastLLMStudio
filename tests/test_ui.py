"""
LocalPodcastLLMStudio UI & Async Pipeline Tests (tests/test_ui.py)
==================================================================
Comprehensive headless unit and integration tests for CustomTkinter UI theming,
custom widgets (StatusBadge, LabeledSlider, TimeSlider, DialogueTurnCard, SectionHeader,
CardFrame, ActionableErrorDialog, AboutDialog), MainWindow grounding mode dropdown,
modality auto-synchronization, thread-safe queue event bus dispatching, and asynchronous
background worker threads (GenerationWorker, ModelPullWorker, OllamaLauncherWorker).
"""

import ctypes
import json
import queue
import sys
import threading
from typing import Any
from unittest.mock import MagicMock, call, patch

import customtkinter as ctk
import pytest

import ui.theme as theme
from core.extractor import DocumentExtractionError
from core.ollama import (
    ModelPullProgress,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)
from core.parser import DialogueTurn
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
from ui.widgets import (
    AboutDialog,
    ActionableErrorDialog,
    CardFrame,
    DialogueTurnCard,
    LabeledSlider,
    LiveStreamingCard,
    SectionHeader,
    StatusBadge,
    TimeSlider,
)


# ==============================================================================
# Fixtures for Headless Testing
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
def mock_main_window():
    """Creates a spec-mocked MainWindow instance with simulated widgets."""
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
    win.current_dialogue = []
    win._live_stream_card = None
    win._streaming_raw_text = ""
    win._streaming_chunks_count = 0
    win._rendered_turns_count = 0

    # Widgets
    win.status_label = MagicMock()
    win.progress_bar = MagicMock()
    win.progress_pct_label = MagicMock()
    win.speed_label = MagicMock()
    win.ollama_badge = MagicMock(spec=StatusBadge)
    win.btn_refresh_models = MagicMock()
    win.btn_logs = MagicMock()
    win.btn_about = MagicMock()
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
    win.highway_preset_label = MagicMock()
    win.nav_segmented = MagicMock()
    win.view_studio = MagicMock()
    win.view_script_studio = MagicMock()
    win.view_settings = MagicMock()
    win.view_about = MagicMock()
    win._update_highway_preset_label = MagicMock()

    # Delegate helper methods to real implementation
    win.get_selected_grounding_mode.side_effect = lambda: MainWindow.get_selected_grounding_mode(
        win
    )

    return win


# ==============================================================================
# 1. UI Theme & Styling Tests
# ==============================================================================
class TestUITheme:
    """Verifies color palette constants, typography helpers, and DWM integration."""

    def test_theme_colors_defined(self):
        # Surface & Backgrounds
        assert theme.COLOR_BG == "#1a1b26"
        assert theme.COLOR_CARD == "#24283b"
        assert theme.COLOR_CARD_HOVER == "#2f3549"
        assert theme.COLOR_CARD_BORDER == "#414868"
        assert theme.COLOR_INPUT_BG == "#16161e"
        assert theme.COLOR_INPUT_BORDER == "#414868"
        assert theme.COLOR_TOOLBAR == "#1f2335"

        # Accent & Action Colors
        assert theme.COLOR_ACCENT == "#7aa2f7"
        assert theme.COLOR_ACCENT_HOVER == "#565f89"
        assert theme.COLOR_ACCENT_ACTIVE == "#3d59a1"

        # Standard Button Colors
        assert theme.COLOR_BUTTON_SECONDARY == "#2b314a"
        assert theme.COLOR_BUTTON_SECONDARY_HOVER == "#3d4566"
        assert theme.COLOR_BUTTON_CLOSE == "#33384d"
        assert theme.COLOR_BUTTON_CLOSE_HOVER == "#414868"
        assert theme.COLOR_BUTTON_SUCCESS == "#9ece6a"
        assert theme.COLOR_BUTTON_SUCCESS_HOVER == "#7fb84e"
        assert theme.COLOR_BUTTON_DANGER == "#f7768e"
        assert theme.COLOR_BUTTON_DANGER_HOVER == "#db4b4b"

        # State Indicators
        assert theme.COLOR_SUCCESS == "#9ece6a"
        assert theme.COLOR_WARNING == "#ff9e64"
        assert theme.COLOR_ERROR == "#f7768e"
        assert theme.COLOR_INFO == "#7dcfff"

        # Progress Bar & Badges
        assert theme.COLOR_PROGRESS_BG == "#1a1c29"
        assert theme.COLOR_PROGRESS_TRACK == "#24283b"
        assert theme.COLOR_PROGRESS_FILL == "#7aa2f7"
        assert theme.COLOR_BADGE_BG == "#1f2335"

        # Text Colors
        assert theme.COLOR_TEXT_PRIMARY == "#c0caf5"
        assert theme.COLOR_TEXT_SECONDARY == "#7982a9"
        assert theme.COLOR_TEXT_MUTED == "#565f89"
        assert theme.COLOR_TEXT_DARK == "#15161e"

        # Persona Colors
        assert theme.COLOR_HOST1 == "#7aa2f7"
        assert theme.COLOR_HOST1_BG == "#1f2744"
        assert theme.COLOR_HOST2 == "#9ece6a"
        assert theme.COLOR_HOST2_BG == "#1d2b27"

    def test_theme_dimensions_and_radii(self):
        assert theme.APP_TITLE == "LocalPodcastLLMStudio - 100% Local AI Podcast Generator"
        assert theme.DEFAULT_WINDOW_SIZE == "1200x860"
        assert theme.MIN_WINDOW_WIDTH == 1080
        assert theme.MIN_WINDOW_HEIGHT == 740
        assert theme.CARD_RADIUS == 12
        assert theme.BUTTON_RADIUS == 8
        assert theme.INPUT_RADIUS == 6
        assert theme.BADGE_RADIUS == 14
        assert theme.PADDING_XS == 4
        assert theme.PADDING_SM == 8
        assert theme.PADDING_MD == 14
        assert theme.PADDING_LG == 20

    def test_typography_helpers_instantiation(self):
        try:
            assert theme.get_font_title() is not None
            assert theme.get_font_subtitle() is not None
            assert theme.get_font_heading() is not None
            assert theme.get_font_subheading() is not None
            assert theme.get_font_body() is not None
            assert theme.get_font_body_bold() is not None
            assert theme.get_font_caption() is not None
            assert theme.get_font_caption_bold() is not None
            assert theme.get_font_badge() is not None
            assert theme.get_font_code() is not None
            assert theme.get_font_code_small() is not None
        except Exception:
            with patch("customtkinter.CTkFont", return_value=MagicMock()):
                assert theme.get_font_title() is not None
                assert theme.get_font_subtitle() is not None
                assert theme.get_font_heading() is not None
                assert theme.get_font_subheading() is not None
                assert theme.get_font_body() is not None
                assert theme.get_font_body_bold() is not None
                assert theme.get_font_caption() is not None
                assert theme.get_font_caption_bold() is not None
                assert theme.get_font_badge() is not None
                assert theme.get_font_code() is not None
                assert theme.get_font_code_small() is not None

    def test_enable_windows_dark_titlebar_platforms(self):
        mock_win = MagicMock()
        mock_win.winfo_id.return_value = 12345

        # 1. Non-Windows platform returns False
        with patch("sys.platform", "linux"):
            assert theme.enable_windows_dark_titlebar(mock_win) is False

        # 2. Windows platform with successful primary attribute (20)
        mock_windll_success = MagicMock()
        mock_windll_success.user32.GetParent.return_value = 12345
        mock_windll_success.dwmapi.DwmSetWindowAttribute.return_value = 0

        with (
            patch("sys.platform", "win32"),
            patch.object(ctypes, "windll", mock_windll_success, create=True),
        ):
            res = theme.enable_windows_dark_titlebar(mock_win)
            assert res is True
            assert mock_windll_success.dwmapi.DwmSetWindowAttribute.call_count >= 1

        # 3. Windows platform fallback attribute (19)
        mock_windll_fallback = MagicMock()
        mock_windll_fallback.user32.GetParent.return_value = 12345
        mock_windll_fallback.dwmapi.DwmSetWindowAttribute.side_effect = [-1, 0]

        with (
            patch("sys.platform", "win32"),
            patch.object(ctypes, "windll", mock_windll_fallback, create=True),
        ):
            res = theme.enable_windows_dark_titlebar(mock_win)
            assert res is True

        # 4. Windows platform error/exception handling
        mock_windll_error = MagicMock()
        mock_windll_error.user32.GetParent.return_value = 12345
        mock_windll_error.dwmapi.DwmSetWindowAttribute.side_effect = OSError("DWM Error")

        with (
            patch("sys.platform", "win32"),
            patch.object(ctypes, "windll", mock_windll_error, create=True),
        ):
            res = theme.enable_windows_dark_titlebar(mock_win)
            assert res is False


# ==============================================================================
# 2. StatusBadge State & Dot Color Tests
# ==============================================================================
class TestStatusBadge:
    """Verifies StatusBadge visual states, dot colors, glyph overrides, and case insensitivity."""

    @pytest.mark.parametrize(
        "status,expected_color",
        [
            ("online", theme.COLOR_SUCCESS),
            ("connected", theme.COLOR_SUCCESS),
            ("ready", theme.COLOR_SUCCESS),
            ("success", theme.COLOR_SUCCESS),
            ("done", theme.COLOR_SUCCESS),
            ("complete", theme.COLOR_SUCCESS),
            ("offline", theme.COLOR_ERROR),
            ("error", theme.COLOR_ERROR),
            ("cancelled", theme.COLOR_ERROR),
            ("failed", theme.COLOR_ERROR),
            ("stopped", theme.COLOR_ERROR),
            ("aborted", theme.COLOR_ERROR),
            ("checking", theme.COLOR_WARNING),
            ("busy", theme.COLOR_WARNING),
            ("working", theme.COLOR_WARNING),
            ("warning", theme.COLOR_WARNING),
            ("starting", theme.COLOR_WARNING),
            ("launching", theme.COLOR_WARNING),
            ("booting", theme.COLOR_WARNING),
            ("missing_model", theme.COLOR_WARNING),
            ("no_models", theme.COLOR_WARNING),
            ("degraded", theme.COLOR_WARNING),
            ("partial", theme.COLOR_WARNING),
            ("downloading", theme.COLOR_INFO),
            ("pulling", theme.COLOR_INFO),
            ("installing", theme.COLOR_INFO),
            ("syncing", theme.COLOR_INFO),
            ("info", theme.COLOR_INFO),
            ("idle", theme.COLOR_INFO),
            ("unknown_fallback_state", theme.COLOR_INFO),
        ],
    )
    def test_status_badge_color_mapping(self, status, expected_color):
        badge = MagicMock(spec=StatusBadge)
        badge.dot_label = MagicMock()
        badge.text_label = MagicMock()

        StatusBadge.set_status(badge, status, f"State: {status}")

        badge.dot_label.configure.assert_called_once_with(text="●", text_color=expected_color)
        badge.text_label.configure.assert_called_once_with(text=f"State: {status}")

    def test_status_badge_case_insensitivity(self):
        badge = MagicMock(spec=StatusBadge)
        badge.dot_label = MagicMock()
        badge.text_label = MagicMock()

        StatusBadge.set_status(badge, "ONLINE", "All Systems Operational")
        badge.dot_label.configure.assert_called_once_with(text="●", text_color=theme.COLOR_SUCCESS)

        badge.dot_label.reset_mock()
        StatusBadge.set_status(badge, "Offline", "Service Unreachable")
        badge.dot_label.configure.assert_called_once_with(text="●", text_color=theme.COLOR_ERROR)

        badge.dot_label.reset_mock()
        StatusBadge.set_status(badge, "DoWnLoAdInG", "Fetching layer...")
        badge.dot_label.configure.assert_called_once_with(text="●", text_color=theme.COLOR_INFO)

    def test_status_badge_dot_color_and_glyph_overrides(self):
        badge = MagicMock(spec=StatusBadge)
        badge.dot_label = MagicMock()
        badge.text_label = MagicMock()

        # Custom dot color and glyph override
        StatusBadge.set_status(
            badge,
            status="online",
            text="Custom Color Test",
            dot_color="#123456",
            dot_glyph="⚡",
        )
        badge.dot_label.configure.assert_called_once_with(text="⚡", text_color="#123456")
        badge.text_label.configure.assert_called_once_with(text="Custom Color Test")


# ==============================================================================
# 3. ActionableErrorDialog & Reusable Widgets Tests
# ==============================================================================
class TestActionableErrorDialog:
    """Verifies ActionableErrorDialog backwards compatibility, multi-action buttons, and dialog types."""

    def test_single_action_backward_compatibility(self):
        cb = MagicMock()
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
            patch("customtkinter.CTkButton") as mock_btn,
        ):
            dialog = ActionableErrorDialog(
                parent=MagicMock(),
                title="Connection Failed",
                message="Cannot connect to Ollama",
                action_button_text="Retry Connection",
                action_callback=cb,
            )
            assert dialog is not None
            assert mock_btn.call_count >= 2  # Action button + Close button

    def test_multi_action_buttons_tuples(self):
        start_cb = MagicMock()
        pull_cb = MagicMock()
        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry"),
            patch("customtkinter.CTkToplevel.minsize"),
            patch("customtkinter.CTkToplevel.configure"),
            patch("customtkinter.CTkToplevel.transient"),
            patch("customtkinter.CTkToplevel.grab_set"),
            patch("customtkinter.CTkToplevel.destroy") as mock_destroy,
            patch("ui.widgets.get_font_heading", return_value=MagicMock()),
            patch("ui.widgets.get_font_body", return_value=MagicMock()),
            patch("ui.widgets.get_font_body_bold", return_value=MagicMock()),
            patch("ui.widgets.get_font_code", return_value=MagicMock()),
            patch("customtkinter.CTkFrame"),
            patch("customtkinter.CTkLabel"),
            patch("customtkinter.CTkTextbox"),
            patch("customtkinter.CTkButton") as mock_btn,
        ):
            created_buttons = []

            def fake_button(*args, **kwargs):
                btn = MagicMock()
                btn.command = kwargs.get("command")
                created_buttons.append(btn)
                return btn

            mock_btn.side_effect = fake_button

            dialog = ActionableErrorDialog(
                parent=MagicMock(),
                title="Prerequisites Incomplete",
                message="Ollama is offline and model is missing.",
                actions=[
                    ("Start Ollama", start_cb, "success", True),
                    ("Download llama3.1:8b", pull_cb, "accent", False),
                ],
                remedy="Check Windows service status.",
                dialog_type="prerequisite",
            )
            assert dialog is not None
            assert len(created_buttons) >= 2

            # Trigger action 1 (dismiss=True)
            created_buttons[0].command()
            mock_destroy.assert_called_once()
            start_cb.assert_called_once()

            # Trigger action 2 (dismiss=False)
            mock_destroy.reset_mock()
            created_buttons[1].command()
            mock_destroy.assert_not_called()
            pull_cb.assert_called_once()

    def test_multi_action_buttons_dicts(self):
        cb1 = MagicMock()
        cb2 = MagicMock()
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
                title="Warning Event",
                message="Disk space low.",
                actions=[
                    {"text": "Clean Temp", "callback": cb1, "style": "warning", "dismiss": True},
                    {"text": "Abort Task", "callback": cb2, "style": "danger", "dismiss": True},
                ],
                dialog_type="warning",
            )
            assert dialog is not None

    def test_dialog_types_and_icons(self):
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
            d_err = ActionableErrorDialog(
                parent=MagicMock(), title="E", message="M", dialog_type="error"
            )
            d_warn = ActionableErrorDialog(
                parent=MagicMock(), title="W", message="M", dialog_type="warning"
            )
            d_info = ActionableErrorDialog(
                parent=MagicMock(), title="I", message="M", dialog_type="info"
            )
            d_prereq = ActionableErrorDialog(
                parent=MagicMock(),
                title="P",
                message="M",
                dialog_type="prerequisite",
                icon="🚀",
            )
            assert d_err is not None
            assert d_warn is not None
            assert d_info is not None
            assert d_prereq is not None

    def test_center_on_parent_and_fallback(self):
        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry") as mock_geom,
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
            # Normal parent geometry
            parent = MagicMock()
            parent.winfo_width.return_value = 1200
            parent.winfo_height.return_value = 800
            parent.winfo_rootx.return_value = 100
            parent.winfo_rooty.return_value = 100

            dialog = ActionableErrorDialog(parent=parent, title="T", message="M")
            assert dialog is not None
            mock_geom.assert_called()

            # Exception fallback parent
            parent_broken = MagicMock()
            parent_broken.update_idletasks.side_effect = RuntimeError("No window")
            dialog_fallback = ActionableErrorDialog(parent=parent_broken, title="T", message="M")
            assert dialog_fallback is not None


class TestOtherUIWidgets:
    """Verifies TimeSlider, LabeledSlider, SectionHeader, CardFrame, DialogueTurnCard, and AboutDialog."""

    def test_time_slider_format_ms(self):
        assert TimeSlider._format_ms(0) == "00:00"
        assert TimeSlider._format_ms(65000) == "01:05"
        assert TimeSlider._format_ms(3600000) == "60:00"
        assert TimeSlider._format_ms(3665000) == "61:05"

    def test_time_slider_update_position(self):
        slider_frame = MagicMock(spec=TimeSlider)
        slider_frame._format_ms = TimeSlider._format_ms
        slider_frame.time_label = MagicMock()
        slider_frame.status_mini = MagicMock()
        slider_frame.slider = MagicMock()
        slider_frame.is_user_dragging = False

        TimeSlider.update_position(slider_frame, 30000, 60000, "Playing")
        slider_frame.status_mini.configure.assert_called_once_with(text="Playing")
        slider_frame.time_label.configure.assert_called_once_with(text="00:30 / 01:00")
        slider_frame.slider.set.assert_called_once_with(50.0)

    def test_labeled_slider_format_and_commands(self):
        cb = MagicMock()
        slider = MagicMock(spec=LabeledSlider)
        slider.format_fn = lambda v: f"{int(v):+d}%"
        slider.user_command = cb
        slider.val_label = MagicMock()
        slider.slider = MagicMock()
        slider.slider.get.return_value = 5.0

        LabeledSlider._on_slider_moved(slider, 5.0)
        slider.val_label.configure.assert_called_once_with(text="+5%")
        cb.assert_called_once_with(5.0)

        assert LabeledSlider.get(slider) == 5.0

        slider.val_label.reset_mock()
        LabeledSlider.set(slider, 10.0)
        slider.slider.set.assert_called_once_with(10.0)
        slider.val_label.configure.assert_called_once_with(text="+10%")

    def test_card_frame_and_section_header_headless(self):
        with (
            patch("customtkinter.CTkFrame.__init__", return_value=None),
            patch("customtkinter.CTkFrame.grid_columnconfigure"),
            patch("ui.widgets.get_font_heading", return_value=MagicMock()),
            patch("ui.widgets.get_font_caption", return_value=MagicMock()),
            patch("customtkinter.CTkLabel") as mock_lbl,
        ):
            card = CardFrame(master=MagicMock())
            assert card is not None

            header = SectionHeader(
                master=MagicMock(),
                title="Test Section",
                subtitle="Test Subtitle",
                icon="🎙️",
            )
            assert header is not None
            assert mock_lbl.call_count >= 2

    def test_dialogue_turn_card_host_styling(self):
        with (
            patch("customtkinter.CTkFrame.__init__", return_value=None) as mock_frame_init,
            patch("customtkinter.CTkFrame.pack"),
            patch("ui.widgets.get_font_body_bold", return_value=MagicMock()),
            patch("ui.widgets.get_font_caption", return_value=MagicMock()),
            patch("ui.widgets.get_font_body", return_value=MagicMock()),
            patch("customtkinter.CTkLabel"),
        ):
            # Host 1 styling
            DialogueTurnCard(
                master=MagicMock(), turn_number=1, speaker="Host 1 (Kari)", text="Hei!"
            )
            assert mock_frame_init.call_args_list[0][1]["fg_color"] == theme.COLOR_HOST1_BG

            # Host 2 styling
            DialogueTurnCard(master=MagicMock(), turn_number=2, speaker="Host 2 (Ola)", text="Hei!")
            assert mock_frame_init.call_args_list[2][1]["fg_color"] == theme.COLOR_HOST2_BG

    def test_about_dialog_instantiation(self):
        with (
            patch("customtkinter.CTkToplevel.__init__", return_value=None),
            patch("customtkinter.CTkToplevel.title"),
            patch("customtkinter.CTkToplevel.geometry"),
            patch("customtkinter.CTkToplevel.minsize"),
            patch("customtkinter.CTkToplevel.configure"),
            patch("customtkinter.CTkToplevel.transient"),
            patch("customtkinter.CTkToplevel.grab_set"),
            patch("ui.about_dialog.get_font_title", return_value=MagicMock()),
            patch("ui.about_dialog.get_font_heading", return_value=MagicMock()),
            patch("ui.about_dialog.get_font_body", return_value=MagicMock()),
            patch("ui.about_dialog.get_font_body_bold", return_value=MagicMock()),
            patch("ui.about_dialog.get_font_caption", return_value=MagicMock()),
            patch("customtkinter.CTkLabel"),
            patch("customtkinter.CTkButton"),
            patch("customtkinter.CTkFrame"),
            patch("customtkinter.CTkScrollableFrame"),
            patch("customtkinter.CTkTabview"),
        ):
            dialog = AboutDialog(parent=MagicMock())
            assert dialog is not None

    def test_live_streaming_card_widget(self):
        with (
            patch("customtkinter.CTkFrame.__init__", return_value=None),
            patch("customtkinter.CTkFrame.pack"),
            patch("customtkinter.CTkLabel") as mock_label,
            patch("customtkinter.CTkTextbox") as mock_textbox,
            patch("ui.widgets.get_font_body_bold", return_value=MagicMock()),
            patch("ui.widgets.get_font_caption", return_value=MagicMock()),
            patch("ui.widgets.get_font_code", return_value=MagicMock()),
        ):
            mock_box_inst = MagicMock()
            mock_textbox.return_value = mock_box_inst

            mock_title = MagicMock()
            mock_token = MagicMock()
            mock_label.side_effect = [mock_title, mock_token]

            card = LiveStreamingCard(master=MagicMock(), title="Writing Act 1/2...")
            assert card is not None
            assert card.token_count == 0
            assert card.get_text() == ""

            # Test appending chunks
            card.append_chunk("Hei ")
            card.append_chunk("verden!")
            assert card.get_text() == "Hei verden!"
            assert card.token_count == 2
            mock_box_inst.insert.assert_called_with("end", "verden!")
            mock_box_inst.see.assert_called_with("end")

            # Test set status
            card.set_status("Writing Act 2/2...")
            mock_title.configure.assert_called_with(text="⚡ Writing Act 2/2...")

            # Test reset
            card.reset("Starting over...")
            assert card.token_count == 0
            assert card.get_text() == ""
            mock_title.configure.assert_called_with(text="⚡ Starting over...")
            mock_token.configure.assert_called_with(text="0 chunks")


# ==============================================================================
# 4. MainWindow Grounding Mode & Modality Synchronization Tests
# ==============================================================================
class TestMainWindowGroundingMode:
    """Verifies Grounding Mode UI dropdown, preset descriptions, and modality auto-sync."""

    def test_grounding_mode_presets_contract(self):
        assert "strict" in GROUNDING_MODE_PRESETS
        assert "creative" in GROUNDING_MODE_PRESETS
        assert "open_topic" in GROUNDING_MODE_PRESETS

        assert GroundingMode.STRICT == "strict"
        assert GroundingMode.CREATIVE == "creative"
        assert GroundingMode.OPEN_TOPIC == "open_topic"

    def test_grounding_ui_options_definition(self):
        assert len(GROUNDING_UI_OPTIONS) == 3
        assert "Strict Source-Only" in GROUNDING_UI_OPTIONS[0]
        assert "Creative Analogy" in GROUNDING_UI_OPTIONS[1]
        assert "Open Topic" in GROUNDING_UI_OPTIONS[2]

    def test_get_selected_grounding_mode(self, mock_main_window):
        # 1. Strict
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[0]
        mode = MainWindow.get_selected_grounding_mode(mock_main_window)
        assert mode == "strict"

        # 2. Creative
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[1]
        mode = MainWindow.get_selected_grounding_mode(mock_main_window)
        assert mode == "creative"

        # 3. Open Topic
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[2]
        mode = MainWindow.get_selected_grounding_mode(mock_main_window)
        assert mode == "open_topic"

    def test_update_grounding_description_bilingual(self, mock_main_window):
        # Norwegian Bokmål + Creative
        mock_main_window.lang_menu.get.return_value = "Norwegian Bokmål (Kari & Ola)"
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[1]
        MainWindow._update_grounding_description(mock_main_window)

        call_kwargs = mock_main_window.grounding_desc_label.configure.call_args[1]
        assert "text" in call_kwargs
        text_nb = call_kwargs["text"].lower()
        assert "forankrer" in text_nb or "kreative" in text_nb or "analogier" in text_nb

        # English + Strict
        mock_main_window.lang_menu.get.return_value = "English (Jenny & Guy)"
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[0]
        MainWindow._update_grounding_description(mock_main_window)

        call_kwargs_en = mock_main_window.grounding_desc_label.configure.call_args[1]
        text_en = call_kwargs_en["text"].lower()
        assert "source" in text_en or "strict" in text_en or "hallucinations" in text_en

    def test_on_grounding_and_language_changed_callbacks(self, mock_main_window):
        MainWindow._on_grounding_mode_changed(mock_main_window, GROUNDING_UI_OPTIONS[1])
        mock_main_window._update_grounding_description.assert_called_once()

        mock_main_window._update_grounding_description.reset_mock()
        MainWindow._on_language_changed(mock_main_window, "English")
        mock_main_window._update_grounding_description.assert_called_once()

    def test_modality_changed_auto_syncs_grounding_mode(self, mock_main_window):
        # 1. Switching to Topic Prompt -> auto switches to Open Topic
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[0]
        MainWindow._on_modality_changed(mock_main_window, "Topic Prompt (Scratch)")
        mock_main_window.input_modality_var.set.assert_called_with("topic")
        mock_main_window.grounding_menu.set.assert_called_with(GROUNDING_UI_OPTIONS[2])
        mock_main_window.file_container.pack_forget.assert_called()
        mock_main_window.text_container.pack.assert_called()
        mock_main_window._update_grounding_description.assert_called()

        # 2. Switching to Document File from open_topic -> auto switches to Strict
        mock_main_window._update_grounding_description.reset_mock()
        mock_main_window.grounding_menu.reset_mock()
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[2]
        MainWindow._on_modality_changed(mock_main_window, "Document (.txt/.md/.pdf)")
        mock_main_window.input_modality_var.set.assert_called_with("file")
        mock_main_window.grounding_menu.set.assert_called_with(GROUNDING_UI_OPTIONS[0])
        mock_main_window.text_container.pack_forget.assert_called()
        mock_main_window.file_container.pack.assert_called()
        mock_main_window._update_grounding_description.assert_called()

        # 3. Switching to Pasted Text from open_topic -> auto switches to Strict
        mock_main_window._update_grounding_description.reset_mock()
        mock_main_window.grounding_menu.reset_mock()
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[2]
        MainWindow._on_modality_changed(mock_main_window, "Pasted Text")
        mock_main_window.input_modality_var.set.assert_called_with("text")
        mock_main_window.grounding_menu.set.assert_called_with(GROUNDING_UI_OPTIONS[0])
        mock_main_window.file_container.pack_forget.assert_called()
        mock_main_window.text_container.pack.assert_called()
        mock_main_window._update_grounding_description.assert_called()


# ==============================================================================
# 5. MainWindow Queue Event Bus & Poller Tests
# ==============================================================================
class TestMainWindowQueueEventHandling:
    """Verifies MainWindow._handle_event and _process_queue message handling."""

    def test_handle_status_and_progress_events(self, mock_main_window):
        # STATUS
        MainWindow._handle_event(mock_main_window, "STATUS", "Ingesting document...")
        mock_main_window.status_label.configure.assert_called_with(text="Ingesting document...")

        # PROGRESS
        MainWindow._handle_event(mock_main_window, "PROGRESS", 0.45)
        mock_main_window.progress_bar.set.assert_called_with(0.45)
        mock_main_window.progress_pct_label.configure.assert_called_with(text="45%")

    def test_handle_script_ready_and_done_events(self, mock_main_window):
        turns = [DialogueTurn(speaker="Host 1", text="Hello")]

        MainWindow._handle_event(mock_main_window, "SCRIPT_READY", turns)
        mock_main_window._render_transcript.assert_called_once_with(turns)

        MainWindow._handle_event(mock_main_window, "GENERATION_DONE", {"mp3_path": "/out.mp3"})
        mock_main_window._on_generation_done.assert_called_once_with({"mp3_path": "/out.mp3"})

        MainWindow._handle_event(mock_main_window, "SCRIPT_ONLY_DONE", {"script_path": "/out.json"})
        mock_main_window._on_script_only_done.assert_called_once_with({"script_path": "/out.json"})

    def test_handle_stream_chunk_and_act_done_events(self, mock_main_window):
        # STREAM_CHUNK
        MainWindow._handle_event(mock_main_window, "STREAM_CHUNK", "Hei på deg")
        mock_main_window._handle_stream_chunk.assert_called_once_with("Hei på deg")

        # ACT_DONE
        act_data = {
            "act_idx": 1,
            "total_acts": 2,
            "turns": [DialogueTurn(speaker="Host 1", text="Hei")],
        }
        MainWindow._handle_event(mock_main_window, "ACT_DONE", act_data)
        mock_main_window._handle_act_done.assert_called_once_with(act_data)

    def test_handle_ollama_service_events(self, mock_main_window):
        # SERVICE_LAUNCHING
        MainWindow._handle_event(
            mock_main_window, "SERVICE_LAUNCHING", {"status": "Starting daemon..."}
        )
        mock_main_window.ollama_badge.set_status.assert_called_with(
            "starting", "Starting Ollama..."
        )
        mock_main_window.status_label.configure.assert_called_with(text="Starting daemon...")
        mock_main_window.btn_start_ollama_header.configure.assert_called_with(state="disabled")

        # SERVICE_STARTED with models
        MainWindow._handle_event(
            mock_main_window,
            "SERVICE_STARTED",
            {"status": "Ready", "models": ["llama3.1:8b"]},
        )
        mock_main_window.status_label.configure.assert_called_with(text="Ready")
        mock_main_window._handle_ollama_status.assert_called_once_with(
            {"connected": True, "models": ["llama3.1:8b"]}
        )

        # SERVICE_STARTED without models
        MainWindow._handle_event(
            mock_main_window, "SERVICE_STARTED", {"status": "Ready", "models": []}
        )
        mock_main_window.refresh_ollama_models.assert_called_once()

        # SERVICE_ERROR
        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            MainWindow._handle_event(
                mock_main_window,
                "SERVICE_ERROR",
                {"error": "Port in use", "details": "Check port 11434"},
            )
            mock_main_window.ollama_badge.set_status.assert_called_with("offline", "Ollama Offline")
            mock_main_window.btn_start_ollama_header.configure.assert_called_with(state="normal")
            mock_dialog.assert_called_once()

    def test_handle_pull_progress_event(self, mock_main_window):
        progress = ModelPullProgress(
            status="downloading layer",
            total=4000000000,
            completed=2000000000,
            percentage=0.50,
            speed_str="15.4 MB/s",
            progress_str="2.00 GB / 4.00 GB (50.0%)",
            eta_str="02:10",
        )

        MainWindow._handle_event(mock_main_window, "PULL_PROGRESS", progress)

        mock_main_window.pull_progress_bar.set.assert_called_with(0.50)
        mock_main_window.pull_status_label.configure.assert_called_with(
            text="Pulling downloading layer (50%)"
        )
        mock_main_window.pull_speed_label.configure.assert_called_with(
            text="15.4 MB/s | ETA: 02:10"
        )
        mock_main_window.pull_details_label.configure.assert_called_with(
            text="2.00 GB / 4.00 GB (50.0%)"
        )
        mock_main_window.ollama_badge.set_status.assert_called_with("downloading", "Pulling (50%)")

    def test_handle_pull_done_and_error_and_cancel_events(self, mock_main_window):
        # PULL_DONE
        MainWindow._handle_event(
            mock_main_window,
            "PULL_DONE",
            {"model": "llama3.1:8b", "message": "Model ready"},
        )
        mock_main_window.pull_frame.pack_forget.assert_called_once()
        mock_main_window.ollama_badge.set_status.assert_called_with(
            "online", "Model Ready: llama3.1:8b"
        )
        mock_main_window.status_label.configure.assert_called_with(text="Model ready")
        mock_main_window.refresh_ollama_models.assert_called_once()

        # PULL_ERROR
        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            MainWindow._handle_event(
                mock_main_window,
                "PULL_ERROR",
                {"model": "llama3.1:8b", "error": "Disk full"},
            )
            mock_main_window.pull_frame.pack_forget.assert_called()
            mock_main_window.ollama_badge.set_status.assert_called_with("error", "Download Failed")
            mock_dialog.assert_called_once()

        # PULL_CANCELLED
        mock_main_window.refresh_ollama_models.reset_mock()
        MainWindow._handle_event(mock_main_window, "PULL_CANCELLED", {"model": "llama3.1:8b"})
        mock_main_window.pull_frame.pack_forget.assert_called()
        mock_main_window.status_label.configure.assert_called_with(text="Model download cancelled.")
        mock_main_window.refresh_ollama_models.assert_called_once()

    def test_handle_cancelled_and_error_events(self, mock_main_window):
        # CANCELLED
        MainWindow._handle_event(mock_main_window, "CANCELLED", "Aborted by user.")
        mock_main_window._set_busy_state.assert_called_with(False)
        mock_main_window.status_label.configure.assert_called_with(text="Aborted by user.")
        mock_main_window.progress_bar.set.assert_called_with(0.0)

        # ERROR (Dict)
        mock_main_window._set_busy_state.reset_mock()
        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            MainWindow._handle_event(
                mock_main_window,
                "ERROR",
                {
                    "title": "Synthesis Error",
                    "message": "Edge-TTS timeout",
                    "details": "Connection dropped",
                },
            )
            mock_main_window._set_busy_state.assert_called_with(False)
            mock_dialog.assert_called_once()

        # ERROR (String fallback)
        mock_main_window._set_busy_state.reset_mock()
        with patch("tkinter.messagebox.showerror") as mock_mb:
            MainWindow._handle_event(mock_main_window, "ERROR", "Generic failure string")
            mock_main_window._set_busy_state.assert_called_with(False)
            mock_mb.assert_called_once_with("Error", "Generic failure string")

    def test_process_queue_dispatches_fifo(self, mock_main_window):
        mock_main_window.msg_queue.put(("STATUS", "Step 1"))
        mock_main_window.msg_queue.put(("PROGRESS", 0.25))
        mock_main_window.msg_queue.put(("STATUS", "Step 2"))

        MainWindow._process_queue(mock_main_window)
        assert mock_main_window._handle_event.call_count == 3
        mock_main_window._handle_event.assert_has_calls(
            [
                call("STATUS", "Step 1"),
                call("PROGRESS", 0.25),
                call("STATUS", "Step 2"),
            ]
        )
        assert mock_main_window.msg_queue.empty()


# ==============================================================================
# 6. Background Workers Async Protocol Tests
# ==============================================================================
class TestBackgroundWorkersAsyncProtocol:
    """Verifies non-blocking background worker threads communicate exclusively via msg_queue."""

    # --- ModelPullWorker Tests ---
    @patch("ui.main_window.pull_model_stream")
    def test_model_pull_worker_success(self, mock_pull_stream):
        def fake_pull(model, base_url, progress_callback, cancel_event, timeout):
            prog = ModelPullProgress(status="pulling manifest", percentage=0.1)
            progress_callback(prog)
            return True

        mock_pull_stream.side_effect = fake_pull

        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = ModelPullWorker(
            model_name="llama3.1:8b",
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )
        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "PULL_PROGRESS" in event_types
        assert "PULL_DONE" in event_types

        done_event = next(ev for ev in events if ev[0] == "PULL_DONE")
        assert done_event[1]["model"] == "llama3.1:8b"

    @patch("ui.main_window.pull_model_stream", side_effect=RuntimeError("Download aborted by peer"))
    def test_model_pull_worker_error(self, mock_pull_stream):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = ModelPullWorker(
            model_name="llama3.1:8b",
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )
        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "PULL_ERROR" in event_types
        err_event = next(ev for ev in events if ev[0] == "PULL_ERROR")
        assert "Download aborted" in err_event[1]["error"]

    @patch("ui.main_window.pull_model_stream", side_effect=RuntimeError("Cancelled"))
    def test_model_pull_worker_cancellation(self, mock_pull_stream):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()
        cancel_event.set()

        worker = ModelPullWorker(
            model_name="llama3.1:8b",
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )
        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "PULL_CANCELLED" in event_types

    # --- OllamaLauncherWorker Tests ---
    @patch("ui.main_window.OllamaClient")
    @patch(
        "ui.main_window.start_ollama_service",
        return_value=(True, "Ollama service started successfully."),
    )
    def test_ollama_launcher_worker_success(self, mock_start, mock_client_cls):
        mock_client = MagicMock()
        mock_client.list_models.return_value = ["llama3.1:8b", "qwen2.5:7b"]
        mock_client_cls.return_value = mock_client

        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = OllamaLauncherWorker(msg_queue=msg_queue, cancel_event=cancel_event)
        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "SERVICE_LAUNCHING" in event_types
        assert "SERVICE_STARTED" in event_types

        started_ev = next(ev for ev in events if ev[0] == "SERVICE_STARTED")
        assert started_ev[1]["models"] == ["llama3.1:8b", "qwen2.5:7b"]

    @patch("ui.main_window.start_ollama_service", return_value=(False, "ollama.exe not found"))
    def test_ollama_launcher_worker_failure(self, mock_start):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = OllamaLauncherWorker(msg_queue=msg_queue, cancel_event=cancel_event)
        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "SERVICE_LAUNCHING" in event_types
        assert "SERVICE_ERROR" in event_types

    @patch("ui.main_window.start_ollama_service", side_effect=Exception("Permission denied"))
    def test_ollama_launcher_worker_exception(self, mock_start):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = OllamaLauncherWorker(msg_queue=msg_queue, cancel_event=cancel_event)
        worker.run()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_types = [ev[0] for ev in events]
        assert "SERVICE_ERROR" in event_types

    # --- GenerationWorker Tests ---
    @patch("ui.main_window.generate_podcast_script")
    @patch("ui.main_window.synthesize_dialogue_audio")
    @patch("ui.main_window.stitch_mp3_files")
    def test_generation_worker_grounding_mode_propagation(
        self, mock_stitch, mock_synth, mock_gen_script, tmp_path
    ):
        mock_gen_script.return_value = [
            DialogueTurn(speaker="Host 1", text="Topic analysis"),
            DialogueTurn(speaker="Host 2", text="Deep dive"),
        ]
        mock_synth.return_value = ["/tmp/t1.mp3", "/tmp/t2.mp3"]
        mock_stitch.return_value = str(tmp_path / "out.mp3")

        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Document content for testing grounding propagation",
            language="en-US",
            model="llama3.1:8b",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_event,
            grounding_mode="creative",
        )
        worker.run()

        mock_gen_script.assert_called_once()
        kwargs = mock_gen_script.call_args[1]
        assert kwargs.get("grounding_mode") == "creative"

    @patch(
        "ui.main_window.extract_text",
        side_effect=DocumentExtractionError("Encrypted PDF"),
    )
    def test_generation_worker_extraction_error(self, mock_extract, tmp_path):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="file",
            input_data="encrypted.pdf",
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

        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        err_event = next(ev for ev in events if ev[0] == "ERROR")
        assert "Document Extraction Error" in err_event[1]["title"]

    @patch(
        "ui.main_window.generate_podcast_script",
        side_effect=OllamaConnectionError("Connection refused"),
    )
    def test_generation_worker_ollama_connection_error(self, mock_gen, tmp_path):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Sample document content text",
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

        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        err_event = next(ev for ev in events if ev[0] == "ERROR")
        assert "Ollama Connection Error" in err_event[1]["title"]

    @patch(
        "ui.main_window.generate_podcast_script",
        side_effect=OllamaModelNotFoundError("Model not found"),
    )
    def test_generation_worker_ollama_model_missing(self, mock_gen, tmp_path):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Sample document content text",
            language="en-US",
            model="missing_model:latest",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_event,
        )
        worker.run()

        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        err_event = next(ev for ev in events if ev[0] == "ERROR")
        assert "Ollama Model Missing" in err_event[1]["title"]

    @patch("ui.main_window.generate_podcast_script", return_value=[])
    def test_generation_worker_empty_dialogue_error(self, mock_gen, tmp_path):
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Sample document content text",
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

        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        err_event = next(ev for ev in events if ev[0] == "ERROR")
        assert "Script Parsing Failed" in err_event[1]["title"]

    @patch("ui.main_window.generate_podcast_script")
    @patch(
        "ui.main_window.synthesize_dialogue_audio",
        side_effect=Exception("Edge-TTS connection failed"),
    )
    def test_generation_worker_tts_synthesis_error(self, mock_synth, mock_gen, tmp_path):
        mock_gen.return_value = [
            DialogueTurn(speaker="Host 1", text="Turn 1"),
            DialogueTurn(speaker="Host 2", text="Turn 2"),
        ]
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Sample document content text",
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

        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        err_event = next(ev for ev in events if ev[0] == "ERROR")
        assert "Voice Synthesis Error" in err_event[1]["title"]

    @patch("ui.main_window.generate_podcast_script")
    @patch("ui.main_window.synthesize_dialogue_audio", return_value=["/tmp/t1.mp3"])
    @patch("ui.main_window.stitch_mp3_files", side_effect=Exception("Disk write denied"))
    def test_generation_worker_mp3_stitch_error(self, mock_stitch, mock_synth, mock_gen, tmp_path):
        mock_gen.return_value = [DialogueTurn(speaker="Host 1", text="Turn 1")]
        msg_queue: queue.Queue[Any] = queue.Queue()
        cancel_event = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="text",
            input_data="Sample document content text",
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

        events = [msg_queue.get_nowait() for _ in range(msg_queue.qsize())]
        err_event = next(ev for ev in events if ev[0] == "ERROR")
        assert "MP3 Stitching Error" in err_event[1]["title"]


# ==============================================================================
# 7. MainWindow UI Interaction & Action Handlers Tests
# ==============================================================================
class TestMainWindowUIInteraction:
    """Verifies MainWindow user actions, Ollama status dispatching, and form management."""

    def test_handle_ollama_status_connected_with_models(self, mock_main_window):
        data = {
            "connected": True,
            "models": ["phi3:medium", "llama3.1:8b", "mistral:latest"],
        }
        MainWindow._handle_ollama_status(mock_main_window, data)

        mock_main_window.model_menu.configure.assert_called_with(values=data["models"])
        # Should pick preferred model llama3.1:8b
        mock_main_window.model_menu.set.assert_called_with("llama3.1:8b")
        mock_main_window.ollama_badge.set_status.assert_called_with(
            "online", "Ollama Connected (3 models)"
        )
        mock_main_window.btn_start_ollama_header.configure.assert_called_with(state="disabled")
        mock_main_window.btn_start_ollama.configure.assert_called_with(state="disabled")

    def test_handle_ollama_status_connected_no_models(self, mock_main_window):
        data = {"connected": True, "models": []}
        MainWindow._handle_ollama_status(mock_main_window, data)

        mock_main_window.model_menu.configure.assert_called_with(values=["No models installed"])
        mock_main_window.model_menu.set.assert_called_with("No models installed")
        mock_main_window.ollama_badge.set_status.assert_called_with(
            "warning", "Ollama Online (No models)"
        )
        mock_main_window.btn_start_ollama_header.configure.assert_called_with(state="disabled")
        mock_main_window.btn_start_ollama.configure.assert_called_with(state="disabled")

    def test_handle_ollama_status_offline(self, mock_main_window):
        data = {"connected": False, "models": [], "error": "Connection refused"}
        MainWindow._handle_ollama_status(mock_main_window, data)

        mock_main_window.model_menu.configure.assert_called_with(
            values=["Ollama Offline (No models)"]
        )
        mock_main_window.model_menu.set.assert_called_with("Ollama Offline (No models)")
        mock_main_window.ollama_badge.set_status.assert_called_with("offline", "Ollama Offline")
        mock_main_window.btn_start_ollama_header.configure.assert_called_with(state="normal")
        mock_main_window.btn_start_ollama.configure.assert_called_with(state="normal")

    def test_start_generation_input_validation(self, mock_main_window, tmp_path):
        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            # 1. Missing file
            mock_main_window.input_modality_var.get.return_value = "file"
            mock_main_window.file_entry.get.return_value = str(tmp_path / "nonexistent.txt")
            MainWindow.start_generation(mock_main_window, mode="full")
            mock_dialog.assert_called_once()
            assert "Missing Document File" in mock_dialog.call_args[1]["title"]

            # 2. Empty text
            mock_dialog.reset_mock()
            mock_main_window.input_modality_var.get.return_value = "text"
            mock_main_window.text_input_box.get.return_value = "   \n"
            MainWindow.start_generation(mock_main_window, mode="full")
            mock_dialog.assert_called_once()
            assert "Input Required" in mock_dialog.call_args[1]["title"]

            # 3. Ollama offline prerequisite dialog
            mock_dialog.reset_mock()
            mock_main_window.text_input_box.get.return_value = "Valid topic description text"
            mock_main_window.model_menu.get.return_value = "Ollama Offline (No models)"
            MainWindow.start_generation(mock_main_window, mode="full")
            mock_dialog.assert_called_once()
            assert "Ollama Service Required" in mock_dialog.call_args[1]["title"]
            assert mock_dialog.call_args[1]["dialog_type"] == "prerequisite"

            # 4. Ollama online but no models
            mock_dialog.reset_mock()
            mock_main_window.model_menu.get.return_value = "No models installed"
            MainWindow.start_generation(mock_main_window, mode="full")
            mock_dialog.assert_called_once()
            assert "Model Required" in mock_dialog.call_args[1]["title"]
            assert mock_dialog.call_args[1]["dialog_type"] == "warning"

    @patch("ui.main_window.GenerationWorker")
    def test_start_generation_valid_full_pipeline(self, mock_worker_cls, mock_main_window):
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        mock_main_window.input_modality_var.get.return_value = "text"
        mock_main_window.text_input_box.get.return_value = "Valid text input topic"
        mock_main_window.model_menu.get.return_value = "llama3.1:8b"
        mock_main_window.lang_menu.get.return_value = "Norwegian Bokmål (Kari & Ola)"
        mock_main_window.length_menu.get.return_value = "Deep Dive (20-26 turns, ~10-15 min)"
        mock_main_window.tone_menu.get.return_value = "Analytical & Educational"
        mock_main_window.speed_slider.get.return_value = 5.0
        mock_main_window.output_entry.get.return_value = "/test/out"
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[1]

        MainWindow.start_generation(mock_main_window, mode="full")
        mock_main_window._set_busy_state.assert_called_with(True)
        mock_worker.start.assert_called_once()
        kwargs = mock_worker_cls.call_args[1]
        assert kwargs["language"] == "nb-NO"
        assert kwargs["format_type"] == "deep_dive"
        assert kwargs["tone"] == "analytical"
        assert kwargs["speed_rate"] == "+5%"
        assert kwargs["grounding_mode"] == "creative"

    def test_synthesize_from_edited_script_validation(self, mock_main_window):
        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            # 1. Empty script
            mock_main_window.editable_script_box.get.return_value = "  "
            MainWindow._synthesize_from_edited_script(mock_main_window)
            mock_dialog.assert_called_once()
            assert "Empty Script" in mock_dialog.call_args[1]["title"]

            # 2. Invalid format
            mock_dialog.reset_mock()
            mock_main_window.editable_script_box.get.return_value = "Random non-dialogue text"
            with patch("ui.main_window.DialogueParser.parse", return_value=[]):
                MainWindow._synthesize_from_edited_script(mock_main_window)
                mock_dialog.assert_called_once()
                assert "Invalid Script Format" in mock_dialog.call_args[1]["title"]

    @patch("ui.main_window.GenerationWorker")
    def test_synthesize_from_edited_script_valid_json(self, mock_worker_cls, mock_main_window):
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        valid_json = json.dumps([{"speaker": "Host 1", "text": "Turn 1"}])
        mock_main_window.editable_script_box.get.return_value = valid_json
        mock_main_window.lang_menu.get.return_value = "English (Jenny & Guy)"
        mock_main_window.speed_slider.get.return_value = 0.0
        mock_main_window.output_entry.get.return_value = "/test/out"
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[0]

        MainWindow._synthesize_from_edited_script(mock_main_window)
        mock_main_window._set_busy_state.assert_called_with(True)
        mock_worker.start.assert_called_once()
        kwargs = mock_worker_cls.call_args[1]
        assert kwargs["mode"] == "audio_from_script"
        assert kwargs["input_type"] == "dialogue"
        assert len(kwargs["input_data"]) == 1

    def test_render_transcript_cards(self, mock_main_window):
        mock_child = MagicMock()
        mock_main_window.formatted_scroll.winfo_children.return_value = [mock_child]

        turns = [
            DialogueTurn(speaker="Host 1", text="First turn"),
            DialogueTurn(speaker="Host 2", text="Second turn"),
        ]

        with patch("ui.main_window.DialogueTurnCard") as mock_card_cls:
            MainWindow._render_transcript(mock_main_window, turns)
            mock_child.destroy.assert_called_once()
            assert mock_card_cls.call_count == 2
            mock_main_window.editable_script_box.delete.assert_called_with("1.0", "end")
            mock_main_window.editable_script_box.insert.assert_called_once()

    def test_on_generation_done_audio_player_init(self, mock_main_window, tmp_path):
        dummy_mp3 = tmp_path / "test.mp3"
        dummy_mp3.write_bytes(b"ID3dummy")

        mock_main_window.player.get_length.return_value = 120000

        result = {
            "mp3_path": str(dummy_mp3),
            "script_path": str(tmp_path / "test.json"),
            "dialogue": [DialogueTurn(speaker="Host 1", text="Done")],
        }

        MainWindow._on_generation_done(mock_main_window, result)
        mock_main_window._set_busy_state.assert_called_with(False)
        mock_main_window.player.open.assert_called_with(str(dummy_mp3))
        mock_main_window.btn_play.configure.assert_called_with(state="normal")
        mock_main_window.btn_pause.configure.assert_called_with(state="normal")
        mock_main_window.btn_stop.configure.assert_called_with(state="normal")
        mock_main_window.btn_export_mp3.configure.assert_called_with(state="normal")

    def test_reset_form(self, mock_main_window):
        MainWindow.reset_form(mock_main_window)
        mock_main_window.file_entry.delete.assert_called_with(0, "end")
        mock_main_window.text_input_box.delete.assert_called_with("1.0", "end")
        mock_main_window.editable_script_box.delete.assert_called_with("1.0", "end")
        mock_main_window.progress_bar.set.assert_called_with(0.0)
        mock_main_window.grounding_menu.set.assert_called_with(GROUNDING_UI_OPTIONS[0])
        mock_main_window._update_grounding_description.assert_called_once()
        mock_main_window._render_transcript.assert_called_once_with([])

    def test_audio_player_controls(self, mock_main_window):
        mock_main_window.current_mp3_path = "/valid/path.mp3"
        mock_main_window.player._is_open = True

        with patch("os.path.exists", return_value=True):
            MainWindow._play_audio(mock_main_window)
            mock_main_window.player.play.assert_called_once()

            mock_main_window.player.is_paused.return_value = True
            MainWindow._pause_audio(mock_main_window)
            mock_main_window.player.resume.assert_called_once()

            mock_main_window.player.is_paused.return_value = False
            MainWindow._pause_audio(mock_main_window)
            mock_main_window.player.pause.assert_called_once()

            MainWindow._stop_audio(mock_main_window)
            mock_main_window.player.stop.assert_called_once()

            MainWindow._on_seek_audio(mock_main_window, 45000)
            mock_main_window.player.seek.assert_called_with(45000)

            MainWindow._on_volume_changed(mock_main_window, 75.0)
            mock_main_window.player.set_volume.assert_called_with(75)

    def test_on_close_cleanup(self, mock_main_window):
        worker = MagicMock()
        worker.is_alive.return_value = True
        mock_main_window.current_worker = worker
        mock_main_window.current_pull_worker = worker
        mock_main_window.current_launcher_worker = worker

        MainWindow._on_close(mock_main_window)
        mock_main_window.player.close.assert_called_once()
        assert mock_main_window.cancel_event.is_set()
        assert mock_main_window.pull_cancel_event.is_set()
        assert mock_main_window.launcher_cancel_event.is_set()
        mock_main_window.destroy.assert_called_once()


# ==============================================================================
# 8. MainWindow Highway Navigation & Multi-View Architecture Tests
# ==============================================================================
class TestMainWindowHighwayNavigation:
    """Verifies tab switching between Studio Highway, Script Studio, Settings, and Diagnostics."""

    def test_switch_tab_and_nav_changed(self, mock_main_window):
        # 1. Switch to Script Studio
        MainWindow._on_nav_tab_changed(mock_main_window, "📜 Script Studio")
        mock_main_window.view_studio.pack_forget.assert_called()
        mock_main_window.view_script_studio.pack.assert_called()

        # 2. Switch to Settings & Personas
        mock_main_window.view_settings.pack.reset_mock()
        MainWindow._on_nav_tab_changed(mock_main_window, "⚙️ Settings & Personas")
        mock_main_window.view_settings.pack.assert_called()

        # 3. Switch to Diagnostics & About
        mock_main_window.view_about.pack.reset_mock()
        MainWindow._on_nav_tab_changed(mock_main_window, "ℹ️ Diagnostics & About")
        mock_main_window.view_about.pack.assert_called()

        # 4. Switch back to Studio Highway
        mock_main_window.view_studio.pack.reset_mock()
        MainWindow._on_nav_tab_changed(mock_main_window, "🎙️ Studio (The Highway)")
        mock_main_window.view_studio.pack.assert_called()

        # 5. Programmatic switch_tab helper
        mock_main_window._on_nav_tab_changed.reset_mock()
        MainWindow.switch_tab(mock_main_window, "⚙️ Settings & Personas")
        mock_main_window.nav_segmented.set.assert_called_with("⚙️ Settings & Personas")

    def test_update_highway_preset_label(self, mock_main_window):
        # English + Standard 8 min + llama3.1:8b
        mock_main_window.lang_menu.get.return_value = "English (Jenny & Guy)"
        mock_main_window.length_menu.get.return_value = "Standard Episode (12-16 turns, ~5-8 min)"
        mock_main_window.model_menu.get.return_value = "llama3.1:8b"

        MainWindow._update_highway_preset_label(mock_main_window)
        mock_main_window.highway_preset_label.configure.assert_called_once()
        text_arg = mock_main_window.highway_preset_label.configure.call_args[1]["text"]
        assert "English" in text_arg
        assert "8 min" in text_arg
        assert "llama3.1" in text_arg


# ==============================================================================
# 9. App Bootstrap & Crash Logger Tests
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
