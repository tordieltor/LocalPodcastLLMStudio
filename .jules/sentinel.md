## 2026-09-21 - Path Traversal Sequence Defense in Output Path Validation
**Vulnerability:** `validate_safe_output_path` in `core.io_utils` validated parameter types, null bytes, and empty strings, but lacked explicit rejection of path traversal (`..`) sequences and control characters.
**Learning:** Calling `os.path.normpath` or `os.path.abspath` before path validation collapses internal `..` path segments (e.g., `"folder/../file.mp3"` becomes `"file.mp3"`), hiding intent and bypassing traversal checks.
**Prevention:** Always split raw path strings by path separators (`/` and `\`) and inspect unnormalized path components for `..` sequences before applying path normalization.
