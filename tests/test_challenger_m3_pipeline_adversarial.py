"""
Empirical Adversarial Test Suite for Pipeline Lifecycle & Failure Handling
==========================================================================
Challenger 1: Milestone 3 Verification Battery
Framework: rational-e2e-testing (5-tier empirical architecture)

Covers:
1. Strict Monotonic Stage Progression (URL and Non-URL inputs, ordinal checks, percentage monotonicity).
2. Cancellation Injection across all 5 stages (Stage 1, 2, 3, 4, 5 and immediate pre-set cancellation).
3. Exception Injection across all 5 stages (SecurityError, DocumentExtractionError, OllamaConnectionError,
   AudioSynthesisError, AudioStitchingError, unexpected exceptions) asserting FAILED status and error attribution.
4. Monologue vs Dialogue Voice Mapping & Speaker Normalization (HostMode permutations, solo_voice propagation,
   markdown transcript rendering).
5. Adversarial Callback Fault-Tolerance & Percentage Clamping.
"""

from __future__ import annotations

import os
import threading
from typing import Any
from unittest.mock import patch

import pytest

from core.exceptions import (
    AudioStitchingError,
    AudioSynthesisError,
    DocumentExtractionError,
    LLMServiceError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    SecurityError,
)
from core.parser import DialogueTurn
from core.pipeline import (
    GenerationOptions,
    PipelineStage,
    PodcastGeneratorService,
    StageStatus,
)


class ComprehensiveStageAuditor:
    """Detailed auditor recording full event stream with validation utilities."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.events: list[dict[str, Any]] = []

    def __call__(
        self,
        stage: PipelineStage | int,
        status: StageStatus | str,
        pct: float,
        msg: str,
    ) -> None:
        with self.lock:
            s_stage = PipelineStage(stage) if not isinstance(stage, PipelineStage) else stage
            s_status = StageStatus(status) if not isinstance(status, StageStatus) else status
            self.events.append(
                {
                    "stage": s_stage,
                    "status": s_status,
                    "pct": float(pct),
                    "msg": str(msg),
                }
            )

    @property
    def stage_sequence(self) -> list[PipelineStage]:
        with self.lock:
            seen: list[PipelineStage] = []
            for ev in self.events:
                if not seen or seen[-1] != ev["stage"]:
                    seen.append(ev["stage"])
            return seen

    @property
    def final_status_per_stage(self) -> dict[PipelineStage, StageStatus]:
        with self.lock:
            statuses: dict[PipelineStage, StageStatus] = {}
            for ev in self.events:
                statuses[ev["stage"]] = ev["status"]
            return statuses

    def get_events_for_stage(self, stage: PipelineStage) -> list[dict[str, Any]]:
        with self.lock:
            return [ev for ev in self.events if ev["stage"] == stage]

    def assert_strictly_monotonic_stages(self) -> None:
        seq = self.stage_sequence
        for i in range(len(seq) - 1):
            assert seq[i] < seq[i + 1], (
                f"Non-monotonic stage sequence: {seq[i].name} ({int(seq[i])}) before {seq[i + 1].name} ({int(seq[i + 1])})"
            )

    def assert_percentage_monotonic_and_bounded(self) -> None:
        with self.lock:
            last_pct = 0.0
            for ev in self.events:
                pct = ev["pct"]
                assert 0.0 <= pct <= 1.0, f"Percentage {pct} out of [0.0, 1.0] bounds in {ev}"
                assert pct >= last_pct - 1e-6, (
                    f"Percentage decreased from {last_pct} to {pct} in {ev}"
                )
                last_pct = pct


# ==============================================================================
# 1. Pipeline Stage Sequencing: Strict Monotonic Progression
# ==============================================================================
class TestAdversarialStageSequencing:
    """Verifies strict ordinal progression across all 5 stages."""

    @pytest.fixture
    def mock_full_pipeline_env(self, tmp_path: Any):
        out_dir = str(tmp_path / "stage_seq_out")
        os.makedirs(out_dir, exist_ok=True)
        dialogue = [
            DialogueTurn(speaker="Host 1", text="Welcome to empirical podcasting!"),
            DialogueTurn(speaker="Host 2", text="Glad to be here!"),
        ]
        audio_files = [os.path.join(out_dir, "turn_0.mp3"), os.path.join(out_dir, "turn_1.mp3")]
        master_mp3 = os.path.join(out_dir, "podcast.mp3")
        with open(master_mp3, "wb") as f:
            f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x44")

        with (
            patch("core.pipeline.extract_text", return_value="Extracted text from doc") as m_ext,
            patch("core.pipeline.generate_podcast_script", return_value=dialogue) as m_script,
            patch("core.pipeline.synthesize_dialogue_audio", return_value=audio_files) as m_tts,
            patch("core.pipeline.stitch_mp3_files", return_value=master_mp3) as m_stitch,
        ):
            yield {
                "extract": m_ext,
                "script": m_script,
                "tts": m_tts,
                "stitch": m_stitch,
                "out_dir": out_dir,
                "master_mp3": master_mp3,
                "dialogue": dialogue,
            }

    def test_strict_monotonic_progression_url_mode(
        self, mock_full_pipeline_env: dict[str, Any]
    ) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        opts = GenerationOptions(
            content="https://secure.example.com/article",
            is_url=True,
            output_dir=mock_full_pipeline_env["out_dir"],
        )

        result = service.generate_podcast(options=opts, stage_callback=auditor)

        assert result.mp3_path == mock_full_pipeline_env["master_mp3"]
        auditor.assert_strictly_monotonic_stages()
        auditor.assert_percentage_monotonic_and_bounded()

        # All 5 stages reached in order
        expected_seq = [
            PipelineStage.URL_INGESTION,
            PipelineStage.CONTENT_EXTRACTION,
            PipelineStage.SCRIPT_GENERATION,
            PipelineStage.TTS_SYNTHESIS,
            PipelineStage.AUDIO_ASSEMBLY,
        ]
        assert auditor.stage_sequence == expected_seq

        # Each stage transitioned IN_ACTION -> COMPLETED
        for stage in expected_seq:
            events = auditor.get_events_for_stage(stage)
            statuses = [e["status"] for e in events]
            assert StageStatus.IN_ACTION in statuses, f"{stage.name} missed IN_ACTION"
            assert StageStatus.COMPLETED in statuses, f"{stage.name} missed COMPLETED"
            assert statuses[-1] == StageStatus.COMPLETED

    def test_strict_monotonic_progression_topic_and_raw_text(
        self, mock_full_pipeline_env: dict[str, Any]
    ) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        opts = GenerationOptions(
            content="Quantum computing basics and cryptographic implications",
            is_topic=True,
            output_dir=mock_full_pipeline_env["out_dir"],
        )

        result = service.generate_podcast(options=opts, stage_callback=auditor)

        assert result.mp3_path == mock_full_pipeline_env["master_mp3"]
        auditor.assert_strictly_monotonic_stages()
        auditor.assert_percentage_monotonic_and_bounded()

        expected_seq = [
            PipelineStage.URL_INGESTION,
            PipelineStage.CONTENT_EXTRACTION,
            PipelineStage.SCRIPT_GENERATION,
            PipelineStage.TTS_SYNTHESIS,
            PipelineStage.AUDIO_ASSEMBLY,
        ]
        assert auditor.stage_sequence == expected_seq


# ==============================================================================
# 2. Cancellation Injection: Stage-by-Stage Verification
# ==============================================================================
class TestAdversarialCancellationInjection:
    """Verifies responsive cancellation at every individual stage and asserts downstream remains PENDING."""

    @pytest.fixture
    def mock_env(self, tmp_path: Any):
        out_dir = str(tmp_path / "cancel_out")
        os.makedirs(out_dir, exist_ok=True)
        return {"out_dir": out_dir}

    def test_cancellation_pre_set_immediate(self, mock_env: dict[str, Any]) -> None:
        """Cancel event set before generation starts."""
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        cancel_ev = threading.Event()
        cancel_ev.set()

        opts = GenerationOptions(
            content="https://example.com/fast-cancel",
            is_url=True,
            output_dir=mock_env["out_dir"],
        )

        with pytest.raises(RuntimeError, match="Generation cancelled by user"):
            service.generate_podcast(
                options=opts,
                stage_callback=auditor,
                cancel_event=cancel_ev,
            )

        # Stage 1 must be CANCELLED
        events_s1 = auditor.get_events_for_stage(PipelineStage.URL_INGESTION)
        assert any(e["status"] == StageStatus.CANCELLED for e in events_s1)

        # Stages 2-5 must NOT be touched
        assert len(auditor.get_events_for_stage(PipelineStage.CONTENT_EXTRACTION)) == 0
        assert len(auditor.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)) == 0
        assert len(auditor.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)) == 0
        assert len(auditor.get_events_for_stage(PipelineStage.AUDIO_ASSEMBLY)) == 0

    def test_cancellation_injection_stage1_url_fetch(self, mock_env: dict[str, Any]) -> None:
        """Cancel event triggered during Stage 1 URL ingestion."""
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        cancel_ev = threading.Event()

        def fake_extract_url(*args: Any, **kwargs: Any) -> str:
            cancel_ev.set()
            prog = kwargs.get("progress_callback")
            if prog:
                prog("Fetching remote HTML...")
            return "Some fetched HTML"

        opts = GenerationOptions(
            content="https://example.com/stage1-cancel",
            is_url=True,
            output_dir=mock_env["out_dir"],
        )

        with patch("core.pipeline.extract_text", side_effect=fake_extract_url):
            with pytest.raises(RuntimeError, match="Generation cancelled by user"):
                service.generate_podcast(
                    options=opts,
                    stage_callback=auditor,
                    cancel_event=cancel_ev,
                )

        assert (
            auditor.final_status_per_stage.get(PipelineStage.URL_INGESTION) == StageStatus.CANCELLED
        )
        assert len(auditor.get_events_for_stage(PipelineStage.CONTENT_EXTRACTION)) == 0
        assert len(auditor.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)) == 0

    def test_cancellation_injection_stage2_content_extraction(
        self, mock_env: dict[str, Any]
    ) -> None:
        """Cancel event triggered during Stage 2 document extraction."""
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        cancel_ev = threading.Event()

        def fake_extract_doc(*args: Any, **kwargs: Any) -> str:
            if not kwargs.get("is_url", False):
                cancel_ev.set()
            return "Extracted document text"

        opts = GenerationOptions(
            content="local_doc.pdf",
            is_raw_text=False,
            output_dir=mock_env["out_dir"],
        )

        with patch("core.pipeline.extract_text", side_effect=fake_extract_doc):
            with pytest.raises(RuntimeError, match="Generation cancelled by user"):
                service.generate_podcast(
                    options=opts,
                    stage_callback=auditor,
                    cancel_event=cancel_ev,
                )

        assert (
            auditor.final_status_per_stage.get(PipelineStage.CONTENT_EXTRACTION)
            == StageStatus.CANCELLED
        )
        assert len(auditor.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)) == 0
        assert len(auditor.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)) == 0

    def test_cancellation_injection_stage3_script_generation(
        self, mock_env: dict[str, Any]
    ) -> None:
        """Cancel event triggered during Stage 3 LLM script generation."""
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        cancel_ev = threading.Event()

        def fake_generate_script(*args: Any, **kwargs: Any) -> list[DialogueTurn]:
            cancel_ev.set()
            ev = kwargs.get("cancel_event")
            if ev and ev.is_set():
                raise RuntimeError("Generation cancelled by user.")
            return []

        opts = GenerationOptions(
            content="Raw content",
            is_raw_text=True,
            output_dir=mock_env["out_dir"],
        )

        with (
            patch("core.pipeline.extract_text", return_value="Raw content"),
            patch("core.pipeline.generate_podcast_script", side_effect=fake_generate_script),
        ):
            with pytest.raises(RuntimeError, match="Generation cancelled by user"):
                service.generate_podcast(
                    options=opts,
                    stage_callback=auditor,
                    cancel_event=cancel_ev,
                )

        assert (
            auditor.final_status_per_stage.get(PipelineStage.SCRIPT_GENERATION)
            == StageStatus.CANCELLED
        )
        assert len(auditor.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)) == 0
        assert len(auditor.get_events_for_stage(PipelineStage.AUDIO_ASSEMBLY)) == 0

    def test_cancellation_injection_stage4_tts_synthesis(self, mock_env: dict[str, Any]) -> None:
        """Cancel event triggered during Stage 4 TTS synthesis."""
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        cancel_ev = threading.Event()
        turns = [
            DialogueTurn(speaker="Host 1", text="Turn 1"),
            DialogueTurn(speaker="Host 2", text="Turn 2"),
        ]

        def fake_synth_audio(*args: Any, **kwargs: Any) -> list[str]:
            cancel_ev.set()
            ev = kwargs.get("cancel_event")
            if ev and ev.is_set():
                raise RuntimeError("Generation cancelled by user.")
            return []

        opts = GenerationOptions(
            content="Raw content",
            is_raw_text=True,
            output_dir=mock_env["out_dir"],
        )

        with (
            patch("core.pipeline.extract_text", return_value="Raw content"),
            patch("core.pipeline.generate_podcast_script", return_value=turns),
            patch("core.pipeline.synthesize_dialogue_audio", side_effect=fake_synth_audio),
        ):
            with pytest.raises(RuntimeError, match="Generation cancelled by user"):
                service.generate_podcast(
                    options=opts,
                    stage_callback=auditor,
                    cancel_event=cancel_ev,
                )

        assert (
            auditor.final_status_per_stage.get(PipelineStage.TTS_SYNTHESIS) == StageStatus.CANCELLED
        )
        assert len(auditor.get_events_for_stage(PipelineStage.AUDIO_ASSEMBLY)) == 0

    def test_cancellation_injection_stage5_audio_assembly(self, mock_env: dict[str, Any]) -> None:
        """Cancel event triggered right before or during Stage 5 audio assembly."""
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        cancel_ev = threading.Event()
        turns = [DialogueTurn(speaker="Host 1", text="Turn 1")]
        audio_files = ["/tmp/turn1.mp3"]

        def fake_stitch(*args: Any, **kwargs: Any) -> str:
            cancel_ev.set()
            raise RuntimeError("Generation cancelled by user.")

        opts = GenerationOptions(
            content="Raw content",
            is_raw_text=True,
            output_dir=mock_env["out_dir"],
        )

        with (
            patch("core.pipeline.extract_text", return_value="Raw content"),
            patch("core.pipeline.generate_podcast_script", return_value=turns),
            patch("core.pipeline.synthesize_dialogue_audio", return_value=audio_files),
            patch("core.pipeline.stitch_mp3_files", side_effect=fake_stitch),
        ):
            with pytest.raises(RuntimeError, match="Generation cancelled by user"):
                service.generate_podcast(
                    options=opts,
                    stage_callback=auditor,
                    cancel_event=cancel_ev,
                )

        assert (
            auditor.final_status_per_stage.get(PipelineStage.AUDIO_ASSEMBLY)
            == StageStatus.CANCELLED
        )


# ==============================================================================
# 3. Exception Injection across All Stages
# ==============================================================================
class TestAdversarialExceptionInjection:
    """Verifies domain and unexpected exceptions cause active stage to mark FAILED and record error metadata."""

    @pytest.fixture
    def mock_env(self, tmp_path: Any):
        out_dir = str(tmp_path / "exc_out")
        os.makedirs(out_dir, exist_ok=True)
        return {"out_dir": out_dir}

    def test_stage1_security_error_ssrf_attribution(self, mock_env: dict[str, Any]) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        opts = GenerationOptions(
            content="http://169.254.169.254/latest/meta-data/",
            is_url=True,
            output_dir=mock_env["out_dir"],
        )

        with patch(
            "core.pipeline.extract_text",
            side_effect=SecurityError("Blocked AWS metadata IP 169.254.169.254"),
        ):
            with pytest.raises(SecurityError, match="Blocked AWS metadata"):
                service.generate_podcast(options=opts, stage_callback=auditor)

        events_s1 = auditor.get_events_for_stage(PipelineStage.URL_INGESTION)
        failed_ev = next(e for e in events_s1 if e["status"] == StageStatus.FAILED)
        assert "Blocked AWS metadata" in failed_ev["msg"]
        assert "URL_INGESTION" in failed_ev["msg"]
        assert len(auditor.get_events_for_stage(PipelineStage.CONTENT_EXTRACTION)) == 0

    def test_stage1_download_timeout_document_extraction_error(
        self, mock_env: dict[str, Any]
    ) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        opts = GenerationOptions(
            content="https://slow-site.com/huge.html",
            is_url=True,
            output_dir=mock_env["out_dir"],
        )

        with patch(
            "core.pipeline.extract_text",
            side_effect=DocumentExtractionError("HTTP request timed out after 10.0s"),
        ):
            with pytest.raises(DocumentExtractionError, match="timed out"):
                service.generate_podcast(options=opts, stage_callback=auditor)

        events_s1 = auditor.get_events_for_stage(PipelineStage.URL_INGESTION)
        failed_ev = next(e for e in events_s1 if e["status"] == StageStatus.FAILED)
        assert "timed out" in failed_ev["msg"]

    def test_stage2_corrupt_file_document_extraction_error(self, mock_env: dict[str, Any]) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        opts = GenerationOptions(
            content="corrupt_document.pdf",
            is_raw_text=False,
            output_dir=mock_env["out_dir"],
        )

        with patch(
            "core.pipeline.extract_text",
            side_effect=DocumentExtractionError("Corrupt PDF EOF marker missing"),
        ):
            with pytest.raises(DocumentExtractionError, match="Corrupt PDF"):
                service.generate_podcast(options=opts, stage_callback=auditor)

        # Stage 1 was completed (non-url inspected), Stage 2 failed
        assert (
            auditor.final_status_per_stage.get(PipelineStage.URL_INGESTION) == StageStatus.COMPLETED
        )
        assert (
            auditor.final_status_per_stage.get(PipelineStage.CONTENT_EXTRACTION)
            == StageStatus.FAILED
        )
        assert len(auditor.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)) == 0

    def test_stage3_ollama_model_not_found_error(self, mock_env: dict[str, Any]) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        opts = GenerationOptions(
            content="Valid content text",
            model="nonexistent:model",
            is_raw_text=True,
            output_dir=mock_env["out_dir"],
        )

        with (
            patch("core.pipeline.extract_text", return_value="Valid text"),
            patch(
                "core.pipeline.generate_podcast_script",
                side_effect=OllamaModelNotFoundError(
                    "Model 'nonexistent:model' not found on Ollama server."
                ),
            ),
        ):
            with pytest.raises(OllamaModelNotFoundError, match="not found"):
                service.generate_podcast(options=opts, stage_callback=auditor)

        assert (
            auditor.final_status_per_stage.get(PipelineStage.SCRIPT_GENERATION)
            == StageStatus.FAILED
        )
        failed_ev = next(
            e
            for e in auditor.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)
            if e["status"] == StageStatus.FAILED
        )
        assert "nonexistent:model" in failed_ev["msg"]
        assert len(auditor.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)) == 0

    def test_stage3_ollama_connection_error(self, mock_env: dict[str, Any]) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        opts = GenerationOptions(
            content="Valid content text",
            is_raw_text=True,
            output_dir=mock_env["out_dir"],
        )

        with (
            patch("core.pipeline.extract_text", return_value="Valid text"),
            patch(
                "core.pipeline.generate_podcast_script",
                side_effect=OllamaConnectionError(
                    "Connection refused to Ollama server at http://localhost:11434"
                ),
            ),
        ):
            with pytest.raises(OllamaConnectionError, match="Connection refused"):
                service.generate_podcast(options=opts, stage_callback=auditor)

        assert (
            auditor.final_status_per_stage.get(PipelineStage.SCRIPT_GENERATION)
            == StageStatus.FAILED
        )
        failed_ev = next(
            e
            for e in auditor.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)
            if e["status"] == StageStatus.FAILED
        )
        assert "Connection refused" in failed_ev["msg"]
        assert len(auditor.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)) == 0

    def test_stage3_generic_llm_service_error(self, mock_env: dict[str, Any]) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        opts = GenerationOptions(
            content="Valid content text",
            is_raw_text=True,
            output_dir=mock_env["out_dir"],
        )

        with (
            patch("core.pipeline.extract_text", return_value="Valid text"),
            patch(
                "core.pipeline.generate_podcast_script",
                side_effect=LLMServiceError("Context window length exceeded 131072 tokens"),
            ),
        ):
            with pytest.raises(LLMServiceError, match="Context window"):
                service.generate_podcast(options=opts, stage_callback=auditor)

        assert (
            auditor.final_status_per_stage.get(PipelineStage.SCRIPT_GENERATION)
            == StageStatus.FAILED
        )

    def test_stage4_audio_synthesis_error(self, mock_env: dict[str, Any]) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        turns = [DialogueTurn(speaker="Host 1", text="Hello")]
        opts = GenerationOptions(
            content="Valid content text",
            is_raw_text=True,
            output_dir=mock_env["out_dir"],
        )

        with (
            patch("core.pipeline.extract_text", return_value="Valid text"),
            patch("core.pipeline.generate_podcast_script", return_value=turns),
            patch(
                "core.pipeline.synthesize_dialogue_audio",
                side_effect=AudioSynthesisError("Piper TTS binary exited with returncode -9 (OOM)"),
            ),
        ):
            with pytest.raises(AudioSynthesisError, match="Piper TTS binary exited"):
                service.generate_podcast(options=opts, stage_callback=auditor)

        assert auditor.final_status_per_stage.get(PipelineStage.TTS_SYNTHESIS) == StageStatus.FAILED
        failed_ev = next(
            e
            for e in auditor.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)
            if e["status"] == StageStatus.FAILED
        )
        assert "OOM" in failed_ev["msg"]
        assert len(auditor.get_events_for_stage(PipelineStage.AUDIO_ASSEMBLY)) == 0

    def test_stage5_audio_stitching_error(self, mock_env: dict[str, Any]) -> None:
        service = PodcastGeneratorService()
        auditor = ComprehensiveStageAuditor()
        turns = [DialogueTurn(speaker="Host 1", text="Hello")]
        opts = GenerationOptions(
            content="Valid content text",
            is_raw_text=True,
            output_dir=mock_env["out_dir"],
        )

        with (
            patch("core.pipeline.extract_text", return_value="Valid text"),
            patch("core.pipeline.generate_podcast_script", return_value=turns),
            patch("core.pipeline.synthesize_dialogue_audio", return_value=["/tmp/turn1.mp3"]),
            patch(
                "core.pipeline.stitch_mp3_files",
                side_effect=AudioStitchingError("Corrupted MPEG sync word at offset 0x002A"),
            ),
        ):
            with pytest.raises(AudioStitchingError, match="Corrupted MPEG sync word"):
                service.generate_podcast(options=opts, stage_callback=auditor)

        assert (
            auditor.final_status_per_stage.get(PipelineStage.AUDIO_ASSEMBLY) == StageStatus.FAILED
        )
        failed_ev = next(
            e
            for e in auditor.get_events_for_stage(PipelineStage.AUDIO_ASSEMBLY)
            if e["status"] == StageStatus.FAILED
        )
        assert "0x002A" in failed_ev["msg"]


# ==============================================================================
# 4. Monologue vs Dialogue Voice Mapping & Speaker Normalization
# ==============================================================================
class TestMonologueVsDialogueAdversarialMapping:
    """Stress tests monologue host mode normalization, solo voice routing, and speaker integrity."""

    @pytest.fixture
    def mock_pipeline_stubs(self, tmp_path: Any):
        out_dir = str(tmp_path / "mono_diag_out")
        os.makedirs(out_dir, exist_ok=True)
        master_mp3 = os.path.join(out_dir, "podcast.mp3")
        with open(master_mp3, "wb") as f:
            f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x44")

        with (
            patch("core.pipeline.extract_text", return_value="Extracted text") as m_ext,
            patch("core.pipeline.generate_podcast_script") as m_script,
            patch(
                "core.pipeline.synthesize_dialogue_audio",
                return_value=[os.path.join(out_dir, "turn_0.mp3")],
            ) as m_tts,
            patch("core.pipeline.stitch_mp3_files", return_value=master_mp3) as m_stitch,
        ):
            yield {
                "ext": m_ext,
                "script": m_script,
                "tts": m_tts,
                "stitch": m_stitch,
                "out_dir": out_dir,
            }

    @pytest.mark.parametrize(
        "raw_host_mode,expected_norm_mode",
        [
            ("monologue", "monologue"),
            ("MONOLOGUE", "monologue"),
            (" monologue ", "monologue"),
            ("audio_essay", "monologue"),
            ("solo", "monologue"),
            ("single_host", "monologue"),
            ("dialogue", "dialogue"),
            ("DIALOGUE", "dialogue"),
            ("two_hosts", "dialogue"),
            ("conversation", "dialogue"),
        ],
    )
    def test_host_mode_normalization_propagation(
        self,
        mock_pipeline_stubs: dict[str, Any],
        raw_host_mode: str,
        expected_norm_mode: str,
    ) -> None:
        service = PodcastGeneratorService()
        sample_turn = [DialogueTurn(speaker="Host 1", text="Essay opening line.")]
        mock_pipeline_stubs["script"].return_value = sample_turn

        opts = GenerationOptions(
            content="Article topic",
            is_topic=True,
            host_mode=raw_host_mode,
            solo_voice="nb_NO-tord-medium" if expected_norm_mode == "monologue" else None,
            output_dir=mock_pipeline_stubs["out_dir"],
        )

        result = service.generate_podcast(options=opts)

        assert len(result.dialogue) == 1
        _, script_kwargs = mock_pipeline_stubs["script"].call_args
        assert script_kwargs["host_mode"] == expected_norm_mode

        _, tts_kwargs = mock_pipeline_stubs["tts"].call_args
        if expected_norm_mode == "monologue":
            assert tts_kwargs["solo_voice"] == "nb_NO-tord-medium"
        else:
            assert tts_kwargs["solo_voice"] is None

    def test_monologue_transcript_markdown_and_json_formatting(
        self, mock_pipeline_stubs: dict[str, Any]
    ) -> None:
        """Asserts monologue transcript markdown contains single-host header and formatting."""
        service = PodcastGeneratorService()
        monologue_turns = [
            DialogueTurn(speaker="Host 1", text="Chapter 1: The introduction to our topic."),
            DialogueTurn(speaker="Host 1", text="Chapter 2: Deep dive into the details."),
        ]
        mock_pipeline_stubs["script"].return_value = monologue_turns

        # Test Norwegian monologue
        opts_nb = GenerationOptions(
            content="Topic for monologue",
            language="nb-NO",
            is_topic=True,
            host_mode="monologue",
            solo_voice="nb_NO-tord-medium",
            output_dir=mock_pipeline_stubs["out_dir"],
        )

        result_nb = service.generate_podcast(options=opts_nb)
        assert os.path.exists(result_nb.script_json_path)
        assert os.path.exists(result_nb.script_md_path)

        with open(result_nb.script_md_path, encoding="utf-8") as f:
            md_nb = f.read()

        assert "# Podcast Transcript" in md_nb
        assert "**Host (Kari)**:" in md_nb
        assert "Host 2" not in md_nb
        assert "Ola" not in md_nb

        # Test English monologue
        opts_en = GenerationOptions(
            content="Topic for monologue",
            language="en-US",
            is_topic=True,
            host_mode="monologue",
            solo_voice="en_US-lessac-medium",
            output_dir=mock_pipeline_stubs["out_dir"],
        )

        result_en = service.generate_podcast(options=opts_en)
        with open(result_en.script_md_path, encoding="utf-8") as f:
            md_en = f.read()

        assert "# Podcast Transcript" in md_en
        assert "**Host (Jenny)**:" in md_en
        assert "Host 2" not in md_en
        assert "Guy" not in md_en


# ==============================================================================
# 5. Adversarial Callback Fault-Tolerance & Percentage Invariants
# ==============================================================================
class TestAdversarialCallbackFaultTolerance:
    """Verifies that malicious or buggy callbacks cannot crash the core pipeline."""

    @pytest.fixture
    def mock_happy_path(self, tmp_path: Any):
        out_dir = str(tmp_path / "callback_out")
        os.makedirs(out_dir, exist_ok=True)
        dialogue = [DialogueTurn(speaker="Host 1", text="Dialogue text")]
        master_mp3 = os.path.join(out_dir, "podcast.mp3")
        with open(master_mp3, "wb") as f:
            f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x44")

        with (
            patch("core.pipeline.extract_text", return_value="Text content"),
            patch("core.pipeline.generate_podcast_script", return_value=dialogue),
            patch(
                "core.pipeline.synthesize_dialogue_audio",
                return_value=[os.path.join(out_dir, "t0.mp3")],
            ),
            patch("core.pipeline.stitch_mp3_files", return_value=master_mp3),
        ):
            yield {"out_dir": out_dir, "master_mp3": master_mp3}

    def test_exploding_stage_callback_does_not_crash_pipeline(
        self, mock_happy_path: dict[str, Any]
    ) -> None:
        service = PodcastGeneratorService()

        def buggy_stage_callback(stage: Any, status: Any, pct: float, msg: str) -> None:
            raise TypeError("Intentional buggy callback signature crash")

        opts = GenerationOptions(
            content="Content",
            is_raw_text=True,
            output_dir=mock_happy_path["out_dir"],
        )

        # Should complete successfully despite buggy callback
        result = service.generate_podcast(
            options=opts,
            stage_callback=buggy_stage_callback,
        )
        assert result.mp3_path == mock_happy_path["master_mp3"]

    def test_exploding_legacy_progress_callback_does_not_crash_pipeline(
        self, mock_happy_path: dict[str, Any]
    ) -> None:
        service = PodcastGeneratorService()

        def buggy_progress_callback(pct: float, msg: str) -> None:
            raise ZeroDivisionError("Intentional zero division error in user callback")

        opts = GenerationOptions(
            content="Content",
            is_raw_text=True,
            output_dir=mock_happy_path["out_dir"],
        )

        result = service.generate_podcast(
            options=opts,
            progress_callback=buggy_progress_callback,
        )
        assert result.mp3_path == mock_happy_path["master_mp3"]


# ==============================================================================
# 6. Concurrency, Extreme Boundaries & Path Safety
# ==============================================================================
class TestAdversarialConcurrencyAndBoundaries:
    """Stress tests multi-threading isolation, asynchronous cancellation races, and path safety."""

    def test_concurrent_pipeline_instances_isolation(self, tmp_path: Any) -> None:
        """Runs multiple independent podcast generation runs concurrently on separate threads."""
        service = PodcastGeneratorService()
        errors: list[Exception] = []

        def fake_extract(source: str, **kwargs: Any) -> str:
            return f"Extracted: {source}"

        def fake_script(content: str, **kwargs: Any) -> list[DialogueTurn]:
            return [
                DialogueTurn(speaker="Host 1", text=f"Script for: {content}"),
                DialogueTurn(speaker="Host 2", text="Second host response"),
            ]

        def fake_tts(dialogue: list[DialogueTurn], **kwargs: Any) -> list[str]:
            return [f"/tmp/turn_{i}.mp3" for i in range(len(dialogue))]

        def fake_stitch(input_files_or_bytes: Any, output_file_path: str) -> str:
            with open(output_file_path, "wb") as f:
                f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x44")
            return output_file_path

        def worker_fn(worker_idx: int) -> None:
            try:
                out_dir = str(tmp_path / f"thread_worker_{worker_idx}")
                os.makedirs(out_dir, exist_ok=True)
                auditor = ComprehensiveStageAuditor()
                opts = GenerationOptions(
                    content=f"Worker {worker_idx} content",
                    is_raw_text=True,
                    output_dir=out_dir,
                )

                expected_mp3 = os.path.join(out_dir, "podcast.mp3")
                res = service.generate_podcast(options=opts, stage_callback=auditor)
                assert res.mp3_path == expected_mp3
                assert len(res.dialogue) == 2
                assert os.path.exists(res.mp3_path)
                assert os.path.exists(res.script_json_path)
                assert os.path.exists(res.script_md_path)
                auditor.assert_strictly_monotonic_stages()
            except Exception as e:
                errors.append(e)

        with (
            patch("core.pipeline.extract_text", side_effect=fake_extract),
            patch("core.pipeline.generate_podcast_script", side_effect=fake_script),
            patch("core.pipeline.synthesize_dialogue_audio", side_effect=fake_tts),
            patch("core.pipeline.stitch_mp3_files", side_effect=fake_stitch),
        ):
            threads = [threading.Thread(target=worker_fn, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10.0)

        assert not errors, f"Thread errors encountered: {errors}"

    def test_rapid_threaded_cancellation_race(self, tmp_path: Any) -> None:
        """Asynchronously triggers cancel_event from a delayed timer thread."""
        service = PodcastGeneratorService()
        cancel_ev = threading.Event()
        out_dir = str(tmp_path / "race_out")
        os.makedirs(out_dir, exist_ok=True)
        auditor = ComprehensiveStageAuditor()

        def delay_cancel() -> None:
            threading.Event().wait(0.05)
            cancel_ev.set()

        opts = GenerationOptions(
            content="Slow generating podcast topic",
            is_topic=True,
            output_dir=out_dir,
        )

        def slow_script(*args: Any, **kwargs: Any) -> list[DialogueTurn]:
            ev = kwargs.get("cancel_event")
            for _ in range(20):
                if ev and ev.is_set():
                    raise RuntimeError("Generation cancelled by user.")
                threading.Event().wait(0.01)
            return []

        timer = threading.Thread(target=delay_cancel)
        timer.start()

        with (
            patch("core.pipeline.extract_text", return_value="Topic content"),
            patch("core.pipeline.generate_podcast_script", side_effect=slow_script),
        ):
            with pytest.raises(RuntimeError, match="cancelled by user"):
                service.generate_podcast(
                    options=opts,
                    stage_callback=auditor,
                    cancel_event=cancel_ev,
                )

        timer.join()
        assert (
            auditor.final_status_per_stage.get(PipelineStage.SCRIPT_GENERATION)
            == StageStatus.CANCELLED
        )

    def test_special_characters_and_spaces_in_output_path(self, tmp_path: Any) -> None:
        """Verifies output paths containing spaces, Norwegian characters, and nested folders."""
        service = PodcastGeneratorService()
        out_dir = str(tmp_path / "Norsk Podkast Mappe (ÆØÅ) 2026")
        os.makedirs(out_dir, exist_ok=True)
        turns = [DialogueTurn(speaker="Host 1", text="Norsk innhold")]
        master_mp3 = os.path.join(out_dir, "podcast.mp3")
        with open(master_mp3, "wb") as f:
            f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x44")

        opts = GenerationOptions(
            content="Spesialtegn og mellomrom",
            is_raw_text=True,
            output_dir=out_dir,
        )

        with (
            patch("core.pipeline.extract_text", return_value="Spesialtegn"),
            patch("core.pipeline.generate_podcast_script", return_value=turns),
            patch(
                "core.pipeline.synthesize_dialogue_audio",
                return_value=[os.path.join(out_dir, "t0.mp3")],
            ),
            patch("core.pipeline.stitch_mp3_files", return_value=master_mp3),
        ):
            result = service.generate_podcast(options=opts)
            assert os.path.exists(result.mp3_path)
            assert os.path.exists(result.script_json_path)
            assert os.path.exists(result.script_md_path)
            assert result.duration_estimate_sec == 4.0
