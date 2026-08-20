"""
LocalPodcastLLMStudio - Reusable CustomTkinter UI Components
Contains modern card frames, status badges, labeled sliders, audio timeline scrubber,
dialogue turn bubbles, and actionable error dialogs.
"""

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from ui.about_dialog import AboutDialog
from ui.theme import (
    BADGE_RADIUS,
    CARD_RADIUS,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_BADGE_BG,
    COLOR_BUTTON_CLOSE,
    COLOR_BUTTON_CLOSE_HOVER,
    COLOR_BUTTON_DANGER,
    COLOR_BUTTON_DANGER_HOVER,
    COLOR_BUTTON_SECONDARY,
    COLOR_BUTTON_SECONDARY_HOVER,
    COLOR_BUTTON_SUCCESS,
    COLOR_BUTTON_SUCCESS_HOVER,
    COLOR_CARD,
    COLOR_CARD_BORDER,
    COLOR_ERROR,
    COLOR_HOST1,
    COLOR_HOST1_BG,
    COLOR_HOST2,
    COLOR_HOST2_BG,
    COLOR_INFO,
    COLOR_INPUT_BG,
    COLOR_INPUT_BORDER,
    COLOR_SUCCESS,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    get_font_badge,
    get_font_body,
    get_font_body_bold,
    get_font_caption,
    get_font_code,
    get_font_heading,
)

__all__ = [
    "AboutDialog",
    "ActionableErrorDialog",
    "CardFrame",
    "DialogueTurnCard",
    "LabeledSlider",
    "SectionHeader",
    "StatusBadge",
    "TimeSlider",
]


class CardFrame(ctk.CTkFrame):
    """
    Styled CustomTkinter frame representing a Windows 11 Fluent Dark card.
    """

    def __init__(
        self,
        master: Any,
        corner_radius: int = CARD_RADIUS,
        fg_color: str = COLOR_CARD,
        border_color: str = COLOR_CARD_BORDER,
        border_width: int = 1,
        **kwargs,
    ):
        super().__init__(
            master=master,
            corner_radius=corner_radius,
            fg_color=fg_color,
            border_color=border_color,
            border_width=border_width,
            **kwargs,
        )


class SectionHeader(ctk.CTkFrame):
    """
    Section header component featuring an icon/number, title, and optional subtitle.
    """

    def __init__(
        self,
        master: Any,
        title: str,
        subtitle: str | None = None,
        icon: str | None = None,
        **kwargs,
    ):
        super().__init__(master=master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)

        header_text = f"{icon} {title}" if icon else title
        self.title_label = ctk.CTkLabel(
            self,
            text=header_text,
            font=get_font_heading(),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        self.title_label.pack(anchor="w", fill="x")

        if subtitle:
            self.subtitle_label = ctk.CTkLabel(
                self,
                text=subtitle,
                font=get_font_caption(),
                text_color=COLOR_TEXT_SECONDARY,
                anchor="w",
            )
            self.subtitle_label.pack(anchor="w", fill="x", pady=(2, 0))


class StatusBadge(ctk.CTkFrame):
    """
    Pill-shaped live status badge with a color-coded indicator dot and status text.
    Supports online, offline, downloading, launching, warning, and custom dot overrides.
    """

    def __init__(
        self,
        master: Any,
        initial_status: str = "checking",
        initial_text: str = "Checking Ollama...",
        **kwargs,
    ):
        super().__init__(
            master=master,
            fg_color=COLOR_BADGE_BG,
            corner_radius=BADGE_RADIUS,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            **kwargs,
        )

        self.dot_label = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_WARNING,
            width=16,
        )
        self.dot_label.pack(side="left", padx=(8, 4), pady=4)

        self.text_label = ctk.CTkLabel(
            self, text=initial_text, font=get_font_badge(), text_color=COLOR_TEXT_PRIMARY
        )
        self.text_label.pack(side="left", padx=(0, 10), pady=4)

        self.set_status(initial_status, initial_text)

    def set_status(
        self,
        status: str,
        text: str,
        dot_color: str | None = None,
        dot_glyph: str | None = None,
    ):
        """
        Updates the badge state, dot color, and text string.

        Args:
            status: Status category string ('online', 'offline', 'downloading', 'starting', etc.)
            text: Human-readable text displayed on the badge.
            dot_color: Optional hex color override for the dot.
            dot_glyph: Optional unicode symbol override for the dot (default: '●').
        """
        st = status.lower()
        if dot_color:
            color = dot_color
        elif st in ["online", "connected", "ready", "success", "done", "complete"]:
            color = COLOR_SUCCESS
        elif st in ["offline", "error", "cancelled", "failed", "stopped", "aborted"]:
            color = COLOR_ERROR
        elif st in [
            "checking",
            "busy",
            "working",
            "warning",
            "starting",
            "launching",
            "booting",
            "missing_model",
            "no_models",
            "degraded",
            "partial",
        ]:
            color = COLOR_WARNING
        elif st in ["downloading", "pulling", "installing", "syncing", "info"]:
            color = COLOR_INFO
        else:
            color = COLOR_INFO

        glyph = dot_glyph if dot_glyph is not None else "●"
        self.dot_label.configure(text=glyph, text_color=color)
        self.text_label.configure(text=text)


class LabeledSlider(ctk.CTkFrame):
    """
    Slider control with label, slider bar, and live value readout.
    """

    def __init__(
        self,
        master: Any,
        label: str,
        from_: float = -10.0,
        to: float = 15.0,
        number_of_steps: int = 5,
        default_value: float = 0.0,
        format_fn: Callable[[float], str] | None = None,
        command: Callable[[float], None] | None = None,
        **kwargs,
    ):
        super().__init__(master=master, fg_color="transparent", **kwargs)

        self.format_fn = format_fn or (lambda val: f"{int(val):+d}%")
        self.user_command = command

        self.grid_columnconfigure(1, weight=1)

        self.label = ctk.CTkLabel(
            self,
            text=label,
            font=get_font_body(),
            text_color=COLOR_TEXT_PRIMARY,
            width=90,
            anchor="w",
        )
        self.label.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.slider = ctk.CTkSlider(
            self,
            from_=from_,
            to=to,
            number_of_steps=number_of_steps,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            progress_color=COLOR_ACCENT,
            command=self._on_slider_moved,
        )
        self.slider.set(default_value)
        self.slider.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        self.val_label = ctk.CTkLabel(
            self,
            text=self.format_fn(default_value),
            font=get_font_body_bold(),
            text_color=COLOR_ACCENT,
            width=50,
            anchor="e",
        )
        self.val_label.grid(row=0, column=2, sticky="e")

    def _on_slider_moved(self, value: float):
        self.val_label.configure(text=self.format_fn(value))
        if self.user_command:
            self.user_command(value)

    def get(self) -> float:
        return float(self.slider.get())

    def set(self, value: float):
        self.slider.set(value)
        self.val_label.configure(text=self.format_fn(value))


class TimeSlider(ctk.CTkFrame):
    """
    Timeline audio progress slider showing '00:00 / 03:45' with user scrubbing support.
    """

    def __init__(self, master: Any, on_seek: Callable[[int], None] | None = None, **kwargs):
        super().__init__(master=master, fg_color="transparent", **kwargs)

        self.on_seek = on_seek
        self.is_user_dragging = False
        self.total_duration_ms = 0

        self.grid_columnconfigure(0, weight=1)

        # Time labels row
        self.info_row = ctk.CTkFrame(self, fg_color="transparent")
        self.info_row.pack(fill="x", pady=(0, 2))

        self.time_label = ctk.CTkLabel(
            self.info_row,
            text="00:00 / 00:00",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.time_label.pack(side="right")

        self.status_mini = ctk.CTkLabel(
            self.info_row, text="Stopped", font=get_font_caption(), text_color=COLOR_TEXT_MUTED
        )
        self.status_mini.pack(side="left")

        # Slider scrubber
        self.slider = ctk.CTkSlider(
            self,
            from_=0,
            to=100,
            number_of_steps=1000,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            progress_color=COLOR_ACCENT,
            command=self._on_seek_drag,
        )
        self.slider.set(0)
        self.slider.pack(fill="x")

        # Bind mouse release to finalize seek
        self.slider.bind("<ButtonRelease-1>", self._on_seek_release)

    def _on_seek_drag(self, val: float):
        self.is_user_dragging = True

    def _on_seek_release(self, event):
        self.is_user_dragging = False
        if self.on_seek and self.total_duration_ms > 0:
            target_pct = self.slider.get() / 100.0
            target_ms = int(target_pct * self.total_duration_ms)
            self.on_seek(target_ms)

    def update_position(self, current_ms: int, total_ms: int, mode_str: str = ""):
        """
        Updates the scrubber slider and time label if the user is not actively dragging.
        """
        self.total_duration_ms = total_ms
        if mode_str:
            self.status_mini.configure(text=mode_str.capitalize())

        cur_str = self._format_ms(current_ms)
        tot_str = self._format_ms(total_ms)
        self.time_label.configure(text=f"{cur_str} / {tot_str}")

        if not self.is_user_dragging:
            if total_ms > 0:
                pct = min(100.0, (current_ms / total_ms) * 100.0)
                self.slider.set(pct)
            else:
                self.slider.set(0)

    @staticmethod
    def _format_ms(ms: int) -> str:
        sec = max(0, int(ms / 1000))
        m = sec // 60
        s = sec % 60
        return f"{m:02d}:{s:02d}"


class DialogueTurnCard(ctk.CTkFrame):
    """
    Visual rich dialogue turn card highlighting Host 1 (Cyan/Blue) vs Host 2 (Green).
    """

    def __init__(self, master: Any, turn_number: int, speaker: str, text: str, **kwargs):
        is_host1 = "1" in speaker or "Kari" in speaker or "Jenny" in speaker
        bg_color = COLOR_HOST1_BG if is_host1 else COLOR_HOST2_BG
        accent_color = COLOR_HOST1 if is_host1 else COLOR_HOST2
        display_speaker = speaker

        super().__init__(
            master=master,
            fg_color=bg_color,
            corner_radius=8,
            border_color=accent_color,
            border_width=1,
            **kwargs,
        )

        # Header Row
        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(8, 4))

        speaker_badge = ctk.CTkLabel(
            top_row, text=f"🎙️ {display_speaker}", font=get_font_body_bold(), text_color=accent_color
        )
        speaker_badge.pack(side="left")

        turn_badge = ctk.CTkLabel(
            top_row,
            text=f"Turn #{turn_number}",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY,
        )
        turn_badge.pack(side="right")

        # Text Body
        body_label = ctk.CTkLabel(
            self,
            text=text,
            font=get_font_body(),
            text_color=COLOR_TEXT_PRIMARY,
            wraplength=480,
            justify="left",
            anchor="w",
        )
        body_label.pack(fill="x", padx=10, pady=(0, 10))


class ActionableErrorDialog(ctk.CTkToplevel):
    """
    Modal diagnostic and error dialog with user-friendly remediation instructions
    and multi-action interactive buttons (e.g., Start Ollama, Download Model, Retry).
    100% backwards-compatible with legacy single-action and remedy parameters.
    """

    def __init__(
        self,
        parent: Any,
        title: str,
        message: str,
        details: str | None = None,
        action_button_text: str | None = None,
        action_callback: Callable[[], None] | None = None,
        remedy: str | None = None,
        actions: list[dict[str, Any] | tuple[Any, ...]] | None = None,
        close_text: str = "Close",
        dialog_type: str = "error",
        icon: str | None = None,
        width: int = 560,
        height: int = 400,
    ):
        super().__init__(parent)
        details = details or remedy

        self.title(title)
        self.geometry(f"{width}x{height}")
        self.minsize(480, 320)
        self.configure(fg_color=COLOR_CARD)

        # Modal focus configuration
        try:
            self.transient(parent)
            self.grab_set()
        except (RuntimeError, AttributeError, ValueError, TypeError):
            pass

        # Center on parent window
        self._center_on_parent(parent, width, height)

        # Header Icon & Title Colors by Dialog Type
        header_colors = {
            "error": (COLOR_ERROR, icon or "⚠️"),
            "warning": (COLOR_WARNING, icon or "⚠️"),
            "info": (COLOR_INFO, icon or "ℹ️"),
            "prerequisite": (COLOR_ACCENT, icon or "⚙️"),
        }
        title_color, default_icon = header_colors.get(
            dialog_type.lower(), (COLOR_ERROR, icon or "⚠️")
        )
        display_icon = icon if icon is not None else default_icon

        # Icon and Title Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        icon_label = ctk.CTkLabel(header_frame, text=display_icon, font=ctk.CTkFont(size=28))
        icon_label.pack(side="left", padx=(0, 12))

        title_label = ctk.CTkLabel(
            header_frame, text=title, font=get_font_heading(), text_color=title_color, anchor="w"
        )
        title_label.pack(side="left", fill="x", expand=True)

        # Message Body
        msg_label = ctk.CTkLabel(
            self,
            text=message,
            font=get_font_body(),
            text_color=COLOR_TEXT_PRIMARY,
            wraplength=width - 60,
            justify="left",
            anchor="w",
        )
        msg_label.pack(fill="x", padx=20, pady=(0, 10))

        # Details / Remedy Textbox (if present)
        if details:
            details_box = ctk.CTkTextbox(
                self,
                height=110,
                font=get_font_code(),
                fg_color=COLOR_INPUT_BG,
                border_color=COLOR_INPUT_BORDER,
                border_width=1,
                text_color=COLOR_TEXT_SECONDARY,
            )
            details_box.pack(fill="both", expand=True, padx=20, pady=(0, 15))
            details_box.insert("1.0", details)
            details_box.configure(state="disabled")

        # Action Buttons Row
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))

        # Normalize Action Descriptors
        normalized_actions: list[dict[str, Any]] = []
        if actions:
            for item in actions:
                if isinstance(item, dict):
                    normalized_actions.append(item)
                elif isinstance(item, (tuple, list)):
                    if len(item) == 2:
                        normalized_actions.append(
                            {
                                "text": item[0],
                                "callback": item[1],
                                "style": "accent",
                                "dismiss": True,
                            }
                        )
                    elif len(item) >= 3:
                        normalized_actions.append(
                            {
                                "text": item[0],
                                "callback": item[1],
                                "style": item[2],
                                "dismiss": item[3] if len(item) > 3 else True,
                            }
                        )
        elif action_button_text:
            normalized_actions.append(
                {
                    "text": action_button_text,
                    "callback": action_callback,
                    "style": "accent",
                    "dismiss": True,
                }
            )

        # Render Action Buttons
        for act in normalized_actions:
            btn_text = act.get("text", "Action")
            btn_cb = act.get("callback")
            btn_style = str(act.get("style", "accent")).lower()
            should_dismiss = act.get("dismiss", True)

            # Style mapping
            if btn_style in ["primary", "accent"]:
                fg = COLOR_ACCENT
                hover = COLOR_ACCENT_HOVER
                txt_col = COLOR_TEXT_DARK
            elif btn_style in ["success", "ready"]:
                fg = COLOR_BUTTON_SUCCESS
                hover = COLOR_BUTTON_SUCCESS_HOVER
                txt_col = COLOR_TEXT_DARK
            elif btn_style in ["warning"]:
                fg = COLOR_WARNING
                hover = "#e08a50"
                txt_col = COLOR_TEXT_DARK
            elif btn_style in ["danger", "error"]:
                fg = COLOR_BUTTON_DANGER
                hover = COLOR_BUTTON_DANGER_HOVER
                txt_col = COLOR_TEXT_PRIMARY
            else:  # secondary / ghost
                fg = COLOR_BUTTON_SECONDARY
                hover = COLOR_BUTTON_SECONDARY_HOVER
                txt_col = COLOR_TEXT_PRIMARY

            def _make_handler(cb=btn_cb, dismiss=should_dismiss):
                def _handler():
                    if dismiss:
                        self.destroy()
                    if cb:
                        cb()

                return _handler

            action_btn = ctk.CTkButton(
                btn_row,
                text=btn_text,
                fg_color=fg,
                hover_color=hover,
                text_color=txt_col,
                font=get_font_body_bold(),
                command=_make_handler(),
            )
            action_btn.pack(side="left", padx=(0, 8))

        # Close / Dismiss Button
        close_btn = ctk.CTkButton(
            btn_row,
            text=close_text,
            fg_color=COLOR_BUTTON_CLOSE,
            hover_color=COLOR_BUTTON_CLOSE_HOVER,
            font=get_font_body(),
            command=self.destroy,
        )
        close_btn.pack(side="right")

    def _center_on_parent(self, parent: Any, width: int, height: int):
        """Centers dialog relative to parent window coordinates."""
        try:
            parent.update_idletasks()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            x = max(50, px + (pw - width) // 2)
            y = max(50, py + (ph - height) // 2)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except (RuntimeError, AttributeError, ValueError, TypeError):
            try:
                self.geometry(f"{width}x{height}")
            except (RuntimeError, AttributeError, ValueError, TypeError):
                pass
