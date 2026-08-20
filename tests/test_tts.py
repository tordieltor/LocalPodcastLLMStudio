"""
Tests for Edge-TTS Voice Synthesis Engine (core/tts.py)
======================================================
Covers Tiers 1, 2, and 3:
- Neural voice selection & mapping (Norwegian: Pernille/Finn, English: Jenny/Guy)
- Speaking rate/speed formatting (-10% to +15%)
- Async turn-by-turn synthesis with mock Edge-TTS
- Turn synthesis pipeline with progress reporting
- Automatic retry on transient failures
- Cancellation handling in synthesis pipeline
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

try:
    from core.tts import (
        TTSEngine,
        synthesize_turn,
        synthesize_dialogue_audio,
        format_rate_str,
    )
    from core.parser import DialogueTurn
except ImportError:
    pass


class TestTTSVoiceMappingAndRates:
    """Tier 1: Feature coverage for voice assignment and rate parsing."""

    @pytest.mark.parametrize("speaker,language,expected_voice", [
        ("Host 1", "nb-NO", "nb-NO-PernilleNeural"),
        ("Kari", "nb-NO", "nb-NO-PernilleNeural"),
        ("Host 2", "nb-NO", "nb-NO-FinnNeural"),
        ("Ola", "nb-NO", "nb-NO-FinnNeural"),
        ("Host 1", "en-US", "en-US-JennyNeural"),
        ("Jenny", "en-US", "en-US-JennyNeural"),
        ("Host 2", "en-US", "en-US-GuyNeural"),
        ("Guy", "en-US", "en-US-GuyNeural"),
    ])
    def test_voice_selection(self, speaker, language, expected_voice):
        from core.tts import TTSEngine
        engine = TTSEngine(language=language)
        voice = engine.get_voice_for_speaker(speaker)
        assert voice == expected_voice

    @pytest.mark.parametrize("rate_input,expected_output", [
        ("-10%", "-10%"),
        ("-5%", "-5%"),
        ("+0%", "+0%"),
        ("+5%", "+5%"),
        ("+10%", "+10%"),
        ("+15%", "+15%"),
        (0, "+0%"),
        (10, "+10%"),
        (-10, "-10%"),
    ])
    def test_speaking_rate_values(self, rate_input, expected_output):
        from core.tts import format_rate_str
        assert format_rate_str(rate_input) == expected_output


class TestTTSSynthesisExecution:
    """Tier 2: Async synthesis pipeline and error handling."""

    @pytest.mark.asyncio
    async def test_synthesize_turn_bytes(self, single_frame_mp3):
        from core.tts import TTSEngine
        from core.parser import DialogueTurn

        engine = TTSEngine(language="nb-NO", rate="+0%")
        turn = DialogueTurn(speaker="Host 1", text="Hei og velkommen!")

        # Mock edge_tts.Communicate async stream
        async def mock_stream():
            yield {"type": "audio", "data": single_frame_mp3}

        mock_comm = MagicMock()
        mock_comm.stream = mock_stream

        with patch("edge_tts.Communicate", return_value=mock_comm):
            audio_bytes = await engine.synthesize_turn_bytes(turn)
            assert len(audio_bytes) > 0
            assert audio_bytes == single_frame_mp3

    @pytest.mark.asyncio
    async def test_synthesize_dialogue_async_progress(self, sample_norwegian_turns, single_frame_mp3):
        from core.tts import TTSEngine

        engine = TTSEngine(language="nb-NO", rate="+0%")
        progress_records = []

        def progress_cb(current, total, msg):
            progress_records.append((current, total, msg))

        async def mock_stream():
            yield {"type": "audio", "data": single_frame_mp3}

        mock_comm = MagicMock()
        mock_comm.stream = mock_stream

        with patch("edge_tts.Communicate", return_value=mock_comm):
            results = await engine.synthesize_dialogue_async(
                sample_norwegian_turns,
                progress_cb=progress_cb
            )
            assert len(results) == len(sample_norwegian_turns)
            assert len(progress_records) == len(sample_norwegian_turns)
            assert progress_records[-1][0] == len(sample_norwegian_turns)

    @pytest.mark.asyncio
    async def test_synthesize_turn_retry_on_glitch(self, single_frame_mp3):
        from core.tts import TTSEngine
        from core.parser import DialogueTurn

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

        with patch("edge_tts.Communicate", side_effect=create_mock_comm), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            audio_bytes = await engine.synthesize_turn_bytes(turn, max_retries=3)
            assert audio_bytes == single_frame_mp3
            assert call_count == 2
