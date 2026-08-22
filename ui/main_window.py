"""
LocalPodcastLLMStudio - Main Window & Asynchronous Pipeline Controller
Universal 100% Local Windows Desktop UI with CustomTkinter Fluent Dark theme,
dedicated non-blocking background worker thread, thread-safe queue event loop,
interactive script studio, integrated native MCI audio player, and actionable error dialogs.
"""

import json
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from core.extractor import DocumentExtractionError, extract_text
from core.io_utils import atomic_write_file
from core.logger import get_log_file_path, get_logger, resolve_log_directory
from core.mp3_stitcher import stitch_mp3_files
from core.ollama import (
    ModelPullProgress,
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    generate_podcast_script,
    pull_model_stream,
    start_ollama_service,
)
from core.parser import (
    DialogueParser,
    DialogueTurn,
    dialogue_to_json,
    dialogue_to_markdown,
)
from core.player import WindowsAudioPlayer, export_audio_file
from core.prompts import (
    GROUNDING_MODE_PRESETS,
    normalize_grounding_mode,
)
from core.tts import (
    format_rate_str,
    synthesize_dialogue_audio,
)

# UI Theming & Reusable Widgets
from ui.theme import (
    APP_TITLE,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_BG,
    COLOR_BUTTON_CLOSE,
    COLOR_BUTTON_CLOSE_HOVER,
    COLOR_BUTTON_DANGER,
    COLOR_BUTTON_DANGER_HOVER,
    COLOR_BUTTON_SECONDARY,
    COLOR_BUTTON_SECONDARY_HOVER,
    COLOR_BUTTON_SUCCESS,
    COLOR_BUTTON_SUCCESS_HOVER,
    COLOR_INPUT_BG,
    COLOR_INPUT_BORDER,
    COLOR_PROGRESS_BG,
    COLOR_PROGRESS_FILL,
    COLOR_PROGRESS_TRACK,
    COLOR_SUCCESS,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    DEFAULT_WINDOW_SIZE,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    enable_windows_dark_titlebar,
    get_font_body,
    get_font_body_bold,
    get_font_caption,
    get_font_caption_bold,
    get_font_code,
    get_font_code_small,
    get_font_subtitle,
    get_font_title,
)
from ui.widgets import (
    AboutDialog,
    ActionableErrorDialog,
    CardFrame,
    DialogueTurnCard,
    LabeledSlider,
    LiveStreamingCard,
    SectionHeader,
    StatusBadge,
    TimeSlider,
)

logger = get_logger("ui.main_window")

GROUNDING_UI_OPTIONS: list[str] = [
    "Strict Source-Only (100% Document Fidelity)",
    "Creative Analogy & Synthesis",
    "Open Topic / Scratch (Free Generative Synthesis)",
]

# Backward compatibility alias
_atomic_write_file = atomic_write_file


# ==============================================================================
# Background Generation Worker Thread
# ==============================================================================
class GenerationWorker(threading.Thread):
    """
    Dedicated background worker thread for executing podcast generation tasks.
    Communicates with the CustomTkinter UI exclusively via thread-safe FIFO queue.
    """

    def __init__(
        self,
        mode: str,  # 'full', 'script_only', or 'audio_from_script'
        input_type: str,  # 'file', 'text', 'topic', or 'dialogue'
        input_data: Any,
        language: str,
        model: str,
        format_type: str,
        tone: str,
        speed_rate: str,
        output_dir: str,
        msg_queue: queue.Queue,
        cancel_event: threading.Event,
        grounding_mode: str = "strict",
        ollama_url: str = "http://localhost:11434",
    ):
        super().__init__(daemon=True)
        self.mode = mode
        self.input_type = input_type
        self.input_data = input_data
        self.language = language
        self.model = model
        self.format_type = format_type
        self.tone = tone
        self.speed_rate = speed_rate
        self.output_dir = output_dir
        self.msg_queue = msg_queue
        self.cancel_event = cancel_event
        self.grounding_mode = grounding_mode
        self.ollama_url = ollama_url
        self.temp_turn_files: list[str] = []

    def run(self):
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            os.makedirs(self.output_dir, exist_ok=True)
            dialogue: list[DialogueTurn] = []

            # ------------------------------------------------------------------
            # Phase 1: Ingestion & Script Generation (if not audio_from_script)
            # ------------------------------------------------------------------
            if self.mode != "audio_from_script":
                # Check cancellation
                if self.cancel_event.is_set():
                    self.msg_queue.put(("CANCELLED", "Generation cancelled before ingestion."))
                    return

                self.msg_queue.put(("STATUS", "Extracting and preparing input content..."))
                self.msg_queue.put(("PROGRESS", 0.05))

                is_raw = self.input_type == "text"
                is_topic = self.input_type == "topic"
                source_content = self.input_data

                try:
                    extracted_text = extract_text(
                        source=source_content, is_raw_text=is_raw, is_topic=is_topic
                    )
                except DocumentExtractionError as de_err:
                    self.msg_queue.put(
                        (
                            "ERROR",
                            {
                                "title": "Document Extraction Error",
                                "message": str(de_err),
                                "details": f"Source: {source_content[:100]}...\nError: {de_err}",
                                "remedy": "Please check that the document contains selectable text (not scanned images) and is not password protected.",
                            },
                        )
                    )
                    return

                if not extracted_text or len(extracted_text.strip()) < 10:
                    self.msg_queue.put(
                        (
                            "ERROR",
                            {
                                "title": "Empty Content",
                                "message": "The provided document or prompt is empty or too short.",
                                "details": "Minimum 10 characters required.",
                                "remedy": "Please provide a document with text or enter a more descriptive topic prompt.",
                            },
                        )
                    )
                    return

                self.msg_queue.put(("PROGRESS", 0.15))
                self.msg_queue.put(
                    (
                        "STATUS",
                        f"Connecting to Ollama ({self.model}) and generating dialogue script...",
                    )
                )

                if self.cancel_event.is_set():
                    self.msg_queue.put(("CANCELLED", "Generation cancelled before LLM request."))
                    return

                def progress_cb(msg: str):
                    if not self.cancel_event.is_set():
                        self.msg_queue.put(("STATUS", msg))
                        if "Act 1/" in msg or "Akt 1/" in msg:
                            self.msg_queue.put(("PROGRESS", 0.12))
                        elif "Act 2/" in msg or "Akt 2/" in msg:
                            self.msg_queue.put(("PROGRESS", 0.18))
                        elif "Act 3/" in msg or "Akt 3/" in msg:
                            self.msg_queue.put(("PROGRESS", 0.24))
                        elif "Act 4/" in msg or "Akt 4/" in msg:
                            self.msg_queue.put(("PROGRESS", 0.30))
                        elif "Act 5/" in msg or "Akt 5/" in msg:
                            self.msg_queue.put(("PROGRESS", 0.36))

                def stream_chunk_cb(chunk: str):
                    if not self.cancel_event.is_set():
                        self.msg_queue.put(("STREAM_CHUNK", chunk))

                def act_done_cb(act_idx: int, total_acts: int, turns: list[DialogueTurn]):
                    if not self.cancel_event.is_set():
                        self.msg_queue.put(
                            (
                                "ACT_DONE",
                                {"act_idx": act_idx, "total_acts": total_acts, "turns": turns},
                            )
                        )

                try:
                    dialogue = generate_podcast_script(
                        content=extracted_text,
                        language=self.language,
                        format_type=self.format_type,
                        tone_style=self.tone,
                        grounding_mode=self.grounding_mode,
                        model=self.model,
                        ollama_url=self.ollama_url,
                        is_topic=is_topic,
                        cancel_event=self.cancel_event,
                        progress_callback=progress_cb,
                        stream_callback=stream_chunk_cb,
                        act_callback=act_done_cb,
                    )
                except OllamaModelNotFoundError as mnf_err:
                    self.msg_queue.put(
                        (
                            "ERROR",
                            {
                                "title": "Ollama Model Missing",
                                "message": f"Requested model '{self.model}' is not installed.",
                                "details": str(mnf_err),
                                "remedy": f"Open terminal and run: 'ollama pull {self.model}', then refresh the model list.",
                            },
                        )
                    )
                    return
                except OllamaConnectionError as oc_err:
                    self.msg_queue.put(
                        (
                            "ERROR",
                            {
                                "title": "Ollama Connection Error",
                                "message": "Could not connect to Ollama local service.",
                                "details": str(oc_err),
                                "remedy": "Ensure Ollama is running ('ollama serve' in terminal or Windows tray app) and click Refresh (↻).",
                            },
                        )
                    )
                    return

                if self.cancel_event.is_set():
                    self.msg_queue.put(("CANCELLED", "Generation cancelled by user."))
                    return

                if not dialogue:
                    self.msg_queue.put(
                        (
                            "ERROR",
                            {
                                "title": "Script Parsing Failed",
                                "message": "Failed to parse a structured dialogue script from the model's output.",
                                "details": "The model response did not contain valid dialogue turns.",
                                "remedy": "Try selecting a more capable model (e.g., llama3.1:8b or qwen2.5:7b) and try again.",
                            },
                        )
                    )
                    return

                # Send script to UI
                self.msg_queue.put(("SCRIPT_READY", dialogue))
                self.msg_queue.put(("PROGRESS", 0.40))

                # Save script files to output folder (.json and .md) atomically
                script_json_path = os.path.join(self.output_dir, f"podcast_script_{timestamp}.json")
                atomic_write_file(script_json_path, dialogue_to_json(dialogue))

                script_md_path = os.path.join(self.output_dir, f"podcast_transcript_{timestamp}.md")
                atomic_write_file(script_md_path, dialogue_to_markdown(dialogue))

                if self.mode == "script_only":
                    self.msg_queue.put(("PROGRESS", 1.0))
                    self.msg_queue.put(
                        ("STATUS", f"Script generated successfully! ({len(dialogue)} turns)")
                    )
                    self.msg_queue.put(
                        (
                            "SCRIPT_ONLY_DONE",
                            {
                                "script_path": script_json_path,
                                "script_md_path": script_md_path,
                                "dialogue": dialogue,
                            },
                        )
                    )
                    return

            else:
                # Mode: audio_from_script
                dialogue = self.input_data
                self.msg_queue.put(("PROGRESS", 0.40))
                # Save script files to output folder (.json and .md) atomically
                script_json_path = os.path.join(self.output_dir, f"podcast_script_{timestamp}.json")
                atomic_write_file(script_json_path, dialogue_to_json(dialogue))

                script_md_path = os.path.join(self.output_dir, f"podcast_transcript_{timestamp}.md")
                atomic_write_file(script_md_path, dialogue_to_markdown(dialogue))

            # ------------------------------------------------------------------
            # Phase 2: Local Piper TTS Neural Voice Synthesis
            # ------------------------------------------------------------------
            if self.cancel_event.is_set():
                self.msg_queue.put(("CANCELLED", "Generation cancelled before audio synthesis."))
                return

            self.msg_queue.put(("STATUS", "Synthesizing neural voices with Piper TTS..."))

            def tts_progress_cb(curr: int, tot: int):
                if not self.cancel_event.is_set():
                    # Map progress range: 40% -> 90%
                    pct = 0.40 + (0.50 * (curr / max(1, tot)))
                    turn_speaker = dialogue[curr - 1].speaker if curr <= len(dialogue) else "Host"
                    self.msg_queue.put(("PROGRESS", pct))
                    self.msg_queue.put(
                        ("STATUS", f"Synthesizing turn {curr}/{tot} ({turn_speaker})...")
                    )

            temp_tts_dir = tempfile.mkdtemp(prefix="localpodcastllmstudio_tts_")

            try:
                self.temp_turn_files = synthesize_dialogue_audio(
                    dialogue=dialogue,
                    language=self.language,
                    rate=self.speed_rate,
                    output_dir=temp_tts_dir,
                    progress_cb=tts_progress_cb,
                    cancel_event=self.cancel_event,
                )
            except (RuntimeError, OSError, ValueError, TypeError, Exception) as tts_err:
                # Clean up temp files
                self._cleanup_temp_dir(temp_tts_dir)
                if self.cancel_event.is_set():
                    self.msg_queue.put(("CANCELLED", "Audio synthesis cancelled by user."))
                    return
                self.msg_queue.put(
                    (
                        "ERROR",
                        {
                            "title": "Voice Synthesis Error",
                            "message": f"Piper TTS synthesis encountered an error: {tts_err}",
                            "details": str(tts_err),
                            "remedy": "Please verify Piper TTS local neural voice models in models/voices/ directory.",
                        },
                    )
                )
                return

            if self.cancel_event.is_set():
                self._cleanup_temp_dir(temp_tts_dir)
                self.msg_queue.put(("CANCELLED", "Generation cancelled by user."))
                return

            # ------------------------------------------------------------------
            # Phase 3: Zero-FFmpeg MP3 Binary Frame Stitching
            # ------------------------------------------------------------------
            self.msg_queue.put(("STATUS", "Stitching audio segments into master MP3..."))
            self.msg_queue.put(("PROGRESS", 0.92))

            output_mp3_path = os.path.join(self.output_dir, f"podcast_{timestamp}.mp3")

            try:
                stitch_mp3_files(
                    input_files_or_bytes=self.temp_turn_files,
                    output_file_path=output_mp3_path,
                    silence_duration_ms=350,
                    title=f"Podcast {timestamp}",
                    artist="LocalPodcastLLMStudio",
                )
            except (RuntimeError, ValueError, OSError, Exception) as stitch_err:
                self._cleanup_temp_dir(temp_tts_dir)
                self.msg_queue.put(
                    (
                        "ERROR",
                        {
                            "title": "MP3 Stitching Error",
                            "message": f"Failed to stitch MP3 audio frames: {stitch_err}",
                            "details": str(stitch_err),
                            "remedy": "Check write permissions in the output directory.",
                        },
                    )
                )
                return

            # Clean up temporary turn files
            self._cleanup_temp_dir(temp_tts_dir)

            # ------------------------------------------------------------------
            # Phase 4: Completion & Readiness
            # ------------------------------------------------------------------
            self.msg_queue.put(("PROGRESS", 1.0))
            self.msg_queue.put(
                ("STATUS", f"Ready! Master podcast generated: {os.path.basename(output_mp3_path)}")
            )
            self.msg_queue.put(
                (
                    "GENERATION_DONE",
                    {
                        "mp3_path": output_mp3_path,
                        "script_path": os.path.join(
                            self.output_dir, f"podcast_script_{timestamp}.json"
                        ),
                        "dialogue": dialogue,
                    },
                )
            )

        except Exception as unhandled_err:
            self.msg_queue.put(
                (
                    "ERROR",
                    {
                        "title": "Unexpected Pipeline Error",
                        "message": str(unhandled_err),
                        "details": str(unhandled_err),
                        "remedy": "Please review the error details and try again.",
                    },
                )
            )

    def _cleanup_temp_dir(self, temp_dir: str):
        """Recursively cleans temporary turn files."""
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except OSError:
                pass


# ==============================================================================
# Async Background Workers for Ollama Service & Model Pull
# ==============================================================================
class OllamaLauncherWorker(threading.Thread):
    """
    Dedicated background worker for starting the local Ollama service daemon
    without blocking the GUI main thread.
    """

    def __init__(
        self,
        msg_queue: queue.Queue,
        cancel_event: threading.Event,
        base_url: str = "http://localhost:11434",
        timeout: float = 10.0,
    ):
        super().__init__(daemon=True)
        self.msg_queue = msg_queue
        self.cancel_event = cancel_event
        self.base_url = base_url
        self.timeout = timeout

    def run(self):
        self.msg_queue.put(
            ("SERVICE_LAUNCHING", {"status": "Starting Ollama background service..."})
        )
        try:
            success, msg = start_ollama_service(
                timeout=self.timeout,
                base_url=self.base_url,
                cancel_event=self.cancel_event,
            )
            if success:
                client = OllamaClient(base_url=self.base_url)
                try:
                    models = client.list_models(timeout=3.0)
                except (OllamaConnectionError, TimeoutError, OSError):
                    models = []
                self.msg_queue.put(("SERVICE_STARTED", {"status": msg, "models": models}))
            else:
                self.msg_queue.put(
                    (
                        "SERVICE_ERROR",
                        {
                            "error": msg,
                            "details": (
                                "Could not launch Ollama daemon. "
                                "Ensure Ollama is installed from https://ollama.com or start it manually."
                            ),
                        },
                    )
                )
        except Exception as e:
            self.msg_queue.put(
                (
                    "SERVICE_ERROR",
                    {
                        "error": str(e),
                        "details": f"Error starting Ollama service: {e}",
                    },
                )
            )


class ModelPullWorker(threading.Thread):
    """
    Dedicated background worker for streaming Ollama model downloads
    with real-time progress callbacks and cancellation.
    """

    def __init__(
        self,
        model_name: str,
        msg_queue: queue.Queue,
        cancel_event: threading.Event,
        base_url: str = "http://localhost:11434",
        timeout: float = 3600.0,
    ):
        super().__init__(daemon=True)
        self.model_name = model_name
        self.msg_queue = msg_queue
        self.cancel_event = cancel_event
        self.base_url = base_url
        self.timeout = timeout

    def run(self):
        def progress_cb(progress: ModelPullProgress):
            self.msg_queue.put(("PULL_PROGRESS", progress))

        try:
            success = pull_model_stream(
                model=self.model_name,
                base_url=self.base_url,
                progress_callback=progress_cb,
                cancel_event=self.cancel_event,
                timeout=self.timeout,
            )
            if success:
                self.msg_queue.put(
                    (
                        "PULL_DONE",
                        {
                            "model": self.model_name,
                            "message": f"Model '{self.model_name}' installed and verified successfully.",
                        },
                    )
                )
        except Exception as e:
            if self.cancel_event.is_set():
                self.msg_queue.put(("PULL_CANCELLED", {"model": self.model_name}))
            else:
                self.msg_queue.put(
                    (
                        "PULL_ERROR",
                        {"model": self.model_name, "error": str(e)},
                    )
                )


# ==============================================================================
# Main Application Window
# ==============================================================================
class MainWindow(ctk.CTk):
    """
    Windows 11 Fluent Dark CustomTkinter Main Application Window.
    Coordinates UI layouts, background worker thread dispatch, polling queue,
    interactive script editing, and native MCI audio playback.
    """

    _queue_poll_id: str | None = None
    _player_poll_id: str | None = None
    _is_closing: bool = False
    current_worker: GenerationWorker | None = None
    current_pull_worker: ModelPullWorker | None = None
    current_launcher_worker: OllamaLauncherWorker | None = None
    cancel_event: threading.Event
    pull_cancel_event: threading.Event
    launcher_cancel_event: threading.Event
    player: WindowsAudioPlayer
    is_busy: bool = False
    current_dialogue: list[DialogueTurn]
    current_mp3_path: str | None = None
    current_script_path: str | None = None
    _live_stream_card: LiveStreamingCard | None = None
    _streaming_raw_text: str = ""
    _streaming_chunks_count: int = 0
    _rendered_turns_count: int = 0

    def __init__(self):
        super().__init__()

        # Window Appearance and Sizing
        self.title(APP_TITLE)
        self.geometry(DEFAULT_WINDOW_SIZE)
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color=COLOR_BG)

        # Apply Windows 11 DWM dark title bar
        enable_windows_dark_titlebar(self)

        # Concurrency & Event State
        self.msg_queue: queue.Queue = queue.Queue()
        self.cancel_event: threading.Event = threading.Event()
        self.current_worker: GenerationWorker | None = None

        # Background Worker State for Launcher and Model Downloader
        self.current_launcher_worker: OllamaLauncherWorker | None = None
        self.launcher_cancel_event: threading.Event = threading.Event()
        self.current_pull_worker: ModelPullWorker | None = None
        self.pull_cancel_event: threading.Event = threading.Event()

        # Poller Timer Tracking & Lifecycle Flags
        self._queue_poll_id: str | None = None
        self._player_poll_id: str | None = None
        self._is_closing: bool = False

        # Data & Playback State
        self.current_dialogue: list[DialogueTurn] = []
        self.current_mp3_path: str | None = None
        self.current_script_path: str | None = None
        self.player: WindowsAudioPlayer = WindowsAudioPlayer()
        self.is_busy: bool = False

        # Live Streaming Generation State
        self._live_stream_card: LiveStreamingCard | None = None
        self._streaming_raw_text: str = ""
        self._streaming_chunks_count: int = 0
        self._rendered_turns_count: int = 0

        # Build UI Architecture
        self._build_header()
        self._build_main_layout()

        # Start Async Queue & Audio Pollers
        self._start_queue_poller()
        self._start_player_poller()

        # Clean Window Close Protocol
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Launch non-blocking background Ollama model discovery
        self.refresh_ollama_models()

    # ==========================================================================
    # Header Layout
    # ==========================================================================
    def _build_header(self):
        header_card = CardFrame(
            self, height=65, corner_radius=0, border_width=0, fg_color="#1f2335"
        )
        header_card.pack(fill="x", padx=0, pady=(0, 10))

        inner_header = ctk.CTkFrame(header_card, fg_color="transparent")
        inner_header.pack(fill="both", expand=True, padx=20, pady=10)

        # Title & Subtitle Group
        title_group = ctk.CTkFrame(inner_header, fg_color="transparent")
        title_group.pack(side="left")

        app_title = ctk.CTkLabel(
            title_group,
            text="🎙️ LocalPodcastLLMStudio",
            font=get_font_title(),
            text_color=COLOR_ACCENT,
        )
        app_title.pack(side="left")

        subtitle = ctk.CTkLabel(
            title_group,
            text="100% Local AI Two-Host Podcast Generator",
            font=get_font_subtitle(),
            text_color=COLOR_TEXT_SECONDARY,
        )
        subtitle.pack(side="left", padx=(14, 0), pady=(3, 0))

        # Right Header: Ollama Status Badge + 1-Click Start + Refresh Button
        status_group = ctk.CTkFrame(inner_header, fg_color="transparent")
        status_group.pack(side="right")

        self.ollama_badge = StatusBadge(
            status_group, initial_status="checking", initial_text="Checking Ollama..."
        )
        self.ollama_badge.pack(side="left", padx=(0, 8))

        self.btn_start_ollama_header = ctk.CTkButton(
            status_group,
            text="⚡ Start Ollama",
            width=105,
            height=30,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_SUCCESS,
            hover_color=COLOR_BUTTON_SUCCESS_HOVER,
            text_color=COLOR_TEXT_DARK,
            text_color_disabled=COLOR_TEXT_DARK,
            command=self.start_ollama_service_async,
        )
        self.btn_start_ollama_header.pack(side="left", padx=(0, 8))

        self.btn_refresh_models = ctk.CTkButton(
            status_group,
            text="↻ Refresh",
            width=80,
            height=30,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.refresh_ollama_models,
        )
        self.btn_refresh_models.pack(side="left")

        self.btn_logs = ctk.CTkButton(
            status_group,
            text="📋 Logs",
            width=75,
            height=30,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self._open_logs,
        )
        self.btn_logs.pack(side="left", padx=(8, 0))

        self.btn_about = ctk.CTkButton(
            status_group,
            text="ℹ️ About",
            width=75,
            height=30,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.show_about_dialog,
        )
        self.btn_about.pack(side="left", padx=(8, 0))

    # ==========================================================================
    # Main 2-Column Responsive Layout
    # ==========================================================================
    # ==========================================================================
    # Navigation & Multi-View Layout Architecture ("The Highway")
    # ==========================================================================
    def _build_nav_bar(self):
        """Builds the top navigation bar to toggle between Highway Studio, Script Studio, Settings, and Diagnostics."""
        nav_container = ctk.CTkFrame(self, fg_color="transparent")
        nav_container.pack(fill="x", padx=20, pady=(0, 10))

        self.nav_segmented = ctk.CTkSegmentedButton(
            nav_container,
            values=[
                "🎙️ Studio (The Highway)",
                "📜 Script Studio",
                "⚙️ Settings & Personas",
                "ℹ️ Diagnostics & About",
            ],
            font=get_font_body_bold(),
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            unselected_color="#1f2335",
            unselected_hover_color="#292e42",
            command=self._on_nav_tab_changed,
        )
        self.nav_segmented.set("🎙️ Studio (The Highway)")
        self.nav_segmented.pack(fill="x")

    def switch_tab(self, tab_name: str):
        """Programmatically switches the active view tab."""
        self.nav_segmented.set(tab_name)
        self._on_nav_tab_changed(tab_name)

    def _on_nav_tab_changed(self, selected_tab: str):
        """Switches active view container based on navigation selection."""
        self.view_studio.pack_forget()
        self.view_script_studio.pack_forget()
        self.view_settings.pack_forget()
        self.view_about.pack_forget()

        if "Script" in selected_tab:
            self.view_script_studio.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        elif "Settings" in selected_tab:
            self.view_settings.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        elif "About" in selected_tab or "Diag" in selected_tab:
            self.view_about.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        else:
            self.view_studio.pack(fill="both", expand=True, padx=20, pady=(0, 15))

    def _build_main_layout(self):
        """Builds the main container and initializes all four views."""
        self._build_nav_bar()

        # View 1: Studio Highway
        self.view_studio = ctk.CTkFrame(self, fg_color="transparent")
        self._build_highway_view(self.view_studio)

        # View 2: Dedicated Script Studio
        self.view_script_studio = ctk.CTkFrame(self, fg_color="transparent")
        self._build_script_studio_view(self.view_script_studio)

        # View 3: Settings & Personas
        self.view_settings = ctk.CTkFrame(self, fg_color="transparent")
        self._build_settings_view(self.view_settings)

        # View 4: Diagnostics & About
        self.view_about = ctk.CTkFrame(self, fg_color="transparent")
        self._build_about_view(self.view_about)

        # Default visible view: The Highway Studio
        self.view_studio.pack(fill="both", expand=True, padx=20, pady=(0, 15))

    # ==========================================================================
    # 1. Studio ("The Highway") View
    # ==========================================================================
    def _build_highway_view(self, parent: ctk.CTkFrame):
        """Builds the clean, 1-page end-to-end Highway creation and playback experience."""
        main_grid = ctk.CTkFrame(parent, fg_color="transparent")
        main_grid.pack(fill="both", expand=True)

        main_grid.grid_columnconfigure(0, weight=5, minsize=480)
        main_grid.grid_columnconfigure(1, weight=5, minsize=480)
        main_grid.grid_rowconfigure(0, weight=1)

        # Left Column: Ingestion & 1-Click Action
        self.left_panel = CardFrame(main_grid)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        self._build_highway_left_panel(self.left_panel)

        # Right Column: Live Status & Native Audio Player
        self.right_panel = CardFrame(main_grid)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        self._build_highway_right_panel(self.right_panel)

    def _build_highway_left_panel(self, parent: CardFrame):
        """Builds the left column of the Highway view: Streamlined Ingestion & 1-Click Highway."""
        scroll_container = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_container.pack(fill="both", expand=True, padx=12, pady=12)

        # --- Step 1: Content Ingestion ---
        SectionHeader(
            scroll_container,
            title="1. Source Content Ingestion",
            subtitle="Pick a document, enter a prompt topic, or paste raw text",
            icon="📄",
        ).pack(fill="x", pady=(0, 8))

        self.input_modality_var = ctk.StringVar(value="file")
        self.modality_segmented = ctk.CTkSegmentedButton(
            scroll_container,
            values=["Document (.txt/.md/.pdf)", "Pasted Text", "Topic Prompt (Scratch)"],
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            unselected_color="#1f2335",
            unselected_hover_color="#292e42",
            command=self._on_modality_changed,
        )
        self.modality_segmented.set("Document (.txt/.md/.pdf)")
        self.modality_segmented.pack(fill="x", pady=(0, 10))

        # File Input Container
        self.file_container = ctk.CTkFrame(scroll_container, fg_color="transparent")
        self.file_container.pack(fill="x", pady=(0, 10))

        file_row = ctk.CTkFrame(self.file_container, fg_color="transparent")
        file_row.pack(fill="x")
        self.file_entry = ctk.CTkEntry(
            file_row,
            placeholder_text="Select a .txt, .md, or .pdf file...",
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
        )
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.btn_browse_file = ctk.CTkButton(
            file_row,
            text="Browse...",
            width=80,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_CLOSE,
            hover_color=COLOR_BUTTON_CLOSE_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self._browse_input_file,
        )
        self.btn_browse_file.pack(side="right")

        self.file_info_label = ctk.CTkLabel(
            self.file_container,
            text="Ready to load document.",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        self.file_info_label.pack(anchor="w", pady=(4, 0))

        # Text & Topic Prompt Textbox Container
        self.text_container = ctk.CTkFrame(scroll_container, fg_color="transparent")
        self.text_input_box = ctk.CTkTextbox(
            self.text_container,
            height=130,
            font=get_font_body(),
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            border_width=1,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.text_input_box.pack(fill="both", expand=True)

        # --- Step 2: 1-Click Podcast Highway ---
        SectionHeader(
            scroll_container,
            title="2. 1-Click Podcast Highway",
            subtitle="Fast-lane generation directly into studio audio player",
            icon="🚀",
        ).pack(fill="x", pady=(14, 8))

        # Highway Preset Summary Box
        preset_box = CardFrame(
            scroll_container, fg_color="#1a1c29", corner_radius=8, border_width=1
        )
        preset_box.pack(fill="x", pady=(0, 10))

        p_inner = ctk.CTkFrame(preset_box, fg_color="transparent")
        p_inner.pack(fill="x", padx=12, pady=10)

        p_top = ctk.CTkFrame(p_inner, fg_color="transparent")
        p_top.pack(fill="x")

        ctk.CTkLabel(
            p_top,
            text="⚡ Highway Profile:",
            font=get_font_body_bold(),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        btn_edit_profile = ctk.CTkButton(
            p_top,
            text="⚙️ Edit in Settings →",
            width=130,
            height=24,
            font=get_font_caption_bold(),
            fg_color="transparent",
            text_color=COLOR_ACCENT,
            hover_color="#24283b",
            command=lambda: self.switch_tab("⚙️ Settings & Personas"),
        )
        btn_edit_profile.pack(side="right")

        self.highway_preset_label = ctk.CTkLabel(
            p_inner,
            text="🇺🇸 English (Jenny & Guy) • ⏱️ ~8 min (Standard) • 🤖 Auto Ollama",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        self.highway_preset_label.pack(fill="x", pady=(4, 0))

        # Primary Action: Big 1-Click Generate Podcast Button
        self.btn_generate_full = ctk.CTkButton(
            scroll_container,
            text="🎙️ Generate Podcast (1-Click)",
            height=48,
            font=get_font_body_bold(),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_DARK,
            text_color_disabled=COLOR_TEXT_DARK,
            command=lambda: self.start_generation(mode="full"),
        )
        self.btn_generate_full.pack(fill="x", pady=(4, 8))

        # Secondary Actions Row
        action_row = ctk.CTkFrame(scroll_container, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 6))

        self.btn_generate_script = ctk.CTkButton(
            action_row,
            text="📝 Script Only",
            height=34,
            font=get_font_body_bold(),
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            text_color_disabled=COLOR_TEXT_MUTED,
            command=lambda: self.start_generation(mode="script_only"),
        )
        self.btn_generate_script.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_cancel = ctk.CTkButton(
            action_row,
            text="⏹️ Cancel",
            height=34,
            font=get_font_body_bold(),
            fg_color=COLOR_BUTTON_DANGER,
            hover_color=COLOR_BUTTON_DANGER_HOVER,
            text_color="#ffffff",
            text_color_disabled=COLOR_TEXT_MUTED,
            state="disabled",
            command=self.cancel_generation,
        )
        self.btn_cancel.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_reset = ctk.CTkButton(
            action_row,
            text="🔄 Reset",
            height=34,
            font=get_font_body_bold(),
            fg_color=COLOR_BUTTON_CLOSE,
            hover_color=COLOR_BUTTON_CLOSE_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            text_color_disabled=COLOR_TEXT_MUTED,
            command=self.reset_form,
        )
        self.btn_reset.pack(side="right", fill="x", expand=True)

    def _build_highway_right_panel(self, parent: CardFrame):
        """Builds the right column of the Highway view: Live Status, Dialogue Preview & Native Audio Player."""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=12)

        # --- Section 1: Generation Progress & Live Status ---
        status_box = CardFrame(container, fg_color="#1a1c29", corner_radius=8, border_width=1)
        status_box.pack(fill="x", pady=(0, 10))

        status_top = ctk.CTkFrame(status_box, fg_color="transparent")
        status_top.pack(fill="x", padx=12, pady=(10, 4))

        self.status_label = ctk.CTkLabel(
            status_top,
            text="Ready to generate your podcast.",
            font=get_font_body_bold(),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.progress_pct_label = ctk.CTkLabel(
            status_top, text="0%", font=get_font_caption(), text_color=COLOR_TEXT_SECONDARY
        )
        self.progress_pct_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            status_box, height=10, progress_color=COLOR_ACCENT, fg_color="#24283b"
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 10))

        # --- Section 2: Live Dialogue Preview Container ---
        preview_header_row = ctk.CTkFrame(container, fg_color="transparent")
        preview_header_row.pack(fill="x", pady=(0, 4))

        SectionHeader(
            preview_header_row,
            title="Live Dialogue & Episode Turns",
            subtitle="Real-time multi-act script streaming and turn previews",
            icon="💬",
        ).pack(side="left", fill="x", expand=True)

        self.formatted_scroll = ctk.CTkScrollableFrame(
            container, fg_color="#1a1c29", corner_radius=8
        )
        self.formatted_scroll.pack(fill="both", expand=True, pady=(0, 10))

        self.empty_script_placeholder = ctk.CTkLabel(
            self.formatted_scroll,
            text="No dialogue script generated yet.\nGenerate a podcast to preview turns here.",
            font=get_font_body(),
            text_color=COLOR_TEXT_MUTED,
        )
        self.empty_script_placeholder.pack(pady=40)

        # --- Section 3: Audio Player Studio ---
        player_card = CardFrame(container, fg_color="#1a1c29", corner_radius=8, border_width=1)
        player_card.pack(fill="x", pady=(0, 0))

        # Audio File Info
        player_top = ctk.CTkFrame(player_card, fg_color="transparent")
        player_top.pack(fill="x", padx=12, pady=(10, 4))

        self.player_title_label = ctk.CTkLabel(
            player_top,
            text="Audio Player: No audio loaded",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        self.player_title_label.pack(side="left", fill="x", expand=True)

        # Native Timeline Scrubber
        self.time_slider = TimeSlider(player_card, on_seek=self._on_seek_audio)
        self.time_slider.pack(fill="x", padx=12, pady=(0, 6))

        # Controls & Volume Row
        ctrl_bar = ctk.CTkFrame(player_card, fg_color="transparent")
        ctrl_bar.pack(fill="x", padx=12, pady=(0, 10))

        self.btn_play = ctk.CTkButton(
            ctrl_bar,
            text="▶ Play",
            width=70,
            state="disabled",
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            text_color_disabled=COLOR_TEXT_MUTED,
            command=self._play_audio,
        )
        self.btn_play.pack(side="left", padx=(0, 4))

        self.btn_pause = ctk.CTkButton(
            ctrl_bar,
            text="⏸ Pause",
            width=70,
            state="disabled",
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            text_color_disabled=COLOR_TEXT_MUTED,
            command=self._pause_audio,
        )
        self.btn_pause.pack(side="left", padx=(0, 4))

        self.btn_stop = ctk.CTkButton(
            ctrl_bar,
            text="⏹ Stop",
            width=70,
            state="disabled",
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            text_color_disabled=COLOR_TEXT_MUTED,
            command=self._stop_audio,
        )
        self.btn_stop.pack(side="left", padx=(0, 10))

        # Volume Slider
        ctk.CTkLabel(
            ctrl_bar, text="Vol:", font=get_font_caption(), text_color=COLOR_TEXT_SECONDARY
        ).pack(side="left", padx=(0, 4))
        self.volume_slider = ctk.CTkSlider(
            ctrl_bar,
            from_=0,
            to=100,
            width=90,
            button_color=COLOR_ACCENT,
            command=self._on_volume_changed,
        )
        self.volume_slider.set(80)
        self.volume_slider.pack(side="left", padx=(0, 10))

        # Export & Folder buttons
        self.btn_export_mp3 = ctk.CTkButton(
            ctrl_bar,
            text="💾 Save MP3 As...",
            width=110,
            state="disabled",
            fg_color=COLOR_BUTTON_CLOSE,
            hover_color=COLOR_BUTTON_CLOSE_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            text_color_disabled=COLOR_TEXT_MUTED,
            font=get_font_caption_bold(),
            command=self._save_mp3_as,
        )
        self.btn_export_mp3.pack(side="right", padx=(4, 0))

        self.btn_open_folder = ctk.CTkButton(
            ctrl_bar,
            text="📁 Open Folder",
            width=100,
            fg_color=COLOR_BUTTON_CLOSE,
            hover_color=COLOR_BUTTON_CLOSE_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=get_font_caption_bold(),
            command=self._open_output_folder,
        )
        self.btn_open_folder.pack(side="right")

    # ==========================================================================
    # 2. Script Studio View
    # ==========================================================================
    def _build_script_studio_view(self, parent: ctk.CTkFrame):
        """Builds the dedicated Script Studio view for inspecting and editing raw dialogue scripts."""
        card = CardFrame(parent)
        card.pack(fill="both", expand=True)

        container = ctk.CTkFrame(card, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=16)

        SectionHeader(
            container,
            title="Interactive Script Studio & Synthesizer",
            subtitle="Directly inspect, edit, or paste structured JSON/dialogue scripts and synthesize podcast audio",
            icon="📜",
        ).pack(fill="x", pady=(0, 10))

        # Editable Script Textbox
        self.editable_script_box = ctk.CTkTextbox(
            container,
            font=get_font_code(),
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            border_width=1,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.editable_script_box.pack(fill="both", expand=True, pady=(0, 12))

        # Action bar
        script_bar = ctk.CTkFrame(container, fg_color="transparent")
        script_bar.pack(fill="x")

        self.btn_copy_script = ctk.CTkButton(
            script_bar,
            text="📋 Copy Script",
            width=110,
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=get_font_body_bold(),
            command=self._copy_script_to_clipboard,
        )
        self.btn_copy_script.pack(side="left", padx=(0, 8))

        self.btn_save_script_as = ctk.CTkButton(
            script_bar,
            text="💾 Save Script As...",
            width=130,
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=get_font_body_bold(),
            command=self._save_script_as,
        )
        self.btn_save_script_as.pack(side="left", padx=(0, 8))

        self.btn_synth_from_script = ctk.CTkButton(
            script_bar,
            text="🔊 Synthesize Audio from Script",
            height=36,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_DARK,
            text_color_disabled=COLOR_TEXT_DARK,
            font=get_font_body_bold(),
            command=self._synthesize_from_edited_script,
        )
        self.btn_synth_from_script.pack(side="right")

    def _update_highway_preset_label(self):
        """Dynamically synchronizes the highway profile badge label with active Settings."""
        if not hasattr(self, "highway_preset_label"):
            return
        lang_str = "🇺🇸 English" if "English" in self.lang_menu.get() else "🇳🇴 Norwegian"
        len_raw = self.length_menu.get()
        if "Quick" in len_raw:
            len_str = "⏱️ ~2-3 min (Quick)"
        elif "Deep" in len_raw:
            len_str = "⏱️ ~10-15 min (Deep Dive)"
        elif "Extended" in len_raw:
            len_str = "⏱️ ~25-30 min (Extended)"
        else:
            len_str = "⏱️ ~8 min (Standard)"

        model_str = (
            self.model_menu.get().split(":")[0] if hasattr(self, "model_menu") else "Auto Ollama"
        )
        if not model_str or "Checking" in model_str or "Offline" in model_str:
            model_str = "Auto Ollama"

        self.highway_preset_label.configure(text=f"{lang_str} • {len_str} • 🤖 {model_str}")

    def _build_settings_view(self, parent: ctk.CTkFrame):
        """Builds the comprehensive settings and persona configuration view."""
        card = CardFrame(parent)
        card.pack(fill="both", expand=True)

        scroll_settings = ctk.CTkScrollableFrame(card, fg_color="transparent")
        scroll_settings.pack(fill="both", expand=True, padx=16, pady=16)

        # --- Section 1: Language, Personas & Episode Length ---
        SectionHeader(
            scroll_settings,
            title="Language, Voices & Episode Length",
            subtitle="Configure target language, neural voices, and podcast episode duration",
            icon="🎙️",
        ).pack(fill="x", pady=(0, 8))

        lang_box = CardFrame(scroll_settings, fg_color="#1a1c29", corner_radius=8, border_width=1)
        lang_box.pack(fill="x", pady=(0, 14))

        l_inner = ctk.CTkFrame(lang_box, fg_color="transparent")
        l_inner.pack(fill="x", padx=14, pady=12)

        # Language Selector (Default English)
        ctk.CTkLabel(
            l_inner,
            text="Target Language & Host Personas:",
            font=get_font_body_bold(),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))
        self.lang_menu = ctk.CTkOptionMenu(
            l_inner,
            values=["English (Jenny & Guy)", "Norwegian Bokmål (Kari & Ola)"],
            fg_color=COLOR_BUTTON_SECONDARY,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            command=self._on_language_changed,
        )
        self.lang_menu.set("English (Jenny & Guy)")
        self.lang_menu.pack(fill="x", pady=(0, 8))

        # Episode Length Preset (Default Standard Episode ~8 min)
        ctk.CTkLabel(
            l_inner,
            text="Episode Length Preset:",
            font=get_font_body_bold(),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", pady=(4, 4))
        self.length_menu = ctk.CTkOptionMenu(
            l_inner,
            values=[
                "Standard Episode (12-16 turns, ~5-8 min)",
                "Quick Summary (6-8 turns, ~2-3 min)",
                "Deep Dive (20-26 turns, ~10-15 min)",
                "Extended In-Depth (45-60 turns, ~25-30 min)",
            ],
            fg_color=COLOR_BUTTON_SECONDARY,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            command=lambda _: self._update_highway_preset_label(),
        )
        self.length_menu.set("Standard Episode (12-16 turns, ~5-8 min)")
        self.length_menu.pack(fill="x", pady=(0, 8))

        # Speaking Speed Slider
        self.speed_slider = LabeledSlider(
            l_inner,
            label="Speaking Speed:",
            from_=-10.0,
            to=15.0,
            number_of_steps=5,
            default_value=0.0,
        )
        self.speed_slider.pack(fill="x", pady=(4, 0))

        # --- Section 2: Ollama Model Management & Downloader ---
        SectionHeader(
            scroll_settings,
            title="Ollama LLM Engine & Model Hub",
            subtitle="Select installed local LLM, start daemon, or download new models",
            icon="🤖",
        ).pack(fill="x", pady=(6, 8))

        model_box = CardFrame(scroll_settings, fg_color="#1a1c29", corner_radius=8, border_width=1)
        model_box.pack(fill="x", pady=(0, 14))

        m_inner = ctk.CTkFrame(model_box, fg_color="transparent")
        m_inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(
            m_inner,
            text="Active Ollama Model:",
            font=get_font_body_bold(),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))

        model_row = ctk.CTkFrame(m_inner, fg_color="transparent")
        model_row.pack(fill="x", pady=(0, 8))
        model_row.grid_columnconfigure(0, weight=1)

        self.model_menu = ctk.CTkOptionMenu(
            model_row,
            values=["Checking models..."],
            fg_color=COLOR_BUTTON_SECONDARY,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            command=lambda _: self._update_highway_preset_label(),
        )
        self.model_menu.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_start_ollama = ctk.CTkButton(
            model_row,
            text="⚡ Start",
            width=65,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_SUCCESS,
            hover_color=COLOR_BUTTON_SUCCESS_HOVER,
            text_color=COLOR_TEXT_DARK,
            text_color_disabled=COLOR_TEXT_DARK,
            command=self.start_ollama_service_async,
        )
        self.btn_start_ollama.grid(row=0, column=1, padx=(0, 4))

        self.btn_download_model = ctk.CTkButton(
            model_row,
            text="⬇ Pull",
            width=60,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self._on_download_model_clicked,
        )
        self.btn_download_model.grid(row=0, column=2)

        # Dynamic Streaming Model Pull Progress Container (Hidden by default)
        self.pull_frame = CardFrame(
            m_inner, fg_color=COLOR_PROGRESS_BG, corner_radius=8, border_width=1
        )
        pull_top_row = ctk.CTkFrame(self.pull_frame, fg_color="transparent")
        pull_top_row.pack(fill="x", padx=10, pady=(8, 2))

        self.pull_status_label = ctk.CTkLabel(
            pull_top_row,
            text="Downloading model...",
            font=get_font_caption_bold(),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        self.pull_status_label.pack(side="left", fill="x", expand=True)

        self.pull_speed_label = ctk.CTkLabel(
            pull_top_row,
            text="",
            font=get_font_code_small(),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="e",
        )
        self.pull_speed_label.pack(side="right")

        self.pull_progress_bar = ctk.CTkProgressBar(
            self.pull_frame,
            height=8,
            progress_color=COLOR_PROGRESS_FILL,
            fg_color=COLOR_PROGRESS_TRACK,
        )
        self.pull_progress_bar.set(0.0)
        self.pull_progress_bar.pack(fill="x", padx=10, pady=(4, 6))

        pull_bottom_row = ctk.CTkFrame(self.pull_frame, fg_color="transparent")
        pull_bottom_row.pack(fill="x", padx=10, pady=(0, 8))

        self.pull_details_label = ctk.CTkLabel(
            pull_bottom_row,
            text="",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        self.pull_details_label.pack(side="left", fill="x", expand=True)

        self.btn_cancel_pull = ctk.CTkButton(
            pull_bottom_row,
            text="Cancel",
            width=60,
            height=24,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_DANGER,
            hover_color=COLOR_BUTTON_DANGER_HOVER,
            text_color="#ffffff",
            command=self.cancel_model_pull,
        )
        self.btn_cancel_pull.pack(side="right")
        self.pull_frame.pack_forget()

        # --- Section 3: Grounding & Anti-Hallucination ---
        SectionHeader(
            scroll_settings,
            title="Grounding Mode & Anti-Hallucination",
            subtitle="Choose how strictly the scriptwriter adheres to provided source documents",
            icon="🎯",
        ).pack(fill="x", pady=(6, 8))

        grounding_box = CardFrame(
            scroll_settings, fg_color="#1a1c29", corner_radius=8, border_width=1
        )
        grounding_box.pack(fill="x", pady=(0, 14))

        g_inner = ctk.CTkFrame(grounding_box, fg_color="transparent")
        g_inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(
            g_inner,
            text="Grounding Mode:",
            font=get_font_body_bold(),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))
        self.grounding_menu = ctk.CTkOptionMenu(
            g_inner,
            values=GROUNDING_UI_OPTIONS,
            fg_color=COLOR_BUTTON_SECONDARY,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            command=self._on_grounding_mode_changed,
        )
        self.grounding_menu.set(GROUNDING_UI_OPTIONS[0])
        self.grounding_menu.pack(fill="x", pady=(0, 6))

        self.grounding_desc_label = ctk.CTkLabel(
            g_inner,
            text="",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY,
            wraplength=700,
            justify="left",
            anchor="w",
        )
        self.grounding_desc_label.pack(fill="x", pady=(0, 8))
        self._update_grounding_description()

        ctk.CTkLabel(
            g_inner,
            text="Conversation Tone / Style:",
            font=get_font_body_bold(),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", pady=(6, 4))
        self.tone_menu = ctk.CTkOptionMenu(
            g_inner,
            values=["Casual & Lively", "Analytical & Educational", "Lively Debate"],
            fg_color=COLOR_BUTTON_SECONDARY,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
        )
        self.tone_menu.set("Casual & Lively")
        self.tone_menu.pack(fill="x")

        # --- Section 4: Output Storage ---
        SectionHeader(
            scroll_settings,
            title="Storage & Destination Directory",
            subtitle="Location where generated audio and transcript artifacts are saved",
            icon="📁",
        ).pack(fill="x", pady=(6, 8))

        out_box = CardFrame(scroll_settings, fg_color="#1a1c29", corner_radius=8, border_width=1)
        out_box.pack(fill="x", pady=(0, 14))

        out_inner = ctk.CTkFrame(out_box, fg_color="transparent")
        out_inner.pack(fill="x", padx=14, pady=12)

        out_row = ctk.CTkFrame(out_inner, fg_color="transparent")
        out_row.pack(fill="x")
        self.output_entry = ctk.CTkEntry(
            out_row,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
        )
        default_out = os.path.abspath(os.path.join(os.getcwd(), "output"))
        self.output_entry.insert(0, default_out)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_browse_output = ctk.CTkButton(
            out_row,
            text="Browse...",
            width=80,
            font=get_font_caption_bold(),
            fg_color=COLOR_BUTTON_CLOSE,
            hover_color=COLOR_BUTTON_CLOSE_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self._browse_output_dir,
        )
        self.btn_browse_output.pack(side="right")

    # ==========================================================================
    # 4. Diagnostics & About View
    # ==========================================================================
    def _build_about_view(self, parent: ctk.CTkFrame):
        """Builds the Diagnostics and system metadata view."""
        card = CardFrame(parent)
        card.pack(fill="both", expand=True)

        scroll_about = ctk.CTkScrollableFrame(card, fg_color="transparent")
        scroll_about.pack(fill="both", expand=True, padx=20, pady=20)

        SectionHeader(
            scroll_about,
            title="System Diagnostics & Offline Privacy Guarantee",
            subtitle="Universal 100% Local AI Studio — Zero cloud dependencies, zero telemetry",
            icon="ℹ️",
        ).pack(fill="x", pady=(0, 14))

        diag_box = CardFrame(scroll_about, fg_color="#1a1c29", corner_radius=8, border_width=1)
        diag_box.pack(fill="x", pady=(0, 14))

        d_inner = ctk.CTkFrame(diag_box, fg_color="transparent")
        d_inner.pack(fill="x", padx=16, pady=14)

        info_lines = [
            ("Application", "LocalPodcastLLMStudio v1.0.0"),
            ("License", "MIT License (Free for personal and commercial use)"),
            ("Inference Engine", "Local Ollama HTTP REST API (http://localhost:11434)"),
            ("Voice Synthesizer", "Piper Neural TTS (ONNX Runtime, 100% Offline)"),
            ("Audio Stitcher", "Pure-Python MPEG Frame Assembler (Zero FFmpeg needed)"),
            ("Audio Player Engine", "Native Windows Multimedia MCI Controller"),
            (
                "Privacy Standard",
                "100% Local. Zero telemetry, zero analytics, zero external network traffic.",
            ),
        ]

        for label, val in info_lines:
            row = ctk.CTkFrame(d_inner, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=f"{label}:",
                font=get_font_body_bold(),
                text_color=COLOR_TEXT_PRIMARY,
                width=160,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=val, font=get_font_body(), text_color=COLOR_TEXT_SECONDARY, anchor="w"
            ).pack(side="left", fill="x", expand=True)

        btn_run_env = ctk.CTkButton(
            d_inner,
            text="🔍 Run Preflight Diagnostic Health Check",
            font=get_font_body_bold(),
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.refresh_ollama_models,
        )
        btn_run_env.pack(anchor="w", pady=(14, 0))

    # ==========================================================================
    # Grounding Mode & Modality Synchronization Handlers
    # ==========================================================================
    def get_selected_grounding_mode(self) -> str:
        """Returns normalized canonical grounding mode string: 'strict', 'creative', or 'open_topic'."""
        raw = self.grounding_menu.get().lower()
        if "creative" in raw:
            return "creative"
        if "open" in raw or "scratch" in raw:
            return "open_topic"
        if "strict" in raw or "fidelity" in raw:
            return "strict"
        return normalize_grounding_mode(self.grounding_menu.get())

    def _on_grounding_mode_changed(self, choice: str):
        """Callback when user selects a different grounding mode."""
        self._update_grounding_description()

    def _on_language_changed(self, choice: str):
        """Callback when user selects a different language."""
        self._update_grounding_description()
        self._update_highway_preset_label()

    def _update_grounding_description(self):
        """Updates the caption helper text based on selected mode and language."""
        mode = self.get_selected_grounding_mode()
        preset = GROUNDING_MODE_PRESETS.get(mode, GROUNDING_MODE_PRESETS["strict"])
        lang_is_nb = "Norwegian" in self.lang_menu.get()

        desc = preset["description_nb"] if lang_is_nb else preset["description_en"]
        badge = preset.get("badge", "")
        prefix = f"[{badge}] " if badge else ""
        self.grounding_desc_label.configure(text=f"{prefix}{desc}")

    def _on_modality_changed(self, value: str):
        if "Document" in value:
            self.input_modality_var.set("file")
            self.text_container.pack_forget()
            self.file_container.pack(fill="x", pady=(0, 12))
            # Auto-sync: If in open_topic, switch to strict
            if self.get_selected_grounding_mode() == "open_topic":
                self.grounding_menu.set(GROUNDING_UI_OPTIONS[0])
                self._update_grounding_description()
        elif "Pasted" in value:
            self.input_modality_var.set("text")
            self.file_container.pack_forget()
            self.text_container.pack(fill="both", expand=True, pady=(0, 12))
            # Auto-sync: If in open_topic, switch to strict
            if self.get_selected_grounding_mode() == "open_topic":
                self.grounding_menu.set(GROUNDING_UI_OPTIONS[0])
                self._update_grounding_description()
        else:  # Topic Prompt (Scratch)
            self.input_modality_var.set("topic")
            self.file_container.pack_forget()
            self.text_container.pack(fill="both", expand=True, pady=(0, 12))
            # Auto-sync: Switch to open_topic
            self.grounding_menu.set(GROUNDING_UI_OPTIONS[2])
            self._update_grounding_description()

    def _browse_input_file(self):
        filetypes = [
            ("Supported Documents", "*.txt;*.md;*.pdf"),
            ("Text Files (*.txt)", "*.txt"),
            ("Markdown Files (*.md)", "*.md"),
            ("PDF Documents (*.pdf)", "*.pdf"),
            ("All Files", "*.*"),
        ]
        chosen = filedialog.askopenfilename(filetypes=filetypes)
        if chosen:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, chosen)
            try:
                size_kb = os.path.getsize(chosen) / 1024
                self.file_info_label.configure(
                    text=f"Selected: {os.path.basename(chosen)} ({size_kb:.1f} KB)",
                    text_color=COLOR_SUCCESS,
                )
            except OSError:
                self.file_info_label.configure(text=f"Selected: {os.path.basename(chosen)}")

    def _browse_output_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.output_entry.get())
        if chosen:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, os.path.abspath(chosen))

    # ==========================================================================
    # Ollama Model Discovery & 1-Click Async Actions
    # ==========================================================================
    def refresh_ollama_models(self):
        """Asynchronously checks Ollama connection and installed models."""
        self.ollama_badge.set_status("checking", "Checking Ollama...")
        self.btn_refresh_models.configure(state="disabled")

        def _bg_fetch():
            client = OllamaClient()
            try:
                models = client.list_models(timeout=3.0)
                self.msg_queue.put(("OLLAMA_STATUS", {"connected": True, "models": models}))
            except (OllamaConnectionError, TimeoutError, OSError, RuntimeError) as err:
                self.msg_queue.put(
                    ("OLLAMA_STATUS", {"connected": False, "models": [], "error": str(err)})
                )

        threading.Thread(target=_bg_fetch, daemon=True).start()

    def start_ollama_service_async(self):
        """Launches local Ollama service in background thread."""
        if self.current_launcher_worker and self.current_launcher_worker.is_alive():
            return
        self.launcher_cancel_event.clear()
        self.ollama_badge.set_status("starting", "Starting Ollama...")
        self.btn_start_ollama_header.configure(state="disabled")
        self.btn_start_ollama.configure(state="disabled")
        self.current_launcher_worker = OllamaLauncherWorker(
            msg_queue=self.msg_queue,
            cancel_event=self.launcher_cancel_event,
        )
        self.current_launcher_worker.start()

    def _on_download_model_clicked(self):
        """Triggers download for currently selected model in menu, or defaults to llama3.1:8b."""
        curr = self.model_menu.get().strip()
        if not curr or "Offline" in curr or "Checking" in curr or "No models" in curr:
            target = "llama3.1:8b"
        else:
            target = curr
        self.download_model_async(target)

    def download_model_async(self, model_name: str = "llama3.1:8b"):
        """Starts streaming download of an Ollama model in background."""
        if self.current_pull_worker and self.current_pull_worker.is_alive():
            messagebox.showinfo("Download in Progress", "A model download is already in progress.")
            return

        self.pull_cancel_event.clear()
        self.pull_progress_bar.set(0.0)
        self.pull_status_label.configure(text=f"Pulling '{model_name}'...")
        self.pull_speed_label.configure(text="")
        self.pull_details_label.configure(text="Connecting to Ollama...")
        self.btn_cancel_pull.configure(state="normal")
        self.pull_frame.pack(fill="x", pady=(0, 10))
        self.ollama_badge.set_status("downloading", f"Pulling {model_name}...")

        self.current_pull_worker = ModelPullWorker(
            model_name=model_name,
            msg_queue=self.msg_queue,
            cancel_event=self.pull_cancel_event,
        )
        self.current_pull_worker.start()

    def cancel_model_pull(self):
        """Cancels active model pull operation."""
        if self.current_pull_worker and self.current_pull_worker.is_alive():
            self.pull_cancel_event.set()
            self.pull_status_label.configure(text="Cancelling download...")
            self.btn_cancel_pull.configure(state="disabled")

    def _handle_ollama_status(self, data: dict[str, Any]):
        self.btn_refresh_models.configure(state="normal")
        self.btn_start_ollama_header.configure(state="normal")
        self.btn_start_ollama.configure(state="normal")

        if data.get("connected") and data.get("models"):
            models = data["models"]
            self.model_menu.configure(values=models)

            # Smart preferred model selection
            preferred_order = [
                "llama3.1:8b",
                "mistral-nemo:latest",
                "qwen2.5:7b",
                "llama3:8b",
                "mistral:latest",
                "gemma2:9b",
                "phi3:medium",
            ]
            selected = models[0]
            for pref in preferred_order:
                matched = [m for m in models if pref in m]
                if matched:
                    selected = matched[0]
                    break
            self.model_menu.set(selected)
            self.ollama_badge.set_status("online", f"Ollama Connected ({len(models)} models)")
            self.btn_start_ollama_header.configure(state="disabled")
            self.btn_start_ollama.configure(state="disabled")
        elif data.get("connected"):
            self.model_menu.configure(values=["No models installed"])
            self.model_menu.set("No models installed")
            self.ollama_badge.set_status("warning", "Ollama Online (No models)")
            self.btn_start_ollama_header.configure(state="disabled")
            self.btn_start_ollama.configure(state="disabled")
        else:
            self.model_menu.configure(values=["Ollama Offline (No models)"])
            self.model_menu.set("Ollama Offline (No models)")
            self.ollama_badge.set_status("offline", "Ollama Offline")

        self._update_highway_preset_label()

    # ==========================================================================
    # Workflow Execution: Start Generation
    # ==========================================================================
    def start_generation(self, mode: str = "full"):
        """Validates inputs and spawns the background GenerationWorker."""
        modality = self.input_modality_var.get()
        source_data = ""

        if modality == "file":
            file_path = self.file_entry.get().strip()
            if not file_path or not os.path.exists(file_path):
                ActionableErrorDialog(
                    self,
                    title="Missing Document File",
                    message="Please select a valid .txt, .md, or .pdf file before generating.",
                    details="Click 'Browse...' in the left panel to choose a file.",
                )
                return
            source_data = file_path
        else:
            text_data = self.text_input_box.get("1.0", "end-1c").strip()
            if not text_data:
                ActionableErrorDialog(
                    self,
                    title="Input Required",
                    message="Please enter some text or a topic prompt description in the input box.",
                )
                return
            source_data = text_data

        selected_model = self.model_menu.get()
        if (
            "Offline" in selected_model
            or "Checking" in selected_model
            or "No models" in selected_model
            or not selected_model
        ):
            if "Offline" in selected_model:
                ActionableErrorDialog(
                    self,
                    title="Ollama Service Required",
                    message="Local Ollama is offline.\n\nPlease start Ollama to generate podcasts with local LLMs.",
                    details="Run 'ollama serve' in terminal or launch Ollama from Windows tray.\nRun 'ollama pull llama3.1:8b' to install the recommended model.",
                    actions=[
                        ("⚡ Start Ollama", self.start_ollama_service_async, "success"),
                        (
                            "⬇ Download llama3.1:8b",
                            lambda: self.download_model_async("llama3.1:8b"),
                            "accent",
                        ),
                        ("↻ Refresh", self.refresh_ollama_models, "secondary"),
                    ],
                    dialog_type="prerequisite",
                )
            else:
                ActionableErrorDialog(
                    self,
                    title="Model Required",
                    message="No LLM models are installed in your local Ollama instance.",
                    details="Click 'Download llama3.1:8b' below or run 'ollama pull llama3.1:8b' in terminal.",
                    actions=[
                        (
                            "⬇ Download llama3.1:8b",
                            lambda: self.download_model_async("llama3.1:8b"),
                            "accent",
                        ),
                        ("↻ Refresh", self.refresh_ollama_models, "secondary"),
                    ],
                    dialog_type="warning",
                )
            return

        # Map Form Inputs
        lang = "nb-NO" if "Norwegian" in self.lang_menu.get() else "en-US"
        raw_len = self.length_menu.get()
        if "Quick" in raw_len:
            fmt_type = "quick"
        elif "Deep" in raw_len:
            fmt_type = "deep_dive"
        elif "Extended" in raw_len:
            fmt_type = "extended"
        else:
            fmt_type = "standard"

        raw_tone = self.tone_menu.get()
        if "Analytical" in raw_tone:
            tone_style = "analytical"
        elif "Debate" in raw_tone:
            tone_style = "debate"
        else:
            tone_style = "casual"

        speed_val = self.speed_slider.get()
        speed_rate = format_rate_str(speed_val)
        out_dir = self.output_entry.get().strip() or os.path.abspath("./output")
        grounding_mode = self.get_selected_grounding_mode()

        # Prepare Worker & Live Streaming UI
        self.cancel_event.clear()
        self._set_busy_state(True)
        self.progress_bar.set(0.02)
        self.status_label.configure(text=f"Connecting to Ollama ({selected_model})...")
        self._init_live_streaming_ui(selected_model)

        self.current_worker = GenerationWorker(
            mode=mode,
            input_type=modality,
            input_data=source_data,
            language=lang,
            model=selected_model,
            format_type=fmt_type,
            tone=tone_style,
            speed_rate=speed_rate,
            output_dir=out_dir,
            msg_queue=self.msg_queue,
            cancel_event=self.cancel_event,
            grounding_mode=grounding_mode,
        )
        self.current_worker.start()

    def cancel_generation(self):
        """Signals active worker thread to abort execution."""
        if self.current_worker and self.current_worker.is_alive():
            self.cancel_event.set()
            self.status_label.configure(text="Cancelling generation...")
            self.btn_cancel.configure(state="disabled")

    def _synthesize_from_edited_script(self):
        """Synthesizes audio directly from the user-edited script tab."""
        if getattr(self, "is_busy", False):
            return

        try:
            raw_text = self.editable_script_box.get("1.0", "end-1c").strip()
            if not raw_text:
                ActionableErrorDialog(
                    self,
                    title="Empty Script",
                    message="No dialogue script content found in the editor to synthesize.",
                )
                return

            dialogue_turns: list[DialogueTurn] = []
            # Attempt JSON parsing first, then fallback to multi-tier dialogue parsing
            try:
                parsed_json = json.loads(raw_text)
                if isinstance(parsed_json, list):
                    dialogue_turns = [
                        DialogueTurn(speaker=t.get("speaker", "Host 1"), text=t.get("text", ""))
                        for t in parsed_json
                        if isinstance(t, dict)
                    ]
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

            if not dialogue_turns:
                dialogue_turns = DialogueParser.parse(raw_text)

            if not dialogue_turns:
                ActionableErrorDialog(
                    self,
                    title="Invalid Script Format",
                    message="Could not parse dialogue turns from the script box.",
                    details="Please ensure dialogue turns follow JSON or 'Host 1: ...' format.",
                )
                return

            lang = "nb-NO" if "Norwegian" in self.lang_menu.get() else "en-US"
            speed_val = self.speed_slider.get()
            speed_rate = format_rate_str(speed_val)
            out_dir = self.output_entry.get().strip() or os.path.abspath("./output")

            self.cancel_event.clear()
            self._set_busy_state(True)
            self.progress_bar.set(0.40)
            self.status_label.configure(text="Synthesizing audio from edited script...")

            self.current_worker = GenerationWorker(
                mode="audio_from_script",
                input_type="dialogue",
                input_data=dialogue_turns,
                language=lang,
                model=self.model_menu.get(),
                format_type="custom",
                tone="custom",
                speed_rate=speed_rate,
                output_dir=out_dir,
                msg_queue=self.msg_queue,
                cancel_event=self.cancel_event,
                grounding_mode=self.get_selected_grounding_mode(),
            )
            self.current_worker.start()
        except Exception as e:
            self._set_busy_state(False)
            ActionableErrorDialog(
                self,
                title="Synthesis Initialization Error",
                message=f"Failed to start audio synthesis: {e}",
                details=str(e),
            )

    # ==========================================================================
    # Queue Poller & Event Dispatch Loop
    # ==========================================================================
    def _start_queue_poller(self):
        if self._is_closing:
            return
        self._process_queue(max_batch_size=30)
        if not self._is_closing:
            self._queue_poll_id = self.after(50, self._start_queue_poller)

    def _process_queue(self, max_batch_size: int | None = None):
        processed = 0
        while not self.msg_queue.empty():
            if max_batch_size is not None and processed >= max_batch_size:
                break
            try:
                event_type, payload = self.msg_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle_event(event_type, payload)
            except (RuntimeError, AttributeError, ValueError, TypeError):
                pass
            finally:
                self.msg_queue.task_done()
                processed += 1

    def _handle_event(self, event_type: str, payload: Any):
        if event_type == "STATUS":
            self.status_label.configure(text=str(payload))
        elif event_type == "PROGRESS":
            pct = float(payload)
            self.progress_bar.set(pct)
            self.progress_pct_label.configure(text=f"{int(pct * 100)}%")
        elif event_type == "STREAM_CHUNK":
            self._handle_stream_chunk(str(payload))
        elif event_type in ("ACT_DONE", "ACT_READY"):
            if isinstance(payload, dict):
                self._handle_act_done(payload)
        elif event_type == "SCRIPT_READY":
            live_card = getattr(self, "_live_stream_card", None)
            if live_card is not None:
                try:
                    live_card.destroy()
                except (RuntimeError, AttributeError):
                    pass
                self._live_stream_card = None
            if hasattr(self, "_render_transcript"):
                self._render_transcript(payload)
        elif event_type == "GENERATION_DONE":
            self._on_generation_done(payload)
        elif event_type == "SCRIPT_ONLY_DONE":
            self._on_script_only_done(payload)
        elif event_type == "OLLAMA_STATUS":
            self._handle_ollama_status(payload)
        elif event_type == "SERVICE_LAUNCHING":
            status_msg = (
                payload.get("status", "Launching Ollama background service...")
                if isinstance(payload, dict)
                else str(payload)
            )
            self.ollama_badge.set_status("starting", "Starting Ollama...")
            self.status_label.configure(text=status_msg)
            self.btn_start_ollama_header.configure(state="disabled")
            self.btn_start_ollama.configure(state="disabled")
        elif event_type == "SERVICE_STARTED":
            status_msg = (
                payload.get("status", "Ollama service started.")
                if isinstance(payload, dict)
                else str(payload)
            )
            models = payload.get("models", []) if isinstance(payload, dict) else []
            self.status_label.configure(text=status_msg)
            if models:
                self._handle_ollama_status({"connected": True, "models": models})
            else:
                self.refresh_ollama_models()
        elif event_type == "SERVICE_ERROR":
            err_msg = (
                payload.get("error", "Service launch error")
                if isinstance(payload, dict)
                else str(payload)
            )
            details = payload.get("details", "") if isinstance(payload, dict) else ""
            self.ollama_badge.set_status("offline", "Ollama Offline")
            self.btn_start_ollama_header.configure(state="normal")
            self.btn_start_ollama.configure(state="normal")
            self.status_label.configure(text=f"Service launch failed: {err_msg}")
            ActionableErrorDialog(
                self,
                title="Ollama Launch Failed",
                message=f"Failed to start Ollama background service:\n{err_msg}",
                details=details or "Please make sure Ollama is installed from https://ollama.com.",
                actions=[
                    ("⚡ Retry Start", self.start_ollama_service_async, "accent"),
                    ("↻ Refresh", self.refresh_ollama_models, "secondary"),
                ],
                dialog_type="error",
            )
        elif event_type == "PULL_PROGRESS":
            if isinstance(payload, ModelPullProgress):
                pct = payload.percentage
                self.pull_progress_bar.set(pct)
                status_text = payload.progress_str or payload.status
                self.pull_status_label.configure(
                    text=f"Pulling {payload.status} ({int(pct * 100)}%)"
                )
                speed_info = []
                if payload.speed_str:
                    speed_info.append(payload.speed_str)
                if payload.eta_str:
                    speed_info.append(f"ETA: {payload.eta_str}")
                self.pull_speed_label.configure(text=" | ".join(speed_info))
                self.pull_details_label.configure(text=status_text)
                self.ollama_badge.set_status("downloading", f"Pulling ({int(pct * 100)}%)")
                self.status_label.configure(
                    text=status_text or f"Downloading model: {int(pct * 100)}%"
                )
        elif event_type == "PULL_DONE":
            model_name = payload.get("model", "") if isinstance(payload, dict) else ""
            msg = (
                payload.get("message", f"Model '{model_name}' installed.")
                if isinstance(payload, dict)
                else str(payload)
            )
            self.pull_frame.pack_forget()
            self.ollama_badge.set_status(
                "online", f"Model Ready: {model_name}" if model_name else "Ollama Online"
            )
            self.status_label.configure(text=msg)
            self.refresh_ollama_models()
        elif event_type == "PULL_ERROR":
            model_name = payload.get("model", "") if isinstance(payload, dict) else ""
            err = payload.get("error", "Pull failed") if isinstance(payload, dict) else str(payload)
            self.pull_frame.pack_forget()
            self.ollama_badge.set_status("error", "Download Failed")
            self.status_label.configure(text=f"Download failed: {err}")
            ActionableErrorDialog(
                self,
                title="Model Download Failed",
                message=f"Could not download model '{model_name}':\n{err}",
                details="Check internet connection, disk space, and Ollama service status.",
                actions=[
                    ("⬇ Retry Download", lambda: self.download_model_async(model_name), "accent"),
                    ("↻ Refresh", self.refresh_ollama_models, "secondary"),
                ],
                dialog_type="error",
            )
        elif event_type == "PULL_CANCELLED":
            self.pull_frame.pack_forget()
            self.status_label.configure(text="Model download cancelled.")
            self.refresh_ollama_models()
        elif event_type == "CANCELLED":
            live_card = getattr(self, "_live_stream_card", None)
            if live_card is not None:
                try:
                    live_card.destroy()
                except (RuntimeError, AttributeError):
                    pass
                self._live_stream_card = None
            if hasattr(self, "_set_busy_state"):
                self._set_busy_state(False)
            if hasattr(self, "status_label"):
                self.status_label.configure(text=str(payload))
            if hasattr(self, "progress_bar"):
                self.progress_bar.set(0.0)
            if hasattr(self, "progress_pct_label"):
                self.progress_pct_label.configure(text="0%")
            curr_diag = getattr(self, "current_dialogue", None)
            if not curr_diag and hasattr(self, "_render_transcript"):
                self._render_transcript([])
        elif event_type == "ERROR":
            live_card = getattr(self, "_live_stream_card", None)
            if live_card is not None:
                try:
                    live_card.destroy()
                except (RuntimeError, AttributeError):
                    pass
                self._live_stream_card = None
            if hasattr(self, "_set_busy_state"):
                self._set_busy_state(False)
            if hasattr(self, "status_label"):
                self.status_label.configure(text="Error encountered.")
            curr_diag = getattr(self, "current_dialogue", None)
            if not curr_diag and hasattr(self, "_render_transcript"):
                self._render_transcript([])
            if isinstance(payload, dict):
                ActionableErrorDialog(
                    self,
                    title=payload.get("title", "Error") or "Error",
                    message=payload.get("message", "An error occurred.") or "An error occurred.",
                    details=payload.get("details"),
                    remedy=payload.get("remedy"),
                    actions=payload.get("actions"),
                    dialog_type=payload.get("dialog_type", "error") or "error",
                )
            else:
                if hasattr(self, "winfo_exists") and self.winfo_exists():
                    messagebox.showerror("Error", str(payload))

    def _init_live_streaming_ui(self, model_name: str):
        """Initializes live streaming UI state across Formatted Dialogue and Editable Script tabs."""
        self._streaming_raw_text = ""
        self._streaming_chunks_count = 0
        self._rendered_turns_count = 0
        self.current_dialogue = []

        # Clear formatted scroll view
        for widget in self.formatted_scroll.winfo_children():
            widget.destroy()

        # Create Live Streaming Card
        self._live_stream_card = LiveStreamingCard(
            self.formatted_scroll,
            title=f"Generating dialogue with Ollama ({model_name})...",
            model_name=model_name,
        )
        self._live_stream_card.pack(fill="x", pady=4)

        # In Editable Script Tab: Show live header and clear old content
        self.editable_script_box.delete("1.0", "end")
        self.editable_script_box.insert(
            "1.0",
            f"# Live Dialogue Stream from Ollama ({model_name})\n# Generating in real-time...\n\n",
        )

    def _handle_stream_chunk(self, chunk: str):
        """Appends streaming chunk to live stream card and editable script box."""
        if not chunk:
            return
        self._streaming_raw_text += chunk
        self._streaming_chunks_count += 1

        # 1. Update Live Streaming Card in Formatted tab
        if self._live_stream_card:
            self._live_stream_card.append_chunk(chunk)

        # 2. Update Editable Script Box
        try:
            self.editable_script_box.insert("end", chunk)
            self.editable_script_box.see("end")
        except (RuntimeError, AttributeError, ValueError):
            pass

        # 3. Update status text with live token/chunk count if currently busy
        if self.is_busy:
            status_curr = self.status_label.cget("text")
            if (
                "Writing Act" in status_curr
                or "Generating" in status_curr
                or "Streaming" in status_curr
                or "Connecting" in status_curr
                or "Akt " in status_curr
            ):
                base_status = status_curr.split(" (Streaming")[0].rstrip(".")
                self.status_label.configure(
                    text=f"{base_status} (Streaming: ~{self._streaming_chunks_count} chunks)..."
                )

    def _handle_act_done(self, data: dict[str, Any]):
        """Renders completed act turns into Formatted Dialogue view while keeping live stream card below."""
        act_idx = int(data.get("act_idx", 1))
        total_acts = int(data.get("total_acts", 1))
        act_turns: list[DialogueTurn] = data.get("turns", [])

        if not act_turns:
            return

        # Add to current_dialogue
        self.current_dialogue.extend(act_turns)

        # If live_stream_card is packed, unpack it temporarily to append turn cards
        if self._live_stream_card:
            self._live_stream_card.pack_forget()

        # Render new DialogueTurnCards for each turn in this act
        start_idx = self._rendered_turns_count + 1
        for i, turn in enumerate(act_turns, start=start_idx):
            turn_card = DialogueTurnCard(
                self.formatted_scroll,
                turn_number=i,
                speaker=turn.speaker,
                text=turn.text,
            )
            turn_card.pack(fill="x", pady=4)
        self._rendered_turns_count += len(act_turns)

        # If more acts remain, reset and repack the LiveStreamingCard below the completed turns
        if act_idx < total_acts and self._live_stream_card:
            next_act = act_idx + 1
            self._live_stream_card.reset(
                title=f"Writing Act {next_act}/{total_acts} (Current total: {len(self.current_dialogue)} turns)..."
            )
            self._live_stream_card.pack(fill="x", pady=4)

    # ==========================================================================
    # UI State & Transcript Rendering
    # ==========================================================================
    def _set_busy_state(self, busy: bool):
        self.is_busy = busy
        state = "disabled" if busy else "normal"

        self.btn_generate_full.configure(state=state)
        self.btn_generate_script.configure(state=state)
        self.btn_synth_from_script.configure(state=state)
        self.btn_reset.configure(state=state)
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def _render_transcript(self, dialogue: list[DialogueTurn]):
        self.current_dialogue = dialogue

        # Clear existing formatted dialogue cards
        for widget in self.formatted_scroll.winfo_children():
            widget.destroy()

        if not dialogue:
            self.empty_script_placeholder = ctk.CTkLabel(
                self.formatted_scroll,
                text="No dialogue turns available.",
                font=get_font_body(),
                text_color=COLOR_TEXT_MUTED,
            )
            self.empty_script_placeholder.pack(pady=40)
            return

        for idx, turn in enumerate(dialogue, start=1):
            turn_card = DialogueTurnCard(
                self.formatted_scroll, turn_number=idx, speaker=turn.speaker, text=turn.text
            )
            turn_card.pack(fill="x", pady=4)

        # Update Editable Script Box with JSON representation
        self.editable_script_box.delete("1.0", "end")
        self.editable_script_box.insert("1.0", dialogue_to_json(dialogue))

    def _on_generation_done(self, result: dict[str, Any]):
        self._set_busy_state(False)
        self.current_mp3_path = result.get("mp3_path")
        self.current_script_path = result.get("script_path")

        if self.current_mp3_path and os.path.exists(self.current_mp3_path):
            self.player_title_label.configure(
                text=f"Loaded: {os.path.basename(self.current_mp3_path)}"
            )
            try:
                self.player.open(self.current_mp3_path)
                self.btn_play.configure(state="normal")
                self.btn_pause.configure(state="normal")
                self.btn_stop.configure(state="normal")
                self.btn_export_mp3.configure(state="normal")

                # Update initial time slider
                tot_ms = self.player.get_length()
                self.time_slider.update_position(0, tot_ms, "Loaded")
            except Exception:
                pass

    def _on_script_only_done(self, result: dict[str, Any]):
        self._set_busy_state(False)
        self.current_script_path = result.get("script_path")
        messagebox.showinfo(
            "Script Ready",
            f"Podcast dialogue script generated successfully!\n\nSaved to: {os.path.basename(str(self.current_script_path))}",
        )

    # ==========================================================================
    # Audio Player & MCI Integration
    # ==========================================================================
    def _start_player_poller(self):
        if self._is_closing:
            return
        self._update_player_position()
        if not self._is_closing:
            self._player_poll_id = self.after(250, self._start_player_poller)

    def _update_player_position(self):
        if self.player and self.player._is_open:
            cur_ms = self.player.get_position()
            tot_ms = self.player.get_length()
            mode = self.player.get_mode()
            self.time_slider.update_position(cur_ms, tot_ms, mode)

    def _play_audio(self):
        if self.current_mp3_path and os.path.exists(self.current_mp3_path):
            if not self.player._is_open:
                self.player.open(self.current_mp3_path)
            self.player.play()

    def _pause_audio(self):
        if self.player and self.player._is_open:
            if self.player.is_paused():
                self.player.resume()
            else:
                self.player.pause()

    def _stop_audio(self):
        if self.player and self.player._is_open:
            self.player.stop()

    def _on_seek_audio(self, target_ms: int):
        if self.player and self.player._is_open:
            self.player.seek(target_ms)

    def _on_volume_changed(self, val: float):
        if self.player:
            self.player.set_volume(int(val))

    def _save_mp3_as(self):
        if not self.current_mp3_path or not os.path.exists(self.current_mp3_path):
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3 Audio Files", "*.mp3")],
            initialfile=os.path.basename(self.current_mp3_path),
        )
        if dest:
            try:
                export_audio_file(self.current_mp3_path, dest)
                messagebox.showinfo("Export Successful", f"Master podcast exported to:\n{dest}")
            except OSError as e:
                messagebox.showerror("Export Failed", f"Could not export MP3: {e}")

    def _open_output_folder(self):
        raw_dir = self.output_entry.get().strip() or os.path.abspath("./output")
        out_dir = os.path.abspath(raw_dir)
        try:
            os.makedirs(out_dir, exist_ok=True)
            if sys.platform == "win32" and os.path.isdir(out_dir):
                os.startfile(out_dir)  # nosec: B606
        except OSError:
            pass

    def _open_logs(self):
        """Opens the application log file or log directory for inspection."""
        log_path = get_log_file_path()
        log_dir = resolve_log_directory()
        logger.info("Opening application log directory/file: %s", log_path)
        try:
            if sys.platform == "win32":
                if os.path.isfile(log_path):
                    os.startfile(log_path)  # nosec: B606
                elif os.path.isdir(log_dir):
                    os.startfile(log_dir)  # nosec: B606
            else:
                if os.path.isdir(log_dir):
                    os.system(f'xdg-open "{log_dir}"')  # nosec: B605
        except OSError as e:
            logger.warning("Could not open log file directly: %s", e)
            messagebox.showinfo("Log File Location", f"Application logs are stored at:\n{log_path}")

    # ==========================================================================
    # Script Actions: Copy, Save As
    # ==========================================================================
    def _copy_script_to_clipboard(self):
        text = self.editable_script_box.get("1.0", "end-1c").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", "Dialogue script copied to clipboard!")

    def _save_script_as(self):
        text = self.editable_script_box.get("1.0", "end-1c").strip()
        if not text:
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[
                ("JSON Script", "*.json"),
                ("Markdown Transcript", "*.md"),
                ("Plain Text", "*.txt"),
            ],
            initialfile="podcast_dialogue.json",
        )
        if dest:
            try:
                atomic_write_file(dest, text)
                messagebox.showinfo("Saved", f"Script saved to:\n{dest}")
            except OSError as e:
                messagebox.showerror("Save Failed", f"Could not save script: {e}")

    def reset_form(self):
        """Clears inputs and resets view."""
        if self._live_stream_card:
            try:
                self._live_stream_card.destroy()
            except (RuntimeError, AttributeError):
                pass
            self._live_stream_card = None
        self._streaming_raw_text = ""
        self._streaming_chunks_count = 0
        self._rendered_turns_count = 0

        self.file_entry.delete(0, "end")
        self.file_info_label.configure(
            text="Ready to load document.", text_color=COLOR_TEXT_SECONDARY
        )
        self.text_input_box.delete("1.0", "end")
        self.editable_script_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.progress_pct_label.configure(text="0%")
        self.status_label.configure(text="Ready to generate your podcast.")
        self.grounding_menu.set(GROUNDING_UI_OPTIONS[0])
        self._update_grounding_description()
        self._render_transcript([])

    def show_about_dialog(self):
        """Displays the modal About dialog explaining tech stack, pipeline, and limitations."""
        AboutDialog(self)

    def _on_close(self):
        """Safely cleans up timers, player, and background workers on application exit."""
        self._is_closing = True

        # Cancel pending poller timers
        queue_poll_id = getattr(self, "_queue_poll_id", None)
        if queue_poll_id is not None:
            try:
                self.after_cancel(queue_poll_id)
            except (RuntimeError, AttributeError, ValueError):
                pass
            self._queue_poll_id = None

        player_poll_id = getattr(self, "_player_poll_id", None)
        if player_poll_id is not None:
            try:
                self.after_cancel(player_poll_id)
            except (RuntimeError, AttributeError, ValueError):
                pass
            self._player_poll_id = None

        player = getattr(self, "player", None)
        if player:
            try:
                player.close()
            except (RuntimeError, AttributeError, OSError):
                pass

        # Signal and gracefully join worker threads
        current_worker = getattr(self, "current_worker", None)
        if current_worker and current_worker.is_alive():
            cancel_event = getattr(self, "cancel_event", None)
            if cancel_event:
                cancel_event.set()
            try:
                current_worker.join(timeout=0.1)
            except (RuntimeError, TimeoutError, AttributeError):
                pass

        current_pull_worker = getattr(self, "current_pull_worker", None)
        if current_pull_worker and current_pull_worker.is_alive():
            pull_cancel_event = getattr(self, "pull_cancel_event", None)
            if pull_cancel_event:
                pull_cancel_event.set()
            try:
                current_pull_worker.join(timeout=0.1)
            except (RuntimeError, TimeoutError, AttributeError):
                pass

        current_launcher_worker = getattr(self, "current_launcher_worker", None)
        if current_launcher_worker and current_launcher_worker.is_alive():
            launcher_cancel_event = getattr(self, "launcher_cancel_event", None)
            if launcher_cancel_event:
                launcher_cancel_event.set()
            try:
                current_launcher_worker.join(timeout=0.1)
            except (RuntimeError, TimeoutError, AttributeError):
                pass

        self.destroy()
