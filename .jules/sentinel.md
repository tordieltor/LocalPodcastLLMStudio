## 2026-08-29 - Windows MCI Command Injection via Unsanitized Alias or File Path
**Vulnerability:** `WindowsAudioPlayer` formatted raw file paths and alias strings into Windows MCI command strings (e.g. `open "{path}" alias {alias}`), allowing MCI command injection if paths or aliases contained double quotes or control characters (`\n`, `\r`, `\x00`).
**Learning:** Native C APIs like Windows `mciSendStringW` parse command strings using whitespace and quote delimiters. Unsanitized user inputs in command string interpolation allow breaking out of quote context or injecting arbitrary MCI sub-commands.
**Prevention:** Strictly sanitize alias strings to `[a-zA-Z0-9_]` and validate/reject file paths containing double quotes or control characters before formatting MCI command strings.
