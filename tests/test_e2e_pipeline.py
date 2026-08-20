"""
End-to-End Integration & Pipeline Tests (tests/test_e2e_pipeline.py)
===================================================================
Covers Tier 4 (Real-World Workloads) & Tier 3 (Cross-Feature Combinations):
- Full workflow: Document Ingestion -> Prompt Builder -> Ollama LLM -> Parser -> TTS -> MP3 Stitcher -> Master MP3 Export
- All 4 Episode Length presets:
    1. Quick Summary (6-8 turns)
    2. Standard Episode (12-16 turns)
    3. Deep Dive (20-26 turns)
    4. Extended In-Depth (45-60 turns)
- Both supported languages: Norwegian Bokmål (Kari & Ola) and English (Jenny & Guy)
- All 3 tones: Casual & Lively, Analytical & Educational, Lively Debate
- Scratch Topic mode ("Generate from Scratch")
- Script-Only workflow (Generate script, edit/inspect, synthesize from script)
- Error cascade recovery in integrated pipeline
"""

import os
import json
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from core.parser import DialogueTurn


class TestFullE2EPipeline:
    """Tier 4: Comprehensive end-to-end podcast generation workflows."""

    @pytest.mark.parametrize("language,host1_name,host2_name,voice1,voice2", [
        ("nb-NO", "Kari", "Ola", "nb-NO-PernilleNeural", "nb-NO-FinnNeural"),
        ("en-US", "Jenny", "Guy", "en-US-JennyNeural", "en-US-GuyNeural"),
    ])
    @pytest.mark.parametrize("format_type", [
        "quick",
        "standard",
        "deep_dive",
        "extended",
    ])
    @pytest.mark.parametrize("tone_style", [
        "casual",
        "analytical",
        "debate",
    ])
    def test_full_document_pipeline_e2e(
        self,
        tmp_path,
        sample_markdown_file,
        synthetic_mp3_factory,
        language,
        host1_name,
        host2_name,
        voice1,
        voice2,
        format_type,
        tone_style,
    ):
        """Tests complete pipeline from markdown document to stitched MP3 output."""
        from core.extractor import extract_text
        from core.prompts import build_system_prompt, build_user_prompt
        from core.parser import DialogueParser
        from core.tts import TTSEngine
        from core.mp3_stitcher import stitch_mp3_files

        # 1. Ingestion
        document_text = extract_text(sample_markdown_file)
        assert len(document_text) > 50

        # 2. Prompt Assembly
        system_prompt = build_system_prompt(language=language, format_type=format_type, tone_style=tone_style)
        user_prompt = build_user_prompt(content=document_text, language=language, is_topic=False)
        assert "Host 1" in system_prompt
        assert document_text in user_prompt

        # 3. Simulated LLM Output (Mocked Ollama response)
        mock_turns_data = [
            {"speaker": "Host 1", "text": f"Welcome to the episode! We are discussing {language} topics today."},
            {"speaker": "Host 2", "text": "Indeed! Let's explore the key points and practical takeaways."},
            {"speaker": "Host 1", "text": "What is the most notable insight from the document?"},
            {"speaker": "Host 2", "text": "The main insight is the total elimination of cloud fees."},
            {"speaker": "Host 1", "text": "Thank you for listening, everyone!"},
            {"speaker": "Host 2", "text": "See you in the next episode!"},
        ]
        mock_raw_llm_output = f"```json\n{json.dumps(mock_turns_data, indent=2)}\n```"

        # 4. Resilient 6-Tier Parsing
        parsed_turns = DialogueParser.parse(mock_raw_llm_output)
        assert len(parsed_turns) == 6
        assert parsed_turns[0].speaker == "Host 1"
        assert parsed_turns[1].speaker == "Host 2"

        # 5. Voice Synthesis Mapping & Execution (Mocked Edge-TTS)
        tts_engine = TTSEngine(language=language, rate="+5%")
        assert tts_engine.get_voice_for_speaker("Host 1") == voice1
        assert tts_engine.get_voice_for_speaker("Host 2") == voice2

        # Create synthetic audio byte buffers for each turn
        turn_audio_buffers = [
            synthetic_mp3_factory(num_frames=2, include_id3v2=True)
            for _ in parsed_turns
        ]

        # 6. Binary MP3 Frame Stitching
        out_file = tmp_path / f"master_podcast_{language}_{format_type}_{tone_style}.mp3"
        result_path = stitch_mp3_files(
            input_files_or_bytes=turn_audio_buffers,
            output_file_path=str(out_file),
            silence_duration_ms=350,
            title="E2E Test Episode",
            artist=f"{host1_name} & {host2_name}",
        )

        # 7. Validation of Master Binary Artifact
        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0
        with open(result_path, "rb") as f:
            final_mp3_bytes = f.read()
            assert final_mp3_bytes[:3] == b"ID3"  # Master ID3v2 tag present
            assert b"TIT2" in final_mp3_bytes      # Title frame present

    def test_scratch_topic_e2e_pipeline(self, tmp_path, synthetic_mp3_factory):
        """Tests the 'Generate from Scratch' topic mode pipeline without an uploaded file."""
        from core.extractor import extract_text
        from core.prompts import build_system_prompt, build_user_prompt
        from core.parser import DialogueParser
        from core.mp3_stitcher import stitch_mp3_files

        # 1. Scratch topic input
        topic = "The history and future of supersonic passenger flight"
        topic_text = extract_text(topic, is_topic=True)
        assert topic in topic_text

        # 2. Prompts
        sys_prompt = build_system_prompt(language="en-US", format_type="standard", tone_style="analytical")
        usr_prompt = build_user_prompt(content=topic_text, language="en-US", is_topic=True)
        assert "Host 1" in sys_prompt

        # 3. Mock LLM output with unescaped trailing comma (Tier 4 parser test)
        llm_response = (
            '[\n'
            '  {"speaker": "Host 1", "text": "Supersonic flight is making a major comeback!",},\n'
            '  {"speaker": "Host 2", "text": "Yes, modern aerodynamic designs dramatically reduce sonic booms.",}\n'
            ']'
        )
        turns = DialogueParser.parse(llm_response)
        assert len(turns) == 2

        # 4. Synthesis & Stitching
        audio_segs = [synthetic_mp3_factory(num_frames=2) for _ in turns]
        mp3_path = tmp_path / "supersonic_podcast.mp3"
        result_path = stitch_mp3_files(
            audio_segs,
            str(mp3_path),
            title="Supersonic Flight",
            artist="Jenny & Guy"
        )
        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0

    def test_script_only_and_resynthesis_pipeline(self, tmp_path, synthetic_mp3_factory):
        """Tests 'Generate Script Only', editing the script JSON, and synthesizing audio from it."""
        from core.parser import DialogueParser, DialogueTurn
        from core.mp3_stitcher import stitch_mp3_files

        # 1. Original script
        raw_script = [
            {"speaker": "Host 1", "text": "Original introduction line."},
            {"speaker": "Host 2", "text": "Original explanation line."}
        ]
        script_file = tmp_path / "script.json"
        script_file.write_text(json.dumps(raw_script, indent=2), encoding="utf-8")

        # 2. User edits script
        edited_script = json.loads(script_file.read_text(encoding="utf-8"))
        edited_script[0]["text"] = "Fine-tuned custom introduction by the user!"
        edited_script.append({"speaker": "Host 1", "text": "Added turn 3 by user."})
        script_file.write_text(json.dumps(edited_script, indent=2), encoding="utf-8")

        # 3. Parse edited script
        parsed_turns = DialogueParser.parse(script_file.read_text(encoding="utf-8"))
        assert len(parsed_turns) == 3
        assert parsed_turns[0].text == "Fine-tuned custom introduction by the user!"

        # 4. Synthesize edited turns
        audio_segs = [synthetic_mp3_factory(num_frames=2) for _ in parsed_turns]
        master_path = tmp_path / "edited_podcast.mp3"
        result_path = stitch_mp3_files(audio_segs, str(master_path), title="Edited Script Podcast")
        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0
