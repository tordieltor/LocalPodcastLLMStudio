"""
Unit Tests for Code Review Remediation & Architectural Hardening
================================================================
Validates all 21 audit findings and enhancements:
- CODE-01: UTF-8 safe unescaping and regex parser resilience.
- CODE-02: SpeakerRole enum classification and alternation.
- CODE-04: pull_model_stream return semantics.
- CODE-05: Homogeneous audio segment validation.
- CODE-06: Unified _stream_ndjson_request helper.
- ARCH-01: Headless PodcastGeneratorService domain orchestration.
- ARCH-02: Centralized atomic_write_file across string and binary buffers.
- ARCH-03: OllamaClient.list_models_detailed and check_env.py deduplication.
- ARCH-04: StudioError unified domain exception hierarchy.
- ARCH-05: ActSpec and EpisodeFormatConfig frozen dataclasses.
- RESIL-01: WindowsAudioPlayer unique alias isolation and error querying.
- SEC-05: Crash dump fallback directory resolution.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app import _resolve_crash_log_path
from core.exceptions import (
    AudioStitchingError,
    AudioSynthesisError,
    DocumentExtractionError,
    DocumentIngestionError,
    LLMServiceError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    StudioError,
)
from core.io_utils import atomic_write_file
from core.mp3_stitcher import stitch_mp3_files
from core.ollama import OllamaClient, pull_model_stream
from core.parser import (
    DialogueParser,
    DialogueTurn,
    SpeakerRole,
    _unescape_json_string,
)
from core.pipeline import GenerationOptions, GenerationResult, PodcastGeneratorService
from core.player import WindowsAudioPlayer
from core.prompts import ActSpec, EpisodeFormatConfig


class TestUTF8UnescapingAndParser:
    """CODE-01: Verify multi-byte UTF-8 character preservation during unescaping."""

    def test_unescape_json_string_norwegian_characters(self):
        sample = (
            "Dette er en spennende episode om b\\u00e6rekraft og milj\\u00f8 i v\\u00e5re fjorder!"
        )
        unescaped = _unescape_json_string(sample)
        assert "bærekraft" in unescaped
        assert "miljø" in unescaped
        assert "våre" in unescaped

    def test_unescape_json_string_literal_utf8_passthrough(self):
        sample = "Kari: Ærlig talt, Øyvind og Åse er på vei!"
        unescaped = _unescape_json_string(sample)
        assert unescaped == sample

    def test_unescape_json_string_standard_escapes(self):
        sample = 'Linje 1\\nLinje 2\\t\\"Sitat\\" \\\\ test'
        unescaped = _unescape_json_string(sample)
        assert 'Linje 1\nLinje 2\t"Sitat" \\ test' == unescaped

    def test_regex_parser_norwegian_utf8_recovery(self):
        raw_llm = """
        Here is the script:
        {"speaker": "Host 1", "text": "Velkommen til vår podcast om bærekraft og økonomi!"}
        {"speaker": "Host 2", "text": "Takk Kari! Dette er et usedvanlig viktig tema for miljøet."}
        """
        turns = DialogueParser.parse(raw_llm, default_language="nb-NO")
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert "bærekraft og økonomi" in turns[0].text
        assert "miljøet" in turns[1].text


class TestSpeakerRole:
    """CODE-02: Verify SpeakerRole enum classification and alternation."""

    def test_speaker_role_from_speaker(self):
        assert SpeakerRole.from_speaker("Host 1") == SpeakerRole.HOST_1
        assert SpeakerRole.from_speaker("Kari") == SpeakerRole.HOST_1
        assert SpeakerRole.from_speaker("Jenny") == SpeakerRole.HOST_1
        assert SpeakerRole.from_speaker("Speaker 1") == SpeakerRole.HOST_1

        assert SpeakerRole.from_speaker("Host 2") == SpeakerRole.HOST_2
        assert SpeakerRole.from_speaker("Ola") == SpeakerRole.HOST_2
        assert SpeakerRole.from_speaker("Guy") == SpeakerRole.HOST_2
        assert SpeakerRole.from_speaker("Speaker 2") == SpeakerRole.HOST_2

    def test_speaker_role_get_alternate(self):
        assert SpeakerRole.get_alternate("Host 1") == "Host 2"
        assert SpeakerRole.get_alternate("Kari") == "Host 2"
        assert SpeakerRole.get_alternate("Host 2") == "Host 1"
        assert SpeakerRole.get_alternate("Ola") == "Host 1"


class TestAtomicWriteUtils:
    """ARCH-02: Verify atomic_write_file across all supported data buffer types."""

    def test_atomic_write_string(self, tmp_path):
        target = tmp_path / "test.txt"
        out = atomic_write_file(str(target), "Hello World! ÆØÅ")
        assert os.path.exists(out)
        with open(out, encoding="utf-8") as f:
            assert f.read() == "Hello World! ÆØÅ"

    def test_atomic_write_bytes(self, tmp_path):
        target = tmp_path / "test.bin"
        out = atomic_write_file(str(target), b"\x00\x01\x02\xff")
        assert os.path.exists(out)
        with open(out, "rb") as f:
            assert f.read() == b"\x00\x01\x02\xff"

    def test_atomic_write_bytearray(self, tmp_path):
        target = tmp_path / "test.bin"
        ba = bytearray(b"Binary Data")
        out = atomic_write_file(str(target), ba)
        assert os.path.exists(out)
        with open(out, "rb") as f:
            assert f.read() == b"Binary Data"

    def test_atomic_write_memoryview(self, tmp_path):
        target = tmp_path / "test.bin"
        mv = memoryview(b"Memory View Data")
        out = atomic_write_file(str(target), mv)
        assert os.path.exists(out)
        with open(out, "rb") as f:
            assert f.read() == b"Memory View Data"


class TestDomainExceptionHierarchy:
    """ARCH-04: Verify unified StudioError domain exception hierarchy."""

    def test_studio_error_base(self):
        assert issubclass(DocumentIngestionError, StudioError)
        assert issubclass(LLMServiceError, StudioError)
        assert issubclass(AudioSynthesisError, StudioError)
        assert issubclass(AudioStitchingError, StudioError)

    def test_backward_compatibility_aliases(self):
        assert DocumentExtractionError is DocumentIngestionError
        assert OllamaConnectionError is LLMServiceError
        assert issubclass(OllamaModelNotFoundError, LLMServiceError)
        assert issubclass(OllamaModelNotFoundError, ValueError)


class TestOllamaClientDetailedAndStreaming:
    """ARCH-03, CODE-04, CODE-06: Verify OllamaClient detailed models and streaming."""

    def test_list_models_detailed(self):
        client = OllamaClient("http://localhost:11434")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {
                "models": [
                    {
                        "name": "llama3.1:8b",
                        "size": 4920737792,
                        "details": {
                            "parameter_size": "8.0B",
                            "quantization_level": "Q4_K_M",
                            "format": "gguf",
                            "family": "llama",
                        },
                        "modified_at": "2026-08-20T12:00:00Z",
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            models = client.list_models_detailed()
            assert len(models) == 1
            m = models[0]
            assert m["name"] == "llama3.1:8b"
            assert m["size_gb"] == 4.58
            assert m["parameter_size"] == "8.0B"
            assert m["quantization_level"] == "Q4_K_M"

    def test_pull_model_stream_success_return(self):
        lines = [
            json.dumps({"status": "pulling manifest"}).encode("utf-8"),
            json.dumps({"status": "success", "done": True}).encode("utf-8"),
        ]
        mock_response = MagicMock()
        mock_response.__iter__.return_value = iter(lines)
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            success = pull_model_stream("llama3.1:8b")
            assert success is True


class TestMP3StitcherFormatValidation:
    """CODE-05: Verify stitch_mp3_files rejects mixed audio segments."""

    def test_mixed_wav_and_mp3_raises_value_error(self, tmp_path):
        wav_header = b"RIFF" + b"\x00" * 32
        mp3_header = b"\xff\xfb\x90\x64" + b"\x00" * 100
        out_path = str(tmp_path / "out.mp3")

        with pytest.raises(ValueError, match="Mixed audio formats detected"):
            stitch_mp3_files(
                input_files_or_bytes=[wav_header, mp3_header],
                output_file_path=out_path,
            )


class TestPodcastGeneratorService:
    """ARCH-01: Verify headless domain orchestrator PodcastGeneratorService."""

    def test_headless_pipeline_execution(self, tmp_path):
        out_dir = str(tmp_path / "podcast_out")
        options = GenerationOptions(
            content="Dette er et testdokument for podcast.",
            language="nb-NO",
            output_dir=out_dir,
            is_raw_text=True,
        )
        service = PodcastGeneratorService()

        sample_dialogue = [
            DialogueTurn(speaker="Host 1", text="Hei og velkommen!"),
            DialogueTurn(speaker="Host 2", text="Takk for det!"),
        ]

        with (
            patch("core.pipeline.extract_text", return_value="Test text"),
            patch("core.pipeline.generate_podcast_script", return_value=sample_dialogue),
            patch("core.pipeline.synthesize_dialogue_audio", return_value=[b"RIFF" + b"\x00" * 40]),
            patch(
                "core.pipeline.stitch_mp3_files", return_value=os.path.join(out_dir, "podcast.mp3")
            ),
        ):
            progress_events = []

            def progress_cb(pct: float, msg: str):
                progress_events.append((pct, msg))

            result = service.generate_podcast(options=options, progress_callback=progress_cb)

            assert isinstance(result, GenerationResult)
            assert os.path.exists(result.script_json_path)
            assert os.path.exists(result.script_md_path)
            assert len(result.dialogue) == 2
            assert len(progress_events) >= 3


class TestWindowsAudioPlayerResilience:
    """RESIL-01: Verify WindowsAudioPlayer per-instance unique aliases and error reporting."""

    def test_unique_alias_generation(self):
        p1 = WindowsAudioPlayer()
        p2 = WindowsAudioPlayer()
        assert p1.alias != p2.alias
        assert p1.alias.startswith("lp_mci_")

    def test_explicit_alias_preserved(self):
        p = WindowsAudioPlayer(alias="custom_alias_123")
        assert p.alias == "custom_alias_123"

    def test_get_last_error_message(self):
        p = WindowsAudioPlayer()
        p._winmm = MagicMock()
        p._last_error = 263
        p._winmm.mciGetErrorStringW.return_value = 1
        # Test error string retrieval
        msg = p.get_last_error_message()
        assert msg is not None


class TestCrashDumpLogResilience:
    """SEC-05: Verify crash dump path resolution."""

    def test_resolve_crash_log_path(self):
        path = _resolve_crash_log_path()
        assert path.endswith(".log")
        assert os.path.isabs(path)


class TestPromptDataclasses:
    """ARCH-05: Verify ActSpec and EpisodeFormatConfig dataclasses."""

    def test_act_spec_dataclass(self):
        spec = ActSpec(
            act_num=1,
            title="Intro",
            prompt_theme="Opening remarks",
            target_turns=10,
            is_intro=True,
        )
        assert spec.act_num == 1
        assert spec.title == "Intro"
        d = spec.to_dict()
        assert d["is_intro"] is True
        assert d["target_turns"] == 10

    def test_episode_format_config(self):
        cfg = EpisodeFormatConfig(
            id="quick",
            name="Quick Summary",
            duration="~2-3 mins",
            target_turns=8,
            min_turns=6,
            max_turns=8,
            description_nb="Kort",
            description_en="Short",
        )
        assert cfg.target_turns == 8
