"""
Tests for Ollama LLM Client (core/ollama.py)
============================================
Covers Tiers 1 and 2:
- OllamaClient initialization and configuration
- Connection checking via GET /api/tags
- Model listing and sorting
- Dialogue generation request formatting (/api/chat & /api/generate)
- Timeout, HTTP error, and connection failure handling
- generate_podcast_script integration with parser
"""

import json
import socket
import urllib.error
import pytest
from unittest.mock import patch, MagicMock

try:
    from core.ollama import OllamaClient, generate_podcast_script
    from core.parser import DialogueTurn
except ImportError:
    pass


class TestOllamaClientUnit:
    """Tier 1: Feature tests for Ollama client."""

    def test_client_init_defaults(self):
        from core.ollama import OllamaClient
        client = OllamaClient()
        assert "11434" in client.base_url

    def test_client_init_custom_url(self):
        from core.ollama import OllamaClient
        client = OllamaClient("http://remote-gpu:11434/")
        assert client.base_url == "http://remote-gpu:11434"

    def test_check_connection_success(self):
        from core.ollama import OllamaClient
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = OllamaClient()
            assert client.check_connection() is True

    def test_check_connection_failure(self):
        from core.ollama import OllamaClient
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            client = OllamaClient()
            assert client.check_connection() is False

    def test_list_models_success(self, mock_ollama_tags_data):
        from core.ollama import OllamaClient
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
        from core.ollama import OllamaClient
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_ollama_empty_tags).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = OllamaClient()
            models = client.list_models()
            assert models == []


class TestOllamaGenerationAndErrors:
    """Tier 2: Request payload generation and failure handling."""

    def test_generate_dialogue_via_chat_endpoint(self, sample_norwegian_turns):
        from core.ollama import OllamaClient
        dialogue_json = json.dumps([{"speaker": t.speaker, "text": t.text} for t in sample_norwegian_turns])
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
                    prompt="Lag et podcast-manus..."
                )
            else:
                result = client.generate_dialogue(
                    model="llama3.1:8b",
                    system_prompt="Du er en podcast-forfatter...",
                    user_prompt="Lag et podcast-manus..."
                )
            assert "Host 1" in result

    def test_generate_dialogue_fallback_to_generate_endpoint(self, sample_english_turns):
        from core.ollama import OllamaClient
        dialogue_json = json.dumps([{"speaker": t.speaker, "text": t.text} for t in sample_english_turns])
        gen_response = {"response": dialogue_json}

        # First call to /api/chat raises HTTPError 404, second call to /api/generate succeeds
        mock_chat_err = urllib.error.HTTPError("http://localhost:11434/api/chat", 404, "Not Found", {}, None)
        mock_gen_resp = MagicMock()
        mock_gen_resp.status = 200
        mock_gen_resp.read.return_value = json.dumps(gen_response).encode("utf-8")
        mock_gen_resp.__enter__.return_value = mock_gen_resp

        with patch("urllib.request.urlopen", side_effect=[mock_chat_err, mock_gen_resp]):
            client = OllamaClient()
            result = client.generate(
                model="llama3.1:8b",
                system="You are a podcast writer...",
                prompt="Create a script..."
            )
            assert "Host 1" in result

    def test_generate_dialogue_timeout_error(self):
        from core.ollama import OllamaClient
        with patch("urllib.request.urlopen", side_effect=socket.timeout()):
            client = OllamaClient()
            with pytest.raises(Exception) as exc_info:
                client.generate(model="llama3.1:8b", system="", prompt="")
            assert "timeout" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower()

    def test_generate_dialogue_connection_refused_error(self):
        from core.ollama import OllamaClient
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            client = OllamaClient()
            with pytest.raises(Exception):
                client.generate(model="llama3.1:8b", system="", prompt="")

    def test_generate_podcast_script_integration(self, sample_english_turns):
        from core.ollama import generate_podcast_script
        dialogue_json = json.dumps([{"speaker": t.speaker, "text": t.text} for t in sample_english_turns])
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
                model="llama3.1:8b"
            )
            assert len(turns) == len(sample_english_turns)
            assert turns[0].speaker == "Host 1"
            assert "Welcome back" in turns[0].text

    def test_generate_podcast_script_multi_act_extended(self):
        from core.ollama import generate_podcast_script
        act_turns = [
            {"speaker": "Host 1", "text": "Del en replikk."},
            {"speaker": "Host 2", "text": "Del to replikk."}
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
                model="mistral-nemo:latest",
                progress_callback=lambda msg: progress_messages.append(msg)
            )
            # Extended in-depth has 5 acts, 2 turns each mock -> 10 turns
            assert len(turns) == 10
            assert any("Act 1" in m or "Akt 1" in m for m in progress_messages)
            assert any("Act 5" in m or "Akt 5" in m for m in progress_messages)
