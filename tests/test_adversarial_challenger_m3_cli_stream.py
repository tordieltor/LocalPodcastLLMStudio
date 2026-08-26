"""
Adversarial Empirical Challenge Test Suite for Milestone 3 (CLI Stream Separation & Flag Matrix)
================================================================================================
Author: Challenger 2 (critic, specialist)
Framework: rational-e2e-testing (5-tier empirical architecture)

Covers:
- Tier 1: CLI stdout/stderr strict stream separation under --json (pure JSON stdout, stage tags stderr)
- Tier 2: Subcommand flag permutations (--url, --host-mode, --solo-voice, --ollama-url, --dry-run, -q/--quiet)
- Tier 3: Error exit codes & SSRF URL injection via CLI with clean stderr/stdout and 0 tracebacks
- Tier 4: Modular subcommand pipe chaining & OS-level subprocess execution
- Tier 5: Adversarial edge cases, quiet mode suppression, invalid subcommands, and parameter matrices
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import cli
from core.parser import DialogueTurn
from core.pipeline import GenerationResult, PipelineStage, StageStatus


class TestTier1StreamSeparationUnderJSON:
    """Tier 1: Strict stream separation between stdout and stderr under --json."""

    def test_pipeline_json_mode_stream_separation(self, capsys: Any) -> None:
        """Verifies pipeline with --json outputs valid JSON on stdout and [STAGE X/5] on stderr."""
        with patch.object(cli.PodcastGeneratorService, "generate_podcast") as mock_gen:

            def fake_gen(
                options: Any, progress_callback: Any = None, stage_callback: Any = None
            ) -> GenerationResult:
                if stage_callback:
                    stage_callback(
                        PipelineStage.URL_INGESTION, StageStatus.IN_ACTION, 0.0, "Checking URL..."
                    )
                    stage_callback(
                        PipelineStage.CONTENT_EXTRACTION,
                        StageStatus.COMPLETED,
                        1.0,
                        "Extracted content.",
                    )
                    stage_callback(
                        PipelineStage.SCRIPT_GENERATION, StageStatus.IN_ACTION, 0.5, "Act 2..."
                    )
                    stage_callback(
                        PipelineStage.TTS_SYNTHESIS, StageStatus.IN_ACTION, 0.8, "Synthesizing..."
                    )
                    stage_callback(
                        PipelineStage.AUDIO_ASSEMBLY, StageStatus.COMPLETED, 1.0, "Stitched."
                    )
                return GenerationResult(
                    mp3_path="output/test_episode.mp3",
                    script_json_path="output/test_script.json",
                    script_md_path="output/test_script.md",
                    dialogue=[DialogueTurn(speaker="Host 1", text="Hello world")],
                    duration_estimate_sec=10.0,
                )

            mock_gen.side_effect = fake_gen

            exit_code = cli.main(["pipeline", "--topic", "Adversarial Stream Test", "--json"])
            assert exit_code == 0

            captured = capsys.readouterr()
            # 1. Stdout must be 100% valid JSON and contain NO diagnostic logging
            parsed = json.loads(captured.out)
            assert parsed["success"] is True
            assert "test_episode.mp3" in parsed["mp3_path"]
            assert "[STAGE" not in captured.out
            assert "[INFO]" not in captured.out

            # 2. Stderr must contain all 5 formatted stage transitions
            for st in range(1, 6):
                assert f"[STAGE {st}/5]" in captured.err

    def test_extract_url_json_mode_stream_separation(self, capsys: Any) -> None:
        """Verifies extract --url under --json sends stages to stderr and clean JSON to stdout."""
        with patch("cli.extract_text", return_value="# Article Title\n\nArticle body content."):
            exit_code = cli.main(
                ["extract", "--url", "https://example.com/adversarial-stream", "--json"]
            )
            assert exit_code == 0

            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert parsed["success"] is True
            assert parsed["is_url"] is True
            assert parsed["char_count"] > 10

            assert "[STAGE 1/5]" in captured.err
            assert "[STAGE 2/5]" in captured.err
            assert "[STAGE" not in captured.out

    def test_quiet_mode_with_json_suppresses_stderr_completely(self, capsys: Any) -> None:
        """Verifies -q/--quiet combined with --json leaves stderr empty (0 bytes)."""
        with patch("cli.extract_text", return_value="Sample content"):
            exit_code = cli.main(
                ["extract", "--url", "https://example.com/quiet-test", "-q", "--json"]
            )
            assert exit_code == 0

            captured = capsys.readouterr()
            assert captured.err == ""
            parsed = json.loads(captured.out)
            assert parsed["success"] is True


class TestTier2FlagPermutationsAndDisambiguation:
    """Tier 2: Flag permutations across subcommands and parameter matrices."""

    @pytest.mark.parametrize("host_mode", ["dialogue", "monologue"])
    @pytest.mark.parametrize("length", ["quick", "standard", "deep_dive", "extended"])
    @pytest.mark.parametrize("tone", ["casual", "analytical", "debate"])
    @pytest.mark.parametrize("grounding", ["strict", "creative", "open_topic"])
    def test_generate_script_flag_permutations(
        self,
        host_mode: str,
        length: str,
        tone: str,
        grounding: str,
        capsys: Any,
    ) -> None:
        """Adversarially verifies all 72 combinations of script generation flags."""
        with patch("cli.generate_podcast_script") as mock_gen:
            mock_gen.return_value = [DialogueTurn(speaker="Host 1", text="Test turn")]

            exit_code = cli.main(
                [
                    "generate-script",
                    "--topic",
                    "Permutation Matrix",
                    "--host-mode",
                    host_mode,
                    "--solo-voice",
                    "en_US-lessac-medium" if host_mode == "monologue" else "",
                    "--length",
                    length,
                    "--tone",
                    tone,
                    "--grounding",
                    grounding,
                    "--json",
                ]
            )
            assert exit_code == 0
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert isinstance(parsed, list)
            assert len(parsed) == 1

    def test_ollama_url_disambiguation_with_source_url(self) -> None:
        """Verifies -u / --ollama-url is not confused with --url."""
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "pipeline",
                "--url",
                "https://en.wikipedia.org/wiki/Podcast",
                "-u",
                "http://remote-ollama:11434",
                "--host-mode",
                "monologue",
                "--solo-voice",
                "nb_NO-torkil-medium",
            ]
        )
        assert args.url == "https://en.wikipedia.org/wiki/Podcast"
        assert args.ollama_url == "http://remote-ollama:11434"
        assert args.host_mode == "monologue"
        assert args.solo_voice == "nb_NO-torkil-medium"

    def test_synthesize_audio_solo_voice_kwarg_forwarding(self, capsys: Any) -> None:
        """Verifies --solo-voice is passed down to synthesize_dialogue_audio."""
        with patch("cli.synthesize_dialogue_audio") as mock_synth:
            mock_synth.return_value = ["out/turn1.mp3"]
            with patch(
                "cli._read_stdin_or_file",
                return_value=json.dumps([{"speaker": "Host 1", "text": "Turn"}]),
            ):
                exit_code = cli.main(
                    [
                        "synthesize-audio",
                        "-i",
                        "dummy.json",
                        "--solo-voice",
                        "en_US-lessac-medium",
                        "--json",
                    ]
                )
                assert exit_code == 0
                captured = capsys.readouterr()
                parsed = json.loads(captured.out)
                assert parsed["success"] is True
                assert mock_synth.call_args[1].get("solo_voice") == "en_US-lessac-medium"


class TestTier3SSRFAndExitCodesAdversarial:
    """Tier 3: SSRF injection attacks and exit code invariants without tracebacks."""

    @pytest.mark.parametrize(
        "target_url",
        [
            "http://127.0.0.1:11434",
            "http://localhost:8080",
            "http://169.254.169.254/latest/meta-data",
            "http://192.168.1.1",
            "http://10.0.0.1",
            "http://172.16.0.1",
            "http://[::1]:8080",
            "file:///etc/passwd",
            "gopher://127.0.0.1:6379",
        ],
    )
    def test_extract_ssrf_attacks_return_code_1_no_traceback_json(
        self, target_url: str, capsys: Any
    ) -> None:
        """Verifies SSRF attacks return exit code 1 with clean JSON error and zero tracebacks."""
        exit_code = cli.main(["extract", "--url", target_url, "--json"])
        assert exit_code == 1

        captured = capsys.readouterr()
        # Parse stdout JSON
        parsed = json.loads(captured.out)
        assert parsed["success"] is False
        assert "error" in parsed

        # Stderr and stdout must NOT contain python tracebacks
        assert "Traceback (most recent call last)" not in captured.err
        assert "Traceback (most recent call last)" not in captured.out

    def test_extract_ssrf_non_json_mode_stderr_formatting(self, capsys: Any) -> None:
        """Verifies SSRF attacks in plaintext mode output [ERROR] to stderr and code 1."""
        exit_code = cli.main(["extract", "--url", "http://127.0.0.1:11434"])
        assert exit_code == 1

        captured = capsys.readouterr()
        assert captured.out.strip() == ""
        assert "[ERROR]" in captured.err
        assert "Traceback (most recent call last)" not in captured.err

    def test_missing_subcommand_inputs_return_code_2(self) -> None:
        """Verifies missing required CLI parameters exit with code 2 without tracebacks."""
        for subcmd in ["extract", "generate-script", "synthesize-audio", "stitch", "pipeline"]:
            code = cli.main([subcmd])
            assert code == 2


class TestTier4SubprocessOSIsolation:
    """Tier 4: True OS-level subprocess execution testing stream separation and dry runs."""

    def test_subprocess_dry_run_pipeline_json(self) -> None:
        """Executes cli.py as an OS process to verify stdout/stderr separation."""
        cmd = [
            sys.executable,
            "cli.py",
            "pipeline",
            "--topic",
            "OS Subprocess Stream Test",
            "--host-mode",
            "monologue",
            "--solo-voice",
            "en_US-lessac-medium",
            "--dry-run",
            "--json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        parsed = json.loads(proc.stdout)
        assert parsed["dry_run"] is True
        assert parsed["host_mode"] == "monologue"
        assert "Traceback" not in proc.stdout
        assert "Traceback" not in proc.stderr

    def test_subprocess_ssrf_blocking_exit_code_1(self) -> None:
        """Executes cli.py with SSRF payload in subprocess to test process exit code 1."""
        cmd = [
            sys.executable,
            "cli.py",
            "extract",
            "--url",
            "http://169.254.169.254/latest/meta-data",
            "--json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 1
        parsed = json.loads(proc.stdout)
        assert parsed["success"] is False
        assert "Traceback" not in proc.stdout
        assert "Traceback" not in proc.stderr


class TestTier5AdversarialPipingAndEdgeCases:
    """Tier 5: Stdin pipe chaining, malformed inputs, and unusual flags."""

    @patch("cli.generate_podcast_script")
    def test_pipe_chaining_via_stdin_hyphen(
        self, mock_gen: MagicMock, monkeypatch: Any, capsys: Any
    ) -> None:
        """Verifies passing '-' reads from stdin for generate-script."""
        mock_gen.return_value = [DialogueTurn(speaker="Host 1", text="Turn from stdin")]
        monkeypatch.setattr("sys.stdin", io.StringIO("Raw text piped from stdin"))

        exit_code = cli.main(["generate-script", "-i", "-", "--json"])
        assert exit_code == 0

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["text"] == "Turn from stdin"
