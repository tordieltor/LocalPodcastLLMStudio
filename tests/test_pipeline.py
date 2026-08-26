"""
Unit & Integration Tests for Headless Podcast Generation Pipeline Service (tests/test_pipeline.py)
Validates:
- PipelineStage (IntEnum) values and ordinal sequence
- StageStatus (str, Enum) states
- GenerationOptions data container defaults and custom overrides
- Full 5-stage lifecycle transitions (URL_INGESTION -> CONTENT_EXTRACTION -> SCRIPT_GENERATION -> TTS_SYNTHESIS -> AUDIO_ASSEMBLY)
- Dual-signature progress callback & stage callback coordination
- Granular Act progression and TTS per-turn speaker reporting
- Monologue mode and solo_voice integration
- URL ingestion vs document/topic input handling
- Error boundary attribution (marking active stage FAILED)
- User cancellation handling (marking active stage CANCELLED)
"""

from __future__ import annotations

import os
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import DocumentExtractionError, OllamaConnectionError, SecurityError
from core.parser import DialogueTurn
from core.pipeline import (
    GenerationOptions,
    GenerationResult,
    PipelineStage,
    PodcastGeneratorService,
    StageStatus,
)


class StageRecorder:
    """Helper recorder capturing all stage lifecycle transitions for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[PipelineStage, StageStatus, float, str]] = []

    def __call__(
        self,
        stage: PipelineStage | int,
        status: StageStatus | str,
        pct: float,
        msg: str,
    ) -> None:
        s_stage = PipelineStage(stage) if not isinstance(stage, PipelineStage) else stage
        s_status = StageStatus(status) if not isinstance(status, StageStatus) else status
        self.events.append((s_stage, s_status, round(pct, 4), msg))

    @property
    def stages_seen(self) -> list[PipelineStage]:
        seen: list[PipelineStage] = []
        for stage, _, _, _ in self.events:
            if not seen or seen[-1] != stage:
                seen.append(stage)
        return seen

    def get_events_for_stage(
        self, stage: PipelineStage
    ) -> list[tuple[PipelineStage, StageStatus, float, str]]:
        return [e for e in self.events if e[0] == stage]

    def assert_stage_completed(self, stage: PipelineStage) -> None:
        events = self.get_events_for_stage(stage)
        assert any(e[1] == StageStatus.IN_ACTION for e in events), (
            f"Stage {stage.name} was never IN_ACTION"
        )
        assert any(e[1] == StageStatus.COMPLETED for e in events), (
            f"Stage {stage.name} was never COMPLETED"
        )

    def assert_stage_failed(self, stage: PipelineStage) -> None:
        events = self.get_events_for_stage(stage)
        assert any(e[1] == StageStatus.FAILED for e in events), (
            f"Stage {stage.name} was never marked FAILED"
        )

    def assert_stage_cancelled(self, stage: PipelineStage) -> None:
        events = self.get_events_for_stage(stage)
        assert any(e[1] == StageStatus.CANCELLED for e in events), (
            f"Stage {stage.name} was never marked CANCELLED"
        )


class TestPipelineDataContracts:
    """Validates enum invariants, ordering, and dataclass structures."""

    def test_pipeline_stage_enum_invariants(self) -> None:
        assert PipelineStage.URL_INGESTION == 1
        assert PipelineStage.CONTENT_EXTRACTION == 2
        assert PipelineStage.SCRIPT_GENERATION == 3
        assert PipelineStage.TTS_SYNTHESIS == 4
        assert PipelineStage.AUDIO_ASSEMBLY == 5
        assert (
            PipelineStage.URL_INGESTION
            < PipelineStage.CONTENT_EXTRACTION
            < PipelineStage.SCRIPT_GENERATION
            < PipelineStage.TTS_SYNTHESIS
            < PipelineStage.AUDIO_ASSEMBLY
        )

    def test_stage_status_enum_invariants(self) -> None:
        assert StageStatus.PENDING == "pending"
        assert StageStatus.IN_ACTION == "in_action"
        assert StageStatus.COMPLETED == "completed"
        assert StageStatus.FAILED == "failed"
        assert StageStatus.CANCELLED == "cancelled"

    def test_generation_options_defaults(self) -> None:
        opts = GenerationOptions(content="Sample input text")
        assert opts.content == "Sample input text"
        assert opts.language == "nb-NO"
        assert opts.model == "llama3.1:8b"
        assert opts.format_type == "standard"
        assert opts.tone_style == "casual"
        assert opts.speed_rate == "+0%"
        assert opts.grounding_mode == "strict"
        assert opts.output_dir == "./output"
        assert opts.is_topic is False
        assert opts.is_raw_text is False
        assert opts.is_url is False
        assert opts.host_mode == "dialogue"
        assert opts.solo_voice is None

    def test_generation_options_custom_overrides(self) -> None:
        opts = GenerationOptions(
            content="https://example.com/podcast-article",
            language="en-US",
            model="qwen2.5:7b",
            format_type="deep_dive",
            tone_style="analytical",
            speed_rate="+10%",
            grounding_mode="creative",
            output_dir="./custom_out",
            is_topic=False,
            is_raw_text=False,
            is_url=True,
            host_mode="monologue",
            solo_voice="en_US-lessac-medium",
        )
        assert opts.is_url is True
        assert opts.host_mode == "monologue"
        assert opts.solo_voice == "en_US-lessac-medium"
        assert opts.language == "en-US"
        assert opts.grounding_mode == "creative"

    def test_generation_result_structure(self) -> None:
        dialogue = [DialogueTurn(speaker="Host 1", text="Intro turn")]
        res = GenerationResult(
            mp3_path="/path/to/pod.mp3",
            script_json_path="/path/to/script.json",
            script_md_path="/path/to/script.md",
            dialogue=dialogue,
            duration_estimate_sec=12.5,
        )
        assert res.mp3_path == "/path/to/pod.mp3"
        assert res.dialogue == dialogue
        assert res.duration_estimate_sec == 12.5


class TestPodcastGeneratorServiceLifecycle:
    """Validates full 5-stage lifecycle transitions, act updates, and TTS turn tracking."""

    @pytest.fixture
    def mock_components(self, tmp_path: Any):
        out_dir = str(tmp_path / "lifecycle_out")
        os.makedirs(out_dir, exist_ok=True)
        sample_dialogue = [
            DialogueTurn(speaker="Host 1", text="Welcome to the podcast!"),
            DialogueTurn(speaker="Host 2", text="Glad to be here with you!"),
            DialogueTurn(speaker="Host 1", text="Let's dive into the topic."),
            DialogueTurn(speaker="Host 2", text="Absolutely, let's explore it."),
        ]
        audio_files = [os.path.join(out_dir, f"turn_{i}.mp3") for i in range(4)]
        master_mp3 = os.path.join(out_dir, "podcast.mp3")
        with open(master_mp3, "wb") as f:
            f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x44" * 10)

        with (
            patch(
                "core.pipeline.extract_text", return_value="Extracted content text from source."
            ) as m_ext,
            patch(
                "core.pipeline.generate_podcast_script", return_value=sample_dialogue
            ) as m_script,
            patch("core.pipeline.synthesize_dialogue_audio", return_value=audio_files) as m_tts,
            patch("core.pipeline.stitch_mp3_files", return_value=master_mp3) as m_stitch,
        ):
            yield {
                "extract": m_ext,
                "script": m_script,
                "tts": m_tts,
                "stitch": m_stitch,
                "out_dir": out_dir,
                "dialogue": sample_dialogue,
                "master_mp3": master_mp3,
            }

    def test_full_5_stage_lifecycle_raw_text(self, mock_components: dict[str, Any]) -> None:
        out_dir = mock_components["out_dir"]
        service = PodcastGeneratorService()
        recorder = StageRecorder()
        legacy_progress: list[tuple[float, str]] = []

        def legacy_cb(pct: float, msg: str) -> None:
            legacy_progress.append((pct, msg))

        opts = GenerationOptions(
            content="Direct raw content for podcast generation.",
            output_dir=out_dir,
            is_raw_text=True,
        )

        result = service.generate_podcast(
            options=opts,
            stage_callback=recorder,
            progress_callback=legacy_cb,
        )

        assert result.mp3_path == mock_components["master_mp3"]
        assert len(result.dialogue) == 4
        assert os.path.exists(result.script_json_path)
        assert os.path.exists(result.script_md_path)

        # Verify all 5 stages were reached and completed
        recorder.assert_stage_completed(PipelineStage.URL_INGESTION)
        recorder.assert_stage_completed(PipelineStage.CONTENT_EXTRACTION)
        recorder.assert_stage_completed(PipelineStage.SCRIPT_GENERATION)
        recorder.assert_stage_completed(PipelineStage.TTS_SYNTHESIS)
        recorder.assert_stage_completed(PipelineStage.AUDIO_ASSEMBLY)

        # Verify legacy progress callback received events
        assert len(legacy_progress) > 0
        assert legacy_progress[-1][0] == 1.0

    def test_full_5_stage_lifecycle_url_input(self, mock_components: dict[str, Any]) -> None:
        out_dir = mock_components["out_dir"]
        service = PodcastGeneratorService()
        recorder = StageRecorder()

        opts = GenerationOptions(
            content="https://example.com/tech-article",
            output_dir=out_dir,
            is_url=True,
        )

        result = service.generate_podcast(
            options=opts,
            stage_callback=recorder,
        )

        assert result.mp3_path == mock_components["master_mp3"]
        recorder.assert_stage_completed(PipelineStage.URL_INGESTION)
        recorder.assert_stage_completed(PipelineStage.CONTENT_EXTRACTION)
        recorder.assert_stage_completed(PipelineStage.SCRIPT_GENERATION)
        recorder.assert_stage_completed(PipelineStage.TTS_SYNTHESIS)
        recorder.assert_stage_completed(PipelineStage.AUDIO_ASSEMBLY)

        # Verify extract_text was called with is_url=True
        mock_components["extract"].assert_called_once()
        _, kwargs = mock_components["extract"].call_args
        assert kwargs["is_url"] is True

    def test_dual_progress_callback_as_stage_recorder(
        self, mock_components: dict[str, Any]
    ) -> None:
        out_dir = mock_components["out_dir"]
        service = PodcastGeneratorService()
        recorder = StageRecorder()

        # Pass 4-argument recorder as progress_callback (dual compatibility)
        opts = GenerationOptions(content="Topic content", is_topic=True, output_dir=out_dir)
        result = service.generate_podcast(
            options=opts,
            progress_callback=recorder,
        )

        assert result.mp3_path == mock_components["master_mp3"]
        assert len(recorder.events) > 5

    def test_act_callback_and_tts_turn_progress_forwarding(
        self, mock_components: dict[str, Any]
    ) -> None:
        out_dir = mock_components["out_dir"]
        service = PodcastGeneratorService()
        recorder = StageRecorder()

        act_events: list[tuple[int, int, list[DialogueTurn]]] = []

        def act_cb(idx: int, tot: int, turns: list[DialogueTurn]) -> None:
            act_events.append((idx, tot, turns))

        # Configure mock_script to invoke act_callback internally
        def fake_generate_script(*args: Any, **kwargs: Any) -> list[DialogueTurn]:
            internal_act = kwargs.get("act_callback")
            if internal_act:
                internal_act(1, 2, mock_components["dialogue"][:2])
                internal_act(2, 2, mock_components["dialogue"][2:])
            return mock_components["dialogue"]

        # Configure mock_tts to invoke progress_cb internally
        def fake_synth_tts(*args: Any, **kwargs: Any) -> list[str]:
            prog = kwargs.get("progress_cb")
            if prog:
                prog(1, 4)
                prog(2, 4)
                prog(3, 4)
                prog(4, 4)
            return mock_components["tts"].return_value

        mock_components["script"].side_effect = fake_generate_script
        mock_components["tts"].side_effect = fake_synth_tts

        opts = GenerationOptions(content="Sample content", output_dir=out_dir)
        service.generate_podcast(
            options=opts,
            stage_callback=recorder,
            act_callback=act_cb,
        )

        # Verify act events were delivered to outer callback
        assert len(act_events) == 2
        assert act_events[0][0] == 1
        assert act_events[1][0] == 2

        # Verify stage messages recorded Act and Turn progression
        script_events = recorder.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)
        assert any("Act 1 of 2" in e[3] for e in script_events)
        assert any("Act 2 of 2" in e[3] for e in script_events)

        tts_events = recorder.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)
        assert any("turn 1 of 4" in e[3] for e in tts_events)
        assert any("turn 4 of 4" in e[3] for e in tts_events)


class TestMonologueAndSoloVoicePipeline:
    """Validates monologue host mode and solo_voice parameter propagation."""

    @patch("core.pipeline.stitch_mp3_files", return_value="/tmp/podcast.mp3")
    @patch("core.pipeline.synthesize_dialogue_audio", return_value=["/tmp/turn_1.mp3"])
    @patch(
        "core.pipeline.generate_podcast_script",
        return_value=[DialogueTurn(speaker="Host 1", text="Solo essay speech.")],
    )
    @patch("core.pipeline.extract_text", return_value="Topic content")
    def test_monologue_mode_and_solo_voice_propagation(
        self,
        mock_ext: MagicMock,
        mock_script: MagicMock,
        mock_tts: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        out_dir = str(tmp_path / "mono_out")
        service = PodcastGeneratorService()
        opts = GenerationOptions(
            content="The Future of Quantum Computing",
            is_topic=True,
            host_mode="monologue",
            solo_voice="en_US-lessac-medium",
            output_dir=out_dir,
        )

        result = service.generate_podcast(options=opts)

        assert result.dialogue[0].text == "Solo essay speech."

        # Verify host_mode passed to generate_podcast_script
        _, script_kwargs = mock_script.call_args
        assert script_kwargs["host_mode"] == "monologue"

        # Verify solo_voice passed to synthesize_dialogue_audio
        _, tts_kwargs = mock_tts.call_args
        assert tts_kwargs["solo_voice"] == "en_US-lessac-medium"


class TestPipelineErrorHandling:
    """Validates stage failure transitions and error boundary containment."""

    def test_stage1_url_ssrf_security_error_marks_stage1_failed(self, tmp_path: Any) -> None:
        service = PodcastGeneratorService()
        recorder = StageRecorder()
        opts = GenerationOptions(
            content="http://127.0.0.1:11434/api/generate",
            is_url=True,
            output_dir=str(tmp_path),
        )

        with patch(
            "core.pipeline.extract_text",
            side_effect=SecurityError("SSRF attempt to loopback IP 127.0.0.1 blocked"),
        ):
            with pytest.raises(SecurityError, match="SSRF attempt"):
                service.generate_podcast(options=opts, stage_callback=recorder)

        recorder.assert_stage_failed(PipelineStage.URL_INGESTION)
        # Downstream stages should never have started
        assert len(recorder.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)) == 0
        assert len(recorder.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)) == 0

    def test_stage2_extraction_error_marks_stage2_failed(self, tmp_path: Any) -> None:
        service = PodcastGeneratorService()
        recorder = StageRecorder()
        opts = GenerationOptions(
            content="corrupted_file.pdf",
            is_raw_text=False,
            output_dir=str(tmp_path),
        )

        with patch(
            "core.pipeline.extract_text",
            side_effect=DocumentExtractionError("PDF parsing failed due to corrupted trailer"),
        ):
            with pytest.raises(DocumentExtractionError, match="PDF parsing failed"):
                service.generate_podcast(options=opts, stage_callback=recorder)

        recorder.assert_stage_failed(PipelineStage.CONTENT_EXTRACTION)
        assert len(recorder.get_events_for_stage(PipelineStage.SCRIPT_GENERATION)) == 0

    def test_stage3_ollama_connection_error_marks_stage3_failed(self, tmp_path: Any) -> None:
        service = PodcastGeneratorService()
        recorder = StageRecorder()
        opts = GenerationOptions(
            content="Valid content string",
            is_raw_text=True,
            output_dir=str(tmp_path),
        )

        with (
            patch("core.pipeline.extract_text", return_value="Valid text content"),
            patch(
                "core.pipeline.generate_podcast_script",
                side_effect=OllamaConnectionError(
                    "Cannot connect to Ollama at http://localhost:11434"
                ),
            ),
        ):
            with pytest.raises(OllamaConnectionError, match="Cannot connect to Ollama"):
                service.generate_podcast(options=opts, stage_callback=recorder)

        recorder.assert_stage_completed(PipelineStage.URL_INGESTION)
        recorder.assert_stage_completed(PipelineStage.CONTENT_EXTRACTION)
        recorder.assert_stage_failed(PipelineStage.SCRIPT_GENERATION)
        assert len(recorder.get_events_for_stage(PipelineStage.TTS_SYNTHESIS)) == 0

    def test_stage4_tts_failure_marks_stage4_failed(self, tmp_path: Any) -> None:
        service = PodcastGeneratorService()
        recorder = StageRecorder()
        opts = GenerationOptions(
            content="Valid content string",
            is_raw_text=True,
            output_dir=str(tmp_path),
        )

        with (
            patch("core.pipeline.extract_text", return_value="Valid text content"),
            patch(
                "core.pipeline.generate_podcast_script",
                return_value=[DialogueTurn(speaker="Host 1", text="Hello")],
            ),
            patch(
                "core.pipeline.synthesize_dialogue_audio",
                side_effect=RuntimeError("Piper TTS executable crashed"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Piper TTS executable crashed"):
                service.generate_podcast(options=opts, stage_callback=recorder)

        recorder.assert_stage_completed(PipelineStage.SCRIPT_GENERATION)
        recorder.assert_stage_failed(PipelineStage.TTS_SYNTHESIS)
        assert len(recorder.get_events_for_stage(PipelineStage.AUDIO_ASSEMBLY)) == 0


class TestPipelineCancellation:
    """Validates responsive cancellation and StageStatus.CANCELLED emission."""

    def test_cancellation_during_script_generation(self, tmp_path: Any) -> None:
        service = PodcastGeneratorService()
        recorder = StageRecorder()
        cancel_ev = threading.Event()

        def fake_generate_script(*args: Any, **kwargs: Any) -> list[DialogueTurn]:
            cancel_ev.set()
            ev = kwargs.get("cancel_event")
            if ev and ev.is_set():
                raise RuntimeError("Generation cancelled by user.")
            return []

        opts = GenerationOptions(
            content="Topic for cancellation test",
            is_topic=True,
            output_dir=str(tmp_path),
        )

        with (
            patch("core.pipeline.extract_text", return_value="Topic content"),
            patch("core.pipeline.generate_podcast_script", side_effect=fake_generate_script),
        ):
            with pytest.raises(RuntimeError, match="cancelled by user"):
                service.generate_podcast(
                    options=opts,
                    stage_callback=recorder,
                    cancel_event=cancel_ev,
                )

        recorder.assert_stage_cancelled(PipelineStage.SCRIPT_GENERATION)
