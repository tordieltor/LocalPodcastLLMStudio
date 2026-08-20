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
