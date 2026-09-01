"""
LocalPodcastLLMStudio - Shared I/O Utilities
Provides safe atomic file persistence with PID/thread-isolated temp files, fsync, and os.replace.
"""

import os
import threading
from typing import Any


def validate_safe_output_path(
    path: Any,
    allow_none: bool = False,
    param_name: str = "output_path",
) -> str:
    """
    Validates that a file or directory path is safe for output operations.
    Rejects non-string types, empty/whitespace strings, and strings with null bytes.

    Args:
        path: The path object to validate.
        allow_none: If True, None is permitted and returns an empty string.
        param_name: Parameter name used in formatted error messages.

    Returns:
        The sanitized, stripped path string (or empty string if allow_none=True and path is None).

    Raises:
        ValueError: If path is None (and allow_none=False), not a str instance,
                    empty or whitespace-only, or contains null bytes (\x00).
    """
    if path is None:
        if allow_none:
            return ""
        raise ValueError(f"{param_name} cannot be None; must be a valid string path.")

    if not isinstance(path, str):
        raise ValueError(
            f"{param_name} must be a str instance, got {type(path).__name__}: {path!r}"
        )

    clean_path = path.strip()
    if not clean_path:
        raise ValueError(f"{param_name} cannot be empty or whitespace-only.")

    if "\x00" in path:
        raise ValueError(f"{param_name} contains forbidden null byte (\\x00) character.")

    return clean_path


def atomic_write_file(
    file_path: str,
    data: str | bytes | bytearray | memoryview,
    encoding: str | None = "utf-8",
) -> str:
    """
    Safely and atomically writes string or binary data to disk using fsync and atomic os.replace.
    Validates output file_path for null bytes, empty/whitespace strings, and non-string types.

    Args:
        file_path: Target destination path.
        data: String or binary data buffer to write.
        encoding: Text encoding when writing string data (default 'utf-8').

    Returns:
        Absolute path to the destination file.
    """
    safe_path = validate_safe_output_path(file_path, param_name="file_path")
    abs_path = os.path.abspath(safe_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    temp_path = f"{abs_path}.tmp.{os.getpid()}_{threading.get_ident()}"
    try:
        if isinstance(data, (bytes, bytearray, memoryview)):
            with open(temp_path, "wb") as f:
                f.write(bytes(data))
                f.flush()
                os.fsync(f.fileno())
        else:
            with open(temp_path, "w", encoding=encoding) as f:
                f.write(str(data))
                f.flush()
                os.fsync(f.fileno())
        os.replace(temp_path, abs_path)
        return abs_path
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# Backward compatibility alias
_atomic_write_file = atomic_write_file
