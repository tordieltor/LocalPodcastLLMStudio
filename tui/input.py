"""
LocalPodcastLLMStudio - Terminal Keyboard & Event Input Engine
Provides non-blocking Windows keyboard event polling, multi-byte scan code translation,
mockable InputReader abstractions for testing/CI, and a stateful TextInputPrompt editor.
"""

from __future__ import annotations

import abc
import queue
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from rich.text import Text

# Key Scan Code Mapping Tables
CHAR_MAP: dict[str, str] = {
    "\r": "enter",
    "\n": "enter",
    "\t": "tab",
    "\x1b": "escape",
    "\x08": "backspace",
    "\x7f": "backspace",
    " ": "space",
}

CTRL_MAP: dict[str, str] = {
    chr(i): f"ctrl+{chr(ord('a') + i - 1)}"
    for i in range(1, 27)
    if chr(i) not in ("\t", "\n", "\r", "\x08")
}

EXTENDED_E0_MAP: dict[str, str] = {
    "H": "up",
    "P": "down",
    "K": "left",
    "M": "right",
    "G": "home",
    "O": "end",
    "I": "page_up",
    "Q": "page_down",
    "R": "insert",
    "S": "delete",
    "\x8d": "ctrl+up",
    "\x91": "ctrl+down",
    "s": "ctrl+left",
    "t": "ctrl+right",
    "w": "ctrl+home",
    "u": "ctrl+end",
    "\x84": "ctrl+page_up",
    "v": "ctrl+page_down",
    "\x85": "f11",
    "\x86": "f12",
    "\x87": "shift+f11",
    "\x88": "shift+f12",
}

EXTENDED_00_MAP: dict[str, str] = {
    ";": "f1",
    "<": "f2",
    "=": "f3",
    ">": "f4",
    "?": "f5",
    "@": "f6",
    "A": "f7",
    "B": "f8",
    "C": "f9",
    "D": "f10",
    "T": "shift+f1",
    "U": "shift+f2",
    "V": "shift+f3",
    "W": "shift+f4",
    "X": "shift+f5",
    "Y": "shift+f6",
    "Z": "shift+f7",
    "[": "shift+f8",
    "\\": "shift+f9",
    "]": "shift+f10",
    "\x0f": "shift+tab",
}


class InputReader(abc.ABC):
    """Abstract base class for keyboard and event input readers."""

    @abc.abstractmethod
    def get_key(self, timeout: float = 0.05) -> str | None:
        """
        Polls for the next key event with a timeout.

        Args:
            timeout: Maximum duration to wait in seconds.

        Returns:
            Optional[str]: Standardized key string, or None if timeout expired.
        """
        pass

    @abc.abstractmethod
    def has_key(self) -> bool:
        """Returns True if a key is immediately waiting in the input buffer."""
        pass

    @abc.abstractmethod
    def flush(self) -> None:
        """Discards all pending keystrokes from the buffer."""
        pass


class WindowsMSVCRTInputReader(InputReader):
    """Non-blocking keyboard reader utilizing Windows msvcrt.kbhit() and getwch()."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsMSVCRTInputReader is only available on Windows platforms.")
        import msvcrt

        self._msvcrt: Any = msvcrt

    def has_key(self) -> bool:
        try:
            return bool(self._msvcrt.kbhit())
        except Exception:
            return False

    def get_key(self, timeout: float = 0.05) -> str | None:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self.has_key():
                return self._read_translated_key()
            if time.monotonic() >= deadline:
                break
            time.sleep(0.005)
        return None

    def _read_translated_key(self) -> str:
        ch = str(self._msvcrt.getwch())
        if ch == "\x00":
            ch2 = str(self._msvcrt.getwch())
            return EXTENDED_00_MAP.get(ch2, f"special_00_{ord(ch2)}")
        elif ch == "\xe0":
            ch2 = str(self._msvcrt.getwch())
            return EXTENDED_E0_MAP.get(ch2, f"special_e0_{ord(ch2)}")
        elif ch in CHAR_MAP:
            return CHAR_MAP[ch]
        elif ch in CTRL_MAP:
            return CTRL_MAP[ch]
        return ch

    def flush(self) -> None:
        try:
            while self._msvcrt.kbhit():
                self._msvcrt.getwch()
        except Exception:  # nosec B110
            pass


class QueueInputReader(InputReader):
    """Thread-safe queue-backed input reader for automated testing and async simulation."""

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()

    def push_key(self, key: str) -> None:
        """Pushes a single key token into the reader queue."""
        self._queue.put_nowait(key)

    def push_keys(self, keys: Iterable[str]) -> None:
        """Pushes multiple key tokens into the reader queue."""
        for k in keys:
            self._queue.put_nowait(k)

    def has_key(self) -> bool:
        return not self._queue.empty()

    def get_key(self, timeout: float = 0.05) -> str | None:
        try:
            return self._queue.get(block=True, timeout=timeout)
        except queue.Empty:
            return None

    def flush(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


class MockInputReader(InputReader):
    """Sequential key generator for deterministic unit testing."""

    def __init__(self, keys: Sequence[str], loop: bool = False) -> None:
        self._keys: list[str] = list(keys)
        self._loop: bool = loop
        self._index: int = 0

    def has_key(self) -> bool:
        if self._loop and len(self._keys) > 0:
            return True
        return self._index < len(self._keys)

    def get_key(self, timeout: float = 0.05) -> str | None:
        if not self.has_key():
            return None
        key = self._keys[self._index]
        self._index += 1
        if self._loop and self._index >= len(self._keys):
            self._index = 0
        return key

    def flush(self) -> None:
        self._index = len(self._keys)


def create_input_reader(
    reader_type: str | None = None,
    mock_keys: Sequence[str] | None = None,
) -> InputReader:
    """
    Factory creating an appropriate InputReader instance.

    Args:
        reader_type: 'msvcrt', 'queue', 'mock', or None for auto-detection.
        mock_keys: Sequence of keys to supply when creating a MockInputReader.

    Returns:
        InputReader: Concrete reader instance.
    """
    if mock_keys is not None or reader_type == "mock":
        return MockInputReader(mock_keys or [])
    if reader_type == "queue":
        return QueueInputReader()
    if sys.platform == "win32" and reader_type != "queue":
        try:
            return WindowsMSVCRTInputReader()
        except Exception:
            return QueueInputReader()
    return QueueInputReader()


@dataclass
class TextInputResult:
    """Result returned by TextInputPrompt upon handling a key."""

    action: str  # "submit", "cancel", "editing"
    value: str


class TextInputPrompt:
    """
    Stateful interactive text prompt model for modal dialogs and inline text boxes.
    Supports cursor navigation, deletion, character insertion, submit, and cancel.
    """

    def __init__(
        self,
        initial_value: str = "",
        placeholder: str = "",
        max_length: int | None = None,
        mask_char: str | None = None,
    ) -> None:
        self.value: str = str(initial_value)
        self.cursor_pos: int = len(self.value)
        self.placeholder: str = placeholder
        self.max_length: int | None = max_length
        self.mask_char: str | None = mask_char

    def set_value(self, new_val: str) -> None:
        """Sets the text buffer value and moves cursor to end."""
        self.value = str(new_val)
        if self.max_length is not None and len(self.value) > self.max_length:
            self.value = self.value[: self.max_length]
        self.cursor_pos = len(self.value)

    def handle_key(self, key: str) -> TextInputResult:
        """
        Processes a single key press event.

        Args:
            key: Standard key token (e.g. 'a', 'left', 'backspace', 'enter', 'escape').

        Returns:
            TextInputResult: Status ('editing', 'submit', 'cancel') and current string.
        """
        if key == "enter":
            return TextInputResult(action="submit", value=self.value)
        elif key == "escape":
            return TextInputResult(action="cancel", value=self.value)
        elif key == "left":
            self.cursor_pos = max(0, self.cursor_pos - 1)
        elif key == "right":
            self.cursor_pos = min(len(self.value), self.cursor_pos + 1)
        elif key in ("home", "ctrl+a"):
            self.cursor_pos = 0
        elif key in ("end", "ctrl+e"):
            self.cursor_pos = len(self.value)
        elif key == "backspace":
            if self.cursor_pos > 0:
                self.value = self.value[: self.cursor_pos - 1] + self.value[self.cursor_pos :]
                self.cursor_pos -= 1
        elif key == "delete":
            if self.cursor_pos < len(self.value):
                self.value = self.value[: self.cursor_pos] + self.value[self.cursor_pos + 1 :]
        elif key == "ctrl+u":
            # Clear text before cursor
            self.value = self.value[self.cursor_pos :]
            self.cursor_pos = 0
        elif key == "ctrl+k":
            # Clear text after cursor
            self.value = self.value[: self.cursor_pos]
        elif len(key) == 1 and key.isprintable():
            if self.max_length is None or len(self.value) < self.max_length:
                self.value = self.value[: self.cursor_pos] + key + self.value[self.cursor_pos :]
                self.cursor_pos += 1
        elif key == "space":
            if self.max_length is None or len(self.value) < self.max_length:
                self.value = self.value[: self.cursor_pos] + " " + self.value[self.cursor_pos :]
                self.cursor_pos += 1

        return TextInputResult(action="editing", value=self.value)

    def render_text(
        self,
        prefix: str = "",
        show_cursor: bool = True,
        style_text: str = "white",
        style_cursor: str = "reverse bold cyan",
        style_placeholder: str = "dim italic",
    ) -> Text:
        """
        Renders the styled prompt as a Rich Text renderable with visual cursor.

        Args:
            prefix: Optional label prepended to text (e.g. 'URL: ').
            show_cursor: Whether to highlight the cursor position.
            style_text: Rich style string for standard characters.
            style_cursor: Rich style string for the cursor block.
            style_placeholder: Rich style string for empty placeholder.

        Returns:
            rich.text.Text: Composed rich text object.
        """
        t = Text()
        if prefix:
            t.append(prefix, style="bold cyan")

        display_text = (
            self.mask_char * len(self.value) if self.mask_char is not None else self.value
        )

        if not display_text and self.placeholder and not show_cursor:
            t.append(self.placeholder, style=style_placeholder)
            return t

        if not show_cursor:
            t.append(display_text, style=style_text)
            return t

        if not display_text and self.placeholder:
            # Show cursor at start of placeholder
            t.append(" ", style=style_cursor)
            t.append(self.placeholder, style=style_placeholder)
            return t

        if self.cursor_pos >= len(display_text):
            t.append(display_text, style=style_text)
            t.append(" ", style=style_cursor)
        else:
            t.append(display_text[: self.cursor_pos], style=style_text)
            t.append(display_text[self.cursor_pos], style=style_cursor)
            t.append(display_text[self.cursor_pos + 1 :], style=style_text)

        return t
