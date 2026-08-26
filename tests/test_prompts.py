"""
Tests for Prompt Generation & Grounding Engine (core/prompts.py)
================================================================
Milestone 1 Test Suite covering:
- GroundingMode enum (STRICT, CREATIVE, OPEN_TOPIC) and GROUNDING_MODE_PRESETS
- GROUNDING_MODE_ALIASES and normalize_grounding_mode() with edge cases & fallbacks
- Negative anti-hallucination constraints & omission acknowledgment in nb-NO and en-US
- Creative analogy & metaphor directives in nb-NO and en-US
- Open topic generative synthesis directives in nb-NO and en-US
- 72-Permutation Combinatorial Matrix: 2 Languages x 3 Grounding Modes x 4 Lengths x 3 Tones
- Document vs. Topic user prompt generation with boundary marker verification
- Multi-act episodic prompt generation across all 11 act specifications
- Backward compatibility and regression verification for baseline prompt APIs
"""

import pytest

from core.prompts import (
    ACT_SPECS_MONOLOGUE_EN,
    ACT_SPECS_MONOLOGUE_NB,
    GROUNDING_DIRECTIVES_EN,
    GROUNDING_DIRECTIVES_NB,
    GROUNDING_MODE_ALIASES,
    GROUNDING_MODE_PRESETS,
    HOST_MODE_ALIASES,
    HOST_MODE_PRESETS,
    SYSTEM_PROMPT_MONOLOGUE_EN,
    SYSTEM_PROMPT_MONOLOGUE_NB,
    GroundingMode,
    HostMode,
    build_act_system_prompt,
    build_act_user_prompt,
    build_system_prompt,
    build_user_prompt,
    get_act_specs,
    get_format_config,
    get_tone_description,
    normalize_grounding_mode,
    normalize_host_mode,
)


class TestGroundingModeEnumAndNormalization:
    """Tier 1: GroundingMode enum, presets, alias normalization, and edge case fallbacks."""

    def test_grounding_mode_enum_values(self):
        """Verify GroundingMode enum values and string subclass behavior."""
        assert GroundingMode.STRICT == "strict"
        assert GroundingMode.STRICT.value == "strict"
        assert GroundingMode.CREATIVE == "creative"
        assert GroundingMode.CREATIVE.value == "creative"
        assert GroundingMode.OPEN_TOPIC == "open_topic"
        assert GroundingMode.OPEN_TOPIC.value == "open_topic"
        assert isinstance(GroundingMode.STRICT, str)
        assert issubclass(GroundingMode, str)

    def test_grounding_mode_presets_metadata(self):
        """Verify GROUNDING_MODE_PRESETS dictionary structure and required metadata keys."""
        assert len(GROUNDING_MODE_PRESETS) == 3
        for mode_key in ["strict", "creative", "open_topic"]:
            assert mode_key in GROUNDING_MODE_PRESETS
            preset = GROUNDING_MODE_PRESETS[mode_key]
            assert preset["id"] == mode_key
            assert "name_en" in preset and len(preset["name_en"]) > 0
            assert "name_nb" in preset and len(preset["name_nb"]) > 0
            assert "description_en" in preset and len(preset["description_en"]) > 0
            assert "description_nb" in preset and len(preset["description_nb"]) > 0
            assert "badge" in preset and len(preset["badge"]) > 0
            assert "anti_hallucination_level" in preset

    def test_grounding_mode_aliases_dict(self):
        """Verify GROUNDING_MODE_ALIASES dictionary mappings and consistency."""
        assert isinstance(GROUNDING_MODE_ALIASES, dict)
        assert len(GROUNDING_MODE_ALIASES) >= 15
        assert GROUNDING_MODE_ALIASES["strict_source_only"] == "strict"
        assert GROUNDING_MODE_ALIASES["creative_analogy"] == "creative"
        assert GROUNDING_MODE_ALIASES["open_topic"] == "open_topic"
        assert GROUNDING_MODE_ALIASES["kilde"] == "strict"
        assert GROUNDING_MODE_ALIASES["scratch"] == "open_topic"

    @pytest.mark.parametrize("mode", ["strict", "creative", "open_topic"])
    def test_normalize_grounding_mode_canonical(self, mode):
        """Verify canonical mode strings resolve to themselves."""
        assert normalize_grounding_mode(mode) == mode

    def test_normalize_grounding_mode_enum_instances(self):
        """Verify GroundingMode enum instances resolve properly."""
        assert normalize_grounding_mode(GroundingMode.STRICT) == "strict"
        assert normalize_grounding_mode(GroundingMode.CREATIVE) == "creative"
        assert normalize_grounding_mode(GroundingMode.OPEN_TOPIC) == "open_topic"

    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("strict_source", "strict"),
            ("strict_source_only", "strict"),
            ("source_only", "strict"),
            ("source-only", "strict"),
            ("strict", "strict"),
            ("source", "strict"),
            ("factual", "strict"),
            ("strict-source", "strict"),
            ("streng", "strict"),
            ("kildetro", "strict"),
            ("kilde", "strict"),
            ("creative_analogy", "creative"),
            ("creative", "creative"),
            ("creative_synthesis", "creative"),
            ("analogy", "creative"),
            ("metaphor", "creative"),
            ("creative-analogy", "creative"),
            ("kreativ", "creative"),
            ("open_topic", "open_topic"),
            ("open", "open_topic"),
            ("scratch", "open_topic"),
            ("topic", "open_topic"),
            ("free", "open_topic"),
            ("fritt", "open_topic"),
            ("tema", "open_topic"),
            ("åpent", "open_topic"),
            ("apent", "open_topic"),
            ("open-topic", "open_topic"),
        ],
    )
    def test_normalize_grounding_mode_aliases(self, alias, expected):
        """Verify all defined aliases resolve to canonical mode identifiers."""
        assert normalize_grounding_mode(alias) == expected

    @pytest.mark.parametrize(
        "raw_input,expected",
        [
            ("  STRICT  ", "strict"),
            ("Creative\n", "creative"),
            (" OPEN_TOPIC ", "open_topic"),
            ("Strict_Source", "strict"),
            ("  open-topic\t", "open_topic"),
            ("CREATIVE_ANALOGY", "creative"),
            ("SOURCE-ONLY", "strict"),
        ],
    )
    def test_normalize_grounding_mode_formatting_and_casing(self, raw_input, expected):
        """Verify case insensitivity and whitespace trimming."""
        assert normalize_grounding_mode(raw_input) == expected

    @pytest.mark.parametrize(
        "invalid_input",
        ["", "   ", "unknown", "invalid_mode", None, 123, 3.14, [], {}, True],
    )
    def test_normalize_grounding_mode_fallback_on_invalid(self, invalid_input):
        """Verify invalid, unknown, or non-string inputs safely fallback to 'strict'."""
        assert normalize_grounding_mode(invalid_input) == "strict"


class TestGroundingDirectivesContent:
    """Tier 1: Verification of localized grounding directives and anti-hallucination constraints."""

    def test_strict_negative_constraints_norwegian(self):
        """Verify Norwegian strict mode directive contains negative anti-hallucination constraints."""
        directive = GROUNDING_DIRECTIVES_NB["strict"]
        assert "STRENG KILDEKONTROLL" in directive or "FORANKRING" in directive
        assert "STRENGT FORBUDT" in directive
        assert "finne på" in directive or "dikte opp" in directive
        assert (
            "uprøvde påstander" in directive
            or "faktiske" in directive
            or "eksterne fakta" in directive
        )
        assert "unevnte statistikker" in directive or "tall" in directive or "fiktive" in directive
        assert "anerkjenne" in directive or "informasjonen mangler" in directive

    def test_strict_negative_constraints_english(self):
        """Verify English strict mode directive contains negative anti-hallucination constraints."""
        directive = GROUNDING_DIRECTIVES_EN["strict"]
        assert "STRICT SOURCE-ONLY" in directive or "GROUNDING" in directive
        assert "STRICTLY FORBIDDEN" in directive
        assert "fabricate" in directive or "invent" in directive
        assert "external facts" in directive or "claims" in directive
        assert "unmentioned statistics" in directive or "statistics" in directive
        assert (
            "acknowledge" in directive
            or "omission" in directive
            or "lack of information" in directive
        )

    def test_creative_analogy_directives_norwegian(self):
        """Verify Norwegian creative mode directive encourages metaphors and analogies grounded in source."""
        directive = GROUNDING_DIRECTIVES_NB["creative"]
        assert "KREATIV ANALOGI" in directive or "KREATIVITET" in directive
        assert "Forankre kjerneinnsiktene" in directive or "kildematerialet" in directive
        assert "hverdagsanalogier" in directive or "metaforer" in directive
        assert "illustrative eksempler" in directive or "eksempler" in directive
        assert "kjernebudskap forblir intakt" in directive or "kilden" in directive

    def test_creative_analogy_directives_english(self):
        """Verify English creative mode directive encourages metaphors and analogies grounded in source."""
        directive = GROUNDING_DIRECTIVES_EN["creative"]
        assert "CREATIVE ANALOGY" in directive or "CREATIVITY" in directive
        assert "Anchor all core insights" in directive or "source material" in directive
        assert "analogies" in directive or "metaphors" in directive
        assert "illustrative examples" in directive or "examples" in directive
        assert (
            "core facts and message remain uncompromised" in directive or "core facts" in directive
        )

    def test_open_topic_synthesis_directives_norwegian(self):
        """Verify Norwegian open topic directive provides generative freedom without document limits."""
        directive = GROUNDING_DIRECTIVES_NB["open_topic"]
        assert "FRITT TEMA" in directive or "ÅPEN DISKUSJON" in directive
        assert "fri syntese" in directive or "utforsking" in directive
        assert (
            "uten binding til et fast kildedokument" in directive
            or "uten kildedokument" in directive
        )
        assert "bred allmennkunnskap" in directive or "varierte perspektiver" in directive

    def test_open_topic_synthesis_directives_english(self):
        """Verify English open topic directive provides generative freedom without document limits."""
        directive = GROUNDING_DIRECTIVES_EN["open_topic"]
        assert "OPEN TOPIC" in directive or "GENERATIVE SYNTHESIS" in directive
        assert "open, creative exploration" in directive or "generative synthesis" in directive
        assert (
            "without constraints to a single source document" in directive
            or "without constraints" in directive
        )
        assert "broad general knowledge" in directive or "diverse perspectives" in directive


class TestPromptsCombinatorialMatrix72:
    """Tier 3: Full 72-permutation combinatorial validation across Languages x Modes x Formats x Tones."""

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("grounding_mode", ["strict", "creative", "open_topic"])
    @pytest.mark.parametrize("format_type", ["quick", "standard", "deep_dive", "extended"])
    @pytest.mark.parametrize("tone_style", ["casual", "analytical", "debate"])
    def test_72_permutation_system_prompt_matrix(
        self, language, grounding_mode, format_type, tone_style
    ):
        """
        Tests every permutation in the 2 x 3 x 4 x 3 = 72 test grid.
        Asserts persona assignment, JSON grammar, turn constraints, tone embedding,
        and grounding mode directives.
        """
        prompt = build_system_prompt(
            language=language,
            format_type=format_type,
            tone_style=tone_style,
            grounding_mode=grounding_mode,
        )

        assert isinstance(prompt, str)
        assert len(prompt) > 200

        # Personas
        if language == "nb-NO":
            assert "Kari" in prompt
            assert "Ola" in prompt
            assert "norsk" in prompt.lower() or "bokmål" in prompt.lower()
        else:
            assert "Jenny" in prompt
            assert "Guy" in prompt
            assert "English" in prompt or "world-class" in prompt

        # Structural requirements
        assert "Host 1" in prompt
        assert "Host 2" in prompt
        assert "JSON" in prompt
        assert '"speaker"' in prompt
        assert '"text"' in prompt

        # Turn metrics
        fmt_cfg = get_format_config(format_type)
        assert fmt_cfg["name"] in prompt
        assert str(fmt_cfg["min_turns"]) in prompt
        assert str(fmt_cfg["max_turns"]) in prompt
        assert str(fmt_cfg["target_turns"]) in prompt

        # Tone description
        tone_desc = get_tone_description(tone_style, language)
        assert any(word in prompt for word in tone_desc.split()[:3])

        # Grounding mode directives
        if grounding_mode == "strict":
            if language == "nb-NO":
                assert "STRENG" in prompt or "FORANKRING" in prompt
                assert "STRENGT FORBUDT" in prompt or "finne på" in prompt
                assert "anerkjenne" in prompt or "informasjonen mangler" in prompt
            else:
                assert "STRICT" in prompt or "GROUNDING" in prompt
                assert "STRICTLY FORBIDDEN" in prompt or "fabricate" in prompt
                assert "acknowledge" in prompt or "omission" in prompt
        elif grounding_mode == "creative":
            if language == "nb-NO":
                assert "KREATIV" in prompt or "ANALOGI" in prompt
                assert "metaforer" in prompt or "hverdagsanalogier" in prompt
            else:
                assert "CREATIVE" in prompt or "ANALOGY" in prompt
                assert "metaphors" in prompt or "analogies" in prompt
        elif grounding_mode == "open_topic":
            if language == "nb-NO":
                assert (
                    "FRITT TEMA" in prompt or "ÅPEN DISKUSJON" in prompt or "fri syntese" in prompt
                )
            else:
                assert (
                    "OPEN TOPIC" in prompt
                    or "GENERATIVE SYNTHESIS" in prompt
                    or "exploration" in prompt
                )


class TestPromptsUserPromptGeneration:
    """Tier 1: User prompt construction with document boundaries and topic formatting."""

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("grounding_mode", ["strict", "creative"])
    def test_user_prompt_document_mode_with_boundaries(self, language, grounding_mode):
        """Verify document input mode encapsulates content inside standard boundary markers."""
        doc_content = "Quarterly financial summary: Revenue increased by 18%."
        prompt = build_user_prompt(
            content=doc_content,
            language=language,
            grounding_mode=grounding_mode,
            is_topic=False,
        )
        assert doc_content in prompt
        if language == "nb-NO":
            assert "--- START KILDEMATERIALE ---" in prompt
            assert "--- SLUTT KILDEMATERIALE ---" in prompt
            assert "kildematerialet" in prompt.lower()
        else:
            assert "--- START SOURCE MATERIAL ---" in prompt
            assert "--- END SOURCE MATERIAL ---" in prompt
            assert "source material" in prompt.lower()

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    def test_user_prompt_topic_mode_formatting(self, language):
        """Verify scratch topic mode formats topic without document boundary markers."""
        topic_content = "The Future of Autonomous Robotics in Agriculture"
        prompt = build_user_prompt(
            content=topic_content,
            language=language,
            grounding_mode="open_topic",
            is_topic=True,
        )
        assert topic_content in prompt
        if language == "nb-NO":
            assert "TEMA:" in prompt or "tema" in prompt.lower()
            assert "--- START KILDEMATERIALE ---" not in prompt
        else:
            assert "TOPIC:" in prompt or "topic" in prompt.lower()
            assert "--- START SOURCE MATERIAL ---" not in prompt

    def test_user_prompt_backward_compatibility_defaults(self):
        """Verify backward compatibility when grounding_mode is omitted."""
        doc_text = "Legacy test document content."
        prompt_nb = build_user_prompt(doc_text, language="nb-NO")
        assert doc_text in prompt_nb
        assert "--- START KILDEMATERIALE ---" in prompt_nb

        topic_text = "Legacy test topic."
        prompt_en = build_user_prompt(topic_text, language="en-US", is_topic=True)
        assert topic_text in prompt_en
        assert "TOPIC:" in prompt_en


class TestPromptsMultiActGenerationWithGrounding:
    """Tier 1 & 3: Multi-act prompt generation across all formats, acts, and grounding modes."""

    @pytest.mark.parametrize("format_type", ["quick", "standard", "deep_dive", "extended"])
    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("grounding_mode", ["strict", "creative", "open_topic"])
    def test_multi_act_system_prompt_all_acts(self, format_type, language, grounding_mode):
        """
        Iterates through every act in the selected format specification.
        Validates act numbering, title, continuity instructions, speaker sequencing,
        turn constraints, and grounding directives.
        """
        act_list = get_act_specs(format_type, language)
        total_acts = len(act_list)

        for act in act_list:
            prompt = build_act_system_prompt(
                act=act,
                total_acts=total_acts,
                language=language,
                tone_style="casual",
                grounding_mode=grounding_mode,
                next_speaker="Host 1",
            )
            assert isinstance(prompt, str)
            assert len(prompt) > 200

            act_num = act["act_num"]
            act_title = act["title"]
            assert str(act_num) in prompt
            assert act_title in prompt

            if language == "nb-NO":
                assert "Kari" in prompt
                assert "Ola" in prompt
            else:
                assert "Jenny" in prompt
                assert "Guy" in prompt

            assert str(act["target_turns"]) in prompt
            assert str(act["min_turns"]) in prompt
            assert str(act["max_turns"]) in prompt

            if act["is_intro"]:
                if language == "nb-NO":
                    assert "AKT 1 (INTRO)" in prompt
                else:
                    assert "ACT 1 (INTRO)" in prompt
            else:
                if language == "nb-NO":
                    assert "PÅGÅENDE SAMTALE" in prompt or "Fortsett" in prompt
                else:
                    assert "CONTINUATION" in prompt or "continue" in prompt.lower()

            if act["is_outro"]:
                if language == "nb-NO":
                    assert "siste akt" in prompt.lower() or "avskjedshilsen" in prompt.lower()
                else:
                    assert "final act" in prompt.lower() or "sign-off" in prompt.lower()

            # Verify grounding directive is present in act system prompt
            if grounding_mode == "strict":
                if language == "nb-NO":
                    assert (
                        "STRENG" in prompt or "FORANKRING" in prompt or "STRENGT FORBUDT" in prompt
                    )
                else:
                    assert (
                        "STRICT" in prompt
                        or "GROUNDING" in prompt
                        or "STRICTLY FORBIDDEN" in prompt
                    )
            elif grounding_mode == "creative":
                if language == "nb-NO":
                    assert "KREATIV" in prompt or "ANALOGI" in prompt
                else:
                    assert "CREATIVE" in prompt or "ANALOGY" in prompt
            elif grounding_mode == "open_topic":
                if language == "nb-NO":
                    assert "FRITT TEMA" in prompt or "ÅPEN DISKUSJON" in prompt
                else:
                    assert "OPEN TOPIC" in prompt or "GENERATIVE SYNTHESIS" in prompt

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("is_topic", [False, True])
    def test_act_user_prompt_with_prev_turns_context(self, language, is_topic):
        """Verify act user prompt preserves previous turn continuity snippets."""
        prev_turns = [
            {"speaker": "Host 1", "text": "Opening thought on climate tech."},
            {"speaker": "Host 2", "text": "Yes, specifically geothermal innovations."},
        ]
        content = "Detailed report on geothermal drilling technology."
        prompt = build_act_user_prompt(
            content=content,
            prev_turns=prev_turns,
            language=language,
            grounding_mode="strict",
            is_topic=is_topic,
        )
        assert content in prompt
        assert "Opening thought on climate tech." in prompt
        assert "geothermal innovations." in prompt
        if language == "nb-NO":
            assert "SISTE REPLIKKER FRA FORRIGE DEL" in prompt
        else:
            assert "LAST TURNS FROM PREVIOUS ACT" in prompt

    def test_act_user_prompt_empty_prev_turns(self):
        """Verify act user prompt works gracefully without previous turns."""
        prompt_nb = build_act_user_prompt(content="Sample text", prev_turns=None, language="nb-NO")
        assert "Sample text" in prompt_nb
        assert "--- START KILDEMATERIALE ---" in prompt_nb
        assert "SISTE REPLIKKER" not in prompt_nb

        prompt_en = build_act_user_prompt(
            content="Topic text", prev_turns=[], language="en-US", is_topic=True
        )
        assert "Topic text" in prompt_en
        assert "Podcast topic:" in prompt_en
        assert "LAST TURNS" not in prompt_en


class TestPromptsExistingCoveragePreserved:
    """Regression: Preserves baseline test methods from original test suite."""

    def test_norwegian_system_prompt_personas(self):
        prompt = build_system_prompt(language="nb-NO", format_type="standard", tone_style="casual")
        assert "Kari" in prompt
        assert "Ola" in prompt
        assert "norsk" in prompt.lower() or "bokmål" in prompt.lower()
        assert "Host 1" in prompt
        assert "Host 2" in prompt
        assert "JSON" in prompt

    def test_english_system_prompt_personas(self):
        prompt = build_system_prompt(language="en-US", format_type="standard", tone_style="casual")
        assert "Jenny" in prompt
        assert "Guy" in prompt
        assert "Host 1" in prompt
        assert "Host 2" in prompt
        assert "JSON" in prompt

    @pytest.mark.parametrize(
        "tone_key,expected_snippet",
        [
            ("casual", "Casual"),
            ("analytical", "Analytical"),
            ("debate", "Debate"),
        ],
    )
    def test_tone_descriptions_english(self, tone_key, expected_snippet):
        desc = get_tone_description(tone_key, language="en-US")
        assert len(desc) > 0
        assert (
            expected_snippet.lower() in desc.lower()
            or "conversational" in desc.lower()
            or "analytical" in desc.lower()
            or "debate" in desc.lower()
        )

    @pytest.mark.parametrize("tone_key", ["casual", "analytical", "debate"])
    def test_tone_descriptions_norwegian(self, tone_key):
        desc = get_tone_description(tone_key, language="nb-NO")
        assert len(desc) > 0

    @pytest.mark.parametrize(
        "fmt_key,min_turns,max_turns",
        [
            ("quick", 6, 8),
            ("quick_summary", 6, 8),
            ("standard", 12, 16),
            ("standard_episode", 12, 16),
            ("deep_dive", 20, 26),
            ("deep", 20, 26),
            ("extended", 45, 60),
            ("extended_in_depth", 45, 60),
        ],
    )
    def test_target_turn_counts(self, fmt_key, min_turns, max_turns):
        cfg = get_format_config(fmt_key)
        assert cfg is not None
        assert "target_turns" in cfg
        assert min_turns <= cfg["min_turns"] <= cfg["max_turns"] <= max_turns

    def test_legacy_format_short_and_deep(self):
        short_cfg = get_format_config("short")
        assert short_cfg is not None
        assert short_cfg["min_turns"] >= 6
        deep_cfg = get_format_config("deep_dive")
        assert deep_cfg is not None
        assert deep_cfg["min_turns"] >= 14

    def test_user_prompt_document_mode(self):
        doc_text = "Detailed quarterly report on renewable energy investments."
        prompt = build_user_prompt(content=doc_text, language="nb-NO", is_topic=False)
        assert doc_text in prompt
        assert "kildematerialet" in prompt.lower() or "source" in prompt.lower()

    def test_user_prompt_scratch_topic_mode(self):
        topic_text = "The emergence of quantum algorithms in cryptography"
        prompt = build_user_prompt(content=topic_text, language="en-US", is_topic=True)
        assert topic_text in prompt
        assert "topic" in prompt.lower() or "tema" in prompt.lower()


class TestHostModeEnumAndNormalization:
    """Milestone 2: HostMode enum, presets, alias normalization, and edge case fallbacks."""

    def test_host_mode_enum_values(self):
        """Verify HostMode enum values and string subclass behavior."""
        assert HostMode.DIALOGUE == "dialogue"
        assert HostMode.DIALOGUE.value == "dialogue"
        assert HostMode.MONOLOGUE == "monologue"
        assert HostMode.MONOLOGUE.value == "monologue"
        assert isinstance(HostMode.MONOLOGUE, str)
        assert issubclass(HostMode, str)

    def test_host_mode_presets_metadata(self):
        """Verify HOST_MODE_PRESETS dictionary structure and required metadata keys."""
        assert len(HOST_MODE_PRESETS) == 2
        for mode_key in ["dialogue", "monologue"]:
            assert mode_key in HOST_MODE_PRESETS
            preset = HOST_MODE_PRESETS[mode_key]
            assert preset["id"] == mode_key
            assert "name_en" in preset and len(preset["name_en"]) > 0
            assert "name_nb" in preset and len(preset["name_nb"]) > 0
            assert "description_en" in preset and len(preset["description_en"]) > 0
            assert "description_nb" in preset and len(preset["description_nb"]) > 0
            assert "badge" in preset and len(preset["badge"]) > 0

    def test_host_mode_aliases_dict(self):
        """Verify HOST_MODE_ALIASES dictionary mappings and consistency."""
        assert isinstance(HOST_MODE_ALIASES, dict)
        assert len(HOST_MODE_ALIASES) >= 15
        assert HOST_MODE_ALIASES["solo"] == "monologue"
        assert HOST_MODE_ALIASES["single_host"] == "monologue"
        assert HOST_MODE_ALIASES["audio_essay"] == "monologue"
        assert HOST_MODE_ALIASES["lydessay"] == "monologue"
        assert HOST_MODE_ALIASES["two_hosts"] == "dialogue"
        assert HOST_MODE_ALIASES["dialog"] == "dialogue"
        assert HOST_MODE_ALIASES["duo"] == "dialogue"

    @pytest.mark.parametrize("mode", ["dialogue", "monologue"])
    def test_normalize_host_mode_canonical(self, mode):
        """Verify canonical mode strings resolve to themselves."""
        assert normalize_host_mode(mode) == mode

    def test_normalize_host_mode_enum_instances(self):
        """Verify HostMode enum instances resolve properly."""
        assert normalize_host_mode(HostMode.DIALOGUE) == "dialogue"
        assert normalize_host_mode(HostMode.MONOLOGUE) == "monologue"

    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("solo", "monologue"),
            ("monolog", "monologue"),
            ("single_host", "monologue"),
            ("single-host", "monologue"),
            ("single", "monologue"),
            ("one_host", "monologue"),
            ("one-host", "monologue"),
            ("one", "monologue"),
            ("audio_essay", "monologue"),
            ("audio-essay", "monologue"),
            ("essay", "monologue"),
            ("narrator", "monologue"),
            ("presenter", "monologue"),
            ("storyteller", "monologue"),
            ("lydessay", "monologue"),
            ("enetal", "monologue"),
            ("enetale", "monologue"),
            ("two_hosts", "dialogue"),
            ("two-hosts", "dialogue"),
            ("two_host", "dialogue"),
            ("two-host", "dialogue"),
            ("two", "dialogue"),
            ("duo", "dialogue"),
            ("dialog", "dialogue"),
            ("conversation", "dialogue"),
            ("interview", "dialogue"),
        ],
    )
    def test_normalize_host_mode_aliases(self, alias, expected):
        """Verify all aliases resolve to canonical modes."""
        assert normalize_host_mode(alias) == expected

    @pytest.mark.parametrize(
        "dirty_input,expected",
        [
            ("  MONOLOGUE\n", "monologue"),
            ("Solo ", "monologue"),
            (" Single_Host ", "monologue"),
            ("Audio-Essay\t", "monologue"),
            ("Two-Hosts", "dialogue"),
            ("DIALOGUE", "dialogue"),
            ("  Duo  ", "dialogue"),
        ],
    )
    def test_normalize_host_mode_casing_and_whitespace(self, dirty_input, expected):
        """Verify case-insensitivity and whitespace trimming during normalization."""
        assert normalize_host_mode(dirty_input) == expected

    @pytest.mark.parametrize(
        "invalid_input",
        [
            None,
            "",
            "   ",
            "unknown_mode",
            "invalid-xyz",
            123,
            True,
            False,
            [],
            {},
        ],
    )
    def test_normalize_host_mode_invalid_fallback(self, invalid_input):
        """Verify invalid/unknown inputs safely fallback to dialogue."""
        assert normalize_host_mode(invalid_input) == "dialogue"


class TestMonologueSystemPromptsContent:
    """Milestone 2: Solo presenter system prompt contents, personas, and structure."""

    def test_monologue_system_prompt_norwegian_persona(self):
        """Verify Norwegian monologue prompt frames Kari as solo presenter without Ola."""
        prompt = build_system_prompt(
            language="nb-NO", format_type="standard", tone_style="casual", host_mode="monologue"
        )
        assert "Kari" in prompt
        assert "Ola" not in prompt
        assert "Host 1" in prompt
        assert "Host 2" not in prompt
        assert "lydessay" in prompt.lower() or "solopodcast" in prompt.lower()
        assert "JSON" in prompt

    def test_monologue_system_prompt_english_persona(self):
        """Verify English monologue prompt frames Jenny as solo presenter without Guy."""
        prompt = build_system_prompt(
            language="en-US", format_type="standard", tone_style="casual", host_mode="monologue"
        )
        assert "Jenny" in prompt
        assert "Guy" not in prompt
        assert "Host 1" in prompt
        assert "Host 2" not in prompt
        assert "audio essay" in prompt.lower() or "solo" in prompt.lower()
        assert "JSON" in prompt

    def test_monologue_json_format_schema(self):
        """Verify sample JSON in monologue prompt contains only Host 1."""
        assert "Kari" in SYSTEM_PROMPT_MONOLOGUE_NB
        assert "Jenny" in SYSTEM_PROMPT_MONOLOGUE_EN
        for lang in ["nb-NO", "en-US"]:
            prompt = build_system_prompt(language=lang, format_type="quick", host_mode="monologue")
            assert '"speaker": "Host 1"' in prompt
            assert '"speaker": "Host 2"' not in prompt


class TestMonologueActSpecs:
    """Milestone 2: Monologue multi-act chapter specifications and personas."""

    def test_monologue_act_specs_constants(self):
        """Verify ACT_SPECS_MONOLOGUE_NB and ACT_SPECS_MONOLOGUE_EN constants."""
        assert len(ACT_SPECS_MONOLOGUE_NB) == 4
        assert len(ACT_SPECS_MONOLOGUE_EN) == 4
        assert "quick" in ACT_SPECS_MONOLOGUE_NB
        assert "extended" in ACT_SPECS_MONOLOGUE_EN

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    def test_act_specs_monologue_counts_and_structure(self, language):
        """Verify act counts and turn targets for all 4 format presets in monologue mode."""
        # quick -> 1 act
        quick_acts = get_act_specs("quick", language=language, host_mode="monologue")
        assert len(quick_acts) == 1
        assert quick_acts[0]["act_num"] == 1
        assert quick_acts[0]["is_intro"] is True
        assert quick_acts[0]["is_outro"] is True
        assert quick_acts[0]["target_turns"] == 8

        # standard -> 2 acts
        std_acts = get_act_specs("standard", language=language, host_mode="monologue")
        assert len(std_acts) == 2
        assert std_acts[0]["is_intro"] is True
        assert std_acts[0]["is_outro"] is False
        assert std_acts[1]["is_intro"] is False
        assert std_acts[1]["is_outro"] is True
        assert sum(a["target_turns"] for a in std_acts) == 14

        # deep_dive -> 4 acts
        deep_acts = get_act_specs("deep_dive", language=language, host_mode="monologue")
        assert len(deep_acts) == 4
        assert deep_acts[0]["is_intro"] is True
        assert deep_acts[-1]["is_outro"] is True
        assert sum(a["target_turns"] for a in deep_acts) == 24

        # extended -> 5 acts
        ext_acts = get_act_specs("extended", language=language, host_mode="monologue")
        assert len(ext_acts) == 5
        assert ext_acts[0]["is_intro"] is True
        assert ext_acts[-1]["is_outro"] is True
        assert sum(a["target_turns"] for a in ext_acts) == 54

    def test_act_specs_monologue_personas_and_themes(self):
        """Verify monologue act themes feature solo presenters and never mention co-hosts."""
        for fmt in ["quick", "standard", "deep_dive", "extended"]:
            nb_acts = get_act_specs(fmt, language="nb-NO", host_mode="monologue")
            for act in nb_acts:
                assert "Kari" in act["prompt_theme"]
                assert "Ola" not in act["prompt_theme"]

            en_acts = get_act_specs(fmt, language="en-US", host_mode="monologue")
            for act in en_acts:
                assert "Jenny" in act["prompt_theme"]
                assert "Guy" not in act["prompt_theme"]


class TestMonologueCombinatorialMatrix72:
    """Milestone 2: 72-Permutation Combinatorial Matrix for Monologue Mode."""

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("grounding_mode", ["strict", "creative", "open_topic"])
    @pytest.mark.parametrize("format_type", ["quick", "standard", "deep_dive", "extended"])
    @pytest.mark.parametrize("tone_style", ["casual", "analytical", "debate"])
    def test_72_permutation_monologue_system_prompt_matrix(
        self, language, grounding_mode, format_type, tone_style
    ):
        """Verify all 72 monologue system prompt combinations produce valid solo prompts."""
        prompt = build_system_prompt(
            language=language,
            format_type=format_type,
            tone_style=tone_style,
            grounding_mode=grounding_mode,
            host_mode="monologue",
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 250
        assert "Host 1" in prompt
        assert "Host 2" not in prompt

        if language == "nb-NO":
            assert "Kari" in prompt
            assert "Ola" not in prompt
        else:
            assert "Jenny" in prompt
            assert "Guy" not in prompt

        # Verify grounding directive insertion
        if grounding_mode == "strict":
            assert "STRENG" in prompt or "STRICT" in prompt
        elif grounding_mode == "creative":
            assert "ANALOGI" in prompt or "ANALOG" in prompt or "METAFOR" in prompt
        elif grounding_mode == "open_topic":
            assert "FRITT" in prompt or "OPEN TOPIC" in prompt or "SYNTHESIS" in prompt


class TestMonologueMultiActGeneration:
    """Milestone 2: Multi-act prompt builders in monologue mode."""

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("format_type", ["quick", "standard", "deep_dive", "extended"])
    @pytest.mark.parametrize("grounding_mode", ["strict", "creative", "open_topic"])
    def test_monologue_multi_act_system_prompt_all_acts(
        self, language, format_type, grounding_mode
    ):
        """Verify build_act_system_prompt for every monologue act."""
        acts = get_act_specs(format_type, language=language, host_mode="monologue")
        total_acts = len(acts)

        for act in acts:
            prompt = build_act_system_prompt(
                act=act,
                total_acts=total_acts,
                language=language,
                tone_style="analytical",
                grounding_mode=grounding_mode,
                host_mode="monologue",
            )
            assert f"AKT {act['act_num']}" in prompt or f"ACT {act['act_num']}" in prompt
            assert act["title"] in prompt
            assert "Host 1" in prompt
            assert "Host 2" not in prompt

            if act.get("is_intro"):
                assert "AKT 1 (INTRO)" in prompt or "ACT 1 (INTRO)" in prompt
            else:
                assert "PÅGÅENDE NARRATIV" in prompt or "CONTINUATION" in prompt

            if act.get("is_outro"):
                assert "siste akt" in prompt.lower() or "final act" in prompt.lower()

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    def test_monologue_act_user_prompt_with_prev_turns(self, language):
        """Verify act user prompt for monologue passes context and uses solo instructions."""
        prev_turns = [
            {"speaker": "Host 1", "text": "First paragraph on solar power development."},
            {"speaker": "Host 1", "text": "Next we analyze grid integration challenges."},
        ]
        prompt = build_act_user_prompt(
            content="Solar power report",
            prev_turns=prev_turns,
            language=language,
            host_mode="monologue",
        )
        assert "Solar power report" in prompt
        assert "solar power development" in prompt
        if language == "nb-NO":
            assert "SISTE AVSNITT FRA FORRIGE DEL" in prompt
            assert "alle replikker tilhører Host 1" in prompt
        else:
            assert "LAST PARAGRAPHS FROM PREVIOUS ACT" in prompt
            assert "all turns belong to Host 1" in prompt


class TestMonologueUserPromptGeneration:
    """Milestone 2: Monologue user prompt formatting for documents and topics."""

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("grounding_mode", ["strict", "creative"])
    def test_monologue_user_prompt_document_mode(self, language, grounding_mode):
        """Verify user prompt in document mode enforces monologue format rule."""
        content = "Executive report on artificial intelligence ethics."
        prompt = build_user_prompt(
            content=content,
            language=language,
            grounding_mode=grounding_mode,
            is_topic=False,
            host_mode="monologue",
        )
        assert content in prompt
        if language == "nb-NO":
            assert "alle replikker tilhører Host 1" in prompt
            assert "vekslende replikker" not in prompt
        else:
            assert "all turns belong to Host 1" in prompt
            assert "alternating turns" not in prompt

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    def test_monologue_user_prompt_topic_mode(self, language):
        """Verify user prompt in topic mode enforces monologue format rule."""
        prompt = build_user_prompt(
            content="Quantum computing basics",
            language=language,
            is_topic=True,
            host_mode="monologue",
        )
        assert "Quantum computing basics" in prompt
        if language == "nb-NO":
            assert "alle replikker tilhører Host 1" in prompt
        else:
            assert "all turns belong to Host 1" in prompt


class TestBackwardCompatibilityDialogueMode:
    """Milestone 2: Verify default parameters preserve 100% backward compatibility."""

    def test_build_system_prompt_default_is_dialogue(self):
        prompt_default = build_system_prompt(language="nb-NO", format_type="standard")
        prompt_explicit = build_system_prompt(
            language="nb-NO", format_type="standard", host_mode="dialogue"
        )
        assert prompt_default == prompt_explicit
        assert "Host 2" in prompt_default

    def test_build_user_prompt_default_is_dialogue(self):
        prompt_default = build_user_prompt(content="Test content", language="en-US")
        prompt_explicit = build_user_prompt(
            content="Test content", language="en-US", host_mode="dialogue"
        )
        assert prompt_default == prompt_explicit
        assert "alternating turns" in prompt_default

    def test_get_act_specs_default_is_dialogue(self):
        specs_default = get_act_specs("deep_dive", language="nb-NO")
        specs_explicit = get_act_specs("deep_dive", language="nb-NO", host_mode="dialogue")
        assert specs_default == specs_explicit
        assert len(specs_default) == 3  # Dialogue deep_dive has 3 acts

    def test_build_act_system_prompt_default_is_dialogue(self):
        act = get_act_specs("standard", language="nb-NO")[0]
        prompt_default = build_act_system_prompt(act=act, total_acts=2, language="nb-NO")
        prompt_explicit = build_act_system_prompt(
            act=act, total_acts=2, language="nb-NO", host_mode="dialogue"
        )
        assert prompt_default == prompt_explicit
        assert "Host 2" in prompt_default

    def test_build_act_user_prompt_default_is_dialogue(self):
        prompt_default = build_act_user_prompt(content="Test content", language="nb-NO")
        prompt_explicit = build_act_user_prompt(
            content="Test content", language="nb-NO", host_mode="dialogue"
        )
        assert prompt_default == prompt_explicit
        assert "alle replikker tilhører Host 1" not in prompt_default
