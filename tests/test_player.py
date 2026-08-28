"""
Tests for Native Windows MCI Audio Player (core/player.py)
==========================================================
Covers Tiers 1 and 2:
- WindowsAudioPlayer initialization
- File loading and path validation
- Play, Pause, Resume, Stop commands
- Seek to millisecond position
- Volume scaling (0-100% mapped to 0-1000 in MCI)
- Querying position, length, and mode status
- Helper functions: format_ms, parse_time_str, export_audio_file
- Device closing and resource cleanup
"""

import os
from typing import Any
from unittest.mock import patch

import pytest

from core.player import (
    WindowsAudioPlayer,
    export_audio_file,
    format_ms,
    parse_time_str,
)


class TestWindowsPlayerMCI:
    """Tier 1 & Tier 2: MCI command string dispatch and state tracking."""

    def test_player_init(self):
        from core.player import WindowsAudioPlayer

        player = WindowsAudioPlayer()
        assert player is not None
        assert player.get_volume() == 80

    def test_player_open_valid_file(self, tmp_path, single_frame_mp3):
        from core.player import WindowsAudioPlayer

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(single_frame_mp3)

        player = WindowsAudioPlayer()
        with patch.object(player, "_send_command", return_value="1000"):
            success = player.open(str(audio_file))
            assert success is True
            assert player.current_file is not None

    def test_player_open_nonexistent_file_returns_false(self):
        from core.player import WindowsAudioPlayer

        player = WindowsAudioPlayer()
        res = player.open("non_existent_file_123.mp3")
        assert res is False

    def test_playback_controls(self, tmp_path, single_frame_mp3):
        from core.player import WindowsAudioPlayer

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(single_frame_mp3)

        player = WindowsAudioPlayer()
        commands_sent = []

        def mock_send(cmd, buffer_len=256):
            commands_sent.append(cmd)
            if "status" in cmd and "mode" in cmd:
                return "playing"
            if "status" in cmd and "position" in cmd:
                return "5000"
            if "status" in cmd and "length" in cmd:
                return "60000"
            return ""

        with patch.object(player, "_send_command", side_effect=mock_send):
            player.open(str(audio_file))
            player.play()
            assert player.is_playing() is True

            player.pause()
            player.resume()
            player.seek(10000)
            player.set_volume(80)
            assert player.get_position() == 5000
            assert player.get_length() == 60000
            player.stop()
            player.close()

            # Verify that expected MCI verbs were dispatched
            all_cmds = " ".join(commands_sent).lower()
            assert "play" in all_cmds
            assert "pause" in all_cmds
            assert "resume" in all_cmds
            assert "seek" in all_cmds
            assert "setaudio" in all_cmds
            assert "stop" in all_cmds
            assert "close" in all_cmds

    def test_volume_clamping(self):
        player = WindowsAudioPlayer()
        commands_sent = []

        def _mock_send(cmd: str, **kw: Any) -> str:
            commands_sent.append(cmd)
            return ""

        with patch.object(player, "_send_command", side_effect=_mock_send):
            player._is_opened = True
            # Volume > 100% clamped to 100
            player.set_volume(150)
            assert player.get_volume() == 100

            # Volume < 0% clamped to 0
            player.set_volume(-20)
            assert player.get_volume() == 0

            assert any("1000" in cmd for cmd in commands_sent)
            assert any("0" in cmd for cmd in commands_sent)


class TestPlayerHelpers:
    """Tests for format_ms, parse_time_str, and export_audio_file."""

    @pytest.mark.parametrize(
        "ms,expected",
        [
            (0, "00:00"),
            (65000, "01:05"),
            (125000, "02:05"),
            (3665000, "01:01:05"),
        ],
    )
    def test_format_ms(self, ms, expected):
        assert format_ms(ms) == expected

    @pytest.mark.parametrize(
        "time_str,expected_ms",
        [
            ("00:00", 0),
            ("01:05", 65000),
            ("02:05", 125000),
            ("01:01:05", 3665000),
        ],
    )
    def test_parse_time_str(self, time_str, expected_ms):
        assert parse_time_str(time_str) == expected_ms

    def test_export_audio_file(self, tmp_path, single_frame_mp3):

        src = tmp_path / "original.mp3"
        src.write_bytes(single_frame_mp3)

        dest = tmp_path / "exports" / "exported_podcast.mp3"
        res_path = export_audio_file(str(src), str(dest))

        assert os.path.exists(res_path)
        assert os.path.getsize(res_path) == len(single_frame_mp3)

    @pytest.mark.parametrize(
        "invalid_dest",
        [
            None,
            "",
            "   ",
            "\t\n",
            "\x00out.mp3",
            "folder\x00/out.mp3",
            123,
        ],
    )
    def test_export_audio_file_invalid_destination_path(self, tmp_path, single_frame_mp3, invalid_dest):
        src = tmp_path / "original.mp3"
        src.write_bytes(single_frame_mp3)

        with pytest.raises(ValueError):
            export_audio_file(str(src), invalid_dest)  # type: ignore[arg-type]
