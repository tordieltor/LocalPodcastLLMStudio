## 2026-09-04 - Output Path Safety Validation Centralization
**Vulnerability:** File persistence and audio export functions (`atomic_write_file` and `export_audio_file`) lacked centralized output path validation, making file operations vulnerable to null-byte injection (`\x00`), invalid types, or empty/whitespace output paths.
**Learning:** Shared low-level I/O abstractions like `atomic_write_file` must enforce path validation at the lowest entry point rather than relying on caller-side validation.
**Prevention:** Always validate output file paths using `validate_safe_output_path` in `core.io_utils` at the start of any I/O operation.
