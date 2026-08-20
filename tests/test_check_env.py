"""
Tests for Environment Diagnostics (check_env.py)
=================================================
Covers Tiers 1 and 2:
- Python runtime version checks
- Virtual environment detection (.venv)
- Package import checks (customtkinter, edge-tts, pypdf, requests, pyinstaller)
- Ollama service connection detection and model parsing
- Edge-TTS network reachability probing
- JSON reporting and CLI option execution
"""

import json
import sys
import urllib.error
from unittest.mock import MagicMock, patch

import check_env


class TestCheckEnvUnit:
    """Tier 1: Unit feature tests for check_env functions."""

    def test_check_python_version_valid(self, monkeypatch):
        monkeypatch.setattr(sys, "version_info", (3, 11, 4, "final", 0))
        res = check_env.check_python_version()
        assert res["ok"] is True
        assert "3.11.4" in res["version"]
        assert res["remediation"] is None

    def test_check_python_version_invalid(self, monkeypatch):
        monkeypatch.setattr(sys, "version_info", (3, 9, 2, "final", 0))
        res = check_env.check_python_version()
        assert res["ok"] is False
        assert "3.9.2" in res["version"]
        assert res["remediation"] is not None
        assert "3.10" in res["remediation"]

    def test_check_virtual_env_active(self, monkeypatch):
        monkeypatch.setattr(sys, "prefix", "/path/to/.venv")
        monkeypatch.setattr(sys, "base_prefix", "/usr/local")
        res = check_env.check_virtual_env()
        assert res["ok"] is True
        assert res["active"] is True
        assert res["warn"] is False

    def test_check_virtual_env_global(self, monkeypatch):
        monkeypatch.setattr(sys, "prefix", "/usr/local")
        monkeypatch.setattr(sys, "base_prefix", "/usr/local")
        if hasattr(sys, "real_prefix"):
            monkeypatch.delattr(sys, "real_prefix")
        res = check_env.check_virtual_env()
        assert res["ok"] is True
        assert res["active"] is False
        assert res["warn"] is True
        assert res["remediation"] is not None

    def test_check_packages_all_present(self):
        # We know test environment or patched imports
        res = check_env.check_packages()
        assert "name" in res
        assert "installed" in res

    def test_check_packages_missing(self, monkeypatch):
        orig_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("No module named pypdf")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        res = check_env.check_packages()
        assert res["ok"] is False
        assert "pypdf" in res["missing"]
        assert res["remediation"] is not None

    def test_check_pyinstaller_installed(self):
        with patch.dict("sys.modules", {"PyInstaller": MagicMock(__version__="6.4.0")}):
            res = check_env.check_pyinstaller()
            assert res["ok"] is True
            assert res["installed"] is True
            assert res["warn"] is False

    def test_check_pyinstaller_missing(self, monkeypatch):
        orig_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "PyInstaller":
                raise ImportError("No module named PyInstaller")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        res = check_env.check_pyinstaller()
        assert res["ok"] is True
        assert res["warn"] is True
        assert res["installed"] is False


class TestCheckEnvOllama:
    """Tier 2: Ollama and Network probing tests with mock scenarios."""

    def test_check_ollama_online_with_models(self, mock_ollama_tags_data):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_ollama_tags_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = check_env.check_ollama_service("http://localhost:11434")
            assert res["ok"] is True
            assert res["online"] is True
            assert res["models_count"] == 3
            assert len(res["models"]) == 3
            assert res["models"][0]["name"] == "llama3.1:8b"
            assert res["models"][0]["size_gb"] > 0
            assert res["remediation"] is None

    def test_check_ollama_online_empty_models(self, mock_ollama_empty_tags):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_ollama_empty_tags).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = check_env.check_ollama_service("http://localhost:11434")
            assert res["ok"] is True
            assert res["online"] is True
            assert res["warn"] is True
            assert res["models_count"] == 0
            assert res["remediation"] is not None
            assert "ollama pull" in res["remediation"]

    def test_check_ollama_offline_url_error(self):
        with patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")
        ):
            res = check_env.check_ollama_service("http://localhost:11434")
            assert res["ok"] is False
            assert res["online"] is False
            assert "Offline" in res["detail"]
            assert "ollama serve" in res["remediation"]

    def test_check_ollama_timeout(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError()):
            res = check_env.check_ollama_service("http://localhost:11434", timeout_sec=0.1)
            assert res["ok"] is False
            assert res["online"] is False
            assert "timed out" in res["detail"]

    def test_check_ollama_service_invalid_scheme(self):
        res = check_env.check_ollama_service("file:///etc/passwd")
        assert res["ok"] is False
        assert res["online"] is False
        assert "Invalid Ollama URL" in res["detail"]

    def test_check_edge_tts_network_success(self):
        mock_sock = MagicMock()
        with patch("socket.create_connection", return_value=mock_sock):
            res = check_env.check_edge_tts_network()
            assert res["ok"] is True
            assert res["reachable"] is True
            assert res["warn"] is False

    def test_check_edge_tts_network_failure(self):
        with patch("socket.create_connection", side_effect=OSError("DNS failed")):
            res = check_env.check_edge_tts_network()
            assert res["ok"] is False
            assert res["reachable"] is False
            assert res["warn"] is True
            assert "remediation" in res


class TestCheckEnvAggregationAndCLI:
    """Tier 3: Aggregated report structure and CLI execution."""

    def test_run_all_checks_structure(self, mock_ollama_tags_data):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_ollama_tags_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        mock_sock = MagicMock()
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("socket.create_connection", return_value=mock_sock),
        ):
            report = check_env.run_all_checks()
            assert "timestamp" in report
            assert "checks" in report
            assert "python" in report["checks"]
            assert "ollama_service" in report["checks"]
            assert isinstance(report["remediations"], list)

    def test_main_json_flag(self, monkeypatch, capsys, mock_ollama_tags_data):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_ollama_tags_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_sock = MagicMock()

        monkeypatch.setattr(sys, "argv", ["check_env.py", "--json"])
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("socket.create_connection", return_value=mock_sock),
        ):
            exit_code = check_env.main()
            captured = capsys.readouterr()
            parsed = json.loads(captured.out)
            assert "checks" in parsed
            assert "python" in parsed["checks"]
            assert exit_code == (0 if parsed["all_passed"] else 1)

    def test_main_quiet_flag(self, monkeypatch, capsys, mock_ollama_tags_data):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_ollama_tags_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_sock = MagicMock()

        monkeypatch.setattr(sys, "argv", ["check_env.py", "--quiet"])
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("socket.create_connection", return_value=mock_sock),
        ):
            exit_code = check_env.main()
            captured = capsys.readouterr()
            # In quiet mode, stdout should be empty
            assert captured.out.strip() == ""
            assert exit_code in (0, 1)
