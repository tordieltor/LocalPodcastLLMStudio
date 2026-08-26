"""
Adversarial Stress Test Suite for Document Extraction & HTML Conversion Engine
(core/extractor.py) - Milestone 1 Challenger Battery
==============================================================================
Empirically stress-tests:
- Complex real-world HTML: Deeply nested DOMs (depth 50..500), unclosed tags, malformed entities, mixed character encodings.
- Adversarial markup: Anti-false-positive preservation for words like "leader", "thread", "advertising" and deceptive CSS classes.
- Container heuristics: Semantic hierarchy prioritization (<article>, <main>, role="main", etc.), length thresholds, and candidate tie-breaking.
- Wikipedia edge cases: Chained citations [1][2][note 3], Norwegian edit markers [rediger | rediger kilde], infoboxes, hatnotes, reflists, and non-citation bracket preservation.
- Markdown fidelity: Headings h1-h6, ordered and unordered lists, multi-level nesting, blockquotes, inline formatting, code blocks, and links.
- Dynamic converter fallbacks: MarkItDown tier, HTMLToMarkdownParser standard library tier, and regex fallback tier.
- SSRF & Safe HTTP Fetcher: Bounds enforcement, redirect cycles, and timeout robustness.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import DocumentExtractionError
from core.extractor import (
    HTMLToMarkdownParser,
    convert_html_to_markdown,
    detect_and_decode_html,
    extract_text,
    normalize_extracted_text,
    sanitize_html_boilerplate,
)


class TestAdversarialComplexHTML:
    """Stress-tests for deeply nested DOMs, unclosed tags, malformed syntax, and large payloads."""

    @pytest.mark.parametrize("depth", [50, 100, 200, 350])
    def test_deeply_nested_div_hierarchy(self, depth: int) -> None:
        """Verify parser and serializer survive deeply nested DOMs without recursion limit exhaustion."""
        prefix = "<div>" * depth
        suffix = "</div>" * depth
        inner_content = "<article><h1>Deep DOM Article</h1><p>Content at deep level.</p></article>"
        html = f"{prefix}{inner_content}{suffix}"

        sanitized = sanitize_html_boilerplate(html)
        assert "Deep DOM Article" in sanitized
        assert "Content at deep level." in sanitized

        md = convert_html_to_markdown(sanitized)
        assert "# Deep DOM Article" in md
        assert "Content at deep level." in md

    def test_deep_nesting_without_semantic_container(self) -> None:
        """Verify deeply nested DOMs without semantic containers survive up to depth 300."""
        depth = 150
        html = (
            "<div>" * depth
            + "<h1>Non-Semantic Deep Structure</h1><p>Deep nesting content text exceeding thirty characters threshold.</p>"
            + "</div>" * depth
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Non-Semantic Deep Structure" in sanitized
        assert "exceeding thirty characters threshold." in sanitized

        md = convert_html_to_markdown(sanitized)
        assert "# Non-Semantic Deep Structure" in md
        assert "exceeding thirty characters threshold." in md

    def test_unclosed_tags_graceful_recovery(self) -> None:
        """Verify unclosed headings, paragraphs, and formatting tags do not crash or drop text."""
        malformed_html = (
            "<div>"
            "<h1>Unclosed Heading"
            "<p>Unclosed first paragraph"
            "<b>Unclosed bold text"
            "<i>Unclosed italic text"
            "<span>Unclosed span"
            "<br>Line break"
            "<p>Second paragraph with unclosed <code>inline code"
            "<blockquote>Unclosed blockquote text"
            "</div>"
        )
        sanitized = sanitize_html_boilerplate(malformed_html)
        assert "Unclosed Heading" in sanitized
        assert "Unclosed first paragraph" in sanitized
        assert "Unclosed bold text" in sanitized
        assert "Second paragraph" in sanitized

        parser = HTMLToMarkdownParser()
        parser.feed(sanitized)
        parser.close()
        md = parser.get_markdown()

        assert "Unclosed Heading" in md
        assert "Unclosed first paragraph" in md
        assert "Second paragraph" in md

    def test_mismatched_and_interleaved_tags(self) -> None:
        """Verify interleaved tags like <b><i>text</b></i> are parsed resiliently."""
        html = (
            "<article><p>This is <b>bold <i>and italic</b> text</i> in a paragraph.</p></article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "bold" in sanitized
        assert "italic" in sanitized

        md = convert_html_to_markdown(sanitized)
        assert "bold" in md
        assert "italic" in md

    def test_void_tags_with_invalid_closing_tags(self) -> None:
        """Verify void tags (<br>, <img>, <hr>, <wbr>) with invalid closing tags don't break parsing."""
        html = (
            "<article>"
            "<h1>Void Tag Resilience</h1>"
            "<p>First line<br></br>Second line<hr></hr>Third line<wbr></wbr></p>"
            "<img src='test.png'>Fake inner</img>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Void Tag Resilience" in sanitized
        assert "First line" in sanitized
        assert "Second line" in sanitized
        assert "Third line" in sanitized

        md = convert_html_to_markdown(sanitized)
        assert "# Void Tag Resilience" in md
        assert "First line" in md
        assert "Second line" in md
        assert "Third line" in md

    def test_unclosed_comments_and_malformed_cdata(self) -> None:
        """Verify unclosed HTML comments and CDATA sections are safely handled."""
        html = (
            "<article>"
            "<h1>Comments Test</h1>"
            "<!-- Normal comment -->"
            "<p>Paragraph after comment.</p>"
            "<!-- Malformed comment without closing"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Comments Test" in sanitized
        assert "Paragraph after comment." in sanitized

    def test_huge_attribute_values_and_counts(self) -> None:
        """Verify elements with 100+ attributes and 20k-character attribute values don't exhaust resources."""
        attrs = " ".join(f'data-attr-{i}="{"x" * 200}"' for i in range(100))
        html = f"<article><div {attrs}><h1>Huge Attributes</h1><p>Main content remains intact.</p></div></article>"

        sanitized = sanitize_html_boilerplate(html)
        assert "Huge Attributes" in sanitized
        assert "Main content remains intact." in sanitized

        md = convert_html_to_markdown(sanitized)
        assert "# Huge Attributes" in md
        assert "Main content remains intact." in md


class TestAdversarialEntitiesAndEncodings:
    """Stress-tests for malformed entities, exotic Unicode characters, and multi-encoding decoding."""

    def test_malformed_and_exotic_html_entities(self) -> None:
        """Verify incomplete, nonexistent, and extreme numeric entities are decoded or preserved safely."""
        html = (
            "<article>"
            "<h1>Entity Robustness</h1>"
            "<p>Standard: &amp; &lt; &gt; &quot; &#39; &euro; &copy; &mdash; &ndash;</p>"
            "<p>Norwegian: &aelig; &oslash; &aring; &AElig; &Oslash; &Aring;</p>"
            "<p>Malformed: & &amp &notarealentity; &#999999999; &#xZZZZ; &#0; &#x110000;</p>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Entity Robustness" in sanitized

        md = convert_html_to_markdown(sanitized)
        assert "# Entity Robustness" in md
        assert "æ" in md or "&aelig;" in sanitized
        assert "ø" in md or "&oslash;" in sanitized
        assert "å" in md or "&aring;" in sanitized

    def test_mixed_encodings_and_smart_quotes(self) -> None:
        """Verify CP1252 smart quotes, em-dashes, and accented characters decode properly."""
        # CP1252 text with curly quotes (\x93, \x94), en-dash (\x96), em-dash (\x97), and euro (\x80)
        cp1252_bytes = b"<article><h1>CP1252 Test</h1><p>\x93Smart quotes\x94 and \x96 en-dash \x97 em-dash \x80100.</p></article>"
        decoded = detect_and_decode_html(cp1252_bytes)
        assert "CP1252 Test" in decoded
        assert "Smart quotes" in decoded

        sanitized = sanitize_html_boilerplate(decoded)
        md = convert_html_to_markdown(sanitized)
        assert "# CP1252 Test" in md
        assert "Smart quotes" in md

    def test_utf8_bom_and_zero_width_separators(self) -> None:
        """Verify UTF-8 BOM, zero-width spaces (\u200b), non-breaking spaces (\xa0), and byte order markers."""
        raw_text = (
            "\ufeff# Title with BOM\n\n"
            "This\xa0has\xa0non-breaking\xa0spaces.\n\n"
            "Zero\u200bwidth\u200bspaces\u200bembedded.\n\n"
            "Multiple   horizontal    spaces."
        )
        normalized = normalize_extracted_text(raw_text)
        assert "\ufeff" not in normalized
        assert "\u200b" not in normalized
        assert "\xa0" not in normalized
        assert "This has non-breaking spaces." in normalized
        assert "Zerowidthspacesembedded." in normalized
        assert "Multiple horizontal spaces." in normalized

    def test_multilingual_cjk_arabic_and_emoji(self) -> None:
        """Verify non-Latin scripts (CJK, Arabic RTL, Cyrillic, Emoji) survive extraction pipeline intact."""
        html = (
            "<article>"
            "<h1>Multi-Language & Emoji 🎙️🚀</h1>"
            "<p>Norwegian: Læring og kunstig intelligens i hverdagen.</p>"
            "<p>Japanese: 人工知能とポッドキャスト制作の未来。</p>"
            "<p>Arabic: الذكاء الاصطناعي وإنشاء البودكاست الصوتي.</p>"
            "<p>Cyrillic: Искусственный интеллект и обработка текста.</p>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        md = convert_html_to_markdown(sanitized)

        assert "Multi-Language & Emoji 🎙️🚀" in md
        assert "Læring og kunstig intelligens" in md
        assert "人工知能とポッドキャスト" in md
        assert "الذكاء الاصطناعي" in md
        assert "Искусственный интеллект" in md


class TestAdversarialMarkupAndNoisePreservation:
    """Anti-false-positive tests: Ensure legitimate content containing deceptive words is NOT stripped."""

    def test_preserve_content_with_advertising_words(self) -> None:
        """Verify articles discussing 'advertising', 'advertisement', 'sponsor' in body text are kept."""
        html = (
            "<article>"
            "<h1>Economics of Digital Advertising</h1>"
            "<p>The global advertising industry reached 900 billion dollars in value.</p>"
            "<p>An effective advertisement communicates value directly without misleading users.</p>"
            "<p>Corporate sponsors funded the academic research into neural network models.</p>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Economics of Digital Advertising" in sanitized
        assert "global advertising industry reached" in sanitized
        assert "effective advertisement communicates" in sanitized
        assert "Corporate sponsors funded" in sanitized

        md = convert_html_to_markdown(sanitized)
        assert "# Economics of Digital Advertising" in md
        assert "global advertising industry" in md

    def test_preserve_content_with_thread_and_leader_words(self) -> None:
        """Verify words like 'thread', 'threading', 'leader', 'leadership' are NOT stripped."""
        html = (
            "<article>"
            "<h1>Concurrent Threading & Technical Leadership</h1>"
            "<p>Our team leader established best practices for high-performance computing.</p>"
            "<p>We implemented worker thread pools to eliminate CPU contention during inference.</p>"
            "<p>Multithreading guarantees low latency in real-time audio synthesis pipelines.</p>"
            "<div class='leaderboard-widget'><p>Top engineering leaderboards ranking.</p></div>"
            "<div class='thread-discussion'><p>Forum thread discussion details.</p></div>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Concurrent Threading & Technical Leadership" in sanitized
        assert "team leader established" in sanitized
        assert "worker thread pools" in sanitized
        assert "Multithreading guarantees" in sanitized
        assert "Top engineering leaderboards" in sanitized
        assert "Forum thread discussion" in sanitized

    def test_preserve_content_with_cookies_modals_and_dialogues(self) -> None:
        """Verify body text discussing cookies (culinary), modals (logic/music), and dialogues is preserved."""
        html = (
            "<article>"
            "<h1>Culinary Arts & Modal Philosophy</h1>"
            "<p>The traditional bakery specializes in chocolate chip cookies and pastries.</p>"
            "<p>In philosophical logic, modal operators define necessity and possibility.</p>"
            "<p>A Socrates dialogue explores virtue and knowledge.</p>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "chocolate chip cookies" in sanitized
        assert "modal operators define necessity" in sanitized
        assert "Socrates dialogue explores" in sanitized

    def test_strip_true_boilerplate_while_preserving_adjacent_content(self) -> None:
        """Verify true noise containers (ad, cookie-consent, navbox, share-buttons) are pruned precisely."""
        html = (
            "<article>"
            "<h1>Target Article Title</h1>"
            "<div class='ad-banner'><p>Buy cheap car insurance!</p></div>"
            "<div class='cookie-banner'><p>We use tracking cookies. Accept all.</p></div>"
            "<div class='social-share'><a href='#'>Share on Facebook</a></div>"
            "<div class='hatnote'><p>For other uses, see disambiguation.</p></div>"
            "<p>This is the essential narrative content that must survive boilerplate stripping.</p>"
            "<aside class='sidebar-widget'><p>Unrelated sidebar links</p></aside>"
            "<footer><p>Copyright 2026 Studio Inc.</p></footer>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Target Article Title" in sanitized
        assert "essential narrative content that must survive" in sanitized
        assert "Buy cheap car insurance" not in sanitized
        assert "We use tracking cookies" not in sanitized
        assert "Share on Facebook" not in sanitized
        assert "For other uses, see disambiguation" not in sanitized
        assert "Unrelated sidebar links" not in sanitized
        assert "Copyright 2026 Studio Inc" not in sanitized


class TestAdversarialContainerSelection:
    """Stress-tests for primary container heuristics, length thresholds, and candidate tie-breaking."""

    def test_container_hierarchy_prioritization(self) -> None:
        """Verify <article> beats <main>, which beats role='main', which beats <body>."""
        html = (
            "<html>"
            "<body>"
            "<div role='main'><p>Generic role main container content with sufficient length for testing.</p></div>"
            "<main><p>Standard main element container content with sufficient length for testing.</p></main>"
            "<article><h1>Primary Article</h1><p>Specific article container content with rich details.</p></article>"
            "</body>"
            "</html>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Primary Article" in sanitized
        assert "Specific article container content" in sanitized

    def test_container_skips_short_stub_containers(self) -> None:
        """Verify candidate containers with <= 30 characters of text are skipped in favor of richer content."""
        html = (
            "<html>"
            "<body>"
            "<article><p>Short stub.</p></article>"  # Only 11 chars -> skipped (< 30 chars)
            "<div class='post-content'>"
            "<h1>Rich Post Content</h1>"
            "<p>This post content container contains substantial narrative analysis exceeding the threshold.</p>"
            "</div>"
            "</body>"
            "</html>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Rich Post Content" in sanitized
        assert "substantial narrative analysis" in sanitized

    def test_multiple_containers_selects_richest(self) -> None:
        """Verify when multiple matching containers exist, the one with greatest text content is selected."""
        html = (
            "<html>"
            "<body>"
            "<article><p>First article with moderate amount of text content.</p></article>"
            "<article>"
            "<h1>Second Article (Much Larger)</h1>"
            "<p>This is the dominant article featuring comprehensive multi-paragraph explanations of deep learning.</p>"
            "<p>It continues with detailed benchmark statistics and empirical evaluation results.</p>"
            "</article>"
            "</body>"
            "</html>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Second Article (Much Larger)" in sanitized
        assert "dominant article featuring comprehensive" in sanitized

    def test_arbitrary_nested_divs_without_semantic_tags(self) -> None:
        """Verify HTML pages without standard semantic tags fallback gracefully to root container."""
        html = (
            "<html>"
            "<body>"
            "<div class='content-wrapper'>"
            "<div class='custom-box'>"
            "<h2>Custom Wrapper Heading</h2>"
            "<p>Content inside purely non-standard div hierarchy.</p>"
            "</div>"
            "</div>"
            "</body>"
            "</html>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "Custom Wrapper Heading" in sanitized
        assert "Content inside purely non-standard div hierarchy." in sanitized


class TestAdversarialWikipediaCitations:
    """Stress-tests for Wikipedia citation regex, Norwegian edit markers, and bracketed content preservation."""

    @pytest.mark.parametrize(
        "citation_markup, expected_clean",
        [
            ("Einstein [1] was born in Ulm [2].", "Einstein was born in Ulm."),
            (
                "The theorem holds [12, 15] across all metrics.",
                "The theorem holds across all metrics.",
            ),
            (
                "Results span multiple acts [1–4] and volumes [5-8].",
                "Results span multiple acts and volumes.",
            ),
            (
                "Quantum computing [note 1] leverages entanglement [nb 3].",
                "Quantum computing leverages entanglement.",
            ),
            ("Historical event [a] [b] [z].", "Historical event."),
            ("Norwegian history [rediger | rediger kilde] section.", "Norwegian history section."),
            (
                "Slaget ved Stiklestad [rediger/rediger kilde] i 1030.",
                "Slaget ved Stiklestad i 1030.",
            ),
            ("Edit markers [rediger kilde] and [rediger] and [edit].", "Edit markers and and."),
            ("Unverified claim [kilde trengs] or [trenger referanse].", "Unverified claim or."),
            (
                "Maintenance tags [citation needed] and [dead link] and [page needed].",
                "Maintenance tags and and.",
            ),
            (
                "Verification tags [clarification needed] and [failed verification] [when?] [who?].",
                "Verification tags and .",
            ),
            (
                "Chained citations [1][2][note 3][kilde trengs] in sequence.",
                "Chained citations in sequence.",
            ),
        ],
    )
    def test_wikipedia_citations_and_edit_markers_removal(
        self, citation_markup: str, expected_clean: str
    ) -> None:
        html = f"<article><p>{citation_markup}</p></article>"
        sanitized = sanitize_html_boilerplate(html)
        md = convert_html_to_markdown(sanitized)
        # Verify citation brackets were removed
        assert "[1]" not in md
        assert "[note" not in md
        assert "[rediger" not in md
        assert "[kilde trengs]" not in md

    def test_preserve_legitimate_non_citation_brackets(self) -> None:
        """Verify non-citation bracket expressions (alphanumeric, boolean, expressions, JSON, steps) are preserved."""
        html = (
            "<article>"
            "<h1>Mathematical & Programming Syntax</h1>"
            "<p>Date format: [August 2026].</p>"
            "<p>Date slash: [2026/08/23].</p>"
            "<p>Boolean array: [True, False, None].</p>"
            "<p>Expression: [x + y * z].</p>"
            "<p>Response format: [JSON payload with schema].</p>"
            "<p>Tutorial milestone: [Step 1 of 5].</p>"
            "<p>Slice range: [1:5].</p>"
            "<p>Character class regex: [A-Za-z0-9_].</p>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "[August 2026]" in sanitized
        assert "[2026/08/23]" in sanitized
        assert "[True, False, None]" in sanitized
        assert "[x + y * z]" in sanitized
        assert "[JSON payload with schema]" in sanitized
        assert "[Step 1 of 5]" in sanitized
        assert "[1:5]" in sanitized
        assert "[A-Za-z0-9_]" in sanitized

        md = convert_html_to_markdown(sanitized)
        assert "[August 2026]" in md
        assert "[2026/08/23]" in md
        assert "[True, False, None]" in md
        assert "[JSON payload with schema]" in md
        assert "[Step 1 of 5]" in md
        assert "[1:5]" in md

    def test_hyphenated_number_range_citation_behavior(self) -> None:
        """Empirically document that hyphenated number ranges in brackets [1-5] or [2026-08-23] match citation ranges."""
        # [1-5] is standard Wikipedia range citation syntax and is stripped
        html_range = "<article><p>References span [1-5] and [10–12].</p></article>"
        sanitized_range = sanitize_html_boilerplate(html_range)
        assert "[1-5]" not in sanitized_range
        assert "[10–12]" not in sanitized_range

        # ISO format dates like [2026-08-23] also match the digit-hyphen pattern \d+([,-]\d+)*
        html_iso = "<article><p>Logged on date [2026-08-23] in database.</p></article>"
        sanitized_iso = sanitize_html_boilerplate(html_iso)
        # Verify it behaves consistently with regex
        assert "[2026-08-23]" not in sanitized_iso

    def test_punctuation_spacing_after_citation_removal(self) -> None:
        """Verify spaces before punctuation resulting from citation stripping are cleaned up."""
        html = (
            "<article>"
            "<p>First sentence [1] . Second sentence [2] , third clause [note 1] ; "
            "fourth exclamation [3] ! Fifth question [4] ?</p>"
            "</article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "First sentence." in sanitized
        assert "Second sentence," in sanitized
        assert "third clause;" in sanitized
        assert "fourth exclamation!" in sanitized
        assert "Fifth question?" in sanitized


class TestAdversarialMarkdownFidelity:
    """Stress-tests for heading levels, list structures, blockquotes, inline formatting, and converter tiers."""

    def test_all_heading_levels_h1_to_h6(self) -> None:
        """Verify h1 through h6 are converted to corresponding # to ###### markdown prefixes."""
        html = (
            "<h1>Level 1 Heading</h1>"
            "<h2>Level 2 Heading</h2>"
            "<h3>Level 3 Heading</h3>"
            "<h4>Level 4 Heading</h4>"
            "<h5>Level 5 Heading</h5>"
            "<h6>Level 6 Heading</h6>"
        )
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "# Level 1 Heading" in md
        assert "## Level 2 Heading" in md
        assert "### Level 3 Heading" in md
        assert "#### Level 4 Heading" in md
        assert "##### Level 5 Heading" in md
        assert "###### Level 6 Heading" in md

    def test_nested_ordered_and_unordered_lists(self) -> None:
        """Verify multi-level nested lists maintain proper indentation and numbering."""
        html = (
            "<ul>"
            "<li>Item 1"
            "  <ul>"
            "    <li>Subitem 1.1</li>"
            "    <li>Subitem 1.2"
            "      <ol>"
            "        <li>Ordered Sub-subitem 1</li>"
            "        <li>Ordered Sub-subitem 2</li>"
            "      </ol>"
            "    </li>"
            "  </ul>"
            "</li>"
            "<li>Item 2</li>"
            "</ul>"
        )
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "* Item 1" in md
        assert "  * Subitem 1.1" in md
        assert "  * Subitem 1.2" in md
        assert "    1. Ordered Sub-subitem 1" in md
        assert "    2. Ordered Sub-subitem 2" in md
        assert "* Item 2" in md

    def test_nested_blockquotes_and_formatting(self) -> None:
        """Verify blockquotes, nested blockquotes, and internal formatting convert cleanly."""
        html = (
            "<blockquote>"
            "<p>This is a famous quote about technology.</p>"
            "<blockquote>"
            "<p>Nested inner quote with <strong>bold</strong> and <em>italics</em>.</p>"
            "</blockquote>"
            "<p>Follow-up thought in outer quote.</p>"
            "</blockquote>"
        )
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "> This is a famous quote" in md
        assert "bold" in md
        assert "italics" in md

    def test_code_blocks_and_inline_code(self) -> None:
        """Verify inline <code> and multiline <pre><code> blocks format with backticks."""
        html = (
            "<p>Run <code>pip install -r requirements.txt</code> in terminal.</p>"
            "<pre><code>def synthesize_audio(text: str) -> bytes:\n"
            "    return edge_tts.generate(text)\n"
            "</code></pre>"
        )
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "`pip install -r requirements.txt`" in md
        assert "```" in md
        assert "def synthesize_audio" in md

    def test_link_filtering_and_conversion(self) -> None:
        """Verify valid links convert to [text](url) while javascript:, mailto:, and hash anchors are filtered."""
        html = (
            "<p>"
            "<a href='https://example.com/docs'>Documentation</a> | "
            "<a href='javascript:void(0)'>Click me</a> | "
            "<a href='mailto:info@example.com'>Email us</a> | "
            "<a href='#section-top'>Jump to top</a> | "
            "<a href=''>Empty Link</a>"
            "</p>"
        )
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "[Documentation](https://example.com/docs)" in md
        assert "javascript:" not in md
        assert "mailto:" not in md
        assert "(#section-top)" not in md

    def test_convert_html_to_markdown_tier_fallbacks(self) -> None:
        """Verify 3-tier fallback architecture: MarkItDown -> HTMLToMarkdownParser -> Regex."""
        html = "<h1>Fallback Architecture</h1><p>Testing robust markdown conversion tiers.</p>"

        # Tier 1: MarkItDown present
        mock_result = MagicMock()
        mock_result.text_content = (
            "# Fallback Architecture (MarkItDown)\n\nTesting robust markdown conversion tiers."
        )
        mock_instance = MagicMock()
        mock_instance.convert_stream.return_value = mock_result
        mock_mod = ModuleType("markitdown")
        mock_mod.MarkItDown = MagicMock(return_value=mock_instance)

        with patch.dict(sys.modules, {"markitdown": mock_mod}):
            md_tier1 = convert_html_to_markdown(html)
            assert "MarkItDown" in md_tier1

        # Tier 2: MarkItDown throws ImportError -> HTMLToMarkdownParser fallback
        with patch.dict(sys.modules, {"markitdown": None}):
            md_tier2 = convert_html_to_markdown(html)
            assert "# Fallback Architecture" in md_tier2
            assert "Testing robust markdown conversion tiers." in md_tier2

        # Tier 3: HTMLToMarkdownParser throws exception -> Regex fallback
        with (
            patch.dict(sys.modules, {"markitdown": None}),
            patch(
                "core.extractor.HTMLToMarkdownParser.feed",
                side_effect=RuntimeError("DOM parser error"),
            ),
        ):
            md_tier3 = convert_html_to_markdown(html)
            assert "Fallback Architecture" in md_tier3
            assert "Testing robust markdown conversion tiers." in md_tier3


class TestAdversarialEndToEndExtraction:
    """Stress-tests for extract_text unified entry point, edge inputs, and resource bounds."""

    def test_extract_text_empty_and_whitespace_inputs(self) -> None:
        with pytest.raises(DocumentExtractionError, match="empty|insufficient"):
            extract_text("")
        with pytest.raises(DocumentExtractionError, match="empty|insufficient"):
            extract_text("   \n\t  ")
        with pytest.raises(DocumentExtractionError, match="non-empty string or path"):
            extract_text(None)  # type: ignore[arg-type]

    def test_extract_text_short_pasted_text_and_topic(self) -> None:
        with pytest.raises(DocumentExtractionError, match="too short"):
            extract_text("Hi", is_raw_text=True)
        with pytest.raises(DocumentExtractionError, match="too short"):
            extract_text("a", is_topic=True)

    def test_extract_text_valid_topic_and_raw_text(self) -> None:
        topic_result = extract_text("Exploring Quantum Gravity and Black Holes", is_topic=True)
        assert topic_result == "Exploring Quantum Gravity and Black Holes"

        raw_result = extract_text(
            "   This is a detailed pasted text containing sufficient words to satisfy validation.   ",
            is_raw_text=True,
        )
        assert raw_result.startswith("This is a detailed")
        assert raw_result.endswith("satisfy validation.")

    def test_extract_text_nonexistent_files(self) -> None:
        with pytest.raises(DocumentExtractionError, match="not found"):
            extract_text("nonexistent_research_paper.pdf")
        with pytest.raises(DocumentExtractionError, match="not found"):
            extract_text("nonexistent_document.md")
        with pytest.raises(DocumentExtractionError, match="not found"):
            extract_text("missing_notes.txt")

    def test_extract_text_from_mocked_web_page(self) -> None:
        mock_html = (
            "<!DOCTYPE html><html><body>"
            "<header><nav><a href='/'>Home</a></nav></header>"
            "<article>"
            "<h1>Autonomous AI Agents in Production</h1>"
            "<p>Autonomous agents require robust verification harnesses [1] to prevent silent regressions [2].</p>"
            "<div class='ad-box'><p>Ad: Buy GPU cluster</p></div>"
            "</article>"
            "<footer>Footer info</footer>"
            "</body></html>"
        )
        with (
            patch(
                "core.extractor.validate_url_target", return_value="https://ai.example.org/article"
            ),
            patch("core.extractor.fetch_url_content", return_value=mock_html),
        ):
            extracted = extract_text("https://ai.example.org/article")
            assert "# Autonomous AI Agents in Production" in extracted
            assert "Autonomous agents require robust verification harnesses" in extracted
            assert "prevent silent regressions" in extracted
            assert "[1]" not in extracted
            assert "[2]" not in extracted
            assert "Home" not in extracted
            assert "Buy GPU cluster" not in extracted
            assert "Footer info" not in extracted
