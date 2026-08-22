"""
Unit tests for tui/theme.py: Tokyo Night color palette, Rich styles, and glyph mappings.
"""

from __future__ import annotations

import rich.box as box
from rich.style import Style
from rich.theme import Theme

import ui.theme as gui_theme
from tui.theme import (
    BOX_ASCII,
    BOX_CARD,
    BOX_DOUBLE,
    BOX_MODAL,
    BOX_SQUARE,
    COLOR_ACCENT,
    COLOR_ACCENT_ACTIVE,
    COLOR_ACCENT_HOVER,
    COLOR_BADGE_BG,
    COLOR_BG,
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
    COLOR_CARD_HOVER,
    COLOR_ERROR,
    COLOR_HOST1,
    COLOR_HOST1_BG,
    COLOR_HOST2,
    COLOR_HOST2_BG,
    COLOR_INFO,
    COLOR_INPUT_BG,
    COLOR_INPUT_BORDER,
    COLOR_PROGRESS_BG,
    COLOR_PROGRESS_FILL,
    COLOR_PROGRESS_TRACK,
    COLOR_SUCCESS,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TOOLBAR,
    COLOR_WARNING,
    GLYPH_AUDIO,
    GLYPH_CHECK,
    GLYPH_CROSS,
    GLYPH_DOT,
    GLYPH_GEAR,
    GLYPH_INFO,
    GLYPH_MIC,
    GLYPH_PACKAGE,
    GLYPH_PAUSE,
    GLYPH_PLAY,
    GLYPH_SLIDER_FILL,
    GLYPH_SLIDER_THUMB,
    GLYPH_SLIDER_TRACK,
    GLYPH_SPARKLE,
    GLYPH_STOP,
    GLYPH_WARN,
    STYLE_ACCENT,
    STYLE_BADGE,
    STYLE_CARD,
    STYLE_CARD_BORDER,
    STYLE_ERROR,
    STYLE_HEADING,
    STYLE_HIGHLIGHT,
    STYLE_HOST1,
    STYLE_HOST1_CARD,
    STYLE_HOST2,
    STYLE_HOST2_CARD,
    STYLE_HOTKEY,
    STYLE_HOTKEY_DESC,
    STYLE_INFO,
    STYLE_INPUT,
    STYLE_MUTED,
    STYLE_PRIMARY,
    STYLE_SECONDARY,
    STYLE_SUBHEADING,
    STYLE_SUCCESS,
    STYLE_TITLE,
    STYLE_WARNING,
    TOKYO_NIGHT_THEME,
    get_tokyo_night_theme,
)


def test_theme_color_parity_with_gui() -> None:
    """Verifies that all terminal colors match the desktop GUI hex palette exactly."""
    assert COLOR_BG == gui_theme.COLOR_BG
    assert COLOR_CARD == gui_theme.COLOR_CARD
    assert COLOR_CARD_HOVER == gui_theme.COLOR_CARD_HOVER
    assert COLOR_CARD_BORDER == gui_theme.COLOR_CARD_BORDER
    assert COLOR_INPUT_BG == gui_theme.COLOR_INPUT_BG
    assert COLOR_INPUT_BORDER == gui_theme.COLOR_INPUT_BORDER
    assert COLOR_TOOLBAR == gui_theme.COLOR_TOOLBAR
    assert COLOR_ACCENT == gui_theme.COLOR_ACCENT
    assert COLOR_ACCENT_HOVER == gui_theme.COLOR_ACCENT_HOVER
    assert COLOR_ACCENT_ACTIVE == gui_theme.COLOR_ACCENT_ACTIVE
    assert COLOR_BUTTON_SECONDARY == gui_theme.COLOR_BUTTON_SECONDARY
    assert COLOR_BUTTON_SECONDARY_HOVER == gui_theme.COLOR_BUTTON_SECONDARY_HOVER
    assert COLOR_BUTTON_CLOSE == gui_theme.COLOR_BUTTON_CLOSE
    assert COLOR_BUTTON_CLOSE_HOVER == gui_theme.COLOR_BUTTON_CLOSE_HOVER
    assert COLOR_BUTTON_SUCCESS == gui_theme.COLOR_BUTTON_SUCCESS
    assert COLOR_BUTTON_SUCCESS_HOVER == gui_theme.COLOR_BUTTON_SUCCESS_HOVER
    assert COLOR_BUTTON_DANGER == gui_theme.COLOR_BUTTON_DANGER
    assert COLOR_BUTTON_DANGER_HOVER == gui_theme.COLOR_BUTTON_DANGER_HOVER
    assert COLOR_SUCCESS == gui_theme.COLOR_SUCCESS
    assert COLOR_WARNING == gui_theme.COLOR_WARNING
    assert COLOR_ERROR == gui_theme.COLOR_ERROR
    assert COLOR_INFO == gui_theme.COLOR_INFO
    assert COLOR_PROGRESS_BG == gui_theme.COLOR_PROGRESS_BG
    assert COLOR_PROGRESS_TRACK == gui_theme.COLOR_PROGRESS_TRACK
    assert COLOR_PROGRESS_FILL == gui_theme.COLOR_PROGRESS_FILL
    assert COLOR_BADGE_BG == gui_theme.COLOR_BADGE_BG
    assert COLOR_TEXT_PRIMARY == gui_theme.COLOR_TEXT_PRIMARY
    assert COLOR_TEXT_SECONDARY == gui_theme.COLOR_TEXT_SECONDARY
    assert COLOR_TEXT_MUTED == gui_theme.COLOR_TEXT_MUTED
    assert COLOR_TEXT_DARK == gui_theme.COLOR_TEXT_DARK
    assert COLOR_HOST1 == gui_theme.COLOR_HOST1
    assert COLOR_HOST1_BG == gui_theme.COLOR_HOST1_BG
    assert COLOR_HOST2 == gui_theme.COLOR_HOST2
    assert COLOR_HOST2_BG == gui_theme.COLOR_HOST2_BG


def test_rich_style_instances() -> None:
    """Verifies that all precompiled Style constants are valid Style objects."""
    styles = [
        STYLE_PRIMARY,
        STYLE_SECONDARY,
        STYLE_MUTED,
        STYLE_ACCENT,
        STYLE_TITLE,
        STYLE_HEADING,
        STYLE_SUBHEADING,
        STYLE_CARD,
        STYLE_CARD_BORDER,
        STYLE_INPUT,
        STYLE_SUCCESS,
        STYLE_WARNING,
        STYLE_ERROR,
        STYLE_INFO,
        STYLE_HOST1,
        STYLE_HOST1_CARD,
        STYLE_HOST2,
        STYLE_HOST2_CARD,
        STYLE_BADGE,
        STYLE_HIGHLIGHT,
        STYLE_HOTKEY,
        STYLE_HOTKEY_DESC,
    ]
    for s in styles:
        assert isinstance(s, Style)


def test_theme_registration() -> None:
    """Verifies that get_tokyo_night_theme provides all expected style keys."""
    theme = get_tokyo_night_theme()
    assert isinstance(theme, Theme)
    assert theme is TOKYO_NIGHT_THEME

    expected_keys = [
        "text",
        "text.secondary",
        "text.muted",
        "dim",
        "muted",
        "accent",
        "title",
        "heading",
        "subheading",
        "card",
        "card.border",
        "input",
        "success",
        "warning",
        "error",
        "info",
        "host1",
        "host1.card",
        "host2",
        "host2.card",
        "badge",
        "highlight",
        "key",
        "rule.line",
        "progress.percentage",
    ]
    for key in expected_keys:
        assert key in theme.styles


def test_box_and_glyph_constants() -> None:
    """Verifies that box-drawing objects and glyph strings are properly set."""
    assert BOX_CARD == box.ROUNDED
    assert BOX_MODAL == box.HEAVY
    assert BOX_DOUBLE == box.DOUBLE
    assert BOX_SQUARE == box.SQUARE
    assert BOX_ASCII == box.ASCII

    assert GLYPH_DOT == "●"
    assert GLYPH_CHECK == "✓"
    assert GLYPH_CROSS == "✗"
    assert GLYPH_WARN == "⚠️"
    assert GLYPH_INFO == "ℹ️"
    assert GLYPH_GEAR == "⚙️"
    assert GLYPH_MIC == "🎙️"
    assert GLYPH_PLAY == "▶"
    assert GLYPH_PAUSE == "⏸"
    assert GLYPH_STOP == "⏹"
    assert GLYPH_PACKAGE == "📦"
    assert GLYPH_SPARKLE == "✨"
    assert GLYPH_AUDIO == "🔊"
    assert GLYPH_SLIDER_TRACK == "─"
    assert GLYPH_SLIDER_FILL == "━"
    assert GLYPH_SLIDER_THUMB == "●"
