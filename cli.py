"""
LocalPodcastLLMStudio - Comprehensive Scriptable CLI & Pipeline Engine
Provides headless unattended podcast creation, rapid topic-only generation, fine-grained
configuration flags, modular subcommands (extract, generate-script, synthesize-audio, stitch, pipeline),
pipe chaining, JSON output, stdout/stderr separation, and robust POSIX/Windows exit codes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from core.exceptions import (
    DocumentExtractionError,
    OllamaConnectionError,
    StudioError,
)
from core.extractor import extract_text
from core.io_utils import atomic_write_file
from core.mp3_stitcher import stitch_mp3_files
from core.ollama import OllamaClient, _validate_url, generate_podcast_script
from core.parser import DialogueParser, dialogue_to_json
from core.pipeline import GenerationOptions, GenerationResult, PodcastGeneratorService
from core.prompts import (
    normalize_grounding_mode,
    normalize_language_code,
)
from core.tts import synthesize_dialogue_audio

# ==============================================================================
# Helper Utilities (Stdout / Stderr Separation & Logging)
# ==============================================================================


class CLILogger:
    """Helper logger ensuring diagnostics go to stderr, preserving stdout for data/JSON."""

    def __init__(self, quiet: bool = False, json_mode: bool = False) -> None:
        self.quiet: bool = quiet
        self.json_mode: bool = json_mode

    def info(self, msg: str) -> None:
        if not self.quiet and not self.json_mode:
            print(f"[INFO] {msg}", file=sys.stderr)

    def progress(self, pct: float, msg: str) -> None:
        if not self.quiet and not self.json_mode:
            pct_str = f"{int(pct * 100):3d}%"
            print(f"[{pct_str}] {msg}", file=sys.stderr)

    def warn(self, msg: str) -> None:
        if not self.quiet:
            print(f"[WARN] {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f"[ERROR] {msg}", file=sys.stderr)


def _read_stdin_or_file(path_or_stdin: str) -> str:
    """Reads full content from a file path or stdin if '-'."""
    if path_or_stdin == "-":
        return sys.stdin.read()
    if not os.path.exists(path_or_stdin):
        raise FileNotFoundError(f"Input file not found: {path_or_stdin}")
    with open(path_or_stdin, encoding="utf-8", errors="replace") as f:
        return f.read()


# ==============================================================================
# Subcommand Execution Functions
# ==============================================================================


def run_extract(args: argparse.Namespace, logger: CLILogger) -> int:
    """
    Subcommand 'extract': Extracts and normalizes text from a document or topic string.
    """
    source_content = ""
    is_raw = False
    is_topic = False

    if args.file:
        source_content = args.file
    elif args.topic:
        source_content = args.topic
        is_topic = True
    elif args.text:
        if args.text == "-":
            source_content = sys.stdin.read()
        else:
            source_content = args.text
        is_raw = True
    else:
        logger.error("No input source provided. Specify -f/--file, -t/--topic, or --text.")
        return 2

    if args.dry_run:
        logger.info("[Dry Run] Extraction validation passed.")
        if args.json:
            print(json.dumps({"status": "valid", "command": "extract", "dry_run": True}, indent=2))
        return 0

    try:
        logger.info("Extracting text content...")
        text = extract_text(
            source=source_content,
            is_raw_text=is_raw,
            is_topic=is_topic,
        )

        char_count = len(text)
        word_count = len(text.split()) if text else 0

        if args.output:
            atomic_write_file(args.output, text)
            logger.info(f"Wrote extracted text to: {args.output}")

        if args.json:
            res = {
                "success": True,
                "char_count": char_count,
                "word_count": word_count,
                "output_file": args.output or None,
                "text": text if not args.output else None,
            }
            print(json.dumps(res, indent=2))
        elif not args.output:
            # Output directly to stdout for shell pipeline chaining
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")

        return 0

    except (DocumentExtractionError, StudioError, ValueError, OSError) as exc:
        logger.error(str(exc))
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 1


def run_generate_script(args: argparse.Namespace, logger: CLILogger) -> int:
    """
    Subcommand 'generate-script': Executes multi-act LLM dialogue generation via Ollama.
    """
    source_content = ""
    is_topic = False

    if args.topic:
        source_content = args.topic
        is_topic = True
    elif args.file:
        source_content = args.file
    elif args.input:
        source_content = _read_stdin_or_file(args.input)
    elif args.text:
        source_content = sys.stdin.read() if args.text == "-" else args.text
    else:
        logger.error(
            "No input content provided. Specify --topic, -f/--file, -i/--input, or --text."
        )
        return 2

    lang = normalize_language_code(args.language)
    grounding = (
        normalize_grounding_mode(args.grounding)
        if args.grounding
        else ("open_topic" if is_topic else "strict")
    )

    if args.dry_run:
        clean_url = _validate_url(args.url)
        client = OllamaClient(base_url=clean_url)
        online = client.check_connection(timeout=3.0)
        logger.info(f"[Dry Run] Script generation options valid. Ollama online: {online}")
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "command": "generate-script",
                        "ollama_online": online,
                        "model": args.model,
                        "dry_run": True,
                    },
                    indent=2,
                )
            )
        return 0

    try:
        logger.info(f"Extracting source content (is_topic={is_topic})...")
        extracted_text = extract_text(
            source=source_content,
            is_raw_text=not is_topic and not (args.file and os.path.isfile(source_content)),
            is_topic=is_topic,
        )

        logger.info(f"Generating dialogue script with Ollama model '{args.model}'...")

        def _prog(msg: str) -> None:
            logger.info(msg)

        dialogue = generate_podcast_script(
            content=extracted_text,
            language=lang,
            format_type=args.length,
            tone_style=args.tone,
            grounding_mode=grounding,
            model=args.model,
            ollama_url=args.url,
            is_topic=is_topic,
            progress_callback=_prog,
        )

        if not dialogue:
            raise ValueError("Ollama generation returned 0 dialogue turns.")

        json_script = dialogue_to_json(dialogue)

        if args.output:
            atomic_write_file(args.output, json_script)
            logger.info(f"Saved dialogue script JSON to: {args.output}")

        if args.json or not args.output:
            # Print JSON script to stdout for shell pipeline chaining
            sys.stdout.write(json_script)
            if not json_script.endswith("\n"):
                sys.stdout.write("\n")

        return 0

    except (OllamaConnectionError, StudioError, ValueError, OSError) as exc:
        logger.error(str(exc))
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 1


def run_synthesize_audio(args: argparse.Namespace, logger: CLILogger) -> int:
    """
    Subcommand 'synthesize-audio': Synthesizes dialogue turns from a JSON script into audio.
    """
    if not args.input:
        logger.error("No input JSON script provided. Specify -i/--input <path> or '-' for stdin.")
        return 2

    raw_json = _read_stdin_or_file(args.input)
    dialogue = DialogueParser.parse(raw_json, default_language=args.language)

    if not dialogue:
        logger.error("Parsed 0 dialogue turns from input JSON.")
        return 1

    lang = normalize_language_code(args.language)

    if args.dry_run:
        logger.info(f"[Dry Run] Synthesize audio options valid for {len(dialogue)} turns.")
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "command": "synthesize-audio",
                        "turns": len(dialogue),
                        "dry_run": True,
                    },
                    indent=2,
                )
            )
        return 0

    try:
        logger.info(f"Synthesizing {len(dialogue)} dialogue turns via Piper TTS...")
        out_dir = args.output_dir or "./output/temp_tts"
        os.makedirs(out_dir, exist_ok=True)

        def _tts_cb(curr: int, tot: int) -> None:
            logger.progress(curr / max(1, tot), f"Synthesizing turn {curr}/{tot}...")

        audio_files = synthesize_dialogue_audio(
            dialogue=dialogue,
            language=lang,
            rate=args.speed,
            output_dir=out_dir,
            progress_cb=_tts_cb,
        )

        logger.info(f"Synthesized {len(audio_files)} audio segment files in {out_dir}")

        if args.json:
            res = {
                "success": True,
                "turns": len(dialogue),
                "audio_files": audio_files,
                "output_dir": out_dir,
            }
            print(json.dumps(res, indent=2))
        else:
            for f in audio_files:
                print(f)

        return 0

    except Exception as exc:
        logger.error(str(exc))
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 1


def run_stitch(args: argparse.Namespace, logger: CLILogger) -> int:
    """
    Subcommand 'stitch': Combines MP3 audio segments into an atomic master MP3 with ID3v2 tags.
    """
    input_files: list[str] = []

    if args.files:
        for f in args.files:
            if f.endswith(".json") and os.path.exists(f):
                with open(f, encoding="utf-8") as jf:
                    data = json.load(jf)
                    if isinstance(data, list):
                        input_files.extend(data)
                    elif isinstance(data, dict) and "audio_files" in data:
                        input_files.extend(data["audio_files"])
            else:
                input_files.append(f)
    elif args.input == "-":
        stdin_content = sys.stdin.read().strip()
        try:
            parsed = json.loads(stdin_content)
            if isinstance(parsed, list):
                input_files.extend(parsed)
            elif isinstance(parsed, dict) and "audio_files" in parsed:
                input_files.extend(parsed["audio_files"])
        except json.JSONDecodeError:
            input_files.extend(stdin_content.splitlines())
    elif args.input:
        input_files.append(args.input)

    input_files = [f.strip() for f in input_files if f.strip() and os.path.exists(f.strip())]

    if not input_files:
        logger.error("No valid audio files found to stitch.")
        return 2

    out_mp3 = args.output or "./output/podcast.mp3"

    if args.dry_run:
        logger.info(f"[Dry Run] Stitch options valid. {len(input_files)} input files.")
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "command": "stitch",
                        "input_file_count": len(input_files),
                        "output_mp3": out_mp3,
                        "dry_run": True,
                    },
                    indent=2,
                )
            )
        return 0

    try:
        logger.info(f"Stitching {len(input_files)} MP3 segments into {out_mp3}...")
        master_mp3 = stitch_mp3_files(
            input_files_or_bytes=input_files,
            output_file_path=out_mp3,
            silence_duration_ms=args.silence,
            title=args.title or "Podcast Episode",
            artist=args.artist or "LocalPodcastLLMStudio",
        )

        size_mb = os.path.getsize(master_mp3) / (1024.0 * 1024.0)
        logger.info(f"Successfully stitched master MP3: {master_mp3} ({size_mb:.2f} MB)")

        if args.json:
            res = {
                "success": True,
                "mp3_path": os.path.abspath(master_mp3),
                "file_size_bytes": os.path.getsize(master_mp3),
                "file_size_mb": round(size_mb, 2),
            }
            print(json.dumps(res, indent=2))
        else:
            print(os.path.abspath(master_mp3))

        return 0

    except Exception as exc:
        logger.error(str(exc))
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 1


def run_pipeline(args: argparse.Namespace, logger: CLILogger) -> int:
    """
    Subcommand 'pipeline': Executes full end-to-end unattended podcast creation.
    """
    content = ""
    is_topic = False
    is_raw = False

    if args.topic:
        content = args.topic
        is_topic = True
    elif args.file:
        content = args.file
    elif args.text:
        content = sys.stdin.read() if args.text == "-" else args.text
        is_raw = True
    else:
        logger.error("No input content provided. Specify --topic, -f/--file, or --text.")
        return 2

    lang = normalize_language_code(args.language)
    grounding = (
        normalize_grounding_mode(args.grounding)
        if args.grounding
        else ("open_topic" if is_topic else "strict")
    )

    if args.dry_run:
        clean_url = _validate_url(args.url)
        client = OllamaClient(base_url=clean_url)
        online = client.check_connection(timeout=3.0)
        logger.info(f"[Dry Run] Full pipeline validation passed. Ollama online: {online}")
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "command": "pipeline",
                        "ollama_online": online,
                        "model": args.model,
                        "language": lang,
                        "format": args.length,
                        "grounding": grounding,
                        "dry_run": True,
                    },
                    indent=2,
                )
            )
        return 0

    options = GenerationOptions(
        content=content,
        language=lang,
        model=args.model,
        format_type=args.length,
        tone_style=args.tone,
        speed_rate=args.speed,
        grounding_mode=grounding,
        output_dir=args.output_dir,
        is_topic=is_topic,
        is_raw_text=is_raw,
    )

    service = PodcastGeneratorService(ollama_url=args.url)

    def _progress(pct: float, msg: str) -> None:
        logger.progress(pct, msg)

    try:
        logger.info(
            f"Starting end-to-end podcast generation ({lang}, model={args.model}, format={args.length})..."
        )
        result: GenerationResult = service.generate_podcast(
            options=options,
            progress_callback=_progress,
        )

        logger.info(f"Podcast generated successfully: {result.mp3_path}")

        if args.json:
            res_dict = {
                "success": True,
                "mp3_path": os.path.abspath(result.mp3_path),
                "script_json_path": os.path.abspath(result.script_json_path),
                "script_md_path": os.path.abspath(result.script_md_path),
                "turns_count": len(result.dialogue),
                "duration_estimate_sec": result.duration_estimate_sec,
            }
            print(json.dumps(res_dict, indent=2))
        else:
            print(os.path.abspath(result.mp3_path))

        return 0

    except (
        OllamaConnectionError,
        DocumentExtractionError,
        StudioError,
        ValueError,
        OSError,
        RuntimeError,
        Exception,
    ) as exc:
        logger.error(str(exc))
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 1


# ==============================================================================
# CLI Argument Parser Construction
# ==============================================================================


def build_parser() -> argparse.ArgumentParser:
    """Builds the comprehensive top-level CLI argument parser with subcommands."""
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational logs and progress output",
    )
    common_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results and metadata formatted strictly as JSON to stdout",
    )
    common_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate parameters, paths, and server reachability without executing heavy operations",
    )

    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="LocalPodcastLLMStudio - Autonomous AI Podcast Generation CLI Engine",
        parents=[common_parser],
    )

    # Subcommands
    subparsers = parser.add_subparsers(
        dest="subcommand",
        title="Subcommands",
        help="Subcommand to execute (default: pipeline)",
    )

    # --------------------------------------------------------------------------
    # 1. Pipeline Subcommand (End-to-End Run)
    # --------------------------------------------------------------------------
    pipe_parser = subparsers.add_parser(
        "pipeline",
        parents=[common_parser],
        help="Run full end-to-end podcast generation pipeline unattended",
    )
    _add_pipeline_arguments(pipe_parser)

    # --------------------------------------------------------------------------
    # 2. Extract Subcommand
    # --------------------------------------------------------------------------
    ext_parser = subparsers.add_parser(
        "extract",
        parents=[common_parser],
        help="Extract & normalize text content from PDF, TXT, MD, or topic string",
    )
    ext_parser.add_argument("-f", "--file", type=str, default="", help="Path to input document")
    ext_parser.add_argument(
        "-t",
        "--topic",
        "-p",
        "--prompt",
        type=str,
        default="",
        dest="topic",
        help="Topic/theme string",
    )
    ext_parser.add_argument(
        "--text", type=str, default="", help="Raw text string (or '-' for stdin)"
    )
    ext_parser.add_argument("-o", "--output", type=str, default="", help="Output text file path")

    # --------------------------------------------------------------------------
    # 3. Generate-Script Subcommand
    # --------------------------------------------------------------------------
    gen_parser = subparsers.add_parser(
        "generate-script",
        parents=[common_parser],
        help="Generate multi-act structured dialogue turns using Ollama LLM",
    )
    gen_parser.add_argument("-f", "--file", type=str, default="", help="Path to input document")
    gen_parser.add_argument(
        "-t",
        "--topic",
        "-p",
        "--prompt",
        type=str,
        default="",
        dest="topic",
        help="Topic/theme string",
    )
    gen_parser.add_argument(
        "-i",
        "--input",
        "--text",
        type=str,
        default="",
        dest="input",
        help="Input text or file (or '-' for stdin)",
    )
    gen_parser.add_argument(
        "-m", "--model", type=str, default="llama3.1:8b", help="Ollama LLM model name"
    )
    gen_parser.add_argument(
        "-u", "--url", type=str, default="http://localhost:11434", help="Ollama API URL"
    )
    gen_parser.add_argument(
        "-l",
        "--lang",
        "--language",
        type=str,
        default="nb-NO",
        dest="language",
        help="Language code (nb-NO or en-US)",
    )
    gen_parser.add_argument(
        "--length",
        "--format",
        type=str,
        default="standard",
        dest="length",
        choices=["quick", "standard", "deep_dive", "extended"],
        help="Episode length preset",
    )
    gen_parser.add_argument(
        "--tone",
        type=str,
        default="casual",
        choices=["casual", "analytical", "debate"],
        help="Conversation tone preset",
    )
    gen_parser.add_argument(
        "--grounding",
        type=str,
        default="",
        choices=["", "strict", "creative", "open_topic"],
        help="Grounding fidelity mode",
    )
    gen_parser.add_argument(
        "--temp",
        "--temperature",
        type=float,
        default=0.70,
        dest="temp",
        help="LLM generation temperature",
    )
    gen_parser.add_argument(
        "--system-prompt", type=str, default="", help="Custom system prompt override"
    )
    gen_parser.add_argument("-o", "--output", type=str, default="", help="Output JSON script path")

    # --------------------------------------------------------------------------
    # 4. Synthesize-Audio Subcommand
    # --------------------------------------------------------------------------
    tts_parser = subparsers.add_parser(
        "synthesize-audio",
        parents=[common_parser],
        help="Synthesize per-turn audio files from JSON dialogue using Piper TTS",
    )
    tts_parser.add_argument(
        "-i",
        "--input",
        "-s",
        "--script",
        type=str,
        default="",
        dest="input",
        help="Input JSON dialogue script file path (or '-' for stdin)",
    )
    tts_parser.add_argument(
        "-l",
        "--lang",
        "--language",
        type=str,
        default="nb-NO",
        dest="language",
        help="Language code (nb-NO or en-US)",
    )
    tts_parser.add_argument(
        "--speed", type=str, default="+0%", help="Speaking speed rate (e.g. +0%%, +5%%, -5%%)"
    )
    tts_parser.add_argument(
        "--host1-voice", type=str, default="", help="Custom TTS voice for Host 1"
    )
    tts_parser.add_argument(
        "--host2-voice", type=str, default="", help="Custom TTS voice for Host 2"
    )
    tts_parser.add_argument(
        "-o",
        "--outdir",
        "--output-dir",
        type=str,
        default="./output/temp_tts",
        dest="output_dir",
        help="Output directory for turn audio files",
    )

    # --------------------------------------------------------------------------
    # 5. Stitch Subcommand
    # --------------------------------------------------------------------------
    stitch_parser = subparsers.add_parser(
        "stitch",
        parents=[common_parser],
        help="Concatenate audio turn files into an atomic tagged MP3",
    )
    stitch_parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="",
        help="Input file path, JSON manifest, or '-' for stdin",
    )
    stitch_parser.add_argument(
        "-f", "--files", nargs="*", default=[], help="List of audio turn files to stitch"
    )
    stitch_parser.add_argument(
        "-o", "--output", type=str, default="./output/podcast.mp3", help="Output master MP3 path"
    )
    stitch_parser.add_argument(
        "--silence", type=int, default=350, help="Inter-turn silence duration in milliseconds"
    )
    stitch_parser.add_argument(
        "--title", type=str, default="Podcast Episode", help="ID3v2 Title metadata"
    )
    stitch_parser.add_argument(
        "--artist", type=str, default="LocalPodcastLLMStudio", help="ID3v2 Artist metadata"
    )

    # Also add default pipeline arguments to top-level parser so root invocation runs pipeline
    _add_pipeline_arguments(parser)

    return parser


def _add_pipeline_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds common pipeline parameters to top-level or pipeline subparser."""
    parser.add_argument(
        "-f", "--file", type=str, default="", help="Path to input document (PDF, TXT, MD)"
    )
    parser.add_argument(
        "-t",
        "--topic",
        "-p",
        "--prompt",
        type=str,
        default="",
        dest="topic",
        help="Topic or theme prompt (Rapid Topic-Only mode)",
    )
    parser.add_argument(
        "--text", type=str, default="", help="Raw text string input (or '-' for stdin)"
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default="llama3.1:8b",
        help="Ollama LLM model name (default: llama3.1:8b)",
    )
    parser.add_argument(
        "-u", "--url", type=str, default="http://localhost:11434", help="Ollama host endpoint URL"
    )
    parser.add_argument(
        "-l",
        "--lang",
        "--language",
        type=str,
        default="nb-NO",
        dest="language",
        help="Dialogue language (nb-NO or en-US)",
    )
    parser.add_argument(
        "--length",
        "--format",
        type=str,
        default="standard",
        dest="length",
        choices=["quick", "standard", "deep_dive", "extended"],
        help="Episode length preset",
    )
    parser.add_argument(
        "--tone",
        type=str,
        default="casual",
        choices=["casual", "analytical", "debate"],
        help="Conversation tone preset",
    )
    parser.add_argument(
        "--grounding",
        type=str,
        default="",
        choices=["", "strict", "creative", "open_topic"],
        help="Grounding fidelity mode",
    )
    parser.add_argument("--host1-name", type=str, default="", help="Custom persona name for Host 1")
    parser.add_argument("--host2-name", type=str, default="", help="Custom persona name for Host 2")
    parser.add_argument("--host1-voice", type=str, default="", help="Custom TTS voice for Host 1")
    parser.add_argument("--host2-voice", type=str, default="", help="Custom TTS voice for Host 2")
    parser.add_argument(
        "--speed",
        type=str,
        default="+0%",
        help="Piper TTS speaking rate adjustment (e.g. +0%%, +5%%)",
    )
    parser.add_argument(
        "--temp",
        "--temperature",
        type=float,
        default=0.70,
        dest="temp",
        help="LLM sampling temperature (default: 0.70)",
    )
    parser.add_argument(
        "--system-prompt", type=str, default="", help="Custom system prompt override"
    )
    parser.add_argument(
        "-o",
        "--outdir",
        "--output-dir",
        type=str,
        default="./output",
        dest="output_dir",
        help="Output directory for podcast artifacts",
    )


# ==============================================================================
# CLI Entry Point
# ==============================================================================


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for LocalPodcastLLMStudio CLI Engine.

    Args:
        argv: Optional argument list (defaults to sys.argv[1:]).

    Returns:
        int: Process exit code (0 for success, non-zero for error).
    """
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    logger = CLILogger(quiet=args.quiet, json_mode=args.json)

    subcmd = getattr(args, "subcommand", None)

    if subcmd == "extract":
        return run_extract(args, logger)
    elif subcmd == "generate-script":
        return run_generate_script(args, logger)
    elif subcmd == "synthesize-audio":
        return run_synthesize_audio(args, logger)
    elif subcmd == "stitch":
        return run_stitch(args, logger)
    elif subcmd == "pipeline" or subcmd is None:
        return run_pipeline(args, logger)
    else:
        logger.error(f"Unknown subcommand: {subcmd}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
