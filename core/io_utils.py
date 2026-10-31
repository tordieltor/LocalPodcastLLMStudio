"""
LocalPodcastLLMStudio - Shared I/O Utilities
Provides safe atomic file persistence with PID/thread-isolated temp files, fsync, and os.replace.
"""

import os
import threading
from pathlib import Path
from typing import Any

_WINDOWS_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


def validate_safe_output_path(
    path: Any,
    allow_none: bool = False,
    param_name: str = "output_path",
    base_dir: str | os.PathLike[str] | None = None,
) -> str:
    """
    Validates that a file or directory path is safe for output operations.
    Rejects non-string types, empty/whitespace strings, ASCII control characters
    (including null bytes), Windows reserved device names, and optional base_dir escapes.

    Args:
        path: The path object to validate.
        allow_none: If True, None is permitted and returns an empty string.
        param_name: Parameter name used in formatted error messages.
        base_dir: Optional directory boundary; if provided, resolved path must reside inside it.

    Returns:
        The sanitized, stripped path string (or empty string if allow_none=True and path is None).

    Raises:
        ValueError: If path is None (and allow_none=False), not a str instance,
                    empty or whitespace-only, contains control characters/reserved device names,
                    or escapes base_dir when base_dir is specified.
    """
    if path is None:
        if allow_none:
            return ""
        raise ValueError(f"{param_name} cannot be None; must be a valid string path.")

    if not isinstance(path, str):
        raise ValueError(
            f"{param_name} must be a str instance, got {type(path).__name__}: {path!r}"
        )

    if "\x00" in path:
        raise ValueError(f"{param_name} contains forbidden null byte (\\x00) character.")

    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise ValueError(f"{param_name} contains forbidden ASCII control character.")

    clean_path = path.strip()
    if not clean_path:
        raise ValueError(f"{param_name} cannot be empty or whitespace-only.")

    # Reject Windows reserved device names on the final path component stem (e.g., CON, NUL.mp3)
    normalized_sep = clean_path.replace("\\", "/").rstrip("/")
    basename = normalized_sep.rsplit("/", 1)[-1] if normalized_sep else clean_path
    stem = basename.split(".", 1)[0].strip().upper()
    if stem in _WINDOWS_RESERVED_DEVICE_NAMES:
        raise ValueError(
            f"{param_name} uses reserved Windows device name '{stem}', which is not a valid file path."
        )

    if base_dir is not None:
        resolved_base = Path(base_dir).resolve()
        resolved_target = Path(clean_path).resolve()
        if not resolved_target.is_relative_to(resolved_base):
            raise ValueError(
                f"{param_name} '{clean_path}' resolves outside allowed directory '{resolved_base}'."
            )

    return clean_path


def atomic_write_file(
    file_path: str,
    data: str | bytes | bytearray | memoryview,
    encoding: str | None = "utf-8",
) -> str:
    """
    Safely and atomically writes string or binary data to disk using fsync and atomic os.replace.

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
