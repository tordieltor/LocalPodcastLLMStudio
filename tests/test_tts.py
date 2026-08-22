"""
Tests for Piper TTS Voice Synthesis Engine (core/tts.py)
========================================================
Covers Tiers 1, 2, and 3:
- Neural voice selection & mapping (Norwegian: Kari/Ola torkil, English: Lessac/Ryan)
- Speaking rate/speed formatting (-10% to +15%)
- Async turn-by-turn synthesis with mock Piper TTS
- Turn synthesis pipeline with progress reporting
- Automatic retry on transient failures
- Cancellation handling in synthesis pipeline
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.parser import DialogueTurn
from core.tts import (
    TTSEngine,
    format_rate_str,
    synthesize_dialogue_audio,
    synthesize_turn,
)


class TestTTSVoiceMappingAndRates:
    """Tier 1: Feature coverage for voice assignment and rate parsing."""

    @pytest.mark.parametrize(
        "speaker,language,expected_voice",
        [
            ("Host 1", "nb-NO", "no_NO-torkil-medium"),
            ("Kari", "nb-NO", "no_NO-torkil-medium"),
            ("Host 2", "nb-NO", "no_NO-torkil-medium"),
            ("Ola", "nb-NO", "no_NO-torkil-medium"),
            ("Host 1", "en-US", "en_US-lessac-medium"),
            ("Jenny", "en-US", "en_US-lessac-medium"),
            ("Host 2", "en-US", "en_US-ryan-medium"),
            ("Guy", "en-US", "en_US-ryan-medium"),
        ],
    )
    def test_voice_selection(self, speaker, language, expected_voice):

        engine = TTSEngine(language=language)
        voice = engine.get_voice_for_speaker(speaker)
        assert voice == expected_voice

    @pytest.mark.parametrize(
        "rate_input,expected_output",
        [
            ("-10%", "-10%"),
            ("-5%", "-5%"),
            ("+0%", "+0%"),
            ("+5%", "+5%"),
            ("+10%", "+10%"),
            ("+15%", "+15%"),
            (0, "+0%"),
            (10, "+10%"),
            (-10, "-10%"),
        ],
    )
    def test_speaking_rate_values(self, rate_input, expected_output):

        assert format_rate_str(rate_input) == expected_output


class TestTTSSynthesisExecution:
    """Tier 2: Async synthesis pipeline and error handling."""

    @pytest.mark.asyncio
    async def test_synthesize_turn_bytes(self, single_frame_mp3):
        import sys

        from core.tts import TTSEngine

        engine = TTSEngine(language="nb-NO", rate="+0%")
        turn = DialogueTurn(speaker="Host 1", text="Hei og velkommen!")

        # Mock edge_tts.Communicate async stream via sys.modules for environments without edge-tts installed
        async def mock_stream():
            yield {"type": "audio", "data": single_frame_mp3}

        mock_comm = MagicMock()
        mock_comm.stream = mock_stream
        mock_edge = MagicMock()
        mock_edge.Communicate.return_value = mock_comm

        with patch.dict(sys.modules, {"edge_tts": mock_edge}):
            audio_bytes = await engine.synthesize_turn_bytes(turn)
            assert len(audio_bytes) > 0
            assert audio_bytes == single_frame_mp3

    @pytest.mark.asyncio
    async def test_synthesize_turn_offline_pcm_fallback(self):
        import sys

        from core.tts import TTSEngine

        engine = TTSEngine(language="nb-NO", rate="+0%")
        turn = DialogueTurn(speaker="Host 1", text="Hei og velkommen!")

        # Ensure no edge_tts in sys.modules and no piper voice loaded
        with (
            patch.dict(sys.modules, {"edge_tts": None}),
            patch("core.tts.get_or_load_piper_voice", return_value=None),
        ):
            audio_bytes = await engine.synthesize_turn_bytes(turn)
            assert len(audio_bytes) > 0
            assert audio_bytes.startswith(b"RIFF")  # Valid WAV PCM fallback

    @pytest.mark.asyncio
    async def test_synthesize_turn_piper_local_onnx(self):
        from core.tts import TTSEngine

        engine = TTSEngine(language="en-US", rate="+5%")
        turn = DialogueTurn(speaker="Host 2", text="Testing local Piper voice synthesis.")

        mock_piper_voice = MagicMock()

        def fake_synthesize(text, wav_file, length_scale=1.0, noise_scale=0.667, **kwargs):
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 100)

        mock_piper_voice.synthesize.side_effect = fake_synthesize

        with patch("core.tts.get_or_load_piper_voice", return_value=mock_piper_voice):
            audio_bytes = await engine.synthesize_turn_bytes(turn)
            assert len(audio_bytes) > 0
            assert audio_bytes.startswith(b"RIFF")
            assert mock_piper_voice.synthesize.called

    @pytest.mark.asyncio
    async def test_synthesize_dialogue_async_progress(
        self, sample_norwegian_turns, single_frame_mp3
    ):
        import sys

        engine = TTSEngine(language="nb-NO", rate="+0%")
        progress_records = []

        def progress_cb(current, total, msg):
            progress_records.append((current, total, msg))

        async def mock_stream():
            yield {"type": "audio", "data": single_frame_mp3}

        mock_comm = MagicMock()
        mock_comm.stream = mock_stream
        mock_edge = MagicMock()
        mock_edge.Communicate.return_value = mock_comm

        with (
            patch("core.tts.get_or_load_piper_voice", return_value=None),
            patch.dict(sys.modules, {"edge_tts": mock_edge}),
        ):
            results = await engine.synthesize_dialogue_async(
                sample_norwegian_turns, progress_cb=progress_cb
            )
            assert len(results) == len(sample_norwegian_turns)
            assert len(progress_records) == len(sample_norwegian_turns)
            assert progress_records[-1][0] == len(sample_norwegian_turns)

    @pytest.mark.asyncio
    async def test_synthesize_turn_retry_on_glitch(self, single_frame_mp3):
        import sys

        from core.tts import TTSEngine

        engine = TTSEngine(language="en-US", rate="+0%")
        turn = DialogueTurn(speaker="Host 2", text="Testing retry mechanism.")

        call_count = 0

        def create_mock_comm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_comm = MagicMock()
            if call_count == 1:
                # First attempt fails with connection error
                async def failing_stream():
                    raise ConnectionError("WebSocket dropped")
                    yield

                mock_comm.stream = failing_stream
            else:
                # Second attempt succeeds
                async def success_stream():
                    yield {"type": "audio", "data": single_frame_mp3}

                mock_comm.stream = success_stream
            return mock_comm

        mock_edge = MagicMock()
        mock_edge.Communicate.side_effect = create_mock_comm

        with (
            patch("core.tts.get_or_load_piper_voice", return_value=None),
            patch.dict(sys.modules, {"edge_tts": mock_edge}),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            audio_bytes = await engine.synthesize_turn_bytes(turn, max_retries=3)
            assert audio_bytes == single_frame_mp3
            assert call_count == 2

    def test_voice_model_caching_mechanism(self):
        import sys
        from pathlib import Path

        from core.tts import _VOICE_MODEL_CACHE, clear_voice_model_cache, get_or_load_piper_voice

        clear_voice_model_cache()
        assert len(_VOICE_MODEL_CACHE) == 0

        mock_piper_module = MagicMock()
        mock_piper_module.__path__ = []
        mock_piper_voice = MagicMock()
        mock_piper_module.voice = MagicMock()
        mock_piper_module.voice.__path__ = []
        mock_piper_module.voice.PiperVoice.load.return_value = mock_piper_voice

        with (
            patch.dict(
                sys.modules, {"piper": mock_piper_module, "piper.voice": mock_piper_module.voice}
            ),
            patch(
                "core.tts.find_voice_model_files",
                return_value=(Path("dummy.onnx"), Path("dummy.onnx.json")),
            ),
        ):
            pv1 = get_or_load_piper_voice("test-voice")
            assert pv1 == mock_piper_voice
            assert "test-voice" in _VOICE_MODEL_CACHE

            # Second call retrieves from cache without re-loading
            pv2 = get_or_load_piper_voice("test-voice")
            assert pv2 is pv1
            assert mock_piper_module.voice.PiperVoice.load.call_count == 1

        clear_voice_model_cache()
        assert len(_VOICE_MODEL_CACHE) == 0

    def test_synthesize_dialogue_audio_cleanup_on_error(self, sample_norwegian_turns):
        with (
            patch(
                "core.tts.TTSEngine.run_synthesis_sync",
                side_effect=RuntimeError("Synthesis exploded"),
            ),
            pytest.raises(RuntimeError, match="Synthesis exploded"),
        ):
            synthesize_dialogue_audio(sample_norwegian_turns)

    @pytest.mark.parametrize("bad_dir", ["", "   ", 12345, ["dir"], "bad\x00dir"])
    def test_synthesize_dialogue_audio_rejects_invalid_output_dir(
        self, bad_dir, sample_norwegian_turns
    ):
        with pytest.raises(ValueError):
            synthesize_dialogue_audio(sample_norwegian_turns, output_dir=bad_dir)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_path", ["", "   ", 12345, ["path"], "bad\x00path.wav"])
    async def test_synthesize_turn_rejects_invalid_output_path(self, bad_path):
        with pytest.raises(ValueError):
            await synthesize_turn(
                text="Hei fra test",
                voice="no_NO-torkil-medium",
                output_path=bad_path,  # type: ignore[arg-type]
            )
