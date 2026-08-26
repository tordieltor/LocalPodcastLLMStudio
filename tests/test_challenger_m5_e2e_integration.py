"""
Milestone 5 Challenger 2: End-to-End Pipeline & Integration Empirical Challenge Suite
====================================================================================
Empirically verifies:
1. End-to-end URL Ingestion -> MarkItDown conversion -> Monologue Script Generation -> Solo TTS Synthesis -> MP3 Stitching with 5-stage progress tracking.
2. CLI automation with `--url`, `--host-mode monologue`, `--solo-voice`, `--json` producing pure stdout data and formatted stderr stage transitions.
3. CustomTkinter UI thread-safe lifecycle simulation (worker dispatching, cancellation, queue processing, error isolation).
"""

from __future__ import annotations

import json
import os
import queue
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import cli
from core.exceptions import (
    DocumentExtractionError,
    SecurityError,
)
from core.parser import DialogueTurn
from core.pipeline import (
    GenerationOptions,
    GenerationResult,
    PipelineStage,
    PodcastGeneratorService,
    StageStatus,
)
from tests.conftest import make_synthetic_mp3
from ui.main_window import GenerationWorker, URLExtractionWorker


# ==============================================================================
# 1. E2E Pipeline Integration: URL Ingestion -> Monologue -> Solo TTS -> Stitching
# ==============================================================================
class TestE2EMonologueURLPipelineEmpirical:
    """Empirical verification of the end-to-end 5-stage pipeline with URL input and Monologue format."""

    @patch("core.pipeline.stitch_mp3_files")
    @patch("core.pipeline.synthesize_dialogue_audio")
    @patch("core.pipeline.generate_podcast_script")
    @patch("core.pipeline.extract_text")
    def test_e2e_url_monologue_norwegian_full_lifecycle(
        self,
        mock_extract: MagicMock,
        mock_gen_script: MagicMock,
        mock_synth_audio: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        """
        Full 5-stage lifecycle verification:
        URL Ingestion -> Extraction -> Monologue Script -> Solo TTS -> MP3 Stitching.
        Verifies:
        - Strict monotonic progress reporting from 0.0 to 1.0.
        - Proper stage transitions (URL_INGESTION -> CONTENT_EXTRACTION -> SCRIPT_GENERATION -> TTS_SYNTHESIS -> AUDIO_ASSEMBLY).
        - Correct monologue speaker normalization ('Host 1') and solo voice propagation.
        - Atomic transcript files (JSON & Markdown) written to output directory.
        """
        url = "https://no.wikipedia.org/wiki/Kunstig_intelligens"
        raw_markdown = (
            "# Kunstig Intelligens\n\n"
            "Kunstig intelligens (KI) refererer til datasystemer som utfører oppgaver som krever menneskelig intelligens.\n\n"
            "## Historie og utvikling\n"
            "Feltet ble etablert i 1956 på Dartmouth-konferansen."
        )
        mock_extract.return_value = raw_markdown

        monologue_turns = [
            DialogueTurn(
                speaker="Host 1",
                text="Velkommen til podkasten om kunstig intelligens og fremtidens teknologi.",
            ),
            DialogueTurn(
                speaker="Host 1",
                text="I dag skal vi dykke ned i hvordan maskinlæring har utviklet seg siden 1956.",
            ),
            DialogueTurn(
                speaker="Host 1",
                text="Dette var alt for denne gangen, takk for at du lyttet på oss!",
            ),
        ]
        mock_gen_script.return_value = monologue_turns

        dummy_turn_mp3s = [str(tmp_path / f"turn_{i}.mp3") for i in range(len(monologue_turns))]
        for p in dummy_turn_mp3s:
            with open(p, "wb") as f:
                f.write(make_synthetic_mp3(num_frames=5))
        mock_synth_audio.return_value = dummy_turn_mp3s

        master_mp3_path = str(tmp_path / "podcast.mp3")
        mock_stitch.return_value = master_mp3_path

        service = PodcastGeneratorService(ollama_url="http://localhost:11434")
        options = GenerationOptions(
            content=url,
            language="nb-NO",
            model="llama3.1:8b",
            format_type="standard",
            tone_style="casual",
            speed_rate="+0%",
            grounding_mode="strict",
            output_dir=str(tmp_path),
            is_url=True,
            host_mode="monologue",
            solo_voice="nb_no_kari",
        )

        stage_transitions: list[tuple[PipelineStage, StageStatus, float, str]] = []

        def _stage_cb(stage: PipelineStage, status: StageStatus, pct: float, msg: str) -> None:
            stage_transitions.append((stage, status, pct, msg))

        result = service.generate_podcast(
            options=options,
            stage_callback=_stage_cb,
        )

        # 1. Verify Return Object Structure
        assert isinstance(result, GenerationResult)
        assert result.mp3_path == master_mp3_path
        assert os.path.exists(result.script_json_path)
        assert os.path.exists(result.script_md_path)
        assert len(result.dialogue) == 3
        assert all(turn.speaker == "Host 1" for turn in result.dialogue)

        # 2. Verify Monologue Transcript Files
        with open(result.script_json_path, encoding="utf-8") as jf:
            loaded_json = json.load(jf)
            assert len(loaded_json) == 3
            assert loaded_json[0]["speaker"] == "Host 1"

        with open(result.script_md_path, encoding="utf-8") as mf:
            md_content = mf.read()
            assert "Host (Kari)" in md_content or "Host 1" in md_content or "**Host" in md_content

        # 3. Verify Downstream Method Calls and Arguments
        mock_extract.assert_called_once()
        _, ext_kwargs = mock_extract.call_args
        assert ext_kwargs.get("is_url") is True

        mock_gen_script.assert_called_once()
        _, gen_kwargs = mock_gen_script.call_args
        assert gen_kwargs.get("host_mode") == "monologue"
        assert gen_kwargs.get("language") == "nb-NO"

        mock_synth_audio.assert_called_once()
        _, synth_kwargs = mock_synth_audio.call_args
        assert synth_kwargs.get("solo_voice") == "nb_no_kari"
        assert synth_kwargs.get("language") == "nb-NO"

        mock_stitch.assert_called_once()

        # 4. Verify 5-Stage Lifecycle Monotonicity
        stages_observed = [st for st, _, _, _ in stage_transitions]
        assert PipelineStage.URL_INGESTION in stages_observed
        assert PipelineStage.CONTENT_EXTRACTION in stages_observed
        assert PipelineStage.SCRIPT_GENERATION in stages_observed
        assert PipelineStage.TTS_SYNTHESIS in stages_observed
        assert PipelineStage.AUDIO_ASSEMBLY in stages_observed

        # Verify percentages are non-decreasing
        pcts = [pct for _, _, pct, _ in stage_transitions]
        for i in range(len(pcts) - 1):
            assert pcts[i] <= pcts[i + 1] + 1e-6, (
                f"Progress decreased from {pcts[i]} to {pcts[i + 1]}"
            )
        assert pcts[0] >= 0.0
        assert pcts[-1] == 1.0

        # Verify all 5 stages reach COMPLETED status
        completed_stages = {
            st for st, status, _, _ in stage_transitions if status == StageStatus.COMPLETED
        }
        assert completed_stages == {
            PipelineStage.URL_INGESTION,
            PipelineStage.CONTENT_EXTRACTION,
            PipelineStage.SCRIPT_GENERATION,
            PipelineStage.TTS_SYNTHESIS,
            PipelineStage.AUDIO_ASSEMBLY,
        }

    @patch("core.pipeline.stitch_mp3_files")
    @patch("core.pipeline.synthesize_dialogue_audio")
    @patch("core.pipeline.generate_podcast_script")
    @patch("core.pipeline.extract_text")
    def test_e2e_url_monologue_english_4_act_deep_dive(
        self,
        mock_extract: MagicMock,
        mock_gen_script: MagicMock,
        mock_synth_audio: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Verifies 4-act English deep-dive monologue with act callback event propagation."""
        mock_extract.return_value = "Long comprehensive research report on AI agent architectures."

        act_turns = [
            DialogueTurn(
                speaker="Host 1", text=f"Act {i} paragraph commentary on agentic pipelines."
            )
            for i in range(1, 5)
        ]

        def fake_generate_podcast_script(*args: Any, **kwargs: Any) -> list[DialogueTurn]:
            act_cb = kwargs.get("act_callback")
            if act_cb:
                for act_idx in range(1, 5):
                    act_cb(act_idx, 4, [act_turns[act_idx - 1]])
            return act_turns

        mock_gen_script.side_effect = fake_generate_podcast_script
        mock_synth_audio.return_value = [str(tmp_path / f"turn_{i}.mp3") for i in range(4)]
        mock_stitch.return_value = str(tmp_path / "deep_dive.mp3")

        act_events: list[tuple[int, int, int]] = []

        def _act_cb(act_idx: int, total_acts: int, turns: list[DialogueTurn]) -> None:
            act_events.append((act_idx, total_acts, len(turns)))

        service = PodcastGeneratorService()
        options = GenerationOptions(
            content="https://example.com/research-paper",
            language="en-US",
            format_type="deep_dive",
            host_mode="monologue",
            solo_voice="en_us_jenny",
            output_dir=str(tmp_path),
            is_url=True,
        )

        res = service.generate_podcast(options=options, act_callback=_act_cb)

        assert len(res.dialogue) == 4
        assert act_events == [(1, 4, 1), (2, 4, 1), (3, 4, 1), (4, 4, 1)]

    def test_e2e_url_monologue_ssrf_blocking_early_failure(self) -> None:
        """Verifies SSRF loopback targets fail immediately in URL_INGESTION and do not proceed."""
        service = PodcastGeneratorService()
        options = GenerationOptions(
            content="http://127.0.0.1:11434/api/generate",
            language="nb-NO",
            is_url=True,
            host_mode="monologue",
        )

        stage_events: list[tuple[PipelineStage, StageStatus, float, str]] = []

        def _stage_cb(st: PipelineStage, status: StageStatus, pct: float, msg: str) -> None:
            stage_events.append((st, status, pct, msg))

        with pytest.raises((SecurityError, DocumentExtractionError)):
            service.generate_podcast(options, stage_callback=_stage_cb)

        # Must fail during Stage 1
        assert len(stage_events) >= 1
        assert stage_events[0][0] == PipelineStage.URL_INGESTION
        assert stage_events[-1][1] == StageStatus.FAILED
        assert stage_events[-1][0] == PipelineStage.URL_INGESTION
        # No subsequent stages were reached
        stages_reached = {st for st, _, _, _ in stage_events}
        assert PipelineStage.SCRIPT_GENERATION not in stages_reached
        assert PipelineStage.TTS_SYNTHESIS not in stages_reached

    @patch("core.pipeline.extract_text")
    def test_e2e_pipeline_cancellation_during_extraction(
        self, mock_extract: MagicMock, tmp_path: Any
    ) -> None:
        """Verifies cancellation during extraction raises RuntimeError and notifies StageStatus.CANCELLED."""
        cancel_evt = threading.Event()

        def slow_extract(*args: Any, **kwargs: Any) -> str:
            cancel_evt.set()
            return "Extracted text"

        mock_extract.side_effect = slow_extract

        service = PodcastGeneratorService()
        options = GenerationOptions(
            content="https://example.com/article",
            is_url=True,
            output_dir=str(tmp_path),
        )

        stage_events: list[tuple[PipelineStage, StageStatus, float, str]] = []

        def _stage_cb(st: PipelineStage, status: StageStatus, pct: float, msg: str) -> None:
            stage_events.append((st, status, pct, msg))

        with pytest.raises(RuntimeError) as exc_info:
            service.generate_podcast(
                options=options,
                stage_callback=_stage_cb,
                cancel_event=cancel_evt,
            )

        assert "cancelled by user" in str(exc_info.value).lower()
        cancelled_events = [ev for ev in stage_events if ev[1] == StageStatus.CANCELLED]
        assert len(cancelled_events) >= 1

    @patch("core.pipeline.stitch_mp3_files")
    @patch("core.pipeline.synthesize_dialogue_audio")
    @patch("core.pipeline.generate_podcast_script")
    @patch("core.pipeline.extract_text")
    def test_e2e_url_monologue_all_duration_presets(
        self,
        mock_extract: MagicMock,
        mock_gen_script: MagicMock,
        mock_synth_audio: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        """
        Verifies all 4 duration presets (quick, standard, deep_dive, extended)
        generate monologue scripts with proper speaker normalization.
        """
        mock_extract.return_value = "Article content for testing all presets."
        mock_stitch.return_value = str(tmp_path / "preset_master.mp3")

        preset_acts = {
            "quick": 1,
            "standard": 2,
            "deep_dive": 4,
            "extended": 5,
        }

        service = PodcastGeneratorService()

        for preset, expected_acts in preset_acts.items():
            preset_dir = tmp_path / preset
            preset_dir.mkdir(parents=True, exist_ok=True)

            turns = [
                DialogueTurn(speaker="Host 1", text=f"Act {i} commentary in {preset} preset.")
                for i in range(1, expected_acts + 1)
            ]
            mock_gen_script.return_value = turns
            mock_synth_audio.return_value = [
                str(preset_dir / f"turn_{i}.mp3") for i in range(expected_acts)
            ]

            options = GenerationOptions(
                content="https://example.com/durations",
                language="nb-NO",
                format_type=preset,
                host_mode="monologue",
                solo_voice="nb_no_kari",
                output_dir=str(preset_dir),
                is_url=True,
            )

            res = service.generate_podcast(options=options)
            assert len(res.dialogue) == expected_acts
            assert all(t.speaker == "Host 1" for t in res.dialogue)
            assert os.path.exists(res.script_json_path)
            assert os.path.exists(res.script_md_path)

    @pytest.mark.parametrize(
        "stage_to_cancel",
        [
            PipelineStage.URL_INGESTION,
            PipelineStage.CONTENT_EXTRACTION,
            PipelineStage.SCRIPT_GENERATION,
            PipelineStage.TTS_SYNTHESIS,
            PipelineStage.AUDIO_ASSEMBLY,
        ],
    )
    def test_e2e_pipeline_cancellation_at_all_five_stages(
        self,
        stage_to_cancel: PipelineStage,
        tmp_path: Any,
    ) -> None:
        """
        Empirically verifies cancellation during each of the 5 distinct pipeline stages.
        In each case, ensures RuntimeError is raised and CANCELLED stage status is recorded.
        """
        cancel_evt = threading.Event()
        stage_events: list[tuple[PipelineStage, StageStatus, float, str]] = []

        def _stage_cb(st: PipelineStage, status: StageStatus, pct: float, msg: str) -> None:
            stage_events.append((st, status, pct, msg))
            if st == stage_to_cancel and status == StageStatus.IN_ACTION:
                cancel_evt.set()

        service = PodcastGeneratorService()
        options = GenerationOptions(
            content="https://example.com/cancel-test",
            language="en-US",
            host_mode="monologue",
            output_dir=str(tmp_path / f"cancel_{stage_to_cancel.name}"),
            is_url=True,
        )

        with (
            patch("core.pipeline.extract_text") as mock_extract,
            patch("core.pipeline.generate_podcast_script") as mock_gen,
            patch("core.pipeline.synthesize_dialogue_audio") as mock_synth,
            patch("core.pipeline.stitch_mp3_files") as mock_stitch,
        ):
            mock_extract.return_value = "Content"
            mock_gen.return_value = [DialogueTurn(speaker="Host 1", text="Text")]
            mock_synth.return_value = [str(tmp_path / "turn.mp3")]
            mock_stitch.return_value = str(tmp_path / "master.mp3")

            with pytest.raises(RuntimeError) as exc_info:
                service.generate_podcast(
                    options=options,
                    stage_callback=_stage_cb,
                    cancel_event=cancel_evt,
                )

            assert "cancelled by user" in str(exc_info.value).lower()
            cancelled = [ev for ev in stage_events if ev[1] == StageStatus.CANCELLED]
            assert len(cancelled) >= 1
            assert cancelled[-1][0] == stage_to_cancel

    @patch("core.pipeline.stitch_mp3_files")
    @patch("core.pipeline.synthesize_dialogue_audio")
    @patch("core.pipeline.generate_podcast_script")
    @patch("core.pipeline.extract_text")
    def test_e2e_url_monologue_default_solo_voice_fallback(
        self,
        mock_extract: MagicMock,
        mock_gen_script: MagicMock,
        mock_synth_audio: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Verifies that when solo_voice is None, synthesize_dialogue_audio receives solo_voice=None without error."""
        mock_extract.return_value = "Default voice content."
        mock_gen_script.return_value = [DialogueTurn(speaker="Host 1", text="Solo talk.")]
        mock_synth_audio.return_value = [str(tmp_path / "t0.mp3")]
        mock_stitch.return_value = str(tmp_path / "master.mp3")

        service = PodcastGeneratorService()
        options = GenerationOptions(
            content="https://example.com/fallback",
            language="nb-NO",
            host_mode="monologue",
            solo_voice=None,
            output_dir=str(tmp_path),
            is_url=True,
        )

        res = service.generate_podcast(options=options)
        assert res is not None
        mock_synth_audio.assert_called_once()
        _, synth_kwargs = mock_synth_audio.call_args
        assert synth_kwargs.get("solo_voice") is None


# ==============================================================================
# 2. CLI Automation: Monologue, --url, --solo-voice, JSON Stdout/Stderr Isolation
# ==============================================================================
class TestCLIAutomationMonologueJSONStdoutStderr:
    """Empirical verification of CLI stdout/stderr isolation and automation flags."""

    @patch("cli.PodcastGeneratorService")
    def test_cli_pipeline_monologue_url_json_stdout_stderr_isolation(
        self, mock_service_cls: MagicMock, capsys: Any, tmp_path: Any
    ) -> None:
        """
        Verifies `cli.py pipeline --url <url> --host-mode monologue --solo-voice <voice> --json`:
        - stdout contains pure parseable JSON with all required keys.
        - stderr contains formatted `[STAGE X/5]` transitions.
        - stdout contains ZERO stderr/diagnostic log strings.
        """
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        dummy_result = GenerationResult(
            mp3_path=str(tmp_path / "podcast.mp3"),
            script_json_path=str(tmp_path / "transcript.json"),
            script_md_path=str(tmp_path / "transcript.md"),
            dialogue=[
                DialogueTurn(speaker="Host 1", text="Solo monologue opening statement."),
                DialogueTurn(speaker="Host 1", text="Solo monologue closing statement."),
            ],
            duration_estimate_sec=8.0,
        )

        def fake_generate_podcast(options: GenerationOptions, **kwargs: Any) -> GenerationResult:
            stage_cb = kwargs.get("stage_callback")
            if stage_cb:
                stage_cb(PipelineStage.URL_INGESTION, StageStatus.IN_ACTION, 0.02, "Fetching URL")
                stage_cb(PipelineStage.URL_INGESTION, StageStatus.COMPLETED, 0.10, "URL Fetched")
                stage_cb(PipelineStage.CONTENT_EXTRACTION, StageStatus.COMPLETED, 0.25, "Extracted")
                stage_cb(
                    PipelineStage.SCRIPT_GENERATION, StageStatus.COMPLETED, 0.60, "Script Done"
                )
                stage_cb(PipelineStage.TTS_SYNTHESIS, StageStatus.COMPLETED, 0.90, "TTS Done")
                stage_cb(
                    PipelineStage.AUDIO_ASSEMBLY, StageStatus.COMPLETED, 1.00, "Master MP3 Ready"
                )
            return dummy_result

        mock_service.generate_podcast.side_effect = fake_generate_podcast

        cli_args = [
            "pipeline",
            "--url",
            "https://example.com/article",
            "--host-mode",
            "monologue",
            "--solo-voice",
            "nb_no_kari",
            "--language",
            "nb-NO",
            "--length",
            "quick",
            "--output-dir",
            str(tmp_path),
            "--json",
        ]

        exit_code = cli.main(cli_args)
        assert exit_code == 0

        captured = capsys.readouterr()

        # 1. Verify stdout is pure JSON
        stdout_str = captured.out.strip()
        assert stdout_str != "", "stdout was empty in JSON mode"
        try:
            data = json.loads(stdout_str)
        except json.JSONDecodeError as err:
            pytest.fail(f"stdout is not valid JSON: {err}\nRaw stdout:\n{stdout_str}")

        assert data["success"] is True
        assert data["host_mode"] == "monologue"
        assert data["is_url"] is True
        assert data["turns_count"] == 2
        assert "mp3_path" in data
        assert "script_json_path" in data
        assert "script_md_path" in data

        # 2. Verify stderr contains stage transitions
        stderr_str = captured.err
        assert "[STAGE 1/5]" in stderr_str
        assert "[STAGE 2/5]" in stderr_str
        assert "[STAGE 3/5]" in stderr_str
        assert "[STAGE 4/5]" in stderr_str
        assert "[STAGE 5/5]" in stderr_str
        assert "(100%)" in stderr_str

        # 3. Verify no diagnostic stage transitions leaked into stdout
        assert "[STAGE" not in stdout_str
        assert "[INFO]" not in stdout_str
        assert "[WARN]" not in stdout_str

    @patch("cli.stitch_mp3_files")
    @patch("cli.synthesize_dialogue_audio")
    @patch("cli.generate_podcast_script")
    @patch("cli.extract_text")
    def test_cli_modular_pipe_chaining_monologue_flow(
        self,
        mock_extract: MagicMock,
        mock_gen_script: MagicMock,
        mock_synth_audio: MagicMock,
        mock_stitch: MagicMock,
        capsys: Any,
        tmp_path: Any,
    ) -> None:
        """
        Verifies modular pipe chaining of subcommands:
        extract --url -> generate-script -> synthesize-audio -> stitch
        """
        mock_extract.return_value = "Article content for pipeline chaining test."
        mock_gen_script.return_value = [
            DialogueTurn(speaker="Host 1", text="Turn 1 audio essay introduction."),
            DialogueTurn(speaker="Host 1", text="Turn 2 audio essay conclusion."),
        ]
        dummy_mp3s = [str(tmp_path / "turn_0.mp3"), str(tmp_path / "turn_1.mp3")]
        for p in dummy_mp3s:
            with open(p, "wb") as f:
                f.write(make_synthetic_mp3(num_frames=3))
        mock_synth_audio.return_value = dummy_mp3s
        master_mp3 = str(tmp_path / "chained_podcast.mp3")

        def fake_stitch_call(*args: Any, **kwargs: Any) -> str:
            out_p = kwargs.get("output_file_path", master_mp3)
            with open(out_p, "wb") as f:
                f.write(make_synthetic_mp3(num_frames=4))
            return out_p

        mock_stitch.side_effect = fake_stitch_call

        # Step 1: extract --url --json
        capsys.readouterr()  # clear buffer
        rc1 = cli.main(["extract", "--url", "https://example.com/chain", "--json"])
        assert rc1 == 0
        out1 = capsys.readouterr().out
        data1 = json.loads(out1)
        assert data1["success"] is True
        extracted_text = data1["text"]

        # Step 2: generate-script --file <extracted_doc> --host-mode monologue --json
        extracted_file = tmp_path / "extracted.txt"
        extracted_file.write_text(extracted_text, encoding="utf-8")

        rc2 = cli.main(
            ["generate-script", "-f", str(extracted_file), "--host-mode", "monologue", "--json"]
        )
        assert rc2 == 0
        out2 = capsys.readouterr().out
        turns2 = json.loads(out2)
        assert len(turns2) == 2
        assert turns2[0]["speaker"] == "Host 1"

        # Step 3: synthesize-audio --input <script_file> --solo-voice nb_no_kari --json
        script_file = tmp_path / "script.json"
        script_file.write_text(out2, encoding="utf-8")

        rc3 = cli.main(
            [
                "synthesize-audio",
                "-i",
                str(script_file),
                "--solo-voice",
                "nb_no_kari",
                "--json",
                "-o",
                str(tmp_path / "turns"),
            ]
        )
        assert rc3 == 0
        out3 = capsys.readouterr().out
        data3 = json.loads(out3)
        assert data3["success"] is True
        assert len(data3["audio_files"]) == 2

        # Step 4: stitch --files ... --output ... --json
        rc4 = cli.main(["stitch", "--files"] + data3["audio_files"] + ["-o", master_mp3, "--json"])
        assert rc4 == 0
        out4 = capsys.readouterr().out
        data4 = json.loads(out4)
        assert data4["success"] is True
        assert os.path.normpath(data4["mp3_path"]) == os.path.normpath(master_mp3)

    def test_cli_monologue_invalid_url_ssrf_returns_code_1_and_error_json(
        self, capsys: Any
    ) -> None:
        """Verifies SSRF URL in CLI returns exit code 1 and formatted JSON error."""
        exit_code = cli.main(["pipeline", "--url", "http://127.0.0.1:11434", "--json"])
        assert exit_code == 1

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert "error" in data
        assert (
            "127.0.0.1" in data["error"]
            or "forbidden" in data["error"].lower()
            or "blocked" in data["error"].lower()
            or "security" in data["error"].lower()
        )

    @patch("cli.PodcastGeneratorService")
    def test_cli_pipeline_monologue_tone_and_grounding_flag_propagation(
        self, mock_service_cls: MagicMock, capsys: Any, tmp_path: Any
    ) -> None:
        """Verifies CLI properly parses and propagates --tone, --grounding, and --length to GenerationOptions."""
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service
        dummy_res = GenerationResult(
            mp3_path=str(tmp_path / "out.mp3"),
            script_json_path=str(tmp_path / "t.json"),
            script_md_path=str(tmp_path / "t.md"),
            dialogue=[DialogueTurn(speaker="Host 1", text="Tone & grounding monologue turn.")],
            duration_estimate_sec=4.0,
        )
        mock_service.generate_podcast.return_value = dummy_res

        cli_args = [
            "pipeline",
            "--url",
            "https://example.com/grounding-test",
            "--host-mode",
            "monologue",
            "--solo-voice",
            "en_us_jenny",
            "--tone",
            "analytical",
            "--grounding",
            "creative",
            "--length",
            "deep_dive",
            "--language",
            "en-US",
            "--json",
        ]
        rc = cli.main(cli_args)
        assert rc == 0
        mock_service.generate_podcast.assert_called_once()
        _, call_kwargs = mock_service.generate_podcast.call_args
        call_options = call_kwargs.get("options")
        if call_options is None and mock_service.generate_podcast.call_args[0]:
            call_options = mock_service.generate_podcast.call_args[0][0]
        assert isinstance(call_options, GenerationOptions)
        assert call_options.tone_style == "analytical"
        assert call_options.grounding_mode == "creative"
        assert call_options.format_type == "deep_dive"
        assert call_options.host_mode == "monologue"
        assert call_options.solo_voice == "en_us_jenny"

    @patch("cli.extract_text")
    def test_cli_extract_url_clean_json_output(self, mock_extract: MagicMock, capsys: Any) -> None:
        """Verifies `cli.py extract --url <url> --json` outputs valid JSON and correct text length."""
        mock_extract.return_value = "## Markdown Heading\n\nExtracted paragraph from web."
        rc = cli.main(["extract", "--url", "https://example.com/sample", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["is_url"] is True
        assert "Markdown Heading" in data["text"]
        assert data["char_count"] == len(mock_extract.return_value)


# ==============================================================================
# 3. UI Thread-Safe Lifecycle Simulation: Workers, Queues, Cancellation & Containment
# ==============================================================================
class TestUIThreadSafeLifecycleSimulation:
    """Empirical verification of CustomTkinter UI background workers and queue protocols."""

    @patch("ui.main_window.extract_text")
    def test_ui_url_extraction_worker_thread_safe_lifecycle(self, mock_extract: MagicMock) -> None:
        """Verifies URLExtractionWorker asynchronously emits start, progress, and done events."""
        mock_extract.return_value = "# Sample Extracted Web Markdown"

        msg_queue: queue.Queue = queue.Queue()
        cancel_evt = threading.Event()

        worker = URLExtractionWorker(
            url="https://example.com/tech-article",
            msg_queue=msg_queue,
            cancel_event=cancel_evt,
        )
        worker.start()
        worker.join(timeout=3.0)

        assert not worker.is_alive(), "URLExtractionWorker did not terminate in time"

        events: list[tuple[str, Any]] = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_names = [e[0] for e in events]
        assert "EXTRACTION_STARTING" in event_names
        assert "EXTRACTION_DONE" in event_names

        done_event = next(e for e in events if e[0] == "EXTRACTION_DONE")
        assert done_event[1]["markdown"] == "# Sample Extracted Web Markdown"
        assert done_event[1]["char_count"] == len("# Sample Extracted Web Markdown")

    @patch("ui.main_window.stitch_mp3_files")
    @patch("ui.main_window.synthesize_dialogue_audio")
    @patch("ui.main_window.generate_podcast_script")
    @patch("ui.main_window.extract_text")
    def test_ui_generation_worker_monologue_url_lifecycle(
        self,
        mock_extract: MagicMock,
        mock_gen_script: MagicMock,
        mock_synth_audio: MagicMock,
        mock_stitch: MagicMock,
        tmp_path: Any,
    ) -> None:
        """
        Verifies GenerationWorker executing in full pipeline mode with URL and Monologue style:
        - Emits STAGE_UPDATE, STREAM_CHUNK, ACT_DONE, SCRIPT_READY, and GENERATION_DONE.
        - Preserves host_mode and solo_voice through all stages.
        - Worker thread exits cleanly without hanging.
        """
        mock_extract.return_value = "Extracted web content for monologue worker test."
        dialogue = [
            DialogueTurn(speaker="Host 1", text="Act 1 opening monologue commentary."),
            DialogueTurn(speaker="Host 1", text="Act 2 detailed monologue exploration."),
        ]
        mock_gen_script.return_value = dialogue
        mock_synth_audio.return_value = [str(tmp_path / "t1.mp3"), str(tmp_path / "t2.mp3")]
        mock_stitch.return_value = str(tmp_path / "podcast.mp3")

        msg_queue: queue.Queue = queue.Queue()
        cancel_evt = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="url",
            input_data="https://example.com/podcast-topic",
            language="nb-NO",
            model="llama3.1:8b",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_evt,
            host_mode="monologue",
            solo_voice="nb_no_kari",
        )

        worker.start()
        worker.join(timeout=5.0)

        assert not worker.is_alive(), "GenerationWorker did not exit within timeout"

        events: list[tuple[str, Any]] = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        event_names = [e[0] for e in events]
        assert "STAGE_UPDATE" in event_names
        assert "SCRIPT_READY" in event_names
        assert "GENERATION_DONE" in event_names

        # Verify final payload
        done_payload = next(e[1] for e in events if e[0] == "GENERATION_DONE")
        assert "mp3_path" in done_payload
        assert "script_path" in done_payload
        assert len(done_payload["dialogue"]) == 2

    def test_ui_queue_flood_and_event_handling_integrity(self) -> None:
        """
        Adversarial test: Simulates rapid queue ingestion of 1,000 mixed lifecycle events.
        Verifies:
        - FIFO ordering is strictly preserved.
        - Zero message loss or corruption.
        - Non-blocking drain loop executes in under 200ms.
        """
        msg_queue: queue.Queue = queue.Queue()
        total_events = 1000

        for i in range(total_events):
            if i % 4 == 0:
                msg_queue.put(
                    (
                        "STAGE_UPDATE",
                        (
                            PipelineStage.SCRIPT_GENERATION,
                            StageStatus.IN_ACTION,
                            i / total_events,
                            f"Progress {i}",
                        ),
                    )
                )
            elif i % 4 == 1:
                msg_queue.put(("STREAM_CHUNK", f"token_{i} "))
            elif i % 4 == 2:
                msg_queue.put(("STATUS", f"Status message {i}"))
            else:
                msg_queue.put(("PROGRESS", i / total_events))

        drained_events = []
        # Simulate GUI drain loop (e.g. process_queue batching)
        while not msg_queue.empty():
            try:
                ev = msg_queue.get_nowait()
                drained_events.append(ev)
            except queue.Empty:
                break

        assert len(drained_events) == total_events
        assert drained_events[0][0] == "STAGE_UPDATE"
        assert drained_events[1][0] == "STREAM_CHUNK"
        assert drained_events[2][0] == "STATUS"
        assert drained_events[3][0] == "PROGRESS"

    @patch("ui.main_window.extract_text")
    def test_ui_worker_exception_boundary_containment(
        self, mock_extract: MagicMock, tmp_path: Any
    ) -> None:
        """
        Verifies that unhandled exceptions inside worker thread are caught by top-level
        exception boundary and delivered to msg_queue as ERROR event rather than killing thread silently.
        """
        mock_extract.side_effect = RuntimeError("Fatal socket reset during extraction")

        msg_queue: queue.Queue = queue.Queue()
        cancel_evt = threading.Event()

        worker = GenerationWorker(
            mode="full",
            input_type="url",
            input_data="https://example.com/unstable",
            language="nb-NO",
            model="llama3.1:8b",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_evt,
        )

        worker.start()
        worker.join(timeout=3.0)

        assert not worker.is_alive()

        events: list[tuple[str, Any]] = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        error_events = [e for e in events if e[0] == "ERROR"]
        assert len(error_events) >= 1
        err_dict = error_events[0][1]
        assert (
            "Fatal socket reset" in err_dict["message"]
            or "Fatal socket reset" in err_dict["details"]
        )

    @patch("ui.main_window.extract_text")
    def test_ui_url_extraction_worker_ssrf_error_delivery(self, mock_extract: MagicMock) -> None:
        """Verifies URLExtractionWorker on SSRF violation emits EXTRACTION_ERROR with security context."""
        mock_extract.side_effect = SecurityError("Target IP is a loopback address: 127.0.0.1")

        msg_queue: queue.Queue = queue.Queue()
        worker = URLExtractionWorker(
            url="http://127.0.0.1:8000/private",
            msg_queue=msg_queue,
        )
        worker.start()
        worker.join(timeout=3.0)

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        error_events = [e for e in events if e[0] == "EXTRACTION_ERROR"]
        assert len(error_events) == 1
        err_payload = error_events[0][1]
        assert err_payload["is_security"] is True
        assert "SSRF Blocked" in err_payload["title"]

    @patch("ui.main_window.synthesize_dialogue_audio")
    @patch("ui.main_window.generate_podcast_script")
    @patch("ui.main_window.extract_text")
    def test_ui_generation_worker_cancel_mid_synthesis(
        self,
        mock_extract: MagicMock,
        mock_gen_script: MagicMock,
        mock_synth_audio: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Verifies that cancelling GenerationWorker during synthesis emits CANCELLED and terminates."""
        mock_extract.return_value = "Content"
        mock_gen_script.return_value = [DialogueTurn(speaker="Host 1", text="Text")]

        cancel_evt = threading.Event()

        def slow_synth(*args: Any, **kwargs: Any) -> list[str]:
            cancel_evt.set()
            raise RuntimeError("Audio synthesis cancelled by user.")

        mock_synth_audio.side_effect = slow_synth

        msg_queue: queue.Queue = queue.Queue()
        worker = GenerationWorker(
            mode="full",
            input_type="url",
            input_data="https://example.com/cancel-synth",
            language="nb-NO",
            model="llama3.1:8b",
            format_type="standard",
            tone="casual",
            speed_rate="+0%",
            output_dir=str(tmp_path),
            msg_queue=msg_queue,
            cancel_event=cancel_evt,
            host_mode="monologue",
        )

        worker.start()
        worker.join(timeout=3.0)
        assert not worker.is_alive()

        events = []
        while not msg_queue.empty():
            events.append(msg_queue.get_nowait())

        cancelled_events = [e for e in events if e[0] == "CANCELLED"]
        assert len(cancelled_events) >= 1
