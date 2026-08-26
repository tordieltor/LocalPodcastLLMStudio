"""
LocalPodcastLLMStudio - Domain Exception Hierarchy
Provides a unified exception hierarchy rooted in StudioError with backward-compatible aliases.
"""


class StudioError(Exception):
    """Base domain exception for LocalPodcastLLMStudio."""

    pass


class DocumentIngestionError(StudioError, ValueError):
    """Raised when document extraction, parsing, or bounds checks fail."""

    pass


class SecurityError(DocumentIngestionError):
    """Raised when SSRF, unauthorized protocol, or network security constraints are violated."""

    pass


class LLMServiceError(StudioError, RuntimeError):
    """Raised when Ollama connection, model pulling, or prompt inference fails."""

    pass


class OllamaModelNotFoundError(LLMServiceError, ValueError):
    """Raised when a requested Ollama model is missing locally."""

    pass


class AudioSynthesisError(StudioError, RuntimeError):
    """Raised when Piper/Edge TTS voice synthesis fails."""

    pass


class AudioStitchingError(StudioError, ValueError):
    """Raised when binary MP3/WAV frame concatenation fails."""

    pass


# Backward compatibility aliases
DocumentExtractionError = DocumentIngestionError
OllamaConnectionError = LLMServiceError
