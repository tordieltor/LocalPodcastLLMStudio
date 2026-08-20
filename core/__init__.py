"""
PodcastStudio - Core Subsystems Package
Zero-cloud-cost, 100% local podcast generation and audio processing engines.
"""

from core.parser import (
    DialogueTurn,
    DialogueParser,
    normalize_speaker,
    parse_dialogue_json,
    dialogue_to_json,
    dialogue_from_json,
    dialogue_to_markdown,
)

from core.extractor import (
    extract_text,
    extract_text_from_file,
    extract_text_from_pdf,
    normalize_extracted_text,
    DocumentExtractionError,
)

from core.prompts import (
    FORMAT_PRESETS,
    TONE_DESCRIPTIONS,
    build_system_prompt,
    build_user_prompt,
    get_format_config,
    get_tone_description,
    normalize_language_code,
)

from core.ollama import (
    OllamaClient,
    generate_podcast_script,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)

from core.tts import (
    TTSEngine,
    get_voice_for_speaker,
    synthesize_turn,
    synthesize_dialogue_audio,
    format_rate_str,
    VOICE_MAP,
)

from core.mp3_stitcher import (
    MP3Stitcher,
    stitch_mp3_files,
)

from core.player import (
    WindowsAudioPlayer,
    WindowsMCIPlayer,
    export_audio_file,
    format_ms,
    parse_time_str,
)

__all__ = [
    # Parser & Models
    "DialogueTurn",
    "DialogueParser",
    "normalize_speaker",
    "parse_dialogue_json",
    "dialogue_to_json",
    "dialogue_from_json",
    "dialogue_to_markdown",
    # Extractor
    "extract_text",
    "extract_text_from_file",
    "extract_text_from_pdf",
    "normalize_extracted_text",
    "DocumentExtractionError",
    # Prompts
    "FORMAT_PRESETS",
    "TONE_DESCRIPTIONS",
    "build_system_prompt",
    "build_user_prompt",
    "get_format_config",
    "get_tone_description",
    "normalize_language_code",
    # Ollama
    "OllamaClient",
    "generate_podcast_script",
    "OllamaConnectionError",
    "OllamaModelNotFoundError",
    # TTS
    "TTSEngine",
    "get_voice_for_speaker",
    "synthesize_turn",
    "synthesize_dialogue_audio",
    "format_rate_str",
    "VOICE_MAP",
    # MP3 Stitcher
    "MP3Stitcher",
    "stitch_mp3_files",
    # Player
    "WindowsAudioPlayer",
    "WindowsMCIPlayer",
    "export_audio_file",
    "format_ms",
    "parse_time_str",
]
