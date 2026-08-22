"""
Unit tests for tui/terminal.py: Windows VTP activation, UTF-8 streams, and terminal management.
"""

from __future__ import annotations

import signal
from unittest.mock import patch

import pytest

from tui.terminal import (
    ANSI_CLEAR_SCREEN,
    ANSI_CURSOR_HOME,
    ANSI_HIDE_CURSOR,
    ANSI_SHOW_CURSOR,
    TerminalManager,
    configure_utf8_streams,
    enable_virtual_terminal_processing,
    get_terminal_dimensions,
    restore_console_mode,
)


def test_configure_utf8_streams() -> None:
    """Verifies that configure_utf8_streams executes without unhandled errors."""
    res = configure_utf8_streams()
    assert isinstance(res, bool)


def test_enable_vtp_and_restore_console_mode() -> None:
    """Tests VTP activation and console mode restoration behavior."""
    success, orig_mode = enable_virtual_terminal_processing()
    assert isinstance(success, bool)

    # Restoring with None should return True cleanly
    assert restore_console_mode(None) is True

    if orig_mode is not None:
        restored = restore_console_mode(orig_mode)
        assert isinstance(restored, bool)


def test_get_terminal_dimensions_clamping() -> None:
    """Tests terminal dimensions retrieval and minimum boundary clamping."""
    cols, lines = get_terminal_dimensions()
    assert isinstance(cols, int)
    assert isinstance(lines, int)
    assert cols >= 20
    assert lines >= 10

    # Test with exception during shutil query
    with patch("shutil.get_terminal_size", side_effect=OSError("No TTY")):
        fallback_cols, fallback_lines = get_terminal_dimensions(fallback=(85, 30))
        assert fallback_cols == 85
        assert fallback_lines == 30

    with patch("shutil.get_terminal_size", side_effect=OSError("No TTY")):
        fallback_cols, fallback_lines = get_terminal_dimensions(fallback=(5, 5))
        assert fallback_cols == 20  # Clamped to min 20
        assert fallback_lines == 10  # Clamped to min 10


def test_terminal_manager_lifecycle() -> None:
    """Verifies TerminalManager start, screen toggling, cursor visibility, and restore."""
    tm = TerminalManager(
        use_alternate_screen=True,
        hide_cursor_on_enter=True,
        install_signal_handlers=True,
    )
    assert tm.is_active is False
    assert tm.in_alternate_screen is False
    assert tm.cursor_hidden is False

    with patch("sys.stdout.write") as mock_write, patch("sys.stdout.flush"):
        tm.start()
        assert tm.is_active is True
        assert tm.in_alternate_screen is True
        assert tm.cursor_hidden is True

        # Calling start again when active is idempotent
        assert tm.start() is tm

        # Clear screen
        tm.clear()
        mock_write.assert_any_call(f"{ANSI_CLEAR_SCREEN}{ANSI_CURSOR_HOME}")

        # Show cursor manually
        tm.show_cursor()
        assert tm.cursor_hidden is False
        mock_write.assert_any_call(ANSI_SHOW_CURSOR)

        # Hide cursor manually
        tm.hide_cursor()
        assert tm.cursor_hidden is True
        mock_write.assert_any_call(ANSI_HIDE_CURSOR)

        # Restore
        tm.restore()
        assert tm.is_active is False
        assert tm.in_alternate_screen is False
        assert tm.cursor_hidden is False

        # Idempotent restore
        tm.restore()
        assert tm.is_active is False


def test_terminal_manager_context_manager() -> None:
    """Verifies TerminalManager context manager behavior with clean exit and exceptions."""
    with patch("sys.stdout.write"), patch("sys.stdout.flush"):
        with TerminalManager(
            use_alternate_screen=False,
            hide_cursor_on_enter=False,
            install_signal_handlers=False,
        ) as tm:
            assert tm.is_active is True

        assert tm.is_active is False


def test_terminal_manager_exception_handling() -> None:
    """Verifies that exceptions inside context manager still trigger restore."""
    tm_instance = None
    with patch("sys.stdout.write"), patch("sys.stdout.flush"):
        with pytest.raises(ValueError, match="Test error"):
            with TerminalManager(
                use_alternate_screen=False,
                hide_cursor_on_enter=False,
                install_signal_handlers=False,
            ) as tm:
                tm_instance = tm
                raise ValueError("Test error")

    assert tm_instance is not None
    assert tm_instance.is_active is False


def test_terminal_manager_signal_handling() -> None:
    """Verifies that signal handlers cleanly trigger restore."""
    tm = TerminalManager(install_signal_handlers=True)
    with patch("sys.stdout.write"), patch("sys.stdout.flush"):
        tm.start()
        assert tm.is_active is True

        # Simulate SIGINT handling
        with patch("sys.exit") as mock_exit:
            tm._handle_signal(signal.SIGINT, None)
            mock_exit.assert_called_once_with(128 + signal.SIGINT)

        assert tm.is_active is False
