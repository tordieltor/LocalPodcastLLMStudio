## 2026-10-30 - Path Traversal Prevention in Output Path Sanitization
**Vulnerability:** Output file and directory paths passed to `atomic_write_file` or `validate_safe_output_path` could contain directory traversal sequences (`..`).
**Learning:** Checking raw unnormalized path segments (`re.split(r"[/\\]", clean_path)`) before any `os.path.normpath` resolution is necessary because `os.path.normpath` collapses internal `..` steps (e.g., `folder/../file`), neutralizing naive traversal checks performed after normalization.
**Prevention:** Always split raw path components by both POSIX (`/`) and Windows (`\`) separators and check for `".." in parts` prior to normalization.
