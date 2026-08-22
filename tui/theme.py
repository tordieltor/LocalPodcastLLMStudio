"""
LocalPodcastLLMStudio - Terminal User Interface Theme & Palette Definition
Defines the Tokyo Night / Fluent Dark color palette, Rich styles, box-drawing styles,
theme registration, and glyph symbols for the interactive TUI application.
"""

from __future__ import annotations

import rich.box as box
from rich.style import Style
from rich.theme import Theme

# ==============================================================================
# Windows 11 Fluent Dark Color Palette (Tokyo Night & Modern Slate)
# ==============================================================================

# Backgrounds & Surfaces
COLOR_BG: str = "#1a1b26"  # App background (deep Tokyo dark slate)
COLOR_CARD: str = "#24283b"  # Card / surface background
COLOR_CARD_HOVER: str = "#2f3549"  # Card hover / selection state
COLOR_CARD_BORDER: str = "#414868"  # Subtle card border / divider line
COLOR_INPUT_BG: str = "#16161e"  # Textbox and input entry background
COLOR_INPUT_BORDER: str = "#414868"  # Border for text inputs and dropdowns
COLOR_TOOLBAR: str = "#1f2335"  # Toolbar / action bar background

# Accent & Action Colors
COLOR_ACCENT: str = "#7aa2f7"  # Primary vibrant accent (Tokyo Cyan / Blue)
COLOR_ACCENT_HOVER: str = "#565f89"  # Accent hover state
COLOR_ACCENT_ACTIVE: str = "#3d59a1"  # Accent pressed state

# Standardized Button Colors
COLOR_BUTTON_SECONDARY: str = "#2b314a"  # Secondary action button (Refresh, About)
COLOR_BUTTON_SECONDARY_HOVER: str = "#3d4566"  # Secondary hover state
COLOR_BUTTON_CLOSE: str = "#33384d"  # Neutral / Close / Browse button
COLOR_BUTTON_CLOSE_HOVER: str = "#414868"  # Neutral / Close hover state
COLOR_BUTTON_SUCCESS: str = "#9ece6a"  # Success action button (Start, Complete)
COLOR_BUTTON_SUCCESS_HOVER: str = "#7fb84e"  # Success hover state
COLOR_BUTTON_DANGER: str = "#db4b4b"  # Cancel / Abort button (high-contrast crimson)
COLOR_BUTTON_DANGER_HOVER: str = "#b93540"  # Cancel hover state

# State Indicators
COLOR_SUCCESS: str = "#9ece6a"  # Vibrant emerald green (Connected / Ready / Done)
COLOR_WARNING: str = "#ff9e64"  # Warm amber orange (Checking / Busy / Warning)
COLOR_ERROR: str = "#db4b4b"  # Crimson red (Offline / Error / Cancelled)
COLOR_INFO: str = "#7dcfff"  # Cyan blue (Informational notifications / Downloading)

# Progress Bar & Badges
COLOR_PROGRESS_BG: str = "#1a1c29"  # Progress container background
COLOR_PROGRESS_TRACK: str = "#24283b"  # Unfilled progress bar track
COLOR_PROGRESS_FILL: str = "#7aa2f7"  # Active progress fill
COLOR_BADGE_BG: str = "#1f2335"  # Status badge pill container background

# Text & Typography Colors
COLOR_TEXT_PRIMARY: str = "#c0caf5"  # High-contrast readable text
COLOR_TEXT_SECONDARY: str = "#9aa5ce"  # Readable text for captions and subtitles (>6:1 contrast)
COLOR_TEXT_MUTED: str = "#787c99"  # Legible muted text for placeholders / borders (>4.2:1 contrast)
COLOR_TEXT_DARK: str = (
    "#0f111a"  # High-contrast dark text for light button badges (>9.5:1 contrast)
)

# Persona Speaker Badges
COLOR_HOST1: str = "#7aa2f7"  # Host 1 / Kari / Jenny (Accent Cyan Blue)
COLOR_HOST1_BG: str = "#1f2744"  # Host 1 Dialogue Card Surface
COLOR_HOST2: str = "#9ece6a"  # Host 2 / Ola / Guy (Emerald Green)
COLOR_HOST2_BG: str = "#1d2b27"  # Host 2 Dialogue Card Surface

# ==============================================================================
# Box Drawing Styles & Constants
# ==============================================================================

BOX_CARD: box.Box = box.ROUNDED  # Standard card border (╭─╮│╰─╯)
BOX_MODAL: box.Box = box.HEAVY  # Modal overlay border (┏━┓┃┗━┛)
BOX_DOUBLE: box.Box = box.DOUBLE  # Double border (╔═╗║╚═╝)
BOX_SQUARE: box.Box = box.SQUARE  # Square border (┌─┐│└─┘)
BOX_ASCII: box.Box = box.ASCII  # ASCII fallback (+-+|+-+)

# ==============================================================================
# Status & Persona Glyphs
# ==============================================================================

GLYPH_DOT: str = "●"
GLYPH_CHECK: str = "✓"
GLYPH_CROSS: str = "✗"
GLYPH_WARN: str = "⚠️"
GLYPH_INFO: str = "ℹ️"
GLYPH_GEAR: str = "⚙️"
GLYPH_MIC: str = "🎙️"
GLYPH_PLAY: str = "▶"
GLYPH_PAUSE: str = "⏸"
GLYPH_STOP: str = "⏹"
GLYPH_PACKAGE: str = "📦"
GLYPH_SPARKLE: str = "✨"
GLYPH_AUDIO: str = "🔊"
GLYPH_SLIDER_TRACK: str = "─"
GLYPH_SLIDER_FILL: str = "━"
GLYPH_SLIDER_THUMB: str = "●"

# ==============================================================================
# Precompiled Rich Styles
# ==============================================================================

STYLE_PRIMARY: Style = Style(color=COLOR_TEXT_PRIMARY)
STYLE_SECONDARY: Style = Style(color=COLOR_TEXT_SECONDARY)
STYLE_MUTED: Style = Style(color=COLOR_TEXT_MUTED)
STYLE_ACCENT: Style = Style(color=COLOR_ACCENT, bold=True)
STYLE_TITLE: Style = Style(color=COLOR_ACCENT, bold=True)
STYLE_HEADING: Style = Style(color=COLOR_TEXT_PRIMARY, bold=True)
STYLE_SUBHEADING: Style = Style(color=COLOR_TEXT_PRIMARY, bold=True)

STYLE_CARD: Style = Style(color=COLOR_TEXT_PRIMARY, bgcolor=COLOR_CARD)
STYLE_CARD_BORDER: Style = Style(color=COLOR_CARD_BORDER)
STYLE_INPUT: Style = Style(color=COLOR_TEXT_PRIMARY, bgcolor=COLOR_INPUT_BG)

STYLE_SUCCESS: Style = Style(color=COLOR_SUCCESS, bold=True)
STYLE_WARNING: Style = Style(color=COLOR_WARNING, bold=True)
STYLE_ERROR: Style = Style(color=COLOR_ERROR, bold=True)
STYLE_INFO: Style = Style(color=COLOR_INFO, bold=True)

STYLE_HOST1: Style = Style(color=COLOR_HOST1, bold=True)
STYLE_HOST1_CARD: Style = Style(color=COLOR_TEXT_PRIMARY, bgcolor=COLOR_HOST1_BG)
STYLE_HOST2: Style = Style(color=COLOR_HOST2, bold=True)
STYLE_HOST2_CARD: Style = Style(color=COLOR_TEXT_PRIMARY, bgcolor=COLOR_HOST2_BG)

STYLE_BADGE: Style = Style(color=COLOR_TEXT_PRIMARY, bgcolor=COLOR_BADGE_BG)
STYLE_HIGHLIGHT: Style = Style(color=COLOR_TEXT_DARK, bgcolor=COLOR_ACCENT, bold=True)
STYLE_HOTKEY: Style = Style(color=COLOR_ACCENT, bold=True)
STYLE_HOTKEY_DESC: Style = Style(color=COLOR_TEXT_SECONDARY)

# ==============================================================================
# Rich Theme Registration
# ==============================================================================

TOKYO_NIGHT_THEME: Theme = Theme(
    {
        "text": COLOR_TEXT_PRIMARY,
        "text.secondary": COLOR_TEXT_SECONDARY,
        "text.muted": COLOR_TEXT_MUTED,
        "dim": COLOR_TEXT_MUTED,
        "muted": COLOR_TEXT_MUTED,
        "accent": f"bold {COLOR_ACCENT}",
        "title": f"bold {COLOR_ACCENT}",
        "heading": f"bold {COLOR_TEXT_PRIMARY}",
        "subheading": f"bold {COLOR_TEXT_PRIMARY}",
        "card": f"{COLOR_TEXT_PRIMARY} on {COLOR_CARD}",
        "card.border": COLOR_CARD_BORDER,
        "input": f"{COLOR_TEXT_PRIMARY} on {COLOR_INPUT_BG}",
        "success": f"bold {COLOR_SUCCESS}",
        "warning": f"bold {COLOR_WARNING}",
        "error": f"bold {COLOR_ERROR}",
        "info": f"bold {COLOR_INFO}",
        "host1": f"bold {COLOR_HOST1}",
        "host1.card": f"{COLOR_TEXT_PRIMARY} on {COLOR_HOST1_BG}",
        "host2": f"bold {COLOR_HOST2}",
        "host2.card": f"{COLOR_TEXT_PRIMARY} on {COLOR_HOST2_BG}",
        "badge": f"{COLOR_TEXT_PRIMARY} on {COLOR_BADGE_BG}",
        "highlight": f"bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}",
        "key": f"bold {COLOR_ACCENT}",
        "rule.line": COLOR_CARD_BORDER,
        "progress.data.speed": COLOR_INFO,
        "progress.percentage": COLOR_ACCENT,
        "progress.remaining": COLOR_TEXT_SECONDARY,
    }
)


def get_tokyo_night_theme() -> Theme:
    """Returns the central Tokyo Night Rich Theme instance."""
    return TOKYO_NIGHT_THEME
