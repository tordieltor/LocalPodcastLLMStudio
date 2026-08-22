"""
LocalPodcastLLMStudio - Shared I/O Utilities
Provides safe atomic file persistence with PID/thread-isolated temp files, fsync, and os.replace.
"""

import os
import threading


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
    abs_path = os.path.abspath(file_path)
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
