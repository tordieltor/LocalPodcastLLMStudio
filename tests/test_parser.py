"""
Tests for 6-Tier Resilient Dialogue Parser (core/parser.py)
===========================================================
Covers Tiers 1 and 2:
- Tier 1: Pure direct JSON array parsing
- Tier 2: Markdown code fence stripping (```json ... ``` and ``` ... ```)
- Tier 3: Substring bounds trimming (finding outer [ ... ])
- Tier 4: Syntax sanitization (trailing commas, single quotes, unescaped control chars)
- Tier 5: Line-by-line regex object extractor
- Tier 6: Plain-text transcript fallback salvager (Host 1:, Kari:, Jenny:, etc.)
- Speaker name normalization (Kari/Jenny -> Host 1, Ola/Guy -> Host 2)
- Exception handling for completely unparseable input
"""

import pytest

from core.parser import DialogueParser


class TestParserSixTiers:
    """Tests covering all 6 fallback tiers of the resilient parser."""

    def test_tier1_pure_json(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["pure_json"])
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[0].text == "Welcome to the show!"
        assert turns[1].speaker == "Host 2"
        assert turns[1].text == "Glad to be here, Jenny!"

    def test_tier2_markdown_fenced_json(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["markdown_fenced"])
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[1].speaker == "Host 2"

    def test_tier2_markdown_fenced_no_lang(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["fenced_no_lang"])
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"

    def test_tier3_substring_bounds_trimming(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["preamble_and_postamble"])
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"  # Kari normalized to Host 1
        assert "Hei og velkommen!" in turns[0].text
        assert turns[1].speaker == "Host 2"  # Ola normalized to Host 2

    def test_tier4_trailing_commas(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["trailing_commas"])
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[1].speaker == "Host 2"

    def test_tier4_single_quotes(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["single_quotes"])
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[1].speaker == "Host 2"

    def test_tier5_regex_object_extraction(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["broken_brackets_regex"])
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert "First line of dialogue." in turns[0].text
        assert turns[1].speaker == "Host 2"
        assert "Second line answering" in turns[1].text

    def test_tier6_plain_text_transcript_english(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["plain_text_transcript"])
        assert len(turns) == 4
        assert turns[0].speaker == "Host 1"
        assert "Welcome to the episode" in turns[0].text
        assert turns[1].speaker == "Host 2"
        assert turns[2].speaker == "Host 1"
        assert turns[3].speaker == "Host 2"

    def test_tier6_plain_text_transcript_norwegian(self, llm_output_cases):

        turns = DialogueParser.parse(llm_output_cases["norwegian_plain_transcript"])
        assert len(turns) == 4
        assert turns[0].speaker == "Host 1"
        assert "Hei og velkommen" in turns[0].text
        assert turns[1].speaker == "Host 2"
        assert "Ola" in llm_output_cases["norwegian_plain_transcript"]


class TestParserSpeakerNormalizationAndValidation:
    """Tests speaker normalization and error handling."""

    @pytest.mark.parametrize(
        "raw_speaker,expected",
        [
            ("Host 1", "Host 1"),
            ("host 1", "Host 1"),
            ("HOST 1", "Host 1"),
            ("Host 2", "Host 2"),
            ("host 2", "Host 2"),
            ("Kari", "Host 1"),
            ("kari", "Host 1"),
            ("Ola", "Host 2"),
            ("ola", "Host 2"),
            ("Jenny", "Host 1"),
            ("Guy", "Host 2"),
        ],
    )
    def test_speaker_normalization(self, raw_speaker, expected):

        json_str = f'[{{"speaker": "{raw_speaker}", "text": "Testing speaker normalization."}}]'
        turns = DialogueParser.parse(json_str)
        assert len(turns) == 1
        assert turns[0].speaker == expected

    def test_empty_input_raises_error(self):

        with pytest.raises((ValueError, Exception)):
            DialogueParser.parse("")

    def test_whitespace_only_raises_error(self):

        with pytest.raises((ValueError, Exception)):
            DialogueParser.parse("   \n\t   ")

    def test_unparseable_gibberish_raises_error(self):

        gibberish = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Completely unrelated prose without speakers."
        with pytest.raises((ValueError, Exception)):
            DialogueParser.parse(gibberish)


class TestMonologueSpeakerNormalizationMatrix:
    """Milestone 2: Speaker normalization matrix for solo and dialogue personas."""

    @pytest.mark.parametrize(
        "raw_speaker,expected",
        [
            ("Host 1", "Host 1"),
            ("host 1", "Host 1"),
            ("HOST 1", "Host 1"),
            ("Host 1 (Kari)", "Host 1"),
            ("Host 1 (Jenny)", "Host 1"),
            ("Host (Kari)", "Host 1"),
            ("Host (Jenny)", "Host 1"),
            ("Host", "Host 1"),
            ("host", "Host 1"),
            ("Narrator", "Host 1"),
            ("narrator", "Host 1"),
            ("Speaker", "Host 1"),
            ("speaker", "Host 1"),
            ("Presenter", "Host 1"),
            ("presenter", "Host 1"),
            ("Solo Host", "Host 1"),
            ("solo host", "Host 1"),
            ("Solo", "Host 1"),
            ("solo", "Host 1"),
            ("Kari", "Host 1"),
            ("kari", "Host 1"),
            ("Jenny", "Host 1"),
            ("jenny", "Host 1"),
            ("Vert", "Host 1"),
            ("vert", "Host 1"),
            ("Forteller", "Host 1"),
            ("Oppleser", "Host 1"),
            ("Programleder", "Host 1"),
            ("Host 2", "Host 2"),
            ("host 2", "Host 2"),
            ("HOST 2", "Host 2"),
            ("Host 2 (Ola)", "Host 2"),
            ("Host 2 (Guy)", "Host 2"),
            ("Ola", "Host 2"),
            ("Guy", "Host 2"),
            ("Speaker 2", "Host 2"),
            ("Vert 2", "Host 2"),
            ("Programleder 2", "Host 2"),
            ("", "Host 1"),
            ("   ", ""),
            ("Guest Expert", "Guest Expert"),
        ],
    )
    def test_speaker_normalization_matrix(self, raw_speaker, expected):
        from core.parser import normalize_speaker

        assert normalize_speaker(raw_speaker) == expected


class TestMonologueSixTiers:
    """Milestone 2: 6-Tier parsing tests specifically for monologue / audio essay structures."""

    def test_tier1_monologue_solo_personas_json(self):
        json_str = '[{"speaker": "Narrator", "text": "Para 1"}, {"speaker": "Solo Host", "text": "Para 2"}]'
        turns = DialogueParser.parse(json_str)
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[0].text == "Para 1"
        assert turns[1].speaker == "Host 1"
        assert turns[1].text == "Para 2"

    def test_tier1_monologue_missing_speaker_field(self):
        json_str = '[{"text": "First audio essay paragraph."}, {"text": "Second paragraph exploring mechanics."}]'
        turns = DialogueParser.parse(json_str)
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[0].text == "First audio essay paragraph."
        assert turns[1].speaker == "Host 1"
        assert turns[1].text == "Second paragraph exploring mechanics."

    def test_tier1_monologue_raw_string_array(self):
        json_str = (
            '["Opening introductory paragraph.", "Core in-depth analysis.", "Concluding sign-off."]'
        )
        turns = DialogueParser.parse(json_str)
        assert len(turns) == 3
        for t in turns:
            assert t.speaker == "Host 1"
        assert turns[0].text == "Opening introductory paragraph."
        assert turns[2].text == "Concluding sign-off."

    @pytest.mark.parametrize(
        "wrapper_key", ["monologue", "essay", "audio_essay", "paragraphs", "sections"]
    )
    def test_tier1_monologue_root_wrapper_dicts(self, wrapper_key):
        json_str = (
            f'{{"{wrapper_key}": [{{"text": "Intro paragraph."}}, {{"text": "Outro paragraph."}}]}}'
        )
        turns = DialogueParser.parse(json_str)
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[0].text == "Intro paragraph."
        assert turns[1].speaker == "Host 1"
        assert turns[1].text == "Outro paragraph."

    def test_tier2_monologue_code_fence(self):
        fence_str = """```json
[
  {"speaker": "Host", "text": "First fenced paragraph."},
  {"speaker": "Host", "text": "Second fenced paragraph."}
]
```"""
        turns = DialogueParser.parse(fence_str)
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[1].speaker == "Host 1"

    def test_tier3_monologue_bounds_trimming(self):
        raw = """Here is the audio essay you requested:
[
  {"speaker": "Presenter", "text": "Welcome to our comprehensive audio documentary."},
  {"speaker": "Presenter", "text": "Let us examine the foundational data."}
]
I hope this format suits your broadcast!"""
        turns = DialogueParser.parse(raw)
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert turns[1].speaker == "Host 1"

    def test_tier4_monologue_syntax_sanitization(self):
        raw = """[
  {'speaker': 'Solo Host', 'text': 'First audio essay paragraph.'},
  {'speaker': 'Solo Host', 'text': 'Second paragraph with trailing comma',},
]"""
        turns = DialogueParser.parse(raw)
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert "First audio essay paragraph." in turns[0].text
        assert turns[1].speaker == "Host 1"

    def test_tier5_monologue_single_key_objects(self):
        raw = """{"text": "First stream chunk paragraph without array brackets."}
{"text": "Second stream chunk paragraph."}"""
        turns = DialogueParser.parse(raw)
        assert len(turns) == 2
        assert turns[0].speaker == "Host 1"
        assert "First stream chunk" in turns[0].text
        assert turns[1].speaker == "Host 1"
        assert "Second stream chunk" in turns[1].text

    def test_tier6_monologue_plain_text_norwegian(self):
        raw = """**Host (Kari):** Hei alle sammen, og velkommen til dette lydessayet.
I dag skal vi dykke dypt ned i de samfunnsmessige konsekvensene.

**Forteller:** For å forstå hele bildet, må vi se på historien bak reformen.
Det var nemlig i 2015 at de første grepene ble tatt.

Oppleser: Dette leder oss til de avgjørende konklusjonene."""
        turns = DialogueParser.parse(raw)
        assert len(turns) == 3
        for t in turns:
            assert t.speaker == "Host 1"
        assert "Hei alle sammen" in turns[0].text
        assert "konsekvensene" in turns[0].text
        assert "historien bak reformen" in turns[1].text
        assert "avgjørende konklusjonene" in turns[2].text

    def test_tier6_monologue_plain_text_english(self):
        raw = """Host: Welcome to today's solo audio essay.
Today, we explore the intricate dynamics of quantum algorithms.

Narrator: To unpack this dilemma, we must understand the core physics.

Presenter: In conclusion, the road ahead is full of potential."""
        turns = DialogueParser.parse(raw)
        assert len(turns) == 3
        for t in turns:
            assert t.speaker == "Host 1"
        assert "Welcome to today's solo" in turns[0].text
        assert "core physics" in turns[1].text
        assert "In conclusion" in turns[2].text


class TestDialogueToMarkdown:
    """Milestone 2: Markdown transcript formatting for dialogue and monologue modes."""

    def test_dialogue_to_markdown_dialogue_nb(self):
        from core.parser import DialogueTurn, dialogue_to_markdown

        turns = [
            DialogueTurn(speaker="Host 1", text="Hei Kari her."),
            DialogueTurn(speaker="Host 2", text="Hei Ola her."),
        ]
        md = dialogue_to_markdown(turns, language="nb-NO", host_mode="dialogue")
        assert "**Host 1 (Kari)**: Hei Kari her." in md
        assert "**Host 2 (Ola)**: Hei Ola her." in md

    def test_dialogue_to_markdown_dialogue_en(self):
        from core.parser import DialogueTurn, dialogue_to_markdown

        turns = [
            DialogueTurn(speaker="Host 1", text="Jenny here."),
            DialogueTurn(speaker="Host 2", text="Guy here."),
        ]
        md = dialogue_to_markdown(turns, language="en-US", host_mode="dialogue")
        assert "**Host 1 (Jenny)**: Jenny here." in md
        assert "**Host 2 (Guy)**: Guy here." in md

    def test_dialogue_to_markdown_monologue_nb(self):
        from core.parser import DialogueTurn, dialogue_to_markdown

        turns = [
            DialogueTurn(speaker="Host 1", text="Første avsnitt i lydessayet."),
            DialogueTurn(speaker="Host 1", text="Andre avsnitt i lydessayet."),
        ]
        md = dialogue_to_markdown(turns, language="nb-NO", host_mode="monologue")
        assert "**Host (Kari)**: Første avsnitt i lydessayet." in md
        assert "**Host (Kari)**: Andre avsnitt i lydessayet." in md
        assert "Host 1 (" not in md
        assert "Host 2 (" not in md

    def test_dialogue_to_markdown_monologue_en(self):
        from core.parser import DialogueTurn, dialogue_to_markdown

        turns = [
            DialogueTurn(speaker="Host 1", text="First audio essay paragraph."),
            DialogueTurn(speaker="Host 1", text="Second audio essay paragraph."),
        ]
        md = dialogue_to_markdown(turns, language="en-US", host_mode="monologue")
        assert "**Host (Jenny)**: First audio essay paragraph." in md
        assert "**Host (Jenny)**: Second audio essay paragraph." in md
        assert "Host 1 (" not in md
        assert "Host 2 (" not in md

    def test_dialogue_to_markdown_backward_compatibility(self):
        from core.parser import DialogueTurn, dialogue_to_markdown

        turns = [
            DialogueTurn(speaker="Host 1", text="Hello."),
            DialogueTurn(speaker="Host 2", text="Hi there."),
        ]
        md = dialogue_to_markdown(turns, language="en-US")
        assert "**Host 1 (Jenny)**: Hello." in md
        assert "**Host 2 (Guy)**: Hi there." in md
