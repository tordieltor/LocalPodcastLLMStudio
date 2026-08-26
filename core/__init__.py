"""
LocalPodcastLLMStudio - Core Subsystems Package
Zero-cloud-cost, 100% local podcast generation and audio processing engines.
"""

from core.exceptions import SecurityError
from core.extractor import (
    DocumentExtractionError,
    convert_html_to_markdown,
    extract_text,
    extract_text_from_file,
    extract_text_from_pdf,
    extract_text_from_url,
    fetch_url_content,
    normalize_extracted_text,
    sanitize_html_boilerplate,
    strip_html_boilerplate,
    validate_url_target,
)
from core.logger import (
    get_log_file_path,
    get_logger,
    resolve_log_directory,
    setup_logging,
)
from core.mp3_stitcher import (
    MP3Stitcher,
    stitch_mp3_files,
    validate_safe_output_path,
)
from core.ollama import (
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    generate_podcast_script,
)
from core.parser import (
    DialogueParser,
    DialogueTurn,
    dialogue_from_json,
    dialogue_to_json,
    dialogue_to_markdown,
    normalize_speaker,
    parse_dialogue_json,
)
from core.pipeline import (
    GenerationOptions,
    GenerationResult,
    PipelineStage,
    PodcastGeneratorService,
    StageProgressCallback,
    StageStatus,
)
from core.player import (
    WindowsAudioPlayer,
    WindowsMCIPlayer,
    export_audio_file,
    format_ms,
    parse_time_str,
)
from core.prompts import (
    ACT_SPECS_MONOLOGUE_EN,
    ACT_SPECS_MONOLOGUE_NB,
    FORMAT_PRESETS,
    GROUNDING_DIRECTIVES_EN,
    GROUNDING_DIRECTIVES_NB,
    GROUNDING_MODE_ALIASES,
    GROUNDING_MODE_PRESETS,
    HOST_MODE_ALIASES,
    HOST_MODE_PRESETS,
    SYSTEM_PROMPT_MONOLOGUE_EN,
    SYSTEM_PROMPT_MONOLOGUE_NB,
    TONE_DESCRIPTIONS,
    GroundingMode,
    HostMode,
    build_act_system_prompt,
    build_act_user_prompt,
    build_system_prompt,
    build_user_prompt,
    get_act_specs,
    get_format_config,
    get_tone_description,
    normalize_grounding_mode,
    normalize_host_mode,
    normalize_language_code,
)
from core.tts import (
    VOICE_MAP,
    TTSEngine,
    format_rate_str,
    get_voice_for_speaker,
    synthesize_dialogue_audio,
    synthesize_turn,
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
    # Extractor & Security
    "SecurityError",
    "DocumentExtractionError",
    "extract_text",
    "extract_text_from_file",
    "extract_text_from_pdf",
    "extract_text_from_url",
    "fetch_url_content",
    "validate_url_target",
    "sanitize_html_boilerplate",
    "strip_html_boilerplate",
    "convert_html_to_markdown",
    "normalize_extracted_text",
    # Prompts & Grounding
    "GroundingMode",
    "GROUNDING_MODE_PRESETS",
    "GROUNDING_MODE_ALIASES",
    "GROUNDING_DIRECTIVES_NB",
    "GROUNDING_DIRECTIVES_EN",
    "normalize_grounding_mode",
    "HostMode",
    "HOST_MODE_PRESETS",
    "HOST_MODE_ALIASES",
    "normalize_host_mode",
    "SYSTEM_PROMPT_MONOLOGUE_NB",
    "SYSTEM_PROMPT_MONOLOGUE_EN",
    "ACT_SPECS_MONOLOGUE_NB",
    "ACT_SPECS_MONOLOGUE_EN",
    "FORMAT_PRESETS",
    "TONE_DESCRIPTIONS",
    "build_system_prompt",
    "build_user_prompt",
    "build_act_system_prompt",
    "build_act_user_prompt",
    "get_act_specs",
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
    "validate_safe_output_path",
    # Pipeline & Lifecycle
    "PipelineStage",
    "StageStatus",
    "StageProgressCallback",
    "GenerationOptions",
    "GenerationResult",
    "PodcastGeneratorService",
    # Player
    "WindowsAudioPlayer",
    "WindowsMCIPlayer",
    "export_audio_file",
    "format_ms",
    "parse_time_str",
    # Logging
    "setup_logging",
    "get_logger",
    "get_log_file_path",
    "resolve_log_directory",
]
