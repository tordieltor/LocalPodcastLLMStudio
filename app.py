"""
LocalPodcastLLMStudio - Universal 100% Local AI Podcast Desktop Application
Main executable entry point initializing CustomTkinter runtime, global crash logger,
and the primary application window.
"""

import os
import sys
import traceback
from typing import Any

import customtkinter as ctk

from ui.main_window import MainWindow


def log_crash(exc_type: Any, exc_value: Any, exc_traceback: Any) -> None:
    """
    Top-level unhandled exception hook.
    Writes full traceback to crash_dump.log so errors are captured even in --noconsole mode.
    """
    log_path = os.path.abspath(os.path.join(os.getcwd(), "crash_dump.log"))
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 70}\n")
            f.write(f"LocalPodcastLLMStudio Crash Report - {sys.version}\n")
            f.write(f"{'=' * 70}\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except OSError:
        pass

    # Print to stderr if console is available
    traceback.print_exception(exc_type, exc_value, exc_traceback)


def main() -> None:
    """Main application bootstrap routine."""
    # Register crash hook
    sys.excepthook = log_crash

    # Initialize CustomTkinter appearance & theme
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    # Instantiate and run main window
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
