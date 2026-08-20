"""
LocalPodcastLLMStudio - Native Windows Audio Player (winmm.dll / MCI)
Provides high-performance, zero-external-dependency audio playback, seeking, volume,
and export control using the Windows Multimedia Media Control Interface (MCI).
"""

import os
import shutil
import sys
from typing import Any


class WindowsAudioPlayer:
    """
    Windows Native MCI Audio Player using ctypes and winmm.dll.
    Supports MP3 playback, pause, resume, stop, position seeking, volume, and length queries.
    """

    def __init__(self, alias: str = "localpodcastllmstudio_mci_player"):
        self.alias = alias
        self.current_file: str | None = None
        self._is_opened = False
        self._length_ms = 0
        self._volume_percent = 80

        # Lazy load winmm.dll
        self._winmm = None
        if sys.platform == "win32":
            try:
                import ctypes

                self._winmm = ctypes.windll.winmm
            except Exception:
                self._winmm = None

    @property
    def _is_open(self) -> bool:
        return self._is_opened

    @_is_open.setter
    def _is_open(self, val: bool) -> None:
        self._is_opened = val

    def _send_command(self, cmd: str, buffer_len: int = 256) -> str:
        """Sends an MCI command string and returns response buffer string."""
        if not self._winmm:
            return ""

        import ctypes

        buf = ctypes.create_unicode_buffer(buffer_len)
        error_code = self._winmm.mciSendStringW(cmd, buf, buffer_len, 0)
        if error_code != 0:
            return ""
        return buf.value.strip()

    def open(self, file_path: str) -> bool:
        """
        Opens an MP3 audio file for playback.

        Args:
            file_path: Absolute or relative path to MP3 file.

        Returns:
            True if file opened successfully, False otherwise.
        """
        if not file_path or not os.path.exists(file_path):
            return False

        # Close any active device first
        self.close()

        abs_path = os.path.abspath(file_path).replace("\\", "/")
        cmd = f'open "{abs_path}" type mpegvideo alias {self.alias}'
        self._send_command(cmd)

        # Configure time format to milliseconds
        self._send_command(f"set {self.alias} time format milliseconds")

        # Query and cache total audio duration in ms
        len_str = self._send_command(f"status {self.alias} length")
        try:
            self._length_ms = int(len_str) if len_str else 0
        except ValueError:
            self._length_ms = 0

        self.current_file = abs_path
        self._is_opened = True

        # Apply default volume
        self.set_volume(self._volume_percent)

        return True

    def load(self, file_path: str) -> bool:
        """Alias for open(), raises FileNotFoundError if file missing."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        return self.open(file_path)

    def play(self, from_ms: int | None = None) -> bool:
        """
        Starts or restarts audio playback.
        """
        if not self._is_opened:
            return False

        if from_ms is not None:
            clamped = max(0, min(self._length_ms, from_ms))
            self._send_command(f"play {self.alias} from {clamped}")
        else:
            self._send_command(f"play {self.alias}")

        return True

    def pause(self) -> bool:
        """Pauses audio playback."""
        if not self._is_opened:
            return False
        self._send_command(f"pause {self.alias}")
        return True

    def resume(self) -> bool:
        """Resumes paused audio playback."""
        if not self._is_opened:
            return False
        self._send_command(f"resume {self.alias}")
        return True

    def stop(self) -> bool:
        """Stops audio playback and rewinds to beginning."""
        if not self._is_opened:
            return False
        self._send_command(f"stop {self.alias}")
        self._send_command(f"seek {self.alias} to 0")
        return True

    def seek(self, position_ms: int) -> bool:
        """
        Seeks to a specific timestamp in milliseconds.
        Preserves playing state if currently active.
        """
        if not self._is_opened:
            return False

        clamped_pos = max(0, min(self._length_ms, position_ms))
        was_playing = self.is_playing()

        self._send_command(f"seek {self.alias} to {clamped_pos}")

        if was_playing:
            self._send_command(f"play {self.alias} from {clamped_pos}")

        return True

    def get_position(self) -> int:
        """
        Queries current playback timestamp in milliseconds.
        """
        if not self._is_opened:
            return 0
        res = self._send_command(f"status {self.alias} position")
        try:
            return int(res) if res else 0
        except ValueError:
            return 0

    def get_length(self) -> int:
        """
        Returns total audio duration in milliseconds.
        """
        if not self._is_opened:
            return 0
        if self._length_ms <= 0:
            res = self._send_command(f"status {self.alias} length")
            try:
                self._length_ms = int(res) if res else 0
            except ValueError:
                self._length_ms = 0
        return self._length_ms

    def set_volume(self, volume_percent: int) -> bool:
        """
        Sets playback volume (0 to 100).
        Maps to MCI volume range (0 to 1000).
        """
        clamped = max(0, min(100, volume_percent))
        self._volume_percent = clamped
        if not self._is_opened:
            return True

        mci_vol = int(clamped * 10)
        self._send_command(f"setaudio {self.alias} volume to {mci_vol}")
        return True

    def get_volume(self) -> int:
        """Returns current configured volume percentage (0 to 100)."""
        return self._volume_percent

    def get_mode(self) -> str:
        """Returns MCI mode string ('playing', 'paused', 'stopped', or 'not ready')."""
        if not self._is_opened:
            return "not ready"
        mode = self._send_command(f"status {self.alias} mode")
        return mode.lower() if mode else "stopped"

    def is_playing(self) -> bool:
        """Returns True if audio is actively playing."""
        return self.get_mode() == "playing"

    def is_paused(self) -> bool:
        """Returns True if audio is paused."""
        return self.get_mode() == "paused"

    def is_stopped(self) -> bool:
        """Returns True if audio is stopped."""
        return self.get_mode() in ["stopped", "not ready"]

    def close(self) -> bool:
        """Closes MCI player device and releases handle."""
        if self._is_opened:
            self._send_command(f"close {self.alias}")
            self._is_opened = False
            self.current_file = None
            self._length_ms = 0
        return True

    def __enter__(self) -> "WindowsAudioPlayer":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# Class alias for backward compatibility
WindowsMCIPlayer = WindowsAudioPlayer


def format_ms(ms: int) -> str:
    """
    Formats milliseconds into MM:SS or HH:MM:SS string.
    Example: 125000 -> '02:05', 3661000 -> '01:01:01'.
    """
    total_seconds = max(0, int(ms / 1000))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def parse_time_str(time_str: str) -> int:
    """
    Parses a time string ('MM:SS' or 'HH:MM:SS') into milliseconds.
    """
    if not time_str:
        return 0

    parts = time_str.strip().split(":")
    try:
        if len(parts) == 2:
            minutes, seconds = int(parts[0]), int(parts[1])
            return (minutes * 60 + seconds) * 1000
        elif len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            return (hours * 3600 + minutes * 60 + seconds) * 1000
    except ValueError:
        return 0

    return 0


def export_audio_file(source_path: str, destination_path: str) -> str:
    """
    Exports/copies generated podcast MP3 to a user-selected destination directory or path.

    Returns:
        Absolute path to the exported file.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source audio file not found: {source_path}")

    dest_dir = os.path.dirname(os.path.abspath(destination_path))
    os.makedirs(dest_dir, exist_ok=True)

    shutil.copy2(source_path, destination_path)
    return os.path.abspath(destination_path)
