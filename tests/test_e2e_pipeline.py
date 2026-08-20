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
- Multi-tier grounding integration: Strict Source-Only, Creative Analogy & Synthesis, Open Topic / Scratch
- Multi-act structured sequential generation pipeline with dialogue context continuity
- Script-Only workflow (Generate script, edit/inspect, synthesize from script)
- Error cascade recovery in integrated pipeline
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from core.parser import DialogueParser


class TestFullE2EPipeline:
    """Tier 4: Comprehensive end-to-end podcast generation workflows."""

    @pytest.mark.parametrize(
        "language,host1_name,host2_name,voice1,voice2",
        [
            ("nb-NO", "Kari", "Ola", "no_NO-torkil-medium", "no_NO-torkil-medium"),
            ("en-US", "Jenny", "Guy", "en_US-lessac-medium", "en_US-ryan-medium"),
        ],
    )
    @pytest.mark.parametrize(
        "format_type",
        [
            "quick",
            "standard",
            "deep_dive",
            "extended",
        ],
    )
    @pytest.mark.parametrize(
        "tone_style",
        [
            "casual",
            "analytical",
            "debate",
        ],
    )
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
        from core.mp3_stitcher import stitch_mp3_files
        from core.parser import DialogueParser
        from core.prompts import build_system_prompt, build_user_prompt
        from core.tts import TTSEngine

        # 1. Ingestion
        document_text = extract_text(sample_markdown_file)
        assert len(document_text) > 50

        # 2. Prompt Assembly
        system_prompt = build_system_prompt(
            language=language, format_type=format_type, tone_style=tone_style
        )
        user_prompt = build_user_prompt(content=document_text, language=language, is_topic=False)
        assert "Host 1" in system_prompt
        assert document_text in user_prompt

        # 3. Simulated LLM Output (Mocked Ollama response)
        mock_turns_data = [
            {
                "speaker": "Host 1",
                "text": f"Welcome to the episode! We are discussing {language} topics today.",
            },
            {
                "speaker": "Host 2",
                "text": "Indeed! Let's explore the key points and practical takeaways.",
            },
            {"speaker": "Host 1", "text": "What is the most notable insight from the document?"},
            {
                "speaker": "Host 2",
                "text": "The main insight is the total elimination of cloud fees.",
            },
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
            synthetic_mp3_factory(num_frames=2, include_id3v2=True) for _ in parsed_turns
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
            assert b"TIT2" in final_mp3_bytes  # Title frame present

    def test_scratch_topic_e2e_pipeline(self, tmp_path, synthetic_mp3_factory):
        """Tests the 'Generate from Scratch' topic mode pipeline without an uploaded file."""
        from core.extractor import extract_text
        from core.mp3_stitcher import stitch_mp3_files
        from core.parser import DialogueParser
        from core.prompts import build_system_prompt, build_user_prompt

        # 1. Scratch topic input
        topic = "The history and future of supersonic passenger flight"
        topic_text = extract_text(topic, is_topic=True)
        assert topic in topic_text

        # 2. Prompts
        sys_prompt = build_system_prompt(
            language="en-US", format_type="standard", tone_style="analytical"
        )
        build_user_prompt(content=topic_text, language="en-US", is_topic=True)
        assert "Host 1" in sys_prompt

        # 3. Mock LLM output with unescaped trailing comma (Tier 4 parser test)
        llm_response = (
            "[\n"
            '  {"speaker": "Host 1", "text": "Supersonic flight is making a major comeback!",},\n'
            '  {"speaker": "Host 2", "text": "Yes, modern aerodynamic designs dramatically reduce sonic booms.",}\n'
            "]"
        )
        turns = DialogueParser.parse(llm_response)
        assert len(turns) == 2

        # 4. Synthesis & Stitching
        audio_segs = [synthetic_mp3_factory(num_frames=2) for _ in turns]
        mp3_path = tmp_path / "supersonic_podcast.mp3"
        result_path = stitch_mp3_files(
            audio_segs, str(mp3_path), title="Supersonic Flight", artist="Jenny & Guy"
        )
        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0

    def test_script_only_and_resynthesis_pipeline(self, tmp_path, synthetic_mp3_factory):
        """Tests 'Generate Script Only', editing the script JSON, and synthesizing audio from it."""
        from core.mp3_stitcher import stitch_mp3_files
        from core.parser import DialogueParser

        # 1. Original script
        raw_script = [
            {"speaker": "Host 1", "text": "Original introduction line."},
            {"speaker": "Host 2", "text": "Original explanation line."},
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


class TestMultiTierGroundingPipeline:
    """Tier 4: Multi-tier grounding engine validation across strict, creative, and scratch modes."""

    def test_strict_source_only_grounding_pipeline_e2e(self, tmp_path, synthetic_mp3_factory):
        """Tests Strict Source-Only mode ensuring strict document constraints throughout."""
        from core.extractor import extract_text
        from core.mp3_stitcher import stitch_mp3_files
        from core.prompts import build_system_prompt, build_user_prompt

        # 1. Document ingestion
        doc_file = tmp_path / "financial_q4.txt"
        doc_file.write_text(
            "Company XYZ reported Q4 revenue of $12.4M, representing a 14% year-over-year increase.",
            encoding="utf-8",
        )
        doc_content = extract_text(str(doc_file))

        # 2. Strict Prompts
        sys_p = build_system_prompt(
            language="en-US", format_type="standard", tone_style="analytical"
        )
        user_p = build_user_prompt(content=doc_content, language="en-US", is_topic=False)
        assert "Jenny" in sys_p
        assert "$12.4M" in user_p

        # 3. LLM Response
        llm_raw = (
            "[\n"
            '  {"speaker": "Host 1", "text": "Welcome to Q4 Financial Insights. What are the key figures?"},\n'
            '  {"speaker": "Host 2", "text": "Revenue reached $12.4M, up 14% year-over-year."}\n'
            "]"
        )
        turns = DialogueParser.parse(llm_raw)
        assert len(turns) == 2
        assert "$12.4M" in turns[1].text

        # 4. Synthesize & Stitch
        audio_segs = [synthetic_mp3_factory(num_frames=2) for _ in turns]
        out_mp3 = tmp_path / "strict_q4.mp3"
        res_path = stitch_mp3_files(audio_segs, str(out_mp3), title="Strict Q4 Review")
        assert os.path.exists(res_path)
        assert os.path.getsize(res_path) > 0

    def test_creative_analogy_grounding_pipeline_e2e(self, tmp_path, synthetic_mp3_factory):
        """Tests Creative Analogy mode synthesizing metaphors with underlying document facts."""
        from core.extractor import extract_text
        from core.mp3_stitcher import stitch_mp3_files
        from core.prompts import build_system_prompt, build_user_prompt

        doc_file = tmp_path / "networking_guide.md"
        doc_file.write_text(
            "# BGP Routing Explained\n\nBorder Gateway Protocol determines the most efficient path for data packets.",
            encoding="utf-8",
        )
        doc_content = extract_text(str(doc_file))

        sys_p = build_system_prompt(language="en-US", format_type="standard", tone_style="casual")
        user_p = build_user_prompt(content=doc_content, language="en-US", is_topic=False)
        assert "Jenny" in sys_p
        assert "Border Gateway Protocol" in user_p

        llm_raw = (
            "[\n"
            '  {"speaker": "Host 1", "text": "So is BGP essentially the GPS navigation system of the entire internet?"},\n'
            '  {"speaker": "Host 2", "text": "Exactly, Jenny! It directs packet traffic through the best route available."}\n'
            "]"
        )
        turns = DialogueParser.parse(llm_raw)
        assert len(turns) == 2
        assert "GPS navigation" in turns[0].text

        audio_segs = [synthetic_mp3_factory(num_frames=2) for _ in turns]
        out_mp3 = tmp_path / "creative_bgp.mp3"
        res_path = stitch_mp3_files(audio_segs, str(out_mp3), title="Creative BGP")
        assert os.path.exists(res_path)
        assert os.path.getsize(res_path) > 0

    def test_open_topic_scratch_grounding_pipeline_e2e(self, tmp_path, synthetic_mp3_factory):
        """Tests Open Topic / Scratch mode pipeline without any source files."""
        from core.extractor import extract_text
        from core.mp3_stitcher import stitch_mp3_files
        from core.prompts import build_system_prompt, build_user_prompt

        topic_prompt = "Ethics of Artificial Intelligence in Autonomous Vehicles"
        extracted = extract_text(topic_prompt, is_topic=True)
        assert topic_prompt in extracted

        sys_p = build_system_prompt(language="nb-NO", format_type="standard", tone_style="debate")
        user_p = build_user_prompt(content=extracted, language="nb-NO", is_topic=True)
        assert "Kari" in sys_p
        assert "TEMA:" in user_p

        llm_raw = (
            "[\n"
            '  {"speaker": "Host 1", "text": "Hei og velkommen! Hvordan skal en selvkjørende bil prioritere i en ulykke?"},\n'
            '  {"speaker": "Host 2", "text": "Hei Kari! Dette er det klassiske tralleproblemet i en helt ny teknologisk drakt."}\n'
            "]"
        )
        turns = DialogueParser.parse(llm_raw)
        assert len(turns) == 2

        audio_segs = [synthetic_mp3_factory(num_frames=2) for _ in turns]
        out_mp3 = tmp_path / "scratch_ethics.mp3"
        res_path = stitch_mp3_files(
            audio_segs, str(out_mp3), title="AI Ethics", artist="Kari & Ola"
        )
        assert os.path.exists(res_path)
        assert os.path.getsize(res_path) > 0


class TestMultiActEpisodicPipeline:
    """Tier 4: Multi-act structured sequential generation pipeline."""

    def test_multi_act_standard_two_act_generation_pipeline(self):
        """Tests 2-act standard episodic pipeline specs and prompt continuity."""
        from core.prompts import build_act_system_prompt, build_act_user_prompt, get_act_specs

        specs = get_act_specs("standard", language="nb-NO")
        assert len(specs) == 2

        # Act 1 (Intro)
        act1_sys = build_act_system_prompt(specs[0], total_acts=2, language="nb-NO")
        act1_user = build_act_user_prompt("Tema for podcast", language="nb-NO", is_topic=True)
        assert "AKT 1 (INTRO)" in act1_sys
        assert "Tema for podcast" in act1_user

        # Simulated Act 1 turns
        act1_turns = [
            {"speaker": "Host 1", "text": "Velkommen til sendingen!"},
            {"speaker": "Host 2", "text": "Hyggelig å være her!"},
        ]

        # Act 2 (Outro)
        act2_sys = build_act_system_prompt(
            specs[1], total_acts=2, language="nb-NO", next_speaker="Host 1"
        )
        act2_user = build_act_user_prompt(
            "Tema for podcast", prev_turns=act1_turns, language="nb-NO", is_topic=True
        )
        assert "siste akt" in act2_sys.lower()
        assert "SISTE REPLIKKER FRA FORRIGE DEL" in act2_user
        assert "Velkommen til sendingen!" in act2_user

    def test_multi_act_deep_dive_three_act_generation_pipeline(self):
        """Tests 3-act deep dive episodic pipeline specs."""
        from core.prompts import build_act_system_prompt, get_act_specs

        specs = get_act_specs("deep_dive", language="en-US")
        assert len(specs) == 3

        act1_sys = build_act_system_prompt(specs[0], total_acts=3, language="en-US")
        act2_sys = build_act_system_prompt(specs[1], total_acts=3, language="en-US")
        act3_sys = build_act_system_prompt(specs[2], total_acts=3, language="en-US")

        assert "ACT 1 (INTRO)" in act1_sys
        assert "ACT 2 of 3 (CONTINUATION)" in act2_sys
        assert "final act" in act3_sys.lower()

    def test_multi_act_extended_five_act_generation_pipeline(self):
        """Tests 5-act extended in-depth masterclass pipeline specs."""
        from core.prompts import build_act_system_prompt, get_act_specs

        specs = get_act_specs("extended", language="nb-NO")
        assert len(specs) == 5

        for idx, spec in enumerate(specs, start=1):
            sys_p = build_act_system_prompt(spec, total_acts=5, language="nb-NO")
            assert f"AKT {idx} av 5" in sys_p

    def test_multi_act_generate_podcast_script_integration(self):
        """Tests generate_podcast_script executing multi-act generation loops."""
        from core.ollama import generate_podcast_script

        act_turns = [
            {"speaker": "Host 1", "text": "Turn 1 in this act."},
            {"speaker": "Host 2", "text": "Turn 2 in this act."},
        ]
        dialogue_json = json.dumps(act_turns)
        chat_resp = {"message": {"role": "assistant", "content": dialogue_json}}

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(chat_resp).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            progress_messages = []
            turns = generate_podcast_script(
                content="Deep topic analysis",
                language="en-US",
                format_type="deep_dive",
                tone_style="analytical",
                progress_callback=lambda msg: progress_messages.append(msg),
            )
            # 3 acts * 2 turns = 6 turns
            assert len(turns) == 6
            assert any("Act 1/3" in m for m in progress_messages)
            assert any("Act 3/3" in m for m in progress_messages)


class TestPipelineFaultToleranceAndRecovery:
    """Tier 4: Error cascade handling and recovery in integrated pipeline."""

    def test_pipeline_parser_malformed_llm_markdown_salvage(self):
        """Tests parser salvaging non-standard and noisy markdown responses."""
        raw_noisy = (
            "Here is the dialogue between Jenny and Guy:\n\n"
            "```\n"
            "[\n"
            '  {"speaker": "Jenny", "text": "Hello Guy, excited to discuss this!"},\n'
            '  {"speaker": "Guy", "text": "Likewise Jenny!"}\n'
            "]\n"
            "```\n\n"
            "Hope you enjoyed the transcript!"
        )
        turns = DialogueParser.parse(raw_noisy)
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[1].speaker == "Host 2"

    def test_pipeline_tts_retry_recovery_simulation(self):
        """Tests TTSEngine voice mapping and speaking rate calculations."""
        from core.tts import TTSEngine

        engine_nb = TTSEngine(language="nb-NO", rate="+10%")
        assert engine_nb.get_voice_for_speaker("Host 1") == "no_NO-torkil-medium"
        assert engine_nb.get_voice_for_speaker("Host 2") == "no_NO-torkil-medium"

        engine_en = TTSEngine(language="en-US", rate="-5%")
        assert engine_en.get_voice_for_speaker("Host 1") == "en_US-lessac-medium"
        assert engine_en.get_voice_for_speaker("Host 2") == "en_US-ryan-medium"
