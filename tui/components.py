"""
LocalPodcastLLMStudio - Reusable Rich Terminal UI Components
Provides styled cards, badges, sliders, timeline scrubbers, dialogue cards, modals,
and navigation toolbars matching the Windows 11 Fluent Dark Tokyo Night theme.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import rich.box as box
from rich.align import Align
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.panel import Panel
from rich.rule import Rule
from rich.style import StyleType
from rich.table import Table
from rich.text import Text

from core.parser import SpeakerRole, normalize_speaker
from tui.theme import (
    BOX_CARD,
    BOX_MODAL,
    BOX_SQUARE,
    COLOR_ACCENT,
    COLOR_BUTTON_CLOSE,
    COLOR_BUTTON_DANGER,
    COLOR_BUTTON_SECONDARY,
    COLOR_BUTTON_SUCCESS,
    COLOR_CARD_BORDER,
    COLOR_ERROR,
    COLOR_HOST1,
    COLOR_HOST1_BG,
    COLOR_HOST2,
    COLOR_HOST2_BG,
    COLOR_INFO,
    COLOR_PROGRESS_FILL,
    COLOR_SUCCESS,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    GLYPH_DOT,
    GLYPH_GEAR,
    GLYPH_INFO,
    GLYPH_MIC,
    GLYPH_PAUSE,
    GLYPH_PLAY,
    GLYPH_SLIDER_FILL,
    GLYPH_SLIDER_THUMB,
    GLYPH_SLIDER_TRACK,
    GLYPH_STOP,
    GLYPH_WARN,
)


class CardFrame:
    """
    Styled Rich container representing a Windows 11 Fluent Dark / Tokyo Night card.
    Implements Rich renderable protocol for clean composition.
    """

    def __init__(
        self,
        renderable: RenderableType,
        title: str | Text | None = None,
        subtitle: str | Text | None = None,
        subtitle_align: Literal["left", "center", "right"] = "right",
        border_style: StyleType = COLOR_CARD_BORDER,
        box_style: box.Box = BOX_CARD,
        padding: tuple[int, int] = (1, 2),
        expand: bool = True,
        style: StyleType | None = None,
    ) -> None:
        self.renderable: RenderableType = renderable
        self.title: str | Text | None = title
        self.subtitle: str | Text | None = subtitle
        self.subtitle_align: Literal["left", "center", "right"] = subtitle_align
        self.border_style: StyleType = border_style
        self.box_style: box.Box = box_style
        self.padding: tuple[int, int] = padding
        self.expand: bool = expand
        self.style: StyleType | None = style

    def __rich__(self) -> Panel:
        formatted_title: str | Text | None = None
        if isinstance(self.title, str):
            formatted_title = Text.from_markup(f"[bold {COLOR_ACCENT}] {self.title} [/]")
        elif self.title is not None:
            formatted_title = self.title

        formatted_subtitle: str | Text | None = None
        if isinstance(self.subtitle, str):
            formatted_subtitle = Text.from_markup(f"[{COLOR_TEXT_SECONDARY}] {self.subtitle} [/]")
        elif self.subtitle is not None:
            formatted_subtitle = self.subtitle

        return Panel(
            self.renderable,
            title=formatted_title,
            subtitle=formatted_subtitle,
            subtitle_align=self.subtitle_align,
            border_style=self.border_style,
            box=self.box_style,
            padding=self.padding,
            expand=self.expand,
            style=self.style or "none",
        )

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.__rich__()


class StatusBadge:
    """
    Status badge indicator rendering a bracketed pill with color-coded dot glyph and text.
    Matches GUI status categories: online, offline, downloading, checking, warning.
    """

    STATUS_COLORS: dict[str, str] = {
        # Success states
        "online": COLOR_SUCCESS,
        "connected": COLOR_SUCCESS,
        "ready": COLOR_SUCCESS,
        "done": COLOR_SUCCESS,
        "complete": COLOR_SUCCESS,
        "success": COLOR_SUCCESS,
        # Error states
        "offline": COLOR_ERROR,
        "error": COLOR_ERROR,
        "failed": COLOR_ERROR,
        "cancelled": COLOR_ERROR,
        "stopped": COLOR_ERROR,
        "aborted": COLOR_ERROR,
        # Warning / In-progress states
        "checking": COLOR_WARNING,
        "busy": COLOR_WARNING,
        "working": COLOR_WARNING,
        "warning": COLOR_WARNING,
        "starting": COLOR_WARNING,
        "launching": COLOR_WARNING,
        "booting": COLOR_WARNING,
        "missing_model": COLOR_WARNING,
        "no_models": COLOR_WARNING,
        "degraded": COLOR_WARNING,
        # Informational / Download states
        "downloading": COLOR_INFO,
        "pulling": COLOR_INFO,
        "installing": COLOR_INFO,
        "syncing": COLOR_INFO,
        "info": COLOR_INFO,
    }

    def __init__(
        self,
        status: str = "checking",
        text: str = "Checking Ollama...",
        dot_color: str | None = None,
        dot_glyph: str | None = None,
    ) -> None:
        self.status: str = status
        self.text: str = text
        self.dot_color: str | None = dot_color
        self.dot_glyph: str = dot_glyph or GLYPH_DOT

    def set_status(
        self,
        status: str,
        text: str,
        dot_color: str | None = None,
        dot_glyph: str | None = None,
    ) -> None:
        """Updates the status category and displayed text."""
        self.status = status
        self.text = text
        if dot_color is not None:
            self.dot_color = dot_color
        if dot_glyph is not None:
            self.dot_glyph = dot_glyph

    def render(self) -> Text:
        """Builds and returns the styled Rich Text renderable."""
        st = self.status.lower().strip()
        color = self.dot_color or self.STATUS_COLORS.get(st, COLOR_INFO)
        glyph = self.dot_glyph or GLYPH_DOT

        t = Text()
        t.append(" [", style=COLOR_CARD_BORDER)
        t.append(f"{glyph} ", style=f"bold {color}")
        t.append(self.text, style=COLOR_TEXT_PRIMARY)
        t.append("] ", style=COLOR_CARD_BORDER)
        return t

    def __rich__(self) -> Text:
        return self.render()


class LabeledSlider:
    """
    Terminal stepped slider control with label, visual track, and live value readout.
    """

    def __init__(
        self,
        label: str,
        from_: float = -10.0,
        to: float = 15.0,
        number_of_steps: int = 5,
        default_value: float = 0.0,
        format_fn: Callable[[float], str] | None = None,
        width: int = 15,
    ) -> None:
        self.label: str = label
        self.from_: float = from_
        self.to: float = to
        self.number_of_steps: int = max(1, number_of_steps)
        self.value: float = default_value
        self.format_fn: Callable[[float], str] = format_fn or (lambda val: f"{int(val):+d}%")
        self.width: int = width

    def get(self) -> float:
        """Returns the current numeric value."""
        return self.value

    def set(self, value: float) -> None:
        """Sets the current value clamped to [from_, to]."""
        self.value = max(self.from_, min(self.to, value))

    def step_up(self) -> float:
        """Increments value by one step interval."""
        step_size = (self.to - self.from_) / self.number_of_steps
        self.set(self.value + step_size)
        return self.value

    def step_down(self) -> float:
        """Decrements value by one step interval."""
        step_size = (self.to - self.from_) / self.number_of_steps
        self.set(self.value - step_size)
        return self.value

    def render(self) -> Text:
        """Renders the formatted slider line."""
        norm = (
            max(0.0, min(1.0, (self.value - self.from_) / (self.to - self.from_)))
            if self.to > self.from_
            else 0.0
        )
        dot_pos = int(norm * (self.width - 1))

        t = Text()
        t.append(f"{self.label:<14} ", style=COLOR_TEXT_PRIMARY)
        t.append(f"{self.format_fn(self.from_)} ", style=COLOR_TEXT_MUTED)
        t.append("[", style=COLOR_CARD_BORDER)
        for i in range(self.width):
            if i == dot_pos:
                t.append(GLYPH_SLIDER_THUMB, style=f"bold {COLOR_ACCENT}")
            elif i < dot_pos:
                t.append(GLYPH_SLIDER_FILL, style=COLOR_ACCENT)
            else:
                t.append(GLYPH_SLIDER_TRACK, style=COLOR_CARD_BORDER)
        t.append("] ", style=COLOR_CARD_BORDER)
        t.append(f"{self.format_fn(self.to)} ", style=COLOR_TEXT_MUTED)
        t.append(f"({self.format_fn(self.value)})", style=f"bold {COLOR_ACCENT}")
        return t

    def __rich__(self) -> Text:
        return self.render()


class TUIProgressBar:
    """
    Renders high-contrast progress bars for LLM generation, model pulls, and TTS synthesis.
    """

    def __init__(
        self,
        completed: float = 0.0,
        total: float = 100.0,
        description: str = "Processing...",
        status_text: str | None = None,
        width: int = 25,
        fill_color: str = COLOR_PROGRESS_FILL,
    ) -> None:
        self.completed: float = completed
        self.total: float = max(0.001, total)
        self.description: str = description
        self.status_text: str | None = status_text
        self.width: int = width
        self.fill_color: str = fill_color

    def update(
        self,
        completed: float,
        total: float | None = None,
        status_text: str | None = None,
    ) -> None:
        """Updates progress metrics and optional status caption."""
        self.completed = completed
        if total is not None:
            self.total = max(0.001, total)
        if status_text is not None:
            self.status_text = status_text

    def render(self) -> Text:
        """Renders the visual progress bar."""
        pct = max(0.0, min(1.0, self.completed / self.total))
        fill_count = int(pct * self.width)
        color = COLOR_SUCCESS if pct >= 1.0 else self.fill_color

        t = Text()
        if self.description:
            t.append(f"{self.description} ", style=COLOR_TEXT_PRIMARY)

        t.append("[", style=COLOR_CARD_BORDER)
        for i in range(self.width):
            if i < fill_count:
                t.append(GLYPH_SLIDER_FILL, style=color)
            else:
                t.append(GLYPH_SLIDER_TRACK, style=COLOR_CARD_BORDER)
        t.append("] ", style=COLOR_CARD_BORDER)

        t.append(f"{int(pct * 100):3d}%", style=f"bold {color}")
        if self.status_text:
            t.append(f"  ({self.status_text})", style=COLOR_TEXT_SECONDARY)
        return t

    def __rich__(self) -> Text:
        return self.render()


class TimeSlider:
    """
    Timeline audio progress slider showing '00:00 / 03:45' with visual scrubber bar.
    """

    def __init__(
        self,
        current_ms: int = 0,
        total_ms: int = 0,
        mode_str: str = "Stopped",
        width: int = 24,
    ) -> None:
        self.current_ms: int = current_ms
        self.total_ms: int = total_ms
        self.mode_str: str = mode_str
        self.width: int = width

    def update_position(self, current_ms: int, total_ms: int, mode_str: str = "") -> None:
        """Updates timestamp positions and playback mode."""
        self.current_ms = current_ms
        self.total_ms = total_ms
        if mode_str:
            self.mode_str = mode_str

    @staticmethod
    def format_ms(ms: int) -> str:
        """Formats milliseconds into MM:SS format."""
        sec = max(0, int(ms / 1000))
        m = sec // 60
        s = sec % 60
        return f"{m:02d}:{s:02d}"

    def render(self) -> Text:
        """Renders the audio timeline line with mode glyph."""
        pct = min(1.0, max(0.0, self.current_ms / self.total_ms)) if self.total_ms > 0 else 0.0
        dot_pos = int(pct * (self.width - 1))

        mode_lower = self.mode_str.lower()
        if mode_lower == "playing":
            mode_prefix = f"{GLYPH_PLAY} Playing"
            mode_style = f"bold {COLOR_SUCCESS}"
        elif mode_lower == "paused":
            mode_prefix = f"{GLYPH_PAUSE} Paused"
            mode_style = f"bold {COLOR_WARNING}"
        else:
            mode_prefix = f"{GLYPH_STOP} Stopped"
            mode_style = COLOR_TEXT_MUTED

        cur_str = self.format_ms(self.current_ms)
        tot_str = self.format_ms(self.total_ms)

        t = Text()
        t.append(f"{mode_prefix:<11} ", style=mode_style)
        t.append("[", style=COLOR_CARD_BORDER)
        for i in range(self.width):
            if i == dot_pos and self.total_ms > 0:
                t.append(GLYPH_SLIDER_THUMB, style=f"bold {COLOR_ACCENT}")
            elif i < dot_pos:
                t.append(GLYPH_SLIDER_FILL, style=COLOR_ACCENT)
            else:
                t.append(GLYPH_SLIDER_TRACK, style=COLOR_CARD_BORDER)
        t.append("] ", style=COLOR_CARD_BORDER)
        t.append(f"{cur_str} / {tot_str}", style=f"bold {COLOR_TEXT_PRIMARY}")
        t.append(f"  ({int(pct * 100):3d}%)", style=COLOR_TEXT_SECONDARY)
        return t

    def __rich__(self) -> Text:
        return self.render()


class DialogueTurnCard:
    """
    Visual rich dialogue turn card highlighting Host 1 (Cyan/Blue) vs Host 2 (Green).
    Interprets persona metadata and formats speech text with clean card styling.
    """

    def __init__(
        self,
        turn_number: int,
        speaker: str,
        text: str,
        language: str = "nb-NO",
        audio_status: str | None = None,
    ) -> None:
        self.turn_number: int = turn_number
        self.speaker: str = speaker
        self.text: str = text
        self.language: str = language
        self.audio_status: str | None = audio_status

    def __rich__(self) -> Panel:
        role = SpeakerRole.from_speaker(self.speaker)
        is_host1 = role == SpeakerRole.HOST_1

        accent_color = COLOR_HOST1 if is_host1 else COLOR_HOST2
        bg_color = COLOR_HOST1_BG if is_host1 else COLOR_HOST2_BG

        # Determine persona display name
        norm = normalize_speaker(self.speaker)
        if norm == "Host 1":
            persona_name = "Host 1 (Kari)" if "nb" in self.language.lower() else "Host 1 (Jenny)"
        elif norm == "Host 2":
            persona_name = "Host 2 (Ola)" if "nb" in self.language.lower() else "Host 2 (Guy)"
        else:
            persona_name = self.speaker

        # Title markup
        title_text = Text()
        title_text.append(f"{GLYPH_MIC} {persona_name}", style=f"bold {accent_color}")
        title_text.append(f"  Turn #{self.turn_number}", style=COLOR_TEXT_SECONDARY)

        subtitle_text: Text | None = None
        if self.audio_status:
            subtitle_text = Text(f" {self.audio_status} ", style=COLOR_TEXT_SECONDARY)

        body = Text(self.text, style=COLOR_TEXT_PRIMARY)

        return Panel(
            body,
            title=title_text,
            subtitle=subtitle_text,
            subtitle_align="right",
            border_style=accent_color,
            box=BOX_CARD,
            padding=(0, 1),
            style=f"on {bg_color}",
        )


class ActionableModal:
    """
    Overlay modal box for errors, missing models, prerequisites, and confirmations.
    Provides numbered action buttons and remediation advice.
    """

    TYPE_CONFIGS: dict[str, dict[str, Any]] = {
        "error": {"icon": GLYPH_WARN, "color": COLOR_ERROR, "box": BOX_MODAL},
        "warning": {"icon": GLYPH_WARN, "color": COLOR_WARNING, "box": BOX_MODAL},
        "info": {"icon": GLYPH_INFO, "color": COLOR_INFO, "box": box.ROUNDED},
        "prerequisite": {"icon": GLYPH_GEAR, "color": COLOR_ACCENT, "box": box.ROUNDED},
    }

    def __init__(
        self,
        title: str,
        message: str,
        details: str | None = None,
        actions: list[dict[str, Any]] | None = None,
        modal_type: str = "error",
        close_text: str = "Close",
        width: int = 70,
    ) -> None:
        self.title: str = title
        self.message: str = message
        self.details: str | None = details
        self.actions: list[dict[str, Any]] = actions or []
        self.modal_type: str = modal_type.lower()
        self.close_text: str = close_text
        self.width: int = width

    def __rich__(self) -> RenderableType:
        cfg = self.TYPE_CONFIGS.get(self.modal_type, self.TYPE_CONFIGS["error"])
        color = cfg["color"]
        icon = cfg["icon"]
        box_style = cfg["box"]

        render_items: list[RenderableType] = []

        # Message Body
        render_items.append(Text(self.message, style=COLOR_TEXT_PRIMARY))

        # Remediation / Details Box
        if self.details:
            render_items.append(Text(""))
            det_panel = Panel(
                Text(self.details, style=COLOR_TEXT_SECONDARY),
                title="[bold #7982a9] Remediation / Details [/]",
                border_style=COLOR_CARD_BORDER,
                box=BOX_SQUARE,
                padding=(0, 1),
            )
            render_items.append(det_panel)

        render_items.append(Text(""))

        # Action Buttons Row
        action_table = Table.grid(padding=(0, 2))
        action_row: list[str] = []

        for i, act in enumerate(self.actions, start=1):
            btn_text = act.get("text", f"Action {i}")
            btn_style = str(act.get("style", "accent")).lower()

            if btn_style in ["primary", "accent"]:
                btn = f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [{i}] {btn_text} [/]"
            elif btn_style in ["success", "ready"]:
                btn = f"[bold {COLOR_TEXT_DARK} on {COLOR_BUTTON_SUCCESS}] [{i}] {btn_text} [/]"
            elif btn_style in ["danger", "error"]:
                btn = f"[bold {COLOR_TEXT_PRIMARY} on {COLOR_BUTTON_DANGER}] [{i}] {btn_text} [/]"
            else:
                btn = (
                    f"[bold {COLOR_TEXT_PRIMARY} on {COLOR_BUTTON_SECONDARY}] [{i}] {btn_text} [/]"
                )

            action_row.append(btn)

        action_row.append(
            f"[bold {COLOR_TEXT_PRIMARY} on {COLOR_BUTTON_CLOSE}] [Esc] {self.close_text} [/]"
        )
        action_table.add_row(*action_row)
        render_items.append(action_table)

        modal_panel = Panel(
            Align.left(Group(*render_items)),
            title=f"[{color} bold] {icon} {self.title} [/]",
            border_style=color,
            box=box_style,
            width=self.width,
            padding=(1, 2),
        )

        return Align.center(modal_panel)


class SectionHeader:
    """Section header featuring an icon, title, optional subtitle, and accent divider rule."""

    def __init__(
        self,
        title: str,
        subtitle: str | None = None,
        icon: str | None = None,
    ) -> None:
        self.title: str = title
        self.subtitle: str | None = subtitle
        self.icon: str | None = icon

    def __rich__(self) -> RenderableType:
        heading_text = f"{self.icon} {self.title}" if self.icon else self.title
        rule = Rule(
            title=f"[bold {COLOR_ACCENT}]{heading_text}[/]",
            align="left",
            style=COLOR_CARD_BORDER,
        )
        if self.subtitle:
            sub = Text(f"  {self.subtitle}", style=COLOR_TEXT_SECONDARY)
            return Group(rule, sub)
        return rule


class KeyValueTable:
    """Styled 2-column key-value settings table."""

    def __init__(self, title: str | None = None) -> None:
        self.table: Table = Table.grid(padding=(0, 2))
        self.table.add_column("Key", style=f"bold {COLOR_ACCENT}", no_wrap=True)
        self.table.add_column("Value", style=COLOR_TEXT_PRIMARY)

    def add_row(self, key: str, value: str) -> None:
        """Appends a key-value row."""
        self.table.add_row(f"{key}:", value)

    def __rich__(self) -> Table:
        return self.table


class HotkeyBar:
    """Bottom footer bar rendering navigation hotkey shortcuts."""

    def __init__(self, shortcuts: list[tuple[str, str]]) -> None:
        self.shortcuts: list[tuple[str, str]] = shortcuts

    def __rich__(self) -> Text:
        t = Text()
        for idx, (key, label) in enumerate(self.shortcuts):
            if idx > 0:
                t.append("  ", style=COLOR_CARD_BORDER)
            t.append(f" {key} ", style=f"bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}")
            t.append(f" {label}", style=COLOR_TEXT_SECONDARY)
        return t
