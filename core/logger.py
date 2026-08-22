"""
LocalPodcastLLMStudio - Unified Local Logging Subsystem
Thread-safe rotating file and console logging for GUI, CLI, TUI, and core engines.
"""

import logging
import os
import sys
import tempfile
import threading
from logging.handlers import RotatingFileHandler

_LOGGING_LOCK = threading.Lock()
_IS_INITIALIZED = False
_DEFAULT_LOG_FILENAME = "app.log"
_RESOLVED_LOG_PATH: str | None = None


def resolve_log_directory() -> str:
    """
    Resolves the primary writable directory for storing application logs.
    Priority:
    1. ./logs relative to current working directory
    2. %LOCALAPPDATA%/LocalPodcastLLMStudio/logs
    3. System temporary directory/LocalPodcastLLMStudio_logs
    """
    candidates = [
        os.path.abspath(os.path.join(os.getcwd(), "logs")),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            os.path.abspath(os.path.join(local_app_data, "LocalPodcastLLMStudio", "logs"))
        )
    candidates.append(
        os.path.abspath(os.path.join(tempfile.gettempdir(), "LocalPodcastLLMStudio_logs"))
    )

    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            # Verify write access with a dummy probe
            test_probe = os.path.join(d, ".write_probe")
            with open(test_probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_probe)
            return d
        except OSError:
            continue

    return os.path.abspath("logs")


def get_log_file_path() -> str:
    """Returns the resolved absolute path to the main application log file."""
    global _RESOLVED_LOG_PATH
    if _RESOLVED_LOG_PATH is not None:
        return _RESOLVED_LOG_PATH
    log_dir = resolve_log_directory()
    _RESOLVED_LOG_PATH = os.path.join(log_dir, _DEFAULT_LOG_FILENAME)
    return _RESOLVED_LOG_PATH


def setup_logging(
    log_level: int = logging.INFO,
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    force: bool = False,
) -> logging.Logger:
    """
    Initializes root application logging with rotating file handler and stderr handler.
    Thread-safe and idempotent (or re-initialized if force=True).
    """
    global _IS_INITIALIZED, _RESOLVED_LOG_PATH

    with _LOGGING_LOCK:
        if _IS_INITIALIZED and not force:
            return logging.getLogger("localpodcastllmstudio")

        root_logger = logging.getLogger("localpodcastllmstudio")
        root_logger.setLevel(log_level)
        root_logger.propagate = False

        if force:
            for h in list(root_logger.handlers):
                root_logger.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 1. Console / Stderr handler
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # 2. Rotating File handler
        target_path = log_file or get_log_file_path()
        _RESOLVED_LOG_PATH = target_path
        try:
            os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
            file_handler = RotatingFileHandler(
                filename=target_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except OSError as e:
            sys.stderr.write(f"[WARNING] Could not initialize file logger at {target_path}: {e}\n")

        _IS_INITIALIZED = True
        root_logger.info(
            "LocalPodcastLLMStudio logging initialized at %s (level=%s)",
            target_path,
            logging.getLevelName(log_level),
        )
        return root_logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Retrieves a child logger under the 'localpodcastllmstudio' hierarchy.
    Automatically initializes logging with default configuration if not already setup.
    """
    if not _IS_INITIALIZED:
        setup_logging()

    if not name or name == "localpodcastllmstudio":
        return logging.getLogger("localpodcastllmstudio")

    if name.startswith("localpodcastllmstudio."):
        return logging.getLogger(name)

    return logging.getLogger(f"localpodcastllmstudio.{name}")
