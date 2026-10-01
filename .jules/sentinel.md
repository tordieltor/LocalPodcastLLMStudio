## 2026-10-01 - Path Traversal Sequence Validation Before Normalization
**Vulnerability:** `validate_safe_output_path` checked string types and null bytes but lacked explicit path traversal (`..`) sequence rejection.
**Learning:** Performing path traversal validation after `os.path.normpath` or `os.path.abspath` can collapse internal traversal components (e.g. `"folder/../file.mp3"` becomes `"file.mp3"`), silently stripping `..` segments and masking path traversal attempts or bypassing security checks.
**Prevention:** Split cleaned path strings on path separators (`/` and `\`) and explicitly check for `".."` components prior to any path normalization or resolution functions.
