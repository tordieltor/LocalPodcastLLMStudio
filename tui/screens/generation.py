"""
LocalPodcastLLMStudio - Terminal Podcast Generation Screen
Provides real-time generation monitoring, multi-act episodic progression,
live LLM token stream buffer with token/sec metrics, status badges,
and non-blocking generation controls with cooperative cancellation.
"""

from __future__ import annotations

import threading
from typing import Any

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

from core.prompts import get_format_config
from tui.components import (
    ActionableModal,
    CardFrame,
    HotkeyBar,
    SectionHeader,
    StatusBadge,
    TUIProgressBar,
)
from tui.state import (
    GenerationStatus,
    ScreenMode,
    SynthesisStatus,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import (
    BOX_CARD,
    COLOR_ACCENT,
    COLOR_CARD_BORDER,
    COLOR_HOST1,
    COLOR_HOST2,
    COLOR_INFO,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    GLYPH_MIC,
)
from tui.workers import GenerationWorker


class GenerationScreen:
    """
    Interactive Terminal Screen for monitoring and executing podcast generation:
    1. Status badges for Generation, LLM Model, Preset, Language, Grounding, and Audio TTS.
    2. Act Progression tracker with real-time TUIProgressBar.
    3. Live streaming token terminal window showing incoming LLM output and tokens/sec.
    4. Real-time metrics: Turn count, elapsed time, synthesis progress.
    5. Action keys for Full Generation, Script-Only, Cancellation, and Reset.
    """

    def __init__(
        self,
        state: TUIState,
        event_queue: TUIEventQueue | None = None,
    ) -> None:
        self.state: TUIState = state
        self.event_queue: TUIEventQueue | None = event_queue

        self.current_worker: GenerationWorker | None = None
        self.cancel_event: threading.Event = threading.Event()

        self.progress_bar: TUIProgressBar = TUIProgressBar(
            completed=0.0,
            total=100.0,
            description="Overall Progress:",
            width=30,
        )

        self.status_badge: StatusBadge = StatusBadge(
            status="ready",
            text="Ready to Generate",
        )

        self.active_modal: ActionableModal | None = None
        self.scroll_offset: int = 0
        self.auto_scroll: bool = True
        self.status_message: str = "Press [G] to Generate Full Podcast or [S] for Script Only"
        self.status_level: str = "info"

    # ==========================================================================
    # Action Triggers & Worker Management
    # ==========================================================================

    def start_generation(self, mode: str = "full") -> tuple[bool, str]:
        """
        Validates preconditions and dispatches the GenerationWorker background thread.

        Args:
            mode: Generation mode ('full', 'script_only', or 'audio_from_script').

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        valid, reason = self.state.validate_can_generate()
        if not valid and mode != "audio_from_script":
            self.status_message = reason
            self.status_level = "error"
            self.active_modal = ActionableModal(
                title="Generation Precondition Failed",
                message=reason,
                details=(
                    f"Selected Model: {self.state.ollama.selected_model or 'None'}\n"
                    f"Ollama Online: {self.state.ollama.is_online}\n"
                    f"Extracted Characters: {self.state.ingestion.char_count}"
                ),
                modal_type="warning",
            )
            return False, reason

        if self.current_worker is not None and self.current_worker.is_alive():
            msg = "Generation is already in progress."
            self.status_message = msg
            self.status_level = "warning"
            return False, msg

        self.active_modal = None
        self.cancel_event = threading.Event()

        input_type = self.state.ingestion.source_mode.value
        input_data: Any
        if self.state.ingestion.source_mode.value == "document":
            input_data = self.state.ingestion.file_path or self.state.ingestion.extracted_text
        elif self.state.ingestion.source_mode.value == "topic_prompt":
            input_data = self.state.ingestion.topic_prompt or self.state.ingestion.extracted_text
        else:
            input_data = self.state.ingestion.raw_text or self.state.ingestion.extracted_text

        with self.state.lock:
            self.state.reset_generation_state()
            self.state.reset_audio_state()
            self.state.generation.status = GenerationStatus.GENERATING
            self.state.ui.is_busy = True
            self.state.ui.busy_task = f"Generating podcast ({mode})"

        self.status_badge.set_status("busy", "Generating...")
        self.status_message = f"Started podcast generation ({mode})..."
        self.status_level = "info"

        self.current_worker = GenerationWorker(
            mode=mode,
            input_type=input_type,
            input_data=input_data,
            language=self.state.config.language,
            model=self.state.ollama.selected_model or "llama3.1:8b",
            format_type=self.state.config.length_preset,
            tone=self.state.config.tone_preset,
            grounding_mode=self.state.config.grounding_mode,
            speed_rate=f"{int(self.state.audio.speaking_speed):+d}%",
            output_dir=self.state.config.output_dir,
            ollama_url=self.state.ollama.server_url,
            state=self.state,
            event_queue=self.event_queue,
            cancel_event=self.cancel_event,
        )
        self.current_worker.start()
        return True, "Generation started."

    def cancel_generation(self) -> bool:
        """
        Cooperatively cancels the running GenerationWorker.

        Returns:
            bool: True if cancellation request was signaled.
        """
        if self.current_worker is not None and self.current_worker.is_alive():
            self.cancel_event.set()
            self.current_worker.cancel()
            self.status_badge.set_status("error", "Cancelling...")
            self.status_message = "Generation cancellation requested."
            self.status_level = "warning"
            return True

        self.status_message = "No generation currently running to cancel."
        self.status_level = "info"
        return False

    def reset_generation(self) -> None:
        """Resets generation and audio sub-states for a clean canvas."""
        if self.current_worker is not None and self.current_worker.is_alive():
            self.cancel_generation()

        with self.state.lock:
            self.state.reset_generation_state()
            self.state.reset_audio_state()
            self.state.ui.is_busy = False
            self.state.ui.busy_task = ""

        self.progress_bar.update(0.0, 100.0, status_text="Reset")
        self.status_badge.set_status("ready", "Ready to Generate")
        self.status_message = "Generation state reset."
        self.status_level = "info"
        self.scroll_offset = 0

    # ==========================================================================
    # Event Handler
    # ==========================================================================

    def handle_event(self, event_type: TUIEventType | str, payload: Any = None) -> None:
        """Processes incoming domain events from background workers."""
        evt_str = event_type.value if isinstance(event_type, TUIEventType) else str(event_type)

        if evt_str == TUIEventType.GEN_STARTED.value:
            self.status_badge.set_status("busy", "Generating Dialogue...")
            self.status_message = "Connecting to Ollama and streaming dialogue script..."
            self.progress_bar.update(5.0, 100.0, status_text="Starting")

        elif evt_str == TUIEventType.GEN_ACT_PROGRESS.value:
            curr = payload.get("current_act", 1) if isinstance(payload, dict) else 1
            tot = payload.get("total_acts", 1) if isinstance(payload, dict) else 1
            title = payload.get("act_title", "") if isinstance(payload, dict) else ""
            pct = 10.0 + (30.0 * (curr / max(1, tot)))
            self.progress_bar.update(pct, 100.0, status_text=f"Act {curr}/{tot}")
            self.status_badge.set_status("busy", f"Act {curr}/{tot}: {title}")
            self.status_message = f"Generating Act {curr}/{tot}: {title}"

        elif evt_str == TUIEventType.GEN_TOKEN_STREAM.value:
            if isinstance(payload, dict):
                tps = payload.get("tps", 0.0)
                elapsed = payload.get("elapsed", 0.0)
                self.status_message = f"Streaming tokens... ({tps:.1f} tok/s, {elapsed:.1f}s)"

        elif evt_str == TUIEventType.GEN_SCRIPT_PARSED.value:
            count = payload.get("count", 0) if isinstance(payload, dict) else 0
            self.progress_bar.update(45.0, 100.0, status_text=f"{count} Turns")
            self.status_message = f"Script parsed: {count} dialogue turns ready."

        elif evt_str == TUIEventType.TTS_STARTED.value:
            self.status_badge.set_status("busy", "Synthesizing Speech...")
            self.progress_bar.update(50.0, 100.0, status_text="TTS Starting")
            self.status_message = "Synthesizing neural voices with Piper TTS..."

        elif evt_str == TUIEventType.TTS_TURN_PROGRESS.value:
            if isinstance(payload, dict):
                curr = payload.get("current", 0)
                tot = payload.get("total", 1)
                speaker = payload.get("speaker", "Host")
                pct = 50.0 + (40.0 * (curr / max(1, tot)))
                self.progress_bar.update(pct, 100.0, status_text=f"Turn {curr}/{tot}")
                self.status_badge.set_status("busy", f"TTS: Turn {curr}/{tot} ({speaker})")
                self.status_message = f"Synthesizing turn {curr}/{tot} ({speaker})..."

        elif evt_str == TUIEventType.TTS_STITCH_STARTED.value:
            self.status_badge.set_status("busy", "Stitching MP3...")
            self.progress_bar.update(92.0, 100.0, status_text="MP3 Stitching")
            self.status_message = "Stitching audio segments into master MP3..."

        elif evt_str in (TUIEventType.GEN_COMPLETED.value, TUIEventType.TTS_COMPLETED.value):
            self.status_badge.set_status("complete", "Generation Complete")
            self.progress_bar.update(100.0, 100.0, status_text="Complete")
            self.status_message = (
                "Podcast generated successfully! Press [V] for Script Studio or [P] for Player."
            )
            self.status_level = "success"

        elif evt_str == TUIEventType.GEN_CANCELLED.value:
            self.status_badge.set_status("cancelled", "Cancelled")
            self.status_message = "Generation was cancelled by user."
            self.status_level = "warning"

        elif evt_str == TUIEventType.GEN_FAILED.value:
            err = (
                payload.get("error", "Unknown error") if isinstance(payload, dict) else str(payload)
            )
            self.status_badge.set_status("error", "Generation Failed")
            self.status_message = f"Generation failed: {err}"
            self.status_level = "error"
            self.active_modal = ActionableModal(
                title="Generation Error",
                message=str(err),
                modal_type="error",
            )

    # ==========================================================================
    # Key Event Handling
    # ==========================================================================

    def handle_key(self, key: str) -> bool:
        """
        Handles keyboard shortcuts for GenerationScreen.

        Args:
            key: Standardized key string (e.g. 'g', 's', 'c', 'r', 'v', 'p', 'escape').

        Returns:
            bool: True if key was consumed.
        """
        k = key.lower().strip()

        if self.active_modal is not None:
            if k in ("escape", "enter", "space", "1", "q"):
                self.active_modal = None
                return True
            return True

        if k in ("g", "1"):
            self.start_generation(mode="full")
            return True

        if k in ("s", "2"):
            self.start_generation(mode="script_only")
            return True

        if k in ("c", "escape"):
            if self.state.generation.status == GenerationStatus.GENERATING:
                self.cancel_generation()
                return True
            return False

        if k in ("r", "3"):
            self.reset_generation()
            return True

        if k in ("v", "4"):
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": ScreenMode.SCRIPT_STUDIO.value},
                )
            return True

        if k in ("p", "5"):
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": ScreenMode.PLAYER.value},
                )
            return True

        if k in ("up", "k"):
            self.scroll_offset = max(0, self.scroll_offset - 2)
            self.auto_scroll = False
            return True

        if k in ("down", "j"):
            self.scroll_offset += 2
            return True

        if k == "end":
            self.auto_scroll = True
            return True

        return False

    # ==========================================================================
    # Rich UI Rendering Protocol
    # ==========================================================================

    def _render_badges_row(self) -> Table:
        """Renders the top row of status indicators and configuration badges."""
        grid = Table.grid(padding=(0, 1), expand=True)
        grid.add_column(justify="left", ratio=3)
        grid.add_column(justify="right", ratio=7)

        # Left: Live Status Badge
        left_text = Text()
        left_text.append(f"{GLYPH_MIC} Status: ", style="bold")
        status_st = self.state.generation.status.value.lower()
        if status_st == "generating":
            badge = StatusBadge(status="busy", text="Generating Podcast...")
        elif status_st == "completed":
            badge = StatusBadge(status="complete", text="Generation Complete")
        elif status_st == "failed":
            badge = StatusBadge(status="error", text="Generation Failed")
        elif status_st == "cancelled":
            badge = StatusBadge(status="error", text="Generation Cancelled")
        else:
            badge = StatusBadge(status="ready", text="Studio Ready")

        left_group = Group(left_text, badge.render())

        # Right: Config Badges
        right_table = Table.grid(padding=(0, 1))
        model_name = self.state.ollama.selected_model or "No Model"
        lang_str = "NB" if "nb" in self.state.config.language.lower() else "EN"
        preset_cfg = get_format_config(self.state.config.length_preset)
        preset_name = preset_cfg.get("name", self.state.config.length_preset)
        grounding_str = self.state.config.grounding_mode.upper()

        right_table.add_row(
            f"[{COLOR_CARD_BORDER}][[/][bold {COLOR_ACCENT}]{model_name}[/][{COLOR_CARD_BORDER}]][/]",
            f"[{COLOR_CARD_BORDER}][[/][bold {COLOR_HOST1}]{lang_str}[/][{COLOR_CARD_BORDER}]][/]",
            f"[{COLOR_CARD_BORDER}][[/][bold {COLOR_HOST2}]{preset_name}[/][{COLOR_CARD_BORDER}]][/]",
            f"[{COLOR_CARD_BORDER}][[/][bold {COLOR_INFO}]{grounding_str}[/][{COLOR_CARD_BORDER}]][/]",
        )

        grid.add_row(left_group, right_table)
        return grid

    def _render_progression_card(self) -> CardFrame:
        """Renders Act progression, TUIProgressBar, and real-time generation metrics."""
        gen = self.state.generation
        audio = self.state.audio

        # Calculate progression metrics
        act_info = f"Act {gen.current_act}/{max(1, gen.total_acts)}"
        if gen.act_title:
            act_info += f" — {gen.act_title}"
        elif gen.status == GenerationStatus.IDLE:
            act_info = "Standby (Not Generating)"

        # Progress calculation
        pct_done = 0.0
        if gen.status == GenerationStatus.COMPLETED:
            pct_done = 100.0
        elif audio.status == SynthesisStatus.SYNTHESIZING and audio.total_turns > 0:
            pct_done = 50.0 + (40.0 * (audio.current_turn / audio.total_turns))
        elif gen.status == GenerationStatus.GENERATING and gen.total_acts > 0:
            pct_done = 10.0 + (35.0 * (gen.current_act / gen.total_acts))

        self.progress_bar.update(
            completed=pct_done,
            total=100.0,
            status_text=f"{int(pct_done)}%",
        )

        # Metrics grid
        metrics_table = Table.grid(padding=(0, 2))
        metrics_table.add_column("Key", style=f"bold {COLOR_ACCENT}")
        metrics_table.add_column("Val", style=COLOR_TEXT_PRIMARY)
        metrics_table.add_column("Key2", style=f"bold {COLOR_ACCENT}")
        metrics_table.add_column("Val2", style=COLOR_TEXT_PRIMARY)

        elapsed_str = f"{int(gen.elapsed_time_sec)}s"
        tps_str = f"{gen.tokens_per_sec:.1f} tok/s" if gen.tokens_per_sec > 0 else "—"
        turns_str = f"{len(gen.turns)} turns" if gen.turns else "0 turns"
        tts_str = (
            f"Turn {audio.current_turn}/{audio.total_turns}"
            if audio.status == SynthesisStatus.SYNTHESIZING
            else audio.status.value.capitalize()
        )

        metrics_table.add_row(
            "Current Phase:",
            act_info,
            "Dialogue Turns:",
            turns_str,
        )
        metrics_table.add_row(
            "Elapsed Time:",
            f"{elapsed_str} ({tps_str})",
            "Audio Synthesis:",
            tts_str,
        )

        content = Group(
            self.progress_bar.render(),
            Text(""),
            metrics_table,
        )

        return CardFrame(
            content,
            title="Generation & Synthesis Pipeline",
            subtitle=f"{pct_done:.0f}% Completed",
            border_style=COLOR_ACCENT
            if gen.status == GenerationStatus.GENERATING
            else COLOR_CARD_BORDER,
        )

    def _render_token_stream_card(self, height: int = 12) -> CardFrame:
        """Renders the live LLM token stream output buffer with tailing and line wrapping."""
        raw_stream = self.state.generation.streamed_tokens

        if not raw_stream:
            body = Text()
            body.append(
                "Streaming token buffer is currently idle.\n",
                style=COLOR_TEXT_MUTED,
            )
            body.append(
                "Press [G] to start Full Generation or [S] to generate Dialogue Script Only.",
                style=COLOR_TEXT_SECONDARY,
            )
        else:
            lines = raw_stream.split("\n")
            visible_lines = (
                lines[-height:]
                if self.auto_scroll
                else lines[self.scroll_offset : self.scroll_offset + height]
            )
            body = Text("\n".join(visible_lines), style=COLOR_TEXT_PRIMARY)

        return CardFrame(
            body,
            title="Live Token Stream Buffer (LLM Output)",
            subtitle=f"Tokens: {len(raw_stream.split())} words",
            border_style=COLOR_CARD_BORDER,
            box_style=BOX_CARD,
        )

    def __rich__(self) -> RenderableType:
        """Assembles the full GenerationScreen Rich renderable."""
        if self.active_modal is not None:
            return self.active_modal.__rich__()

        header = SectionHeader(
            title="Podcast Generation Studio",
            subtitle=self.status_message,
            icon="🎙️",
        )

        badges_row = self._render_badges_row()
        progression_card = self._render_progression_card()
        stream_card = self._render_token_stream_card(height=8)

        is_generating = self.state.generation.status == GenerationStatus.GENERATING
        hotkeys = [
            ("G", "Generate Full" if not is_generating else "Generating..."),
            ("S", "Script Only"),
            ("C", "Cancel" if is_generating else ""),
            ("R", "Reset"),
            ("V", "Script Studio"),
            ("P", "Player"),
            ("Esc", "Back"),
        ]
        # Filter empty
        active_hotkeys = [(k, label) for (k, label) in hotkeys if label]
        footer = HotkeyBar(shortcuts=active_hotkeys)

        return Group(
            header,
            Text(""),
            badges_row,
            Text(""),
            progression_card,
            Text(""),
            stream_card,
            Text(""),
            footer,
        )

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.__rich__()
