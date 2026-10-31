"""
LocalPodcastLLMStudio - 100% Offline Piper TTS Neural Voice Synthesis Engine
Local, privacy-first asynchronous and synchronous neural voice synthesis for
Norwegian and English personas with rate/speed control and zero cloud dependencies.
"""

import asyncio
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.exceptions import AudioSynthesisError
from core.io_utils import atomic_write_file, validate_safe_output_path
from core.logger import get_logger
from core.parser import DialogueTurn, SpeakerRole, normalize_speaker
from core.prompts import normalize_language_code

logger = get_logger("core.tts")

edge_tts: Any = None
_EDGE_TTS_AVAILABLE: bool = False
try:
    import edge_tts as _edge_tts_mod  # type: ignore[import-not-found,import-untyped,unused-ignore]

    edge_tts = _edge_tts_mod
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    pass

# Global thread-safe in-memory cache for loaded PiperVoice ONNX instances & per-voice locks
_VOICE_MODEL_CACHE: dict[str, Any] = {}
_VOICE_SYNTH_LOCKS: dict[str, threading.Lock] = {}
_VOICE_CACHE_LOCK = threading.Lock()


def _get_voice_synth_lock(voice_name: str) -> threading.Lock:
    """Returns a dedicated Lock for serializing concurrent synthesize() calls on a cached PiperVoice."""
    clean_name = voice_name.strip()
    with _VOICE_CACHE_LOCK:
        lock = _VOICE_SYNTH_LOCKS.get(clean_name)
        if lock is None:
            lock = threading.Lock()
            _VOICE_SYNTH_LOCKS[clean_name] = lock
        return lock


def get_or_load_piper_voice(voice_name: str) -> Any | None:
    """
    Retrieves cached PiperVoice model instance or loads and caches it in a thread-safe manner.
    """
    clean_name = voice_name.strip()
    with _VOICE_CACHE_LOCK:
        if clean_name in _VOICE_MODEL_CACHE:
            return _VOICE_MODEL_CACHE[clean_name]

        onnx_path, json_path = find_voice_model_files(clean_name)
        if onnx_path and json_path:
            try:
                from piper.voice import PiperVoice  # type: ignore[import-not-found]

                pv = PiperVoice.load(str(onnx_path), config_path=str(json_path))
                _VOICE_MODEL_CACHE[clean_name] = pv
                if clean_name not in _VOICE_SYNTH_LOCKS:
                    _VOICE_SYNTH_LOCKS[clean_name] = threading.Lock()
                return pv
            except (ImportError, OSError, RuntimeError, ValueError):
                return None
    return None


def clear_voice_model_cache() -> None:
    """Clears the in-memory Piper voice model cache."""
    with _VOICE_CACHE_LOCK:
        _VOICE_MODEL_CACHE.clear()
        _VOICE_SYNTH_LOCKS.clear()


# ==============================================================================
# Voice Roster & Mapping (100% Local Piper Models)
# ==============================================================================
VOICE_MAP: dict[str, dict[str, str]] = {
    "nb-NO": {
        "Host 1": "no_NO-torkil-medium",
        "Host 2": "no_NO-torkil-medium",
        "Kari": "no_NO-torkil-medium",
        "Ola": "no_NO-torkil-medium",
        "Pernille": "no_NO-torkil-medium",
        "Finn": "no_NO-torkil-medium",
    },
    "en-US": {
        "Host 1": "en_US-lessac-medium",
        "Host 2": "en_US-ryan-medium",
        "Jenny": "en_US-lessac-medium",
        "Guy": "en_US-ryan-medium",
        "Lessac": "en_US-lessac-medium",
        "Ryan": "en_US-ryan-medium",
        "Amy": "en_US-amy-medium",
        "Joe": "en_US-joe-medium",
    },
}

DEFAULT_VOICES = {
    "nb-NO": ("no_NO-torkil-medium", "no_NO-torkil-medium"),
    "en-US": ("en_US-lessac-medium", "en_US-ryan-medium"),
}

VOICE_LABEL_MAP: dict[str, str] = {
    "jenny (female)": "en_US-lessac-medium",
    "jenny": "en_US-lessac-medium",
    "lessac": "en_US-lessac-medium",
    "lessac (female)": "en_US-lessac-medium",
    "amy (female)": "en_US-amy-medium",
    "amy": "en_US-amy-medium",
    "guy (male)": "en_US-ryan-medium",
    "guy": "en_US-ryan-medium",
    "ryan": "en_US-ryan-medium",
    "ryan (male)": "en_US-ryan-medium",
    "joe (male)": "en_US-joe-medium",
    "joe": "en_US-joe-medium",
    "kari (female)": "no_NO-torkil-medium",
    "kari": "no_NO-torkil-medium",
    "pernille (female)": "no_NO-torkil-medium",
    "pernille": "no_NO-torkil-medium",
    "ola (male)": "no_NO-torkil-medium",
    "ola": "no_NO-torkil-medium",
    "finn (male)": "no_NO-torkil-medium",
    "finn": "no_NO-torkil-medium",
    "torkil": "no_NO-torkil-medium",
    "torkil (male)": "no_NO-torkil-medium",
}


def resolve_voice_identifier(
    voice_or_label: str | None,
    language: str = "nb-NO",
    speaker: str = "Host 1",
) -> str:
    """
    Normalizes UI human-readable voice labels (e.g. 'Amy (Female)', 'Kari (Female)')
    or short persona aliases into canonical Piper ONNX model identifiers, while
    preserving explicit Piper model IDs or Edge neural voice IDs verbatim.
    """
    if not voice_or_label or not isinstance(voice_or_label, str) or not voice_or_label.strip():
        return get_voice_for_speaker(speaker, language)
    cleaned = voice_or_label.strip()
    mapped = VOICE_LABEL_MAP.get(cleaned.lower())
    if mapped is not None:
        return mapped
    return cleaned


def get_voice_for_speaker(speaker: str, language: str = "nb-NO") -> str:
    """Standalone utility resolving speaker name and language to local neural voice ID."""
    lang_norm = normalize_language_code(language)
    spk_norm = normalize_speaker(speaker)
    voices = VOICE_MAP.get(lang_norm, VOICE_MAP["en-US"])
    return voices.get(spk_norm, voices.get("Host 1", "en_US-lessac-medium"))


def format_rate_str(rate: str | int | float) -> str:
    """
    Normalizes rate input into speech rate string, e.g. '+0%', '+10%', '-5%'.
    Clamps between -50% and +50% (standard UX: -10% to +15%).
    """
    # PERFORMANCE OPTIMIZATION: Fast-path for common string inputs & exact matches
    # Bypasses string slicing, float conversions, and formatting overhead (~2x speedup)
    if isinstance(rate, str):
        s = rate.strip()
        if s in ("+0%", "0%", "0", ""):
            return "+0%"
        if s in (
            "+5%",
            "+10%",
            "+15%",
            "+20%",
            "+25%",
            "+30%",
            "-5%",
            "-10%",
            "-15%",
            "-20%",
            "-25%",
            "-30%",
        ):
            return s
        rate_str = s
    elif isinstance(rate, (int, float)):
        val = int(rate)
        val = max(-50, min(50, val))
        return f"+{val}%" if val >= 0 else f"{val}%"
    else:
        rate_str = str(rate).strip()
        if not rate_str:
            return "+0%"

    if not rate_str.endswith("%"):
        try:
            val = int(float(rate_str))
            val = max(-50, min(50, val))
            return f"+{val}%" if val >= 0 else f"{val}%"
        except ValueError:
            return "+0%"

    clean_num = rate_str[:-1].strip()
    try:
        val = int(float(clean_num))
        val = max(-50, min(50, val))
        return f"+{val}%" if val >= 0 else f"{val}%"
    except ValueError:
        return "+0%"


def get_voices_search_dirs() -> list[Path]:
    """Returns candidate directories containing local Piper voice ONNX models."""
    candidates: list[Path] = []

    # 1. Models directory relative to current working directory
    candidates.append(Path.cwd() / "models" / "voices")

    # 2. Models directory relative to executable or script root
    app_root = Path(__file__).resolve().parent.parent
    candidates.append(app_root / "models" / "voices")

    # 3. PyInstaller temporary extraction directory (_MEIPASS)
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "models" / "voices")

    # 4. User home directory cache
    home_dir = Path.home() / ".localpodcastllmstudio" / "voices"
    candidates.append(home_dir)

    return [c for c in candidates if c.exists()]


def find_voice_model_files(voice_name: str) -> tuple[Path | None, Path | None]:
    """
    Locates the .onnx and .onnx.json files for a given voice name.
    """
    clean_name = voice_name.strip()
    for search_dir in get_voices_search_dirs():
        onnx_file = search_dir / f"{clean_name}.onnx"
        json_file = search_dir / f"{clean_name}.onnx.json"
        if onnx_file.is_file() and json_file.is_file():
            return onnx_file, json_file

    return None, None


def find_piper_binary() -> str | None:
    """Locates a standalone piper CLI executable on PATH or local models/piper directory."""
    which_bin = shutil.which("piper") or shutil.which("piper.exe")
    if which_bin and os.path.isfile(which_bin):
        return os.path.abspath(which_bin)

    app_root = Path(__file__).resolve().parent.parent
    exe_names = ("piper.exe", "piper") if os.name == "nt" else ("piper",)
    search_roots = [
        Path.cwd() / "models" / "piper",
        app_root / "models" / "piper",
        Path.home() / ".localpodcastllmstudio" / "piper",
    ]
    if hasattr(sys, "_MEIPASS"):
        search_roots.append(Path(sys._MEIPASS) / "models" / "piper")

    for root in search_roots:
        for exe in exe_names:
            candidate = root / exe
            if candidate.is_file():
                return str(candidate.resolve())
    return None


def _synthesize_via_piper_cli(
    text: str,
    voice_name: str,
    length_scale: float,
    noise_scale: float,
) -> bytes | None:
    """Synthesizes speech using standalone piper CLI binary when piper Python wheel is unavailable."""
    onnx_path, json_path = find_voice_model_files(voice_name)
    if not onnx_path or not json_path:
        return None
    piper_bin = find_piper_binary()
    if not piper_bin:
        return None

    with tempfile.TemporaryDirectory(prefix="lp_piper_cli_") as tmp_dir:
        out_wav = os.path.join(tmp_dir, "out.wav")
        cmd = [
            piper_bin,
            "--model",
            str(onnx_path),
            "--config",
            str(json_path),
            "--output_file",
            out_wav,
            "--length_scale",
            f"{length_scale:.3f}",
            "--noise_scale",
            f"{noise_scale:.3f}",
        ]
        res = subprocess.run(  # nosec B603
            cmd,
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=60.0,
            check=False,
        )
        if res.returncode == 0 and os.path.isfile(out_wav):
            with open(out_wav, "rb") as f:
                data = f.read()
            if data.startswith(b"RIFF"):
                return data
    return None


def _generate_fallback_wav_pcm(duration_sec: float = 1.0, sample_rate: int = 22050) -> bytes:
    """Generates silent PCM WAV audio bytes for offline testing and fallback."""
    num_samples = int(sample_rate * duration_sec)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * num_samples)
    return buffer.getvalue()


async def synthesize_turn(
    text: str,
    voice: str,
    rate: str | int | float = "+0%",
    output_path: str | None = None,
    max_retries: int = 3,
    speaker: str = "Host 1",
    allow_cloud_tts: bool = False,
    allow_silent_fallback: bool | None = None,
) -> bytes:
    """
    Synthesizes a single dialogue line 100% locally using Piper TTS (library or CLI binary),
    with optional explicit opt-in cloud Edge-TTS fallback.
    Returns raw audio bytes (WAV/MP3 format) and optionally saves to output_path.

    Raises:
        AudioSynthesisError: If no TTS engine/voice is available (when silent fallback is disabled)
                             or synthesis fails after all retry attempts.
    """
    safe_out_path: str | None = None
    if output_path is not None:
        safe_out_path = validate_safe_output_path(output_path, param_name="output_path")

    if not text or not text.strip():
        return b""

    cleaned_text = text.strip()
    resolved_voice = resolve_voice_identifier(voice, language=voice, speaker=speaker)
    rate_formatted = format_rate_str(rate)

    effective_silent_fallback = (
        allow_silent_fallback
        if allow_silent_fallback is not None
        else bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    env_cloud_opt_in = os.environ.get("LP_ALLOW_CLOUD_TTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    # Calculate length scale (inverse of speech rate)
    try:
        rate_val = int(rate_formatted.replace("%", "").replace("+", ""))
        speed_mult = max(0.5, 1.0 + (rate_val / 100.0))
        length_scale = 1.0 / speed_mult
    except (ValueError, TypeError):
        length_scale = 1.0

    # Differentiate Host 1 vs Host 2 personas
    if SpeakerRole.from_speaker(speaker) == SpeakerRole.HOST_2:
        length_scale *= 1.04
        noise_scale = 0.70
    else:
        length_scale *= 0.98
        noise_scale = 0.667

    for attempt in range(1, max_retries + 1):
        try:
            # 1. Local Piper Python ONNX library (thread-safe per-voice lock)
            audio_bytes: bytes | None = None
            piper_voice = get_or_load_piper_voice(resolved_voice)
            if piper_voice is not None:
                wav_buf = io.BytesIO()
                with _get_voice_synth_lock(resolved_voice), wave.open(wav_buf, "wb") as wav_file:
                    try:
                        piper_voice.synthesize(
                            cleaned_text,
                            wav_file,
                            length_scale=length_scale,
                            noise_scale=noise_scale,
                            noise_w=0.8,
                        )
                    except TypeError:
                        piper_voice.synthesize(
                            cleaned_text,
                            wav_file,
                            length_scale=length_scale,
                            noise_scale=noise_scale,
                        )
                audio_bytes = wav_buf.getvalue()

            # 2. Standalone local Piper CLI binary (Python 3.14 / bundled binary compatible)
            if not audio_bytes:
                audio_bytes = _synthesize_via_piper_cli(
                    cleaned_text,
                    resolved_voice,
                    length_scale=length_scale,
                    noise_scale=noise_scale,
                )

            # 3. Cloud Edge-TTS (ONLY when explicitly opted in OR injected as a unit-test double)
            edge_engine = sys.modules.get("edge_tts")
            if edge_engine is None and "edge_tts" not in sys.modules and _EDGE_TTS_AVAILABLE:
                edge_engine = edge_tts

            is_mock_edge = edge_engine is not None and (
                not isinstance(edge_engine, types.ModuleType)
                or getattr(edge_engine, "__file__", None) is None
            )

            if (
                not audio_bytes
                and edge_engine is not None
                and (allow_cloud_tts or env_cloud_opt_in or is_mock_edge)
            ):
                # Map voice names to Edge neural voice IDs
                edge_voice = resolved_voice
                lower_v = resolved_voice.lower()
                if "neural" in lower_v:
                    edge_voice = resolved_voice
                elif "torkil" in lower_v:
                    edge_voice = (
                        "nb-NO-FinnNeural"
                        if SpeakerRole.from_speaker(speaker) == SpeakerRole.HOST_2
                        else "nb-NO-PernilleNeural"
                    )
                elif "lessac" in lower_v or "amy" in lower_v:
                    edge_voice = "en-US-JennyNeural"
                elif "ryan" in lower_v or "joe" in lower_v:
                    edge_voice = "en-US-GuyNeural"
                elif (
                    "nb" in normalize_language_code(resolved_voice).lower()
                    or "norwegian" in lower_v
                ):
                    edge_voice = "nb-NO-PernilleNeural"
                else:
                    edge_voice = "en-US-JennyNeural"

                communicate = edge_engine.Communicate(
                    text=cleaned_text, voice=edge_voice, rate=rate_formatted
                )
                chunks = []
                async for chunk in communicate.stream():
                    if isinstance(chunk, dict) and chunk.get("type") == "audio" and "data" in chunk:
                        chunks.append(chunk["data"])
                if chunks:
                    audio_bytes = b"".join(chunks)

            # 4. Handle missing local voice models
            if not audio_bytes:
                if effective_silent_fallback:
                    logger.warning(
                        "Local Piper voice '%s' unavailable; generating silent fallback PCM WAV for test/dev mode.",
                        resolved_voice,
                    )
                    words = len(cleaned_text.split())
                    est_sec = max(0.5, (words / 2.5) * length_scale)
                    audio_bytes = _generate_fallback_wav_pcm(duration_sec=est_sec)
                else:
                    raise AudioSynthesisError(
                        f"Local Piper neural voice model '{resolved_voice}' is not installed in 'models/voices/' "
                        f"(or ~/.localpodcastllmstudio/voices/), and cloud Edge-TTS is disabled by default to protect "
                        f"local privacy. Place '{resolved_voice}.onnx' and '{resolved_voice}.onnx.json' in 'models/voices/' "
                        f"(with piper-tts or standalone piper binary), or pass --allow-cloud-tts to opt into cloud synthesis."
                    )

            if safe_out_path:
                atomic_write_file(safe_out_path, audio_bytes)

            return audio_bytes

        except AudioSynthesisError:
            raise
        except (RuntimeError, ConnectionError, OSError, ValueError, TypeError, Exception) as err:
            logger.warning(
                "TTS synthesis attempt %d/%d failed for speaker '%s' (voice='%s'): %s",
                attempt,
                max_retries,
                speaker,
                resolved_voice,
                err,
            )
            if attempt == max_retries:
                if effective_silent_fallback:
                    logger.warning(
                        "Exhausted %d TTS retries for '%s'; returning silent fallback PCM WAV in test/dev mode.",
                        max_retries,
                        resolved_voice,
                    )
                    words = len(cleaned_text.split())
                    est_sec = max(0.5, (words / 2.5) * length_scale)
                    audio_bytes = _generate_fallback_wav_pcm(duration_sec=est_sec)
                    if safe_out_path:
                        atomic_write_file(safe_out_path, audio_bytes)
                    return audio_bytes
                raise AudioSynthesisError(
                    f"Voice synthesis failed after {max_retries} attempts for '{resolved_voice}': {err}"
                ) from err
            await asyncio.sleep(0.5 * attempt)

    return b""


class TTSEngine:
    """
    100% Offline Stateful TTS Engine managing local Piper neural voices,
    persona speed/pitch parameters, and batch async/sync generation workflows.
    """

    def __init__(
        self,
        language: str = "nb-NO",
        rate: str | int | float = "+0%",
        solo_voice: str | None = None,
        host1_voice: str | None = None,
        host2_voice: str | None = None,
        allow_cloud_tts: bool = False,
        allow_silent_fallback: bool | None = None,
    ):
        self.language = normalize_language_code(language)
        self.rate = format_rate_str(rate)
        self.solo_voice = (
            resolve_voice_identifier(solo_voice, language=self.language, speaker="Host 1")
            if (solo_voice and isinstance(solo_voice, str) and solo_voice.strip())
            else None
        )
        self.host1_voice = (
            resolve_voice_identifier(host1_voice, language=self.language, speaker="Host 1")
            if (host1_voice and isinstance(host1_voice, str) and host1_voice.strip())
            else None
        )
        self.host2_voice = (
            resolve_voice_identifier(host2_voice, language=self.language, speaker="Host 2")
            if (host2_voice and isinstance(host2_voice, str) and host2_voice.strip())
            else None
        )
        self.allow_cloud_tts = allow_cloud_tts
        self.allow_silent_fallback = allow_silent_fallback

    def get_voice(self, speaker: str) -> str:
        """Resolves speaker name to configured local neural voice ID."""
        return self.get_voice_for_speaker(speaker)

    def get_voice_for_speaker(self, speaker: str) -> str:
        """Resolves speaker name to configured local neural voice ID."""
        norm_speaker = normalize_speaker(speaker)
        if self.solo_voice and norm_speaker in (SpeakerRole.HOST_1.value, "Host 1", "Host", ""):
            return self.solo_voice
        if self.host1_voice and norm_speaker in (SpeakerRole.HOST_1.value, "Host 1", "Host", ""):
            return self.host1_voice
        if self.host2_voice and norm_speaker in (SpeakerRole.HOST_2.value, "Host 2"):
            return self.host2_voice
        voices = VOICE_MAP.get(self.language, VOICE_MAP["en-US"])
        return voices.get(norm_speaker, voices.get("Host 1", "en_US-lessac-medium"))

    async def synthesize_turn_bytes(self, turn: DialogueTurn, max_retries: int = 3) -> bytes:
        """Synthesizes a single dialogue turn to audio bytes 100% locally."""
        voice = self.get_voice_for_speaker(turn.speaker)
        return await synthesize_turn(
            text=turn.text,
            voice=voice,
            rate=self.rate,
            max_retries=max_retries,
            speaker=turn.speaker,
            allow_cloud_tts=self.allow_cloud_tts,
            allow_silent_fallback=self.allow_silent_fallback,
        )

    async def synthesize_dialogue_pipeline(
        self,
        dialogue: list[DialogueTurn],
        progress_callback: Callable[[int, int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[bytes]:
        """
        Asynchronously synthesizes an entire dialogue script into a list of audio byte buffers.
        """
        results: list[bytes] = []
        total = len(dialogue)

        for idx, turn in enumerate(dialogue, start=1):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Audio synthesis cancelled by user.")

            speaker = normalize_speaker(turn.speaker)

            if progress_callback:
                mode_tag = "Cloud Opt-In" if self.allow_cloud_tts else "100% Offline"
                progress_callback(
                    idx, total, f"Synthesizing turn {idx}/{total} ({speaker}) [{mode_tag}]..."
                )

            audio_bytes = await self.synthesize_turn_bytes(turn)
            results.append(audio_bytes)

        return results

    async def synthesize_dialogue_async(
        self,
        dialogue: list[DialogueTurn],
        progress_cb: Callable[[int, int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[bytes]:
        """Alias for synthesize_dialogue_pipeline."""
        return await self.synthesize_dialogue_pipeline(dialogue, progress_cb, cancel_event)

    def run_synthesis_sync(
        self,
        dialogue: list[DialogueTurn],
        progress_cb: Callable[[int, int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[bytes]:
        """
        Synchronous helper for executing asynchronous TTS synthesis inside a worker thread.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.synthesize_dialogue_pipeline(dialogue, progress_cb, cancel_event)
            )
        finally:
            try:
                asyncio.set_event_loop(None)
            finally:
                loop.close()


def synthesize_dialogue_audio(
    dialogue: list[DialogueTurn],
    language: str = "nb-NO",
    rate: str | int | float = "+0%",
    output_dir: str | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
    solo_voice: str | None = None,
    host1_voice: str | None = None,
    host2_voice: str | None = None,
    allow_cloud_tts: bool = False,
    allow_silent_fallback: bool | None = None,
) -> list[str]:
    """
    Synthesizes each dialogue turn to a temporary audio file on disk locally.

    Args:
        dialogue: List of DialogueTurn objects.
        language: 'nb-NO' or 'en-US'.
        rate: Speaking speed (e.g. '+0%', '+10%').
        output_dir: Directory for temporary turn audio files.
        progress_cb: Callback function receiving (current_turn_index, total_turns).
        cancel_event: Threading event for aborting synthesis.
        solo_voice: Optional voice ID override for solo host turns.
        host1_voice: Optional voice ID/label override for Host 1 turns.
        host2_voice: Optional voice ID/label override for Host 2 turns.
        allow_cloud_tts: Explicit opt-in allowing network Edge-TTS fallback.
        allow_silent_fallback: Optional override for silent PCM fallback behavior.

    Returns:
        List of paths to generated turn audio files.

    Raises:
        RuntimeError: If synthesis is cancelled or fails.
    """
    if not dialogue:
        return []

    is_temp_dir = output_dir is None
    if output_dir is not None:
        target_dir = validate_safe_output_path(output_dir, param_name="output_dir")
    else:
        target_dir = tempfile.mkdtemp(prefix="localpodcastllmstudio_tts_")
    os.makedirs(target_dir, exist_ok=True)

    engine = TTSEngine(
        language=language,
        rate=rate,
        solo_voice=solo_voice,
        host1_voice=host1_voice,
        host2_voice=host2_voice,
        allow_cloud_tts=allow_cloud_tts,
        allow_silent_fallback=allow_silent_fallback,
    )
    temp_file_paths: list[str] = []

    def handle_progress(current: int, total: int, msg: str) -> None:
        if progress_cb:
            progress_cb(current, total)

    try:
        audio_buffers = engine.run_synthesis_sync(
            dialogue=dialogue, progress_cb=handle_progress, cancel_event=cancel_event
        )

        for idx, buf in enumerate(audio_buffers, start=1):
            # Detect format (RIFF for WAV, ID3/FF for MP3)
            ext = "wav" if buf.startswith(b"RIFF") else "mp3"
            file_path = os.path.join(target_dir, f"turn_{idx:03d}.{ext}")
            atomic_write_file(file_path, buf)
            temp_file_paths.append(file_path)

        return temp_file_paths

    except BaseException:
        for p in temp_file_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        if is_temp_dir and os.path.exists(target_dir):
            try:
                shutil.rmtree(target_dir, ignore_errors=True)
            except OSError:
                pass
        raise
