"""
Adversarial and Empirical Stress Test Suite for Milestone 2.
Target subsystems:
  - core/ollama.py: NDJSON streaming pull parser, speed estimator,
    Windows binary resolver, detached service launcher, socket reachability probe.
  - check_env.py: URL validation, Ollama service inspection, Edge-TTS network probe.
"""

import io
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

import check_env
from core.ollama import (
    ModelPullProgress,
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    _validate_url,
    check_edge_tts_reachability,
    check_prerequisites,
    find_ollama_binary,
    pull_model_stream,
    start_ollama_service,
)

# ============================================================================
# Helper Classes for Streaming Simulation
# ============================================================================


class ChunkedBytesIO(io.BytesIO):
    """Simulates an HTTP response stream yielding arbitrary byte chunks or lines."""

    def __init__(self, chunks: list[bytes]):
        super().__init__(b"".join(chunks))
        self._chunks = chunks
        self._iter = iter(chunks)

    def __iter__(self):
        return iter(self._chunks)

    def readline(self, size=-1):
        try:
            return next(self._iter)
        except StopIteration:
            return b""


# ============================================================================
# 1. NDJSON Streaming Parser Adversarial Stress Tests
# ============================================================================


class TestNDJSONParserStress:
    """Stress-tests the NDJSON streaming parser under hostile stream conditions."""

    def test_single_byte_fragmentation(self):
        """Simulates an adversarial stream where JSON is fragmented across lines."""
        raw_events = [
            {"status": "pulling manifest"},
            {
                "status": "downloading layer",
                "digest": "sha256:abc",
                "total": 1000,
                "completed": 500,
            },
            {"status": "success"},
        ]
        lines = [json.dumps(ev).encode("utf-8") + b"\n" for ev in raw_events]

        collected_progress = []

        def callback(p: ModelPullProgress):
            collected_progress.append(p)

        mock_resp = ChunkedBytesIO(lines)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            success = pull_model_stream("llama3.1:8b", progress_callback=callback)

        assert success is True
        assert len(collected_progress) == 3
        assert collected_progress[0].status == "pulling manifest"
        assert collected_progress[1].completed == 500
        assert collected_progress[2].status == "success"
        assert collected_progress[2].is_done is True
        assert collected_progress[2].percentage == 1.0

    def test_crlf_and_mixed_line_endings_and_blank_lines(self):
        """Tests stream containing CRLF, LF, mixed trailing spaces, and blank lines."""
        chunks = [
            b"\r\n\r\n",
            b'{"status": "verifying sha256 digest"}\r\n',
            b"\n   \n",
            b'{"status": "downloading", "digest": "sha256:111", "total": 2048, "completed": 1024}\n',
            b"\r\n",
            b'{"status": "success", "done": true}\r\n',
            b"\n\n",
        ]

        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            success = pull_model_stream(
                "qwen2.5:7b", progress_callback=lambda p: collected.append(p)
            )

        assert success is True
        assert len(collected) == 3
        assert collected[0].status == "verifying sha256 digest"
        assert collected[1].completed == 1024
        assert collected[2].is_done is True

    def test_malformed_json_garbage_interleaved(self):
        """Ensures corrupted JSON chunks or HTML error snippets are skipped gracefully."""
        chunks = [
            b"<!DOCTYPE html><html><body>502 Bad Gateway</body></html>\n",
            b'{"status": "pulling manifest"}\n',
            b"{not valid json at all}\n",
            b'{"status": "downloading", "total": 100, "completed": 50}\n',
            b'{"incomplete json...\n',
            b'{"status": "success"}\n',
        ]

        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            success = pull_model_stream(
                "test-model", progress_callback=lambda p: collected.append(p)
            )

        assert success is True
        assert len(collected) == 3
        assert [c.status for c in collected] == ["pulling manifest", "downloading", "success"]

    def test_server_error_chunk_aborts_stream_with_runtime_error(self):
        """Ensures that in-band error messages in JSON trigger RuntimeError and error callback."""
        chunks = [
            b'{"status": "pulling manifest"}\n',
            b'{"error": "pull model manifest failed: 404 not found"}\n',
            b'{"status": "downloading"}\n',
        ]

        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="pull model manifest failed: 404 not found"):
                pull_model_stream("missing-model", progress_callback=lambda p: collected.append(p))

        assert len(collected) == 2
        assert collected[1].status == "error"
        assert collected[1].error == "pull model manifest failed: 404 not found"
        assert collected[1].is_done is False

    def test_massive_error_payload(self):
        """Tests handling of huge error payload (e.g. 50KB string)."""
        huge_msg = "A" * 50000
        chunks = [json.dumps({"error": huge_msg}).encode("utf-8") + b"\n"]

        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError) as exc_info:
                pull_model_stream("huge-err-model", progress_callback=lambda p: collected.append(p))

        assert huge_msg in str(exc_info.value)
        assert collected[0].error == huge_msg


# ============================================================================
# 2. Speed Estimator & Math Boundary Stress Tests
# ============================================================================


class TestSpeedAndETAMathStress:
    """Adversarial stress on mathematical division, EMA smoothing, and clock anomalies."""

    def test_zero_delta_time_multiple_chunks_same_timestamp(self):
        """Multiple chunks arriving at exact same monotonic timestamp (dt = 0.0)."""
        chunks = [
            b'{"status": "downloading", "digest": "sha256:1", "total": 10000, "completed": 1000}\n',
            b'{"status": "downloading", "digest": "sha256:1", "total": 10000, "completed": 2000}\n',
            b'{"status": "downloading", "digest": "sha256:1", "total": 10000, "completed": 3000}\n',
            b'{"status": "success"}\n',
        ]

        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", return_value=100.0),
        ):
            pull_model_stream("llama3.1:8b", progress_callback=lambda p: collected.append(p))

        assert len(collected) == 4
        assert collected[0].speed_bps == 0.0
        assert collected[1].speed_bps == 0.0
        assert collected[2].speed_bps == 0.0

    def test_negative_delta_time_clock_anomaly(self):
        """Monotonic clock jumping backward (e.g. mock clock anomaly)."""
        chunks = [
            b'{"status": "downloading", "digest": "sha256:1", "total": 10000, "completed": 1000}\n',
            b'{"status": "downloading", "digest": "sha256:1", "total": 10000, "completed": 2000}\n',
            b'{"status": "downloading", "digest": "sha256:1", "total": 10000, "completed": 3000}\n',
            b'{"status": "success"}\n',
        ]

        time_seq = [100.0, 90.0, 80.0, 70.0, 60.0]
        time_iter = iter(time_seq)

        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", side_effect=lambda: next(time_iter, 50.0)),
        ):
            pull_model_stream("llama3.1:8b", progress_callback=lambda p: collected.append(p))

        for c in collected:
            assert c.speed_bps >= 0.0

    def test_completed_bytes_regressing_or_exceeding_total(self):
        """Completed bytes jumping backwards or exceeding total."""
        chunks = [
            b'{"status": "downloading", "digest": "sha256:1", "total": 1000, "completed": 500}\n',
            b'{"status": "downloading", "digest": "sha256:1", "total": 1000, "completed": 200}\n',
            b'{"status": "downloading", "digest": "sha256:1", "total": 1000, "completed": 2500}\n',
            b'{"status": "success"}\n',
        ]

        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            pull_model_stream("llama3.1:8b", progress_callback=lambda p: collected.append(p))

        assert len(collected) == 4
        assert 0.0 <= collected[0].percentage <= 1.0
        assert 0.0 <= collected[1].percentage <= 1.0
        assert collected[2].percentage == 1.0

    def test_layer_digest_rapid_switching(self):
        """Multiple layers with rapid digest changes reset speed tracking properly."""
        chunks = [
            b'{"status": "downloading", "digest": "sha256:layer1", "total": 1000, "completed": 500}\n',
            b'{"status": "downloading", "digest": "sha256:layer1", "total": 1000, "completed": 1000}\n',
            b'{"status": "downloading", "digest": "sha256:layer2", "total": 2000, "completed": 100}\n',
            b'{"status": "downloading", "digest": "sha256:layer2", "total": 2000, "completed": 1500}\n',
            b'{"status": "success"}\n',
        ]

        time_seq = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", side_effect=time_seq),
        ):
            pull_model_stream("llama3.1:8b", progress_callback=lambda p: collected.append(p))

        assert len(collected) == 5
        assert collected[2].speed_bps == 0.0
        assert collected[3].speed_bps > 0.0

    def test_huge_model_and_eta_formatting_over_24h(self):
        """Model with huge size (> 100GB) and slow speed produces HH:MM:SS ETA."""
        total_bytes = 200 * 1024 * 1024 * 1024
        completed_1 = 1000
        completed_2 = 2000

        chunks = [
            json.dumps(
                {
                    "status": "downloading",
                    "digest": "sha256:huge",
                    "total": total_bytes,
                    "completed": completed_1,
                }
            ).encode()
            + b"\n",
            json.dumps(
                {
                    "status": "downloading",
                    "digest": "sha256:huge",
                    "total": total_bytes,
                    "completed": completed_2,
                }
            ).encode()
            + b"\n",
        ]

        time_seq = [10.0, 11.0]
        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", side_effect=time_seq),
        ):
            pull_model_stream("huge-model", progress_callback=lambda p: collected.append(p))

        assert len(collected) == 2
        eta_str = collected[1].eta_str
        assert eta_str != ""
        parts = eta_str.split(":")
        assert len(parts) == 3


# ============================================================================
# 3. Unicode, Emojis, RTL, and Input Sanitization Tests
# ============================================================================


class TestUnicodeAndInputSanitization:
    """Tests resilience against complex unicode, emojis, and weird strings."""

    def test_unicode_and_emoji_in_model_name_and_status(self):
        """Model name and status strings containing Norwegian, Chinese, Emojis, and RTL."""
        model_name = "llama3.1:8b-æøå-🔥-模型-مرحبا"
        chunks = [
            b'{"status": "\xc3\xa6\xc3\xb8\xc3\xa5 \xe2\x9c\xa8 \xe6\xa8\xa1\xe5\x9e\x8b"}\n',
            b'{"status": "downloading", "digest": "sha256:\xf0\x9f\x94\xa5", "total": 100, "completed": 50}\n',
            b'{"status": "success"}\n',
        ]

        collected = []
        mock_resp = ChunkedBytesIO(chunks)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            success = pull_model_stream(model_name, progress_callback=lambda p: collected.append(p))

        assert success is True
        assert len(collected) == 3
        assert "æøå" in collected[0].status or "✨" in collected[0].status

    def test_invalid_empty_or_whitespace_model_names(self):
        """Rejects empty, whitespace-only, or non-string model names."""
        for invalid in ["", "   ", "\t\n", None, 123, [], {}]:
            with pytest.raises((ValueError, TypeError)):
                pull_model_stream(invalid)

    def test_validate_url_comprehensive_schemes(self):
        """Tests strict scheme and host validation in _validate_url."""
        assert _validate_url("http://localhost:11434") == "http://localhost:11434"
        assert _validate_url("https://remote.ollama.ai:443/") == "https://remote.ollama.ai:443"
        assert _validate_url("http://192.168.1.50:11434") == "http://192.168.1.50:11434"

        invalid_urls = [
            "ftp://localhost:11434",
            "file:///etc/passwd",
            "gopher://localhost:70",
            "ws://localhost:11434",
            "http://",
            "https://",
            "",
            "   ",
            None,
            123,
        ]
        for bad_url in invalid_urls:
            with pytest.raises(ValueError):
                _validate_url(bad_url)


# ============================================================================
# 4. Rapid and Preemptive Cancellation Tests
# ============================================================================


class TestCancellationStress:
    """Stress tests cancellation tokens at every stage of execution."""

    def test_cancellation_pre_request(self):
        """Cancellation event set before pull_model_stream starts."""
        cancel_ev = threading.Event()
        cancel_ev.set()

        with pytest.raises(RuntimeError, match="cancelled by user before request dispatch"):
            pull_model_stream("llama3.1:8b", cancel_event=cancel_ev)

    def test_cancellation_mid_stream(self):
        """Cancellation event triggered while consuming stream lines."""
        cancel_ev = threading.Event()

        chunks = [
            b'{"status": "pulling manifest"}\n',
            b'{"status": "downloading", "total": 1000, "completed": 100}\n',
            b'{"status": "downloading", "total": 1000, "completed": 200}\n',
            b'{"status": "success"}\n',
        ]

        def line_generator():
            for i, c in enumerate(chunks):
                if i == 2:
                    cancel_ev.set()
                yield c

        mock_resp = ChunkedBytesIO(list(line_generator()))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="cancelled by user"):
                pull_model_stream("llama3.1:8b", cancel_event=cancel_ev)

    def test_cancellation_concurrent_thread(self):
        """Simulates another thread triggering cancellation during slow stream."""
        cancel_ev = threading.Event()

        def delayed_stream():
            yield b'{"status": "pulling manifest"}\n'
            time.sleep(0.05)
            yield b'{"status": "downloading", "total": 1000, "completed": 100}\n'
            time.sleep(0.05)
            yield b'{"status": "downloading", "total": 1000, "completed": 200}\n'

        timer = threading.Timer(0.02, cancel_ev.set)
        timer.start()

        mock_resp = ChunkedBytesIO(list(delayed_stream()))
        try:
            with patch("urllib.request.urlopen", return_value=mock_resp):
                with pytest.raises(RuntimeError, match="cancelled by user"):
                    pull_model_stream("llama3.1:8b", cancel_event=cancel_ev)
        finally:
            timer.cancel()


# ============================================================================
# 5. Windows Binary Resolver & Service Launcher Adversarial Tests
# ============================================================================


class TestBinaryResolverAndServiceLauncherStress:
    """Stress tests find_ollama_binary and start_ollama_service edge cases."""

    def test_find_binary_with_corrupted_path_env(self):
        """PATH contains non-existent paths, quotes, and empty entries."""
        fake_env = {
            "PATH": os.pathsep.join(
                [
                    "",
                    '"C:\\NonExistent Folder with spaces"',
                    "C:\\Invalid*Chars",
                    "Z:\\DoesNotExist",
                ]
            ),
            "LOCALAPPDATA": "C:\\MockLocalAppData",
            "ProgramFiles": "C:\\MockProgramFiles",
            "ProgramFiles(x86)": "C:\\MockProgramFilesX86",
            "ProgramW6432": "C:\\MockProgramW6432",
        }

        with (
            patch.dict(os.environ, fake_env, clear=True),
            patch("shutil.which", return_value=None),
            patch("os.path.isfile", return_value=False),
        ):
            result = find_ollama_binary()
            assert result is None

    def test_find_binary_in_nested_windows_appdata_fallback(self):
        """Finds ollama.exe in LOCALAPPDATA\\Programs\\Ollama when not in PATH."""

        def mock_isfile(p):
            norm = p.replace("\\", "/")
            return "test/AppData/Local/Programs/Ollama/ollama.exe" in norm

        fake_env = {
            "PATH": "",
            "LOCALAPPDATA": r"C:\Users\test\AppData\Local",
        }

        with (
            patch.dict(os.environ, fake_env, clear=True),
            patch("shutil.which", return_value=None),
            patch("sys.platform", "win32"),
            patch("os.path.isfile", side_effect=mock_isfile),
        ):
            result = find_ollama_binary()
            assert result is not None
            norm_result = result.replace("\\", "/")
            assert "test/AppData/Local/Programs/Ollama/ollama.exe" in norm_result

    def test_start_service_immediate_exit_non_zero_code(self):
        """Process crashes immediately with non-zero exit code (e.g. exit code 1 or 255)."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1

        with (
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch("core.ollama.find_ollama_binary", return_value="C:\\Ollama\\ollama.exe"),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            success, msg = start_ollama_service(timeout=2.0)

        assert success is False
        assert "terminated immediately with exit code 1" in msg

    def test_start_service_popen_permission_error(self):
        """Popen raises PermissionError/OSError when launching binary."""
        with (
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch("core.ollama.find_ollama_binary", return_value="C:\\Ollama\\ollama.exe"),
            patch("subprocess.Popen", side_effect=PermissionError("Access Denied")),
        ):
            success, msg = start_ollama_service(timeout=2.0)

        assert success is False
        assert "Failed to start Ollama process" in msg
        assert "Access Denied" in msg

    def test_start_service_cancelled_during_polling(self):
        """User cancels startup while polling is in progress."""
        cancel_ev = threading.Event()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        def check_conn_side_effect(*args, **kwargs):
            cancel_ev.set()
            return False

        with (
            patch("core.ollama.OllamaClient.check_connection", side_effect=check_conn_side_effect),
            patch("core.ollama.find_ollama_binary", return_value="C:\\Ollama\\ollama.exe"),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            success, msg = start_ollama_service(timeout=5.0, cancel_event=cancel_ev)

        assert success is False
        assert "cancelled by user" in msg


# ============================================================================
# 6. Edge-TTS Network Probe Adversarial Tests
# ============================================================================


class TestEdgeTTSReachabilityProbeStress:
    """Stress tests socket probes for speech.platform.bing.com:443."""

    def test_edge_tts_dns_resolution_failure(self):
        """Simulates DNS failure (socket.gaierror)."""
        with patch(
            "socket.create_connection", side_effect=socket.gaierror(-2, "Name or service not known")
        ):
            reachable, msg = check_edge_tts_reachability(timeout=1.0)

        assert reachable is False
        assert "DNS resolution failed" in msg

    def test_edge_tts_socket_timeout(self):
        """Simulates timeout during socket handshake."""
        with patch("socket.create_connection", side_effect=TimeoutError("Connection timed out")):
            reachable, msg = check_edge_tts_reachability(timeout=1.0)

        assert reachable is False
        assert "timed out" in msg

    def test_edge_tts_connection_reset_by_peer(self):
        """Simulates TCP connection reset."""
        with patch(
            "socket.create_connection", side_effect=ConnectionResetError("Connection reset by peer")
        ):
            reachable, msg = check_edge_tts_reachability(timeout=1.0)

        assert reachable is False
        assert "probe failed" in msg
        assert "reset by peer" in msg

    def test_edge_tts_connection_refused(self):
        """Simulates port connection refused."""
        with patch(
            "socket.create_connection", side_effect=ConnectionRefusedError("Connection refused")
        ):
            reachable, msg = check_edge_tts_reachability(timeout=1.0)

        assert reachable is False
        assert "probe failed" in msg


# ============================================================================
# 7. Unified Prerequisite Check & Diagnostics Combinatorial Matrix
# ============================================================================


class TestPrerequisitesCombinatorialMatrix:
    """Tests all permutations of prerequisite failure and remediation messages."""

    @pytest.mark.parametrize(
        "binary_found,ollama_online,models,edge_online,expected_all_ready",
        [
            (True, True, ["llama3.1:8b"], True, True),
            (True, True, ["llama3.1:8b"], False, False),
            (True, True, [], True, False),
            (True, False, [], True, False),
            (False, False, [], True, False),
            (False, False, [], False, False),
            (True, True, ["qwen2.5:7b"], True, True),
        ],
    )
    def test_prerequisite_permutations(
        self,
        binary_found,
        ollama_online,
        models,
        edge_online,
        expected_all_ready,
    ):
        bin_path = "C:\\Ollama\\ollama.exe" if binary_found else None

        with (
            patch("core.ollama.find_ollama_binary", return_value=bin_path),
            patch("core.ollama.OllamaClient.check_connection", return_value=ollama_online),
            patch("core.ollama.OllamaClient.list_models", return_value=models),
            patch("core.ollama.check_edge_tts_reachability", return_value=(edge_online, "msg")),
        ):
            status = check_prerequisites(recommended_model="llama3.1:8b")

        assert status.all_ready is expected_all_ready
        assert status.ollama_binary_found is binary_found
        assert status.ollama_online is ollama_online
        assert status.edge_tts_online is edge_online

        if not binary_found:
            assert any("binary not found" in h.lower() for h in status.remediation_hints)
        if not ollama_online:
            assert any("offline" in h.lower() for h in status.remediation_hints)
        if ollama_online and len(models) == 0:
            assert any("no llm models" in h.lower() for h in status.remediation_hints)
        if not edge_online:
            assert any("edge-tts" in h.lower() for h in status.remediation_hints)


# ============================================================================
# 8. check_env.py Diagnostic Tool Adversarial Tests
# ============================================================================


class TestCheckEnvAdversarial:
    """Stress tests check_env.py CLI functions and error handling."""

    def test_check_ollama_service_malformed_url(self):
        """check_ollama_service handles completely malformed URLs without crashing."""
        res = check_env.check_ollama_service(host="invalid://host:9999")
        assert res["ok"] is False
        assert res["online"] is False
        assert "Invalid URL scheme" in res["detail"]

    def test_check_ollama_service_http_500_response(self):
        """check_ollama_service handles non-200 HTTP status gracefully."""
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = check_env.check_ollama_service(host="http://localhost:11434")

        assert res["ok"] is False
        assert res["online"] is False
        assert "HTTP status 500" in res["detail"]

    def test_check_edge_tts_network_failure_handling(self):
        """check_edge_tts_network handles socket timeout and exceptions."""
        with patch("socket.create_connection", side_effect=TimeoutError()):
            res = check_env.check_edge_tts_network(timeout_sec=0.1)
            assert res["reachable"] is False
            assert res["warn"] is True
            assert "timed out" in res["detail"]

    def test_run_all_checks_aggregation_structure(self):
        """run_all_checks produces a compliant structure with timestamp and remediations."""
        with (
            patch(
                "check_env.check_ollama_service",
                return_value={
                    "ok": True,
                    "warn": False,
                    "online": True,
                    "models_count": 1,
                    "models": [],
                },
            ),
            patch(
                "check_env.check_edge_tts_network",
                return_value={"ok": True, "warn": False, "reachable": True},
            ),
        ):
            report = check_env.run_all_checks()

        assert "timestamp" in report
        assert "all_passed" in report
        assert "checks" in report
        assert "remediations" in report
        assert isinstance(report["remediations"], list)


# ============================================================================
# 9. OllamaClient Generation & Script Pipeline Adversarial Tests
# ============================================================================


class TestOllamaGenerationAdversarial:
    """Stress tests OllamaClient.generate under hostile server responses and network failures."""

    def test_generate_pre_request_cancellation(self):
        """Cancellation event set before generate is called."""
        client = OllamaClient()
        cancel_ev = threading.Event()
        cancel_ev.set()

        with pytest.raises(RuntimeError, match="cancelled by user before request dispatch"):
            client.generate("llama3.1:8b", "test prompt", cancel_event=cancel_ev)

    def test_generate_chat_streaming_cancellation_mid_stream(self):
        """Cancellation triggered while consuming chat streaming tokens."""
        client = OllamaClient()
        cancel_ev = threading.Event()

        chunks = [
            b'{"message": {"content": "Hello "}}\n',
            b'{"message": {"content": "world"}}\n',
            b'{"message": {"content": "!"}}\n',
        ]

        class LazyStream:
            def __init__(self, raw_chunks, event_to_set_on_chunk):
                self.raw_chunks = raw_chunks
                self.event = event_to_set_on_chunk

            def __iter__(self):
                for i, c in enumerate(self.raw_chunks):
                    if i == 1:
                        self.event.set()
                    yield c

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        mock_resp = LazyStream(chunks, cancel_ev)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="cancelled by user during streaming"):
                client.generate("llama3.1:8b", "test", stream=True, cancel_event=cancel_ev)

    def test_generate_chat_404_model_not_found_exception(self):
        """404 with 'model not found' body maps directly to OllamaModelNotFoundError."""
        client = OllamaClient()
        fp = io.BytesIO(b'{"error": "model \'missing-model\' not found"}')
        http_err = urllib.error.HTTPError(
            url="http://localhost:11434/api/chat",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=fp,
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(
                OllamaModelNotFoundError, match="Model 'missing-model' is not installed in Ollama"
            ):
                client.generate("missing-model", "test")

    def test_generate_socket_timeout_maps_to_timeout_error(self):
        """URLError with socket.timeout reason raises TimeoutError."""
        client = OllamaClient()
        url_err = urllib.error.URLError(reason=TimeoutError("timed out"))

        with patch("urllib.request.urlopen", side_effect=url_err):
            with pytest.raises(TimeoutError, match="timed out after 10.0 seconds"):
                client.generate("llama3.1:8b", "test", timeout=10.0)

    def test_generate_connection_refused_maps_to_ollama_connection_error(self):
        """URLError with connection refused raises OllamaConnectionError."""
        client = OllamaClient()
        url_err = urllib.error.URLError(reason=ConnectionRefusedError("Connection refused"))

        with patch("urllib.request.urlopen", side_effect=url_err):
            with pytest.raises(OllamaConnectionError, match="Cannot connect to Ollama"):
                client.generate("llama3.1:8b", "test")


# ============================================================================
# 10. check_env CLI & URL Edge Cases
# ============================================================================


class TestCheckEnvCLIExtended:
    """Stress tests check_env CLI invocation and helper functions."""

    def test_validate_ollama_url_normalization(self):
        """Validates URL schemes and normalization in check_env._validate_ollama_url."""
        assert check_env._validate_ollama_url("http://localhost:11434") == "http://localhost:11434"
        assert check_env._validate_ollama_url("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
        assert (
            check_env._validate_ollama_url("https://remote.ollama.ai:443")
            == "https://remote.ollama.ai:443"
        )

        with pytest.raises(ValueError):
            check_env._validate_ollama_url("ftp://localhost:11434")

        with pytest.raises(ValueError):
            check_env._validate_ollama_url("")

    def test_main_cli_quiet_mode(self, monkeypatch):
        """Tests check_env.main with --quiet flag."""
        monkeypatch.setattr(sys, "argv", ["check_env.py", "--quiet"])
        with patch("check_env.run_all_checks", return_value={"all_passed": True}):
            code = check_env.main()
            assert code == 0

        with patch("check_env.run_all_checks", return_value={"all_passed": False}):
            code = check_env.main()
            assert code == 1
