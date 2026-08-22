"""
LocalPodcastLLMStudio - Terminal Audio Player Screen
Provides an integrated Windows MCI audio player controller with Play, Pause, Resume, Stop,
Seek/Position scrubber (TimeSlider), Volume slider, Save MP3 As export dialog, and Open Folder reveal.
"""

from __future__ import annotations

import os
import subprocess  # nosec: B404
import sys
from typing import Any

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

from core.player import WindowsAudioPlayer, export_audio_file, format_ms
from tui.components import (
    ActionableModal,
    CardFrame,
    HotkeyBar,
    KeyValueTable,
    LabeledSlider,
    SectionHeader,
    StatusBadge,
    TimeSlider,
)
from tui.input import TextInputPrompt, TextInputResult
from tui.state import (
    PlaybackMode,
    ScreenMode,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import (
    COLOR_ACCENT,
    COLOR_CARD_BORDER,
    COLOR_SUCCESS,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    GLYPH_AUDIO,
)


class AudioPlayerScreen:
    """
    Interactive Terminal Screen for Audio Playback and Master Track Management:
    - Windows MCI native playback engine integration
    - Play / Pause / Resume / Stop controls
    - Live audio timeline scrubber (TimeSlider) with 5s / 10s stepping and seek
    - Volume control slider (0% to 100%)
    - Save MP3 As export dialog
    - Open containing folder reveal action
    - Load external audio file (MP3 / WAV) prompt
    """

    SEEK_STEP_SHORT_MS: int = 5000  # 5 seconds
    SEEK_STEP_LONG_MS: int = 15000  # 15 seconds

    def __init__(
        self,
        state: TUIState,
        event_queue: TUIEventQueue | None = None,
        player: WindowsAudioPlayer | None = None,
    ) -> None:
        self.state: TUIState = state
        self.event_queue: TUIEventQueue | None = event_queue
        self.player: WindowsAudioPlayer = player or WindowsAudioPlayer()

        self.time_slider: TimeSlider = TimeSlider(
            current_ms=0,
            total_ms=0,
            mode_str="Stopped",
            width=36,
        )

        self.volume_slider: LabeledSlider = LabeledSlider(
            label="Master Volume",
            from_=0.0,
            to=100.0,
            number_of_steps=10,
            default_value=float(self.state.player.volume),
            format_fn=lambda val: f"{int(val)}%",
            width=20,
        )

        self.status_badge: StatusBadge = StatusBadge(
            status="offline",
            text="No Audio File Loaded",
        )

        # Modals and Text Prompts
        self.export_prompt: TextInputPrompt = TextInputPrompt(
            placeholder="Export path (e.g. C:/Podcasts/episode.mp3)...",
            max_length=260,
        )
        self.load_prompt: TextInputPrompt = TextInputPrompt(
            placeholder="Audio file path (e.g. ./output/podcast.mp3)...",
            max_length=260,
        )

        self.is_editing_export: bool = False
        self.is_editing_load: bool = False
        self.active_modal: ActionableModal | None = None

        self.status_message: str = "Audio Player Ready"
        self.status_level: str = "info"

        # Check if master MP3 path already available in state
        if self.state.audio.master_mp3_path and os.path.exists(self.state.audio.master_mp3_path):
            self.load_file(self.state.audio.master_mp3_path)

    # ==========================================================================
    # Audio Player Core Actions
    # ==========================================================================

    def load_file(self, file_path: str) -> bool:
        """
        Loads an audio file into the Windows MCI player and synchronizes state.

        Args:
            file_path: Absolute or relative file path to audio file.

        Returns:
            bool: True if loaded successfully, False otherwise.
        """
        if not file_path or not os.path.exists(file_path):
            msg = f"Audio file not found: {file_path}"
            self.status_message = msg
            self.status_level = "error"
            return False

        try:
            success = self.player.open(file_path)
            if success:
                duration_ms = self.player.get_length()
                with self.state.lock:
                    self.state.player.current_file = file_path
                    self.state.player.duration_ms = duration_ms
                    self.state.player.position_ms = 0
                    self.state.player.mode = PlaybackMode.STOPPED
                    self.state.player.is_loaded = True

                self.time_slider.update_position(0, duration_ms, mode_str="Stopped")
                self.status_badge.set_status(
                    "ready", f"Loaded: {os.path.basename(file_path)} ({format_ms(duration_ms)})"
                )
                self.status_message = f"Loaded audio file: {os.path.basename(file_path)}"
                self.status_level = "success"

                if self.event_queue:
                    self.event_queue.post_event(
                        TUIEventType.PLAYER_FILE_LOADED,
                        payload={"path": file_path, "duration_ms": duration_ms},
                    )
                return True
            else:
                err = self.player.get_last_error_message() or "MCI open failed"
                self.status_message = f"Failed to load audio: {err}"
                self.status_level = "error"
                return False
        except Exception as exc:
            self.status_message = f"Error opening audio: {exc}"
            self.status_level = "error"
            return False

    def play(self, from_ms: int | None = None) -> bool:
        """
        Starts or restarts audio playback.

        Args:
            from_ms: Optional timestamp in milliseconds to play from.

        Returns:
            bool: True if playback started.
        """
        if not self.state.player.is_loaded:
            # Try auto-loading master MP3 from state if present
            if self.state.audio.master_mp3_path and os.path.exists(
                self.state.audio.master_mp3_path
            ):
                if not self.load_file(self.state.audio.master_mp3_path):
                    return False
            else:
                self.status_message = (
                    "No audio file loaded. Generate a podcast or press [L] to load an MP3."
                )
                self.status_level = "warning"
                return False

        try:
            target_pos = from_ms if from_ms is not None else self.state.player.position_ms
            success = self.player.play(from_ms=target_pos)
            if success:
                with self.state.lock:
                    self.state.player.mode = PlaybackMode.PLAYING
                self.time_slider.update_position(
                    self.state.player.position_ms,
                    self.state.player.duration_ms,
                    mode_str="Playing",
                )
                self.status_badge.set_status("online", "Playing")
                self.status_message = "Playback started."
                self.status_level = "info"

                if self.event_queue:
                    self.event_queue.post_event(
                        TUIEventType.PLAYER_PLAY,
                        payload={"position_ms": self.state.player.position_ms},
                    )
                return True
        except Exception as exc:
            self.status_message = f"Playback error: {exc}"
            self.status_level = "error"
        return False

    def pause(self) -> bool:
        """Pauses active audio playback."""
        if not self.state.player.is_loaded:
            return False

        try:
            success = self.player.pause()
            if success:
                pos = self.player.get_position()
                with self.state.lock:
                    self.state.player.mode = PlaybackMode.PAUSED
                    self.state.player.position_ms = pos
                self.time_slider.update_position(
                    pos, self.state.player.duration_ms, mode_str="Paused"
                )
                self.status_badge.set_status("checking", "Paused")
                self.status_message = "Playback paused."
                self.status_level = "info"

                if self.event_queue:
                    self.event_queue.post_event(
                        TUIEventType.PLAYER_PAUSE,
                        payload={"position_ms": pos},
                    )
                return True
        except Exception as exc:
            self.status_message = f"Pause error: {exc}"
            self.status_level = "error"
        return False

    def resume(self) -> bool:
        """Resumes paused audio playback."""
        if not self.state.player.is_loaded:
            return False

        try:
            success = self.player.resume()
            if success:
                with self.state.lock:
                    self.state.player.mode = PlaybackMode.PLAYING
                self.status_badge.set_status("online", "Playing")
                self.status_message = "Playback resumed."
                self.status_level = "info"

                if self.event_queue:
                    self.event_queue.post_event(
                        TUIEventType.PLAYER_PLAY,
                        payload={"position_ms": self.state.player.position_ms},
                    )
                return True
        except Exception as exc:
            self.status_message = f"Resume error: {exc}"
            self.status_level = "error"
        return False

    def toggle_play_pause(self) -> bool:
        """Toggles playback between playing and paused / stopped."""
        if self.state.player.mode == PlaybackMode.PLAYING:
            return self.pause()
        elif self.state.player.mode == PlaybackMode.PAUSED:
            return self.resume()
        else:
            return self.play()

    def stop(self) -> bool:
        """Stops audio playback and rewinds scrubber to beginning."""
        if not self.state.player.is_loaded:
            return False

        try:
            self.player.stop()
            with self.state.lock:
                self.state.player.mode = PlaybackMode.STOPPED
                self.state.player.position_ms = 0

            self.time_slider.update_position(0, self.state.player.duration_ms, mode_str="Stopped")
            self.status_badge.set_status("ready", "Stopped")
            self.status_message = "Playback stopped."
            self.status_level = "info"

            if self.event_queue:
                self.event_queue.post_event(
                    TUIEventType.PLAYER_STOP,
                    payload={"position_ms": 0},
                )
            return True
        except Exception as exc:
            self.status_message = f"Stop error: {exc}"
            self.status_level = "error"
        return False

    def seek(self, position_ms: int) -> int:
        """
        Seeks playback to an absolute timestamp in milliseconds.

        Args:
            position_ms: Target timestamp clamped to [0, duration_ms].

        Returns:
            int: Resulting position in milliseconds.
        """
        if not self.state.player.is_loaded:
            return 0

        duration = self.state.player.duration_ms
        clamped = max(0, min(duration, position_ms))

        try:
            self.player.seek(clamped)
            with self.state.lock:
                self.state.player.position_ms = clamped

            mode_str = "Playing" if self.state.player.mode == PlaybackMode.PLAYING else "Paused"
            self.time_slider.update_position(clamped, duration, mode_str=mode_str)
            self.status_message = f"Seeked to {format_ms(clamped)} / {format_ms(duration)}"

            if self.event_queue:
                self.event_queue.post_event(
                    TUIEventType.PLAYER_SEEK,
                    payload={"position_ms": clamped},
                )
            return clamped
        except Exception as exc:
            self.status_message = f"Seek error: {exc}"
            self.status_level = "error"
            return self.state.player.position_ms

    def seek_relative(self, delta_ms: int) -> int:
        """Seeks relative to current position by delta_ms."""
        current = self.state.player.position_ms
        return self.seek(current + delta_ms)

    def set_volume(self, volume: int | float) -> int:
        """
        Sets master volume percentage clamped to [0, 100].

        Args:
            volume: Volume percentage.

        Returns:
            int: Clamped volume integer.
        """
        clamped = max(0, min(100, int(volume)))
        try:
            self.player.set_volume(clamped)
            with self.state.lock:
                self.state.player.volume = clamped
            self.volume_slider.set(float(clamped))
            self.status_message = f"Volume set to {clamped}%"

            if self.event_queue:
                self.event_queue.post_event(
                    TUIEventType.PLAYER_VOLUME_CHANGED,
                    payload={"volume": clamped},
                )
            return clamped
        except Exception as exc:
            self.status_message = f"Volume error: {exc}"
            self.status_level = "error"
            return self.state.player.volume

    def adjust_volume(self, delta: int | float) -> int:
        """Increments or decrements master volume."""
        cur = self.state.player.volume
        return self.set_volume(cur + int(delta))

    # ==========================================================================
    # File Export & Folder Reveal
    # ==========================================================================

    def export_audio(self, destination_path: str) -> tuple[bool, str]:
        """
        Copies active audio file to user-specified destination path.

        Args:
            destination_path: Destination file path.

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        cur_file = self.state.player.current_file or self.state.audio.master_mp3_path
        if not cur_file or not os.path.exists(cur_file):
            msg = "No audio file available to export."
            self.status_message = msg
            self.status_level = "warning"
            return False, msg

        clean_dest = destination_path.strip().strip('"').strip("'")
        if not clean_dest:
            msg = "Destination path cannot be empty."
            self.status_message = msg
            self.status_level = "error"
            return False, msg

        try:
            saved_path = export_audio_file(cur_file, clean_dest)
            msg = f"Exported audio to: {saved_path}"
            self.status_message = msg
            self.status_level = "success"
            return True, msg
        except Exception as exc:
            msg = f"Export failed: {exc}"
            self.status_message = msg
            self.status_level = "error"
            return False, msg

    def open_containing_folder(self) -> bool:
        """Reveals the folder containing the audio file in the system file explorer."""
        cur_file = self.state.player.current_file or self.state.audio.master_mp3_path
        target_dir = (
            os.path.dirname(os.path.abspath(cur_file))
            if cur_file and os.path.exists(cur_file)
            else os.path.abspath(self.state.config.output_dir)
        )

        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        try:
            if sys.platform == "win32" and hasattr(os, "startfile"):
                os.startfile(target_dir)  # nosec: B606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target_dir])  # nosec: B603, B607
            else:
                subprocess.Popen(["xdg-open", target_dir])  # nosec: B603, B607

            self.status_message = f"Opened folder: {target_dir}"
            self.status_level = "info"
            return True
        except Exception as exc:
            self.status_message = f"Failed to open folder: {exc}"
            self.status_level = "error"
            return False

    # ==========================================================================
    # Periodic Status Synchronization
    # ==========================================================================

    def update_player_status(self) -> None:
        """Polls current MCI position and state for live UI updates."""
        if not self.state.player.is_loaded:
            return

        try:
            mode = self.player.get_mode()
            pos = self.player.get_position()
            duration = self.player.get_length() or self.state.player.duration_ms

            if mode == "playing":
                with self.state.lock:
                    self.state.player.mode = PlaybackMode.PLAYING
                    self.state.player.position_ms = pos
                    self.state.player.duration_ms = duration
                self.time_slider.update_position(pos, duration, mode_str="Playing")
                self.status_badge.set_status("online", "Playing")
            elif mode == "paused":
                with self.state.lock:
                    self.state.player.mode = PlaybackMode.PAUSED
                    self.state.player.position_ms = pos
                self.time_slider.update_position(pos, duration, mode_str="Paused")
                self.status_badge.set_status("checking", "Paused")
            elif mode in ("stopped", "not ready"):
                if self.state.player.mode == PlaybackMode.PLAYING and pos >= max(0, duration - 500):
                    # Track ended naturally
                    with self.state.lock:
                        self.state.player.mode = PlaybackMode.STOPPED
                        self.state.player.position_ms = 0
                    self.time_slider.update_position(0, duration, mode_str="Stopped")
                    self.status_badge.set_status("ready", "Track Finished")
        except Exception:  # nosec B110
            pass

    # ==========================================================================
    # Event Handler
    # ==========================================================================

    def handle_event(self, event_type: TUIEventType | str, payload: Any = None) -> None:
        """Handles incoming events dispatched to the audio player screen."""
        evt_str = event_type.value if isinstance(event_type, TUIEventType) else str(event_type)

        if evt_str in (TUIEventType.TTS_COMPLETED.value, TUIEventType.GEN_COMPLETED.value):
            if isinstance(payload, dict):
                mp3_path = payload.get("mp3_path")
                if mp3_path and os.path.exists(mp3_path):
                    self.load_file(mp3_path)

        elif evt_str == TUIEventType.PLAYER_FILE_LOADED.value:
            if isinstance(payload, dict):
                path = payload.get("path")
                if path and os.path.exists(path):
                    self.load_file(path)

    # ==========================================================================
    # Key Event Handling
    # ==========================================================================

    def handle_key(self, key: str) -> bool:
        """
        Processes interactive key events for AudioPlayerScreen.

        Args:
            key: Standardized key token.

        Returns:
            bool: True if key was handled.
        """
        k = key.lower().strip()

        # Modal dismissal
        if self.active_modal is not None:
            if k in ("escape", "enter", "space", "1", "q"):
                self.active_modal = None
                return True
            return True

        # Export prompt handling
        if self.is_editing_export:
            res: TextInputResult = self.export_prompt.handle_key(key)
            if res.action == "submit":
                self.is_editing_export = False
                self.export_audio(res.value)
                return True
            elif res.action == "cancel":
                self.is_editing_export = False
                self.status_message = "Export cancelled."
                return True
            return True

        # Load file prompt handling
        if self.is_editing_load:
            res_load: TextInputResult = self.load_prompt.handle_key(key)
            if res_load.action == "submit":
                self.is_editing_load = False
                self.load_file(res_load.value)
                return True
            elif res_load.action == "cancel":
                self.is_editing_load = False
                self.status_message = "Load file cancelled."
                return True
            return True

        # Playback controls
        if k in ("space", "p", "1"):
            self.toggle_play_pause()
            return True

        if k in ("s", "2"):
            self.stop()
            return True

        # Seeking controls
        if k in ("left", "j"):
            self.seek_relative(-self.SEEK_STEP_SHORT_MS)
            return True

        if k in ("right", "l"):
            self.seek_relative(+self.SEEK_STEP_SHORT_MS)
            return True

        if k in ("page_up", "pageup", "u"):
            self.seek_relative(-self.SEEK_STEP_LONG_MS)
            return True

        if k in ("page_down", "pagedown", "d"):
            self.seek_relative(+self.SEEK_STEP_LONG_MS)
            return True

        if k == "home":
            self.seek(0)
            return True

        if k == "end":
            self.seek(self.state.player.duration_ms)
            return True

        # Volume controls
        if k in ("up", "+", "="):
            self.adjust_volume(+10)
            return True

        if k in ("down", "-", "_"):
            self.adjust_volume(-10)
            return True

        # File actions
        if k in ("e", "3"):
            cur_file = self.state.player.current_file or self.state.audio.master_mp3_path
            default_export = (
                os.path.join(
                    os.path.expanduser("~"), "Desktop", os.path.basename(cur_file or "podcast.mp3")
                )
                if cur_file
                else ""
            )
            self.export_prompt.set_value(default_export)
            self.is_editing_export = True
            self.status_message = "Enter export destination path (Enter to save, Esc to cancel)..."
            return True

        if k in ("o", "4"):
            self.open_containing_folder()
            return True

        if k in ("f", "load"):
            self.load_prompt.set_value("")
            self.is_editing_load = True
            self.status_message = "Enter audio file path to load (Enter to load, Esc to cancel)..."
            return True

        # Navigation shortcuts
        if k in ("g",):
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": ScreenMode.GENERATION.value},
                )
            return True

        if k in ("v",):
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": ScreenMode.SCRIPT_STUDIO.value},
                )
            return True

        return False

    # ==========================================================================
    # Rich UI Rendering Protocol
    # ==========================================================================

    def _render_scrubber_card(self) -> CardFrame:
        """Renders the master audio timeline progress bar, mode icon, and time display."""
        content_items: list[RenderableType] = []

        cur_file = self.state.player.current_file or self.state.audio.master_mp3_path
        file_label = os.path.basename(cur_file) if cur_file else "No Audio File Loaded"

        file_header = Table.grid(padding=(0, 2), expand=True)
        file_header.add_column("File", justify="left")
        file_header.add_column("Status", justify="right")

        file_text = Text()
        file_text.append(f"{GLYPH_AUDIO} Track: ", style=f"bold {COLOR_ACCENT}")
        file_text.append(
            file_label, style="bold " + (COLOR_SUCCESS if cur_file else COLOR_TEXT_MUTED)
        )

        file_header.add_row(file_text, self.status_badge.render())
        content_items.append(file_header)
        content_items.append(Text(""))

        # Timeline Scrubber
        content_items.append(self.time_slider.render())
        content_items.append(Text(""))

        # Quick Control Buttons Row
        mode = self.state.player.mode
        btn_play = (
            f"[bold {COLOR_TEXT_DARK} on {COLOR_SUCCESS}] [Space] Pause [/]"
            if mode == PlaybackMode.PLAYING
            else f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [Space] Play [/]"
        )
        btn_stop = f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [S] Stop [/]"
        btn_rewind = f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [←] -5s [/]"
        btn_forward = f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [→] +5s [/]"
        btn_export = f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [E] Export MP3 [/]"
        btn_folder = f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [O] Open Folder [/]"

        btn_table = Table.grid(padding=(0, 1))
        btn_table.add_row(btn_play, btn_stop, btn_rewind, btn_forward, btn_export, btn_folder)
        content_items.append(btn_table)

        return CardFrame(
            Group(*content_items),
            title="Audio Playback & Timeline Scrubber",
            subtitle=self.time_slider.format_ms(self.state.player.duration_ms)
            if self.state.player.duration_ms > 0
            else "00:00",
            border_style=COLOR_ACCENT if mode == PlaybackMode.PLAYING else COLOR_CARD_BORDER,
        )

    def _render_metadata_card(self) -> CardFrame:
        """Renders track metadata, ID3 tag details, and volume level."""
        items: list[RenderableType] = []

        cur_file = self.state.player.current_file or self.state.audio.master_mp3_path
        file_size_str = "—"
        if cur_file and os.path.exists(cur_file):
            size_kb = os.path.getsize(cur_file) / 1024.0
            file_size_str = f"{size_kb / 1024.0:.2f} MB" if size_kb > 1024 else f"{int(size_kb)} KB"

        table = KeyValueTable()
        table.add_row("Master MP3 File", cur_file or "None (Not generated)")
        table.add_row("File Size", file_size_str)
        table.add_row(
            "Language / Voices",
            f"{self.state.config.language} (Host 1: {self.state.audio.host1_voice}, Host 2: {self.state.audio.host2_voice})",
        )
        table.add_row("Speaking Speed", f"{int(self.state.audio.speaking_speed):+d}%")
        table.add_row("Total Turns", f"{len(self.state.generation.turns)} dialogue turns")

        items.append(table.__rich__())
        items.append(Text(""))
        items.append(self.volume_slider.render())

        return CardFrame(
            Group(*items),
            title="Track Information & Volume",
            border_style=COLOR_CARD_BORDER,
        )

    def __rich__(self) -> RenderableType:
        """Assembles the full AudioPlayerScreen Rich layout."""
        if self.active_modal is not None:
            return self.active_modal.__rich__()

        header = SectionHeader(
            title="Audio Player & Timeline Scrubber",
            subtitle=self.status_message,
            icon="🔊",
        )

        scrubber_card = self._render_scrubber_card()
        meta_card = self._render_metadata_card()

        # Prompt overlays if active
        prompt_panel: RenderableType | None = None
        if self.is_editing_export:
            prompt_panel = CardFrame(
                self.export_prompt.render_text(
                    prefix="Export MP3 Destination: ",
                    style_text=COLOR_TEXT_PRIMARY,
                    style_cursor=f"reverse bold {COLOR_ACCENT}",
                ),
                title="Save MP3 As...",
                border_style=COLOR_ACCENT,
            )
        elif self.is_editing_load:
            prompt_panel = CardFrame(
                self.load_prompt.render_text(
                    prefix="Load Audio File Path: ",
                    style_text=COLOR_TEXT_PRIMARY,
                    style_cursor=f"reverse bold {COLOR_ACCENT}",
                ),
                title="Open Audio File...",
                border_style=COLOR_ACCENT,
            )

        hotkeys = [
            ("Space", "Play/Pause"),
            ("S", "Stop"),
            ("←/→", "Seek 5s"),
            ("PgUp/PgDn", "Seek 15s"),
            ("↑/↓", "Volume"),
            ("E", "Export MP3"),
            ("O", "Open Folder"),
            ("F", "Load File"),
            ("G", "Generation"),
            ("V", "Script Studio"),
            ("Esc", "Back"),
        ]
        footer = HotkeyBar(shortcuts=hotkeys)

        content: list[RenderableType] = [
            header,
            Text(""),
            scrubber_card,
            Text(""),
            meta_card,
        ]

        if prompt_panel:
            content.extend([Text(""), prompt_panel])

        content.extend([Text(""), footer])
        return Group(*content)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.__rich__()
