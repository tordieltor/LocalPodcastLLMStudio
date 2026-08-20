"""
Tests for Prompt Generation Engine (core/prompts.py)
====================================================
Covers Tiers 1 and 3:
- Bilingual system prompt generation (Norwegian Bokmål vs English)
- Persona assignments: Kari & Ola (nb-NO), Jenny & Guy (en-US)
- 4 Episode length presets: Quick Summary (6-8), Standard (12-16), Deep Dive (20-26), Extended In-Depth (45-60)
- Backward compatibility for legacy format names ("short", "deep_dive")
- 3 Dialogue tone presets: Casual & Lively, Analytical & Educational, Lively Debate
- Document-driven vs. Scratch Topic prompt formatting
- Strict JSON grammar and alternating host requirements
- Combinatorial verification across the full Language x Format x Tone matrix
"""

import pytest

try:
    from core.prompts import (
        build_system_prompt,
        build_user_prompt,
        get_tone_description,
        get_format_config,
        FORMAT_PRESETS,
    )
except ImportError:
    pass


class TestPromptsBilingualAndPersonas:
    """Tier 1: Feature coverage for language personas and tone descriptions."""

    def test_norwegian_system_prompt_personas(self):
        from core.prompts import build_system_prompt
        prompt = build_system_prompt(language="nb-NO", format_type="standard", tone_style="casual")
        assert "Kari" in prompt
        assert "Ola" in prompt
        assert "norsk" in prompt.lower() or "bokmål" in prompt.lower()
        assert "Host 1" in prompt
        assert "Host 2" in prompt
        assert "JSON" in prompt

    def test_english_system_prompt_personas(self):
        from core.prompts import build_system_prompt
        prompt = build_system_prompt(language="en-US", format_type="standard", tone_style="casual")
        assert "Jenny" in prompt
        assert "Guy" in prompt
        assert "Host 1" in prompt
        assert "Host 2" in prompt
        assert "JSON" in prompt

    @pytest.mark.parametrize("tone_key,expected_snippet", [
        ("casual", "Casual"),
        ("analytical", "Analytical"),
        ("debate", "Debate"),
    ])
    def test_tone_descriptions_english(self, tone_key, expected_snippet):
        from core.prompts import get_tone_description
        desc = get_tone_description(tone_key, language="en-US")
        assert len(desc) > 0
        assert expected_snippet.lower() in desc.lower() or "conversational" in desc.lower() or "analytical" in desc.lower() or "debate" in desc.lower()

    @pytest.mark.parametrize("tone_key", ["casual", "analytical", "debate"])
    def test_tone_descriptions_norwegian(self, tone_key):
        from core.prompts import get_tone_description
        desc = get_tone_description(tone_key, language="nb-NO")
        assert len(desc) > 0


class TestPromptsFourEpisodeFormats:
    """Tier 1 & Tier 3: All 4 Episode Length presets + legacy support."""

    @pytest.mark.parametrize("fmt_key,min_turns,max_turns", [
        ("quick", 6, 8),
        ("quick_summary", 6, 8),
        ("standard", 12, 16),
        ("standard_episode", 12, 16),
        ("deep_dive", 20, 26),
        ("deep", 20, 26),
        ("extended", 45, 60),
        ("extended_in_depth", 45, 60),
    ])
    def test_target_turn_counts(self, fmt_key, min_turns, max_turns):
        from core.prompts import get_format_config
        cfg = get_format_config(fmt_key)
        assert cfg is not None
        assert "target_turns" in cfg
        assert min_turns <= cfg["min_turns"] <= cfg["max_turns"] <= max_turns

    def test_legacy_format_short_and_deep(self):
        from core.prompts import get_format_config
        # Legacy 'short' and 'deep_dive' should resolve smoothly
        short_cfg = get_format_config("short")
        assert short_cfg is not None
        assert short_cfg["min_turns"] >= 6
        deep_cfg = get_format_config("deep_dive")
        assert deep_cfg is not None
        assert deep_cfg["min_turns"] >= 14


class TestPromptsDocumentVsScratchTopic:
    """Tier 1: Document input mode vs. Scratch topic input mode."""

    def test_user_prompt_document_mode(self):
        from core.prompts import build_user_prompt
        doc_text = "Detailed quarterly report on renewable energy investments."
        prompt = build_user_prompt(content=doc_text, language="nb-NO", is_topic=False)
        assert doc_text in prompt
        assert "kildemateriale" in prompt.lower() or "source" in prompt.lower()

    def test_user_prompt_scratch_topic_mode(self):
        from core.prompts import build_user_prompt
        topic_text = "The emergence of quantum algorithms in cryptography"
        prompt = build_user_prompt(content=topic_text, language="en-US", is_topic=True)
        assert topic_text in prompt
        assert "topic" in prompt.lower() or "tema" in prompt.lower()


class TestPromptsCombinatorialMatrix:
    """Tier 3: Combinatorial validation across Languages x Formats x Tones."""

    @pytest.mark.parametrize("language", ["nb-NO", "en-US"])
    @pytest.mark.parametrize("format_type", ["quick", "standard", "deep_dive", "extended"])
    @pytest.mark.parametrize("tone_style", ["casual", "analytical", "debate"])
    def test_prompt_matrix_validity(self, language, format_type, tone_style):
        from core.prompts import build_system_prompt
        prompt = build_system_prompt(language=language, format_type=format_type, tone_style=tone_style)
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "Host 1" in prompt
        assert "Host 2" in prompt
        assert "JSON" in prompt
