## 2026-10-28 - Strict Output Path Control Character Validation
**Vulnerability:** Output path validation in `validate_safe_output_path` checked only for null bytes (`\x00`), allowing strings with ASCII control characters (such as newlines `\n` or carriage returns `\r`) to pass initial validation. In addition, `PodcastGeneratorService` did not validate `options.output_dir` before pipeline execution.
**Learning:** Checking for null bytes is insufficient for path safety; ASCII control characters (`0x00`-`0x1F`, `0x7F`) must be rejected uniformly across all file and directory output parameters.
**Prevention:** Always validate all output paths and directories using `validate_safe_output_path` in `core.io_utils` at service entry points.
