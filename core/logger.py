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

# Attach a silent NullHandler at import time so library imports never emit to stderr
# or touch ./logs/app.log until an application entrypoint explicitly calls setup_logging().
_ROOT_LOGGER = logging.getLogger("localpodcastllmstudio")
if not _ROOT_LOGGER.handlers:
    _ROOT_LOGGER.addHandler(logging.NullHandler())


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
    uid_suffix = f"_{os.getuid()}" if hasattr(os, "getuid") else ""
    candidates.append(
        os.path.abspath(
            os.path.join(tempfile.gettempdir(), f"LocalPodcastLLMStudio_logs{uid_suffix}")
        )
    )

    probe_name = f".write_probe_{os.getpid()}_{threading.get_ident()}"
    for d in candidates:
        test_probe = os.path.join(d, probe_name)
        try:
            # Enforce 0o700 directory permissions to prevent local log tampering / disclosure
            os.makedirs(d, mode=0o700, exist_ok=True)
            if hasattr(os, "chmod") and os.name != "nt":
                try:
                    os.chmod(d, 0o700)
                except OSError:
                    pass
            # Verify write access with a PID/thread-isolated dummy probe
            with open(test_probe, "w", encoding="utf-8") as f:
                f.write("ok")
            return d
        except OSError:
            continue
        finally:
            if os.path.exists(test_probe):
                try:
                    os.remove(test_probe)
                except OSError:
                    pass

    return os.path.abspath("logs")


def get_log_file_path() -> str:
    """Returns the resolved absolute path to the main application log file."""
    global _RESOLVED_LOG_PATH
    with _LOGGING_LOCK:
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
    enable_console: bool = True,
) -> logging.Logger:
    """
    Initializes root application logging with rotating file handler and optional stderr handler.
    Thread-safe and idempotent (or re-initialized if force=True).
    """
    global _IS_INITIALIZED, _RESOLVED_LOG_PATH

    with _LOGGING_LOCK:
        if _IS_INITIALIZED and not force:
            return logging.getLogger("localpodcastllmstudio")

        root_logger = logging.getLogger("localpodcastllmstudio")
        root_logger.setLevel(log_level)
        root_logger.propagate = False

        for h in list(root_logger.handlers):
            if force or isinstance(h, logging.NullHandler):
                root_logger.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 1. Console / Stderr handler (suppressed when enable_console=False or under --noconsole)
        if enable_console and sys.stderr is not None:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)

        # 2. Rotating File handler
        if log_file:
            target_path = log_file
        elif _RESOLVED_LOG_PATH is not None:
            target_path = _RESOLVED_LOG_PATH
        else:
            target_path = os.path.join(resolve_log_directory(), _DEFAULT_LOG_FILENAME)
        _RESOLVED_LOG_PATH = target_path
        try:
            log_dir = os.path.dirname(os.path.abspath(target_path))
            os.makedirs(log_dir, mode=0o700, exist_ok=True)
            if hasattr(os, "chmod") and os.name != "nt":
                try:
                    os.chmod(log_dir, 0o700)
                except OSError:
                    pass
            file_handler = RotatingFileHandler(
                filename=target_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            if hasattr(os, "chmod") and os.name != "nt" and os.path.exists(target_path):
                try:
                    os.chmod(target_path, 0o600)
                except OSError:
                    pass
        except OSError as e:
            if enable_console and sys.stderr is not None:
                sys.stderr.write(
                    f"[WARNING] Could not initialize file logger at {target_path}: {e}\n"
                )

        if not root_logger.handlers:
            root_logger.addHandler(logging.NullHandler())

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
    Uses a silent NullHandler until setup_logging() is explicitly called by an entrypoint.
    """
    root = logging.getLogger("localpodcastllmstudio")
    if not root.handlers:
        root.addHandler(logging.NullHandler())

    if not name or name == "localpodcastllmstudio":
        return root

    if name.startswith("localpodcastllmstudio."):
        return logging.getLogger(name)

    return logging.getLogger(f"localpodcastllmstudio.{name}")
