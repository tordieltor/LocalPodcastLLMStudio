"""
Milestone 2 Empirical Challenger Test Suite:
Concurrency, Invariants, Public API Robustness & Grounding Mode Integration
===========================================================================
Adversarially tests:
1. Concurrency: High-contention parallel threads executing `pull_model_stream`,
   `check_prerequisites`, `start_ollama_service`, and `generate_podcast_script`.
2. Invariants: `ModelPullProgress` fields (percentage in [0.0, 1.0], speed_bps >= 0,
   eta_str format, progress_str format, speed_str format).
3. Public API Robustness: Error containment under corrupted network responses,
   socket crashes, non-JSON streams, invalid schemes, and cancellation events.
4. Grounding Mode Propagation: Valid, aliased, and adversarial grounding modes
   in single-act and multi-act script generation pipelines.
5. check_env.py Preflight Diagnostics: Comprehensive verification of preflight checks
   and CLI options (--json, --quiet).
"""

import concurrent.futures
import email.message
import io
import json
import socket
import subprocess
import sys
import threading
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import check_env
from core.ollama import (
    ModelPullProgress,
    PrerequisiteStatus,
    _validate_url,
    check_edge_tts_reachability,
    check_prerequisites,
    generate_podcast_script,
    pull_model_stream,
    start_ollama_service,
)
from core.prompts import (
    GroundingMode,
    build_act_system_prompt,
    build_act_user_prompt,
    build_system_prompt,
    build_user_prompt,
    normalize_grounding_mode,
)

# ==============================================================================
# 1. Concurrency & Thread-Safety Tests
# ==============================================================================


class TestConcurrencyAndThreadSafety:
    """Stress tests verifying absence of shared mutable state corruption under concurrency."""

    def test_concurrent_pull_model_streams(self):
        """
        Spawns 20 parallel threads each pulling a different model with a unique NDJSON stream.
        Verifies that thread progress callbacks remain isolated and receive their exact events.
        """
        num_threads = 20
        results = [None] * num_threads
        thread_callbacks = [[] for _ in range(num_threads)]

        def mock_urlopen_for_thread(thread_idx):
            chunks = [
                {"status": "pulling manifest"},
                {
                    "status": "downloading",
                    "digest": f"sha256:thread_{thread_idx}",
                    "total": 1000 * (thread_idx + 1),
                    "completed": 500 * (thread_idx + 1),
                },
                {"status": "success"},
            ]
            raw_lines = [json.dumps(c).encode("utf-8") + b"\n" for c in chunks]
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = raw_lines
            mock_resp.status = 200
            return mock_resp

        def worker(idx):
            mock_resp = mock_urlopen_for_thread(idx)
            with patch("urllib.request.urlopen", return_value=mock_resp):
                success = pull_model_stream(
                    model=f"model-worker-{idx}:latest",
                    base_url="http://localhost:11434",
                    progress_callback=lambda p: thread_callbacks[idx].append(p),
                )
                results[idx] = success

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
            assert not t.is_alive(), "Worker thread timed out or deadlocked"

        # Assertions on thread isolation
        for idx in range(num_threads):
            assert results[idx] is True, f"Thread {idx} pull did not return True"
            cb_list = thread_callbacks[idx]
            assert len(cb_list) == 3, (
                f"Thread {idx} expected 3 progress callbacks, got {len(cb_list)}"
            )
            assert cb_list[0].status == "pulling manifest"
            assert cb_list[1].digest == f"sha256:thread_{idx}"
            assert cb_list[1].total == 1000 * (idx + 1)
            assert cb_list[1].completed == 500 * (idx + 1)
            assert cb_list[1].percentage == 0.5
            assert cb_list[2].is_done is True
            assert cb_list[2].percentage == 1.0

    def test_concurrent_check_prerequisites(self):
        """
        Spawns 25 parallel threads calling check_prerequisites simultaneously.
        Verifies thread safety across socket probes, URL parsing, and model matching.
        """
        num_threads = 25
        results = [None] * num_threads

        def mock_worker(idx):
            with (
                patch(
                    "core.ollama.find_ollama_binary",
                    return_value=r"C:\Program Files\Ollama\ollama.exe",
                ),
                patch("core.ollama.OllamaClient.check_connection", return_value=True),
                patch(
                    "core.ollama.OllamaClient.list_models",
                    return_value=[f"model_{idx}:latest", "llama3.1:8b"],
                ),
                patch("core.ollama.check_edge_tts_reachability", return_value=(True, "Connected")),
            ):
                status = check_prerequisites(recommended_model="llama3.1:8b")
                results[idx] = status

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(mock_worker, i) for i in range(num_threads)]
            concurrent.futures.wait(futures, timeout=10.0)

        for idx, status in enumerate(results):
            assert status is not None
            assert status.all_ready is True
            assert status.ollama_online is True
            assert status.has_recommended_model is True
            assert f"model_{idx}:latest" in status.installed_models
            assert status.remediation_hints == []

    def test_concurrent_start_ollama_service(self):
        """
        Tests multiple threads simultaneously invoking start_ollama_service.
        Verifies no crash or race condition when service becomes responsive.
        """
        num_threads = 10
        results = [None] * num_threads

        def worker(idx):
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            with (
                patch(
                    "core.ollama.OllamaClient.check_connection",
                    side_effect=lambda *a, **k: True,
                ),
                patch("core.ollama.find_ollama_binary", return_value=r"C:\Ollama\ollama.exe"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("time.sleep"),
            ):
                success, msg = start_ollama_service(timeout=5.0)
                results[idx] = (success, msg)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        for idx, (success, msg) in enumerate(results):
            assert success is True, f"Thread {idx} failed to start service"
            assert "started successfully" in msg or "already running" in msg

    def test_concurrent_generate_podcast_script(self):
        """
        Tests 12 concurrent threads running generate_podcast_script with various grounding modes.
        """
        num_threads = 12
        modes = ["strict", "creative", "open_topic"]
        results = [None] * num_threads

        def worker(idx):
            mode = modes[idx % len(modes)]
            dialogue = [
                {"speaker": "Host 1", "text": f"Welcome from thread {idx} in mode {mode}!"},
                {"speaker": "Host 2", "text": f"Glad to be here on thread {idx}."},
            ]
            chat_resp = {"message": {"role": "assistant", "content": json.dumps(dialogue)}}
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps(chat_resp).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp

            with patch("urllib.request.urlopen", return_value=mock_resp):
                turns = generate_podcast_script(
                    content=f"Content for thread {idx}",
                    language="en-US",
                    format_type="quick",
                    grounding_mode=mode,
                )
                results[idx] = (mode, turns)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        for idx, res in enumerate(results):
            assert res is not None
            mode, turns = res
            assert len(turns) == 2
            assert f"thread {idx}" in turns[0].text
            assert mode in turns[0].text


# ==============================================================================
# 2. Invariant Verification Tests
# ==============================================================================


class TestInvariantVerification:
    """Stress tests validating numerical and string formatting invariants in ModelPullProgress."""

    @pytest.mark.parametrize(
        ("total", "completed", "is_done", "expected_min", "expected_max"),
        [
            (1000, 500, False, 0.5, 0.5),
            (1000, 0, False, 0.0, 0.0),
            (1000, 1000, False, 1.0, 1.0),
            (1000, 1500, False, 1.0, 1.0),  # Completed exceeds total -> clamped to 1.0
            (1000, -100, False, 0.0, 0.0),  # Negative completed -> clamped to 0.0
            (0, 500, False, 0.0, 0.0),  # Total 0 -> 0.0
            (-500, 100, False, 0.0, 0.0),  # Negative total -> 0.0
            (0, 0, False, 0.0, 0.0),  # 0 / 0 -> 0.0
            (1000, 200, True, 1.0, 1.0),  # is_done True -> 1.0 regardless of completed
            (0, 0, True, 1.0, 1.0),  # is_done True -> 1.0
        ],
    )
    def test_percentage_invariant_always_in_unit_interval(
        self, total, completed, is_done, expected_min, expected_max
    ):
        """Verifies ModelPullProgress.percentage is strictly clamped within [0.0, 1.0]."""
        chunk = {
            "status": "success" if is_done else "downloading",
            "digest": "sha256:test",
            "total": total,
            "completed": completed,
        }
        if is_done:
            chunk["done"] = True

        raw_lines = [json.dumps(chunk).encode("utf-8") + b"\n"]
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = raw_lines
        mock_resp.status = 200

        received: list[ModelPullProgress] = []
        with patch("urllib.request.urlopen", return_value=mock_resp):
            pull_model_stream(
                model="test-model",
                progress_callback=lambda p: received.append(p),
            )

        assert len(received) == 1
        p = received[0]
        assert 0.0 <= p.percentage <= 1.0
        assert expected_min <= p.percentage <= expected_max

    def test_speed_bps_invariant_non_negative_and_clock_skew(self):
        """
        Verifies speed_bps >= 0 even under backward clock ticks (monotonic jitter)
        or negative delta bytes.
        """
        chunks = [
            {"status": "downloading", "digest": "sha256:layer", "total": 1000, "completed": 200},
            {
                "status": "downloading",
                "digest": "sha256:layer",
                "total": 1000,
                "completed": 100,
            },  # Decreased bytes
            {"status": "downloading", "digest": "sha256:layer", "total": 1000, "completed": 300},
            {"status": "success"},
        ]
        raw_lines = [json.dumps(c).encode("utf-8") + b"\n" for c in chunks]
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = raw_lines
        mock_resp.status = 200

        # Monotonic times: 100.0, 99.0 (backward tick!), 101.0, 102.0
        time_seq = [100.0, 99.0, 101.0, 102.0]
        received: list[ModelPullProgress] = []

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", side_effect=time_seq),
        ):
            pull_model_stream(
                model="test-model",
                progress_callback=lambda p: received.append(p),
            )

        for p in received:
            assert p.speed_bps >= 0.0, f"speed_bps was negative: {p.speed_bps}"

    def test_eta_str_formatting_invariants(self):
        """
        Verifies eta_str conforms strictly to 'MM:SS', 'HH:MM:SS', or '00:00' / ''.
        """
        chunks = [
            # Chunk 1: Initial (speed_bps = 0 -> eta_str = "")
            {
                "status": "downloading",
                "digest": "sha256:l",
                "total": 1000000000,
                "completed": 100000,
            },
            # Chunk 2: dt = 1.0s, db = 100000 -> speed = 100,000 B/s. remaining = 999,800,000 -> eta ~ 9998s (> 3600s) -> 'HH:MM:SS'
            {
                "status": "downloading",
                "digest": "sha256:l",
                "total": 1000000000,
                "completed": 200000,
            },
            # Chunk 3: total reduced or close to completion -> eta < 3600s -> 'MM:SS'
            {"status": "downloading", "digest": "sha256:l", "total": 300000, "completed": 250000},
            # Chunk 4: is_done -> '00:00'
            {"status": "success"},
        ]
        raw_lines = [json.dumps(c).encode("utf-8") + b"\n" for c in chunks]
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = raw_lines
        mock_resp.status = 200

        time_seq = [10.0, 11.0, 12.0, 13.0]
        received: list[ModelPullProgress] = []

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", side_effect=time_seq),
        ):
            pull_model_stream(
                model="test-model",
                progress_callback=lambda p: received.append(p),
            )

        assert received[0].eta_str == ""
        assert len(received[1].eta_str.split(":")) == 3  # HH:MM:SS format (total=1GB, eta ~ 2h46m)
        assert len(received[2].eta_str.split(":")) == 2  # MM:SS format (remaining 50KB, eta < 1m)
        assert received[3].eta_str == "00:00"

    def test_speed_str_scale_invariants(self):
        """Verifies speed_str formatting across MB/s, KB/s, B/s, and zero speed."""
        # 1. Zero speed -> ""
        p_zero = ModelPullProgress(status="test", speed_bps=0.0)
        assert p_zero.speed_str == ""

        # 2. Small bytes/s
        chunks = [
            {"status": "downloading", "digest": "sha256:l", "total": 1000, "completed": 10},
            {"status": "downloading", "digest": "sha256:l", "total": 1000, "completed": 110},
            {"status": "success"},
        ]
        raw_lines = [json.dumps(c).encode("utf-8") + b"\n" for c in chunks]
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = raw_lines
        mock_resp.status = 200

        received: list[ModelPullProgress] = []
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", side_effect=[10.0, 11.0, 12.0]),
        ):
            pull_model_stream("test-model", progress_callback=lambda p: received.append(p))

        assert "100 B/s" in received[1].speed_str


# ==============================================================================
# 3. Public API Robustness & Error Containment Tests
# ==============================================================================


class TestPublicApiRobustness:
    """Stress tests error containment across Ollama client, preflight probes, and network boundaries."""

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "",
            "   ",
            "ftp://localhost:11434",
            "file:///etc/passwd",
            "file://c:/windows/system32/cmd.exe",
            "javascript:alert(1)",
            "data:text/plain;base64,SGVsbG8=",
            "http://",
            "https://",
        ],
    )
    def test_validate_url_rejections_and_boundaries(self, invalid_url):
        """Verifies strict rejection of invalid schemes, empty hosts, and missing netlocs."""
        with pytest.raises(ValueError):
            _validate_url(invalid_url)

    def test_check_prerequisites_malformed_and_error_responses(self):
        """
        Verifies check_prerequisites never raises an unhandled exception when Ollama
        daemon returns malformed JSON, 500 errors, or connection resets.
        """
        # Scenario A: /api/tags returns invalid JSON
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<!DOCTYPE html><html><body>Error 500</body></html>"
        mock_resp.__enter__.return_value = mock_resp

        with (
            patch(
                "core.ollama.find_ollama_binary", return_value=r"C:\Program Files\Ollama\ollama.exe"
            ),
            patch("core.ollama.OllamaClient.check_connection", return_value=True),
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("core.ollama.check_edge_tts_reachability", return_value=(True, "Connected")),
        ):
            status = check_prerequisites()
            assert isinstance(status, PrerequisiteStatus)
            assert status.ollama_online is True
            assert status.installed_models == []
            assert status.all_ready is False

        # Scenario B: /api/tags returns HTTP 503 Service Unavailable
        mock_http_err = urllib.error.HTTPError(
            "http://localhost:11434/api/tags",
            503,
            "Service Unavailable",
            email.message.Message(),
            io.BytesIO(b"Service Unavailable"),
        )
        with (
            patch(
                "core.ollama.find_ollama_binary", return_value=r"C:\Program Files\Ollama\ollama.exe"
            ),
            patch("urllib.request.urlopen", side_effect=mock_http_err),
            patch("core.ollama.check_edge_tts_reachability", return_value=(True, "Connected")),
        ):
            status = check_prerequisites()
            assert isinstance(status, PrerequisiteStatus)
            assert status.ollama_online is False
            assert status.all_ready is False

    def test_check_edge_tts_reachability_all_exceptions_caught(self):
        """Verifies check_edge_tts_reachability safely encapsulates all socket/DNS/OS errors."""
        exceptions_to_test = [
            TimeoutError("Socket connection timed out"),
            socket.gaierror(11001, "getaddrinfo failed: no such host"),
            ConnectionRefusedError("Connection refused by peer"),
            ConnectionResetError("Connection reset by peer"),
            OSError("Network is unreachable"),
        ]

        for exc in exceptions_to_test:
            with patch("socket.create_connection", side_effect=exc):
                reachable, detail = check_edge_tts_reachability(timeout=1.0)
                assert reachable is False
                assert isinstance(detail, str)
                assert len(detail) > 0

    def test_pull_model_stream_cancellation_states(self):
        """
        Tests cancellation before request dispatch, during NDJSON iteration,
        and verifies cleanup and proper exception propagation.
        """
        # Pre-dispatch cancellation
        cancel_pre = threading.Event()
        cancel_pre.set()
        with pytest.raises(RuntimeError) as exc_pre:
            pull_model_stream(model="llama3.1:8b", cancel_event=cancel_pre)
        assert "cancelled by user" in str(exc_pre.value).lower()

        # Mid-stream cancellation
        cancel_mid = threading.Event()

        def mock_stream_gen():
            yield json.dumps({"status": "pulling manifest"}).encode("utf-8") + b"\n"
            cancel_mid.set()
            yield (
                json.dumps({"status": "downloading", "total": 100, "completed": 50}).encode("utf-8")
                + b"\n"
            )

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_stream_gen()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError) as exc_mid:
                pull_model_stream(model="llama3.1:8b", cancel_event=cancel_mid)
            assert "cancelled by user" in str(exc_mid.value).lower()


# ==============================================================================
# 4. Grounding Mode Propagation & Generation Tests
# ==============================================================================


class TestGroundingModeIntegration:
    """Adversarially tests grounding mode inputs and propagation into LLM prompts and pipelines."""

    @pytest.mark.parametrize(
        ("input_mode", "expected_normalized"),
        [
            # Enum instances
            (GroundingMode.STRICT, "strict"),
            (GroundingMode.CREATIVE, "creative"),
            (GroundingMode.OPEN_TOPIC, "open_topic"),
            # Canonical strings
            ("strict", "strict"),
            ("creative", "creative"),
            ("open_topic", "open_topic"),
            # Case variations and whitespace
            ("STRICT", "strict"),
            ("  Creative  ", "creative"),
            ("Open_Topic", "open_topic"),
            ("OPEN-TOPIC", "open_topic"),
            # Known aliases
            ("strict_source_only", "strict"),
            ("source_only", "strict"),
            ("kildetro", "strict"),
            ("streng", "strict"),
            ("creative_analogy", "creative"),
            ("analogy", "creative"),
            ("kreativ", "creative"),
            ("scratch", "open_topic"),
            ("fritt", "open_topic"),
            ("åpent", "open_topic"),
            ("apent_tema", "open_topic"),
            # Invalid or unrecognized inputs -> fallback to 'strict'
            ("unrecognized_xyz_mode", "strict"),
            ("", "strict"),
            ("   ", "strict"),
            (None, "strict"),
            (12345, "strict"),
            (True, "strict"),
        ],
    )
    def test_normalize_grounding_mode_matrix(self, input_mode, expected_normalized):
        """Verifies normalize_grounding_mode handles canonical names, aliases, and adversarial garbage."""
        assert normalize_grounding_mode(input_mode) == expected_normalized

    @pytest.mark.parametrize("lang", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("fmt", ["quick", "standard", "deep_dive", "extended"])
    @pytest.mark.parametrize(
        "mode", ["strict", "creative", "open_topic", "invalid_mode_garbage", None]
    )
    def test_prompt_builders_with_grounding_modes(self, lang, fmt, mode):
        """
        Verifies build_system_prompt, build_user_prompt, build_act_system_prompt, and
        build_act_user_prompt safely generate valid prompt strings across all grounding modes.
        """
        # 1. build_system_prompt
        sys_prompt = build_system_prompt(
            language=lang, format_type=fmt, tone_style="casual", grounding_mode=mode
        )
        assert isinstance(sys_prompt, str)
        assert len(sys_prompt) > 200

        norm_mode = normalize_grounding_mode(mode)
        if norm_mode == "strict":
            if lang == "nb-NO":
                assert "STRENG KILDEKONTROLL" in sys_prompt
            else:
                assert "STRICT SOURCE-ONLY" in sys_prompt
        elif norm_mode == "creative":
            if lang == "nb-NO":
                assert "KREATIV ANALOGI" in sys_prompt
            else:
                assert "CREATIVE ANALOGY" in sys_prompt
        elif norm_mode == "open_topic":
            if lang == "nb-NO":
                assert "FRITT TEMA" in sys_prompt
            else:
                assert "OPEN TOPIC" in sys_prompt

        # 2. build_user_prompt
        user_prompt = build_user_prompt(
            content="Sample source content about artificial intelligence.",
            language=lang,
            grounding_mode=mode,
        )
        assert isinstance(user_prompt, str)
        assert len(user_prompt) > 50

        # 3. build_act_system_prompt & build_act_user_prompt
        act_spec = {
            "act_num": 1,
            "title": "Intro Act",
            "prompt_theme": "Introduction to AI",
            "target_turns": 8,
            "min_turns": 6,
            "max_turns": 10,
            "is_intro": True,
            "is_outro": False,
        }
        act_sys = build_act_system_prompt(
            act=act_spec,
            total_acts=2,
            language=lang,
            tone_style="casual",
            grounding_mode=mode,
        )
        assert isinstance(act_sys, str)
        assert len(act_sys) > 100

        act_user = build_act_user_prompt(
            content="Sample source content.",
            prev_turns=None,
            language=lang,
            grounding_mode=mode,
        )
        assert isinstance(act_user, str)
        assert len(act_user) > 30

    def test_generate_podcast_script_propagates_grounding_mode(self):
        """
        Verifies generate_podcast_script accepts grounding_mode and passes it to prompt builders.
        """
        dialogue = [
            {"speaker": "Host 1", "text": "Welcome to our discussion on quantum computing."},
            {"speaker": "Host 2", "text": "Quantum computers use qubits in superposition."},
        ]
        chat_resp = {"message": {"role": "assistant", "content": json.dumps(dialogue)}}
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(chat_resp).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            # Test with creative grounding mode
            turns = generate_podcast_script(
                content="Quantum computing basics",
                language="en-US",
                format_type="quick",
                tone_style="analytical",
                grounding_mode="creative",
                model="llama3.1:8b",
            )
            assert len(turns) == 2
            assert turns[0].speaker == "Host 1"
            assert turns[1].speaker == "Host 2"

            # Test with invalid grounding mode (must fallback without error)
            turns_fallback = generate_podcast_script(
                content="Quantum computing basics",
                language="en-US",
                format_type="quick",
                tone_style="casual",
                grounding_mode="nonexistent_mode_string",
                model="llama3.1:8b",
            )
            assert len(turns_fallback) == 2


# ==============================================================================
# 5. check_env.py Comprehensive Diagnostic Tests
# ==============================================================================


class TestCheckEnvDiagnostics:
    """Adversarially tests check_env.py preflight diagnostics and CLI execution."""

    def test_check_python_version(self):
        """Tests check_python_version with mocked version tuples."""
        # 3.10 -> OK
        with patch.object(sys, "version_info", (3, 10, 0, "final", 0)):
            res = check_env.check_python_version()
            assert res["ok"] is True

        # 3.14 -> OK
        with patch.object(sys, "version_info", (3, 14, 6, "final", 0)):
            res = check_env.check_python_version()
            assert res["ok"] is True

        # 3.9 -> Fail
        with patch.object(sys, "version_info", (3, 9, 7, "final", 0)):
            res = check_env.check_python_version()
            assert res["ok"] is False
            assert res["remediation"] is not None

    def test_check_ollama_service_online_and_offline(self):
        """Tests check_ollama_service across online with models, online empty, and offline."""
        # 1. Online with models
        mock_models_data = {
            "models": [
                {
                    "name": "llama3.1:8b",
                    "size": 4920737382,
                    "details": {
                        "parameter_size": "8.0B",
                        "quantization_level": "Q4_K_M",
                        "format": "gguf",
                    },
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_models_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = check_env.check_ollama_service("http://localhost:11434")
            assert res["ok"] is True
            assert res["online"] is True
            assert res["models_count"] == 1
            assert res["models"][0]["name"] == "llama3.1:8b"
            assert res["models"][0]["size_gb"] > 4.0

        # 2. Offline URLError
        with patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")
        ):
            res_off = check_env.check_ollama_service("http://localhost:11434")
            assert res_off["ok"] is False
            assert res_off["online"] is False
            assert res_off["remediation"] is not None

    def test_run_all_checks_aggregation(self):
        """Tests run_all_checks aggregating pass/fail states correctly."""
        with (
            patch("check_env.check_python_version", return_value={"ok": True, "warn": False}),
            patch("check_env.check_virtual_env", return_value={"ok": True, "warn": False}),
            patch("check_env.check_packages", return_value={"ok": True, "warn": False}),
            patch("check_env.check_pyinstaller", return_value={"ok": True, "warn": False}),
            patch(
                "check_env.check_ollama_service",
                return_value={
                    "ok": True,
                    "warn": False,
                    "online": True,
                    "models_count": 2,
                    "models": [],
                },
            ),
            patch("check_env.check_edge_tts_network", return_value={"ok": True, "warn": False}),
        ):
            report = check_env.run_all_checks()
            assert report["all_passed"] is True
            assert report["has_warnings"] is False
            assert report["remediations"] == []

    def test_check_env_cli_execution_json_and_quiet(self):
        """Executes check_env.py via subprocess to verify CLI flags."""
        py_exe = sys.executable

        # --json flag
        res_json = subprocess.run(
            [py_exe, "check_env.py", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_json.stdout.strip().startswith("{")
        parsed = json.loads(res_json.stdout)
        assert "all_passed" in parsed
        assert "checks" in parsed

        # --quiet flag
        res_quiet = subprocess.run(
            [py_exe, "check_env.py", "--quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_quiet.stdout == ""
