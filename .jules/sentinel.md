## 2026-09-08 - Shell Execution in Log File Opener
**Vulnerability:** `ui/main_window.py` used `os.system(f'xdg-open "{log_dir}"')` to open application logs on non-Windows platforms, introducing shell command injection risks if the log directory path contained shell metacharacters.
**Learning:** System utility callers often fall back to shell execution helpers (`os.system`) instead of array-based process spawning (`subprocess.Popen`).
**Prevention:** Always use array-argument `subprocess.Popen(["xdg-open", path])` without `shell=True` to execute system commands safely without shell interpretation.
