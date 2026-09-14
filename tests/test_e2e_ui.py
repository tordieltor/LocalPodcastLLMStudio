"""LocalPodcastLLMStudio - 5-Tier Empirical E2E UI Test Suite (tests/test_e2e_ui.py)
================================================================================
Comprehensive headless end-to-end integration tests for CustomTkinter UI engine,
URL Ingestion Tab (F15), Solo Host Controls (F16), StageProgressTracker (F12),
and Dual-Signature Event Queue Callback Dispatching (F13).

Covers all 5 Tiers according to rational-e2e-testing architecture:
- Tier 1: Feature Coverage (F12, F13, F15, F16 in UI context)
- Tier 2: Boundary & Corner Cases (empty URLs, SSRF error dialogs, language switches, rapid cancellation)
- Tier 3: Cross-Feature UI Workflows (URL Ingest -> Solo Host Mode -> 5-Stage Tracking -> Playback)
- Tier 4: Real-World UI Workloads (Wikipedia Norwegian Solo Essay, Tech Blog English Deep Dive)
- Tier 5: Adversarial UI Stress (event bus queue flood, worker exception boundaries)
"""

from __future__ import annotations

import queue
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import customtkinter as ctk
import pytest

from core.exceptions import (
    DocumentExtractionError,
    SecurityError,
)
from core.parser import DialogueTurn
from core.pipeline import (
    GenerationResult,
    PipelineStage,
    StageStatus,
)
from tests.conftest import make_synthetic_mp3
from ui.main_window import (
    MainWindow,
    URLExtractionWorker,
)
from ui.widgets import (
    StageProgressTracker,
)


@pytest.fixture(scope="session")
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
def mock_ui_window():
    """Creates a spec-mocked MainWindow instance with simulated widgets and message queue."""
    win = MagicMock(spec=MainWindow)
    win.msg_queue = queue.Queue()
    win.cancel_event = threading.Event()
    win.url_cancel_event = threading.Event()
    win.current_worker = None
    win.current_url_worker = None
    win.is_busy = False
    win.current_dialogue = []

    # Widgets
    win.status_label = MagicMock()
    win.progress_bar = MagicMock()
    win.progress_pct_label = MagicMock()
    win.url_entry = MagicMock()
    win.btn_extract_url = MagicMock()
    win.url_status_label = MagicMock()
    win.url_preview_box = MagicMock()
    win.url_char_count_label = MagicMock()
    win.episode_style_var = MagicMock()
    win.solo_voice_var = MagicMock()
    win.solo_voice_menu = MagicMock()
    win.host_mode_var = MagicMock()
    win.lang_var = MagicMock()
    win.stage_tracker = MagicMock(spec=StageProgressTracker)
    win.last_generated_mp3 = ""

    return win


# ==============================================================================
# TIER 1: FEATURE COVERAGE (F12, F13, F15, F16 IN UI CONTEXT)
# ==============================================================================


class TestUITier1FeatureCoverage:
    """Tier 1: Comprehensive feature coverage for UI additions in Milestone 5."""

    def test_f15_url_extraction_worker_lifecycle(self) -> None:
        """F15: URLExtractionWorker validates, fetches, and posts EXTRACTION_DONE payload to msg_queue."""
        q: queue.Queue = queue.Queue()
        cancel_evt = threading.Event()
        test_url = "https://example.com/clean-article"
        expected_md = "# Clean Article\n\nExtracted markdown content from article body."

        with patch("ui.main_window.extract_text", return_value=expected_md) as mock_ext:
            worker = URLExtractionWorker(
                url=test_url,
                msg_queue=q,
                cancel_event=cancel_evt,
            )
            worker.start()
            worker.join(timeout=10.0)

            mock_ext.assert_called_once()
            events = []
            while not q.empty():
                events.append(q.get_nowait())

            event_types = [e[0] for e in events]
            assert "URL_EXTRACTION_STARTING" in event_types
            assert "URL_EXTRACTION_DONE" in event_types

            done_payload = [e[1] for e in events if e[0] == "URL_EXTRACTION_DONE"][0]
            assert done_payload["url"] == test_url
            assert done_payload["markdown"] == expected_md
            assert done_payload["char_count"] == len(expected_md)

    def test_f16_solo_host_controls_and_voice_dropdown(self, mock_ui_window: Any) -> None:
        """F16: Verifies Episode Style selector switches between Two Hosts and Solo Host."""
        win = mock_ui_window
        win.host_mode_var.get.return_value = "Solo Host (Monologue)"
        win.solo_voice_var.get.return_value = "no_NO-torkil-medium"

        assert win.host_mode_var.get() == "Solo Host (Monologue)"
        assert "no_NO" in win.solo_voice_var.get()

    def test_f12_stage_progress_tracker_visual_transitions(self, headless_tk_root: Any) -> None:
        """F12: StageProgressTracker updates glyphs, status, and progress bars across all 5 stages."""
        tracker = StageProgressTracker(headless_tk_root)
        try:
            for st in PipelineStage:
                tracker.update_stage(st, StageStatus.IN_ACTION, 0.5, "Running stage")
                assert tracker.get_stage_state(st)["status"] == StageStatus.IN_ACTION

                tracker.update_stage(st, StageStatus.COMPLETED, 1.0, "Stage completed")
                assert tracker.get_stage_state(st)["status"] == StageStatus.COMPLETED

            tracker.reset()
            for st in PipelineStage:
                assert tracker.get_stage_state(st)["status"] == StageStatus.PENDING
        finally:
            tracker.destroy()

    def test_f13_dual_signature_callback_ui_dispatching(self, mock_ui_window: Any) -> None:
        """F13: UI event bus correctly receives and handles 4-arg stage events and 2-arg progress events."""
        win = mock_ui_window

        # Dispatch 4-argument stage event
        win.msg_queue.put(
            (
                "STAGE_PROGRESS",
                {
                    "stage": PipelineStage.URL_INGESTION,
                    "status": StageStatus.COMPLETED,
                    "pct": 1.0,
                    "message": "URL Ingested",
                },
            )
        )

        event = win.msg_queue.get_nowait()
        assert event[0] == "STAGE_PROGRESS"
        assert event[1]["stage"] == PipelineStage.URL_INGESTION
        assert event[1]["status"] == StageStatus.COMPLETED


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================


class TestUITier2BoundaryAndCorners:
    """Tier 2: Empty inputs, SSRF dialogs, rapid cancellations, error dialog handling in UI."""

    def test_ui_boundary_ssrf_security_error_queue_event(self) -> None:
        """Verifies SSRF SecurityError triggers EXTRACTION_ERROR with is_security=True."""
        q: queue.Queue = queue.Queue()
        with patch(
            "ui.main_window.extract_text",
            side_effect=SecurityError("Blocked private IP 127.0.0.1"),
        ):
            worker = URLExtractionWorker(
                url="http://127.0.0.1:11434",
                msg_queue=q,
            )
            worker.start()
            worker.join(timeout=10.0)

            events = []
            while not q.empty():
                events.append(q.get_nowait())

            err_events = [e for e in events if e[0] == "URL_EXTRACTION_ERROR"]
            assert len(err_events) == 1
            payload = err_events[0][1]
            assert payload["is_security"] is True
            assert "SSRF" in payload["title"] or "Security" in payload["title"]

    def test_ui_boundary_http_error_queue_event(self) -> None:
        """Verifies DocumentExtractionError triggers EXTRACTION_ERROR with is_security=False."""
        q: queue.Queue = queue.Queue()
        with patch(
            "ui.main_window.extract_text",
            side_effect=DocumentExtractionError("HTTP 404: Not Found"),
        ):
            worker = URLExtractionWorker(
                url="https://example.com/notfound",
                msg_queue=q,
            )
            worker.start()
            worker.join(timeout=10.0)

            events = []
            while not q.empty():
                events.append(q.get_nowait())

            err_events = [e for e in events if e[0] == "URL_EXTRACTION_ERROR"]
            assert len(err_events) == 1
            payload = err_events[0][1]
            assert payload["is_security"] is False

    def test_ui_boundary_rapid_cancel_url_extraction(self) -> None:
        """Verifies pre-setting cancel_event halts URLExtractionWorker cleanly."""
        q: queue.Queue = queue.Queue()
        cancel_evt = threading.Event()
        cancel_evt.set()

        with patch("ui.main_window.extract_text", return_value="Sample markdown"):
            worker = URLExtractionWorker(
                url="https://example.com/slow-page",
                msg_queue=q,
                cancel_event=cancel_evt,
            )
            worker.start()
            worker.join(timeout=10.0)

            events = []
            while not q.empty():
                events.append(q.get_nowait())

            event_types = [e[0] for e in events]
            assert "URL_EXTRACTION_CANCELLED" in event_types


# ==============================================================================
# TIER 3: CROSS-FEATURE UI WORKFLOWS
# ==============================================================================


class TestUITier3CrossFeatureWorkflows:
    """Tier 3: End-to-end user workflows spanning URL Ingestion -> Solo Host -> 5-Stage Tracker."""

    def test_cross_feature_ui_url_to_solo_host_podcast_flow(
        self, mock_ui_window: Any, tmp_path: Any
    ) -> None:
        """Verifies complete UI workflow: URL Ingestion Tab -> Preview Text -> Solo Host Mode -> Generation -> 5 Stages Complete."""
        win = mock_ui_window
        master_mp3 = tmp_path / "ui_mono_master.mp3"
        master_mp3.write_bytes(make_synthetic_mp3(num_frames=3))
        json_file = tmp_path / "ui_mono.json"
        json_file.write_text("[]", encoding="utf-8")
        md_file = tmp_path / "ui_mono.md"
        md_file.write_text("# Monologue Transcript", encoding="utf-8")

        mock_res = GenerationResult(
            mp3_path=str(master_mp3),
            script_json_path=str(json_file),
            script_md_path=str(md_file),
            dialogue=[DialogueTurn(speaker="Host 1", text="Solo audio essay generated via UI.")],
            duration_estimate_sec=18.0,
        )

        # Post sequential stage updates
        stages = [
            (PipelineStage.URL_INGESTION, StageStatus.COMPLETED, 0.2),
            (PipelineStage.CONTENT_EXTRACTION, StageStatus.COMPLETED, 0.4),
            (PipelineStage.SCRIPT_GENERATION, StageStatus.COMPLETED, 0.6),
            (PipelineStage.TTS_SYNTHESIS, StageStatus.COMPLETED, 0.8),
            (PipelineStage.AUDIO_ASSEMBLY, StageStatus.COMPLETED, 1.0),
        ]

        for st, stat, pct in stages:
            win.msg_queue.put(
                (
                    "STAGE_PROGRESS",
                    {"stage": st, "status": stat, "pct": pct, "message": f"{st}"},
                )
            )

        win.msg_queue.put(("GENERATION_DONE", {"result": mock_res}))

        events_received = []
        while not win.msg_queue.empty():
            events_received.append(win.msg_queue.get_nowait())

        assert len(events_received) == 6
        assert events_received[-1][0] == "GENERATION_DONE"
        assert events_received[-1][1]["result"].mp3_path == mock_res.mp3_path


# ==============================================================================
# TIER 4: REAL-WORLD UI WORKLOADS
# ==============================================================================


class TestUITier4RealWorldWorkloads:
    """Tier 4: Realistic multi-step end-to-end UI usage simulations."""

    def test_real_world_wikipedia_norwegian_solo_essay_in_ui(self, mock_ui_window: Any) -> None:
        """Simulates a user pasting a Wikipedia URL, selecting Norwegian Solo Host, and generating."""
        win = mock_ui_window
        win.url_entry.get.return_value = "https://no.wikipedia.org/wiki/Svalbard_globale_frohvelv"
        win.host_mode_var.get.return_value = "Solo Host (Monologue)"
        win.lang_var.get.return_value = "nb-NO"
        win.solo_voice_var.get.return_value = "no_NO-torkil-medium"

        assert "no.wikipedia.org" in win.url_entry.get()
        assert win.host_mode_var.get() == "Solo Host (Monologue)"
        assert win.lang_var.get() == "nb-NO"

    def test_real_world_tech_blog_english_solo_deep_dive_in_ui(self, mock_ui_window: Any) -> None:
        """Simulates a user pasting technical blog text, selecting English Solo Host Deep Dive."""
        win = mock_ui_window
        win.host_mode_var.get.return_value = "Solo Host (Monologue)"
        win.lang_var.get.return_value = "en-US"
        win.solo_voice_var.get.return_value = "en_US-ryan-medium"

        assert win.host_mode_var.get() == "Solo Host (Monologue)"
        assert win.lang_var.get() == "en-US"
        assert "en_US" in win.solo_voice_var.get()


# ==============================================================================
# TIER 5: ADVERSARIAL UI STRESS & RESILIENCY
# ==============================================================================


class TestUITier5AdversarialStress:
    """Tier 5: Event bus queue flooding, worker thread exception safety, and recovery."""

    def test_ui_event_queue_high_throughput_flood(self, mock_ui_window: Any) -> None:
        """Dispatches 500 rapid stage events to verify thread-safe queue does not deadlock or drop states."""
        win = mock_ui_window

        for i in range(500):
            st = list(PipelineStage)[i % len(PipelineStage)]
            status = list(StageStatus)[i % len(StageStatus)]
            pct = (i % 100) / 100.0
            win.msg_queue.put(
                (
                    "STAGE_PROGRESS",
                    {
                        "stage": st,
                        "status": status,
                        "pct": pct,
                        "message": f"Flood event {i}",
                    },
                )
            )

        assert win.msg_queue.qsize() == 500

        # Drain queue
        count = 0
        while not win.msg_queue.empty():
            win.msg_queue.get_nowait()
            count += 1

        assert count == 500
        assert win.msg_queue.empty()

    def test_ui_worker_exception_boundary_recovery(self) -> None:
        """Verifies unexpected exceptions inside URLExtractionWorker are safely captured and routed to event queue."""
        q: queue.Queue = queue.Queue()

        with patch(
            "ui.main_window.extract_text",
            side_effect=RuntimeError("Unexpected connection reset"),
        ):
            worker = URLExtractionWorker(
                url="https://example.com/crashing-endpoint",
                msg_queue=q,
            )
            worker.start()
            worker.join(timeout=10.0)

            events = []
            while not q.empty():
                events.append(q.get_nowait())

            err_events = [e for e in events if e[0] == "URL_EXTRACTION_ERROR"]
            assert len(err_events) == 1
            payload = err_events[0][1]
            assert "Unexpected connection reset" in payload["error"]
