"""
LocalPodcastLLMStudio - Local Ollama LLM Dialogue Engine
REST client, background service launcher, streaming model downloader,
and dialogue script generation pipeline interfacing with local Ollama.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from core.exceptions import OllamaConnectionError, OllamaModelNotFoundError
from core.parser import DialogueParser, DialogueTurn, SpeakerRole
from core.prompts import (
    build_act_system_prompt,
    build_act_user_prompt,
    build_system_prompt,
    build_user_prompt,
    get_act_specs,
    normalize_language_code,
)


def _validate_url(url: str) -> str:
    """
    Validates and normalizes Ollama host URL ensuring http/https scheme.

    Raises:
        ValueError: If scheme is not http or https, or if host is invalid.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Ollama URL must be a non-empty string.")
    clean = url.strip()
    if not clean:
        raise ValueError("Ollama URL must be a non-empty string.")

    if any(ord(c) < 32 or ord(c) == 127 for c in clean) or any(
        c in clean for c in (" ", "\t", "\r", "\n", "\x00")
    ):
        raise ValueError(
            f"Invalid Ollama URL '{url}': contains forbidden control characters or whitespace."
        )

    if "://" in clean:
        scheme = clean.split("://", 1)[0].lower()
        if scheme not in ("http", "https"):
            raise ValueError(
                f"Invalid URL scheme '{scheme}': only 'http' and 'https' are supported for Ollama service."
            )
    elif ":" in clean:
        prefix, suffix = clean.split(":", 1)
        port_candidate = suffix.split("/")[0]
        if port_candidate.isdigit():
            clean = f"http://{clean}"
        else:
            raise ValueError(
                f"Invalid URL scheme '{prefix}': only 'http' and 'https' are supported for Ollama service."
            )
    elif not clean.startswith(("http://", "https://")):
        clean = f"http://{clean}"

    clean = clean.rstrip("/")
    parsed = urlparse(clean)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(
            f"Invalid URL scheme '{parsed.scheme}': only 'http' and 'https' are supported for Ollama service."
        )
    if not parsed.netloc or not parsed.hostname:
        raise ValueError(f"Invalid Ollama URL '{url}': missing hostname or network location.")
    return clean


@dataclass
class ModelPullProgress:
    """
    Real-time progress state for Ollama model pull streaming operations.

    Attributes:
        status: Current phase description (e.g., 'pulling manifest', 'downloading sha256:...',
            'verifying sha256 digest', 'writing manifest', 'success', 'error').
        digest: Active layer SHA256 digest identifier.
        total: Total expected bytes for current layer/model (0 if unknown).
        completed: Downloaded bytes for current layer/model (0 if unknown).
        percentage: Normalized download completion ratio in range [0.0, 1.0].
        speed_bps: Current transfer speed in bytes per second (float).
        speed_str: Human-readable transfer speed (e.g., '14.2 MB/s', '512 KB/s', '120 B/s').
        progress_str: Human-readable downloaded/total progress (e.g., '1.20 GB / 4.70 GB (25.5%)').
        eta_str: Estimated time remaining (e.g., '02:45' or '01:15:30').
        is_done: True if the pull operation completed successfully.
        error: Error message string if an error occurred, otherwise None.
    """

    status: str
    digest: str = ""
    total: int = 0
    completed: int = 0
    percentage: float = 0.0
    speed_bps: float = 0.0
    speed_str: str = ""
    progress_str: str = ""
    eta_str: str = ""
    is_done: bool = False
    error: str | None = None


@dataclass
class PrerequisiteStatus:
    """
    Diagnostic status of system prerequisites for LocalPodcastLLMStudio.

    Attributes:
        ollama_binary_found: True if ollama executable was located on filesystem/PATH.
        ollama_binary_path: Absolute normalized path to ollama binary, or None.
        ollama_online: True if Ollama HTTP daemon is reachable at base_url.
        installed_models: List of installed model tags in Ollama.
        has_recommended_model: True if recommended model is present.
        recommended_model_name: Target recommended model name.
        edge_tts_online: True if Edge-TTS synthesis endpoint is reachable.
        all_ready: True if all core requirements (online, >=1 model, TTS) are met.
        remediation_hints: Actionable suggestions for missing prerequisites.
    """

    ollama_binary_found: bool
    ollama_binary_path: str | None
    ollama_online: bool
    installed_models: list[str]
    has_recommended_model: bool
    recommended_model_name: str
    edge_tts_online: bool
    all_ready: bool
    remediation_hints: list[str]


def format_speed_bps(bps: float) -> str:
    """Formats bytes-per-second into human-readable rate string."""
    if bps >= 1024 * 1024 * 1024:
        return f"{bps / (1024**3):.1f} GB/s"
    if bps >= 1024 * 1024:
        return f"{bps / (1024**2):.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.1f} KB/s"
    if bps > 0:
        return f"{bps:.0f} B/s"
    return "0 B/s" if bps == 0.0 else f"{bps:.0f} B/s"


def format_progress_bytes(completed: int, total: int) -> str:
    """Formats completed / total progress string with percentage."""
    if total <= 0:
        if completed > 0:
            if completed >= 1024 * 1024 * 1024:
                return f"{completed / (1024**3):.2f} GB downloaded"
            elif completed >= 1024 * 1024:
                return f"{completed / (1024**2):.1f} MB downloaded"
            return f"{completed / 1024:.1f} KB downloaded"
        return "0 MB"

    pct = (completed / total) * 100.0
    if total >= 1024 * 1024 * 1024:
        comp_gb = completed / (1024**3)
        tot_gb = total / (1024**3)
        return f"{comp_gb:.2f} GB / {tot_gb:.2f} GB ({pct:.1f}%)"
    comp_mb = completed / (1024 * 1024)
    tot_mb = total / (1024 * 1024)
    return f"{comp_mb:.1f} MB / {tot_mb:.1f} MB ({pct:.1f}%)"


def format_eta_seconds(seconds: float) -> str:
    """Formats estimated remaining seconds into MM:SS or HH:MM:SS."""
    if seconds < 0 or seconds == float("inf"):
        return "--:--"
    sec = int(seconds)
    if sec >= 3600:
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"


def find_ollama_binary() -> str | None:
    """
    Locates the Ollama executable binary on the local system.
    Searches system PATH, standard Windows installation directories
    (%LOCALAPPDATA%, %ProgramFiles%, %ProgramFiles(x86)%, %ProgramW6432%),
    and standard POSIX paths.

    Returns:
        Absolute normalized path to ollama executable, or None if not found.
    """
    # 1. Check system PATH
    which_binary = shutil.which("ollama") or shutil.which("ollama.exe")
    if which_binary and os.path.isfile(which_binary):
        return os.path.abspath(which_binary)

    # 2. Windows standard paths
    if sys.platform == "win32" or os.name == "nt":
        candidate_dirs: list[str] = []

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidate_dirs.append(os.path.join(local_app_data, "Programs", "Ollama"))

        prog_files = os.environ.get("ProgramFiles")
        if prog_files:
            candidate_dirs.append(os.path.join(prog_files, "Ollama"))

        prog_files_x86 = os.environ.get("ProgramFiles(x86)")
        if prog_files_x86:
            candidate_dirs.append(os.path.join(prog_files_x86, "Ollama"))

        prog_w6432 = os.environ.get("ProgramW6432")
        if prog_w6432:
            candidate_dirs.append(os.path.join(prog_w6432, "Ollama"))

        # User profile fallback
        candidate_dirs.append(os.path.expanduser(r"~\AppData\Local\Programs\Ollama"))

        for base_dir in candidate_dirs:
            if not base_dir:
                continue
            for exe_name in ("ollama.exe", "ollama app.exe", "ollama"):
                candidate_path = os.path.join(base_dir, exe_name)
                if os.path.isfile(candidate_path):
                    return os.path.abspath(candidate_path)

    # 3. Cross-platform POSIX fallback paths
    posix_candidates = [
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
        "/opt/homebrew/bin/ollama",
        os.path.expanduser("~/.local/bin/ollama"),
        os.path.expanduser("~/.ollama/bin/ollama"),
    ]
    for posix_path in posix_candidates:
        if os.path.isfile(posix_path):
            return os.path.abspath(posix_path)

    return None


def start_ollama_service(
    timeout: float = 10.0,
    base_url: str = "http://localhost:11434",
    cancel_event: threading.Event | None = None,
) -> tuple[bool, str]:
    """
    Starts the local Ollama background service via detached subprocess.
    Verifies service health by polling {base_url}/api/tags until responsive,
    an early crash is detected, cancellation is requested, or the timeout expires.

    Args:
        timeout: Maximum seconds to wait for service readiness.
        base_url: Ollama HTTP endpoint to health-check.
        cancel_event: Optional threading.Event to abort startup polling.

    Returns:
        Tuple[bool, str]: (success, status_or_error_message).
    """
    if cancel_event and cancel_event.is_set():
        return False, "Ollama service startup cancelled by user."

    clean_url = _validate_url(base_url)
    health_client = OllamaClient(base_url=clean_url)

    # 1. Preflight check: If already online, return immediately
    if health_client.check_connection(timeout=0.5):
        return True, f"Ollama service is already running at {clean_url}."

    # 2. Locate Ollama executable
    binary_path = find_ollama_binary()
    if not binary_path:
        return (
            False,
            "Ollama executable not found on this system. "
            "Please download and install Ollama from https://ollama.com.",
        )

    # 3. Configure platform-specific detached subprocess kwargs
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }

    if sys.platform == "win32":
        # 0x08000000 (CREATE_NO_WINDOW) | 0x00000008 (DETACHED_PROCESS)
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        detached_process = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        popen_kwargs["creationflags"] = create_no_window | detached_process
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen([binary_path, "serve"], **popen_kwargs)
    except OSError as e:
        return False, f"Failed to start Ollama process ({binary_path}): {e}"

    # 4. Polling loop with crash detection & cancellation support
    poll_interval = 0.25
    deadline = time.time() + max(1.0, timeout)

    while time.time() < deadline:
        if cancel_event and cancel_event.is_set():
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass
            return False, "Ollama service startup cancelled by user."

        # Detect early process crash
        exit_code = proc.poll()
        if exit_code is not None:
            # Process terminated: check if another instance was activated or exited on error
            if health_client.check_connection(timeout=0.5):
                return True, f"Ollama service is active at {clean_url}."
            return (
                False,
                f"Ollama process terminated immediately with exit code {exit_code}.",
            )

        # Health probe
        remaining = deadline - time.time()
        if health_client.check_connection(timeout=min(0.5, max(0.1, remaining))):
            return True, f"Ollama service started successfully at {clean_url}."

        sleep_time = min(poll_interval, max(0.01, deadline - time.time()))
        time.sleep(sleep_time)

    # 5. Final check after timeout loop
    if health_client.check_connection(timeout=0.5):
        return True, f"Ollama service started successfully at {clean_url}."

    return (
        False,
        f"Ollama service failed to become responsive at {clean_url} within {timeout} seconds.",
    )


def pull_model_stream(
    model: str,
    base_url: str = "http://localhost:11434",
    progress_callback: Callable[[ModelPullProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = 3600.0,
) -> bool:
    """
    Pulls a model from Ollama library with real-time streaming progress callbacks.

    Reads NDJSON stream from POST /api/pull, parses progress, and computes download speed and ETA.
    Returns True on success.

    Raises:
        ValueError: If model name is empty or base_url scheme is invalid.
        RuntimeError: If pull fails due to server error or user cancellation.
        OllamaConnectionError: If connection to Ollama fails.
        TimeoutError: If request times out.
    """
    if not model or not isinstance(model, str) or not model.strip():
        raise ValueError("Model name must be a non-empty string.")

    clean_model = model.strip()
    clean_url = _validate_url(base_url)

    if cancel_event and cancel_event.is_set():
        raise RuntimeError("Model pull cancelled by user before request dispatch.")

    url = f"{clean_url}/api/pull"
    payload = {"name": clean_model, "stream": True, "insecure": False}
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "LocalPodcastLLMStudio/1.0",
            "Accept": "application/x-ndjson, application/json",
        },
    )

    last_time: float | None = None
    last_bytes: int = 0
    last_digest: str = ""
    speed_bps: float = 0.0
    completed_successfully = False

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec: B310
            for line in response:
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("Model pull cancelled by user.")

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    # Skip malformed NDJSON stream chunks
                    continue

                # 1. Check for server error chunk
                if "error" in data and data["error"]:
                    err_msg = str(data["error"])
                    if progress_callback:
                        progress_callback(
                            ModelPullProgress(
                                status="error",
                                error=err_msg,
                                is_done=False,
                            )
                        )
                    raise RuntimeError(f"Ollama pull failed: {err_msg}")

                status = data.get("status", "")
                digest = data.get("digest", "")
                total = int(data.get("total") or 0)
                completed = int(data.get("completed") or 0)

                # Check if this is the final success chunk
                is_done = (status.lower() == "success") or bool(data.get("done", False))
                if is_done:
                    completed_successfully = True

                # Percentage calculation
                if is_done:
                    percentage = 1.0
                elif total > 0:
                    percentage = min(1.0, max(0.0, completed / total))
                else:
                    percentage = 0.0

                # Speed calculation
                now = time.monotonic()
                if digest and digest != last_digest:
                    # New layer/digest started, reset speed tracking
                    last_digest = digest
                    last_time = now
                    last_bytes = completed
                    speed_bps = 0.0
                elif last_time is not None:
                    dt = now - last_time
                    db = completed - last_bytes
                    if dt > 0 and db >= 0:
                        inst_speed = db / dt
                        if speed_bps == 0.0:
                            speed_bps = inst_speed
                        else:
                            speed_bps = 0.7 * speed_bps + 0.3 * inst_speed
                        last_time = now
                        last_bytes = completed
                else:
                    if digest:
                        last_digest = digest
                    last_time = now
                    last_bytes = completed

                # Format speed_str
                if speed_bps >= 1024 * 1024:
                    speed_str = f"{speed_bps / (1024 * 1024):.1f} MB/s"
                elif speed_bps >= 1024:
                    speed_str = f"{speed_bps / 1024:.0f} KB/s"
                elif speed_bps > 0:
                    speed_str = f"{speed_bps:.0f} B/s"
                else:
                    speed_str = ""

                # Format progress_str
                if total >= 1024 * 1024 * 1024:
                    progress_str = (
                        f"{completed / (1024**3):.2f} GB / {total / (1024**3):.2f} GB "
                        f"({percentage * 100:.1f}%)"
                    )
                elif total > 0:
                    progress_str = (
                        f"{completed / (1024**2):.1f} MB / {total / (1024**2):.1f} MB "
                        f"({percentage * 100:.1f}%)"
                    )
                elif completed > 0:
                    if completed >= 1024 * 1024 * 1024:
                        progress_str = f"{completed / (1024**3):.2f} GB downloaded"
                    elif completed >= 1024 * 1024:
                        progress_str = f"{completed / (1024**2):.1f} MB downloaded"
                    else:
                        progress_str = f"{completed / 1024:.1f} KB downloaded"
                else:
                    progress_str = status if status else ""

                # Format eta_str
                if is_done:
                    eta_str = "00:00"
                elif speed_bps > 0 and total > completed:
                    eta_sec = int((total - completed) / speed_bps)
                    if eta_sec < 3600:
                        eta_str = f"{eta_sec // 60:02d}:{eta_sec % 60:02d}"
                    else:
                        eta_str = (
                            f"{eta_sec // 3600:02d}:{(eta_sec % 3600) // 60:02d}:{eta_sec % 60:02d}"
                        )
                else:
                    eta_str = ""

                progress_obj = ModelPullProgress(
                    status=status,
                    digest=digest,
                    total=total,
                    completed=completed,
                    percentage=percentage,
                    speed_bps=speed_bps,
                    speed_str=speed_str,
                    progress_str=progress_str,
                    eta_str=eta_str,
                    is_done=is_done,
                    error=None,
                )

                if progress_callback:
                    progress_callback(progress_obj)

        return completed_successfully

    except RuntimeError:
        raise
    except TimeoutError as to_err:
        raise TimeoutError(
            f"Ollama model pull timed out after {timeout} seconds: {to_err}"
        ) from to_err
    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("error", str(http_err))
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
            msg = f"HTTP {http_err.code}: {http_err.reason}"
        raise RuntimeError(f"Ollama pull failed ({http_err.code}): {msg}") from http_err
    except urllib.error.URLError as url_err:
        if isinstance(url_err.reason, socket.timeout):
            raise TimeoutError(f"Ollama model pull timed out after {timeout} seconds.") from url_err
        raise OllamaConnectionError(
            f"Cannot connect to Ollama at {clean_url}: {url_err.reason}"
        ) from url_err


def check_edge_tts_reachability(timeout: float = 3.0) -> tuple[bool, str]:
    """
    Checks reachability to Microsoft Edge-TTS neural voice synthesis endpoint
    (speech.platform.bing.com:443) via a lightweight socket connection probe.

    Returns:
        Tuple[bool, str]: (is_reachable, detail_message)
    """
    host = "speech.platform.bing.com"
    port = 443
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"Connected to {host}:{port}"
    except TimeoutError:
        return False, f"Connection to {host}:{port} timed out after {timeout}s"
    except socket.gaierror as e:
        return False, f"DNS resolution failed for {host}: {e}"
    except (OSError, RuntimeError) as e:
        return False, f"Reachability probe failed for {host}:{port}: {e}"


def check_prerequisites(
    ollama_url: str = "http://localhost:11434",
    recommended_model: str = "llama3.1:8b",
    timeout: float = 3.0,
) -> PrerequisiteStatus:
    """
    Performs unified preflight inspection of local Ollama installation,
    daemon connectivity, installed models, and Edge-TTS synthesis endpoint.

    Returns:
        PrerequisiteStatus dataclass with diagnostic results and remediation hints.
    """
    binary_path = find_ollama_binary()
    binary_found = binary_path is not None

    clean_url = _validate_url(ollama_url)
    client = OllamaClient(base_url=clean_url)
    ollama_online = client.check_connection(timeout=timeout)

    installed_models: list[str] = []
    if ollama_online:
        try:
            installed_models = client.list_models(timeout=timeout)
        except (OllamaConnectionError, TimeoutError, OSError):
            installed_models = []

    rec_prefix = recommended_model.split(":")[0].lower()
    has_rec = any(
        recommended_model.lower() == m.lower()
        or m.lower().startswith(f"{rec_prefix}:")
        or m.lower() == rec_prefix
        for m in installed_models
    )

    edge_online, _ = check_edge_tts_reachability(timeout=timeout)
    all_ready = ollama_online and (len(installed_models) > 0) and edge_online

    remediations: list[str] = []
    if not binary_found:
        remediations.append(
            "Ollama binary not found. Download and install Ollama from https://ollama.com."
        )
    if not ollama_online:
        if binary_found:
            remediations.append(
                "Ollama service is offline. Click 'Start Ollama' or run 'ollama serve' in your terminal."
            )
        else:
            remediations.append(
                "Ollama is offline and binary was not found. Install and launch Ollama."
            )
    elif len(installed_models) == 0:
        remediations.append(
            f"No LLM models installed in Ollama. Click 'Download Model' or run 'ollama pull {recommended_model}'."
        )
    elif not has_rec:
        remediations.append(
            f"Recommended model '{recommended_model}' is not installed (installed: {', '.join(installed_models)})."
        )

    if not edge_online:
        remediations.append(
            "Edge-TTS neural voice endpoint is unreachable. Please verify internet connection and DNS settings."
        )

    return PrerequisiteStatus(
        ollama_binary_found=binary_found,
        ollama_binary_path=binary_path,
        ollama_online=ollama_online,
        installed_models=installed_models,
        has_recommended_model=has_rec,
        recommended_model_name=recommended_model,
        edge_tts_online=edge_online,
        all_ready=all_ready,
        remediation_hints=remediations,
    )


class OllamaClient:
    """
    Standard Library HTTP client for local Ollama REST API.
    Zero external HTTP dependencies (uses urllib.request).
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = _validate_url(base_url)

    def check_connection(self, timeout: float = 3.0) -> bool:
        """
        Returns True if the Ollama service is reachable and responsive.
        """
        url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "LocalPodcastLLMStudio/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec: B310
                return bool(response.status == 200)
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def list_models(self, timeout: float = 5.0) -> list[str]:
        """
        Retrieves list of installed model names (e.g. ['llama3.1:8b', 'qwen2.5:7b']).

        Raises:
            OllamaConnectionError: If connection to Ollama fails.
        """
        url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "LocalPodcastLLMStudio/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec: B310
                data = json.loads(response.read().decode("utf-8"))
                models = [
                    m["name"] for m in data.get("models", []) if isinstance(m, dict) and "name" in m
                ]
                return sorted(models)
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Please make sure Ollama is running ('ollama serve' or Windows tray app)."
            ) from e
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
            raise OllamaConnectionError(f"Error fetching Ollama models: {e}") from e

    def list_models_detailed(self, timeout: float = 5.0) -> list[dict[str, Any]]:
        """
        Retrieves rich metadata (name, size_gb, params, quant, format) for all installed models.

        Raises:
            OllamaConnectionError: If connection to Ollama fails.
        """
        url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "LocalPodcastLLMStudio/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec: B310
                if getattr(response, "status", 200) != 200:
                    raise OllamaConnectionError(f"HTTP status {response.status} from {url}")
                raw_bytes = response.read()
                raw_text = (
                    raw_bytes.decode("utf-8")
                    if isinstance(raw_bytes, (bytes, bytearray))
                    else str(raw_bytes)
                )
                data = json.loads(raw_text)
                parsed = []
                for m in data.get("models", []):
                    if not isinstance(m, dict):
                        continue
                    size_bytes = int(m.get("size") or 0)
                    details = m.get("details") or {}
                    parsed.append(
                        {
                            "name": str(m.get("name") or "unknown"),
                            "size_bytes": size_bytes,
                            "size_gb": round(size_bytes / (1024**3), 2),
                            "parameter_size": str(details.get("parameter_size") or "N/A"),
                            "quantization_level": str(details.get("quantization_level") or "N/A"),
                            "format": str(details.get("format") or "gguf"),
                            "family": str(details.get("family") or ""),
                            "modified_at": str(m.get("modified_at") or ""),
                        }
                    )
                return parsed
        except TimeoutError as e:
            raise TimeoutError(f"Connection timed out after {timeout}s") from e
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Please make sure Ollama is running ('ollama serve' or Windows tray app)."
            ) from e
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
            raise OllamaConnectionError(f"Error fetching Ollama models: {e}") from e

    def pull_model(
        self,
        model: str,
        progress_callback: Callable[[ModelPullProgress], None] | None = None,
        cancel_event: threading.Event | None = None,
        timeout: float = 3600.0,
    ) -> bool:
        """
        Pulls a model using the client's configured base_url.
        """
        return pull_model_stream(
            model=model,
            base_url=self.base_url,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
            timeout=timeout,
        )

    def check_prerequisites(
        self,
        recommended_model: str = "llama3.1:8b",
        timeout: float = 3.0,
    ) -> PrerequisiteStatus:
        """
        Checks prerequisites using this client's configured base_url.
        """
        return check_prerequisites(
            ollama_url=self.base_url,
            recommended_model=recommended_model,
            timeout=timeout,
        )

    def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        stream: bool = False,
        timeout: float = 300.0,
        temperature: float = 0.7,
        num_ctx: int = 8192,
        cancel_event: threading.Event | None = None,
        callback: Callable[[str], None] | None = None,
    ) -> str:
        """
        Generates text using Ollama /api/chat or fallback to /api/generate.
        Supports cancellation checks and streaming callbacks.

        Raises:
            OllamaConnectionError, OllamaModelNotFoundError, TimeoutError, RuntimeError.
        """
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Generation cancelled by user before request dispatch.")

        chat_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": stream or (callback is not None),
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": 4096,
            },
        }

        try:
            return self._execute_chat(chat_payload, timeout, cancel_event, callback)
        except TimeoutError as to_err:
            raise TimeoutError(
                f"Ollama generation timed out after {timeout} seconds: {to_err}"
            ) from to_err
        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                err_body = http_err.read().decode("utf-8", errors="ignore")
                if "model" in err_body.lower() or "not found" in err_body.lower():
                    raise OllamaModelNotFoundError(
                        f"Model '{model}' is not installed in Ollama. "
                        f"Please run 'ollama pull {model}' in your terminal."
                    ) from http_err
            # Fallback to /api/generate
            return self._execute_generate(
                model,
                prompt,
                system,
                timeout,
                temperature,
                num_ctx,
                cancel_event,
                callback,
            )
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, socket.timeout):
                raise TimeoutError(
                    f"Ollama request timed out after {timeout} seconds."
                ) from url_err
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Please make sure Ollama is running ('ollama serve')."
            ) from url_err

    def generate_dialogue(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        timeout: float = 300.0,
        temperature: float = 0.7,
    ) -> str:
        """Convenience method for generating dialogue with system & user prompt."""
        return self.generate(
            model=model,
            prompt=user_prompt,
            system=system_prompt,
            timeout=timeout,
            temperature=temperature,
        )

    def _stream_ndjson_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        content_key: str,
        timeout: float,
        cancel_event: threading.Event | None,
        callback: Callable[[str], None] | None,
    ) -> str:
        is_streaming = bool(payload.get("stream", False) or (callback is not None))
        payload_copy = dict(payload)
        payload_copy["stream"] = is_streaming

        url = f"{self.base_url}{endpoint}"
        req_data = json.dumps(payload_copy).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "LocalPodcastLLMStudio/1.0",
            },
        )
        collected_chunks: list[str] = []

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec: B310
                if not is_streaming:
                    data = json.loads(response.read().decode("utf-8"))
                    if content_key == "message":
                        msg_obj = data.get("message") or {}
                        return str(msg_obj.get("content", ""))
                    return str(data.get(content_key) or "")

                for line in response:
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("Generation cancelled by user during streaming.")
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue
                    try:
                        chunk = json.loads(line_str)
                        msg_obj = chunk.get("message") or {}
                        content_piece = (
                            msg_obj.get("content", "")
                            if content_key == "message"
                            else (chunk.get(content_key) or "")
                        )
                        if content_piece:
                            collected_chunks.append(content_piece)
                            if callback:
                                callback(content_piece)
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

            return "".join(collected_chunks)
        except TimeoutError as e:
            raise TimeoutError(f"Ollama generation timed out after {timeout} seconds.") from e

    def _execute_chat(
        self,
        payload: dict[str, Any],
        timeout: float,
        cancel_event: threading.Event | None,
        callback: Callable[[str], None] | None,
    ) -> str:
        return self._stream_ndjson_request(
            endpoint="/api/chat",
            payload=payload,
            content_key="message",
            timeout=timeout,
            cancel_event=cancel_event,
            callback=callback,
        )

    def _execute_generate(
        self,
        model: str,
        prompt: str,
        system: str,
        timeout: float,
        temperature: float,
        num_ctx: int,
        cancel_event: threading.Event | None,
        callback: Callable[[str], None] | None,
    ) -> str:
        payload = {
            "model": model,
            "system": system,
            "prompt": prompt,
            "stream": callback is not None,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": 4096,
            },
        }
        return self._stream_ndjson_request(
            endpoint="/api/generate",
            payload=payload,
            content_key="response",
            timeout=timeout,
            cancel_event=cancel_event,
            callback=callback,
        )


def generate_podcast_script(
    content: str,
    language: str = "nb-NO",
    format_type: str = "standard",
    tone_style: str = "casual",
    grounding_mode: str = "strict",
    model: str = "llama3.1:8b",
    ollama_url: str = "http://localhost:11434",
    is_topic: bool = False,
    timeout: float = 300.0,
    cancel_event: threading.Event | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[DialogueTurn]:
    """
    High-level dialogue generation pipeline with Multi-Act Structured Generation:
    For short summaries: Generates single-shot dialogue.
    For standard, deep dive, and extended in-depth episodes:
      Executes sequential thematic acts (chapters) passing previous dialogue context,
      guaranteeing authentic progression and reaching the target 45-60 turns.

    Returns:
        List[DialogueTurn] containing structured conversation.

    Raises:
        OllamaConnectionError, OllamaModelNotFoundError, ValueError.
    """
    lang = normalize_language_code(language)
    client = OllamaClient(base_url=ollama_url)
    act_specs = get_act_specs(format_type=format_type, language=lang)

    # 1. Single-Act Mode (Quick Summary)
    if len(act_specs) <= 1:
        if progress_callback:
            progress_callback(f"Generating episode dialogue via Ollama ({model})...")

        system_prompt = build_system_prompt(
            language=lang,
            format_type=format_type,
            tone_style=tone_style,
            grounding_mode=grounding_mode,
        )
        user_prompt = build_user_prompt(
            content=content,
            language=lang,
            grounding_mode=grounding_mode,
            is_topic=is_topic,
        )

        raw_response = client.generate(
            model=model,
            prompt=user_prompt,
            system=system_prompt,
            stream=False,
            timeout=timeout,
            cancel_event=cancel_event,
        )

        if not raw_response or not raw_response.strip():
            raise ValueError("Ollama returned an empty response.")

        return DialogueParser.parse(raw_response, default_language=lang)

    # 2. Multi-Act Sequential Generation Mode (Standard, Deep Dive, Extended In-Depth)
    full_script: list[DialogueTurn] = []
    total_acts = len(act_specs)

    for act_idx, act in enumerate(act_specs, 1):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Generation cancelled by user.")

        act_title = act.get("title", f"Act {act_idx}")
        target_turns = act.get("target_turns", 10)

        # Determine speaker alternation across act boundary
        next_speaker = SpeakerRole.HOST_1.value
        if full_script:
            next_speaker = SpeakerRole.get_alternate(full_script[-1].speaker)

        if progress_callback:
            progress_callback(
                f"Writing Act {act_idx}/{total_acts}: {act_title} "
                f"(Generating ~{target_turns} turns, current total: {len(full_script)})..."
            )

        prev_dict_turns = [t.to_dict() for t in full_script[-2:]] if full_script else None
        act_system_prompt = build_act_system_prompt(
            act=act,
            total_acts=total_acts,
            language=lang,
            tone_style=tone_style,
            grounding_mode=grounding_mode,
            next_speaker=next_speaker,
        )
        act_user_prompt = build_act_user_prompt(
            content=content,
            prev_turns=prev_dict_turns,
            language=lang,
            grounding_mode=grounding_mode,
            is_topic=is_topic,
        )

        raw_act_response = client.generate(
            model=model,
            prompt=act_user_prompt,
            system=act_system_prompt,
            stream=False,
            timeout=timeout,
            cancel_event=cancel_event,
        )

        if raw_act_response and raw_act_response.strip():
            try:
                act_turns = DialogueParser.parse(raw_act_response, default_language=lang)
                if act_turns:
                    for t in act_turns:
                        full_script.append(t)
            except ValueError:
                if not full_script and act_idx == 1:
                    # Fallback retry on Act 1 if parsing failed
                    pass

    if not full_script:
        raise ValueError("Failed to generate dialogue turns across all acts.")

    if progress_callback:
        progress_callback(f"Successfully generated full {len(full_script)}-turn dialogue script.")

    return full_script
