"""
Tests for Zero-FFmpeg MP3 Binary Stitcher (core/mp3_stitcher.py)
================================================================
Covers Tiers 1 and 2:
- ID3v2 synchsafe header parsing & stripping
- ID3v1 trailing tag stripping
- MPEG Audio Layer III frame header parsing & sync detection (0xFFE0)
- Extracting clean audio frames from raw buffers
- Programmatic MPEG silence frame & byte sequence synthesis
- Minimal valid ID3v2.3 tag creation
- Multi-turn binary stitching with inter-turn pause injection
- File-to-file stitching verification
"""

import os

import pytest

from core.mp3_stitcher import MP3Stitcher, stitch_mp3_files, validate_safe_output_path


class TestMP3StitcherHeadersAndFrames:
    """Tier 1: MPEG header parsing and ID3 tag manipulation."""

    def test_strip_id3v2_tag(self, synthetic_mp3_factory):

        raw_mp3 = synthetic_mp3_factory(num_frames=3, include_id3v2=True, include_id3v1=False)
        assert raw_mp3[:3] == b"ID3"

        stripped = MP3Stitcher.strip_id3(raw_mp3)
        assert stripped[:3] != b"ID3"
        # First byte of clean MPEG frame must be 0xFF
        assert stripped[0] == 0xFF

    def test_strip_id3v1_tag(self, synthetic_mp3_factory):

        raw_mp3 = synthetic_mp3_factory(num_frames=3, include_id3v2=False, include_id3v1=True)
        assert raw_mp3[-128:-125] == b"TAG"

        stripped = MP3Stitcher.strip_id3(raw_mp3)
        assert len(stripped) < len(raw_mp3)
        assert stripped[-128:-125] != b"TAG"

    def test_parse_frame_header_valid(self, single_frame_mp3):

        res = MP3Stitcher.parse_frame_header(single_frame_mp3[:4])
        assert res is not None
        frame_len, version_id, bitrate, sample_rate = res
        assert frame_len == len(single_frame_mp3)
        assert bitrate == 32
        assert sample_rate == 24000

    def test_parse_frame_header_invalid_sync(self):

        bad_header = b"\x00\x00\x00\x00"
        res = MP3Stitcher.parse_frame_header(bad_header)
        assert res is None

    def test_extract_audio_frames(self, synthetic_mp3_factory):

        raw_mp3 = synthetic_mp3_factory(num_frames=4, include_id3v2=True, include_id3v1=True)
        frames_res = MP3Stitcher.extract_audio_frames(raw_mp3)
        if isinstance(frames_res, tuple):
            frames, header_info = frames_res
        else:
            frames = frames_res

        assert len(frames) > 0
        assert frames[0] == 0xFF
        assert frames[1] & 0xE0 == 0xE0


class TestMP3StitcherAssemblyAndExport:
    """Tier 2: Silence injection, ID3 tag writing, and full audio stitching."""

    def test_generate_silence_frame(self):

        silence = MP3Stitcher.generate_silence_frame()
        assert len(silence) == 144
        assert silence[0] == 0xFF
        assert silence[1] & 0xE0 == 0xE0

    def test_generate_silence_bytes(self):

        silence_bytes = MP3Stitcher.generate_silence_bytes(duration_ms=350)
        assert len(silence_bytes) > 0
        # Multiples of single frame length (144)
        assert len(silence_bytes) % 144 == 0

    def test_build_id3v23_tag(self):

        tag = MP3Stitcher.build_id3v23_tag(title="Test Episode", artist="LocalPodcastLLMStudio")
        assert tag[:3] == b"ID3"
        assert tag[3] == 0x03  # ID3v2.3
        assert b"TIT2" in tag
        assert b"TPE1" in tag

    def test_stitch_empty_inputs_raises_error(self, tmp_path):

        out_path = tmp_path / "empty.mp3"
        with pytest.raises(ValueError):
            stitch_mp3_files([], str(out_path))

    def test_stitch_mp3_files_to_disk(self, tmp_path, synthetic_mp3_factory):

        f1 = tmp_path / "turn1.mp3"
        f2 = tmp_path / "turn2.mp3"
        f1.write_bytes(synthetic_mp3_factory(num_frames=3, include_id3v2=True))
        f2.write_bytes(synthetic_mp3_factory(num_frames=3, include_id3v2=True))

        out_path = tmp_path / "final_podcast.mp3"
        result_path = stitch_mp3_files(
            [str(f1), str(f2)],
            str(out_path),
            silence_duration_ms=350,
            title="Episode 1",
            artist="Kari & Ola",
        )

        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0
        with open(result_path, "rb") as f:
            data = f.read()
            assert data[:3] == b"ID3"
            assert b"TIT2" in data

    def test_stitch_mp3_bytes_inputs(self, tmp_path, synthetic_mp3_factory):

        b1 = synthetic_mp3_factory(num_frames=2, include_id3v2=True)
        b2 = synthetic_mp3_factory(num_frames=2, include_id3v2=True)

        out_path = tmp_path / "bytes_podcast.mp3"
        result_path = stitch_mp3_files([b1, b2], str(out_path))

        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0


class TestValidateSafeOutputPath:
    """Unit tests verifying path validation behavior across all edge cases."""

    @pytest.mark.parametrize(
        "invalid_path",
        [
            "",
            "   ",
            "\t\n",
            None,
            123,
            45.6,
            ["out.mp3"],
            {"path": "out.mp3"},
            b"out.mp3",
            "out.mp3\x00",
            "folder\x00/test.mp3",
            "\x00test.mp3",
        ],
    )
    def test_validate_safe_output_path_rejections(self, invalid_path):
        with pytest.raises(ValueError):
            validate_safe_output_path(invalid_path)

    def test_validate_safe_output_path_allow_none(self):
        assert validate_safe_output_path(None, allow_none=True) == ""

    def test_validate_safe_output_path_valid_stripping(self):
        assert validate_safe_output_path("  podcast.mp3  ") == "podcast.mp3"
        assert validate_safe_output_path("output/test.mp3") == "output/test.mp3"

    @pytest.mark.parametrize("bad_out", ["", "   ", None, 12345, "bad\x00path.mp3"])
    def test_stitch_mp3_files_rejects_invalid_output_path(self, bad_out, synthetic_mp3_factory):
        b1 = synthetic_mp3_factory(num_frames=2)
        with pytest.raises(ValueError):
            stitch_mp3_files([b1], bad_out)  # type: ignore[arg-type]
