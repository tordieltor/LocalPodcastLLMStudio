"""
Unit tests for tui/input.py: Non-blocking input readers, scan code translation, and TextInputPrompt.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from rich.text import Text

from tui.input import (
    CHAR_MAP,
    CTRL_MAP,
    EXTENDED_00_MAP,
    EXTENDED_E0_MAP,
    MockInputReader,
    QueueInputReader,
    TextInputPrompt,
    WindowsMSVCRTInputReader,
    create_input_reader,
)


def test_mock_input_reader() -> None:
    """Verifies MockInputReader sequential key playback and timeout."""
    reader = MockInputReader(["up", "down", "enter"])
    assert reader.has_key() is True
    assert reader.get_key() == "up"
    assert reader.get_key() == "down"
    assert reader.get_key() == "enter"
    assert reader.has_key() is False
    assert reader.get_key(timeout=0.01) is None

    # Test looping mode
    loop_reader = MockInputReader(["a", "b"], loop=True)
    assert loop_reader.get_key() == "a"
    assert loop_reader.get_key() == "b"
    assert loop_reader.get_key() == "a"
    assert loop_reader.has_key() is True

    # Test flush
    reader2 = MockInputReader(["1", "2", "3"])
    reader2.flush()
    assert reader2.has_key() is False
    assert reader2.get_key() is None


def test_queue_input_reader() -> None:
    """Verifies thread-safe QueueInputReader operations."""
    q_reader = QueueInputReader()
    assert q_reader.has_key() is False
    assert q_reader.get_key(timeout=0.01) is None

    q_reader.push_key("tab")
    q_reader.push_keys(["q", "escape"])
    assert q_reader.has_key() is True

    assert q_reader.get_key() == "tab"
    assert q_reader.get_key() == "q"
    assert q_reader.get_key() == "escape"
    assert q_reader.has_key() is False

    q_reader.push_keys(["x", "y", "z"])
    q_reader.flush()
    assert q_reader.has_key() is False
    assert q_reader.get_key(timeout=0.01) is None


def test_create_input_reader_factory() -> None:
    """Verifies factory instantiation for mock, queue, and platform readers."""
    mock_r = create_input_reader(reader_type="mock", mock_keys=["1", "2"])
    assert isinstance(mock_r, MockInputReader)

    queue_r = create_input_reader(reader_type="queue")
    assert isinstance(queue_r, QueueInputReader)

    auto_r = create_input_reader()
    assert auto_r is not None


def test_msvcrt_input_reader_translation() -> None:
    """Tests WindowsMSVCRTInputReader key translation logic."""
    if sys.platform != "win32":
        with pytest.raises(RuntimeError, match="only available on Windows"):
            WindowsMSVCRTInputReader()
        return

    reader = WindowsMSVCRTInputReader()

    # Test normal char
    with patch.object(reader._msvcrt, "getwch", return_value="a"):
        assert reader._read_translated_key() == "a"

    # Test control char
    with patch.object(reader._msvcrt, "getwch", return_value="\x03"):
        assert reader._read_translated_key() == "ctrl+c"

    # Test single mapped char
    with patch.object(reader._msvcrt, "getwch", return_value="\r"):
        assert reader._read_translated_key() == "enter"

    # Test 0x00 extended sequence (e.g. F1)
    with patch.object(reader._msvcrt, "getwch", side_effect=["\x00", ";"]):
        assert reader._read_translated_key() == "f1"

    # Test 0xe0 extended sequence (e.g. Up arrow)
    with patch.object(reader._msvcrt, "getwch", side_effect=["\xe0", "H"]):
        assert reader._read_translated_key() == "up"


def test_scan_code_maps_coverage() -> None:
    """Verifies scan code table mappings."""
    assert CHAR_MAP["\r"] == "enter"
    assert CHAR_MAP["\x1b"] == "escape"
    assert CHAR_MAP["\t"] == "tab"
    assert CTRL_MAP["\x01"] == "ctrl+a"
    assert CTRL_MAP["\x03"] == "ctrl+c"
    assert EXTENDED_E0_MAP["H"] == "up"
    assert EXTENDED_E0_MAP["P"] == "down"
    assert EXTENDED_E0_MAP["K"] == "left"
    assert EXTENDED_E0_MAP["M"] == "right"
    assert EXTENDED_00_MAP[";"] == "f1"
    assert EXTENDED_00_MAP["<"] == "f2"


def test_text_input_prompt_typing_and_navigation() -> None:
    """Verifies TextInputPrompt character entry, cursor navigation, and deletion."""
    prompt = TextInputPrompt(initial_value="hello")
    assert prompt.value == "hello"
    assert prompt.cursor_pos == 5

    # Type a letter
    res = prompt.handle_key("!")
    assert res.action == "editing"
    assert prompt.value == "hello!"
    assert prompt.cursor_pos == 6

    # Move left twice
    prompt.handle_key("left")
    prompt.handle_key("left")
    assert prompt.cursor_pos == 4

    # Insert character at position 4
    prompt.handle_key("X")
    assert prompt.value == "hellXo!"
    assert prompt.cursor_pos == 5

    # Move to start (home)
    prompt.handle_key("home")
    assert prompt.cursor_pos == 0

    # Move right and backspace
    prompt.handle_key("right")
    prompt.handle_key("backspace")
    assert prompt.value == "ellXo!"
    assert prompt.cursor_pos == 0

    # Delete at cursor
    prompt.handle_key("delete")
    assert prompt.value == "llXo!"
    assert prompt.cursor_pos == 0

    # Move to end
    prompt.handle_key("end")
    assert prompt.cursor_pos == 5

    # Submit
    submit_res = prompt.handle_key("enter")
    assert submit_res.action == "submit"
    assert submit_res.value == "llXo!"

    # Cancel
    cancel_res = prompt.handle_key("escape")
    assert cancel_res.action == "cancel"
    assert cancel_res.value == "llXo!"


def test_text_input_prompt_ctrl_shortcuts_and_limits() -> None:
    """Verifies TextInputPrompt ctrl shortcuts, spaces, and max length."""
    prompt = TextInputPrompt(initial_value="foo bar baz", max_length=15)

    # Position cursor at index 4 ("b")
    prompt.cursor_pos = 4

    # ctrl+u: delete before cursor
    prompt.handle_key("ctrl+u")
    assert prompt.value == "bar baz"
    assert prompt.cursor_pos == 0

    # move to index 3 and ctrl+k: delete after cursor
    prompt.cursor_pos = 3
    prompt.handle_key("ctrl+k")
    assert prompt.value == "bar"

    # Test space insertion
    prompt.handle_key("space")
    assert prompt.value == "bar "

    # Test max length enforcement
    limited = TextInputPrompt(initial_value="12345", max_length=5)
    limited.handle_key("6")
    assert limited.value == "12345"

    limited.set_value("123456789")
    assert limited.value == "12345"


def test_text_input_prompt_rendering() -> None:
    """Verifies Rich Text rendering with prefix, placeholder, and masking."""
    prompt = TextInputPrompt(initial_value="", placeholder="Enter name...")
    rendered_empty = prompt.render_text(prefix="Name: ", show_cursor=False)
    assert isinstance(rendered_empty, Text)
    assert "Enter name..." in rendered_empty.plain

    prompt.set_value("secret")
    prompt.mask_char = "*"
    rendered_masked = prompt.render_text(prefix="Password: ", show_cursor=True)
    assert isinstance(rendered_masked, Text)
    assert "******" in rendered_masked.plain
    assert "Password: " in rendered_masked.plain
