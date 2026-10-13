"""
Tests for core/io_utils.py module functions, including validate_safe_output_path
and atomic_write_file security validation.
"""

import pytest

from core.io_utils import atomic_write_file, validate_safe_output_path


def test_validate_safe_output_path_valid():
    """Verifies validate_safe_output_path accepts valid paths and strips whitespace."""
    assert validate_safe_output_path("  output/file.mp3  ") == "output/file.mp3"
    assert validate_safe_output_path("C:/podcasts/episode1.mp3") == "C:/podcasts/episode1.mp3"
    assert validate_safe_output_path("/tmp/test.txt") == "/tmp/test.txt"


def test_validate_safe_output_path_none_and_type():
    """Verifies validate_safe_output_path handling of None and invalid types."""
    assert validate_safe_output_path(None, allow_none=True) == ""
    with pytest.raises(ValueError, match="cannot be None"):
        validate_safe_output_path(None, allow_none=False)

    with pytest.raises(ValueError, match="must be a str instance"):
        validate_safe_output_path(12345)  # type: ignore[arg-type]


def test_validate_safe_output_path_empty():
    """Verifies rejection of empty or whitespace-only paths."""
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_safe_output_path("   ")


def test_validate_safe_output_path_null_byte():
    """Verifies rejection of paths containing null byte (\\x00)."""
    with pytest.raises(ValueError, match="forbidden null byte"):
        validate_safe_output_path("output/\x00file.mp3")


def test_validate_safe_output_path_control_chars():
    """Verifies rejection of paths containing control characters (ASCII < 32 or 127)."""
    with pytest.raises(ValueError, match="forbidden control character"):
        validate_safe_output_path("output/file\n.mp3")

    with pytest.raises(ValueError, match="forbidden control character"):
        validate_safe_output_path("output/file\r.mp3")

    with pytest.raises(ValueError, match="forbidden control character"):
        validate_safe_output_path("output/file\t.mp3")

    with pytest.raises(ValueError, match="forbidden control character"):
        validate_safe_output_path("output/file\x7f.mp3")


def test_validate_safe_output_path_path_traversal():
    """Verifies rejection of path traversal ('..') components."""
    with pytest.raises(ValueError, match="forbidden path traversal"):
        validate_safe_output_path("../outside.mp3")

    with pytest.raises(ValueError, match="forbidden path traversal"):
        validate_safe_output_path("output/../../outside.mp3")

    with pytest.raises(ValueError, match="forbidden path traversal"):
        validate_safe_output_path("output\\..\\outside.mp3")


def test_atomic_write_file(tmp_path):
    """Verifies atomic_write_file writes string and bytes data safely."""
    target = tmp_path / "test_output.txt"
    written = atomic_write_file(str(target), "Hello World!")
    assert written == str(target.resolve())
    assert target.read_text(encoding="utf-8") == "Hello World!"
