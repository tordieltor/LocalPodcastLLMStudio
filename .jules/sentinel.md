# Sentinel Security Journal

## 2026-10-25 - Path Traversal Sequence Protection in Output Path Validation
**Vulnerability:** Output file and directory paths passed to `validate_safe_output_path` checked for empty strings, non-string types, and null bytes (`\x00`), but omitted checking for directory traversal sequences (`..`). This allowed directory traversal breakout when creating output directories or writing files.
**Learning:** Checking paths for `..` must be performed on raw, unnormalized path components by splitting on both `/` and `\` separators (`re.split(r"[/\\]", clean_path)`). Performing `os.path.normpath` prior to checking for `..` would collapse traversal segments (e.g., `folder/../file.mp3` -> `file.mp3`), allowing internal path traversal components to bypass validation.
**Prevention:** Always validate unnormalized path strings against split path segments containing `..` before creating directories or persisting output files.
