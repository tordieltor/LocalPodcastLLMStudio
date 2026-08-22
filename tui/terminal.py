"""
LocalPodcastLLMStudio - Terminal and Virtual Terminal Processing (VTP) Engine
Provides Windows Console VTP activation, UTF-8 stream management, alternate screen
buffering, cursor visibility toggling, dimension querying, and fail-safe console restoration.
"""

from __future__ import annotations

import atexit
import ctypes
import shutil
import signal
import sys
from types import FrameType
from typing import Any

# Win32 Console API Constants
STD_INPUT_HANDLE: int = -10
STD_OUTPUT_HANDLE: int = -11
STD_ERROR_HANDLE: int = -12

ENABLE_PROCESSED_OUTPUT: int = 0x0001
ENABLE_WRAP_AT_EOL_OUTPUT: int = 0x0002
ENABLE_VIRTUAL_TERMINAL_PROCESSING: int = 0x0004
DISABLE_NEWLINE_AUTO_RETURN: int = 0x0008

ENABLE_PROCESSED_INPUT: int = 0x0001
ENABLE_LINE_INPUT: int = 0x0002
ENABLE_ECHO_INPUT: int = 0x0004
ENABLE_WINDOW_INPUT: int = 0x0008
ENABLE_MOUSE_INPUT: int = 0x0010
ENABLE_INSERT_MODE: int = 0x0020
ENABLE_QUICK_EDIT_MODE: int = 0x0040
ENABLE_EXTENDED_FLAGS: int = 0x0080
ENABLE_VIRTUAL_TERMINAL_INPUT: int = 0x0200

# ANSI Escape Sequences
ANSI_ENTER_ALT_SCREEN: str = "\033[?1049h"
ANSI_EXIT_ALT_SCREEN: str = "\033[?1049l"
ANSI_HIDE_CURSOR: str = "\033[?25l"
ANSI_SHOW_CURSOR: str = "\033[?25h"
ANSI_CURSOR_HOME: str = "\033[H"
ANSI_CLEAR_SCREEN: str = "\033[2J"
ANSI_RESET_ATTRIBUTES: str = "\033[0m"


def configure_utf8_streams() -> bool:
    """
    Configures standard input, output, and error streams to UTF-8 encoding
    with replacement error handling. On Windows, sets active code page to 65001.

    Returns:
        bool: True if UTF-8 was successfully configured on at least one stream.
    """
    configured = False
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
                configured = True
            except Exception:  # nosec B110
                pass

    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
            configured = True
        except Exception:  # nosec B110
            pass

    return configured


def enable_virtual_terminal_processing() -> tuple[bool, int | None]:
    """
    Enables Windows Console Virtual Terminal Processing (VTP) on stdout.

    Returns:
        Tuple[bool, Optional[int]]: (success_flag, original_console_mode)
    """
    if sys.platform != "win32":
        return True, None

    try:
        kernel32 = ctypes.windll.kernel32
        h_out = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        if h_out in (0, -1, None):
            return False, None

        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
            return False, None

        original_mode = mode.value
        new_mode = original_mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING | ENABLE_PROCESSED_OUTPUT
        if original_mode != new_mode:
            res = kernel32.SetConsoleMode(h_out, new_mode)
            return bool(res != 0), original_mode

        return True, original_mode
    except Exception:
        return False, None


def restore_console_mode(original_mode: int | None) -> bool:
    """
    Restores the original Windows console mode on stdout.

    Args:
        original_mode: The previous console mode DWORD, or None.

    Returns:
        bool: True if restored, False otherwise.
    """
    if sys.platform != "win32" or original_mode is None:
        return True

    try:
        kernel32 = ctypes.windll.kernel32
        h_out = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        if h_out not in (0, -1, None):
            res = kernel32.SetConsoleMode(h_out, original_mode)
            return bool(res != 0)
    except Exception:  # nosec B110
        pass
    return False


def get_terminal_dimensions(fallback: tuple[int, int] = (80, 24)) -> tuple[int, int]:
    """
    Retrieves the current terminal width and height in columns and lines.

    Args:
        fallback: Default (columns, lines) if dimension query fails.

    Returns:
        Tuple[int, int]: (columns, lines) with clamped minimums (20, 10).
    """
    try:
        size = shutil.get_terminal_size(fallback=fallback)
        cols = max(20, size.columns)
        lines = max(10, size.lines)
        return cols, lines
    except Exception:
        return max(20, fallback[0]), max(10, fallback[1])


class TerminalManager:
    """
    Context manager and controller for terminal lifecycle, VTP initialization,
    alternate screen buffering, cursor visibility, and clean teardown.
    """

    def __init__(
        self,
        use_alternate_screen: bool = True,
        hide_cursor_on_enter: bool = True,
        install_signal_handlers: bool = True,
    ) -> None:
        self.use_alternate_screen: bool = use_alternate_screen
        self.hide_cursor_on_enter: bool = hide_cursor_on_enter
        self.install_signal_handlers: bool = install_signal_handlers

        self._original_mode: int | None = None
        self._vtp_enabled: bool = False
        self._in_alternate_screen: bool = False
        self._cursor_hidden: bool = False
        self._is_active: bool = False
        self._prev_signal_handlers: dict[int, Any] = {}

    @property
    def is_active(self) -> bool:
        """Returns True if the terminal manager has started and not yet restored."""
        return self._is_active

    @property
    def vtp_enabled(self) -> bool:
        """Returns True if Virtual Terminal Processing was successfully enabled."""
        return self._vtp_enabled

    @property
    def in_alternate_screen(self) -> bool:
        """Returns True if alternate screen buffer is currently active."""
        return self._in_alternate_screen

    @property
    def cursor_hidden(self) -> bool:
        """Returns True if text cursor is currently hidden."""
        return self._cursor_hidden

    def start(self) -> TerminalManager:
        """Initializes streams, enables VTP, enters alternate screen, and registers traps."""
        if self._is_active:
            return self

        configure_utf8_streams()
        self._vtp_enabled, self._original_mode = enable_virtual_terminal_processing()

        if self.use_alternate_screen:
            self.enter_alternate_screen()

        if self.hide_cursor_on_enter:
            self.hide_cursor()

        if self.install_signal_handlers:
            self._register_signals()

        atexit.register(self.restore)
        self._is_active = True
        return self

    def restore(self) -> None:
        """Restores terminal to original buffer, shows cursor, and restores console modes."""
        if not self._is_active:
            return

        self._is_active = False

        if self._cursor_hidden:
            self.show_cursor()

        if self._in_alternate_screen:
            self.exit_alternate_screen()

        if self._original_mode is not None:
            restore_console_mode(self._original_mode)
            self._original_mode = None

        self._restore_signals()

        try:
            sys.stdout.flush()
        except Exception:  # nosec B110
            pass

    def enter_alternate_screen(self) -> None:
        """Switches to alternate screen buffer."""
        try:
            sys.stdout.write(ANSI_ENTER_ALT_SCREEN)
            sys.stdout.flush()
            self._in_alternate_screen = True
        except Exception:  # nosec B110
            pass

    def exit_alternate_screen(self) -> None:
        """Exits alternate screen buffer back to primary console."""
        try:
            sys.stdout.write(ANSI_EXIT_ALT_SCREEN)
            sys.stdout.flush()
            self._in_alternate_screen = False
        except Exception:  # nosec B110
            pass

    def hide_cursor(self) -> None:
        """Hides the text cursor."""
        try:
            sys.stdout.write(ANSI_HIDE_CURSOR)
            sys.stdout.flush()
            self._cursor_hidden = True
        except Exception:  # nosec B110
            pass

    def show_cursor(self) -> None:
        """Restores visible text cursor."""
        try:
            sys.stdout.write(ANSI_SHOW_CURSOR)
            sys.stdout.flush()
            self._cursor_hidden = False
        except Exception:  # nosec B110
            pass

    def clear(self) -> None:
        """Clears the console screen and homes the cursor."""
        try:
            sys.stdout.write(f"{ANSI_CLEAR_SCREEN}{ANSI_CURSOR_HOME}")
            sys.stdout.flush()
        except Exception:  # nosec B110
            pass

    def _register_signals(self) -> None:
        """Registers signal handlers for safe restoration upon interrupt or termination."""
        signals_to_trap = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, "SIGBREAK"):  # Windows Ctrl+Break
            signals_to_trap.append(signal.SIGBREAK)

        for sig in signals_to_trap:
            try:
                old_handler = signal.signal(sig, self._handle_signal)
                self._prev_signal_handlers[sig] = old_handler
            except Exception:  # nosec B110
                pass

    def _restore_signals(self) -> None:
        """Restores previous signal handlers."""
        for sig, handler in self._prev_signal_handlers.items():
            try:
                signal.signal(sig, handler)
            except Exception:  # nosec B110
                pass
        self._prev_signal_handlers.clear()

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        """Handles caught signal by cleanly restoring the terminal before exit."""
        self.restore()
        prev = self._prev_signal_handlers.get(signum)
        if callable(prev) and prev not in (signal.SIG_DFL, signal.SIG_IGN):
            prev(signum, frame)
        else:
            sys.exit(128 + signum)

    def __enter__(self) -> TerminalManager:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        self.restore()
