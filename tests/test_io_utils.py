"""
Unit tests for core/io_utils.py (validate_safe_output_path and atomic_write_file).
"""

import pytest

from core.io_utils import atomic_write_file, validate_safe_output_path


class TestValidateSafeOutputPathSecurity:
    """Security tests for validate_safe_output_path."""

    @pytest.mark.parametrize(
        "traversal_path",
        [
            "../secret.txt",
            "..\\secret.txt",
            "subfolder/../secret.txt",
            "subfolder\\..\\secret.txt",
            "a/b/../c",
            "..",
            "folder/..",
        ],
    )
    def test_validate_safe_output_path_rejects_path_traversal(self, traversal_path):
        """Verifies path traversal ('..') segments trigger a ValueError."""
        with pytest.raises(ValueError, match="forbidden path traversal"):
            validate_safe_output_path(traversal_path)

    @pytest.mark.parametrize(
        "control_char_path",
        [
            "file\nname.mp3",
            "file\rname.mp3",
            "file\tname.mp3",
            "file\x07name.mp3",
            "file\x1bname.mp3",
            "file\x7fname.mp3",
        ],
    )
    def test_validate_safe_output_path_rejects_control_characters(self, control_char_path):
        """Verifies ASCII control characters trigger a ValueError."""
        with pytest.raises(ValueError, match="forbidden control characters"):
            validate_safe_output_path(control_char_path)

    def test_validate_safe_output_path_accepts_valid_paths(self):
        """Verifies valid output paths are stripped and returned."""
        assert validate_safe_output_path("  output/podcast.mp3  ") == "output/podcast.mp3"
        assert validate_safe_output_path("my_file.txt") == "my_file.txt"
        assert validate_safe_output_path("C:\\Podcasts\\episode.mp3") == "C:\\Podcasts\\episode.mp3"

    def test_atomic_write_file_rejects_traversal(self, tmp_path):
        """Verifies atomic_write_file enforces path safety checks."""
        bad_path = str(tmp_path / ".." / "unauthorized.txt")
        with pytest.raises(ValueError, match="forbidden path traversal"):
            atomic_write_file(bad_path, "sensitive data")
