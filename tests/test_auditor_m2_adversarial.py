"""Adversarial stress-testing of Milestone 2 (Monologue Episode Generation & Audio Synthesis)."""

import json
from unittest.mock import MagicMock, patch

from core.ollama import generate_podcast_script
from core.parser import DialogueParser, normalize_speaker
from core.prompts import (
    HostMode,
    build_system_prompt,
    get_act_specs,
    normalize_host_mode,
)
from core.tts import TTSEngine


class TestAuditorM2AdversarialIntegrity:
    """Rigorous empirical validation of all M2 invariants and boundary conditions."""

    def test_host_mode_normalization_adversarial(self):
        # Norwegian aliases
        assert normalize_host_mode("lydessay") == "monologue"
        assert normalize_host_mode("enetale") == "monologue"
        assert normalize_host_mode("enetal") == "monologue"
        assert normalize_host_mode("kåsør") == "dialogue"  # persona not mode
        assert normalize_host_mode("  SOLO \n\t") == "monologue"
        assert normalize_host_mode("Single_Host") == "monologue"
        assert normalize_host_mode("AUDIO-ESSAY") == "monologue"
        assert normalize_host_mode("dialogue") == "dialogue"
        assert normalize_host_mode("two-hosts") == "dialogue"
        assert normalize_host_mode(None) == "dialogue"
        assert normalize_host_mode(12345) == "dialogue"
        assert normalize_host_mode(HostMode.MONOLOGUE) == "monologue"
        assert normalize_host_mode(HostMode.DIALOGUE) == "dialogue"

    def test_speaker_normalization_adversarial(self):
        # Host 1 / Solo personas
        for solo_p in [
            "Host 1",
            "Host 1 (Kari)",
            "Kari",
            "Jenny",
            "Narrator",
            "Presenter",
            "Solo Host",
            "solo",
            "Forteller",
            "Oppleser",
            "Essayist",
            "Author",
            "Monologue",
        ]:
            assert normalize_speaker(solo_p) == "Host 1", f"Failed for {solo_p}"

        # Host 2 personas (priority test: 'Host 2' must not be mapped to Host 1)
        for h2_p in [
            "Host 2",
            "Host 2 (Ola)",
            "Speaker 2",
            "Ola",
            "Guy",
            "Co-host",
            "cohost",
            "Vert 2",
            "Programleder 2",
            "Host B",
        ]:
            assert normalize_speaker(h2_p) == "Host 2", f"Failed for {h2_p}"

    def test_monologue_prompt_hermeticity(self):
        # Ensure Norwegian monologue never leaks Ola or Host 2
        nb_mono = build_system_prompt(
            "nb-NO", "standard", "casual", "strict", host_mode="monologue"
        )
        assert "Kari" in nb_mono
        assert "Ola" not in nb_mono
        assert "Host 1" in nb_mono
        assert "Host 2" not in nb_mono

        # Ensure English monologue never leaks Guy or Host 2
        en_mono = build_system_prompt(
            "en-US", "standard", "casual", "strict", host_mode="monologue"
        )
        assert "Jenny" in en_mono
        assert "Guy" not in en_mono
        assert "Host 1" in en_mono
        assert "Host 2" not in en_mono

    def test_act_specs_turn_counts_and_boundaries(self):
        for fmt, exp_acts, exp_turns in [
            ("quick", 1, 8),
            ("standard", 2, 14),
            ("deep_dive", 4, 24),
            ("extended", 5, 54),
        ]:
            nb_acts = get_act_specs(fmt, "nb-NO", host_mode="monologue")
            assert len(nb_acts) == exp_acts
            assert sum(a["target_turns"] for a in nb_acts) == exp_turns

            en_acts = get_act_specs(fmt, "en-US", host_mode="monologue")
            assert len(en_acts) == exp_acts
            assert sum(a["target_turns"] for a in en_acts) == exp_turns

    def test_parser_monologue_all_tiers_stress(self):
        # Tier 1 single-key objects
        t1 = DialogueParser.parse('[{"text": "Paragraph 1"}, {"text": "Paragraph 2"}]')
        assert len(t1) == 2 and all(t.speaker == "Host 1" for t in t1)

        # Tier 1 raw string array
        t2 = DialogueParser.parse('["Paragraph string 1", "Paragraph string 2"]')
        assert len(t2) == 2 and all(t.speaker == "Host 1" for t in t2)

        # Tier 1 root wrapper objects
        for wrap in ["monologue", "essay", "audio_essay", "paragraphs", "sections"]:
            t3 = DialogueParser.parse(f'{{"{wrap}": [{{"text": "A"}}, {{"text": "B"}}]}}')
            assert len(t3) == 2 and all(t.speaker == "Host 1" for t in t3)

        # Tier 4 single quotes & trailing comma
        t4 = DialogueParser.parse("[{'speaker': 'Solo Host', 'text': 'Fixed line',},]")
        assert len(t4) == 1 and t4[0].speaker == "Host 1" and t4[0].text == "Fixed line"

        # Tier 5 stream single-key regex
        t5 = DialogueParser.parse('{"text": "First chunk"}\n{"text": "Second chunk"}')
        assert len(t5) == 2 and all(t.speaker == "Host 1" for t in t5)

        # Tier 6 plain text
        t6 = DialogueParser.parse("**Host (Kari):** Hei alle sammen.\n\nOppleser: Her er analysen.")
        assert len(t6) == 2 and all(t.speaker == "Host 1" for t in t6)

    def test_tts_engine_solo_voice_resolution(self):
        engine_nb = TTSEngine(language="nb-NO", solo_voice="no_NO-torkil-medium")
        assert engine_nb.get_voice_for_speaker("Host 1") == "no_NO-torkil-medium"
        assert engine_nb.get_voice_for_speaker("Narrator") == "no_NO-torkil-medium"
        assert engine_nb.get_voice_for_speaker("Solo Host") == "no_NO-torkil-medium"

        engine_en = TTSEngine(language="en-US", solo_voice="en_US-amy-medium")
        assert engine_en.get_voice_for_speaker("Host 1") == "en_US-amy-medium"
        assert engine_en.get_voice_for_speaker("Narrator") == "en_US-amy-medium"
        assert engine_en.get_voice_for_speaker("Solo Host") == "en_US-amy-medium"
        assert engine_en.get_voice_for_speaker("Host 2") == "en_US-ryan-medium"

    def test_generate_podcast_script_monologue_full_pipeline(self):
        act_turns = [
            {"speaker": "Host 1", "text": "Del en."},
            {"speaker": "Host 1", "text": "Del to."},
        ]
        dialogue_json = json.dumps(act_turns)
        chat_response = {"message": {"role": "assistant", "content": dialogue_json}}

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(chat_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            turns = generate_podcast_script(
                content="Adversarial monologue generation test",
                language="nb-NO",
                format_type="standard",
                host_mode="monologue",
            )
            # standard monologue has 2 acts, 2 turns each mock -> 4 turns
            assert len(turns) == 4
            for t in turns:
                assert t.speaker == "Host 1"
