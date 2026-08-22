"""
LocalPodcastLLMStudio - Universal 100% Local AI Podcast Desktop Application
Main executable entry point initializing CustomTkinter runtime, global crash logger,
and the primary application window.
"""

import os
import sys
import tempfile
import threading
import traceback
from typing import Any

import customtkinter as ctk

from core.logger import get_log_file_path, get_logger, setup_logging
from ui.main_window import MainWindow

logger = get_logger("bootstrap")


def _resolve_crash_log_path() -> str:
    """Resolves a writable path for crash_dump.log across standard and write-protected directories."""
    candidates = [
        os.path.abspath(os.path.join(os.getcwd(), "crash_dump.log")),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        app_dir = os.path.join(local_app_data, "LocalPodcastLLMStudio")
        candidates.append(os.path.join(app_dir, "crash_dump.log"))
    candidates.append(os.path.join(tempfile.gettempdir(), "LocalPodcastLLMStudio_crash_dump.log"))

    for candidate in candidates:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(candidate)), exist_ok=True)
            with open(candidate, "a", encoding="utf-8"):
                pass
            return candidate
        except OSError:
            continue
    return os.path.abspath("crash_dump.log")


def log_crash(exc_type: Any, exc_value: Any, exc_traceback: Any) -> None:
    """
    Top-level unhandled exception hook.
    Writes full traceback to crash_dump.log and application log.
    """
    logger.critical(
        "Unhandled exception encountered: %s",
        exc_value,
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    log_path = _resolve_crash_log_path()
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
    # Initialize unified local logging
    setup_logging()
    logger.info("Starting LocalPodcastLLMStudio desktop application...")
    logger.info("Application log file: %s", get_log_file_path())

    # Register crash hooks for main thread and background worker threads
    sys.excepthook = log_crash
    if hasattr(threading, "excepthook"):
        threading.excepthook = lambda args: log_crash(
            args.exc_type, args.exc_value, args.exc_traceback
        )

    # Initialize CustomTkinter appearance & theme
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    # Instantiate and run main window
    app = MainWindow()
    app.report_callback_exception = lambda exc, val, tb: log_crash(exc, val, tb)
    app.mainloop()


if __name__ == "__main__":
    main()
