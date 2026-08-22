"""
LocalPodcastLLMStudio - Terminal User Interface Launcher Script
Entry point for running the interactive Tokyo Night Terminal User Interface with CLI argument bootstrapping.
"""

from __future__ import annotations

import argparse
import os
import sys

from core.extractor import extract_text
from core.prompts import normalize_grounding_mode, normalize_language_code
from tui.app import TUIApplication
from tui.state import ScreenMode, SourceMode, TUIState


def build_arg_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for interactive TUI session bootstrapping."""
    parser = argparse.ArgumentParser(
        prog="tui.py",
        description="LocalPodcastLLMStudio - Interactive Tokyo Night Terminal User Interface",
    )

    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default="",
        help="Pre-load a document file (PDF, TXT, MD) into ingestion",
    )
    parser.add_argument(
        "-t",
        "--topic",
        "--prompt",
        type=str,
        default="",
        dest="topic",
        help="Pre-set a theme, topic, or prompt string (Rapid Topic-Only mode)",
    )
    parser.add_argument(
        "--text",
        type=str,
        default="",
        help="Pre-load raw text into ingestion buffer",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default="",
        help="Pre-select an Ollama LLM model (e.g. llama3.1:8b, qwen2.5:7b)",
    )
    parser.add_argument(
        "-u",
        "--url",
        type=str,
        default="http://localhost:11434",
        help="Custom Ollama host endpoint URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "-l",
        "--lang",
        "--language",
        type=str,
        default="",
        dest="language",
        help="Dialogue language ('nb-NO' for Norwegian, 'en-US' for English)",
    )
    parser.add_argument(
        "--length",
        "--format",
        type=str,
        default="",
        dest="length",
        choices=["", "quick", "standard", "deep_dive", "extended"],
        help="Episode length format preset (quick, standard, deep_dive, extended)",
    )
    parser.add_argument(
        "--tone",
        type=str,
        default="",
        choices=["", "casual", "analytical", "debate"],
        help="Conversation tone style (casual, analytical, debate)",
    )
    parser.add_argument(
        "--grounding",
        type=str,
        default="",
        choices=["", "strict", "creative", "open_topic"],
        help="Fidelity / anti-hallucination grounding mode (strict, creative, open_topic)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.0,
        help="Piper TTS speaking speed adjustment percentage (e.g. +5.0 or -5.0)",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        type=str,
        default="./output",
        help="Directory to save generated scripts and MP3 audio artifacts (default: ./output)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Disable automatic Ollama connectivity check on startup",
    )
    parser.add_argument(
        "--screen",
        type=str,
        default="dashboard",
        choices=[s.value for s in ScreenMode],
        help="Initial screen to display on launch (default: dashboard)",
    )

    return parser


def bootstrap_state(args: argparse.Namespace) -> TUIState:
    """Populates initial TUIState from parsed CLI arguments."""
    state = TUIState()

    with state.lock:
        # 1. Ollama URL
        if args.url:
            state.ollama.server_url = args.url.strip()

        # 2. Pre-selected Model
        if args.model:
            state.ollama.selected_model = args.model.strip()

        # 3. Output directory
        if args.outdir:
            state.config.output_dir = args.outdir.strip()

        # 4. Language
        if args.language:
            state.config.language = normalize_language_code(args.language)
            state.sync_voices_with_language()

        # 5. Length preset
        if args.length:
            state.config.length_preset = args.length.lower().strip()

        # 6. Tone preset
        if args.tone:
            state.config.tone_preset = args.tone.lower().strip()

        # 7. Grounding mode
        if args.grounding:
            state.config.grounding_mode = normalize_grounding_mode(args.grounding)

        # 8. Speaking speed
        if args.speed != 0.0:
            state.audio.speaking_speed = max(-10.0, min(15.0, float(args.speed)))

        # 9. Ingestion Modality
        if args.file and os.path.isfile(args.file):
            state.ingestion.source_mode = SourceMode.DOCUMENT
            state.ingestion.file_path = os.path.abspath(args.file)
            try:
                extracted = extract_text(args.file, is_raw_text=False, is_topic=False)
                state.ingestion.update_extracted(extracted)
            except Exception:  # nosec B110
                pass
        elif args.topic:
            state.ingestion.source_mode = SourceMode.TOPIC_PROMPT
            state.ingestion.topic_prompt = args.topic.strip()
            state.config.grounding_mode = "open_topic"
            try:
                extracted = extract_text(args.topic, is_raw_text=False, is_topic=True)
                state.ingestion.update_extracted(extracted)
            except Exception:  # nosec B110
                pass
        elif args.text:
            state.ingestion.source_mode = SourceMode.PASTED_TEXT
            state.ingestion.raw_text = args.text
            try:
                extracted = extract_text(args.text, is_raw_text=True, is_topic=False)
                state.ingestion.update_extracted(extracted)
            except Exception:  # nosec B110
                pass

    return state


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for interactive TUI launcher.

    Args:
        argv: Optional list of command-line arguments (uses sys.argv[1:] if None).

    Returns:
        int: Process exit code (0 for success).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    state = bootstrap_state(args)
    initial_screen = ScreenMode(args.screen)

    app = TUIApplication(
        state=state,
        auto_probe_ollama=not args.offline,
        initial_screen=initial_screen,
    )

    return app.run()


if __name__ == "__main__":
    sys.exit(main())
