"""
LocalPodcastLLMStudio - Windows 11 Fluent Dark Theme & Styling Constants
Defines the color palette, typography, layout dimensions, and DWM window integration.
"""

import ctypes
import sys

import customtkinter as ctk

# ==============================================================================
# Windows 11 Fluent Dark Color Palette (Tokyo Night & Modern Slate)
# ==============================================================================

# Backgrounds & Surfaces
COLOR_BG = "#1a1b26"  # App background (deep Tokyo dark slate)
COLOR_CARD = "#24283b"  # Card / surface background
COLOR_CARD_HOVER = "#2f3549"  # Card hover state
COLOR_CARD_BORDER = "#414868"  # Subtle card border
COLOR_INPUT_BG = "#16161e"  # Textbox and input entry background
COLOR_INPUT_BORDER = "#414868"  # Border for text inputs and dropdowns
COLOR_TOOLBAR = "#1f2335"  # Toolbar / action bar background

# Accent & Action Colors
COLOR_ACCENT = "#7aa2f7"  # Primary vibrant accent (Tokyo Cyan / Blue)
COLOR_ACCENT_HOVER = "#565f89"  # Accent hover state
COLOR_ACCENT_ACTIVE = "#3d59a1"  # Accent pressed state

# Standardized Button Colors
COLOR_BUTTON_SECONDARY = "#2b314a"  # Secondary action button (Refresh, About, Secondary)
COLOR_BUTTON_SECONDARY_HOVER = "#3d4566"  # Secondary hover state
COLOR_BUTTON_CLOSE = "#33384d"  # Neutral / Close / Browse button
COLOR_BUTTON_CLOSE_HOVER = "#414868"  # Neutral / Close hover state
COLOR_BUTTON_SUCCESS = "#9ece6a"  # Success action button (Start, Complete)
COLOR_BUTTON_SUCCESS_HOVER = "#7fb84e"  # Success hover state
COLOR_BUTTON_DANGER = "#f7768e"  # Cancel / Abort button
COLOR_BUTTON_DANGER_HOVER = "#db4b4b"  # Cancel hover state

# State Indicators
COLOR_SUCCESS = "#9ece6a"  # Vibrant emerald green (Connected / Ready)
COLOR_WARNING = "#ff9e64"  # Warm amber orange (Checking / Busy / Warning)
COLOR_ERROR = "#f7768e"  # Soft crimson red (Offline / Error / Cancelled)
COLOR_INFO = "#7dcfff"  # Cyan blue (Informational notifications)

# Progress Bar & Badges
COLOR_PROGRESS_BG = "#1a1c29"  # Progress container card background
COLOR_PROGRESS_TRACK = "#24283b"  # Unfilled progress bar track
COLOR_PROGRESS_FILL = "#7aa2f7"  # Active progress fill
COLOR_BADGE_BG = "#1f2335"  # Status badge pill container background

# Text & Typography Colors
COLOR_TEXT_PRIMARY = "#c0caf5"  # High-contrast readable text
COLOR_TEXT_SECONDARY = "#7982a9"  # Muted text for captions and subtitles
COLOR_TEXT_MUTED = "#565f89"  # Deep muted text for placeholders
COLOR_TEXT_DARK = "#15161e"  # Dark text for light button badges

# Persona Speaker Badges
COLOR_HOST1 = "#7aa2f7"  # Host 1 / Kari / Jenny (Accent Cyan Blue)
COLOR_HOST1_BG = "#1f2744"  # Host 1 Dialogue Card Surface
COLOR_HOST2 = "#9ece6a"  # Host 2 / Ola / Guy (Emerald Green)
COLOR_HOST2_BG = "#1d2b27"  # Host 2 Dialogue Card Surface

# ==============================================================================
# Dimensions, Radii, & Paddings
# ==============================================================================
APP_TITLE = "LocalPodcastLLMStudio - 100% Local AI Podcast Generator"
DEFAULT_WINDOW_SIZE = "1200x860"
MIN_WINDOW_WIDTH = 1080
MIN_WINDOW_HEIGHT = 740

CARD_RADIUS = 12
BUTTON_RADIUS = 8
INPUT_RADIUS = 6
BADGE_RADIUS = 14

PADDING_XS = 4
PADDING_SM = 8
PADDING_MD = 14
PADDING_LG = 20


# ==============================================================================
# Typography Helper Functions
# ==============================================================================
def get_font_title() -> ctk.CTkFont:
    """Returns primary window title font."""
    return ctk.CTkFont(family="Segoe UI", size=20, weight="bold")


def get_font_subtitle() -> ctk.CTkFont:
    """Returns window subtitle / subheader font."""
    return ctk.CTkFont(family="Segoe UI", size=12)


def get_font_heading() -> ctk.CTkFont:
    """Returns card section heading font."""
    return ctk.CTkFont(family="Segoe UI", size=14, weight="bold")


def get_font_subheading() -> ctk.CTkFont:
    """Returns bold sub-section heading font (size 12)."""
    return ctk.CTkFont(family="Segoe UI", size=12, weight="bold")


def get_font_body() -> ctk.CTkFont:
    """Returns standard body font."""
    return ctk.CTkFont(family="Segoe UI", size=13)


def get_font_body_bold() -> ctk.CTkFont:
    """Returns bold body font."""
    return ctk.CTkFont(family="Segoe UI", size=13, weight="bold")


def get_font_caption() -> ctk.CTkFont:
    """Returns small caption font."""
    return ctk.CTkFont(family="Segoe UI", size=11)


def get_font_caption_bold() -> ctk.CTkFont:
    """Returns bold caption font (size 11)."""
    return ctk.CTkFont(family="Segoe UI", size=11, weight="bold")


def get_font_badge() -> ctk.CTkFont:
    """Returns status badge font."""
    return ctk.CTkFont(family="Segoe UI", size=11, weight="bold")


def get_font_code() -> ctk.CTkFont:
    """Returns monospaced script / JSON code font."""
    return ctk.CTkFont(family="Consolas", size=12)


def get_font_code_small() -> ctk.CTkFont:
    """Returns compact code font (size 10) for download throughput/ETA."""
    return ctk.CTkFont(family="Consolas", size=10)


# ==============================================================================
# Windows 11 DWM Immersive Dark Title Bar Integration
# ==============================================================================
def enable_windows_dark_titlebar(window: ctk.CTk) -> bool:
    """
    Enables Windows 11 / Windows 10 DWM immersive dark mode on the native title bar.
    Prevents bright white title bar flickering on dark themes.
    """
    if sys.platform != "win32":
        return False

    try:
        window.update_idletasks()
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 11 / 10 build 19041+)
        # DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19 (Windows 10 older builds)
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()

        value = ctypes.c_int(2)  # 2 = DWMWA_USE_IMMERSIVE_DARK_MODE
        try:
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
            )
            if res == 0:
                return True
        except (AttributeError, OSError):
            pass

        # Fallback to attribute 19
        try:
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(value), ctypes.sizeof(value)
            )
            return True
        except (AttributeError, OSError):
            pass

    except (AttributeError, OSError, TypeError, Exception):
        pass

    return False
