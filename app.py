"""
LocalPodcastLLMStudio - Universal 100% Local AI Podcast Desktop Application
Main executable entry point initializing CustomTkinter runtime, global crash logger,
and the primary application window.
"""

import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from typing import Any

import customtkinter as ctk

from core.logger import get_log_file_path, get_logger, resolve_log_directory, setup_logging
from ui.main_window import MainWindow

APP_VERSION = "1.0.0"
logger = get_logger("bootstrap")


def _resolve_crash_log_path() -> str:
    """Resolves a writable path for crash_dump.log inside the application log directory."""
    log_dir = resolve_log_directory()
    return os.path.abspath(os.path.join(log_dir, "crash_dump.log"))


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
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    try:
        os.makedirs(os.path.dirname(log_path), mode=0o700, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 70}\n")
            f.write(f"LocalPodcastLLMStudio v{APP_VERSION} Crash Report - {timestamp_utc}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"{'=' * 70}\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
        if hasattr(os, "chmod") and os.name != "nt":
            try:
                os.chmod(log_path, 0o600)
            except OSError:
                pass
    except OSError:
        pass

    # Print to stderr only when a console stream is attached (None under PyInstaller --noconsole)
    if sys.stderr is not None:
        try:
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        except OSError:
            pass


def _run_self_test() -> int:
    """
    Headless smoke check verifying core, UI, TUI, and CLI subsystems without opening a GUI loop.
    Used by CI/CD and PyInstaller standalone executable verification.
    """
    log_dir = resolve_log_directory()
    if not os.path.isdir(log_dir):
        raise RuntimeError(f"Resolved log directory does not exist: {log_dir}")

    import cli
    import core
    import tui
    import ui.theme
    import ui.widgets
    from core.parser import DialogueParser

    sample = DialogueParser.parse('[{"speaker": "Host 1", "text": "Self-test verification turn."}]')
    if len(sample) != 1:
        raise RuntimeError("DialogueParser self-test failed to parse canonical JSON turn.")

    _ = (cli, core, tui, ui.theme, ui.widgets)
    if sys.stdout is not None:
        print(f"LocalPodcastLLMStudio {APP_VERSION} self-test OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main application bootstrap routine."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args or "-V" in args:
        if sys.stdout is not None:
            print(f"LocalPodcastLLMStudio {APP_VERSION}")
        return 0
    if "--self-test" in args:
        return _run_self_test()

    # Initialize unified local logging (suppress stderr stream if --noconsole detached it)
    setup_logging(enable_console=sys.stderr is not None)
    logger.info("Starting LocalPodcastLLMStudio desktop application...")
    logger.info("Application log file: %s", get_log_file_path())

    # Register crash hooks for main thread and background worker threads
    sys.excepthook = log_crash
    if hasattr(threading, "excepthook"):
        threading.excepthook = lambda hook_args: log_crash(
            hook_args.exc_type, hook_args.exc_value, hook_args.exc_traceback
        )

    # Initialize CustomTkinter appearance & theme
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    # Instantiate and run main window
    app = MainWindow()
    app.report_callback_exception = lambda exc, val, tb: log_crash(exc, val, tb)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
