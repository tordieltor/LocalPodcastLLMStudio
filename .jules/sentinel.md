## 2026-09-23 - Raw Path Traversal Checking Before Normalization
**Vulnerability:** Path traversal (`..`) checks can be bypassed if paths are normalized via `os.path.normpath()` or `os.path.abspath()` prior to inspection, as internal `..` components get collapsed (e.g., `"folder/../file.mp3"` collapses to `"file.mp3"`).
**Learning:** Checking raw path segments (`re.split(r"[/\\]", path)`) without prior normalization ensures that all directory traversal sequences are caught regardless of where they appear in the path structure.
**Prevention:** Always perform character and path traversal sequence validation on the un-normalized input path before converting to an absolute or normalized path.
