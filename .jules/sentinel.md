## 2026-10-03 - ASCII Control Character Injection in URL & Path Validation
**Vulnerability:** Input path validation (`validate_safe_output_path`) and web page URL validation (`validate_url_target`) checked for null bytes (`\x00`) and private/loopback IP addresses, but permitted ASCII control characters (`\r`, `\n`, `\t`, C0 control codes `ord(c) < 32` or `127`).
**Learning:** Functions that sanitize or validate strings across system boundaries must evaluate the raw input prior to stripping, ensuring embedded or trailing control characters cannot bypass validation.
**Prevention:** Enforce `any(ord(c) < 32 or ord(c) == 127 for c in raw_input)` checks across all URL, file path, and API endpoint validation helpers.
