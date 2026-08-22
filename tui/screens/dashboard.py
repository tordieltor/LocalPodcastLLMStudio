"""
LocalPodcastLLMStudio - Terminal Master Dashboard Screen
Provides a 2-column master dashboard bringing together Status Overview, Active Screen panel,
Ingestion Summary, Ollama Status, Generation Controls, Script Studio, and Audio Player scrubber.
"""

from __future__ import annotations

import os
from typing import Any

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.prompts import get_format_config
from tui.components import (
    CardFrame,
    HotkeyBar,
    KeyValueTable,
    SectionHeader,
    TimeSlider,
)
from tui.state import (
    PlaybackMode,
    ScreenMode,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import (
    BOX_SQUARE,
    COLOR_ACCENT,
    COLOR_CARD_BORDER,
    COLOR_HOST1,
    COLOR_HOST2,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
)


class DashboardScreen:
    """
    Interactive Master Dashboard Screen:
    - 2-Column Responsive Tokyo Night layout
    - Left Column:
        1. Ingestion Overview (Source mode, File/Topic, Character count, Validation)
        2. Ollama LLM Connection & Active Model
        3. Podcast & Persona Configuration Summary
    - Right Column:
        4. Dialogue Script Status (Turn counts, Act specs, JSON/MD persistence)
        5. Audio Synthesis & Master MP3 Info
        6. Mini Audio Scrubber & Quick Playback Controller
    - Top Status Bar & Quick Jump Action Buttons
    """

    def __init__(
        self,
        state: TUIState,
        event_queue: TUIEventQueue | None = None,
    ) -> None:
        self.state: TUIState = state
        self.event_queue: TUIEventQueue | None = event_queue

        self.time_slider: TimeSlider = TimeSlider(
            current_ms=0,
            total_ms=0,
            mode_str="Stopped",
            width=26,
        )

        self.status_message: str = (
            "Welcome to LocalPodcastLLMStudio. Select a stage or press [G] to generate."
        )
        self.status_level: str = "info"

    # ==========================================================================
    # Event Handler
    # ==========================================================================

    def handle_event(self, event_type: TUIEventType | str, payload: Any = None) -> None:
        """Processes incoming events to update dashboard status badges."""
        evt_str = event_type.value if isinstance(event_type, TUIEventType) else str(event_type)

        if evt_str in (TUIEventType.PLAYER_POSITION_UPDATE.value, TUIEventType.PLAYER_SEEK.value):
            if isinstance(payload, dict):
                pos = payload.get("position_ms", 0)
                dur = payload.get("duration_ms", self.state.player.duration_ms)
                mode = self.state.player.mode.value.capitalize()
                self.time_slider.update_position(pos, dur, mode_str=mode)

        elif evt_str in (TUIEventType.GEN_COMPLETED.value, TUIEventType.TTS_COMPLETED.value):
            self.status_message = "Podcast generation completed successfully!"
            self.status_level = "success"

        elif evt_str == TUIEventType.GEN_STARTED.value:
            self.status_message = "Generating podcast dialogue script..."
            self.status_level = "info"

    # ==========================================================================
    # Key Event Handling
    # ==========================================================================

    def handle_key(self, key: str) -> bool:
        """
        Processes interactive shortcuts on the dashboard.

        Args:
            key: Standardized key string.

        Returns:
            bool: True if key was handled.
        """
        k = key.lower().strip()

        # Direct Screen Navigation
        nav_map = {
            "1": ScreenMode.INGESTION,
            "i": ScreenMode.INGESTION,
            "f2": ScreenMode.INGESTION,
            "2": ScreenMode.OLLAMA,
            "o": ScreenMode.OLLAMA,
            "f3": ScreenMode.OLLAMA,
            "3": ScreenMode.CONFIG,
            "c": ScreenMode.CONFIG,
            "f4": ScreenMode.CONFIG,
            "4": ScreenMode.GENERATION,
            "f5": ScreenMode.GENERATION,
            "5": ScreenMode.SCRIPT_STUDIO,
            "s": ScreenMode.SCRIPT_STUDIO,
            "f6": ScreenMode.SCRIPT_STUDIO,
            "6": ScreenMode.PLAYER,
            "p": ScreenMode.PLAYER,
            "f7": ScreenMode.PLAYER,
            "?": ScreenMode.HELP,
            "h": ScreenMode.HELP,
            "f1": ScreenMode.HELP,
            "f8": ScreenMode.HELP,
        }

        if k in nav_map:
            target_screen = nav_map[k]
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": target_screen.value},
                )
            return True

        # Quick Actions
        if k in ("g",):
            # Navigate to generation and trigger full run
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": ScreenMode.GENERATION.value, "auto_start": True},
                )
            return True

        if k in ("r",):
            if self.event_queue is not None:
                self.event_queue.post_event(TUIEventType.OLLAMA_PROBE_REQUESTED)
            self.status_message = "Probing Ollama local daemon..."
            self.status_level = "info"
            return True

        if k in ("space",):
            # Quick toggle playback on loaded audio
            if self.state.player.is_loaded:
                if self.state.player.mode == PlaybackMode.PLAYING:
                    if self.event_queue:
                        self.event_queue.post_event(TUIEventType.PLAYER_PAUSE)
                else:
                    if self.event_queue:
                        self.event_queue.post_event(TUIEventType.PLAYER_PLAY)
                return True

        return False

    # ==========================================================================
    # Column Renderers
    # ==========================================================================

    def _render_ingestion_card(self) -> CardFrame:
        """Renders the document and scratch topic ingestion overview."""
        ing = self.state.ingestion
        mode_str = ing.source_mode.value.replace("_", " ").title()

        source_desc = "None"
        if ing.file_path:
            source_desc = os.path.basename(ing.file_path)
        elif ing.topic_prompt:
            source_desc = (
                f'"{ing.topic_prompt[:30]}..."'
                if len(ing.topic_prompt) > 30
                else f'"{ing.topic_prompt}"'
            )
        elif ing.raw_text:
            source_desc = f"Raw Text ({ing.char_count} chars)"

        table = KeyValueTable()
        table.add_row("Input Modality", mode_str)
        table.add_row("Source Content", source_desc)
        table.add_row("Extracted Size", f"{ing.char_count} chars, {ing.word_count} words")

        status_color = COLOR_SUCCESS if ing.is_valid else COLOR_WARNING
        status_txt = (
            f"[{status_color} bold]{'✓ Valid Input' if ing.is_valid else '⚠️ Incomplete'}[/]"
        )
        table.add_row("Validation", status_txt)

        if ing.extracted_preview:
            preview_box = Panel(
                Text(ing.extracted_preview, style=COLOR_TEXT_SECONDARY),
                title="[bold #7982a9] Content Preview [/]",
                border_style=COLOR_CARD_BORDER,
                box=BOX_SQUARE,
                padding=(0, 1),
            )
            content = Group(table.__rich__(), Text(""), preview_box)
        else:
            content = Group(table.__rich__())

        return CardFrame(
            content,
            title="[1] Source Content Ingestion",
            subtitle="Press [1] or [I] to configure",
            border_style=COLOR_ACCENT if ing.is_valid else COLOR_CARD_BORDER,
        )

    def _render_ollama_card(self) -> CardFrame:
        """Renders Ollama server status and model selection."""
        oll = self.state.ollama
        table = KeyValueTable()
        table.add_row("Ollama URL", oll.server_url)

        st_color = COLOR_SUCCESS if oll.is_online else COLOR_WARNING
        st_txt = f"[{st_color} bold]{'Online' if oll.is_online else 'Offline / Checking'}[/]"
        table.add_row("Service Status", st_txt)

        model_txt = f"[bold {COLOR_ACCENT}]{oll.selected_model or 'None Selected'}[/]"
        table.add_row("Active Model", model_txt)
        table.add_row("Available Models", f"{len(oll.available_models)} installed")

        return CardFrame(
            table.__rich__(),
            title="[2] Ollama Local LLM Engine",
            subtitle="Press [2] or [O] to configure (R to probe)",
            border_style=COLOR_CARD_BORDER,
        )

    def _render_config_card(self) -> CardFrame:
        """Renders Generation configuration presets and personas."""
        cfg = self.state.config
        fmt = get_format_config(cfg.length_preset)

        table = KeyValueTable()
        table.add_row(
            "Language / Tone",
            f"{'Norwegian (nb-NO)' if 'nb' in cfg.language.lower() else 'English (en-US)'} / {cfg.tone_preset.capitalize()}",
        )
        table.add_row(
            "Episode Format", f"{fmt['name']} ({fmt['target_turns']} turns, {fmt['duration']})"
        )
        table.add_row("Grounding Mode", f"{cfg.grounding_mode.upper()} fidelity")
        table.add_row(
            "Host Personas",
            f"[{COLOR_HOST1}]{cfg.host1_name}[/] & [{COLOR_HOST2}]{cfg.host2_name}[/]",
        )
        table.add_row("Speaking Speed", f"{int(self.state.audio.speaking_speed):+d}%")

        return CardFrame(
            table.__rich__(),
            title="[3] Podcast Settings & Personas",
            subtitle="Press [3] or [C] to configure",
            border_style=COLOR_CARD_BORDER,
        )

    def _render_generation_card(self) -> CardFrame:
        """Renders live LLM generation status, token progress, and active acts."""
        gen = self.state.generation
        table = KeyValueTable()
        st_color = (
            COLOR_SUCCESS
            if gen.status.value == "completed"
            else (COLOR_WARNING if gen.status.value == "generating" else COLOR_TEXT_SECONDARY)
        )
        token_count = len(gen.streamed_tokens.split()) if gen.streamed_tokens else 0
        table.add_row("Pipeline Status", f"[{st_color} bold]{gen.status.value.capitalize()}[/]")
        table.add_row("Active Act", f"{gen.current_act} / {gen.total_acts}")
        table.add_row(
            "Stream Tokens",
            f"{token_count:,} words ({gen.tokens_per_sec:.1f} tok/s)",
        )
        table.add_row("Dialogue Turns", f"{len(gen.turns)} turns captured")

        return CardFrame(
            table.__rich__(),
            title="[4] Generation Pipeline & Studio",
            subtitle="Press [4] or [G] to run pipeline",
            border_style=COLOR_ACCENT if gen.status.value == "generating" else COLOR_CARD_BORDER,
        )

    def _render_script_card(self) -> CardFrame:
        """Renders dialogue turn counts and script status."""
        gen = self.state.generation
        turns = gen.turns
        turn_count = len(turns)

        table = KeyValueTable()
        table.add_row("Script Status", gen.status.value.capitalize())
        table.add_row("Dialogue Turns", f"{turn_count} total turns")
        if gen.script_json_path:
            table.add_row("Saved JSON", os.path.basename(gen.script_json_path))
        if gen.script_md_path:
            table.add_row("Saved Transcript", os.path.basename(gen.script_md_path))

        items: list[RenderableType] = [table.__rich__()]

        if turns:
            h1_turns = sum(
                1 for t in turns if "1" in t.speaker or "Kari" in t.speaker or "Jenny" in t.speaker
            )
            h2_turns = turn_count - h1_turns
            dist_text = Text()
            dist_text.append("Turn Distribution: ", style=COLOR_TEXT_SECONDARY)
            dist_text.append(f"Host 1 ({h1_turns}) ", style=f"bold {COLOR_HOST1}")
            dist_text.append("• ", style=COLOR_TEXT_MUTED)
            dist_text.append(f"Host 2 ({h2_turns})", style=f"bold {COLOR_HOST2}")
            items.append(Text(""))
            items.append(dist_text)

        return CardFrame(
            Group(*items),
            title="[5] Script Studio & Dialogue Turns",
            subtitle="Press [5] or [S] to inspect cards",
            border_style=COLOR_CARD_BORDER,
        )

    def _render_audio_card(self) -> CardFrame:
        """Renders audio synthesis state, master MP3, and timeline scrubber."""
        audio = self.state.audio
        player_st = self.state.player

        cur_file = player_st.current_file or audio.master_mp3_path
        file_label = os.path.basename(cur_file) if cur_file else "None"

        table = KeyValueTable()
        table.add_row("TTS Engine", "Piper Neural TTS (ONNX)")
        table.add_row("Voices", f"H1: {audio.host1_voice} | H2: {audio.host2_voice}")
        table.add_row("Master Audio", file_label)
        table.add_row(
            "Playback Status",
            f"{player_st.mode.value.capitalize()} ({player_st.scrubber_str})",
        )

        self.time_slider.update_position(
            player_st.position_ms,
            player_st.duration_ms,
            mode_str=player_st.mode.value.capitalize(),
        )

        content = Group(
            table.__rich__(),
            Text(""),
            self.time_slider.render(),
        )

        return CardFrame(
            content,
            title="[6] Master Audio & MCI Player",
            subtitle="Press [6] or [P] for player",
            border_style=COLOR_ACCENT
            if player_st.mode == PlaybackMode.PLAYING
            else COLOR_CARD_BORDER,
        )

    # ==========================================================================
    # Main Render Protocol
    # ==========================================================================

    def __rich__(self) -> RenderableType:
        """Assembles the full 2-column master dashboard layout."""
        header = SectionHeader(
            title="LocalPodcastLLMStudio — Autonomous AI Podcast Station",
            subtitle=self.status_message,
            icon="🎙️",
        )

        left_col = Group(
            self._render_ingestion_card(),
            Text(""),
            self._render_ollama_card(),
            Text(""),
            self._render_config_card(),
        )

        right_col = Group(
            self._render_generation_card(),
            Text(""),
            self._render_script_card(),
            Text(""),
            self._render_audio_card(),
        )

        dashboard_grid = Table.grid(padding=(0, 2), expand=True)
        dashboard_grid.add_column("Left", ratio=1)
        dashboard_grid.add_column("Right", ratio=1)
        dashboard_grid.add_row(left_col, right_col)

        hotkeys = [
            ("1/I", "Ingestion"),
            ("2/O", "Ollama"),
            ("3/C", "Config"),
            ("4", "Generate"),
            ("5/S", "Script Studio"),
            ("6/P", "Player"),
            ("G", "Quick Run"),
            ("Space", "Play/Pause"),
            ("R", "Probe"),
            ("?", "Help"),
            ("Q", "Quit"),
        ]
        footer = HotkeyBar(shortcuts=hotkeys)

        return Group(
            header,
            Text(""),
            dashboard_grid,
            Text(""),
            footer,
        )

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.__rich__()
