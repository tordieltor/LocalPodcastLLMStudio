"""
LocalPodcastLLMStudio - Headless Podcast Generation Pipeline Service
Provides a headless domain orchestrator executing end-to-end podcast generation workflows
across a 5-stage lifecycle state machine without GUI dependencies.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, IntEnum

from core.extractor import extract_text
from core.io_utils import atomic_write_file
from core.mp3_stitcher import stitch_mp3_files
from core.ollama import generate_podcast_script
from core.parser import DialogueTurn, dialogue_to_json, dialogue_to_markdown
from core.prompts import normalize_host_mode, normalize_language_code
from core.tts import synthesize_dialogue_audio


class PipelineStage(IntEnum):
    """
    Ordinal 5-stage lifecycle stages for the podcast generation pipeline.
    """

    URL_INGESTION = 1
    CONTENT_EXTRACTION = 2
    SCRIPT_GENERATION = 3
    TTS_SYNTHESIS = 4
    AUDIO_ASSEMBLY = 5


class StageStatus(str, Enum):
    """
    Lifecycle execution status for an individual pipeline stage.
    """

    PENDING = "pending"
    IN_ACTION = "in_action"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


StageProgressCallback = Callable[[PipelineStage, StageStatus, float, str], None]


@dataclass
class GenerationOptions:
    """Configuration options for a podcast generation run."""

    content: str
    language: str = "nb-NO"
    model: str = "llama3.1:8b"
    format_type: str = "standard"
    tone_style: str = "casual"
    speed_rate: str = "+0%"
    grounding_mode: str = "strict"
    output_dir: str = "./output"
    is_topic: bool = False
    is_raw_text: bool = False
    is_url: bool = False
    host_mode: str = "dialogue"
    solo_voice: str | None = None


@dataclass
class GenerationResult:
    """Structured output result from a completed podcast generation pipeline."""

    mp3_path: str
    script_json_path: str
    script_md_path: str
    dialogue: list[DialogueTurn]
    duration_estimate_sec: float


class PodcastGeneratorService:
    """Headless domain orchestrator for end-to-end podcast generation."""

    def __init__(self, ollama_url: str = "http://localhost:11434") -> None:
        self.ollama_url = ollama_url

    def generate_podcast(
        self,
        options: GenerationOptions,
        progress_callback: Callable[[float, str], None] | StageProgressCallback | None = None,
        stage_callback: StageProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        stream_callback: Callable[[str], None] | None = None,
        act_callback: Callable[[int, int, list[DialogueTurn]], None] | None = None,
    ) -> GenerationResult:
        """
        Executes the 5-stage podcast generation pipeline:
        1. URL_INGESTION: Protocol & SSRF validation, streaming fetch (if URL).
        2. CONTENT_EXTRACTION: Boilerplate stripping, MarkItDown conversion & normalization.
        3. SCRIPT_GENERATION: Multi-act structured LLM dialogue/monologue generation.
        4. TTS_SYNTHESIS: Neural text-to-speech voice synthesis.
        5. AUDIO_ASSEMBLY: Binary MP3 frame concatenation and ID3v2 tagging.

        Returns:
            GenerationResult containing file paths, dialogue turns, and duration estimate.
        """
        current_pct = 0.0
        current_stage = PipelineStage.URL_INGESTION

        def _notify(stage: PipelineStage, status: StageStatus, pct: float, msg: str) -> None:
            nonlocal current_pct, current_stage
            current_pct = max(0.0, min(1.0, float(pct)))
            current_stage = stage
            if stage_callback is not None:
                try:
                    stage_callback(stage, status, current_pct, msg)
                except TypeError:
                    pass
            if progress_callback is not None:
                try:
                    # Attempt 4-argument dispatch (if progress_callback is a StageProgressCallback)
                    progress_callback(stage, status, current_pct, msg)  # type: ignore[call-arg]
                except TypeError:
                    try:
                        # Fallback to 2-argument legacy callback (pct, msg)
                        progress_callback(current_pct, msg)  # type: ignore[call-arg,arg-type]
                    except Exception:
                        pass
                except Exception:
                    pass

        def _check_cancelled() -> None:
            if cancel_event and cancel_event.is_set():
                _notify(
                    current_stage,
                    StageStatus.CANCELLED,
                    current_pct,
                    "Generation cancelled by user.",
                )
                raise RuntimeError("Generation cancelled by user.")

        try:
            # ------------------------------------------------------------------
            # Stage 1: URL Ingestion & Security Validation
            # ------------------------------------------------------------------
            current_stage = PipelineStage.URL_INGESTION
            is_url_input = bool(
                options.is_url
                or str(options.content).strip().lower().startswith(("http://", "https://"))
            )

            if is_url_input:
                _notify(
                    PipelineStage.URL_INGESTION,
                    StageStatus.IN_ACTION,
                    0.02,
                    f"Validating and fetching URL: {options.content}",
                )
                _check_cancelled()

                # Run extraction while in URL_INGESTION stage so any SSRF/network failure is attributed to URL_INGESTION
                def _extractor_url_cb(msg: str) -> None:
                    _notify(PipelineStage.URL_INGESTION, StageStatus.IN_ACTION, 0.06, msg)

                text = extract_text(
                    source=options.content,
                    is_raw_text=options.is_raw_text,
                    is_topic=options.is_topic,
                    is_url=True,
                    progress_callback=_extractor_url_cb,
                )
                _check_cancelled()
                _notify(
                    PipelineStage.URL_INGESTION,
                    StageStatus.COMPLETED,
                    0.10,
                    "URL content securely validated and fetched.",
                )
                _check_cancelled()

                # Stage 2: Content Extraction & Normalization
                current_stage = PipelineStage.CONTENT_EXTRACTION
                _notify(
                    PipelineStage.CONTENT_EXTRACTION,
                    StageStatus.IN_ACTION,
                    0.12,
                    "Extracting and normalizing source content...",
                )
                _check_cancelled()
                _notify(
                    PipelineStage.CONTENT_EXTRACTION,
                    StageStatus.COMPLETED,
                    0.25,
                    f"Extracted {len(text)} characters of content.",
                )
            else:
                _notify(
                    PipelineStage.URL_INGESTION,
                    StageStatus.IN_ACTION,
                    0.01,
                    "Inspecting non-URL input source...",
                )
                _check_cancelled()
                _notify(
                    PipelineStage.URL_INGESTION,
                    StageStatus.COMPLETED,
                    0.05,
                    "Source is not a URL (skipped ingestion).",
                )
                _check_cancelled()

                # Stage 2: Content Extraction & Normalization
                current_stage = PipelineStage.CONTENT_EXTRACTION
                _notify(
                    PipelineStage.CONTENT_EXTRACTION,
                    StageStatus.IN_ACTION,
                    0.12,
                    "Extracting and normalizing source content...",
                )

                def _extractor_non_url_cb(msg: str) -> None:
                    _notify(PipelineStage.CONTENT_EXTRACTION, StageStatus.IN_ACTION, 0.18, msg)

                text = extract_text(
                    source=options.content,
                    is_raw_text=options.is_raw_text,
                    is_topic=options.is_topic,
                    is_url=False,
                    progress_callback=_extractor_non_url_cb,
                )
                _check_cancelled()
                _notify(
                    PipelineStage.CONTENT_EXTRACTION,
                    StageStatus.COMPLETED,
                    0.25,
                    f"Extracted {len(text)} characters of content.",
                )

            _check_cancelled()

            # ------------------------------------------------------------------
            # Stage 3: Multi-Act Structured LLM Generation
            # ------------------------------------------------------------------
            current_stage = PipelineStage.SCRIPT_GENERATION
            norm_host_mode = normalize_host_mode(options.host_mode)
            norm_lang = normalize_language_code(options.language)

            _notify(
                PipelineStage.SCRIPT_GENERATION,
                StageStatus.IN_ACTION,
                0.25,
                f"Generating {norm_host_mode} script via Ollama ({options.model})...",
            )

            def _llm_progress(msg: str) -> None:
                _notify(PipelineStage.SCRIPT_GENERATION, StageStatus.IN_ACTION, 0.35, msg)

            def _internal_act_cb(
                act_idx: int, total_acts: int, act_turns: list[DialogueTurn]
            ) -> None:
                pct = 0.25 + (0.33 * (act_idx / max(1, total_acts)))
                _notify(
                    PipelineStage.SCRIPT_GENERATION,
                    StageStatus.IN_ACTION,
                    pct,
                    f"Writing Act {act_idx} of {total_acts} ({len(act_turns)} turns generated)...",
                )
                if act_callback:
                    act_callback(act_idx, total_acts, act_turns)

            dialogue = generate_podcast_script(
                content=text,
                language=norm_lang,
                format_type=options.format_type,
                tone_style=options.tone_style,
                grounding_mode=options.grounding_mode,
                model=options.model,
                ollama_url=self.ollama_url,
                is_topic=options.is_topic,
                cancel_event=cancel_event,
                progress_callback=_llm_progress,
                stream_callback=stream_callback,
                act_callback=_internal_act_cb,
                host_mode=norm_host_mode,
            )

            _check_cancelled()

            os.makedirs(options.output_dir, exist_ok=True)
            script_json_path = os.path.join(options.output_dir, "transcript.json")
            script_md_path = os.path.join(options.output_dir, "transcript.md")
            atomic_write_file(script_json_path, dialogue_to_json(dialogue))
            atomic_write_file(
                script_md_path,
                dialogue_to_markdown(dialogue, language=norm_lang, host_mode=norm_host_mode),
            )

            _notify(
                PipelineStage.SCRIPT_GENERATION,
                StageStatus.COMPLETED,
                0.60,
                f"Generated full {len(dialogue)}-turn script.",
            )
            _check_cancelled()

            # ------------------------------------------------------------------
            # Stage 4: Neural Voice Synthesis
            # ------------------------------------------------------------------
            current_stage = PipelineStage.TTS_SYNTHESIS
            _notify(
                PipelineStage.TTS_SYNTHESIS,
                StageStatus.IN_ACTION,
                0.60,
                f"Synthesizing {len(dialogue)} dialogue turns via neural voice engine...",
            )

            def _tts_progress(current: int, total: int) -> None:
                pct = 0.60 + (0.30 * (current / max(1, total)))
                speaker = "Host"
                if 0 < current <= len(dialogue):
                    speaker = dialogue[current - 1].speaker
                _notify(
                    PipelineStage.TTS_SYNTHESIS,
                    StageStatus.IN_ACTION,
                    pct,
                    f"Synthesizing turn {current} of {total} ({speaker})...",
                )

            audio_files = synthesize_dialogue_audio(
                dialogue=dialogue,
                language=norm_lang,
                rate=options.speed_rate,
                progress_cb=_tts_progress,
                cancel_event=cancel_event,
                solo_voice=options.solo_voice,
            )

            _check_cancelled()
            _notify(
                PipelineStage.TTS_SYNTHESIS,
                StageStatus.COMPLETED,
                0.90,
                f"Synthesized {len(audio_files)} audio turn segments.",
            )
            _check_cancelled()

            # ------------------------------------------------------------------
            # Stage 5: Master Audio Frame Stitching & Tagging
            # ------------------------------------------------------------------
            current_stage = PipelineStage.AUDIO_ASSEMBLY
            _notify(
                PipelineStage.AUDIO_ASSEMBLY,
                StageStatus.IN_ACTION,
                0.92,
                "Stitching audio frames into master MP3...",
            )

            master_mp3 = stitch_mp3_files(
                input_files_or_bytes=audio_files,
                output_file_path=os.path.join(options.output_dir, "podcast.mp3"),
            )

            _check_cancelled()
            _notify(
                PipelineStage.AUDIO_ASSEMBLY,
                StageStatus.COMPLETED,
                1.00,
                "Master podcast generated successfully!",
            )

            return GenerationResult(
                mp3_path=master_mp3,
                script_json_path=script_json_path,
                script_md_path=script_md_path,
                dialogue=dialogue,
                duration_estimate_sec=len(dialogue) * 4.0,
            )

        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                _notify(
                    current_stage,
                    StageStatus.CANCELLED,
                    current_pct,
                    "Generation cancelled by user.",
                )
                raise RuntimeError("Generation cancelled by user.") from exc
            _notify(
                current_stage,
                StageStatus.FAILED,
                current_pct,
                f"Failed during {current_stage.name}: {str(exc)}",
            )
            raise
