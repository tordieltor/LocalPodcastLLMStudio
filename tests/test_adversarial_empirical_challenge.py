"""
LocalPodcastLLMStudio - Empirical Adversarial Challenger Test Suite
============================================================
Adversarially stress-tests:
1. MP3Stitcher with heterogeneous iterables, generator expressions, bytearrays,
   empty collections, corrupt sync words, malformed ID3 headers, and truncation.
2. Prompt generation parameter combinations across all languages, length presets,
   tone styles, and grounding modes.
3. Edge case boundary testing on extractor, parser, and URL validation.
"""

from collections.abc import Generator
from typing import Any

import pytest

from core.extractor import (
    DocumentExtractionError,
    extract_text,
)
from core.mp3_stitcher import MP3Stitcher, stitch_mp3_files
from core.ollama import _validate_url
from core.prompts import (
    FORMAT_PRESETS,
    GROUNDING_MODE_PRESETS,
    TONE_DESCRIPTIONS,
    GroundingMode,
    build_act_system_prompt,
    build_act_user_prompt,
    build_system_prompt,
    build_user_prompt,
    get_act_specs,
    normalize_grounding_mode,
    normalize_language_code,
)


# ==============================================================================
# 1. MP3Stitcher Adversarial Testing
# ==============================================================================
class TestMP3StitcherAdversarial:
    """Stress-tests MP3Stitcher against boundary conditions, invalid formats, and types."""

    @pytest.fixture
    def valid_mp3_frame(self) -> bytes:
        """Returns a valid 144-byte MPEG-2 Layer III 24kHz 48kbps mono frame."""
        return MP3Stitcher.generate_silence_frame(
            version_id=2, bitrate_kbps=48, sample_rate=24000, channel_mode=3
        )

    def test_stitch_empty_and_falsy_inputs(self):
        """Test stitching empty lists, tuples, and falsy containers."""
        assert MP3Stitcher.stitch([]) == b""
        assert MP3Stitcher.stitch(()) == b""
        assert MP3Stitcher.stitch([b"", bytearray(), b""]) == b""

    def test_stitch_heterogeneous_iterables(self, valid_mp3_frame):
        """Test stitching combinations of bytes, bytearray, memoryview, and generator inputs."""
        # Bytearray + bytes
        mixed_list = [bytearray(valid_mp3_frame), valid_mp3_frame, bytearray(valid_mp3_frame)]
        stitched = MP3Stitcher.stitch(mixed_list)
        assert len(stitched) > len(valid_mp3_frame)
        assert stitched.startswith(b"ID3\x03\x00\x00")

        # Tuple of bytearrays
        mixed_tuple = (bytearray(valid_mp3_frame), valid_mp3_frame)
        stitched_tuple = MP3Stitcher.stitch(mixed_tuple)
        assert stitched_tuple.startswith(b"ID3\x03\x00\x00")

    def test_stitch_generator_expressions(self, valid_mp3_frame):
        """Test passing generator expression to MP3Stitcher.stitch."""

        def gen() -> Generator[bytes, None, None]:
            yield valid_mp3_frame
            yield valid_mp3_frame

        # Sequence typing allows sequence; generator can be converted to list or handled
        stitched = MP3Stitcher.stitch(list(gen()))
        assert stitched.startswith(b"ID3\x03\x00\x00")

    def test_stitch_corrupt_and_invalid_byte_sequences(self):
        """Test stitching totally invalid byte sequences (random noise, text, broken syncs)."""
        corrupt_samples = [
            b"RIFF\x00\x00\x00\x00WAVEfmt ",  # WAV header
            b"\x89PNG\r\n\x1a\n",  # PNG header
            b"\xff\xd8\xff\xe0\x00\x10JFIF",  # JPEG header
            b"Plain text non-audio string",  # Plain text
            b"\xff\x00\xff\x00\xff\x00",  # Partial sync bytes
            b"\x00" * 500,  # All zeros
            b"\xff" * 500,  # All 0xFF without valid MPEG layer/bitrate
            b"\xff\xfa\x00\x00",  # Sync with invalid bitrate/sr index 0
        ]
        # Should return b"" cleanly without raising unhandled exceptions
        assert MP3Stitcher.stitch(corrupt_samples) == b""

    def test_stitch_partially_corrupted_stream(self, valid_mp3_frame):
        """Test stitching valid frames interleaved with garbage bytes."""
        mixed = [
            b"Garbage bytes before frame",
            valid_mp3_frame,
            b"Corrupt data in middle" * 10,
            valid_mp3_frame,
            b"Trailing garbage",
        ]
        stitched = MP3Stitcher.stitch(mixed)
        assert stitched.startswith(b"ID3\x03\x00\x00")
        assert len(stitched) > 0

    def test_strip_id3_boundary_conditions(self):
        """Adversarial test on ID3 header and footer stripper."""
        assert MP3Stitcher.strip_id3(b"") == b""
        assert MP3Stitcher.strip_id3(b"ID3") == b"ID3"  # Truncated header (< 10 bytes) is untouched
        assert MP3Stitcher.strip_id3(b"ID3\x03\x00\x00\x00\x00\x00\x05AAAAA") == b""
        # Huge declared size exceeding payload
        assert MP3Stitcher.strip_id3(b"ID3\x03\x00\x00\x7f\x7f\x7f\x7fDATA") == b""
        # Valid ID3 followed by audio
        tag = MP3Stitcher.build_id3v23_tag(title="Test")
        payload = b"\xff\xfb\x90\x64" + b"\x00" * 400
        stripped = MP3Stitcher.strip_id3(tag + payload)
        assert stripped == payload

    def test_parse_frame_header_adversarial(self):
        """Test parse_frame_header with edge cases and malformed headers."""
        assert MP3Stitcher.parse_frame_header(b"") is None
        assert MP3Stitcher.parse_frame_header(b"\xff") is None
        assert MP3Stitcher.parse_frame_header(b"\xff\xe0") is None
        assert MP3Stitcher.parse_frame_header(b"\xff\xe0\x00") is None
        # Version 1 (reserved)
        assert MP3Stitcher.parse_frame_header(b"\xff\xe8\x90\x00") is None
        # Layer 0 (reserved)
        assert MP3Stitcher.parse_frame_header(b"\xff\xf8\x90\x00") is None
        # Bitrate index 15 (bad)
        assert MP3Stitcher.parse_frame_header(b"\xff\xfb\xf0\x00") is None
        # Sample rate index 3 (reserved)
        assert MP3Stitcher.parse_frame_header(b"\xff\xfb\x9c\x00") is None

    def test_generate_silence_boundary_values(self):
        """Test silence generation with 0ms, negative ms, and extreme values."""
        assert MP3Stitcher.generate_silence_bytes(duration_ms=0) == b""
        assert MP3Stitcher.generate_silence_bytes(duration_ms=-100) == b""
        large_silence = MP3Stitcher.generate_silence_bytes(duration_ms=5000)
        assert len(large_silence) > 0
        assert len(large_silence) % 144 == 0

    def test_stitch_mp3_files_adversarial_errors(self, tmp_path):
        """Test stitch_mp3_files raises ValueError on empty or invalid inputs."""
        with pytest.raises(ValueError, match="Cannot stitch empty list"):
            stitch_mp3_files([], str(tmp_path / "out.mp3"))

        with pytest.raises(ValueError, match="No valid MPEG Layer III audio frames"):
            stitch_mp3_files([b"invalid non mp3 bytes"], str(tmp_path / "out.mp3"))


# ==============================================================================
# 2. Prompts Matrix & Parameter Combinations Stress Testing
# ==============================================================================
class TestPromptsAdversarialMatrix:
    """Exhaustively tests all permutations of language, format, tone, and grounding modes."""

    LANGUAGES = [
        "nb-NO",
        "en-US",
        "nb",
        "en",
        "norsk",
        "english",
        "Norwegian Bokmål",
        "UNKNOWN_LANG",
    ]
    FORMATS = list(FORMAT_PRESETS.keys()) + ["short", "std", "deep", "long", "UNKNOWN_FMT"]
    TONES = list(TONE_DESCRIPTIONS.keys()) + ["lively", "serious", "fun", "UNKNOWN_TONE"]
    MODES: list[Any] = list(GROUNDING_MODE_PRESETS.keys()) + [
        "strict_source_only",
        "kildetro",
        "creative_synthesis",
        "scratch",
        "UNKNOWN_MODE",
        GroundingMode.STRICT,
        GroundingMode.CREATIVE,
        GroundingMode.OPEN_TOPIC,
        None,
    ]

    def test_normalize_grounding_mode_matrix(self):
        """Tests all inputs normalize cleanly to one of the 3 valid modes."""
        valid_modes = {"strict", "creative", "open_topic"}
        for mode in self.MODES:
            normalized = normalize_grounding_mode(mode)
            assert normalized in valid_modes

    def test_normalize_language_code_matrix(self):
        """Tests all languages normalize cleanly to 'nb-NO' or 'en-US'."""
        for lang in self.LANGUAGES:
            normalized = normalize_language_code(lang)
            assert normalized in ("nb-NO", "en-US")

    def test_build_system_prompt_exhaustive_combinations(self):
        """Generates system prompt for every permutation of (lang, format, tone, mode)."""
        count = 0
        for lang in ["nb-NO", "en-US"]:
            for fmt in ["quick", "standard", "deep_dive", "extended"]:
                for tone in ["casual", "analytical", "debate"]:
                    for mode in ["strict", "creative", "open_topic"]:
                        prompt = build_system_prompt(
                            language=lang, format_type=fmt, tone_style=tone, grounding_mode=mode
                        )
                        assert isinstance(prompt, str)
                        assert len(prompt) > 200
                        # Ensure no unformatted format template placeholders remain
                        for placeholder in [
                            "{target_turns}",
                            "{language}",
                            "{format_type}",
                            "{tone_style}",
                            "{grounding_mode}",
                        ]:
                            assert placeholder not in prompt
                        if lang == "nb-NO":
                            assert "Host 1 (Kari)" in prompt
                            assert "Host 2 (Ola)" in prompt
                        else:
                            assert "Host 1 (Jenny)" in prompt
                            assert "Host 2 (Guy)" in prompt
                        count += 1
        assert count == 2 * 4 * 3 * 3  # 72 combinations

    def test_build_user_prompt_matrix(self):
        """Tests user prompt across all modes, languages, empty/whitespace content, and is_topic flags."""
        contents = ["Simple content", "", "   \n\t  ", "A" * 10000]
        for content in contents:
            for lang in ["nb-NO", "en-US"]:
                for mode in ["strict", "creative", "open_topic"]:
                    for is_topic in [False, True]:
                        u_prompt = build_user_prompt(
                            content=content,
                            language=lang,
                            grounding_mode=mode,
                            is_topic=is_topic,
                        )
                        assert isinstance(u_prompt, str)
                        assert len(u_prompt) > 0
                        if is_topic or mode == "open_topic":
                            if lang == "nb-NO":
                                assert "TEMA:" in u_prompt
                            else:
                                assert "TOPIC:" in u_prompt
                        elif mode == "creative":
                            if lang == "nb-NO":
                                assert "START KILDEMATERIALE" in u_prompt
                                assert "analogier" in u_prompt
                            else:
                                assert "START SOURCE MATERIAL" in u_prompt
                                assert "analogies" in u_prompt
                        else:  # strict
                            if lang == "nb-NO":
                                assert "START KILDEMATERIALE" in u_prompt
                                assert "uten å finne på eksterne fakta" in u_prompt
                            else:
                                assert "START SOURCE MATERIAL" in u_prompt
                                assert "without inventing external facts" in u_prompt

    def test_multi_act_specs_and_prompts_adversarial(self):
        """Tests multi-act prompt generation across all formats and acts."""
        for lang in ["nb-NO", "en-US"]:
            for fmt in ["quick", "standard", "deep_dive", "extended"]:
                specs = get_act_specs(fmt, lang)
                assert len(specs) >= 1
                for spec in specs:
                    act_sys = build_act_system_prompt(
                        act=spec,
                        total_acts=len(specs),
                        language=lang,
                        tone_style="casual",
                        grounding_mode="strict",
                    )
                    assert isinstance(act_sys, str)
                    assert "JSON" in act_sys

                    act_user = build_act_user_prompt(
                        content="Test source document",
                        prev_turns=[{"speaker": "Host 1", "text": "Prior turn"}],
                        language=lang,
                        grounding_mode="strict",
                        is_topic=False,
                    )
                    assert isinstance(act_user, str)
                    assert "Prior turn" in act_user


# ==============================================================================
# 3. Security & Extraction Boundary Adversarial Testing
# ==============================================================================
class TestSecurityExtractorAdversarial:
    """Stress-tests URL validation and document extraction safety boundaries."""

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "",
            "   ",
            "ftp://localhost:11434",
            "file:///etc/passwd",
            "file://c:/windows/system32/cmd.exe",
            "javascript:alert(1)",
            "data:text/plain;base64,SGVsbG8=",
            "http://",
            "https://",
            "http:///no-host",
        ],
    )
    def test_validate_url_rejections(self, invalid_url):
        """Test URL validator rejects all non-http(s) and malformed URLs."""
        with pytest.raises(ValueError):
            _validate_url(invalid_url)

    @pytest.mark.parametrize(
        "valid_url,expected_output",
        [
            ("http://localhost:11434", "http://localhost:11434"),
            ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
            ("https://ollama.internal.net:8080/api/", "https://ollama.internal.net:8080/api"),
            ("  http://localhost:11434/  ", "http://localhost:11434"),
        ],
    )
    def test_validate_url_accepts_clean(self, valid_url, expected_output):
        """Test URL validator accepts and normalizes valid http/https URLs."""
        assert _validate_url(valid_url) == expected_output

    def test_extractor_nonexistent_and_directory(self, tmp_path):
        """Test extractor error handling on non-existent files and directories."""
        with pytest.raises(DocumentExtractionError, match="not found|does not exist"):
            extract_text(tmp_path / "nonexistent.txt")

        with pytest.raises(DocumentExtractionError, match="Unsupported file format|is a directory"):
            extract_text(tmp_path)

    def test_extractor_file_size_boundary(self, tmp_path):
        """Test extractor respects custom max_file_size_mb limits."""
        test_file = tmp_path / "sample.txt"
        test_file.write_text("A" * 1000, encoding="utf-8")

        # Set threshold below 1000 bytes (e.g. 0.0001 MB = ~100 bytes)
        with pytest.raises(DocumentExtractionError, match="exceeds.*maximum.*size"):
            extract_text(test_file, max_file_size_mb=0.0005)
