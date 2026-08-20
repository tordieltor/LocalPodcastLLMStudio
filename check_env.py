#!/usr/bin/env python3
"""
LocalPodcastLLMStudio Environment Diagnostic Tool
=================================================
Performs comprehensive preflight diagnostics on:
  1. Python runtime (>= 3.10)
  2. Virtual environment (.venv)
  3. Core dependencies (customtkinter, edge-tts, pypdf, requests)
  4. Development tools (pyinstaller)
  5. Local Ollama LLM service connectivity (http://localhost:11434/api/tags)
  6. Installed Ollama model inventory (parameter size, quantization, format)
  7. Edge-TTS neural voice synthesis network reachability

Usage:
  python check_env.py          # Formatted ANSI terminal report
  python check_env.py --json   # Machine-readable JSON output
  python check_env.py --quiet  # Silent check, exit code only (0=OK, 1=Fail)
"""

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

# Reconfigure stdout/stderr for UTF-8 on Windows consoles to prevent charmap UnicodeEncodeErrors
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        hOut = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE = -11
        out_mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(hOut, ctypes.byref(out_mode)):
            kernel32.SetConsoleMode(
                hOut, out_mode.value | 0x0004
            )  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass

# ANSI Color and Formatting Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"


def check_python_version() -> dict[str, Any]:
    """Verify that Python version is at least 3.10."""
    v = sys.version_info
    major = getattr(v, "major", v[0])
    minor = getattr(v, "minor", v[1])
    micro = getattr(v, "micro", v[2] if len(v) > 2 else 0)
    v_str = f"{major}.{minor}.{micro}"
    is_ok = (major, minor) >= (3, 10)
    return {
        "name": "Python Version",
        "ok": is_ok,
        "warn": False,
        "version": v_str,
        "detail": f"{v_str} ({'Supported' if is_ok else 'Unsupported - requires Python >= 3.10'})",
        "remediation": "Install Python 3.10 or newer from https://www.python.org/downloads/ and ensure 'Add python.exe to PATH' is checked."
        if not is_ok
        else None,
    }


def check_virtual_env() -> dict[str, Any]:
    """Detect if running inside an active virtual environment (.venv)."""
    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )
    venv_path = sys.prefix if in_venv else None
    return {
        "name": "Virtual Environment",
        "ok": True,
        "warn": not in_venv,
        "active": in_venv,
        "path": venv_path,
        "detail": f"Active ({venv_path})"
        if in_venv
        else "Running in global Python (Recommended: run inside .venv)",
        "remediation": "Create and activate virtual environment via 'setup.bat' or '.venv\\Scripts\\activate'."
        if not in_venv
        else None,
    }


def check_packages() -> dict[str, Any]:
    """Check availability of required runtime dependencies."""
    required = [
        ("customtkinter", "customtkinter", "GUI framework"),
        ("edge-tts", "edge_tts", "Voice synthesis engine"),
        ("pypdf", "pypdf", "PDF document parser"),
        ("requests", "requests", "Ollama HTTP client"),
    ]
    installed = {}
    missing = []

    for display_name, mod_name, purpose in required:
        try:
            mod = __import__(mod_name)
            version = getattr(mod, "__version__", "Installed")
            installed[display_name] = {"version": str(version), "purpose": purpose}
        except ImportError:
            missing.append(display_name)

    is_ok = len(missing) == 0
    installed_str = ", ".join(f"{k} {v['version']}" for k, v in installed.items())

    return {
        "name": "Core Runtime Dependencies",
        "ok": is_ok,
        "warn": False,
        "installed": installed,
        "missing": missing,
        "detail": f"All installed ({installed_str})" if is_ok else f"Missing: {', '.join(missing)}",
        "remediation": "Install required dependencies with: pip install -r requirements.txt"
        if not is_ok
        else None,
    }


def check_pyinstaller() -> dict[str, Any]:
    """Check if PyInstaller build tool is installed."""
    try:
        import PyInstaller

        version = getattr(PyInstaller, "__version__", "Installed")
        return {
            "name": "PyInstaller (Build Tool)",
            "ok": True,
            "warn": False,
            "installed": True,
            "version": str(version),
            "detail": f"Installed ({version})",
            "remediation": None,
        }
    except ImportError:
        return {
            "name": "PyInstaller (Build Tool)",
            "ok": True,
            "warn": True,
            "installed": False,
            "version": None,
            "detail": "Not installed (only required for building standalone .exe)",
            "remediation": "Install build tools with: pip install -r requirements-dev.txt",
        }


def _validate_ollama_url(url: str) -> str:
    """
    Validates and normalizes Ollama host URL ensuring http/https scheme.

    Raises:
        ValueError: If scheme is not http or https, or if host is invalid.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Ollama host URL must be a non-empty string.")
    clean = url.strip()
    if "://" in clean:
        scheme = clean.split("://", 1)[0].lower()
        if scheme not in ("http", "https"):
            raise ValueError(
                f"Invalid URL scheme '{scheme}'. Only 'http' and 'https' are supported."
            )
    elif not clean.startswith(("http://", "https://")):
        clean = f"http://{clean}"
    clean = clean.rstrip("/")
    parsed = urlparse(clean)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid URL scheme '{parsed.scheme}'. Only 'http' and 'https' are supported."
        )
    if not parsed.netloc or not parsed.hostname:
        raise ValueError(f"Invalid Ollama URL '{url}': missing host or network location.")
    return clean


def check_ollama_service(
    host: str = "http://localhost:11434", timeout_sec: float = 3.0
) -> dict[str, Any]:
    """
    Connect to local Ollama API at /api/tags to detect service status and installed models.
    """
    try:
        clean_host = _validate_ollama_url(host)
    except ValueError as val_err:
        return {
            "name": "Ollama LLM Service",
            "ok": False,
            "warn": False,
            "online": False,
            "url": host,
            "models_count": 0,
            "models": [],
            "detail": f"Invalid Ollama URL: {val_err}",
            "remediation": "Provide a valid http:// or https:// URL for the Ollama service.",
        }

    tags_url = f"{clean_host}/api/tags"

    try:
        req = urllib.request.Request(
            tags_url,
            headers={
                "User-Agent": "LocalPodcastLLMStudio-Diagnostic/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:  # nosec: B310
            if response.status == 200:
                raw_body = response.read().decode("utf-8")
                data = json.loads(raw_body)
                raw_models = data.get("models", [])

                parsed_models = []
                for m in raw_models:
                    name = m.get("name", "unknown")
                    size_bytes = m.get("size", 0)
                    size_gb = round(size_bytes / (1024**3), 2)
                    details = m.get("details", {})
                    param_size = details.get("parameter_size", "N/A")
                    quant = details.get("quantization_level", "N/A")
                    fmt = details.get("format", "gguf")
                    family = details.get("family", "")

                    parsed_models.append(
                        {
                            "name": name,
                            "size_bytes": size_bytes,
                            "size_gb": size_gb,
                            "parameter_size": param_size,
                            "quantization_level": quant,
                            "format": fmt,
                            "family": family,
                            "modified_at": m.get("modified_at", ""),
                        }
                    )

                has_models = len(parsed_models) > 0
                return {
                    "name": "Ollama LLM Service",
                    "ok": True,
                    "warn": not has_models,
                    "online": True,
                    "url": clean_host,
                    "models_count": len(parsed_models),
                    "models": parsed_models,
                    "detail": f"Online at {clean_host} ({len(parsed_models)} model(s) available)",
                    "remediation": "Ollama is running but has no models installed. Pull a model with: ollama pull llama3.1:8b (or ollama pull qwen2.5:7b / mistral-nemo)"
                    if not has_models
                    else None,
                }
            else:
                return {
                    "name": "Ollama LLM Service",
                    "ok": False,
                    "warn": False,
                    "online": False,
                    "url": clean_host,
                    "models_count": 0,
                    "models": [],
                    "detail": f"HTTP status {response.status} from {tags_url}",
                    "remediation": f"Verify Ollama is healthy and accessible at {clean_host}.",
                }
    except urllib.error.URLError as e:
        reason = str(e.reason)
        try:
            from core.ollama import find_ollama_binary

            bin_path = find_ollama_binary()
        except Exception:
            bin_path = None

        if bin_path:
            remediation = f"Start the Ollama desktop application or run in a terminal: ollama serve (binary found at {bin_path})"
        else:
            remediation = "Start the Ollama desktop application or run in a terminal: ollama serve"

        return {
            "name": "Ollama LLM Service",
            "ok": False,
            "warn": False,
            "online": False,
            "url": clean_host,
            "models_count": 0,
            "models": [],
            "detail": f"Offline ({reason})",
            "remediation": remediation,
        }
    except TimeoutError:
        return {
            "name": "Ollama LLM Service",
            "ok": False,
            "warn": False,
            "online": False,
            "url": clean_host,
            "models_count": 0,
            "models": [],
            "detail": f"Connection timed out after {timeout_sec}s",
            "remediation": "Ollama is taking too long to respond. Ensure the Ollama daemon is responsive.",
        }
    except Exception as e:
        return {
            "name": "Ollama LLM Service",
            "ok": False,
            "warn": False,
            "online": False,
            "url": clean_host,
            "models_count": 0,
            "models": [],
            "detail": f"Connection failed: {str(e)}",
            "remediation": f"Ensure Ollama is running and accessible at {clean_host}.",
        }


def check_edge_tts_network(timeout_sec: float = 3.0) -> dict[str, Any]:
    """Check connectivity to Microsoft Edge-TTS neural voice endpoint."""
    target_host = "speech.platform.bing.com"
    target_port = 443
    try:
        sock = socket.create_connection((target_host, target_port), timeout=timeout_sec)
        sock.close()
        return {
            "name": "Edge-TTS Voice Network",
            "ok": True,
            "warn": False,
            "reachable": True,
            "endpoint": f"{target_host}:{target_port}",
            "detail": f"Connected to {target_host}:{target_port}",
            "remediation": None,
        }
    except TimeoutError:
        return {
            "name": "Edge-TTS Voice Network",
            "ok": False,
            "warn": True,
            "reachable": False,
            "endpoint": f"{target_host}:{target_port}",
            "detail": f"Network probe timed out after {timeout_sec}s",
            "remediation": "Ensure your internet connection is active. Edge-TTS neural voices require outbound HTTPS to speech.platform.bing.com.",
        }
    except Exception as e:
        return {
            "name": "Edge-TTS Voice Network",
            "ok": False,
            "warn": True,
            "reachable": False,
            "endpoint": f"{target_host}:{target_port}",
            "detail": f"Reachability probe failed ({str(e)})",
            "remediation": "Edge-TTS neural voices require internet access. Please verify firewall and outbound DNS/HTTPS connections.",
        }


def run_all_checks(ollama_url: str = "http://localhost:11434") -> dict[str, Any]:
    """Execute all diagnostic checks and aggregate results."""
    py_check = check_python_version()
    venv_check = check_virtual_env()
    pkgs_check = check_packages()
    pyinst_check = check_pyinstaller()
    ollama_check = check_ollama_service(host=ollama_url)
    edge_check = check_edge_tts_network()

    checks = {
        "python": py_check,
        "virtual_environment": venv_check,
        "runtime_dependencies": pkgs_check,
        "pyinstaller": pyinst_check,
        "ollama_service": ollama_check,
        "edge_tts_network": edge_check,
    }

    # Critical checks determine all_passed
    critical_ok = (
        py_check["ok"]
        and pkgs_check["ok"]
        and ollama_check["online"]
        and (ollama_check["models_count"] > 0)
    )

    has_warnings = (
        venv_check["warn"] or pyinst_check["warn"] or ollama_check["warn"] or edge_check["warn"]
    )

    remediations = []
    for c in checks.values():
        rem = c.get("remediation")
        if rem and rem not in remediations:
            # Add remediation if failed or if warning
            if not c.get("ok", False) or c.get("warn", False):
                remediations.append(rem)

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "all_passed": critical_ok,
        "has_warnings": has_warnings,
        "checks": checks,
        "models": ollama_check.get("models", []),
        "remediations": remediations,
    }


def print_box(title: str) -> None:
    width = 70
    print(f"\n{BOLD}{CYAN}┌{'─' * (width - 2)}┐{RESET}")
    print(f"{BOLD}{CYAN}│{WHITE}  {title:<{width - 4}}{CYAN}│{RESET}")
    print(f"{BOLD}{CYAN}└{'─' * (width - 2)}┘{RESET}")


def print_status_line(name: str, status_badge: str, detail: str) -> None:
    print(f"  {status_badge}  {BOLD}{name:<28}{RESET} : {detail}")


def print_diagnostic_report(report: dict[str, Any]) -> int:
    """Print a visually polished ANSI terminal report."""
    print_box("LocalPodcastLLMStudio Preflight Environment Diagnostics")

    checks = report["checks"]
    for _key, c in checks.items():
        is_ok = c.get("ok", False)
        is_warn = c.get("warn", False)

        if is_ok and not is_warn:
            badge = f"{GREEN}[ OK ]{RESET}"
        elif is_warn:
            badge = f"{YELLOW}[WARN]{RESET}"
        else:
            badge = f"{RED}[FAIL]{RESET}"

        print_status_line(c["name"], badge, c.get("detail", ""))

    # Installed Models Section
    models = report.get("models", [])
    print(f"\n  {BOLD}{WHITE}Installed Ollama Models ({len(models)} found):{RESET}")
    if models:
        # Table Header
        print(
            f"    {DIM}{'Model Name':<28} {'Size':>9}   {'Params':<8} {'Format':<6} {'Quantization':<12}{RESET}"
        )
        print(f"    {DIM}{'─' * 28} {'─' * 9}   {'─' * 8} {'─' * 6} {'─' * 12}{RESET}")
        for m in models:
            m_name = m.get("name", "unknown")
            size_gb = f"{m.get('size_gb', 0.0):.2f} GB"
            param_size = m.get("parameter_size", "N/A")
            fmt = m.get("format", "gguf")
            quant = m.get("quantization_level", "N/A")
            print(
                f"    {BOLD}{CYAN}{m_name:<28}{RESET} {size_gb:>9}   {param_size:<8} {fmt:<6} {quant:<12}"
            )
    else:
        print(f"    {YELLOW}• No models found in local Ollama service.{RESET}")

    # Summary & Actionable Recommendations
    print_box("Diagnostic Summary & Remediation Guide")
    all_passed = report["all_passed"]
    remediations = report["remediations"]

    if all_passed and not report["has_warnings"]:
        print(f"  {GREEN}{BOLD}✓ ALL SYSTEMS GO!{RESET} Your environment is fully configured.")
        print(f"  Start LocalPodcastLLMStudio with: {CYAN}{BOLD}python app.py{RESET}\n")
        return 0
    elif all_passed and report["has_warnings"]:
        print(
            f"  {GREEN}{BOLD}✓ READY WITH WARNINGS:{RESET} Core requirements met, optional items flagged."
        )
        if remediations:
            print(f"\n  {YELLOW}Recommendations:{RESET}")
            for idx, rem in enumerate(remediations, 1):
                print(f"    {CYAN}{idx}.{RESET} {rem}")
        print(f"\n  You can proceed to launch: {CYAN}{BOLD}python app.py{RESET}\n")
        return 0
    else:
        print(f"  {RED}{BOLD}✗ ACTION REQUIRED:{RESET} One or more critical requirements failed.")
        print(f"\n  {WHITE}Follow these steps to resolve:{RESET}")
        for idx, rem in enumerate(remediations, 1):
            print(f"    {RED}{idx}.{RESET} {rem}")
        print()
        return 1


def main() -> int:
    ollama_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not ollama_url.startswith("http"):
        ollama_url = f"http://{ollama_url}"

    is_json = "--json" in sys.argv
    is_quiet = "--quiet" in sys.argv or "-q" in sys.argv

    report = run_all_checks(ollama_url=ollama_url)

    if is_json:
        print(json.dumps(report, indent=2))
        return 0 if report["all_passed"] else 1
    elif is_quiet:
        return 0 if report["all_passed"] else 1
    else:
        return print_diagnostic_report(report)


if __name__ == "__main__":
    sys.exit(main())
