"""
LocalPodcastLLMStudio - Headless Podcast Generation Pipeline Service
Provides a headless domain orchestrator executing end-to-end podcast generation workflows
without GUI dependencies.
"""

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass

from core.extractor import extract_text
from core.io_utils import atomic_write_file
from core.mp3_stitcher import stitch_mp3_files
from core.ollama import generate_podcast_script
from core.parser import DialogueTurn, dialogue_to_json, dialogue_to_markdown
from core.tts import synthesize_dialogue_audio


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

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url

    def generate_podcast(
        self,
        options: GenerationOptions,
        progress_callback: Callable[[float, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> GenerationResult:
        """
        Executes the 5-stage podcast generation pipeline:
        1. Source text extraction and normalization.
        2. Multi-act structured LLM dialogue generation.
        3. Atomic transcript persistence (JSON & Markdown).
        4. Neural text-to-speech voice synthesis.
        5. Binary audio frame concatenation and ID3v2 tagging.

        Returns:
            GenerationResult containing file paths, dialogue turns, and duration estimate.
        """
        # 1. Extraction
        if progress_callback:
            progress_callback(0.05, "Extracting and normalizing source content...")
        text = extract_text(
            source=options.content,
            is_raw_text=options.is_raw_text,
            is_topic=options.is_topic,
        )

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Generation cancelled by user.")

        # 2. Multi-Act LLM Generation
        def _llm_progress(msg: str) -> None:
            if progress_callback:
                progress_callback(0.35, msg)

        dialogue = generate_podcast_script(
            content=text,
            language=options.language,
            format_type=options.format_type,
            tone_style=options.tone_style,
            grounding_mode=options.grounding_mode,
            model=options.model,
            ollama_url=self.ollama_url,
            is_topic=options.is_topic,
            cancel_event=cancel_event,
            progress_callback=_llm_progress,
        )

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Generation cancelled by user.")

        # 3. Save Transcripts
        os.makedirs(options.output_dir, exist_ok=True)
        script_json_path = os.path.join(options.output_dir, "transcript.json")
        script_md_path = os.path.join(options.output_dir, "transcript.md")
        atomic_write_file(script_json_path, dialogue_to_json(dialogue))
        atomic_write_file(script_md_path, dialogue_to_markdown(dialogue, language=options.language))

        # 4. Audio Synthesis
        def _tts_progress(current: int, total: int) -> None:
            if progress_callback:
                pct = 0.50 + (0.40 * (current / max(1, total)))
                progress_callback(pct, f"Synthesizing turn {current}/{total}...")

        audio_files = synthesize_dialogue_audio(
            dialogue=dialogue,
            language=options.language,
            rate=options.speed_rate,
            progress_cb=_tts_progress,
            cancel_event=cancel_event,
        )

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Generation cancelled by user.")

        # 5. Audio Stitching
        if progress_callback:
            progress_callback(0.95, "Stitching audio frames...")
        master_mp3 = stitch_mp3_files(
            input_files_or_bytes=audio_files,
            output_file_path=os.path.join(options.output_dir, "podcast.mp3"),
        )

        if progress_callback:
            progress_callback(1.0, "Generation complete!")

        return GenerationResult(
            mp3_path=master_mp3,
            script_json_path=script_json_path,
            script_md_path=script_md_path,
            dialogue=dialogue,
            duration_estimate_sec=len(dialogue) * 4.0,
        )
