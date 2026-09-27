## 2026-09-27 - Path Traversal Protection in Output Path Validation
**Vulnerability:** Output path validation checks in `validate_safe_output_path` verified types, empty/whitespace strings, and null bytes, but lacked explicit checks for directory traversal (`..`) sequences.
**Learning:** Calling `os.path.normpath` or `os.path.abspath` before validating directory components collapses internal `..` sequences (e.g., `"folder/../file.mp3"` becomes `"file.mp3"`), obscuring path traversal attempts and bypassing validation.
**Prevention:** Always inspect raw path components by splitting on `/` and `\` prior to path normalization to explicitly detect and reject any `".."` segment.
