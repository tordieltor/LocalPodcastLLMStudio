"""
Comprehensive Unit and Integration Test Suite for CLI Engine (cli.py):
- Subcommand parsing (pipeline, extract, generate-script, synthesize-audio, stitch)
- Rapid Topic-Only mode (--topic with zero document input)
- Safe URL ingestion flags (--url, --timeout, --max-size)
- Monologue / Solo Essay mode (--host-mode, --solo-voice)
- Ollama endpoint disambiguation (-u/--ollama-url vs --url)
- Fine-grained specificity flags (grounding, temperature, tone, length, voices, personas)
- CLILogger stage formatting strictly to stderr ([STAGE X/5] [STATUS] (PCT%) MSG)
- Modular subcommand executions and pipe chaining
- Pure JSON output formatting (--json)
- Quiet mode and stdout/stderr separation (-q/--quiet)
- Dry-run validation (--dry-run)
- POSIX and Windows exit codes (0 for success, 1 for runtime/security error, 2 for validation error)
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import cli
from core.exceptions import SecurityError
from core.parser import DialogueTurn
from core.pipeline import GenerationResult, PipelineStage, StageStatus


class TestCLIArgumentParser:
    """Test suite for CLI argument parser, flag disambiguation, and subcommand dispatch."""

    def test_parser_defaults_and_pipeline_subcommand(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args([])
        assert args.subcommand is None or args.subcommand == "pipeline"
        assert args.model == "llama3.1:8b"
        assert args.ollama_url == "http://localhost:11434"
        assert args.url == ""
        assert args.language == "nb-NO"
        assert args.host_mode == "dialogue"
        assert args.solo_voice == ""
        assert args.length == "standard"
        assert args.tone == "casual"
        assert args.speed == "+0%"
        assert args.quiet is False
        assert args.json is False
        assert args.dry_run is False

    def test_url_and_ollama_endpoint_disambiguation(self) -> None:
        parser = cli.build_parser()
        # Top-level / pipeline
        args = parser.parse_args(
            [
                "pipeline",
                "--url",
                "https://example.com/tech-news",
                "-u",
                "http://ollama-remote:11434",
                "--host-mode",
                "monologue",
                "--solo-voice",
                "en_US-lessac-medium",
            ]
        )
        assert args.url == "https://example.com/tech-news"
        assert args.ollama_url == "http://ollama-remote:11434"
        assert args.host_mode == "monologue"
        assert args.solo_voice == "en_US-lessac-medium"

    def test_extract_subcommand_flags(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "extract",
                "--url",
                "https://example.com/article",
                "--timeout",
                "15.5",
                "--max-size",
                "10485760",
                "-o",
                "out.md",
            ]
        )
        assert args.subcommand == "extract"
        assert args.url == "https://example.com/article"
        assert args.timeout == 15.5
        assert args.max_size == 10485760
        assert args.output == "out.md"

    def test_generate_script_subcommand_flags(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "generate-script",
                "--url",
                "https://example.com/article",
                "--host-mode",
                "monologue",
                "--solo-voice",
                "no_NO-torkil-medium",
                "--ollama-endpoint",
                "http://localhost:11434",
            ]
        )
        assert args.subcommand == "generate-script"
        assert args.url == "https://example.com/article"
        assert args.host_mode == "monologue"
        assert args.solo_voice == "no_NO-torkil-medium"
        assert args.ollama_url == "http://localhost:11434"

    def test_topic_only_argument_parsing(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "--topic",
                "Autonomous AI Agents in 2026",
                "--model",
                "qwen2.5:7b",
                "--lang",
                "en-US",
                "--length",
                "quick",
                "--tone",
                "analytical",
                "--temp",
                "0.85",
                "--json",
            ]
        )
        assert args.topic == "Autonomous AI Agents in 2026"
        assert args.model == "qwen2.5:7b"
        assert args.language == "en-US"
        assert args.length == "quick"
        assert args.tone == "analytical"
        assert args.temp == 0.85
        assert args.json is True


class TestCLILoggerAndStderrFormatting:
    """Test suite for CLILogger stderr streaming and stage progress formatting."""

    def test_cli_logger_stage_formatted_tags_to_stderr(self, capsys: Any) -> None:
        logger = cli.CLILogger(quiet=False, json_mode=False)
        logger.stage(PipelineStage.URL_INGESTION, StageStatus.IN_ACTION, 0.0, "Validating URL...")
        logger.stage(PipelineStage.URL_INGESTION, StageStatus.COMPLETED, 1.0, "URL validated.")
        logger.stage(
            PipelineStage.SCRIPT_GENERATION, StageStatus.IN_ACTION, 0.45, "Writing Act 2 of 3..."
        )
        logger.stage(PipelineStage.TTS_SYNTHESIS, StageStatus.FAILED, 0.10, "TTS crashed.")

        captured = capsys.readouterr()
        # Stdout must remain pure empty
        assert captured.out == ""
        # Stderr must contain formatted stage tags
        assert "[STAGE 1/5] [IN_ACTION] (  0%) Validating URL..." in captured.err
        assert "[STAGE 1/5] [COMPLETED] (100%) URL validated." in captured.err
        assert "[STAGE 3/5] [IN_ACTION] ( 45%) Writing Act 2 of 3..." in captured.err
        assert "[STAGE 4/5] [FAILED] ( 10%) TTS crashed." in captured.err

    def test_cli_logger_quiet_mode_suppresses_all_stderr(self, capsys: Any) -> None:
        logger = cli.CLILogger(quiet=True, json_mode=False)
        logger.info("Informational message")
        logger.stage(PipelineStage.URL_INGESTION, StageStatus.IN_ACTION, 0.0, "Starting stage")
        logger.progress(0.5, "Halfway done")
        logger.warn("Warning message")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_cli_logger_json_mode_preserves_stage_on_stderr(self, capsys: Any) -> None:
        logger = cli.CLILogger(quiet=False, json_mode=True)
        logger.info("Should be suppressed in json mode")
        logger.progress(0.2, "Should be suppressed in json mode")
        logger.stage(PipelineStage.URL_INGESTION, StageStatus.IN_ACTION, 0.0, "Active stage")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "[INFO]" not in captured.err
        assert "[STAGE 1/5] [IN_ACTION] (  0%) Active stage" in captured.err


class TestExtractSubcommand:
    """Test suite for 'extract' subcommand."""

    def test_extract_missing_arguments_returns_code_2(self) -> None:
        exit_code = cli.main(["extract"])
        assert exit_code == 2

    def test_extract_from_text_to_stdout(self, capsys: Any) -> None:
        sample_text = "This is a direct raw text string for extraction testing."
        exit_code = cli.main(["extract", "--text", sample_text])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert sample_text in captured.out

    @patch("cli.extract_text", return_value="# Extracted Web Article\n\nArticle body paragraph.")
    def test_extract_from_url_to_stdout(self, mock_ext: MagicMock, capsys: Any) -> None:
        exit_code = cli.main(["extract", "--url", "https://example.com/sample"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "# Extracted Web Article" in captured.out
        assert "[STAGE 1/5]" in captured.err
        assert "[STAGE 2/5]" in captured.err

    @patch("cli.extract_text", return_value="# Extracted Web Article\n\nArticle body paragraph.")
    def test_extract_from_url_with_json_output(self, mock_ext: MagicMock, capsys: Any) -> None:
        exit_code = cli.main(["extract", "--url", "https://example.com/sample", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["is_url"] is True
        assert data["char_count"] > 10

    @patch("cli.extract_text", side_effect=SecurityError("Blocked SSRF loopback"))
    def test_extract_ssrf_error_returns_code_1(self, mock_ext: MagicMock, capsys: Any) -> None:
        exit_code = cli.main(["extract", "--url", "http://127.0.0.1:11434", "--json"])
        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert "Blocked SSRF" in data["error"]

    def test_extract_dry_run(self, capsys: Any) -> None:
        exit_code = cli.main(["extract", "-t", "Solar Flares", "--dry-run", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["dry_run"] is True
        assert data["status"] == "valid"


class TestGenerateScriptSubcommand:
    """Test suite for 'generate-script' subcommand."""

    def test_generate_script_missing_args(self) -> None:
        exit_code = cli.main(["generate-script"])
        assert exit_code == 2

    @patch("cli.generate_podcast_script")
    def test_generate_script_monologue_mode(self, mock_gen_script: MagicMock, capsys: Any) -> None:
        mock_gen_script.return_value = [
            DialogueTurn(speaker="Host 1", text="Solo host essay paragraph 1."),
            DialogueTurn(speaker="Host 1", text="Solo host essay paragraph 2."),
        ]

        exit_code = cli.main(
            [
                "generate-script",
                "--topic",
                "Solo Monologue Essay",
                "--host-mode",
                "monologue",
                "--solo-voice",
                "en_US-lessac-medium",
                "--json",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["speaker"] == "Host 1"

        # Verify host_mode was passed
        _, kwargs = mock_gen_script.call_args
        assert kwargs["host_mode"] == "monologue"

    def test_generate_script_dry_run(self, capsys: Any) -> None:
        with patch("cli.OllamaClient.check_connection", return_value=True):
            exit_code = cli.main(
                [
                    "generate-script",
                    "--topic",
                    "Space Exploration",
                    "--host-mode",
                    "monologue",
                    "--dry-run",
                    "--json",
                ]
            )
            assert exit_code == 0
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["dry_run"] is True
            assert data["ollama_online"] is True
            assert data["host_mode"] == "monologue"


class TestSynthesizeAudioSubcommand:
    """Test suite for 'synthesize-audio' subcommand."""

    def test_synthesize_audio_missing_input(self) -> None:
        exit_code = cli.main(["synthesize-audio"])
        assert exit_code == 2

    @patch("cli.synthesize_dialogue_audio")
    def test_synthesize_audio_with_solo_voice(
        self, mock_synth: MagicMock, tmp_path: Any, capsys: Any
    ) -> None:
        script_file = tmp_path / "script.json"
        script_file.write_text(
            json.dumps([{"speaker": "Host 1", "text": "Solo turn speech."}]),
            encoding="utf-8",
        )

        mock_synth.return_value = [str(tmp_path / "turn_001.mp3")]

        exit_code = cli.main(
            [
                "synthesize-audio",
                "-i",
                str(script_file),
                "--solo-voice",
                "en_US-lessac-medium",
                "--json",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert len(data["audio_files"]) == 1

        _, kwargs = mock_synth.call_args
        assert kwargs["solo_voice"] == "en_US-lessac-medium"


class TestStitchSubcommand:
    """Test suite for 'stitch' subcommand."""

    def test_stitch_missing_files(self) -> None:
        exit_code = cli.main(["stitch"])
        assert exit_code == 2

    @patch("cli.stitch_mp3_files")
    def test_stitch_audio_files(self, mock_stitch: MagicMock, tmp_path: Any, capsys: Any) -> None:
        f1 = tmp_path / "f1.mp3"
        f2 = tmp_path / "f2.mp3"
        f1.write_bytes(b"\xff\xfb\x90\x44" * 10)
        f2.write_bytes(b"\xff\xfb\x90\x44" * 10)

        out_mp3 = tmp_path / "master.mp3"
        out_mp3.write_bytes(b"\xff\xfb\x90\x44" * 20)

        mock_stitch.return_value = str(out_mp3)

        exit_code = cli.main(
            [
                "stitch",
                "-f",
                str(f1),
                str(f2),
                "-o",
                str(out_mp3),
                "--json",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert "master.mp3" in data["mp3_path"]


class TestPipelineSubcommand:
    """Test suite for full end-to-end 'pipeline' subcommand."""

    def test_pipeline_missing_input_returns_code_2(self) -> None:
        exit_code = cli.main(["pipeline"])
        assert exit_code == 2

    @patch.object(cli.PodcastGeneratorService, "generate_podcast")
    def test_pipeline_monologue_run(
        self, mock_gen_pod: MagicMock, tmp_path: Any, capsys: Any
    ) -> None:
        master_mp3 = str(tmp_path / "podcast.mp3")
        json_path = str(tmp_path / "transcript.json")
        md_path = str(tmp_path / "transcript.md")

        mock_gen_pod.return_value = GenerationResult(
            mp3_path=master_mp3,
            script_json_path=json_path,
            script_md_path=md_path,
            dialogue=[DialogueTurn(speaker="Host 1", text="Solo essay 1")],
            duration_estimate_sec=4.0,
        )

        exit_code = cli.main(
            [
                "pipeline",
                "--topic",
                "Quantum Computing Essay",
                "--host-mode",
                "monologue",
                "--solo-voice",
                "en_US-lessac-medium",
                "--outdir",
                str(tmp_path),
                "--json",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["host_mode"] == "monologue"
        assert "podcast.mp3" in data["mp3_path"]

        # Check options passed to generate_podcast
        _, kwargs = mock_gen_pod.call_args
        opts = kwargs["options"]
        assert opts.host_mode == "monologue"
        assert opts.solo_voice == "en_US-lessac-medium"

    @patch.object(cli.PodcastGeneratorService, "generate_podcast")
    def test_pipeline_url_input_run(
        self, mock_gen_pod: MagicMock, tmp_path: Any, capsys: Any
    ) -> None:
        master_mp3 = str(tmp_path / "podcast.mp3")
        mock_gen_pod.return_value = GenerationResult(
            mp3_path=master_mp3,
            script_json_path=str(tmp_path / "transcript.json"),
            script_md_path=str(tmp_path / "transcript.md"),
            dialogue=[DialogueTurn(speaker="Host 1", text="Turn 1")],
            duration_estimate_sec=4.0,
        )

        exit_code = cli.main(
            [
                "pipeline",
                "--url",
                "https://example.com/article",
                "--outdir",
                str(tmp_path),
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        # Clean stdout contains only the output path
        assert captured.out.strip() == os.path.abspath(master_mp3)

    def test_pipeline_dry_run(self, capsys: Any) -> None:
        with patch("cli.OllamaClient.check_connection", return_value=True):
            exit_code = cli.main(
                [
                    "pipeline",
                    "--url",
                    "https://example.com/article",
                    "--host-mode",
                    "monologue",
                    "--dry-run",
                    "--json",
                ]
            )
            assert exit_code == 0
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["dry_run"] is True
            assert data["ollama_online"] is True
            assert data["is_url"] is True
            assert data["host_mode"] == "monologue"

    @patch.object(cli.PodcastGeneratorService, "generate_podcast")
    def test_pipeline_runtime_error_returns_code_1(
        self, mock_gen_pod: MagicMock, capsys: Any
    ) -> None:
        mock_gen_pod.side_effect = RuntimeError("Ollama connection aborted")

        exit_code = cli.main(
            [
                "pipeline",
                "--topic",
                "Error Scenario",
                "--json",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert "Ollama connection aborted" in data["error"]
