"""
LocalPodcastLLMStudio - Native Windows Audio Player (winmm.dll / MCI)
Provides high-performance, zero-external-dependency audio playback, seeking, volume,
and export control using the Windows Multimedia Media Control Interface (MCI).
"""

import atexit
import ctypes
import os
import shutil
import sys
import uuid
from typing import Any

from core.mp3_stitcher import validate_safe_output_path


class WindowsAudioPlayer:
    """
    Windows Native MCI Audio Player using ctypes and winmm.dll.
    Supports MP3 playback, pause, resume, stop, position seeking, volume, and length queries.
    """

    def __init__(self, alias: str | None = None):
        if alias is None:
            self.alias = f"lp_mci_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        else:
            self.alias = alias
        self.current_file: str | None = None
        self._is_opened = False
        self._length_ms = 0
        self._volume_percent = 80
        self._last_error = 0

        # Lazy load winmm.dll
        self._winmm = None
        if sys.platform == "win32":
            try:
                self._winmm = ctypes.windll.winmm
            except (AttributeError, OSError):
                self._winmm = None

        # Register exit handler for process cleanup
        atexit.register(self.close)

    @property
    def _is_open(self) -> bool:
        return self._is_opened

    @_is_open.setter
    def _is_open(self, val: bool) -> None:
        self._is_opened = val

    def get_last_error_message(self) -> str:
        """Retrieves human-readable error string from Windows winmm.dll."""
        if not self._winmm or self._last_error == 0:
            return ""
        err_buf = ctypes.create_unicode_buffer(512)
        try:
            if self._winmm.mciGetErrorStringW(self._last_error, err_buf, 512):
                return err_buf.value.strip()
        except (AttributeError, OSError):
            pass
        return f"MCI Error Code {self._last_error}"

    def _send_command(self, cmd: str, buffer_len: int = 256) -> str:
        """Sends an MCI command string and returns response buffer string."""
        if not self._winmm:
            return ""

        buf = ctypes.create_unicode_buffer(buffer_len)
        try:
            error_code = self._winmm.mciSendStringW(cmd, buf, buffer_len, 0)
            self._last_error = error_code
            if error_code != 0:
                return ""
        except (AttributeError, OSError):
            self._last_error = -1
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

        # Ensure clean close before opening
        self.close()
        self._send_command(f"close {self.alias}")

        abs_path = os.path.abspath(file_path).replace("\\", "/")

        # Inspect file binary magic bytes to determine exact MCI driver
        is_wav = False
        is_mp3 = False
        try:
            with open(file_path, "rb") as f:
                header_bytes = f.read(4)
                if header_bytes.startswith(b"RIFF"):
                    is_wav = True
                elif header_bytes.startswith(b"ID3") or (
                    len(header_bytes) >= 2
                    and header_bytes[0] == 0xFF
                    and (header_bytes[1] & 0xE0) == 0xE0
                ):
                    is_mp3 = True
        except (OSError, ValueError):
            pass

        if is_wav or abs_path.lower().endswith(".wav"):
            cmd = f'open "{abs_path}" type waveaudio alias {self.alias}'
        elif is_mp3 or abs_path.lower().endswith(".mp3"):
            cmd = f'open "{abs_path}" type mpegvideo alias {self.alias}'
        else:
            cmd = f'open "{abs_path}" alias {self.alias}'

        self._last_error = 0
        self._send_command(cmd)
        if self._last_error != 0:
            # Fallback: attempt opening without explicit type parameter
            fallback_cmd = f'open "{abs_path}" alias {self.alias}'
            self._send_command(fallback_cmd)
            if self._last_error != 0:
                self._is_opened = False
                return False

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
        except (AttributeError, OSError):
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
    Sanitizes both input paths to prevent path traversal or null byte injection.

    Returns:
        Absolute path to the exported file.
    """
    # Security input validation: sanitize and reject invalid paths / null bytes
    clean_src = validate_safe_output_path(source_path, param_name="source_path")
    clean_dest = validate_safe_output_path(destination_path, param_name="destination_path")

    if not os.path.exists(clean_src):
        raise FileNotFoundError(f"Source audio file not found: {clean_src}")

    dest_dir = os.path.dirname(os.path.abspath(clean_dest))
    os.makedirs(dest_dir, exist_ok=True)

    shutil.copy2(clean_src, clean_dest)
    return os.path.abspath(clean_dest)
