"""
Comprehensive Regression Test Suite for P0-P3 Stability, Security & Quality Remediations
========================================================================================
Covers reconciled Jules optimizations and codebase-wide defect fixes across:
- Core engine (DNS-rebinding SSRF defense, iterative deep HTML parsing, HTML entity escaping
  in DOM serialization, UI voice label resolution, offline-by-default TTS privacy,
  multi-rate WAV resampling, pipeline temp cleanup, MCI player atexit lifecycle).
- Desktop GUI & bootstrap (`app.py --version` / `--self-test`, `--noconsole` crash logging,
  URL extraction dual-event deduplication).
- Interactive TUI (`python -m tui`, MCI `PLAYER_FILE_LOADED` loop prevention, Dashboard
  `[Space]` playback events, modal action routing, inline editor `F2` precedence, idle `Esc`
  navigation, signal handler chaining, Rich markup escaping).
- Headless CLI & tooling (root `--json` flag inheritance, `--text` raw input, structured JSON
  errors on corrupt/missing files, `check_env.py`, `LocalPodcastLLMStudio.spec`, and safe
  bounded Jules PR triage filtering).
"""

from __future__ import annotations

import atexit
import io
import json
import os
import signal
import struct
import types
import wave
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

import app as desktop_app
import check_env
import cli
from core.exceptions import AudioSynthesisError, SecurityError
from core.extractor import (
    convert_html_to_markdown,
    extract_text_from_url,
    strip_html_boilerplate,
)
from core.mp3_stitcher import WAVStitcher
from core.parser import DialogueTurn
from core.pipeline import GenerationOptions, PodcastGeneratorService
from core.player import WindowsAudioPlayer
from core.tts import TTSEngine, resolve_voice_identifier, synthesize_turn
from scripts import bulk_close_superseded_prs as pr_triage
from tui.__main__ import build_arg_parser as build_tui_arg_parser
from tui.app import TUIApplication
from tui.state import ModalType, PlaybackMode, ScreenMode, TUIState
from tui.terminal import TerminalManager
from ui.main_window import _is_duplicate_url_event


def _make_pcm_wav_bytes(
    *,
    framerate: int = 22050,
    channels: int = 1,
    sampwidth: int = 2,
    duration_ms: int = 80,
    amplitude: int = 4000,
) -> bytes:
    """Create a deterministic in-memory PCM WAV byte buffer for multi-rate stitcher tests."""
    n_frames = max(1, int(framerate * (duration_ms / 1000.0)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        samples: list[int] = []
        for idx in range(n_frames):
            val = amplitude if (idx % 20) < 10 else -amplitude
            for _ in range(channels):
                samples.append(val)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


# ==============================================================================
# 1. Core Security, HTML, Parser, TTS, Stitcher, Pipeline & Player Regressions
# ==============================================================================


class TestCoreRemediations:
    def test_ssrf_dns_rebinding_peer_socket_verification_blocks_loopback(self) -> None:
        """Even if pre-request DNS returns a public IP, a rebound loopback peer socket is blocked."""
        fake_sock = MagicMock()
        fake_sock.getpeername.return_value = ("127.0.0.1", 80)

        fake_conn = MagicMock()
        fake_conn.sock = fake_sock

        fake_raw = MagicMock()
        fake_raw._connection = fake_conn

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.is_redirect = False
        fake_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        fake_resp.raw = fake_raw
        fake_resp.iter_content.return_value = [b"<html><body>Secret internal page</body></html>"]

        public_addrinfo = [(2, 1, 6, "", ("93.184.216.34", 0))]
        with (
            patch("socket.getaddrinfo", return_value=public_addrinfo),
            patch("requests.get", return_value=fake_resp),
        ):
            with pytest.raises(SecurityError, match="DNS rebinding / SSRF blocked"):
                extract_text_from_url("http://rebind.example.com/article")

        fake_resp.close.assert_called_once()

    def test_deeply_nested_html_2500_levels_parses_iteratively_without_recursion_error(
        self,
    ) -> None:
        """Iterative DOM traversal handles >2,000 nested tags without Python RecursionError."""
        depth = 2500
        deep_html = (
            "<html><body><article>"
            + ("<div>" * depth)
            + "<h2>Deep Heading</h2><p>Resilient iterative extraction payload.</p>"
            + ("</div>" * depth)
            + "</article></body></html>"
        )
        cleaned = strip_html_boilerplate(deep_html)
        markdown = convert_html_to_markdown(cleaned)
        assert "Deep Heading" in markdown
        assert "Resilient iterative extraction payload." in markdown

    def test_html_boilerplate_serializer_escapes_text_node_html_entities(self) -> None:
        """DOM serializer escapes `<` / `>` / `&` inside text nodes so entity-encoded tags stay inert."""
        raw_html = (
            "<html><body><article>"
            "<p>Literal &lt;script&gt;alert(1)&lt;/script&gt; &amp; safe text.</p>"
            "</article></body></html>"
        )
        cleaned_html = strip_html_boilerplate(raw_html)
        assert "<script>" not in cleaned_html
        assert "&lt;script&gt;" in cleaned_html

    def test_resolve_voice_identifier_maps_ui_labels_to_canonical_piper_models(self) -> None:
        """Human-readable UI dropdown labels resolve cleanly to Piper ONNX model identifiers."""
        assert resolve_voice_identifier("Jenny (Female)", language="en-US") == "en_US-lessac-medium"
        assert resolve_voice_identifier("Amy (Female)", language="en-US") == "en_US-amy-medium"
        assert resolve_voice_identifier("Guy (Male)", language="en-US") == "en_US-ryan-medium"
        assert resolve_voice_identifier("Kari (Female)", language="nb-NO") == "no_NO-torkil-medium"
        assert resolve_voice_identifier("Ola (Male)", language="nb-NO") == "no_NO-torkil-medium"

        engine = TTSEngine(
            language="en-US",
            host1_voice="Amy (Female)",
            host2_voice="Joe (Male)",
        )
        assert engine.get_voice_for_speaker("Host 1") == "en_US-amy-medium"
        assert engine.get_voice_for_speaker("Host 2") == "en_US-joe-medium"

    @pytest.mark.asyncio
    async def test_tts_offline_by_default_blocks_real_cloud_edge_tts_and_honors_strict_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Real Edge-TTS module is NOT invoked when allow_cloud_tts=False; strict mode raises AudioSynthesisError."""
        real_like_edge = types.ModuleType("edge_tts")
        real_like_edge.__file__ = "/fake/site-packages/edge_tts/__init__.py"
        communicate_spy = MagicMock()
        real_like_edge.Communicate = communicate_spy  # type: ignore[attr-defined]

        monkeypatch.setitem(__import__("sys").modules, "edge_tts", real_like_edge)
        monkeypatch.delenv("LOCALPODCAST_ALLOW_CLOUD_TTS", raising=False)

        with (
            patch("core.tts.get_or_load_piper_voice", return_value=None),
            patch("core.tts._synthesize_via_piper_cli", return_value=b""),
        ):
            with pytest.raises(AudioSynthesisError, match="cloud Edge-TTS is disabled by default"):
                await synthesize_turn(
                    text="Offline privacy verification turn.",
                    voice="en_US-lessac-medium",
                    allow_cloud_tts=False,
                    allow_silent_fallback=False,
                )

        communicate_spy.assert_not_called()

    def test_wav_stitcher_resamples_mixed_sample_rates_and_channels(self) -> None:
        """WAVStitcher normalizes 16kHz mono + 22.05kHz stereo segments into a consistent WAV."""
        seg_16k_mono = _make_pcm_wav_bytes(framerate=16000, channels=1, duration_ms=100)
        seg_22k_stereo = _make_pcm_wav_bytes(framerate=22050, channels=2, duration_ms=100)

        stitched = WAVStitcher.stitch([seg_16k_mono, seg_22k_stereo], pause_ms=100)
        assert stitched.startswith(b"RIFF")

        with wave.open(io.BytesIO(stitched), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            total_frames = wf.getnframes()
            assert 4500 <= total_frames <= 5100

    def test_pipeline_cleans_up_temp_directory_when_synthesis_raises(self, tmp_path: Path) -> None:
        """PodcastGeneratorService removes ephemeral TemporaryDirectory even when TTS fails."""
        service = PodcastGeneratorService(ollama_url="http://localhost:11434")
        opts = GenerationOptions(
            content="Artificial intelligence safety and alignment fundamentals.",
            language="en-US",
            model="llama3.1:8b",
            output_dir=str(tmp_path / "out"),
            is_raw_text=True,
        )
        fake_turns = [DialogueTurn(speaker="Host 1", text="Hello listeners.")]
        captured_temp_dirs: list[str] = []

        def failing_synth(**kwargs: Any) -> list[str]:
            out_dir = str(kwargs["output_dir"])
            captured_temp_dirs.append(out_dir)
            (Path(out_dir) / "partial_turn.wav").write_bytes(b"RIFF")
            raise AudioSynthesisError("Simulated TTS failure")

        with (
            patch("core.pipeline.generate_podcast_script", return_value=fake_turns),
            patch("core.pipeline.synthesize_dialogue_audio", side_effect=failing_synth),
        ):
            with pytest.raises(AudioSynthesisError, match="Simulated TTS failure"):
                service.generate_podcast(opts)

        assert len(captured_temp_dirs) == 1
        assert not os.path.exists(captured_temp_dirs[0])

    def test_windows_audio_player_registers_atexit_on_open_and_unregisters_on_close(
        self, tmp_path: Path
    ) -> None:
        """Opening a media file registers atexit cleanup and close() unregisters it cleanly."""
        audio_path = tmp_path / "sample.mp3"
        audio_path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 400)

        player = WindowsAudioPlayer()
        with (
            patch.object(player, "_send_command", return_value="1000"),
            patch.object(atexit, "register") as reg_spy,
            patch.object(atexit, "unregister") as unreg_spy,
        ):
            assert player.open(str(audio_path)) is True
            reg_spy.assert_called_once_with(player.close)
            player.close()
            unreg_spy.assert_called_once_with(player.close)


# ==============================================================================
# 2. Desktop Bootstrap (`app.py`) & GUI Event Deduplication Regressions
# ==============================================================================


class TestDesktopAppAndGUIRemediations:
    def test_app_version_and_self_test_flags_exit_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """app.main supports headless --version and --self-test flags for CI smoke gating."""
        assert desktop_app.main(["--version"]) == 0
        out_ver = capsys.readouterr().out
        assert desktop_app.APP_VERSION in out_ver

        assert desktop_app.main(["--self-test"]) == 0
        out_self = capsys.readouterr().out
        assert "self-test OK" in out_self

    def test_app_crash_logger_handles_detached_none_stderr_in_noconsole_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """log_crash writes crash_dump.log inside log dir and survives sys.stderr=None."""
        crash_file = tmp_path / "logs" / "crash_dump.log"
        monkeypatch.setattr(desktop_app, "_resolve_crash_log_path", lambda: str(crash_file))
        monkeypatch.setattr("sys.stderr", None)

        try:
            raise ValueError("Simulated windowed --noconsole exception")
        except ValueError as exc:
            desktop_app.log_crash(type(exc), exc, exc.__traceback__)

        assert crash_file.is_file()
        assert "Simulated windowed --noconsole exception" in crash_file.read_text(encoding="utf-8")

    def test_url_extraction_dual_event_deduplication_helper(self) -> None:
        """_is_duplicate_url_event suppresses paired _event_id payloads while preserving singletons."""
        dummy_window = types.SimpleNamespace()

        dual_payload = {"text": "Extracted article", "_event_id": "evt-101"}
        assert _is_duplicate_url_event(dummy_window, dual_payload) is False
        assert _is_duplicate_url_event(dummy_window, dual_payload) is True

        # Non-dual legacy payloads without _event_id are never suppressed
        legacy_payload = {"text": "Legacy single payload"}
        assert _is_duplicate_url_event(dummy_window, legacy_payload) is False
        assert _is_duplicate_url_event(dummy_window, legacy_payload) is False


# ==============================================================================
# 3. Interactive TUI (`tui/*`) Regressions
# ==============================================================================


class TestTUIRemediations:
    def test_tui_module_arg_parser_supports_cli_bootstrap_options(self) -> None:
        """tui.__main__.build_arg_parser parses --topic, --file, and --model cleanly."""
        parser = build_tui_arg_parser()
        args = parser.parse_args(["--topic", "Local AI Podcasts", "--model", "qwen2.5:7b"])
        assert args.topic == "Local AI Podcasts"
        assert args.model == "qwen2.5:7b"

    def test_audio_player_screen_does_not_loop_on_player_file_loaded_and_handles_dashboard_space(
        self, tmp_path: Path
    ) -> None:
        """PLAYER_FILE_LOADED does not re-open MCI in a loop, and Dashboard Space triggers play/pause."""
        audio_file = tmp_path / "episode.mp3"
        audio_file.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 400)

        mock_player = MagicMock()
        mock_player.open.return_value = True
        mock_player.get_length.return_value = 12000
        mock_player.play.return_value = True
        mock_player.pause.return_value = True

        state = TUIState()
        tui_app = TUIApplication(state=state, auto_probe_ollama=False)
        tui_app.player_screen.player = mock_player

        assert tui_app.player_screen.load_file(str(audio_file)) is True
        assert mock_player.open.call_count == 1

        # Draining PLAYER_FILE_LOADED event must NOT call load_file / player.open again
        tui_app.process_events()
        assert mock_player.open.call_count == 1

        # Dashboard [Space] posts PLAYER_PLAY -> starts playback cleanly
        tui_app.navigate_to(ScreenMode.DASHBOARD)
        tui_app.step(key="space")
        tui_app.process_events()
        assert mock_player.play.call_count == 1
        assert state.player.mode == PlaybackMode.PLAYING

        # Pressing [Space] again on Dashboard posts PLAYER_PAUSE -> pauses playback
        tui_app.step(key="space")
        tui_app.process_events()
        assert mock_player.pause.call_count == 1
        assert state.player.mode == PlaybackMode.PAUSED

    def test_tui_modal_actions_render_and_numeric_hotkey_invokes_callback(self) -> None:
        """Application-level modal renders actions and pressing '1' invokes callback & closes modal."""
        tui_app = TUIApplication(state=TUIState(), auto_probe_ollama=False)
        triggered: list[str] = []

        tui_app.open_modal(
            ModalType.CONFIRMATION,
            {
                "title": "Confirm Action",
                "message": "Proceed with test action?",
                "actions": [
                    {"key": "1", "label": "Confirm Now", "callback": lambda: triggered.append("ok")}
                ],
            },
        )

        console = Console(width=100, height=32, record=True)
        console.print(tui_app.render())
        rendered = console.export_text()
        assert "Confirm Now" in rendered

        tui_app.step(key="1")
        assert triggered == ["ok"]
        assert tui_app.state.ui.active_modal == ModalType.NONE

    def test_script_studio_json_editor_captures_f2_before_global_navigation(self) -> None:
        """Pressing F2 inside ScriptStudioScreen JSON editor saves JSON instead of switching screens."""
        state = TUIState()
        state.generation.turns = [DialogueTurn(speaker="Host 1", text="Initial turn")]
        tui_app = TUIApplication(state=state, auto_probe_ollama=False)
        tui_app.navigate_to(ScreenMode.SCRIPT_STUDIO)

        studio = tui_app.script_studio_screen
        studio.handle_key("e")
        assert studio.is_editing_json is True
        studio.json_editor_prompt.value = '[{"speaker": "Host 2", "text": "Updated via F2 save"}]'

        tui_app.step(key="f2")
        assert tui_app.state.ui.active_screen == ScreenMode.SCRIPT_STUDIO
        assert studio.is_editing_json is False
        assert tui_app.state.generation.turns[0].text == "Updated via F2 save"

    @pytest.mark.parametrize(
        "screen_mode",
        [
            ScreenMode.INGESTION,
            ScreenMode.OLLAMA,
            ScreenMode.CONFIG,
            ScreenMode.GENERATION,
            ScreenMode.SCRIPT_STUDIO,
            ScreenMode.PLAYER,
        ],
    )
    def test_idle_escape_navigates_back_to_dashboard_across_all_subscreens(
        self, screen_mode: ScreenMode
    ) -> None:
        """Pressing Esc when idle on any subscreen returns cleanly to DASHBOARD."""
        tui_app = TUIApplication(state=TUIState(), auto_probe_ollama=False)
        tui_app.navigate_to(screen_mode)
        assert tui_app.state.ui.active_screen == screen_mode

        tui_app.step(key="escape")
        tui_app.process_events()
        assert tui_app.state.ui.active_screen == ScreenMode.DASHBOARD

    def test_terminal_manager_signal_handler_chains_custom_hook_before_restore_clears_map(
        self,
    ) -> None:
        """_handle_signal invokes custom previous handler captured prior to self.restore()."""
        term = TerminalManager()
        called_with: list[int] = []

        def custom_prev_handler(signum: int, _frame: Any) -> None:
            called_with.append(signum)

        term._prev_signal_handlers[signal.SIGINT] = custom_prev_handler
        with (
            patch.object(term, "restore", wraps=term.restore) as restore_spy,
            patch("sys.exit", side_effect=SystemExit(130)),
        ):
            with pytest.raises(SystemExit) as exc_info:
                term._handle_signal(signal.SIGINT, None)

        assert exc_info.value.code == 128 + int(signal.SIGINT)
        restore_spy.assert_called_once()
        assert called_with == [int(signal.SIGINT)]

    def test_untrusted_bracketed_strings_render_across_tui_screens_without_markup_error(
        self,
    ) -> None:
        """Untrusted paths/topics/models containing '[/]' or '[bold' never crash Rich rendering."""
        hostile = "notes_[/]_[bold_unclosed.pdf"
        state = TUIState()
        state.ingestion.source_label = hostile
        state.ingestion.file_path = hostile
        state.ingestion.topic_text = hostile
        state.ollama.selected_model = hostile
        state.ollama.server_url = f"http://localhost:11434/{hostile}"
        state.config.output_dir = hostile
        state.player.current_file = hostile
        state.ui.status_message = hostile

        tui_app = TUIApplication(state=state, auto_probe_ollama=False)
        console = Console(width=110, height=36, record=True)

        for mode in ScreenMode:
            tui_app.navigate_to(mode)
            console.print(tui_app.render())


# ==============================================================================
# 4. Headless CLI (`cli.py`), Packaging & PR Triage Script Regressions
# ==============================================================================


class TestCLIToolingAndPackagingRemediations:
    def test_cli_root_json_flag_is_preserved_across_subcommands(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Root `--json` placed before subcommand is not shadowed by subparser defaults."""
        code = cli.main(["--json", "extract", "--topic", "Quantum Computing Breakthroughs"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert "Quantum Computing Breakthroughs" in payload["text"]

    def test_cli_generate_script_text_flag_treats_value_as_raw_text_in_dry_run(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`generate-script --text ...` treats input as literal raw text rather than a file path."""
        code = cli.main(
            [
                "generate-script",
                "--text",
                "Literal inline paragraph that is definitely not a file on disk.",
                "--dry-run",
                "--json",
            ]
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["dry_run"] is True
        assert payload["command"] == "generate-script"

    def test_cli_synthesize_audio_corrupt_json_emits_structured_json_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Corrupt input JSON file in synthesize-audio returns exit code 1 with valid JSON error."""
        bad_json = tmp_path / "corrupt.json"
        bad_json.write_text("{not valid json", encoding="utf-8")

        code = cli.main(["synthesize-audio", "-i", str(bad_json), "--json"])
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "error" in payload

    def test_cli_stitch_missing_explicit_file_fails_with_exit_code_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`stitch -f` fails loudly when any specified segment path does not exist."""
        existing = tmp_path / "seg1.mp3"
        existing.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 413)
        missing = tmp_path / "missing_seg2.mp3"

        code = cli.main(
            [
                "stitch",
                "-f",
                str(existing),
                str(missing),
                "-o",
                str(tmp_path / "out.mp3"),
                "--json",
            ]
        )
        assert code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "missing_seg2.mp3" in payload["error"]

    def test_check_env_preserves_non_http_scheme_rejection_and_reports_rich_and_local_tts(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """check_env --json rejects ftp:// URLs cleanly and includes rich & local_tts checks."""
        mock_sock = MagicMock()
        with patch("socket.create_connection", return_value=mock_sock):
            code = check_env.main(["--json", "-u", "ftp://localhost:11434"])

        assert code == 1
        report = json.loads(capsys.readouterr().out)
        assert report["checks"]["ollama_service"]["ok"] is False
        assert "Invalid Ollama URL" in report["checks"]["ollama_service"]["detail"]
        assert "rich" in report["checks"]["runtime_dependencies"]["installed"]
        assert report["checks"]["local_tts"]["ok"] is True

    def test_pyinstaller_spec_compiles_without_creating_cwd_build_or_dist_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Compiling LocalPodcastLLMStudio.spec has zero CWD directory creation side effects."""
        repo_root = Path(__file__).resolve().parent.parent
        spec_path = repo_root / "LocalPodcastLLMStudio.spec"
        spec_source = spec_path.read_text(encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        compiled = compile(spec_source, str(spec_path), "exec")
        assert compiled is not None
        assert "os.makedirs" not in spec_source
        assert not (tmp_path / "build").exists()
        assert not (tmp_path / "dist").exists()

    def test_bulk_close_superseded_prs_strictly_filters_range_author_and_exclusions(
        self,
    ) -> None:
        """PR triage filter never targets human PRs, out-of-range PRs, or excluded PRs."""
        sample_prs = [
            {
                "number": 75,
                "title": "Older PR below min",
                "author": {"login": "app/google-labs-jules", "is_bot": True},
            },
            {
                "number": 100,
                "title": "Valid Jules PR",
                "author": {"login": "google-labs-jules", "is_bot": True},
            },
            {
                "number": 150,
                "title": "Human contributor PR",
                "author": {"login": "tordieltor", "is_bot": False},
            },
            {
                "number": 180,
                "title": "Explicitly excluded Jules PR",
                "author": {"login": "app/google-labs-jules", "is_bot": True},
            },
            {
                "number": 213,
                "title": "Newer PR above max",
                "author": {"login": "app/google-labs-jules", "is_bot": True},
            },
        ]

        matched, skipped = pr_triage.filter_target_prs(
            sample_prs,
            min_pr=76,
            max_pr=212,
            allowed_authors=set(pr_triage.DEFAULT_JULES_AUTHORS),
            excluded_prs={180},
        )
        assert [pr["number"] for pr in matched] == [100]
        assert {num for num, _ in skipped} == {75, 150, 180, 213}
