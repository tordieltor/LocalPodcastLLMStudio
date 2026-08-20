"""
PodcastStudio - Reusable CustomTkinter UI Components
Contains modern card frames, status badges, labeled sliders, audio timeline scrubber,
dialogue turn bubbles, and actionable error dialogs.
"""

import sys
import tkinter as tk
from typing import Optional, Callable, Any
import customtkinter as ctk

from ui.theme import (
    COLOR_CARD,
    COLOR_CARD_BORDER,
    COLOR_INPUT_BG,
    COLOR_INPUT_BORDER,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED,
    COLOR_HOST1,
    COLOR_HOST1_BG,
    COLOR_HOST2,
    COLOR_HOST2_BG,
    CARD_RADIUS,
    BUTTON_RADIUS,
    INPUT_RADIUS,
    BADGE_RADIUS,
    PADDING_SM,
    PADDING_MD,
    get_font_heading,
    get_font_body,
    get_font_body_bold,
    get_font_caption,
    get_font_badge,
    get_font_title,
    get_font_code,
)


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
        **kwargs
    ):
        super().__init__(
            master=master,
            corner_radius=corner_radius,
            fg_color=fg_color,
            border_color=border_color,
            border_width=border_width,
            **kwargs
        )


class SectionHeader(ctk.CTkFrame):
    """
    Section header component featuring an icon/number, title, and optional subtitle.
    """

    def __init__(
        self,
        master: Any,
        title: str,
        subtitle: Optional[str] = None,
        icon: Optional[str] = None,
        **kwargs
    ):
        super().__init__(master=master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)

        header_text = f"{icon} {title}" if icon else title
        self.title_label = ctk.CTkLabel(
            self,
            text=header_text,
            font=get_font_heading(),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w"
        )
        self.title_label.pack(anchor="w", fill="x")

        if subtitle:
            self.subtitle_label = ctk.CTkLabel(
                self,
                text=subtitle,
                font=get_font_caption(),
                text_color=COLOR_TEXT_SECONDARY,
                anchor="w"
            )
            self.subtitle_label.pack(anchor="w", fill="x", pady=(2, 0))


class StatusBadge(ctk.CTkFrame):
    """
    Pill-shaped live status badge with a color-coded indicator dot and status text.
    """

    def __init__(
        self,
        master: Any,
        initial_status: str = "checking",
        initial_text: str = "Checking Ollama...",
        **kwargs
    ):
        super().__init__(
            master=master,
            fg_color="#1f2335",
            corner_radius=BADGE_RADIUS,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            **kwargs
        )

        self.dot_label = ctk.CTkLabel(
            self,
            text="●",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_WARNING,
            width=16
        )
        self.dot_label.pack(side="left", padx=(8, 4), pady=4)

        self.text_label = ctk.CTkLabel(
            self,
            text=initial_text,
            font=get_font_badge(),
            text_color=COLOR_TEXT_PRIMARY
        )
        self.text_label.pack(side="left", padx=(0, 10), pady=4)

        self.set_status(initial_status, initial_text)

    def set_status(self, status: str, text: str):
        """
        Updates the badge state and dot color.
        
        Args:
            status: 'online', 'connected', 'offline', 'error', 'checking', 'busy', 'idle'
            text: Status string to display
        """
        st = status.lower()
        if st in ["online", "connected", "ready", "success"]:
            color = COLOR_SUCCESS
        elif st in ["offline", "error", "cancelled"]:
            color = COLOR_ERROR
        elif st in ["checking", "busy", "working", "warning"]:
            color = COLOR_WARNING
        else:
            color = COLOR_INFO

        self.dot_label.configure(text_color=color)
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
        format_fn: Optional[Callable[[float], str]] = None,
        command: Optional[Callable[[float], None]] = None,
        **kwargs
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
            anchor="w"
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
            command=self._on_slider_moved
        )
        self.slider.set(default_value)
        self.slider.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        self.val_label = ctk.CTkLabel(
            self,
            text=self.format_fn(default_value),
            font=get_font_body_bold(),
            text_color=COLOR_ACCENT,
            width=50,
            anchor="e"
        )
        self.val_label.grid(row=0, column=2, sticky="e")

    def _on_slider_moved(self, value: float):
        self.val_label.configure(text=self.format_fn(value))
        if self.user_command:
            self.user_command(value)

    def get(self) -> float:
        return self.slider.get()

    def set(self, value: float):
        self.slider.set(value)
        self.val_label.configure(text=self.format_fn(value))


class TimeSlider(ctk.CTkFrame):
    """
    Timeline audio progress slider showing '00:00 / 03:45' with user scrubbing support.
    """

    def __init__(
        self,
        master: Any,
        on_seek: Optional[Callable[[int], None]] = None,
        **kwargs
    ):
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
            text_color=COLOR_TEXT_SECONDARY
        )
        self.time_label.pack(side="right")

        self.status_mini = ctk.CTkLabel(
            self.info_row,
            text="Stopped",
            font=get_font_caption(),
            text_color=COLOR_TEXT_MUTED
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
            command=self._on_seek_drag
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

    def __init__(
        self,
        master: Any,
        turn_number: int,
        speaker: str,
        text: str,
        **kwargs
    ):
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
            **kwargs
        )

        # Header Row
        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(8, 4))

        speaker_badge = ctk.CTkLabel(
            top_row,
            text=f"🎙️ {display_speaker}",
            font=get_font_body_bold(),
            text_color=accent_color
        )
        speaker_badge.pack(side="left")

        turn_badge = ctk.CTkLabel(
            top_row,
            text=f"Turn #{turn_number}",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY
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
            anchor="w"
        )
        body_label.pack(fill="x", padx=10, pady=(0, 10))


class ActionableErrorDialog(ctk.CTkToplevel):
    """
    Modal error dialog with user-friendly remediation instructions
    (e.g., how to start Ollama or pull models).
    """

    def __init__(
        self,
        parent: Any,
        title: str,
        message: str,
        details: Optional[str] = None,
        action_button_text: Optional[str] = None,
        action_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry("540x360")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_CARD)

        # Modal focus
        self.transient(parent)
        self.grab_set()

        # Icon and Title Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        icon_label = ctk.CTkLabel(
            header_frame,
            text="⚠️",
            font=ctk.CTkFont(size=28)
        )
        icon_label.pack(side="left", padx=(0, 12))

        title_label = ctk.CTkLabel(
            header_frame,
            text=title,
            font=get_font_heading(),
            text_color=COLOR_ERROR,
            anchor="w"
        )
        title_label.pack(side="left", fill="x", expand=True)

        # Message Body
        msg_label = ctk.CTkLabel(
            self,
            text=message,
            font=get_font_body(),
            text_color=COLOR_TEXT_PRIMARY,
            wraplength=480,
            justify="left",
            anchor="w"
        )
        msg_label.pack(fill="x", padx=20, pady=(0, 10))

        # Details Textbox (if available)
        if details:
            details_box = ctk.CTkTextbox(
                self,
                height=100,
                font=get_font_code(),
                fg_color=COLOR_INPUT_BG,
                border_color=COLOR_INPUT_BORDER,
                border_width=1,
                text_color=COLOR_TEXT_SECONDARY
            )
            details_box.pack(fill="both", expand=True, padx=20, pady=(0, 15))
            details_box.insert("1.0", details)
            details_box.configure(state="disabled")

        # Action Buttons Row
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))

        if action_button_text and action_callback:
            action_btn = ctk.CTkButton(
                btn_row,
                text=action_button_text,
                fg_color=COLOR_ACCENT,
                hover_color=COLOR_ACCENT_HOVER,
                font=get_font_body_bold(),
                command=lambda: [self.destroy(), action_callback()]
            )
            action_btn.pack(side="left", padx=(0, 10))

        close_btn = ctk.CTkButton(
            btn_row,
            text="Close",
            fg_color="#33384d",
            hover_color="#414868",
            font=get_font_body(),
            command=self.destroy
        )
        close_btn.pack(side="right")
