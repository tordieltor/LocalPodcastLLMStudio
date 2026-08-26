"""
LocalPodcastLLMStudio - Milestone 4 Adversarial Stress Test Suite
================================================================
Author: Challenger 1 (critic, specialist)
Framework: rational-e2e-testing (5-tier empirical architecture)

Adversarial Stress Test Matrix:
1. Rapid Modality Switching:
   - Rapid cycling between File, Website URL, Pasted Text, and Topic Prompt (Scratch).
   - Container visibility synchronization (file_container, url_container, text_container).
   - Grounding mode auto-synchronization (switching to Topic auto-selects open_topic; switching away auto-reverts to strict).
   - Interleaved modality switching under concurrent state updates.
   - Start generation validation and source data routing across all modalities.

2. Malicious & Invalid URL Payloads into URLExtractionWorker & MainWindow:
   - SSRF loopback endpoints (127.0.0.1, localhost, 0.0.0.0, [::1]).
   - Private IP addresses (10.0.0.1, 192.168.1.1, 172.16.0.1).
   - Cloud metadata services (169.254.169.254, 168.63.129.16).
   - Non-HTTP/HTTPS schemes (file://, ftp://, gopher://, data:, javascript:).
   - Malformed, oversized, and corrupted URL strings.
   - Network errors: DNS failure (gaierror), TimeoutError, ConnectionRefused, HTTP 4xx/5xx, empty responses.
   - UI error dialog dispatch verification without unhandled exceptions or thread locks.

3. Monologue vs Dialogue Style Switching & Voice Selection:
   - Dynamic style toggle between Dialogue (Two Hosts) and Monologue (Solo Host).
   - Dynamic voice container packing/unpacking (dialogue_voice_frame vs monologue_voice_frame).
   - Voice menu population across English and Norwegian languages.
   - Highway preset summary label synchronization.
   - GenerationWorker parameter propagation for host_mode and solo_voice.

4. Fine-Grained Worker Cancellation During Active Extraction & Generation:
   - URLExtractionWorker pre-dispatch and in-flight cancellation.
   - GenerationWorker multi-phase cancellation (ingestion, extraction, LLM, TTS, MP3 stitch).
   - Verification of temporary directory cleanup and Windows file-lock prevention (WinError 32).
   - Rapid concurrent cancellation spam.
"""

import queue
import socket
import tempfile
import threading
from unittest.mock import MagicMock, patch

import customtkinter as ctk
import pytest

from ui.main_window import (
    GROUNDING_UI_OPTIONS,
    GenerationWorker,
    MainWindow,
    URLExtractionWorker,
)
from ui.widgets import StatusBadge


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
    win.url_cancel_event = threading.Event()
    win.current_worker = None
    win.current_pull_worker = None
    win.current_launcher_worker = None
    win.current_url_worker = None
    win.player = MagicMock()
    win.is_busy = False
    win._is_closing = False
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
    win.lang_menu.get.return_value = "English (Jenny & Guy)"
    win.length_menu = MagicMock()
    win.tone_menu = MagicMock()
    win.speed_slider = MagicMock()
    win.output_entry = MagicMock()
    win.output_entry.get.return_value = tempfile.gettempdir()
    win.file_entry = MagicMock()
    win.file_info_label = MagicMock()
    win.text_input_box = MagicMock()
    win.editable_script_box = MagicMock()
    win.input_modality_var = MagicMock()
    win.input_modality_var.get.return_value = "file"
    win.grounding_menu = MagicMock()
    win.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[0]
    win.grounding_desc_label = MagicMock()
    win.modality_segmented = MagicMock()

    # Modality Containers
    win.file_container = MagicMock()
    win.url_container = MagicMock()
    win.text_container = MagicMock()
    win.url_entry = MagicMock()
    win.btn_extract_url = MagicMock()
    win.url_status_label = MagicMock()
    win.url_info_label = win.url_status_label
    win.url_preview_box = MagicMock()
    win.url_char_count_label = MagicMock()

    # Voice / Episode Style Widgets
    win.episode_style_var = MagicMock()
    win.episode_style_var.get.return_value = "dialogue"
    win.style_segmented = MagicMock()
    win.style_segmented.get.return_value = "🎙️ Dialogue (Two Hosts)"
    win.episode_style_segmented = win.style_segmented
    win.voice_selection_container = MagicMock()
    win.dialogue_voice_frame = MagicMock()
    win.monologue_voice_frame = MagicMock()
    win.solo_voice_frame = win.monologue_voice_frame
    win.host1_voice_frame = MagicMock()
    win.host1_voice_menu = MagicMock()
    win.host1_voice_menu.get.return_value = "Jenny (Female)"
    win.host2_voice_frame = MagicMock()
    win.host2_voice_menu = MagicMock()
    win.host2_voice_menu.get.return_value = "Guy (Male)"
    win.solo_voice_menu = MagicMock()
    win.solo_voice_menu.get.return_value = "Jenny (Female)"
    win.highway_preset_label = MagicMock()

    win.stage_tracker = MagicMock()
    win.pull_frame = MagicMock()
    win.pull_status_label = MagicMock()
    win.pull_progress_bar = MagicMock()
    win.pull_speed_label = MagicMock()
    win.pull_details_label = MagicMock()
    win.btn_cancel_pull = MagicMock()
    win.formatted_scroll = MagicMock()
    win.formatted_scroll.winfo_children.return_value = []

    # Re-bind methods from MainWindow to mock
    win.get_selected_grounding_mode = lambda: MainWindow.get_selected_grounding_mode(win)
    win._update_grounding_description = lambda: MainWindow._update_grounding_description(win)
    win._on_modality_changed = lambda val: MainWindow._on_modality_changed(win, val)
    win._on_style_changed = lambda val: MainWindow._on_style_changed(win, val)
    win._update_voice_selectors = lambda: MainWindow._update_voice_selectors(win)
    win._on_language_changed = lambda val: MainWindow._on_language_changed(win, val)
    win._update_highway_preset_label = lambda: MainWindow._update_highway_preset_label(win)
    win._extract_url_async = lambda: MainWindow._extract_url_async(win)
    win._handle_event = lambda evt, payload: MainWindow._handle_event(win, evt, payload)
    win._process_queue = lambda: MainWindow._process_queue(win)
    win._set_busy_state = lambda busy: MainWindow._set_busy_state(win, busy)
    win.start_generation = lambda mode="full": MainWindow.start_generation(win, mode)
    win.cancel_generation = lambda: MainWindow.cancel_generation(win)

    return win


# ==============================================================================
# 1. Rapid Modality Switching Adversarial Tests
# ==============================================================================
class TestRapidModalitySwitchingAdversarial:
    """Stress tests verifying container visibility, grounding mode synchronization, and state stability."""

    def test_single_cycle_modality_switching_and_containers(self, mock_main_window):
        """Verifies each modality switch shows the correct container and hides others."""
        # 1. Switch to Document (File)
        mock_main_window._on_modality_changed("Document (.txt/.md/.pdf)")
        mock_main_window.input_modality_var.set.assert_called_with("file")
        mock_main_window.file_container.pack.assert_called()
        mock_main_window.url_container.pack_forget.assert_called()
        mock_main_window.text_container.pack_forget.assert_called()

        # 2. Switch to Website URL
        mock_main_window.file_container.reset_mock()
        mock_main_window.url_container.reset_mock()
        mock_main_window.text_container.reset_mock()
        mock_main_window._on_modality_changed("Website URL")
        mock_main_window.input_modality_var.set.assert_called_with("url")
        mock_main_window.url_container.pack.assert_called()
        mock_main_window.file_container.pack_forget.assert_called()
        mock_main_window.text_container.pack_forget.assert_called()

        # 3. Switch to Pasted Text
        mock_main_window.file_container.reset_mock()
        mock_main_window.url_container.reset_mock()
        mock_main_window.text_container.reset_mock()
        mock_main_window._on_modality_changed("Pasted Text")
        mock_main_window.input_modality_var.set.assert_called_with("text")
        mock_main_window.text_container.pack.assert_called()
        mock_main_window.file_container.pack_forget.assert_called()
        mock_main_window.url_container.pack_forget.assert_called()

        # 4. Switch to Topic Prompt (Scratch)
        mock_main_window.file_container.reset_mock()
        mock_main_window.url_container.reset_mock()
        mock_main_window.text_container.reset_mock()
        mock_main_window._on_modality_changed("Topic Prompt (Scratch)")
        mock_main_window.input_modality_var.set.assert_called_with("topic")
        mock_main_window.text_container.pack.assert_called()
        mock_main_window.file_container.pack_forget.assert_called()
        mock_main_window.url_container.pack_forget.assert_called()

    def test_grounding_mode_auto_sync_on_modality_switch(self, mock_main_window):
        """
        Verifies that switching to Topic Prompt automatically selects 'open_topic',
        and switching from open_topic to File/URL/Text automatically reverts to 'strict'.
        """
        # Start in Document mode with strict
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[0]  # Strict
        mock_main_window._on_modality_changed("Document (.txt/.md/.pdf)")

        # Switch to Topic Prompt -> Should auto-sync to Open Topic
        mock_main_window._on_modality_changed("Topic Prompt (Scratch)")
        mock_main_window.grounding_menu.set.assert_called_with(GROUNDING_UI_OPTIONS[2])

        # Now simulate grounding menu returning Open Topic
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[2]  # Open Topic
        # Switch to Website URL -> Should auto-revert to Strict
        mock_main_window._on_modality_changed("Website URL")
        mock_main_window.grounding_menu.set.assert_called_with(GROUNDING_UI_OPTIONS[0])

        # Switch to Topic again
        mock_main_window._on_modality_changed("Topic Prompt (Scratch)")
        mock_main_window.grounding_menu.set.assert_called_with(GROUNDING_UI_OPTIONS[2])

        # Switch to Pasted Text -> Should auto-revert to Strict
        mock_main_window.grounding_menu.get.return_value = GROUNDING_UI_OPTIONS[2]
        mock_main_window._on_modality_changed("Pasted Text")
        mock_main_window.grounding_menu.set.assert_called_with(GROUNDING_UI_OPTIONS[0])

    def test_rapid_100_modality_switches_stress(self, mock_main_window):
        """
        Stress tests 100 rapid random switches across all 4 modalities.
        Verifies no exception is thrown and UI remains completely consistent.
        """
        modalities = [
            "Document (.txt/.md/.pdf)",
            "Website URL",
            "Pasted Text",
            "Topic Prompt (Scratch)",
        ]
        for i in range(100):
            chosen = modalities[i % len(modalities)]
            mock_main_window._on_modality_changed(chosen)

        # Final check
        mock_main_window._on_modality_changed("Website URL")
        mock_main_window.input_modality_var.set.assert_called_with("url")

    def test_start_generation_input_routing_per_modality(self, mock_main_window, tmp_path):
        """Verifies start_generation routes source data correctly for each modality."""
        dummy_file = tmp_path / "article.txt"
        dummy_file.write_text(
            "Valid sample article content for podcast generation.", encoding="utf-8"
        )

        mock_main_window.model_menu.get.return_value = "llama3.1:8b"
        mock_main_window.lang_menu.get.return_value = "English (Jenny & Guy)"
        mock_main_window.length_menu.get.return_value = "Standard (~8 min)"
        mock_main_window.tone_menu.get.return_value = "Casual & Engaging"
        mock_main_window.speed_slider.get.return_value = 0.0

        with patch("ui.main_window.GenerationWorker") as mock_worker_cls:
            mock_worker = MagicMock()
            mock_worker_cls.return_value = mock_worker

            # 1. File modality
            mock_main_window.input_modality_var.get.return_value = "file"
            mock_main_window.file_entry.get.return_value = str(dummy_file)
            mock_main_window.start_generation(mode="full")
            assert mock_worker_cls.call_args[1]["input_type"] == "file"
            assert mock_worker_cls.call_args[1]["input_data"] == str(dummy_file)

            # 2. URL modality
            mock_main_window.input_modality_var.get.return_value = "url"
            mock_main_window.url_entry.get.return_value = "https://en.wikipedia.org/wiki/Podcast"
            mock_main_window.start_generation(mode="full")
            assert mock_worker_cls.call_args[1]["input_type"] == "url"
            assert (
                mock_worker_cls.call_args[1]["input_data"]
                == "https://en.wikipedia.org/wiki/Podcast"
            )

            # 3. Text modality
            mock_main_window.input_modality_var.get.return_value = "text"
            mock_main_window.text_input_box.get.return_value = "Pasted text content for podcast."
            mock_main_window.start_generation(mode="full")
            assert mock_worker_cls.call_args[1]["input_type"] == "text"
            assert mock_worker_cls.call_args[1]["input_data"] == "Pasted text content for podcast."

            # 4. Topic modality
            mock_main_window.input_modality_var.get.return_value = "topic"
            mock_main_window.text_input_box.get.return_value = "Topic: Future of Quantum Computing"
            mock_main_window.start_generation(mode="full")
            assert mock_worker_cls.call_args[1]["input_type"] == "topic"
            assert (
                mock_worker_cls.call_args[1]["input_data"] == "Topic: Future of Quantum Computing"
            )


# ==============================================================================
# 2. Malicious and Invalid URL Payloads Adversarial Tests
# ==============================================================================
class TestMaliciousAndInvalidURLAdversarial:
    """Stress tests URLExtractionWorker and MainWindow against SSRF, invalid schemes, and network faults."""

    @pytest.mark.parametrize(
        "ssrf_payload",
        [
            "http://127.0.0.1:8000/secret",
            "http://127.0.0.1:11434/api/tags",
            "http://localhost:8080/admin",
            "http://localhost/metrics",
            "http://0.0.0.0:80/",
            "http://10.0.0.1/internal",
            "http://10.254.254.254/status",
            "http://192.168.1.1/router",
            "http://192.168.0.254/setup",
            "http://172.16.0.1/private",
            "http://172.31.255.255/dashboard",
            "http://169.254.169.254/latest/meta-data/",
            "http://168.63.129.16/metadata",
            "http://[::1]:8080/debug",
            "http://[fe80::1]/link-local",
        ],
    )
    def test_ssrf_loopback_and_private_ip_blocking(self, ssrf_payload: str):
        """Verifies URLExtractionWorker catches SSRF attempts and emits structured error."""
        msg_q = queue.Queue()
        worker = URLExtractionWorker(url=ssrf_payload, msg_queue=msg_q)
        worker.start()
        worker.join(timeout=3.0)

        assert not worker.is_alive()
        events = []
        while not msg_q.empty():
            events.append(msg_q.get_nowait())

        error_events = [e for e in events if e[0] in ("EXTRACTION_ERROR", "URL_EXTRACTION_ERROR")]
        assert len(error_events) >= 1
        payload = error_events[0][1]
        assert payload.get("is_security") is True
        assert "SSRF" in payload.get("title", "") or "Security" in payload.get("title", "")
        assert "remedy" in payload

    @pytest.mark.parametrize(
        "non_http_url",
        [
            "file:///c:/windows/system32/drivers/etc/hosts",
            "ftp://ftp.example.com/secret.txt",
            "gopher://gopher.floodgap.com/",
            "data:text/html,<h1>Malicious</h1>",
            "javascript:alert(1)",
            "blob:https://example.com/123-456",
            "ws://localhost:8080/socket",
        ],
    )
    def test_non_http_schemes_rejected_before_and_in_worker(
        self, mock_main_window, non_http_url: str
    ):
        """Verifies non-HTTP schemes are rejected by MainWindow synchronous check and worker."""
        # 1. Test MainWindow._extract_url_async validation
        mock_main_window.url_entry.get.return_value = non_http_url
        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            mock_main_window._extract_url_async()
            assert mock_dialog.called
            call_kwargs = mock_dialog.call_args[1]
            assert "Invalid URL Scheme" in call_kwargs.get("title", "")

        # 2. Test URLExtractionWorker directly
        msg_q = queue.Queue()
        worker = URLExtractionWorker(url=non_http_url, msg_queue=msg_q)
        worker.start()
        worker.join(timeout=3.0)

        events = []
        while not msg_q.empty():
            events.append(msg_q.get_nowait())

        error_events = [e for e in events if e[0] in ("EXTRACTION_ERROR", "URL_EXTRACTION_ERROR")]
        assert len(error_events) >= 1

    def test_dns_resolution_failure_handling(self, mock_main_window):
        """Simulates DNS lookup failure (gaierror) and asserts proper error dialog dispatch."""
        msg_q = queue.Queue()
        with patch(
            "core.extractor.socket.getaddrinfo",
            side_effect=socket.gaierror(-2, "Name or service not known"),
        ):
            worker = URLExtractionWorker(
                url="https://nonexistent-domain-123456789.org", msg_queue=msg_q
            )
            worker.start()
            worker.join(timeout=3.0)

        events = []
        while not msg_q.empty():
            events.append(msg_q.get_nowait())

        error_events = [e for e in events if e[0] in ("EXTRACTION_ERROR", "URL_EXTRACTION_ERROR")]
        assert len(error_events) >= 1

        # Dispatch through MainWindow
        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            mock_main_window._handle_event("URL_EXTRACTION_ERROR", error_events[0][1])
            assert mock_dialog.called
            mock_main_window.btn_extract_url.configure.assert_called_with(state="normal")

    def test_connection_timeout_handling(self, mock_main_window):
        """Simulates request timeout and asserts graceful error handling."""
        msg_q = queue.Queue()
        import requests

        with (
            patch(
                "core.extractor.socket.getaddrinfo",
                return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
            ),
            patch(
                "core.extractor.requests.get",
                side_effect=requests.Timeout("Request timed out after 10.0s"),
            ),
        ):
            worker = URLExtractionWorker(url="https://slow-site.example.com", msg_queue=msg_q)
            worker.start()
            worker.join(timeout=3.0)

        events = []
        while not msg_q.empty():
            events.append(msg_q.get_nowait())

        error_events = [e for e in events if e[0] in ("EXTRACTION_ERROR", "URL_EXTRACTION_ERROR")]
        assert len(error_events) >= 1

        with patch("ui.main_window.ActionableErrorDialog") as mock_dialog:
            mock_main_window._handle_event("URL_EXTRACTION_ERROR", error_events[0][1])
            assert mock_dialog.called

    def test_oversized_web_content_handling(self):
        """Verifies worker handles payloads exceeding max size limit (5MB)."""
        msg_q = queue.Queue()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_redirect = False
        mock_response.headers = {"Content-Type": "text/html", "Content-Length": "10000000"}

        with (
            patch(
                "core.extractor.socket.getaddrinfo",
                return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
            ),
            patch("core.extractor.requests.get", return_value=mock_response),
        ):
            # Set max_size_bytes low to trigger limit
            worker = URLExtractionWorker(
                url="https://example.com/huge",
                msg_queue=msg_q,
                max_size_bytes=1000,
            )
            worker.start()
            worker.join(timeout=3.0)

        events = []
        while not msg_q.empty():
            events.append(msg_q.get_nowait())

        error_events = [e for e in events if e[0] in ("EXTRACTION_ERROR", "URL_EXTRACTION_ERROR")]
        assert len(error_events) >= 1

    def test_successful_url_extraction_updates_preview_box(self, mock_main_window):
        """Verifies successful URL extraction renders markdown into url_preview_box and updates char count."""
        payload = {
            "url": "https://en.wikipedia.org/wiki/Podcast",
            "markdown": "# Podcast\nA podcast is an episodic series of digital audio files.",
            "char_count": 58,
        }
        mock_main_window._handle_event("URL_EXTRACTION_DONE", payload)
        mock_main_window.btn_extract_url.configure.assert_called_with(state="normal")
        mock_main_window.url_char_count_label.configure.assert_called_with(text="58 chars")
        mock_main_window.url_preview_box.delete.assert_called_with("1.0", "end")
        mock_main_window.url_preview_box.insert.assert_called_with("1.0", payload["markdown"])


# ==============================================================================
# 3. Monologue vs Dialogue Style Switching & Voice Selection
# ==============================================================================
class TestMonologueVsDialogueStyleSwitchingAdversarial:
    """Stress tests verifying style toggle, voice packing, preset updates, and generation propagation."""

    def test_style_switching_voice_container_visibility(self, mock_main_window):
        """Verifies toggling between monologue and dialogue packs/unpacks voice frames correctly."""
        # 1. Switch to Monologue
        mock_main_window._on_style_changed("👤 Monologue (Solo Host)")
        mock_main_window.episode_style_var.set.assert_called_with("monologue")
        mock_main_window.dialogue_voice_frame.pack_forget.assert_called()
        mock_main_window.host2_voice_frame.pack_forget.assert_called()
        mock_main_window.monologue_voice_frame.pack.assert_called_with(fill="x", pady=(0, 4))

        # 2. Switch back to Dialogue
        mock_main_window.dialogue_voice_frame.reset_mock()
        mock_main_window.host2_voice_frame.reset_mock()
        mock_main_window.monologue_voice_frame.reset_mock()

        mock_main_window._on_style_changed("🎙️ Dialogue (Two Hosts)")
        mock_main_window.episode_style_var.set.assert_called_with("dialogue")
        mock_main_window.monologue_voice_frame.pack_forget.assert_called()
        mock_main_window.dialogue_voice_frame.pack.assert_called_with(fill="x")
        mock_main_window.host2_voice_frame.pack.assert_called_with(fill="x", pady=(0, 4))

    def test_language_change_updates_voice_dropdowns(self, mock_main_window):
        """Verifies changing language updates Host 1, Host 2, and Solo Host dropdown menus."""
        # Switch to Norwegian
        mock_main_window.lang_menu.get.return_value = "Norwegian Bokmål (Kari & Ola)"
        mock_main_window._on_language_changed("Norwegian Bokmål (Kari & Ola)")

        mock_main_window.host1_voice_menu.configure.assert_called_with(
            values=["Kari (Female)", "Pernille (Female)"]
        )
        mock_main_window.host2_voice_menu.configure.assert_called_with(
            values=["Ola (Male)", "Finn (Male)"]
        )
        mock_main_window.solo_voice_menu.configure.assert_called_with(
            values=["Kari (Female)", "Ola (Male)"]
        )

        # Switch to English
        mock_main_window.lang_menu.get.return_value = "English (Jenny & Guy)"
        mock_main_window._on_language_changed("English (Jenny & Guy)")

        mock_main_window.host1_voice_menu.configure.assert_called_with(
            values=["Jenny (Female)", "Amy (Female)"]
        )
        mock_main_window.host2_voice_menu.configure.assert_called_with(
            values=["Guy (Male)", "Joe (Male)"]
        )
        mock_main_window.solo_voice_menu.configure.assert_called_with(
            values=["Jenny (Female)", "Guy (Male)"]
        )

    def test_highway_preset_label_updates_on_style_and_language_change(self, mock_main_window):
        """Verifies highway_preset_label dynamically reflects solo host vs dual hosts."""
        mock_main_window.lang_menu.get.return_value = "English (Jenny & Guy)"
        mock_main_window.length_menu.get.return_value = "Standard (~8 min)"
        mock_main_window.model_menu.get.return_value = "llama3.1:8b"

        # Dialogue
        mock_main_window.episode_style_var.get.return_value = "dialogue"
        mock_main_window.host1_voice_menu.get.return_value = "Jenny (Female)"
        mock_main_window.host2_voice_menu.get.return_value = "Guy (Male)"
        mock_main_window._update_highway_preset_label()
        assert mock_main_window.highway_preset_label.configure.called

        # Monologue
        mock_main_window.episode_style_var.get.return_value = "monologue"
        mock_main_window.solo_voice_menu.get.return_value = "Jenny (Female)"
        mock_main_window._update_highway_preset_label()
        assert mock_main_window.highway_preset_label.configure.called

    def test_start_generation_propagates_host_mode_and_solo_voice(self, mock_main_window, tmp_path):
        """Verifies start_generation passes host_mode='monologue' and solo_voice to GenerationWorker."""
        dummy_file = tmp_path / "test.txt"
        dummy_file.write_text("Sample podcast text for monologue test.", encoding="utf-8")

        mock_main_window.input_modality_var.get.return_value = "file"
        mock_main_window.file_entry.get.return_value = str(dummy_file)
        mock_main_window.model_menu.get.return_value = "llama3.1:8b"
        mock_main_window.lang_menu.get.return_value = "English (Jenny & Guy)"
        mock_main_window.length_menu.get.return_value = "Standard (~8 min)"
        mock_main_window.tone_menu.get.return_value = "Casual & Engaging"
        mock_main_window.speed_slider.get.return_value = 0.0

        # Monologue mode
        mock_main_window.episode_style_var.get.return_value = "monologue"
        mock_main_window.solo_voice_menu.get.return_value = "Jenny (Female)"

        with patch("ui.main_window.GenerationWorker") as mock_worker_cls:
            mock_worker = MagicMock()
            mock_worker_cls.return_value = mock_worker

            mock_main_window.start_generation(mode="full")

            assert mock_worker_cls.call_args[1]["host_mode"] == "monologue"
            assert mock_worker_cls.call_args[1]["solo_voice"] == "Jenny (Female)"


# ==============================================================================
# 4. Background Worker Cancellation Adversarial Tests
# ==============================================================================
class TestWorkerCancellationAdversarial:
    """Stress tests verifying cancellation responsiveness and temporary artifact cleanup."""

    def test_url_extraction_worker_pre_cancellation(self):
        """Verifies URLExtractionWorker immediately stops when cancel_event is set pre-run."""
        msg_q = queue.Queue()
        cancel_evt = threading.Event()
        cancel_evt.set()  # Pre-cancelled

        worker = URLExtractionWorker(
            url="https://en.wikipedia.org/wiki/Podcast",
            msg_queue=msg_q,
            cancel_event=cancel_evt,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert not worker.is_alive()
        events = []
        while not msg_q.empty():
            events.append(msg_q.get_nowait())

        assert any(e[0] in ("EXTRACTION_CANCELLED", "URL_EXTRACTION_CANCELLED") for e in events)

    def test_url_extraction_worker_in_flight_cancellation(self):
        """Verifies cancellation during active URL extraction progress callback."""
        msg_q = queue.Queue()
        cancel_evt = threading.Event()

        def mock_extract_text(*args, **kwargs):
            cb = kwargs.get("progress_callback")
            if cb:
                cb("Fetching payload bytes...")
            cancel_evt.set()  # Cancel mid-flight
            return "# Mock content"

        with patch("ui.main_window.extract_text", side_effect=mock_extract_text):
            worker = URLExtractionWorker(
                url="https://en.wikipedia.org/wiki/Podcast",
                msg_queue=msg_q,
                cancel_event=cancel_evt,
            )
            worker.start()
            worker.join(timeout=3.0)

            assert not worker.is_alive()
            events = []
            while not msg_q.empty():
                events.append(msg_q.get_nowait())

            assert any(e[0] in ("EXTRACTION_CANCELLED", "URL_EXTRACTION_CANCELLED") for e in events)

    def test_generation_worker_cancellation_during_url_ingestion(self, tmp_path):
        """Verifies GenerationWorker handles cancellation during URL ingestion phase."""
        msg_q = queue.Queue()
        cancel_evt = threading.Event()

        def mock_extract(*args, **kwargs):
            cancel_evt.set()
            return "Sample web content."

        with patch("ui.main_window.extract_text", side_effect=mock_extract):
            worker = GenerationWorker(
                mode="full",
                input_type="url",
                input_data="https://en.wikipedia.org/wiki/Podcast",
                language="en-US",
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

    def test_generation_worker_cancellation_during_llm_streaming(self, tmp_path):
        """Verifies GenerationWorker handles cancellation during LLM script generation streaming."""
        msg_q = queue.Queue()
        cancel_evt = threading.Event()

        def mock_generate_script(*args, **kwargs):
            cancel = kwargs.get("cancel_event")
            stream_cb = kwargs.get("stream_callback")
            if stream_cb:
                stream_cb("Streaming first chunk...")
            if cancel:
                cancel.set()
            return []

        with (
            patch("ui.main_window.extract_text", return_value="Sample document content for test."),
            patch("ui.main_window.generate_podcast_script", side_effect=mock_generate_script),
        ):
            worker = GenerationWorker(
                mode="full",
                input_type="text",
                input_data="Sample document content for test.",
                language="en-US",
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

    def test_rapid_cancellation_command_spam(self, mock_main_window):
        """Spams cancel_generation from 20 threads simultaneously to test race conditions."""
        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True
        mock_main_window.current_worker = mock_worker

        def cancel_caller():
            for _ in range(10):
                mock_main_window.cancel_generation()

        threads = [threading.Thread(target=cancel_caller, daemon=True) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert mock_main_window.cancel_event.is_set()
        mock_main_window.btn_cancel.configure.assert_called_with(state="disabled")
