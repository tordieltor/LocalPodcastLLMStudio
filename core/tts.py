"""
PodcastStudio - Edge-TTS Neural Voice Synthesis Engine
Asynchronous and synchronous neural voice synthesis for Norwegian and English personas
with rate/speed control and automatic connection retry logic.
"""

import asyncio
import os
import tempfile
import threading
from typing import List, Dict, Optional, Callable, Union

from core.parser import DialogueTurn, normalize_speaker
from core.prompts import normalize_language_code

# ==============================================================================
# Voice Roster & Mapping
# ==============================================================================
VOICE_MAP: Dict[str, Dict[str, str]] = {
    "nb-NO": {
        "Host 1": "nb-NO-PernilleNeural",
        "Host 2": "nb-NO-FinnNeural",
        "Kari": "nb-NO-PernilleNeural",
        "Ola": "nb-NO-FinnNeural",
    },
    "en-US": {
        "Host 1": "en-US-JennyNeural",
        "Host 2": "en-US-GuyNeural",
        "Jenny": "en-US-JennyNeural",
        "Guy": "en-US-GuyNeural",
    }
}

DEFAULT_VOICES = {
    "nb-NO": ("nb-NO-PernilleNeural", "nb-NO-FinnNeural"),
    "en-US": ("en-US-JennyNeural", "en-US-GuyNeural"),
}


def get_voice_for_speaker(speaker: str, language: str = "nb-NO") -> str:
    """Standalone utility resolving speaker name and language to neural voice ID."""
    lang_norm = normalize_language_code(language)
    spk_norm = normalize_speaker(speaker)
    voices = VOICE_MAP.get(lang_norm, VOICE_MAP["en-US"])
    return voices.get(spk_norm, voices.get("Host 1", "en-US-JennyNeural"))


def format_rate_str(rate: Union[str, int, float]) -> str:
    """
    Normalizes rate input into Edge-TTS rate string, e.g. '+0%', '+10%', '-5%'.
    Clamps between -50% and +50% (standard UX: -10% to +15%).
    """
    if isinstance(rate, (int, float)):
        val = int(rate)
        val = max(-50, min(50, val))
        return f"+{val}%" if val >= 0 else f"{val}%"

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

    # Already ends with %
    clean_num = rate_str[:-1].strip()
    try:
        val = int(float(clean_num))
        val = max(-50, min(50, val))
        return f"+{val}%" if val >= 0 else f"{val}%"
    except ValueError:
        return "+0%"


async def synthesize_turn(
    text: str,
    voice: str,
    rate: Union[str, int, float] = "+0%",
    output_path: Optional[str] = None,
    max_retries: int = 3
) -> bytes:
    """
    Synthesizes a single dialogue line using edge-tts.Communicate.
    Returns raw MP3 bytes and optionally saves to output_path.
    
    Raises:
        RuntimeError: If synthesis fails after all retry attempts.
    """
    if not text or not text.strip():
        return b""

    try:
        import edge_tts
    except ImportError:
        raise RuntimeError(
            "edge-tts package is not installed. Please install edge-tts to synthesize audio."
        )

    rate_formatted = format_rate_str(rate)
    cleaned_text = text.strip()

    for attempt in range(1, max_retries + 1):
        try:
            communicate = edge_tts.Communicate(
                text=cleaned_text,
                voice=voice,
                rate=rate_formatted
            )
            audio_chunks = []
            async for chunk in communicate.stream():
                if isinstance(chunk, dict) and chunk.get("type") == "audio" and "data" in chunk:
                    audio_chunks.append(chunk["data"])

            audio_bytes = b"".join(audio_chunks)
            if not audio_bytes:
                raise RuntimeError("Edge-TTS returned 0 audio bytes.")

            if output_path:
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)

            return audio_bytes

        except Exception as e:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Edge-TTS synthesis failed for voice '{voice}' after {max_retries} attempts: {e}"
                ) from e
            await asyncio.sleep(0.8 * attempt)

    return b""


class TTSEngine:
    """
    Stateful TTS Engine managing voice assignments, rate parameters,
    and batch async/sync generation workflows.
    """

    def __init__(self, language: str = "nb-NO", rate: Union[str, int, float] = "+0%"):
        self.language = normalize_language_code(language)
        self.rate = format_rate_str(rate)

    def get_voice(self, speaker: str) -> str:
        """Resolves speaker name to configured neural voice ID."""
        return self.get_voice_for_speaker(speaker)

    def get_voice_for_speaker(self, speaker: str) -> str:
        """Resolves speaker name to configured neural voice ID."""
        norm_speaker = normalize_speaker(speaker)
        voices = VOICE_MAP.get(self.language, VOICE_MAP["en-US"])
        return voices.get(norm_speaker, voices.get("Host 1", "en-US-JennyNeural"))

    async def synthesize_turn_bytes(
        self,
        turn: DialogueTurn,
        max_retries: int = 3
    ) -> bytes:
        """Synthesizes a single dialogue turn to MP3 bytes."""
        voice = self.get_voice_for_speaker(turn.speaker)
        return await synthesize_turn(
            text=turn.text,
            voice=voice,
            rate=self.rate,
            max_retries=max_retries
        )

    async def synthesize_dialogue_pipeline(
        self,
        dialogue: List[DialogueTurn],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
    ) -> List[bytes]:
        """
        Asynchronously synthesizes an entire dialogue script into a list of MP3 byte buffers.
        """
        results: List[bytes] = []
        total = len(dialogue)

        for idx, turn in enumerate(dialogue, start=1):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Audio synthesis cancelled by user.")

            speaker = normalize_speaker(turn.speaker)
            voice = self.get_voice_for_speaker(speaker)

            if progress_callback:
                progress_callback(idx, total, f"Synthesizing turn {idx}/{total} ({speaker})...")

            audio_bytes = await self.synthesize_turn_bytes(turn)
            results.append(audio_bytes)

        return results

    async def synthesize_dialogue_async(
        self,
        dialogue: List[DialogueTurn],
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
    ) -> List[bytes]:
        """Alias for synthesize_dialogue_pipeline."""
        return await self.synthesize_dialogue_pipeline(dialogue, progress_cb, cancel_event)

    def run_synthesis_sync(
        self,
        dialogue: List[DialogueTurn],
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None
    ) -> List[bytes]:
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
            loop.close()


def synthesize_dialogue_audio(
    dialogue: List[DialogueTurn],
    language: str = "nb-NO",
    rate: Union[str, int, float] = "+0%",
    output_dir: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> List[str]:
    """
    Synthesizes each dialogue turn to a temporary MP3 file on disk.
    
    Args:
        dialogue: List of DialogueTurn objects.
        language: 'nb-NO' or 'en-US'.
        rate: Speaking speed (e.g. '+0%', '+10%').
        output_dir: Directory for temporary turn MP3 files.
        progress_cb: Callback function receiving (current_turn_index, total_turns).
        cancel_event: Threading event for aborting synthesis.
        
    Returns:
        List of paths to generated turn MP3 files.
        
    Raises:
        RuntimeError: If synthesis is cancelled or fails.
    """
    if not dialogue:
        return []

    target_dir = output_dir or tempfile.mkdtemp(prefix="podcaststudio_tts_")
    os.makedirs(target_dir, exist_ok=True)

    engine = TTSEngine(language=language, rate=rate)
    temp_file_paths: List[str] = []

    def handle_progress(current: int, total: int, msg: str):
        if progress_cb:
            progress_cb(current, total)

    try:
        audio_buffers = engine.run_synthesis_sync(
            dialogue=dialogue,
            progress_cb=handle_progress,
            cancel_event=cancel_event
        )

        for idx, buf in enumerate(audio_buffers, start=1):
            file_path = os.path.join(target_dir, f"turn_{idx:03d}.mp3")
            with open(file_path, "wb") as f:
                f.write(buf)
            temp_file_paths.append(file_path)

        return temp_file_paths

    except Exception:
        for p in temp_file_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        raise
