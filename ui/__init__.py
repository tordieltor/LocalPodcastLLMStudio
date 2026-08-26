"""
LocalPodcastLLMStudio - Modern CustomTkinter Desktop User Interface Package
Fluent Dark UI, reusable cards and widgets, async background event pipeline.
"""

from ui.main_window import (
    GenerationWorker,
    MainWindow,
    URLExtractionWorker,
)
from ui.theme import (
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_CARD,
    COLOR_CARD_BORDER,
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_WARNING,
    enable_windows_dark_titlebar,
)
from ui.widgets import (
    AboutDialog,
    ActionableErrorDialog,
    CardFrame,
    DialogueTurnCard,
    LabeledSlider,
    LiveStreamingCard,
    SectionHeader,
    StageProgressTracker,
    StatusBadge,
    TimeSlider,
)

__all__ = [
    # Main Window & Worker
    "MainWindow",
    "GenerationWorker",
    "URLExtractionWorker",
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
    "LiveStreamingCard",
    "StageProgressTracker",
    "ActionableErrorDialog",
    "AboutDialog",
]
