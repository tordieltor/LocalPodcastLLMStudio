"""
Tests for Ollama LLM Client, Launcher, Downloader & Prerequisite Subsystem
==========================================================================
Covers:
- OllamaClient initialization and configuration
- Connection checking via GET /api/tags
- Model listing and sorting
- Dialogue generation request formatting (/api/chat & /api/generate)
- Timeout, HTTP error, and connection failure handling
- generate_podcast_script integration with parser and grounding_mode
- ModelPullProgress and PrerequisiteStatus dataclasses
- find_ollama_binary resolution across PATH, Windows envs, and POSIX
- start_ollama_service detached subprocess launching, polling, crash detection, cancellation
- pull_model_stream NDJSON streaming, speed/ETA formatting, error/cancellation handling
- check_edge_tts_reachability socket probe
- check_prerequisites aggregated diagnostic checks
"""

import email.message
import io
import json
import os
import socket
import subprocess
import threading
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from core.ollama import (
    ModelPullProgress,
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    PrerequisiteStatus,
    _validate_url,
    check_edge_tts_reachability,
    check_prerequisites,
    find_ollama_binary,
    generate_podcast_script,
    pull_model_stream,
    start_ollama_service,
)


class TestOllamaClientUnit:
    """Tier 1: Feature tests for Ollama client."""

    def test_client_init_defaults(self):
        client = OllamaClient()
        assert "11434" in client.base_url

    def test_client_init_custom_url(self):
        client = OllamaClient("http://remote-gpu:11434/")
        assert client.base_url == "http://remote-gpu:11434"

    def test_client_init_https_scheme(self):
        client = OllamaClient("https://ollama.internal.company.com:11434/")
        assert client.base_url == "https://ollama.internal.company.com:11434"

    def test_client_init_disallowed_schemes(self):
        with pytest.raises(ValueError) as exc_file:
            OllamaClient("file:///etc/passwd")
        assert "Invalid URL scheme" in str(exc_file.value)

        with pytest.raises(ValueError) as exc_ftp:
            OllamaClient("ftp://localhost:11434")
        assert "Invalid URL scheme" in str(exc_ftp.value)

        with pytest.raises(ValueError) as exc_js:
            OllamaClient("javascript:alert(1)")
        assert "Invalid URL scheme" in str(exc_js.value)

    def test_client_init_invalid_urls(self):
        with pytest.raises(ValueError):
            OllamaClient("")
        with pytest.raises(ValueError):
            OllamaClient("http://")
        with pytest.raises(ValueError):
            OllamaClient("http://:80")
        with pytest.raises(ValueError):
            _validate_url("http://:80")
        with pytest.raises(ValueError):
            _validate_url("http://")

    def test_client_init_crlf_and_control_chars(self):
        with pytest.raises(ValueError) as exc1:
            OllamaClient("http://localhost:11434\r\nX-Injected: Header")
        assert "forbidden control characters" in str(exc1.value)

        with pytest.raises(ValueError) as exc2:
            _validate_url("http://localhost:11434\nHost: evil.com")
        assert "forbidden control characters" in str(exc2.value)

        with pytest.raises(ValueError) as exc3:
            _validate_url("http://localhost:11434\x00")
        assert "forbidden control characters" in str(exc3.value)

        with pytest.raises(ValueError) as exc4:
            _validate_url("http://localhost:11434 /api")
        assert "forbidden control characters" in str(exc4.value)

    def test_check_connection_success(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = OllamaClient()
            assert client.check_connection() is True

    def test_check_connection_failure(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            client = OllamaClient()
            assert client.check_connection() is False

    def test_list_models_success(self, mock_ollama_tags_data):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_ollama_tags_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = OllamaClient()
            models = client.list_models()
            assert len(models) == 3
            assert "llama3.1:8b" in models
            assert "qwen2.5:7b" in models
            assert "mistral-nemo:latest" in models

    def test_list_models_empty(self, mock_ollama_empty_tags):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_ollama_empty_tags).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = OllamaClient()
            models = client.list_models()
            assert models == []

    def test_client_pull_model_delegation(self):
        with patch("core.ollama.pull_model_stream", return_value=True) as mock_pull:
            client = OllamaClient("http://localhost:11434")
            res = client.pull_model("llama3.1:8b")
            assert res is True
            mock_pull.assert_called_once()
            _, kwargs = mock_pull.call_args
            assert kwargs.get("model") == "llama3.1:8b"
            assert kwargs.get("base_url") == "http://localhost:11434"

    def test_client_check_prerequisites_delegation(self):
        with patch("core.ollama.check_prerequisites", return_value=MagicMock()) as mock_check:
            client = OllamaClient("http://localhost:11434")
            res = client.check_prerequisites(recommended_model="qwen2.5:7b")
            assert res is not None
            mock_check.assert_called_once_with(
                ollama_url="http://localhost:11434",
                recommended_model="qwen2.5:7b",
                timeout=3.0,
            )


class TestOllamaGenerationAndErrors:
    """Tier 2: Request payload generation and failure handling."""

    def test_generate_dialogue_via_chat_endpoint(self, sample_norwegian_turns):
        dialogue_json = json.dumps(
            [{"speaker": t.speaker, "text": t.text} for t in sample_norwegian_turns]
        )
        chat_response = {"message": {"role": "assistant", "content": dialogue_json}}

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(chat_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = OllamaClient()
            gen_func = getattr(client, "generate_dialogue", client.generate)
            if gen_func == client.generate:
                result = client.generate(
                    model="llama3.1:8b",
                    system="Du er en podcast-forfatter...",
                    prompt="Lag et podcast-manus...",
                )
            else:
                result = client.generate_dialogue(
                    model="llama3.1:8b",
                    system_prompt="Du er en podcast-forfatter...",
                    user_prompt="Lag et podcast-manus...",
                )
            assert "Host 1" in result

    def test_generate_dialogue_fallback_to_generate_endpoint(self, sample_english_turns):
        dialogue_json = json.dumps(
            [{"speaker": t.speaker, "text": t.text} for t in sample_english_turns]
        )
        gen_response = {"response": dialogue_json}

        # First call to /api/chat raises HTTPError 404, second call to /api/generate succeeds
        mock_chat_err = urllib.error.HTTPError(
            "http://localhost:11434/api/chat",
            404,
            "Not Found",
            email.message.Message(),
            None,
        )
        mock_gen_resp = MagicMock()
        mock_gen_resp.status = 200
        mock_gen_resp.read.return_value = json.dumps(gen_response).encode("utf-8")
        mock_gen_resp.__enter__.return_value = mock_gen_resp

        with patch(
            "urllib.request.urlopen",
            side_effect=[mock_chat_err, mock_gen_resp],
        ):
            client = OllamaClient()
            result = client.generate(
                model="llama3.1:8b",
                system="You are a podcast writer...",
                prompt="Create a script...",
            )
            assert "Host 1" in result

    def test_generate_dialogue_timeout_error(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError()):
            client = OllamaClient()
            with pytest.raises(TimeoutError) as exc_info:
                client.generate(model="llama3.1:8b", system="", prompt="")
            assert (
                "timeout" in str(exc_info.value).lower()
                or "timed out" in str(exc_info.value).lower()
            )

    def test_generate_dialogue_connection_refused_error(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            client = OllamaClient()
            with pytest.raises(OllamaConnectionError):
                client.generate(model="llama3.1:8b", system="", prompt="")

    def test_generate_dialogue_model_not_found_error(self):
        mock_http_err = urllib.error.HTTPError(
            "http://localhost:11434/api/chat",
            404,
            "Not Found",
            email.message.Message(),
            io.BytesIO(b'{"error": "model \'missing_model:latest\' not found"}'),
        )
        with patch("urllib.request.urlopen", side_effect=mock_http_err):
            client = OllamaClient()
            with pytest.raises(OllamaModelNotFoundError):
                client.generate(model="missing_model:latest", prompt="Test")

    def test_generate_dialogue_pre_request_cancellation(self):
        cancel_event = threading.Event()
        cancel_event.set()
        client = OllamaClient()
        with pytest.raises(RuntimeError) as exc_info:
            client.generate(model="llama3.1:8b", prompt="Test", cancel_event=cancel_event)
        assert "cancelled by user" in str(exc_info.value).lower()

    def test_generate_podcast_script_integration(self, sample_english_turns):
        dialogue_json = json.dumps(
            [{"speaker": t.speaker, "text": t.text} for t in sample_english_turns]
        )
        chat_response = {"message": {"role": "assistant", "content": dialogue_json}}

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(chat_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            turns = generate_podcast_script(
                content="Quantum computing overview",
                language="en-US",
                format_type="quick",
                tone_style="casual",
                grounding_mode="strict",
                model="llama3.1:8b",
            )
            assert len(turns) == len(sample_english_turns)
            assert turns[0].speaker == "Host 1"
            assert "Welcome back" in turns[0].text

    def test_generate_podcast_script_multi_act_extended(self):
        act_turns = [
            {"speaker": "Host 1", "text": "Del en replikk."},
            {"speaker": "Host 2", "text": "Del to replikk."},
        ]
        dialogue_json = json.dumps(act_turns)
        chat_response = {"message": {"role": "assistant", "content": dialogue_json}}

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(chat_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            progress_messages = []
            turns = generate_podcast_script(
                content="Studentsamskipnaden i Bergen og på Vestlandet",
                language="nb-NO",
                format_type="extended",
                tone_style="analytical",
                grounding_mode="creative",
                model="mistral-nemo:latest",
                progress_callback=lambda msg: progress_messages.append(msg),
            )
            # Extended in-depth has 5 acts, 2 turns each mock -> 10 turns
            assert len(turns) == 10
            assert any("Act 1" in m or "Akt 1" in m for m in progress_messages)
            assert any("Act 5" in m or "Akt 5" in m for m in progress_messages)

    def test_generate_podcast_script_streaming_callbacks(self):
        act_turns = [
            {"speaker": "Host 1", "text": "Hei verden"},
            {"speaker": "Host 2", "text": "Hei tilbake"},
        ]
        dialogue_json = json.dumps(act_turns)
        lines = [
            json.dumps({"message": {"role": "assistant", "content": "Hei "}}).encode("utf-8"),
            json.dumps({"message": {"role": "assistant", "content": "verden\n"}}).encode("utf-8"),
            json.dumps(
                {"message": {"role": "assistant", "content": dialogue_json}, "done": True}
            ).encode("utf-8"),
        ]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__iter__.return_value = lines
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            streamed_chunks = []
            act_updates = []

            turns = generate_podcast_script(
                content="Tema for episode",
                language="nb-NO",
                format_type="quick",
                model="llama3.1:8b",
                stream_callback=lambda chunk: streamed_chunks.append(chunk),
                act_callback=lambda act_idx, tot, turns: act_updates.append(
                    (act_idx, tot, len(turns))
                ),
            )
            assert len(turns) == 2
            assert len(streamed_chunks) >= 2
            assert len(act_updates) == 1
            assert act_updates[0] == (1, 1, 2)


class TestModelPullProgressDataclass:
    """Validation of ModelPullProgress dataclass."""

    def test_dataclass_defaults(self):
        p = ModelPullProgress(status="starting")
        assert p.status == "starting"
        assert p.digest == ""
        assert p.total == 0
        assert p.completed == 0
        assert p.percentage == 0.0
        assert p.speed_bps == 0.0
        assert p.speed_str == ""
        assert p.progress_str == ""
        assert p.eta_str == ""
        assert p.is_done is False
        assert p.error is None

    def test_dataclass_custom_values(self):
        p = ModelPullProgress(
            status="downloading",
            digest="sha256:1234",
            total=1000,
            completed=500,
            percentage=0.5,
            speed_bps=500000.0,
            speed_str="488 KB/s",
            progress_str="500.0 MB / 1000.0 MB (50.0%)",
            eta_str="00:01",
            is_done=False,
            error=None,
        )
        assert p.percentage == 0.5
        assert p.speed_str == "488 KB/s"
        assert p.is_done is False
        assert p.total == 1000
        assert p.completed == 500


class TestPrerequisiteStatusDataclass:
    """Validation of PrerequisiteStatus dataclass."""

    def test_dataclass_fields(self):
        s = PrerequisiteStatus(
            ollama_binary_found=True,
            ollama_binary_path=r"C:\Program Files\Ollama\ollama.exe",
            ollama_online=True,
            installed_models=["llama3.1:8b"],
            has_recommended_model=True,
            recommended_model_name="llama3.1:8b",
            edge_tts_online=True,
            all_ready=True,
            remediation_hints=[],
        )
        assert s.ollama_binary_found is True
        assert s.all_ready is True
        assert len(s.installed_models) == 1
        assert s.remediation_hints == []


class TestEdgeTTSReachabilityProbe:
    """Validation of Edge-TTS socket connection probe."""

    def test_reachability_success(self):
        mock_sock = MagicMock()
        with patch("socket.create_connection", return_value=mock_sock) as mock_conn:
            reachable, detail = check_edge_tts_reachability(timeout=2.5)
            assert reachable is True
            assert "speech.platform.bing.com:443" in detail
            mock_conn.assert_called_once_with(("speech.platform.bing.com", 443), timeout=2.5)

    def test_reachability_timeout(self):
        with patch(
            "socket.create_connection",
            side_effect=TimeoutError("Connection timed out"),
        ):
            reachable, detail = check_edge_tts_reachability(timeout=1.0)
            assert reachable is False
            assert "timed out after 1.0s" in detail

    def test_reachability_dns_failure(self):
        with patch(
            "socket.create_connection",
            side_effect=socket.gaierror(11001, "getaddrinfo failed"),
        ):
            reachable, detail = check_edge_tts_reachability(timeout=3.0)
            assert reachable is False
            assert "DNS resolution failed" in detail

    def test_reachability_os_error(self):
        with patch(
            "socket.create_connection",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            reachable, detail = check_edge_tts_reachability(timeout=3.0)
            assert reachable is False
            assert "Reachability probe failed" in detail

    def test_reachability_invalid_timeout_inputs(self):
        """Security unit test: Verifies invalid timeout values fail safely without socket connection attempt."""
        with patch("socket.create_connection") as mock_conn:
            reachable, detail = check_edge_tts_reachability(timeout=-1.0)
            assert reachable is False
            assert "Invalid timeout" in detail

            reachable, detail = check_edge_tts_reachability(timeout=0)
            assert reachable is False
            assert "Invalid timeout" in detail

            reachable, detail = check_edge_tts_reachability(timeout="invalid")
            assert reachable is False
            assert "Invalid timeout" in detail

            reachable, detail = check_edge_tts_reachability(timeout=True)
            assert reachable is False
            assert "Invalid timeout" in detail

            reachable, detail = check_edge_tts_reachability(timeout=float("nan"))
            assert reachable is False
            assert "Invalid timeout" in detail

            mock_conn.assert_not_called()


class TestOllamaBinaryResolver:
    """Tests for find_ollama_binary across platforms and fallback paths."""

    def test_find_binary_in_path(self):
        with (
            patch("shutil.which", return_value=r"C:\Custom\Ollama\ollama.exe"),
            patch("os.path.isfile", return_value=True),
        ):
            res = find_ollama_binary()
            assert res is not None
            assert "ollama.exe" in res.lower()

    def test_find_binary_in_localappdata(self):
        def mock_isfile(p):
            norm = p.replace("\\", "/")
            return "AppData/Local/Programs/Ollama/ollama.exe" in norm

        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"}),
            patch("sys.platform", "win32"),
            patch("os.path.isfile", side_effect=mock_isfile),
        ):
            res = find_ollama_binary()
            assert res is not None
            norm_res = res.replace("\\", "/")
            assert "Tester/AppData/Local/Programs/Ollama/ollama.exe" in norm_res

    def test_find_binary_in_program_files(self):
        def mock_isfile(p):
            norm = p.replace("\\", "/")
            return "Program Files/Ollama/ollama.exe" in norm

        with (
            patch("shutil.which", return_value=None),
            patch.dict(
                os.environ,
                {"LOCALAPPDATA": "", "ProgramFiles": r"C:\Program Files"},
            ),
            patch("sys.platform", "win32"),
            patch("os.path.isfile", side_effect=mock_isfile),
        ):
            res = find_ollama_binary()
            assert res is not None
            norm_res = res.replace("\\", "/")
            assert "Program Files/Ollama/ollama.exe" in norm_res

    def test_find_binary_in_program_files_x86(self):
        def mock_isfile(p):
            norm = p.replace("\\", "/")
            return "Program Files (x86)/Ollama/ollama.exe" in norm

        with (
            patch("shutil.which", return_value=None),
            patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": "",
                    "ProgramFiles": "",
                    "ProgramFiles(x86)": r"C:\Program Files (x86)",
                },
            ),
            patch("sys.platform", "win32"),
            patch("os.path.isfile", side_effect=mock_isfile),
        ):
            res = find_ollama_binary()
            assert res is not None
            norm_res = res.replace("\\", "/")
            assert "Program Files (x86)/Ollama/ollama.exe" in norm_res

    def test_find_binary_in_program_w6432(self):
        def mock_isfile(p):
            norm = p.replace("\\", "/")
            return "ProgramW6432/Ollama/ollama.exe" in norm

        with (
            patch("shutil.which", return_value=None),
            patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": "",
                    "ProgramFiles": "",
                    "ProgramFiles(x86)": "",
                    "ProgramW6432": r"C:\ProgramW6432",
                },
            ),
            patch("sys.platform", "win32"),
            patch("os.path.isfile", side_effect=mock_isfile),
        ):
            res = find_ollama_binary()
            assert res is not None
            norm_res = res.replace("\\", "/")
            assert "ProgramW6432/Ollama/ollama.exe" in norm_res

    def test_find_binary_posix_fallbacks(self):
        def mock_isfile(p):
            return p == "/usr/local/bin/ollama"

        with (
            patch("shutil.which", return_value=None),
            patch("sys.platform", "linux"),
            patch("os.name", "posix"),
            patch("os.path.isfile", side_effect=mock_isfile),
        ):
            res = find_ollama_binary()
            assert res == os.path.abspath("/usr/local/bin/ollama")

    def test_find_binary_not_found(self):
        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {}, clear=True),
            patch("os.path.isfile", return_value=False),
        ):
            res = find_ollama_binary()
            assert res is None


class TestOllamaServiceLauncher:
    """Tests for start_ollama_service background execution and health polling."""

    def test_start_service_already_running(self):
        with (
            patch("core.ollama.OllamaClient.check_connection", return_value=True),
            patch("subprocess.Popen") as mock_popen,
        ):
            success, msg = start_ollama_service()
            assert success is True
            assert "already running" in msg
            mock_popen.assert_not_called()

    def test_start_service_binary_not_found(self):
        with (
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch("core.ollama.find_ollama_binary", return_value=None),
            patch("subprocess.Popen") as mock_popen,
        ):
            success, msg = start_ollama_service()
            assert success is False
            assert "not found" in msg.lower()
            mock_popen.assert_not_called()

    def test_start_service_windows_flags_success(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        conn_results = [False, True]
        with (
            patch(
                "core.ollama.OllamaClient.check_connection",
                side_effect=conn_results,
            ),
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Ollama\ollama.exe",
            ),
            patch("sys.platform", "win32"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
            patch("time.sleep"),
        ):
            success, msg = start_ollama_service(timeout=5.0)
            assert success is True
            assert "started successfully" in msg
            mock_popen.assert_called_once()
            _, kwargs = mock_popen.call_args
            assert kwargs.get("close_fds") is True
            assert kwargs.get("stdin") == subprocess.DEVNULL
            assert kwargs.get("stdout") == subprocess.DEVNULL
            assert kwargs.get("stderr") == subprocess.DEVNULL
            creationflags = kwargs.get("creationflags", 0)
            assert creationflags & 0x08000000  # CREATE_NO_WINDOW
            assert creationflags & 0x00000008  # DETACHED_PROCESS

    def test_start_service_posix_flags_success(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        conn_results = [False, True]
        with (
            patch(
                "core.ollama.OllamaClient.check_connection",
                side_effect=conn_results,
            ),
            patch(
                "core.ollama.find_ollama_binary",
                return_value="/usr/local/bin/ollama",
            ),
            patch("sys.platform", "darwin"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
            patch("time.sleep"),
        ):
            success, msg = start_ollama_service(timeout=5.0)
            assert success is True
            mock_popen.assert_called_once()
            _, kwargs = mock_popen.call_args
            assert kwargs.get("start_new_session") is True
            assert "creationflags" not in kwargs

    def test_start_service_immediate_crash(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1

        with (
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Ollama\ollama.exe",
            ),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("time.sleep"),
        ):
            success, msg = start_ollama_service(timeout=5.0)
            assert success is False
            assert (
                "terminated immediately" in msg or "exit code 1" in msg or "failed" in msg.lower()
            )

    def test_start_service_timeout(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Ollama\ollama.exe",
            ),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("time.sleep"),
            patch(
                "time.time",
                side_effect=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
            ),
        ):
            success, msg = start_ollama_service(timeout=2.0)
            assert success is False
            assert "failed to become responsive" in msg or "seconds" in msg

    def test_start_service_preflight_cancellation(self):
        """Pre-set cancel_event must immediately abort without checking connection or spawning."""
        cancel_ev = threading.Event()
        cancel_ev.set()
        with (
            patch("core.ollama.OllamaClient.check_connection") as mock_check,
            patch("core.ollama.find_ollama_binary") as mock_find,
            patch("subprocess.Popen") as mock_popen,
        ):
            success, msg = start_ollama_service(cancel_event=cancel_ev)
            assert success is False
            assert "cancelled by user" in msg.lower()
            mock_check.assert_not_called()
            mock_find.assert_not_called()
            mock_popen.assert_not_called()

    def test_start_service_user_cancellation(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        cancel_ev = threading.Event()
        cancel_ev.set()

        with (
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Ollama\ollama.exe",
            ),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            success, msg = start_ollama_service(timeout=5.0, cancel_event=cancel_ev)
            assert success is False
            assert "cancelled by user" in msg.lower()

    def test_start_service_popen_oserror(self):
        with (
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Ollama\ollama.exe",
            ),
            patch(
                "subprocess.Popen",
                side_effect=PermissionError("Access is denied"),
            ),
        ):
            success, msg = start_ollama_service(timeout=5.0)
            assert success is False
            assert "Failed to start Ollama process" in msg
            assert "Access is denied" in msg


class TestStreamingModelDownloader:
    """Tests for pull_model_stream NDJSON streaming, speed/ETA metrics, and error trapping."""

    def _make_mock_response(self, lines: list[dict | str | bytes]):
        raw_lines = []
        for item in lines:
            if isinstance(item, dict):
                raw_lines.append(json.dumps(item).encode("utf-8") + b"\n")
            elif isinstance(item, str):
                raw_lines.append(item.encode("utf-8") + b"\n")
            elif isinstance(item, bytes):
                raw_lines.append(item + b"\n")
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = raw_lines
        mock_resp.status = 200
        return mock_resp

    def test_pull_success_multi_chunk(self):
        stream_chunks = [
            {"status": "pulling manifest"},
            {
                "status": "downloading",
                "digest": "sha256:abc",
                "total": 1000,
                "completed": 250,
            },
            {
                "status": "downloading",
                "digest": "sha256:abc",
                "total": 1000,
                "completed": 750,
            },
            {"status": "verifying sha256 digest"},
            {"status": "writing manifest"},
            {"status": "success"},
        ]
        mock_resp = self._make_mock_response(stream_chunks)
        progress_reports: list[ModelPullProgress] = []

        with patch("urllib.request.urlopen", return_value=mock_resp):
            success = pull_model_stream(
                model="llama3.1:8b",
                progress_callback=lambda p: progress_reports.append(p),
            )
            assert success is True
            assert len(progress_reports) == 6
            assert progress_reports[0].status == "pulling manifest"
            assert progress_reports[1].completed == 250
            assert progress_reports[1].percentage == 0.25
            assert progress_reports[2].completed == 750
            assert progress_reports[2].percentage == 0.75
            assert progress_reports[-1].is_done is True
            assert progress_reports[-1].percentage == 1.0

    def test_pull_metrics_calculation(self):
        stream_chunks = [
            {
                "status": "downloading",
                "digest": "sha256:layer1",
                "total": 4294967296,
                "completed": 1073741824,
            },
            {
                "status": "downloading",
                "digest": "sha256:layer1",
                "total": 4294967296,
                "completed": 2147483648,
            },
            {"status": "success"},
        ]
        mock_resp = self._make_mock_response(stream_chunks)
        progress_reports: list[ModelPullProgress] = []

        time_values = [100.0, 101.0, 102.0]
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", side_effect=time_values),
        ):
            pull_model_stream(
                model="llama3.1:8b",
                progress_callback=lambda p: progress_reports.append(p),
            )
            # Chunk 0: 1.00 GB / 4.00 GB (25.0%)
            assert "1.00 GB / 4.00 GB (25.0%)" in progress_reports[0].progress_str
            # Chunk 1: 2.00 GB / 4.00 GB (50.0%)
            assert "2.00 GB / 4.00 GB (50.0%)" in progress_reports[1].progress_str
            assert progress_reports[1].speed_bps > 0
            assert "MB/s" in progress_reports[1].speed_str
            assert progress_reports[1].eta_str != ""

    def test_pull_speed_units_kb_and_bytes(self):
        stream_chunks = [
            {
                "status": "downloading",
                "digest": "sha256:l1",
                "total": 500000,
                "completed": 10000,
            },
            {
                "status": "downloading",
                "digest": "sha256:l1",
                "total": 500000,
                "completed": 20000,
            },
            {
                "status": "downloading",
                "digest": "sha256:l1",
                "total": 500000,
                "completed": 20100,
            },
            {"status": "success"},
        ]
        mock_resp = self._make_mock_response(stream_chunks)
        reports: list[ModelPullProgress] = []

        # dt = 1.0s, delta = 10000 bytes -> ~9.8 KB/s
        # dt = 1.0s, delta = 100 bytes -> small B/s
        time_values = [10.0, 11.0, 12.0, 13.0]
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("time.monotonic", side_effect=time_values),
        ):
            pull_model_stream(
                model="small-model:latest",
                progress_callback=lambda p: reports.append(p),
            )
            assert "KB/s" in reports[1].speed_str
            assert "MB" in reports[1].progress_str

    def test_pull_server_error_chunk(self):
        stream_chunks = [
            {"status": "pulling manifest"},
            {"error": "pull model manifest: file does not exist"},
        ]
        mock_resp = self._make_mock_response(stream_chunks)
        progress_reports: list[ModelPullProgress] = []

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError) as exc_info:
                pull_model_stream(
                    model="nonexistent:latest",
                    progress_callback=lambda p: progress_reports.append(p),
                )
            assert "file does not exist" in str(exc_info.value)
            assert len(progress_reports) == 2
            assert progress_reports[-1].status == "error"
            assert (
                "file does not exist" in progress_reports[-1].error
                if progress_reports[-1].error
                else True
            )

    def test_pull_cancel_before_dispatch(self):
        cancel_event = threading.Event()
        cancel_event.set()

        with pytest.raises(RuntimeError) as exc_info:
            pull_model_stream(model="llama3.1:8b", cancel_event=cancel_event)
        assert "cancelled by user before request" in str(exc_info.value)

    def test_pull_cancel_during_stream(self):
        cancel_event = threading.Event()

        def stream_generator():
            yield (json.dumps({"status": "pulling manifest"}).encode("utf-8") + b"\n")
            cancel_event.set()
            yield (
                json.dumps({"status": "downloading", "total": 100, "completed": 10}).encode("utf-8")
                + b"\n"
            )

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = stream_generator()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError) as exc_info:
                pull_model_stream(model="llama3.1:8b", cancel_event=cancel_event)
            assert "cancelled by user" in str(exc_info.value)

    def test_pull_malformed_json_resilience(self):
        stream_chunks = [
            {"status": "pulling manifest"},
            "CORRUPTED_NON_JSON_DATA_GARBAGE",
            "",
            {"status": "success"},
        ]
        mock_resp = self._make_mock_response(stream_chunks)
        progress_reports: list[ModelPullProgress] = []

        with patch("urllib.request.urlopen", return_value=mock_resp):
            success = pull_model_stream(
                model="llama3.1:8b",
                progress_callback=lambda p: progress_reports.append(p),
            )
            assert success is True
            assert len(progress_reports) == 2
            assert progress_reports[0].status == "pulling manifest"
            assert progress_reports[1].is_done is True

    def test_pull_http_error_handling(self):
        mock_http_err = urllib.error.HTTPError(
            "http://localhost:11434/api/pull",
            404,
            "Not Found",
            email.message.Message(),
            io.BytesIO(b'{"error": "model \'unknown\' not found"}'),
        )
        with patch("urllib.request.urlopen", side_effect=mock_http_err):
            with pytest.raises(RuntimeError) as exc_info:
                pull_model_stream(model="unknown")
            assert "404" in str(exc_info.value) or "unknown" in str(exc_info.value)

    def test_pull_url_error_connection_refused(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with pytest.raises(OllamaConnectionError):
                pull_model_stream(model="llama3.1:8b")

    def test_pull_url_error_socket_timeout(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError(TimeoutError("Connection timed out")),
        ):
            with pytest.raises(TimeoutError):
                pull_model_stream(model="llama3.1:8b")

    def test_pull_timeout_error(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=TimeoutError("Request timed out"),
        ):
            with pytest.raises(TimeoutError):
                pull_model_stream(model="llama3.1:8b", timeout=5.0)

    def test_pull_invalid_model_names(self):
        with pytest.raises(ValueError):
            pull_model_stream(model="")
        with pytest.raises(ValueError):
            pull_model_stream(model="   ")

    def test_pull_invalid_urls(self):
        with pytest.raises(ValueError):
            pull_model_stream(model="llama3.1:8b", base_url="ftp://localhost:11434")


class TestPrerequisiteStatusCheck:
    """Validation of aggregated check_prerequisites logic and remediation suggestions."""

    def test_check_prerequisites_all_ready(self):
        with (
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Program Files\Ollama\ollama.exe",
            ),
            patch("core.ollama.OllamaClient.check_connection", return_value=True),
            patch(
                "core.ollama.OllamaClient.list_models",
                return_value=["llama3.1:8b", "qwen2.5:7b"],
            ),
            patch(
                "core.ollama.check_edge_tts_reachability",
                return_value=(True, "Connected"),
            ),
        ):
            status = check_prerequisites(recommended_model="llama3.1:8b")
            assert status.all_ready is True
            assert status.ollama_binary_found is True
            assert status.ollama_online is True
            assert status.has_recommended_model is True
            assert status.edge_tts_online is True
            assert status.remediation_hints == []

    def test_check_prerequisites_ollama_offline_binary_found(self):
        with (
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Program Files\Ollama\ollama.exe",
            ),
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch(
                "core.ollama.check_edge_tts_reachability",
                return_value=(True, "Connected"),
            ),
        ):
            status = check_prerequisites(recommended_model="llama3.1:8b")
            assert status.all_ready is False
            assert status.ollama_binary_found is True
            assert status.ollama_online is False
            assert len(status.remediation_hints) > 0
            assert any(
                "offline" in h.lower() or "serve" in h.lower() for h in status.remediation_hints
            )

    def test_check_prerequisites_ollama_offline_binary_missing(self):
        with (
            patch("core.ollama.find_ollama_binary", return_value=None),
            patch("core.ollama.OllamaClient.check_connection", return_value=False),
            patch(
                "core.ollama.check_edge_tts_reachability",
                return_value=(True, "Connected"),
            ),
        ):
            status = check_prerequisites(recommended_model="llama3.1:8b")
            assert status.all_ready is False
            assert status.ollama_binary_found is False
            assert status.ollama_online is False
            assert any(
                "not found" in h.lower() or "install" in h.lower() for h in status.remediation_hints
            )

    def test_check_prerequisites_no_models_installed(self):
        with (
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Program Files\Ollama\ollama.exe",
            ),
            patch("core.ollama.OllamaClient.check_connection", return_value=True),
            patch("core.ollama.OllamaClient.list_models", return_value=[]),
            patch(
                "core.ollama.check_edge_tts_reachability",
                return_value=(True, "Connected"),
            ),
        ):
            status = check_prerequisites(recommended_model="llama3.1:8b")
            assert status.all_ready is False
            assert status.ollama_online is True
            assert len(status.installed_models) == 0
            assert status.has_recommended_model is False
            assert any(
                "no llm models" in h.lower() or "pull" in h.lower()
                for h in status.remediation_hints
            )

    def test_check_prerequisites_missing_recommended_model(self):
        with (
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Program Files\Ollama\ollama.exe",
            ),
            patch("core.ollama.OllamaClient.check_connection", return_value=True),
            patch(
                "core.ollama.OllamaClient.list_models",
                return_value=["qwen2.5:7b"],
            ),
            patch(
                "core.ollama.check_edge_tts_reachability",
                return_value=(True, "Connected"),
            ),
        ):
            status = check_prerequisites(recommended_model="llama3.1:8b")
            assert status.all_ready is True  # Online + has model + tts online
            assert status.has_recommended_model is False
            assert any("recommended model" in h.lower() for h in status.remediation_hints)

    def test_check_prerequisites_edge_tts_offline(self):
        with (
            patch(
                "core.ollama.find_ollama_binary",
                return_value=r"C:\Program Files\Ollama\ollama.exe",
            ),
            patch("core.ollama.OllamaClient.check_connection", return_value=True),
            patch(
                "core.ollama.OllamaClient.list_models",
                return_value=["llama3.1:8b"],
            ),
            patch(
                "core.ollama.check_edge_tts_reachability",
                return_value=(False, "Connection timed out"),
            ),
        ):
            status = check_prerequisites(recommended_model="llama3.1:8b")
            assert status.all_ready is False
            assert status.edge_tts_online is False
            assert any(
                "edge-tts" in h.lower() or "unreachable" in h.lower()
                for h in status.remediation_hints
            )
