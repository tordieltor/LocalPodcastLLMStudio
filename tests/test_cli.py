"""
Comprehensive Unit and Integration Test Suite for CLI Engine (cli.py):
- Subcommand parsing (pipeline, extract, generate-script, synthesize-audio, stitch)
- Rapid Topic-Only mode (--topic with zero document input)
- Fine-grained specificity flags (grounding, temperature, tone, length, voices, personas)
- Modular subcommand executions and pipe chaining
- JSON output formatting (--json)
- Quiet mode and stdout/stderr separation (-q/--quiet)
- Dry-run validation (--dry-run)
- POSIX and Windows exit codes (0 for success, 1 for runtime error, 2 for validation error)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import cli
from core.parser import DialogueTurn
from core.pipeline import GenerationResult


class TestCLIArgumentParser:
    """Test suite for CLI argument parser and subcommand dispatch."""

    def test_parser_defaults_and_pipeline_subcommand(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args([])
        assert args.subcommand is None or args.subcommand == "pipeline"
        assert args.model == "llama3.1:8b"
        assert args.url == "http://localhost:11434"
        assert args.language == "nb-NO"
        assert args.length == "standard"
        assert args.tone == "casual"
        assert args.speed == "+0%"
        assert args.quiet is False
        assert args.json is False
        assert args.dry_run is False

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

    def test_fine_grained_specificity_flags(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "pipeline",
                "-f",
                "input_doc.pdf",
                "--grounding",
                "strict",
                "--host1-name",
                "Ada",
                "--host2-name",
                "Alan",
                "--host1-voice",
                "en_US-lessac-medium",
                "--host2-voice",
                "en_US-ryan-medium",
                "--speed",
                "+10%",
                "--temperature",
                "0.50",
                "--system-prompt",
                "You are expert science communicators.",
                "--outdir",
                "./custom_podcast",
            ]
        )
        assert args.file == "input_doc.pdf"
        assert args.grounding == "strict"
        assert args.host1_name == "Ada"
        assert args.host2_name == "Alan"
        assert args.host1_voice == "en_US-lessac-medium"
        assert args.host2_voice == "en_US-ryan-medium"
        assert args.speed == "+10%"
        assert args.temp == 0.50
        assert args.system_prompt == "You are expert science communicators."
        assert args.output_dir == "./custom_podcast"


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

    def test_extract_from_file_with_json_output(self, tmp_path: Any, capsys: Any) -> None:
        doc = tmp_path / "sample.txt"
        doc.write_text("Dette er innholdet i en tekstfil som skal trekkes ut.", encoding="utf-8")

        exit_code = cli.main(["extract", "-f", str(doc), "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["char_count"] > 10
        assert data["word_count"] > 3

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
    def test_generate_script_topic_mode(self, mock_gen_script: MagicMock, capsys: Any) -> None:
        mock_gen_script.return_value = [
            DialogueTurn(speaker="Host 1", text="Welcome to the podcast!"),
            DialogueTurn(speaker="Host 2", text="Glad to be here!"),
        ]

        exit_code = cli.main(
            [
                "generate-script",
                "--topic",
                "Deep Learning",
                "--lang",
                "en-US",
                "--model",
                "llama3.1:8b",
                "--json",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["speaker"] == "Host 1"

    def test_generate_script_dry_run(self, capsys: Any) -> None:
        with patch("cli.OllamaClient.check_connection", return_value=True):
            exit_code = cli.main(
                [
                    "generate-script",
                    "--topic",
                    "Space Exploration",
                    "--dry-run",
                    "--json",
                ]
            )
            assert exit_code == 0
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["dry_run"] is True
            assert data["ollama_online"] is True


class TestSynthesizeAudioSubcommand:
    """Test suite for 'synthesize-audio' subcommand."""

    def test_synthesize_audio_missing_input(self) -> None:
        exit_code = cli.main(["synthesize-audio"])
        assert exit_code == 2

    @patch("cli.synthesize_dialogue_audio")
    def test_synthesize_audio_from_json_file(
        self, mock_synth: MagicMock, tmp_path: Any, capsys: Any
    ) -> None:
        script_file = tmp_path / "script.json"
        script_file.write_text(
            json.dumps(
                [
                    {"speaker": "Host 1", "text": "Turn 1 speech."},
                    {"speaker": "Host 2", "text": "Turn 2 speech."},
                ]
            ),
            encoding="utf-8",
        )

        mock_synth.return_value = [
            str(tmp_path / "turn_001.mp3"),
            str(tmp_path / "turn_002.mp3"),
        ]

        exit_code = cli.main(
            [
                "synthesize-audio",
                "-i",
                str(script_file),
                "--lang",
                "en-US",
                "--json",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert len(data["audio_files"]) == 2

    def test_synthesize_audio_dry_run(self, tmp_path: Any, capsys: Any) -> None:
        script_file = tmp_path / "script.json"
        script_file.write_text(
            json.dumps([{"speaker": "Host 1", "text": "Turn 1"}]),
            encoding="utf-8",
        )

        exit_code = cli.main(
            [
                "synthesize-audio",
                "-i",
                str(script_file),
                "--dry-run",
                "--json",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["dry_run"] is True
        assert data["turns"] == 1


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

    def test_stitch_dry_run(self, tmp_path: Any, capsys: Any) -> None:
        f1 = tmp_path / "f1.mp3"
        f1.write_bytes(b"\xff\xfb\x90\x44" * 10)

        exit_code = cli.main(
            [
                "stitch",
                "-f",
                str(f1),
                "--dry-run",
                "--json",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["dry_run"] is True
        assert data["input_file_count"] == 1


class TestPipelineSubcommand:
    """Test suite for full end-to-end 'pipeline' subcommand."""

    def test_pipeline_missing_input_returns_code_2(self) -> None:
        exit_code = cli.main(["pipeline"])
        assert exit_code == 2

    @patch.object(cli.PodcastGeneratorService, "generate_podcast")
    def test_pipeline_topic_only_run(
        self, mock_gen_pod: MagicMock, tmp_path: Any, capsys: Any
    ) -> None:
        master_mp3 = str(tmp_path / "podcast.mp3")
        json_path = str(tmp_path / "transcript.json")
        md_path = str(tmp_path / "transcript.md")

        mock_gen_pod.return_value = GenerationResult(
            mp3_path=master_mp3,
            script_json_path=json_path,
            script_md_path=md_path,
            dialogue=[
                DialogueTurn(speaker="Host 1", text="Topic discussion 1"),
                DialogueTurn(speaker="Host 2", text="Topic discussion 2"),
            ],
            duration_estimate_sec=8.0,
        )

        exit_code = cli.main(
            [
                "pipeline",
                "--topic",
                "Artificial General Intelligence in 2030",
                "--lang",
                "en-US",
                "--model",
                "llama3.1:8b",
                "--outdir",
                str(tmp_path),
                "--json",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["turns_count"] == 2
        assert "podcast.mp3" in data["mp3_path"]

    def test_pipeline_dry_run(self, capsys: Any) -> None:
        with patch("cli.OllamaClient.check_connection", return_value=True):
            exit_code = cli.main(
                [
                    "pipeline",
                    "--topic",
                    "Neuroscience",
                    "--dry-run",
                    "--json",
                ]
            )
            assert exit_code == 0
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["dry_run"] is True
            assert data["ollama_online"] is True
            assert data["command"] == "pipeline"

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
