"""
LocalPodcastLLMStudio - Terminal Help & Shortcuts Cheat Sheet Screen
Provides a comprehensive keyboard shortcuts guide, navigation reference,
technology stack overview, and end-to-end podcast generation workflow instructions.
"""

from __future__ import annotations

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tui.components import (
    CardFrame,
    HotkeyBar,
    KeyValueTable,
    SectionHeader,
)
from tui.state import (
    ScreenMode,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import (
    BOX_SQUARE,
    COLOR_ACCENT,
    COLOR_CARD_BORDER,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)


class HelpScreen:
    """
    Interactive Terminal Screen for Keyboard Shortcuts, Architecture & Workflow Documentation:
    1. Global navigation & screen selection keys (F1-F8, 1-8, Tab, Esc)
    2. Screen-specific action hotkeys for each pipeline stage
    3. LocalPodcastLLMStudio core technology stack summary
    4. Step-by-step workflow guide
    5. Privacy and offline architecture guarantee
    """

    TAB_SHORTCUTS: str = "shortcuts"
    TAB_WORKFLOW: str = "workflow"
    TAB_TECH_STACK: str = "tech_stack"

    def __init__(
        self,
        state: TUIState,
        event_queue: TUIEventQueue | None = None,
    ) -> None:
        self.state: TUIState = state
        self.event_queue: TUIEventQueue | None = event_queue
        self.active_tab: str = self.TAB_SHORTCUTS
        self.status_message: str = "Help & Shortcuts Reference"
        self.status_level: str = "info"

    def switch_tab(self, tab: str | None = None) -> str:
        """Cycles or sets active documentation tab."""
        tabs = [self.TAB_SHORTCUTS, self.TAB_WORKFLOW, self.TAB_TECH_STACK]
        if tab in tabs:
            self.active_tab = tab
        else:
            idx = tabs.index(self.active_tab) if self.active_tab in tabs else 0
            self.active_tab = tabs[(idx + 1) % len(tabs)]
        return self.active_tab

    def handle_key(self, key: str) -> bool:
        """
        Processes interactive keys on the help screen.

        Args:
            key: Standardized key string.

        Returns:
            bool: True if key was handled.
        """
        k = key.lower().strip()

        if k in ("tab", "t"):
            self.switch_tab()
            return True

        if k in ("1",):
            self.switch_tab(self.TAB_SHORTCUTS)
            return True

        if k in ("2",):
            self.switch_tab(self.TAB_WORKFLOW)
            return True

        if k in ("3",):
            self.switch_tab(self.TAB_TECH_STACK)
            return True

        if k in ("escape", "q", "b", "h", "f1", "f8", "?"):
            if self.event_queue is not None:
                self.event_queue.post_event(
                    TUIEventType.NAVIGATE_SCREEN,
                    payload={"screen": ScreenMode.DASHBOARD.value},
                )
            return True

        return False

    # ==========================================================================
    # Tab View Renderers
    # ==========================================================================

    def _render_tab_header(self) -> Table:
        """Renders the top tab navigation bar."""
        table = Table.grid(padding=(0, 2), expand=True)
        table.add_column("Tabs", justify="left")
        table.add_column("Hint", justify="right")

        tab1_style = (
            f"bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}"
            if self.active_tab == self.TAB_SHORTCUTS
            else f"bold {COLOR_TEXT_SECONDARY} on {COLOR_CARD_BORDER}"
        )
        tab2_style = (
            f"bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}"
            if self.active_tab == self.TAB_WORKFLOW
            else f"bold {COLOR_TEXT_SECONDARY} on {COLOR_CARD_BORDER}"
        )
        tab3_style = (
            f"bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}"
            if self.active_tab == self.TAB_TECH_STACK
            else f"bold {COLOR_TEXT_SECONDARY} on {COLOR_CARD_BORDER}"
        )

        tabs_text = Text()
        tabs_text.append(" [Tab] Section: ", style=COLOR_TEXT_MUTED)
        tabs_text.append(" [1] Keyboard Shortcuts ", style=tab1_style)
        tabs_text.append(" ")
        tabs_text.append(" [2] Workflow Guide ", style=tab2_style)
        tabs_text.append(" ")
        tabs_text.append(" [3] Tech Stack & Parity ", style=tab3_style)

        hint_text = Text("Press [Esc] or [Q] to return to Dashboard", style=COLOR_TEXT_SECONDARY)
        table.add_row(tabs_text, hint_text)
        return table

    def _render_shortcuts_tab(self) -> RenderableType:
        """Renders comprehensive 2-column shortcuts cheat sheet."""
        left_table = Table.grid(padding=(0, 2))
        left_table.add_column("Key", style=f"bold {COLOR_ACCENT}", no_wrap=True)
        left_table.add_column("Action", style=COLOR_TEXT_PRIMARY)

        left_table.add_row("[bold #7aa2f7]Global Navigation[/]", "")
        left_table.add_row("F1 / 0", "Dashboard (Master Overview)")
        left_table.add_row("F2 / 1", "Document / Topic Ingestion")
        left_table.add_row("F3 / 2", "Ollama Connection & Models")
        left_table.add_row("F4 / 3", "Podcast & Preset Config")
        left_table.add_row("F5 / 4", "Generation Studio")
        left_table.add_row("F6 / 5", "Script Studio (Dialogue Cards)")
        left_table.add_row("F7 / 6", "Audio Player & Timeline")
        left_table.add_row("F8 / ?", "Help & Shortcuts (This Screen)")
        left_table.add_row("Q / Esc", "Back / Quit Application")
        left_table.add_row("", "")

        left_table.add_row("[bold #9ece6a]Ingestion & Ollama[/]", "")
        left_table.add_row("F / B", "Browse & select file (PDF, TXT, MD)")
        left_table.add_row("T / P", "Enter prompt / topic theme directly")
        left_table.add_row("R", "Refresh / probe Ollama models")
        left_table.add_row("P / D", "Pull / download recommended model")
        left_table.add_row("S / B", "Start Ollama background daemon")

        right_table = Table.grid(padding=(0, 2))
        right_table.add_column("Key", style=f"bold {COLOR_ACCENT}", no_wrap=True)
        right_table.add_column("Action", style=COLOR_TEXT_PRIMARY)

        right_table.add_row("[bold #7dcfff]Config & Generation[/]", "")
        right_table.add_row("L", "Toggle Language (Norwegian / English)")
        right_table.add_row("1-4", "Quick length preset (Quick/Std/Deep/Ext)")
        right_table.add_row("T / G", "Cycle Tone / Grounding Fidelity")
        right_table.add_row("+ / -", "Adjust Temperature (±0.05)")
        right_table.add_row("[ / ]", "Adjust TTS Speed (±2.5%)")
        right_table.add_row("G", "Execute Full Podcast Generation")
        right_table.add_row("S", "Generate Dialogue Script Only")
        right_table.add_row("C", "Cancel active generation/synthesis")
        right_table.add_row("", "")

        right_table.add_row("[bold #ff9e64]Script Studio & Player[/]", "")
        right_table.add_row("Tab", "Switch Formatted Cards / Raw JSON")
        right_table.add_row("↑ / ↓", "Navigate dialogue turns")
        right_table.add_row("A", "Synthesize Audio from Script")
        right_table.add_row("C / S", "Copy Script / Save to disk")
        right_table.add_row("Space", "Play / Pause Audio Track")
        right_table.add_row("← / →", "Seek backward / forward 5s")
        right_table.add_row("E / O", "Export MP3 As... / Open Folder")

        cols_table = Table.grid(padding=(0, 3), expand=True)
        cols_table.add_column("Col1", ratio=1)
        cols_table.add_column("Col2", ratio=1)
        cols_table.add_row(
            Panel(
                left_table,
                title="[bold #7aa2f7]Navigation & Ingestion[/]",
                border_style=COLOR_CARD_BORDER,
                box=BOX_SQUARE,
            ),
            Panel(
                right_table,
                title="[bold #9ece6a]Generation & Playback[/]",
                border_style=COLOR_CARD_BORDER,
                box=BOX_SQUARE,
            ),
        )

        return CardFrame(
            cols_table,
            title="Complete Keyboard Shortcuts Cheat Sheet",
            border_style=COLOR_ACCENT,
        )

    def _render_workflow_tab(self) -> RenderableType:
        """Renders step-by-step workflow guide."""
        items: list[RenderableType] = []

        wf_table = KeyValueTable()
        wf_table.add_row(
            "1. Source Ingestion",
            "Select a document (PDF, TXT, MD), paste text, or simply provide a topic prompt ('--topic'). Document input is completely optional.",
        )
        wf_table.add_row(
            "2. Ollama Connection",
            "Auto-discovers local models (e.g. Llama 3.1, Qwen 2.5, Mistral). Can start the local daemon or pull missing models automatically.",
        )
        wf_table.add_row(
            "3. Preset & Grounding",
            "Select language (NB/EN), episode length (Quick, Standard, Deep Dive, Extended), tone (Casual, Analytical, Debate), and grounding fidelity (Strict, Creative, Open Topic).",
        )
        wf_table.add_row(
            "4. Multi-Act Generation",
            "Ollama streams conversational acts sequentially with live token tracking, maintaining contextual continuity between Host 1 & Host 2.",
        )
        wf_table.add_row(
            "5. Script Studio",
            "Inspect color-coded persona dialogue cards, edit raw JSON dialogue with live syntax checking, copy to clipboard, or save to disk.",
        )
        wf_table.add_row(
            "6. TTS Voice Synthesis",
            "Piper neural TTS synthesizes each turn locally with customizable speed and pitch, falling back cleanly to Edge TTS if needed.",
        )
        wf_table.add_row(
            "7. Zero-FFmpeg Stitching",
            "Concatenates per-turn MP3 frames in pure Python with 350ms natural silence padding and standard ID3v2 metadata tags.",
        )
        wf_table.add_row(
            "8. MCI Audio Player",
            "Play, pause, seek, adjust volume, and export your completed podcast broadcast directly to disk.",
        )

        items.append(wf_table.__rich__())

        return CardFrame(
            Group(*items),
            title="End-to-End Podcast Creation Workflow",
            subtitle="8-Stage Automated & Interactive Pipeline",
            border_style=COLOR_CARD_BORDER,
        )

    def _render_tech_stack_tab(self) -> RenderableType:
        """Renders technical architecture and local privacy stack overview."""
        items: list[RenderableType] = []

        tech_table = KeyValueTable()
        tech_table.add_row(
            "LLM Engine",
            "Ollama local API (http://localhost:11434) with streaming HTTP POST /api/generate and /api/pull.",
        )
        tech_table.add_row(
            "Dialogue Engine",
            "6-Tier Resilient Parser handling JSON markdown blocks, raw JSON arrays, Markdown turns, and regex speaker fallbacks.",
        )
        tech_table.add_row(
            "Voice Engine",
            "Piper ONNX neural TTS with localized voices (no_NO-torkil-medium, en_US-lessac, en_US-ryan) and Edge TTS cloud fallback.",
        )
        tech_table.add_row(
            "Audio Assembly",
            "Pure Python MP3 binary frame stitcher — Zero external FFmpeg binary dependencies required.",
        )
        tech_table.add_row(
            "Audio Playback",
            "Windows Multimedia (winmm.dll) Media Control Interface (MCI) for native, low-latency audio control.",
        )
        tech_table.add_row(
            "Terminal UX",
            "Rich & Textual-inspired Tokyo Night Fluent Dark theme, non-blocking msvcrt input, and Windows VTP terminal restoration.",
        )
        tech_table.add_row(
            "Privacy & Offline",
            "100% local execution. No telemetry, no cloud subscriptions, zero data leaves your local machine.",
        )

        items.append(tech_table.__rich__())

        return CardFrame(
            Group(*items),
            title="LocalPodcastLLMStudio Technical Architecture",
            subtitle="100% Local & Private Autonomous Podcast Studio",
            border_style=COLOR_CARD_BORDER,
        )

    def __rich__(self) -> RenderableType:
        """Assembles the full HelpScreen layout."""
        header = SectionHeader(
            title="LocalPodcastLLMStudio Help & Reference",
            subtitle="Full keyboard cheat sheet, technology architecture, and workflow instructions",
            icon="ℹ️",
        )

        tab_header = self._render_tab_header()

        if self.active_tab == self.TAB_SHORTCUTS:
            body = self._render_shortcuts_tab()
        elif self.active_tab == self.TAB_WORKFLOW:
            body = self._render_workflow_tab()
        else:
            body = self._render_tech_stack_tab()

        hotkeys = [
            ("Tab", "Switch Section"),
            ("1", "Shortcuts"),
            ("2", "Workflow"),
            ("3", "Tech Stack"),
            ("Esc / Q", "Dashboard"),
        ]
        footer = HotkeyBar(shortcuts=hotkeys)

        return Group(
            header,
            Text(""),
            tab_header,
            Text(""),
            body,
            Text(""),
            footer,
        )

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.__rich__()
