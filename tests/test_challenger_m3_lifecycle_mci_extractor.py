"""
Empirical Challenge Test Suite: Lifecycle, MCI Player, and Extractor Robustness
==============================================================================
Author: Challenger 2 (critic, specialist)
Framework: rational-e2e-testing (5-tier empirical architecture)

Covers:
1. Tkinter `after()` timer cancellation in `_on_close()` under rapid open/close cycles and simulated active worker threads.
2. Windows MCI player open failure handling when given corrupted audio, non-audio files, or invalid paths.
3. Document extractor error boundary with invalid PDFs, password-protected PDFs, and corrupted encodings.
"""

import os
import queue
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.extractor import (
    DocumentExtractionError,
    extract_text,
    extract_text_from_file,
    extract_text_from_pdf,
    normalize_extracted_text,
)
from core.player import (
    WindowsAudioPlayer,
    export_audio_file,
)
from ui.main_window import (
    MainWindow,
)


# ==============================================================================
# 1. Tkinter Lifecycle & Timer Teardown Empirical Tests
# ==============================================================================
class TestTkinterLifecycleAndTimerTeardown:
    """Stress tests Tkinter after() timer cancellation, worker termination, and rapid open/close."""

    @pytest.fixture
    def mock_ui_instance(self):
        """Creates a mock MainWindow instance."""
        win = MagicMock(spec=MainWindow)
        win._is_closing = False
        win._queue_poll_id = "after#101"
        win._player_poll_id = "after#102"
        win.msg_queue = queue.Queue()
        win.cancel_event = threading.Event()
        win.pull_cancel_event = threading.Event()
        win.launcher_cancel_event = threading.Event()
        win.current_worker = None
        win.current_pull_worker = None
        win.current_launcher_worker = None
        win.player = MagicMock(spec=WindowsAudioPlayer)
        win.after_cancel = MagicMock()
        win.destroy = MagicMock()
        return win

    def test_on_close_cancels_both_after_timers_and_clears_ids(self, mock_ui_instance):
        """Verifies _on_close invokes after_cancel for both queue and player poller and sets ids to None."""
        MainWindow._on_close(mock_ui_instance)

        assert mock_ui_instance._is_closing is True
        mock_ui_instance.after_cancel.assert_any_call("after#101")
        mock_ui_instance.after_cancel.assert_any_call("after#102")
        assert mock_ui_instance._queue_poll_id is None
        assert mock_ui_instance._player_poll_id is None
        mock_ui_instance.player.close.assert_called_once()
        mock_ui_instance.destroy.assert_called_once()

    def test_on_close_idempotent_multiple_calls_safe(self, mock_ui_instance):
        """Calling _on_close() multiple times successively must not raise exceptions or crash."""
        for _ in range(5):
            MainWindow._on_close(mock_ui_instance)

        assert mock_ui_instance._is_closing is True
        assert mock_ui_instance._queue_poll_id is None
        assert mock_ui_instance._player_poll_id is None

    def test_on_close_handles_after_cancel_exceptions_gracefully(self, mock_ui_instance):
        """If after_cancel throws (e.g. invalid ID or already cancelled in Tk), _on_close suppresses it."""
        mock_ui_instance.after_cancel.side_effect = RuntimeError("Invalid after identifier")

        MainWindow._on_close(mock_ui_instance)

        assert mock_ui_instance._is_closing is True
        assert mock_ui_instance._queue_poll_id is None
        assert mock_ui_instance._player_poll_id is None
        mock_ui_instance.destroy.assert_called_once()

    def test_pollers_do_not_reschedule_when_closing(self, mock_ui_instance):
        """When _is_closing is True, pollers must exit immediately without calling after()."""
        mock_ui_instance._is_closing = True
        mock_ui_instance.after = MagicMock()

        MainWindow._start_queue_poller(mock_ui_instance)
        MainWindow._start_player_poller(mock_ui_instance)

        mock_ui_instance.after.assert_not_called()

    def test_on_close_with_active_multithreaded_workers_and_queue_flood(self, mock_ui_instance):
        """Simulates all 3 background workers actively running and queue flooded when user closes window."""
        worker_stop_event = threading.Event()

        def active_worker_loop(cancel_evt: threading.Event, name: str):
            while not cancel_evt.is_set() and not worker_stop_event.is_set():
                mock_ui_instance.msg_queue.put(("STATUS", f"Working {name}"))
                time.sleep(0.005)

        w1 = threading.Thread(
            target=active_worker_loop, args=(mock_ui_instance.cancel_event, "gen")
        )
        w2 = threading.Thread(
            target=active_worker_loop, args=(mock_ui_instance.pull_cancel_event, "pull")
        )
        w3 = threading.Thread(
            target=active_worker_loop, args=(mock_ui_instance.launcher_cancel_event, "launcher")
        )

        w1.start()
        w2.start()
        w3.start()

        mock_ui_instance.current_worker = w1
        mock_ui_instance.current_pull_worker = w2
        mock_ui_instance.current_launcher_worker = w3

        MainWindow._on_close(mock_ui_instance)

        assert mock_ui_instance.cancel_event.is_set()
        assert mock_ui_instance.pull_cancel_event.is_set()
        assert mock_ui_instance.launcher_cancel_event.is_set()

        w1.join(timeout=1.0)
        w2.join(timeout=1.0)
        w3.join(timeout=1.0)

        assert not w1.is_alive()
        assert not w2.is_alive()
        assert not w3.is_alive()

        worker_stop_event.set()

    def test_rapid_open_close_cycles_stress(self):
        """Runs 30 simulated rapid open/close lifecycle sequences without resource leaks."""
        for cycle in range(30):
            win = MagicMock(spec=MainWindow)
            win._is_closing = False
            win._queue_poll_id = f"after#{cycle}_q"
            win._player_poll_id = f"after#{cycle}_p"
            win.msg_queue = queue.Queue()
            win.cancel_event = threading.Event()
            win.pull_cancel_event = threading.Event()
            win.launcher_cancel_event = threading.Event()
            win.current_worker = None
            win.current_pull_worker = None
            win.current_launcher_worker = None
            win.player = WindowsAudioPlayer(alias=f"test_alias_{cycle}")

            MainWindow._on_close(win)
            assert win._is_closing is True
            assert win._queue_poll_id is None
            assert win._player_poll_id is None


# ==============================================================================
# 2. Windows MCI Audio Player Open Failure & Edge Cases
# ==============================================================================
class TestWindowsMCIPlayerErrorBoundaries:
    """Stress tests WindowsAudioPlayer under corrupt files, invalid paths, and MCI failures."""

    def test_open_corrupted_empty_file_fails_cleanly(self, tmp_path):
        """0-byte file must return False, keep _is_opened False, and not crash."""
        empty_file = tmp_path / "empty.mp3"
        empty_file.write_bytes(b"")

        player = WindowsAudioPlayer(alias="test_empty_mci")

        def simulate_mci_send(cmd, buffer_len=256):
            if "open" in cmd:
                player._last_error = 263  # MCIERR_INVALID_FILE
                return ""
            return ""

        with patch.object(player, "_send_command", side_effect=simulate_mci_send):
            success = player.open(str(empty_file))
            assert success is False
            assert player._is_opened is False
            assert player.is_playing() is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows MCI tests require Windows OS")
    def test_real_windows_mci_open_invalid_audio_returns_false(self, tmp_path):
        """Tests actual Windows MCI driver (winmm.dll) handling of 0-byte or corrupted file without mocks."""
        empty_file = tmp_path / "real_empty.mp3"
        empty_file.write_bytes(b"")

        player = WindowsAudioPlayer(alias="real_test_empty_mci")
        try:
            res = player.open(str(empty_file))
            assert res is False
            assert player._is_opened is False
            assert player.is_playing() is False
        finally:
            player.close()

    def test_open_garbage_binary_file_returns_false_on_mci_error(self, tmp_path):
        """Corrupted random binary payload causing non-zero MCI error returns False."""
        garbage_file = tmp_path / "corrupted.mp3"
        garbage_file.write_bytes(os.urandom(1024))

        player = WindowsAudioPlayer(alias="test_garbage_mci")

        def simulate_mci_send(cmd, buffer_len=256):
            if "open" in cmd:
                player._last_error = 275  # MCIERR_DEVICE_NOT_READY or similar
                return ""
            return ""

        with patch.object(player, "_send_command", side_effect=simulate_mci_send):
            res = player.open(str(garbage_file))
            assert res is False
            assert player._is_opened is False
            assert player.is_playing() is False
            assert player.get_position() == 0
            assert player.get_length() == 0
            assert player.get_mode() == "not ready"

    def test_player_methods_safe_when_unopened(self):
        """Calling play, pause, resume, stop, seek, etc. on unopened player returns safe defaults."""
        player = WindowsAudioPlayer(alias="test_unopened_mci")
        assert player._is_opened is False

        assert player.play() is False
        assert player.play(from_ms=1000) is False
        assert player.pause() is False
        assert player.resume() is False
        assert player.stop() is False
        assert player.seek(5000) is False
        assert player.get_position() == 0
        assert player.get_length() == 0
        assert player.get_mode() == "not ready"
        assert player.is_playing() is False
        assert player.is_paused() is False
        assert player.is_stopped() is True
        assert player.close() is True

    def test_player_reopen_closes_previous_session(self, tmp_path, single_frame_mp3):
        """Consecutive open() calls must issue close command before re-opening."""
        f1 = tmp_path / "f1.mp3"
        f1.write_bytes(single_frame_mp3)
        f2 = tmp_path / "f2.mp3"
        f2.write_bytes(single_frame_mp3)

        player = WindowsAudioPlayer(alias="test_reopen_mci")
        commands = []

        def mock_send(cmd, buffer_len=256):
            commands.append(cmd)
            if "status" in cmd and "length" in cmd:
                return "12000"
            return ""

        with patch.object(player, "_send_command", side_effect=mock_send):
            assert player.open(str(f1)) is True
            assert player._is_opened is True
            assert "f1.mp3" in (player.current_file or "")

            assert player.open(str(f2)) is True
            assert player._is_opened is True
            assert "f2.mp3" in (player.current_file or "")

            close_commands = [c for c in commands if c.startswith(f"close {player.alias}")]
            assert len(close_commands) >= 2

    def test_player_context_manager_and_del_cleanup(self, tmp_path, single_frame_mp3):
        """WindowsAudioPlayer works safely as context manager and invokes close in __exit__ and __del__."""
        f1 = tmp_path / "test.mp3"
        f1.write_bytes(single_frame_mp3)

        with WindowsAudioPlayer(alias="test_cm_mci") as player:
            with patch.object(player, "_send_command", return_value="5000"):
                player.open(str(f1))
                assert player._is_opened is True

        assert player._is_opened is False

        player_del = WindowsAudioPlayer(alias="test_del_mci")
        player_del.__del__()

    def test_export_audio_file_nonexistent_raises(self, tmp_path):
        """export_audio_file raises FileNotFoundError if source is missing."""
        with pytest.raises(FileNotFoundError):
            export_audio_file(str(tmp_path / "nonexistent.mp3"), str(tmp_path / "out.mp3"))

    def test_export_audio_file_creates_nested_directories(self, tmp_path, single_frame_mp3):
        """export_audio_file creates any missing target directories."""
        src = tmp_path / "src.mp3"
        src.write_bytes(single_frame_mp3)
        dest = tmp_path / "deeply" / "nested" / "output.mp3"

        out_path = export_audio_file(str(src), str(dest))
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) == len(single_frame_mp3)


# ==============================================================================
# 3. Document Extractor Error Boundaries & Corruption Handling
# ==============================================================================
class TestDocumentExtractorErrorBoundaries:
    """Stress tests DocumentExtractor with invalid PDFs, encrypted PDFs, corrupted encodings, and edge cases."""

    def test_pdf_0_byte_raises_extraction_error(self, tmp_path):
        """0-byte PDF file must raise DocumentExtractionError cleanly."""
        pdf_file = tmp_path / "zero_byte.pdf"
        pdf_file.write_bytes(b"")

        with pytest.raises(DocumentExtractionError) as exc_info:
            extract_text_from_pdf(str(pdf_file))
        assert "Failed to open or parse PDF" in str(exc_info.value) or "contains 0 pages" in str(
            exc_info.value
        )

    def test_pdf_corrupted_header_raises_extraction_error(self, tmp_path):
        """Corrupted PDF header / binary garbage raises DocumentExtractionError."""
        bad_pdf = tmp_path / "garbage.pdf"
        bad_pdf.write_bytes(b"NOT_A_REAL_PDF_HEADER_JUST_RANDOM_DATA_1234567890\x00\xff\xfe")

        with pytest.raises(DocumentExtractionError) as exc_info:
            extract_text_from_pdf(str(bad_pdf))
        assert "Failed to open or parse PDF" in str(exc_info.value)

    def test_pdf_encrypted_with_password_raises_extraction_error(self, tmp_path):
        """Password-protected PDF with non-blank password raises descriptive DocumentExtractionError."""
        encrypted_pdf = tmp_path / "encrypted.pdf"
        with patch("pypdf.PdfReader") as mock_reader_cls:
            mock_reader = MagicMock()
            mock_reader.is_encrypted = True
            from pypdf.errors import PdfReadError

            mock_reader.decrypt.side_effect = PdfReadError("Password required")
            mock_reader_cls.return_value = mock_reader

            encrypted_pdf.write_bytes(b"%PDF-1.4 simulated encrypted content")

            with pytest.raises(DocumentExtractionError) as exc_info:
                extract_text_from_pdf(str(encrypted_pdf))

            assert "password protected" in str(exc_info.value).lower()

    def test_pdf_with_page_extraction_partial_errors(self, tmp_path):
        """PDF where one page throws an error during extract_text continues extracting remaining pages."""
        pdf_file = tmp_path / "partial_fail.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 simulated")

        with patch("pypdf.PdfReader") as mock_reader_cls:
            mock_reader = MagicMock()
            mock_reader.is_encrypted = False
            page1 = MagicMock()
            page1.extract_text.side_effect = ValueError("Corrupt stream on page 1")
            page2 = MagicMock()
            page2.extract_text.return_value = "Valid extracted content on page 2 of document."

            mock_reader.pages = [page1, page2]
            mock_reader_cls.return_value = mock_reader

            text = extract_text_from_pdf(str(pdf_file))
            assert "Valid extracted content on page 2" in text

    def test_encodings_fallback_cp1252_norwegian_special_chars(self, tmp_path):
        """Verifies CP1252 encoded file with Scandinavian characters (æ, ø, å) extracts accurately."""
        cp1252_file = tmp_path / "norwegian_cp1252.txt"
        norwegian_text = (
            "Dette er en viktig test av norske tegn: Blåbærsyltetøy på brødskiven smaker godt."
        )
        cp1252_file.write_bytes(norwegian_text.encode("cp1252"))

        extracted = extract_text_from_file(str(cp1252_file))
        assert "Blåbærsyltetøy" in extracted
        assert "brødskiven" in extracted

    def test_encodings_fallback_latin1_iso8859_1(self, tmp_path):
        """Verifies Latin-1 / ISO-8859-1 encoded file extracts accurately."""
        latin1_file = tmp_path / "latin1_doc.txt"
        sample_text = "Résumé of François Müller: Über die Brücke und café crème."
        latin1_file.write_bytes(sample_text.encode("latin-1"))

        extracted = extract_text_from_file(str(latin1_file))
        assert "Résumé" in extracted
        assert "François" in extracted

    def test_corrupted_binary_text_file_errors_replace_fallback(self, tmp_path):
        """Text file with invalid raw bytes falls back to utf-8 replace without raising unhandled exceptions."""
        bad_text = tmp_path / "bad_bytes.txt"
        bad_bytes = (
            b"Valid start of text file "
            + b"\x80\x81\x82\xff\xfe"
            + b" and valid continuation text."
        )
        bad_text.write_bytes(bad_bytes)

        extracted = extract_text_from_file(str(bad_text))
        assert "Valid start of text file" in extracted
        assert "and valid continuation text" in extracted

    def test_extract_oversized_file_exceeding_mb_limit(self, tmp_path):
        """Files exceeding max_file_size_mb raise DocumentExtractionError immediately."""
        big_file = tmp_path / "oversized.txt"
        big_file.write_text("Hello world content exceeding 0 MB limit.")

        with pytest.raises(DocumentExtractionError) as exc_info:
            extract_text_from_file(str(big_file), max_file_size_mb=0)

        assert "exceeds the maximum allowed size" in str(exc_info.value)

    def test_extract_text_unified_entrypoint_robustness(self, tmp_path):
        """Tests unified extract_text with various input modalities, whitespace, and path edge cases."""
        assert (
            extract_text("This is valid raw text input directly.")
            == "This is valid raw text input directly."
        )
        assert (
            extract_text("Quantum Computing in 2026", is_topic=True) == "Quantum Computing in 2026"
        )

        with pytest.raises(DocumentExtractionError):
            extract_text(None)  # type: ignore

        with pytest.raises(DocumentExtractionError):
            extract_text("   \n\t  ")

        with pytest.raises(DocumentExtractionError) as exc:
            extract_text("non_existent_document.pdf")
        assert "not found" in str(exc.value).lower()

    def test_normalize_extracted_text_complex_unicode_and_hyphens(self):
        """Verifies dehyphenation, CRLF normalization, and Unicode space cleanup."""
        raw = "This is an auto-\nmatic process with non\xa0breaking spaces and \r\n\r\n\r\n\r\nexcessive newlines."
        normalized = normalize_extracted_text(raw)
        assert "automatic" in normalized
        assert "non breaking spaces" in normalized
        assert "\r" not in normalized
        assert "\n\n\n" not in normalized
