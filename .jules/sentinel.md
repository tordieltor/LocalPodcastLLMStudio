## 2026-09-24 - Output Path Control Character Validation

**Vulnerability:** `validate_safe_output_path` only checked for null bytes (`\x00`), allowing output path parameters containing control characters like newlines (`\n`), carriage returns (`\r`), tabs (`\t`), and non-printable ASCII characters (`ord(c) < 32` or `ord(c) == 127`).
**Learning:** Checking for null bytes in path inputs is insufficient for robust path sanitization. Unsanitized control characters in path arguments can lead to CRLF injection in logs or file system errors when passed to OS calls.
**Prevention:** Always validate path strings using `any(ord(c) < 32 or ord(c) == 127 for c in path)` to reject all control characters and non-printable bytes alongside null byte checks.
