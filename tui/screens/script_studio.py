"""
LocalPodcastLLMStudio - Terminal Interactive Script Studio Screen
Provides formatted dialogue turn inspection cards (color-coded per speaker with badges),
raw JSON script viewer/editor with live syntax validation, copy script to clipboard,
atomic file export, and 1-click 'Synthesize Audio from Script' execution via background worker.
"""

from __future__ import annotations

import os
import subprocess  # nosec: B404
import sys
import threading
import time
from typing import Any

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.io_utils import atomic_write_file
from core.parser import (
    DialogueParser,
    DialogueTurn,
    SpeakerRole,
    dialogue_to_json,
    dialogue_to_markdown,
    normalize_speaker,
)
from tui.components import (
    ActionableModal,
    CardFrame,
    HotkeyBar,
    SectionHeader,
)
from tui.input import TextInputPrompt
from tui.state import (
    ScreenMode,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import (
    BOX_CARD,
    BOX_SQUARE,
    COLOR_ACCENT,
    COLOR_CARD_BORDER,
    COLOR_HOST1,
    COLOR_HOST1_BG,
    COLOR_HOST2,
    COLOR_HOST2_BG,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    GLYPH_MIC,
)
from tui.workers import TTSSynthesisWorker


def _copy_to_system_clipboard(text: str) -> bool:
    """
    Cross-platform safe system clipboard copier with fallbacks.
    Tries win32/clip on Windows, pbcopy on macOS, xclip/xsel on Linux, or ctypes/tkinter.
    """
    if not text:
        return False

    # 1. Try Windows clip.exe
    if sys.platform == "win32":
        try:
            p = subprocess.Popen(  # nosec: B603, B607
                ["clip"],
                stdin=subprocess.PIPE,
                shell=False,
            )
            p.communicate(input=text.encode("utf-16le"))
            if p.returncode == 0:
                return True
        except (OSError, ValueError):
            pass

    # 2. Try macOS pbcopy
    elif sys.platform == "darwin":
        try:
            p = subprocess.Popen(  # nosec: B603, B607
                ["pbcopy"],
                stdin=subprocess.PIPE,
                shell=False,
            )
            p.communicate(input=text.encode("utf-8"))
            if p.returncode == 0:
                return True
        except (OSError, ValueError):
            pass

    # 3. Try Linux xclip / xsel
    elif sys.platform.startswith("linux"):
        for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
            try:
                p = subprocess.Popen(  # nosec: B603
                    cmd,
                    stdin=subprocess.PIPE,
                    shell=False,
                )
                p.communicate(input=text.encode("utf-8"))
                if p.returncode == 0:
                    return True
            except (OSError, ValueError):
                continue

    # 4. Fallback: Tkinter clipboard if available
    try:
        import tkinter as tk  # nosec: B404

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


class ScriptStudioScreen:
    """
    Interactive Terminal Screen for reviewing and editing podcast scripts:
    1. Formatted dialogue turn inspection cards (color-coded per speaker with badges).
    2. Raw JSON script viewer and in-place code editor with real-time validation.
    3. Copy script to system clipboard (`[C]`).
    4. Save JSON and Markdown script to disk (`[S]`).
    5. Trigger 'Synthesize Audio from Script' (`[A]`) via background TTSSynthesisWorker.
    """

    TAB_FORMATTED: str = "formatted"
    TAB_RAW_JSON: str = "raw_json"

    def __init__(
        self,
        state: TUIState,
        event_queue: TUIEventQueue | None = None,
    ) -> None:
        self.state: TUIState = state
        self.event_queue: TUIEventQueue | None = event_queue

        self.active_tab: str = self.TAB_FORMATTED
        self.selected_turn_index: int = 0
        self.turns_per_page: int = 3
        self.scroll_top_turn: int = 0

        self.is_editing_json: bool = False
        self.json_editor_prompt: TextInputPrompt = TextInputPrompt(
            placeholder="Edit raw JSON script...",
            max_length=50000,
        )

        self.current_worker: TTSSynthesisWorker | None = None
        self.cancel_event: threading.Event = threading.Event()
        self.active_modal: ActionableModal | None = None

        self.status_message: str = "Script Studio Ready"
        self.status_level: str = "info"

    # ==========================================================================
    # Script Operations & Navigation
    # ==========================================================================

    def get_turns(self) -> list[DialogueTurn]:
        """Returns the active list of dialogue turns from TUIState."""
        with self.state.lock:
            return list(self.state.generation.turns)

    def set_turns(self, turns: list[DialogueTurn]) -> None:
        """Updates dialogue turns in TUIState and regenerates JSON and Markdown representations."""
        raw_json = dialogue_to_json(turns)
        with self.state.lock:
            self.state.generation.turns = list(turns)
            self.state.generation.raw_json_script = raw_json

    def switch_tab(self, tab: str | None = None) -> str:
        """Toggles or sets the active tab between 'formatted' and 'raw_json'."""
        if tab is not None:
            self.active_tab = (
                tab if tab in (self.TAB_FORMATTED, self.TAB_RAW_JSON) else self.TAB_FORMATTED
            )
        else:
            self.active_tab = (
                self.TAB_RAW_JSON if self.active_tab == self.TAB_FORMATTED else self.TAB_FORMATTED
            )

        if self.active_tab == self.TAB_RAW_JSON:
            turns = self.get_turns()
            self.json_editor_prompt.set_value(dialogue_to_json(turns))

        self.status_message = f"Switched to {'Formatted Dialogue Cards' if self.active_tab == self.TAB_FORMATTED else 'Raw JSON Editor'} tab"
        self.status_level = "info"
        return self.active_tab

    def select_turn(self, index: int) -> int:
        """Selects the dialogue turn at the specified index, clamping to valid bounds."""
        turns = self.get_turns()
        if not turns:
            self.selected_turn_index = 0
            self.scroll_top_turn = 0
            return 0

        self.selected_turn_index = max(0, min(len(turns) - 1, index))

        # Adjust window scroll
        if self.selected_turn_index < self.scroll_top_turn:
            self.scroll_top_turn = self.selected_turn_index
        elif self.selected_turn_index >= self.scroll_top_turn + self.turns_per_page:
            self.scroll_top_turn = self.selected_turn_index - self.turns_per_page + 1

        return self.selected_turn_index

    def next_turn(self) -> int:
        """Navigates to the next dialogue turn."""
        return self.select_turn(self.selected_turn_index + 1)

    def prev_turn(self) -> int:
        """Navigates to the previous dialogue turn."""
        return self.select_turn(self.selected_turn_index - 1)

    # ==========================================================================
    # Script Export, Clipboard & Audio Synthesis Actions
    # ==========================================================================

    def copy_script_to_clipboard(self) -> tuple[bool, str]:
        """
        Copies formatted JSON script to system clipboard.

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        turns = self.get_turns()
        if not turns:
            msg = "Cannot copy script: No dialogue turns exist."
            self.status_message = msg
            self.status_level = "warning"
            return False, msg

        json_text = dialogue_to_json(turns)
        success = _copy_to_system_clipboard(json_text)

        if success:
            msg = f"Copied {len(turns)} dialogue turns ({len(json_text)} bytes) to clipboard."
            self.status_message = msg
            self.status_level = "success"
            return True, msg
        else:
            msg = "Clipboard utility unavailable, but script is ready."
            self.status_message = msg
            self.status_level = "warning"
            return False, msg

    def save_script_to_disk(self, custom_path: str | None = None) -> tuple[bool, str]:
        """
        Atomically exports the active dialogue script as JSON and Markdown files.

        Args:
            custom_path: Optional custom output path for JSON file.

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        turns = self.get_turns()
        if not turns:
            msg = "Cannot save script: No dialogue turns exist."
            self.status_message = msg
            self.status_level = "warning"
            return False, msg

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_dir = self.state.config.output_dir
        os.makedirs(out_dir, exist_ok=True)

        json_path = custom_path or os.path.join(out_dir, f"podcast_script_{timestamp}.json")
        md_path = os.path.splitext(json_path)[0] + ".md"

        try:
            atomic_write_file(json_path, dialogue_to_json(turns))
            atomic_write_file(md_path, dialogue_to_markdown(turns))

            with self.state.lock:
                self.state.generation.script_json_path = json_path
                self.state.generation.script_md_path = md_path

            msg = f"Saved script to {os.path.basename(json_path)} & {os.path.basename(md_path)}"
            self.status_message = msg
            self.status_level = "success"
            return True, msg

        except Exception as exc:
            msg = f"Failed to save script: {exc}"
            self.status_message = msg
            self.status_level = "error"
            return False, msg

    def synthesize_audio_from_script(self) -> tuple[bool, str]:
        """
        Initiates asynchronous TTS audio synthesis directly from current script turns.

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        turns = self.get_turns()
        if not turns:
            msg = "Cannot synthesize audio: No dialogue turns available in script."
            self.status_message = msg
            self.status_level = "warning"
            self.active_modal = ActionableModal(
                title="No Script to Synthesize",
                message=msg,
                details="Please generate a script on the Generation screen or paste JSON first.",
                modal_type="warning",
            )
            return False, msg

        if self.current_worker is not None and self.current_worker.is_alive():
            msg = "Audio synthesis is already in progress."
            self.status_message = msg
            self.status_level = "warning"
            return False, msg

        self.cancel_event = threading.Event()
        self.status_message = f"Starting Piper TTS synthesis for {len(turns)} dialogue turns..."
        self.status_level = "info"

        self.current_worker = TTSSynthesisWorker(
            dialogue=turns,
            language=self.state.config.language,
            speed_rate=f"{int(self.state.audio.speaking_speed):+d}%",
            output_dir=self.state.config.output_dir,
            state=self.state,
            event_queue=self.event_queue,
            cancel_event=self.cancel_event,
        )
        self.current_worker.start()
        return True, "Audio synthesis initiated."

    def cancel_synthesis(self) -> bool:
        """Signals cancellation to running audio synthesis worker."""
        if self.current_worker is not None and self.current_worker.is_alive():
            self.cancel_event.set()
            self.current_worker.cancel()
            self.status_message = "Audio synthesis cancellation requested."
            self.status_level = "warning"
            return True
        return False

    def apply_raw_json_edits(self) -> tuple[bool, str]:
        """
        Validates and parses the content in the raw JSON editor, updating TUIState turns.

        Returns:
            Tuple[bool, str]: (success, status_message)
        """
        raw_text = self.json_editor_prompt.value.strip()
        if not raw_text:
            msg = "JSON editor is empty."
            self.status_message = msg
            self.status_level = "error"
            return False, msg

        try:
            parsed_turns = DialogueParser.parse(
                raw_text, default_language=self.state.config.language
            )
            if not parsed_turns:
                raise ValueError("Parsed result contained zero dialogue turns.")

            self.set_turns(parsed_turns)
            self.is_editing_json = False
            msg = f"Applied raw JSON edits: {len(parsed_turns)} dialogue turns successfully parsed."
            self.status_message = msg
            self.status_level = "success"
            return True, msg

        except Exception as exc:
            msg = f"Invalid dialogue JSON format: {exc}"
            self.status_message = msg
            self.status_level = "error"
            self.active_modal = ActionableModal(
                title="JSON Parse Error",
                message="Failed to parse structured dialogue turns from the edited JSON text.",
                details=str(exc),
                modal_type="error",
            )
            return False, msg

    # ==========================================================================
    # Event Handler
    # ==========================================================================

    def handle_event(self, event_type: TUIEventType | str, payload: Any = None) -> None:
        """Processes incoming events dispatched from background workers."""
        evt_str = event_type.value if isinstance(event_type, TUIEventType) else str(event_type)

        if evt_str == TUIEventType.GEN_SCRIPT_PARSED.value:
            if isinstance(payload, dict):
                turns = payload.get("turns", [])
                if turns:
                    self.set_turns(turns)
                    self.select_turn(0)
                    self.status_message = f"Script loaded: {len(turns)} turns ready for inspection."
                    self.status_level = "info"

        elif evt_str == TUIEventType.TTS_STARTED.value:
            self.status_message = "Piper TTS voice synthesis in progress..."
            self.status_level = "info"

        elif evt_str == TUIEventType.TTS_TURN_PROGRESS.value:
            if isinstance(payload, dict):
                curr = payload.get("current", 0)
                tot = payload.get("total", 1)
                spk = payload.get("speaker", "Host")
                self.status_message = f"Synthesizing turn {curr}/{tot} ({spk})..."

        elif evt_str == TUIEventType.TTS_COMPLETED.value:
            self.status_message = "Audio synthesized and stitched successfully! Press [P] to play."
            self.status_level = "success"

        elif evt_str == TUIEventType.TTS_FAILED.value:
            err = payload.get("error", "TTS Error") if isinstance(payload, dict) else str(payload)
            self.status_message = f"Audio synthesis failed: {err}"
            self.status_level = "error"
            self.active_modal = ActionableModal(
                title="TTS Synthesis Error",
                message=str(err),
                modal_type="error",
            )

    # ==========================================================================
    # Key Event Handling
    # ==========================================================================

    def handle_key(self, key: str) -> bool:
        """
        Handles keyboard shortcuts for ScriptStudioScreen.

        Args:
            key: Standardized key string.

        Returns:
            bool: True if key was handled.
        """
        k = key.lower().strip()

        if self.active_modal is not None:
            if k in ("escape", "enter", "space", "1", "q"):
                self.active_modal = None
                return True
            return True

        # If currently editing raw JSON text in prompt
        if self.is_editing_json:
            if k == "escape":
                self.is_editing_json = False
                self.status_message = "Exited JSON editor without applying changes."
                self.status_level = "info"
                return True
            elif k == "ctrl+s" or k == "f2":
                self.apply_raw_json_edits()
                return True
            else:
                res = self.json_editor_prompt.handle_key(key)
                if res.action == "submit":
                    self.apply_raw_json_edits()
                elif res.action == "cancel":
                    self.is_editing_json = False
                return True

        if k in ("tab", "t"):
            self.switch_tab()
            return True

        if k in ("c",):
            self.copy_script_to_clipboard()
            return True

        if k in ("s",):
            self.save_script_to_disk()
            return True

        if k in ("a", "1"):
            self.synthesize_audio_from_script()
            return True

        if k in ("e", "2"):
            if self.active_tab != self.TAB_RAW_JSON:
                self.switch_tab(self.TAB_RAW_JSON)
            self.is_editing_json = True
            self.status_message = (
                "Editing raw JSON script. Press [Ctrl+S] or [Enter] to apply, [Esc] to cancel."
            )
            self.status_level = "info"
            return True

        if k in ("up", "k"):
            self.prev_turn()
            return True

        if k in ("down", "j"):
            self.next_turn()
            return True

        if k in ("page_up", "pageup"):
            self.select_turn(self.selected_turn_index - self.turns_per_page)
            return True

        if k in ("page_down", "pagedown"):
            self.select_turn(self.selected_turn_index + self.turns_per_page)
            return True

        if k == "home":
            self.select_turn(0)
            return True

        if k == "end":
            turns = self.get_turns()
            self.select_turn(len(turns) - 1)
            return True

        if k in ("g",):
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": ScreenMode.GENERATION.value},
                )
            return True

        if k in ("p",):
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": ScreenMode.PLAYER.value},
                )
            return True

        return False

    # ==========================================================================
    # Rich UI Rendering Protocol
    # ==========================================================================

    def _render_tab_header(self) -> Table:
        """Renders the top tab selection bar."""
        table = Table.grid(padding=(0, 2), expand=True)
        table.add_column("Tabs", justify="left")
        table.add_column("Summary", justify="right")

        tab1_style = (
            f"bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}"
            if self.active_tab == self.TAB_FORMATTED
            else f"bold {COLOR_TEXT_SECONDARY} on {COLOR_CARD_BORDER}"
        )
        tab2_style = (
            f"bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}"
            if self.active_tab == self.TAB_RAW_JSON
            else f"bold {COLOR_TEXT_SECONDARY} on {COLOR_CARD_BORDER}"
        )

        tabs_text = Text()
        tabs_text.append(" [Tab] Active View: ", style=COLOR_TEXT_MUTED)
        tabs_text.append(" [1] Formatted Dialogue ", style=tab1_style)
        tabs_text.append(" ")
        tabs_text.append(" [2] Raw JSON Editor ", style=tab2_style)

        turns = self.get_turns()
        summary_text = Text(f"Total: {len(turns)} turns", style=COLOR_TEXT_SECONDARY)

        table.add_row(tabs_text, summary_text)
        return table

    def _render_formatted_turns_view(self) -> RenderableType:
        """Renders paginated dialogue turn inspection cards with host styling."""
        turns = self.get_turns()

        if not turns:
            return CardFrame(
                Text(
                    "No dialogue script available to inspect.\n"
                    "Generate a podcast on the Generation Screen or paste JSON into the Raw JSON Editor.",
                    style=COLOR_TEXT_MUTED,
                ),
                title="Dialogue Turn Cards",
                subtitle="Empty Script",
                border_style=COLOR_CARD_BORDER,
            )

        render_items: list[RenderableType] = []
        visible_turns = turns[self.scroll_top_turn : self.scroll_top_turn + self.turns_per_page]

        for offset, turn in enumerate(visible_turns):
            turn_idx = self.scroll_top_turn + offset
            is_selected = turn_idx == self.selected_turn_index

            role = SpeakerRole.from_speaker(turn.speaker)
            is_host1 = role == SpeakerRole.HOST_1
            accent = COLOR_HOST1 if is_host1 else COLOR_HOST2
            bg = COLOR_HOST1_BG if is_host1 else COLOR_HOST2_BG

            norm = normalize_speaker(turn.speaker)
            if norm == "Host 1":
                persona_name = (
                    "Host 1 (Kari)"
                    if "nb" in self.state.config.language.lower()
                    else "Host 1 (Jenny)"
                )
            elif norm == "Host 2":
                persona_name = (
                    "Host 2 (Ola)" if "nb" in self.state.config.language.lower() else "Host 2 (Guy)"
                )
            else:
                persona_name = turn.speaker

            title_text = Text()
            if is_selected:
                title_text.append("▶ ", style=f"bold {COLOR_ACCENT}")
            title_text.append(f"{GLYPH_MIC} {persona_name}", style=f"bold {accent}")
            title_text.append(f"  Turn #{turn_idx + 1}/{len(turns)}", style=COLOR_TEXT_SECONDARY)

            card_border = COLOR_ACCENT if is_selected else accent
            card = Panel(
                Text(turn.text, style=COLOR_TEXT_PRIMARY),
                title=title_text,
                border_style=card_border,
                box=BOX_CARD,
                padding=(0, 1),
                style=f"on {bg}",
            )
            render_items.append(card)

        indicator_text = Text(
            f"Showing turns {self.scroll_top_turn + 1}-{min(len(turns), self.scroll_top_turn + len(visible_turns))} of {len(turns)}  (Selected: #{self.selected_turn_index + 1})",
            style=COLOR_TEXT_MUTED,
            justify="center",
        )
        render_items.append(indicator_text)

        return Group(*render_items)

    def _render_raw_json_view(self) -> RenderableType:
        """Renders raw JSON code view and editor."""
        turns = self.get_turns()
        json_str = self.json_editor_prompt.value or dialogue_to_json(turns)

        if self.is_editing_json:
            content = Group(
                Text(
                    "Editing raw JSON dialogue below: (Press Ctrl+S or Enter to Apply, Esc to Cancel)",
                    style=COLOR_ACCENT,
                ),
                Text(""),
                Panel(
                    Text(json_str, style=COLOR_TEXT_PRIMARY),
                    border_style=COLOR_ACCENT,
                    box=BOX_SQUARE,
                    title="[bold] JSON Editor [/]",
                ),
            )
        else:
            content = Group(
                Panel(
                    Text(json_str, style=COLOR_TEXT_PRIMARY),
                    border_style=COLOR_CARD_BORDER,
                    box=BOX_CARD,
                    title="[bold] Formatted JSON Script [/]",
                    subtitle="Press [E] to edit directly",
                )
            )

        return CardFrame(
            content,
            title="Raw Script JSON Viewer & Editor",
            subtitle=f"{len(json_str.splitlines())} lines",
        )

    def __rich__(self) -> RenderableType:
        """Assembles the full ScriptStudioScreen Rich renderable."""
        if self.active_modal is not None:
            return self.active_modal.__rich__()

        header = SectionHeader(
            title="Interactive Script Studio",
            subtitle=self.status_message,
            icon="📝",
        )

        tab_header = self._render_tab_header()

        if self.active_tab == self.TAB_FORMATTED:
            main_view = self._render_formatted_turns_view()
        else:
            main_view = self._render_raw_json_view()

        hotkeys = [
            ("Tab", "Switch Tab"),
            ("↑/↓", "Navigate Turns"),
            ("A", "Synthesize Audio"),
            ("C", "Copy Script"),
            ("S", "Save Script"),
            ("E", "Edit JSON"),
            ("G", "Generation"),
            ("P", "Player"),
        ]
        footer = HotkeyBar(shortcuts=hotkeys)

        return Group(
            header,
            Text(""),
            tab_header,
            Text(""),
            main_view,
            Text(""),
            footer,
        )

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.__rich__()
