"""
PodcastStudio - Modern CustomTkinter Desktop User Interface Package
Fluent Dark UI, reusable cards and widgets, async background event pipeline.
"""

from ui.theme import (
    COLOR_BG,
    COLOR_CARD,
    COLOR_CARD_BORDER,
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    enable_windows_dark_titlebar,
)

from ui.widgets import (
    CardFrame,
    SectionHeader,
    StatusBadge,
    LabeledSlider,
    TimeSlider,
    DialogueTurnCard,
    ActionableErrorDialog,
)

from ui.main_window import (
    MainWindow,
    GenerationWorker,
)

__all__ = [
    # Main Window & Worker
    "MainWindow",
    "GenerationWorker",
    # Theme & Helpers
    "COLOR_BG",
    "COLOR_CARD",
    "COLOR_CARD_BORDER",
    "COLOR_ACCENT",
    "COLOR_SUCCESS",
    "COLOR_WARNING",
    "COLOR_ERROR",
    "enable_windows_dark_titlebar",
    # Widgets
    "CardFrame",
    "SectionHeader",
    "StatusBadge",
    "LabeledSlider",
    "TimeSlider",
    "DialogueTurnCard",
    "ActionableErrorDialog",
]
