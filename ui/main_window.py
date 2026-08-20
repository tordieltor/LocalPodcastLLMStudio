"""
PodcastStudio - Main Window & Asynchronous Pipeline Controller
Universal 100% Local Windows Desktop UI with CustomTkinter Fluent Dark theme,
dedicated non-blocking background worker thread, thread-safe queue event loop,
interactive script studio, integrated native MCI audio player, and actionable error dialogs.
"""

import os
import sys
import json
import time
import queue
import shutil
import tempfile
import threading
from typing import List, Dict, Any, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

# Core Subsystem Imports
from core.extractor import extract_text, extract_text_from_file, DocumentExtractionError
from core.prompts import (
    FORMAT_PRESETS,
    TONE_DESCRIPTIONS,
    normalize_language_code,
)
from core.parser import (
    DialogueTurn,
    DialogueParser,
    dialogue_to_json,
    dialogue_from_json,
    dialogue_to_markdown,
)
from core.ollama import (
    OllamaClient,
    generate_podcast_script,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)
from core.tts import (
    TTSEngine,
    synthesize_dialogue_audio,
    format_rate_str,
)
from core.mp3_stitcher import stitch_mp3_files
from core.player import WindowsAudioPlayer, export_audio_file, format_ms

# UI Theming & Reusable Widgets
from ui.theme import (
    APP_TITLE,
    DEFAULT_WINDOW_SIZE,
    MIN_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    COLOR_BG,
    COLOR_CARD,
    COLOR_CARD_BORDER,
    COLOR_INPUT_BG,
    COLOR_INPUT_BORDER,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED,
    CARD_RADIUS,
    BUTTON_RADIUS,
    PADDING_SM,
    PADDING_MD,
    PADDING_LG,
    get_font_title,
    get_font_subtitle,
    get_font_heading,
    get_font_body,
    get_font_body_bold,
    get_font_caption,
    get_font_code,
    enable_windows_dark_titlebar,
)
from ui.widgets import (
    CardFrame,
    SectionHeader,
    StatusBadge,
    LabeledSlider,
    TimeSlider,
    DialogueTurnCard,
    ActionableErrorDialog,
)


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
        ollama_url: str = "http://localhost:11434"
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
        self.ollama_url = ollama_url
        self.temp_turn_files: List[str] = []

    def run(self):
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            os.makedirs(self.output_dir, exist_ok=True)
            dialogue: List[DialogueTurn] = []

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
                        source=source_content,
                        is_raw_text=is_raw,
                        is_topic=is_topic
                    )
                except DocumentExtractionError as de_err:
                    self.msg_queue.put(("ERROR", {
                        "title": "Document Extraction Error",
                        "message": str(de_err),
                        "details": f"Source: {source_content[:100]}...\nError: {de_err}",
                        "remedy": "Please check that the document contains selectable text (not scanned images) and is not password protected."
                    }))
                    return

                if not extracted_text or len(extracted_text.strip()) < 10:
                    self.msg_queue.put(("ERROR", {
                        "title": "Empty Content",
                        "message": "The provided document or prompt is empty or too short.",
                        "details": "Minimum 10 characters required.",
                        "remedy": "Please provide a document with text or enter a more descriptive topic prompt."
                    }))
                    return

                self.msg_queue.put(("PROGRESS", 0.15))
                self.msg_queue.put(("STATUS", f"Connecting to Ollama ({self.model}) and generating dialogue script..."))

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

                try:
                    dialogue = generate_podcast_script(
                        content=extracted_text,
                        language=self.language,
                        format_type=self.format_type,
                        tone_style=self.tone,
                        model=self.model,
                        ollama_url=self.ollama_url,
                        is_topic=is_topic,
                        cancel_event=self.cancel_event,
                        progress_callback=progress_cb
                    )
                except OllamaConnectionError as oc_err:
                    self.msg_queue.put(("ERROR", {
                        "title": "Ollama Connection Error",
                        "message": "Could not connect to Ollama local service.",
                        "details": str(oc_err),
                        "remedy": "Ensure Ollama is running ('ollama serve' in terminal or Windows tray app) and click Refresh (↻)."
                    }))
                    return
                except OllamaModelNotFoundError as mnf_err:
                    self.msg_queue.put(("ERROR", {
                        "title": "Ollama Model Missing",
                        "message": f"Requested model '{self.model}' is not installed.",
                        "details": str(mnf_err),
                        "remedy": f"Open terminal and run: 'ollama pull {self.model}', then refresh the model list."
                    }))
                    return

                if self.cancel_event.is_set():
                    self.msg_queue.put(("CANCELLED", "Generation cancelled by user."))
                    return

                if not dialogue:
                    self.msg_queue.put(("ERROR", {
                        "title": "Script Parsing Failed",
                        "message": "Failed to parse a structured dialogue script from the model's output.",
                        "details": "The model response did not contain valid dialogue turns.",
                        "remedy": "Try selecting a more capable model (e.g., llama3.1:8b or qwen2.5:7b) and try again."
                    }))
                    return

                # Send script to UI
                self.msg_queue.put(("SCRIPT_READY", dialogue))
                self.msg_queue.put(("PROGRESS", 0.40))

                # Save script files to output folder (.json and .md)
                script_json_path = os.path.join(self.output_dir, f"podcast_script_{timestamp}.json")
                with open(script_json_path, "w", encoding="utf-8") as f:
                    f.write(dialogue_to_json(dialogue))

                script_md_path = os.path.join(self.output_dir, f"podcast_transcript_{timestamp}.md")
                with open(script_md_path, "w", encoding="utf-8") as f:
                    f.write(dialogue_to_markdown(dialogue))

                if self.mode == "script_only":
                    self.msg_queue.put(("PROGRESS", 1.0))
                    self.msg_queue.put(("STATUS", f"Script generated successfully! ({len(dialogue)} turns)"))
                    self.msg_queue.put(("SCRIPT_ONLY_DONE", {
                        "script_path": script_json_path,
                        "script_md_path": script_md_path,
                        "dialogue": dialogue
                    }))
                    return

            else:
                # Mode: audio_from_script
                dialogue = self.input_data
                self.msg_queue.put(("PROGRESS", 0.40))

            # ------------------------------------------------------------------
            # Phase 2: Edge-TTS Neural Voice Synthesis
            # ------------------------------------------------------------------
            if self.cancel_event.is_set():
                self.msg_queue.put(("CANCELLED", "Generation cancelled before audio synthesis."))
                return

            self.msg_queue.put(("STATUS", "Synthesizing neural voices with Edge-TTS..."))
            total_turns = len(dialogue)

            def tts_progress_cb(curr: int, tot: int):
                if not self.cancel_event.is_set():
                    # Map progress range: 40% -> 90%
                    pct = 0.40 + (0.50 * (curr / max(1, tot)))
                    turn_speaker = dialogue[curr - 1].speaker if curr <= len(dialogue) else "Host"
                    self.msg_queue.put(("PROGRESS", pct))
                    self.msg_queue.put(("STATUS", f"Synthesizing turn {curr}/{tot} ({turn_speaker})..."))

            temp_tts_dir = tempfile.mkdtemp(prefix="podcaststudio_tts_")

            try:
                self.temp_turn_files = synthesize_dialogue_audio(
                    dialogue=dialogue,
                    language=self.language,
                    rate=self.speed_rate,
                    output_dir=temp_tts_dir,
                    progress_cb=tts_progress_cb,
                    cancel_event=self.cancel_event
                )
            except Exception as tts_err:
                # Clean up temp files
                self._cleanup_temp_dir(temp_tts_dir)
                if self.cancel_event.is_set():
                    self.msg_queue.put(("CANCELLED", "Audio synthesis cancelled by user."))
                    return
                self.msg_queue.put(("ERROR", {
                    "title": "Voice Synthesis Error",
                    "message": f"Edge-TTS synthesis encountered an error: {tts_err}",
                    "details": str(tts_err),
                    "remedy": "Please check your internet connection for Microsoft Edge-TTS voice generation."
                }))
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
                    artist="PodcastStudio"
                )
            except Exception as stitch_err:
                self._cleanup_temp_dir(temp_tts_dir)
                self.msg_queue.put(("ERROR", {
                    "title": "MP3 Stitching Error",
                    "message": f"Failed to stitch MP3 audio frames: {stitch_err}",
                    "details": str(stitch_err),
                    "remedy": "Check write permissions in the output directory."
                }))
                return

            # Clean up temporary turn files
            self._cleanup_temp_dir(temp_tts_dir)

            # ------------------------------------------------------------------
            # Phase 4: Completion & Readiness
            # ------------------------------------------------------------------
            self.msg_queue.put(("PROGRESS", 1.0))
            self.msg_queue.put(("STATUS", f"Ready! Master podcast generated: {os.path.basename(output_mp3_path)}"))
            self.msg_queue.put(("GENERATION_DONE", {
                "mp3_path": output_mp3_path,
                "script_path": os.path.join(self.output_dir, f"podcast_script_{timestamp}.json"),
                "dialogue": dialogue
            }))

        except Exception as unhandled_err:
            self.msg_queue.put(("ERROR", {
                "title": "Unexpected Pipeline Error",
                "message": str(unhandled_err),
                "details": str(unhandled_err),
                "remedy": "Please review the error details and try again."
            }))

    def _cleanup_temp_dir(self, temp_dir: str):
        """Recursively cleans temporary turn files."""
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


# ==============================================================================
# Main Application Window
# ==============================================================================
class MainWindow(ctk.CTk):
    """
    Windows 11 Fluent Dark CustomTkinter Main Application Window.
    Coordinates UI layouts, background worker thread dispatch, polling queue,
    interactive script editing, and native MCI audio playback.
    """

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
        self.current_worker: Optional[GenerationWorker] = None

        # Data & Playback State
        self.current_dialogue: List[DialogueTurn] = []
        self.current_mp3_path: Optional[str] = None
        self.current_script_path: Optional[str] = None
        self.player: WindowsAudioPlayer = WindowsAudioPlayer()
        self.is_busy: bool = False

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
        header_card = CardFrame(self, height=65, corner_radius=0, border_width=0, fg_color="#1f2335")
        header_card.pack(fill="x", padx=0, pady=(0, 10))

        inner_header = ctk.CTkFrame(header_card, fg_color="transparent")
        inner_header.pack(fill="both", expand=True, padx=20, pady=10)

        # Title & Subtitle Group
        title_group = ctk.CTkFrame(inner_header, fg_color="transparent")
        title_group.pack(side="left")

        app_title = ctk.CTkLabel(
            title_group,
            text="🎙️ PodcastStudio",
            font=get_font_title(),
            text_color=COLOR_ACCENT
        )
        app_title.pack(side="left")

        subtitle = ctk.CTkLabel(
            title_group,
            text="100% Local AI Two-Host Podcast Generator",
            font=get_font_subtitle(),
            text_color=COLOR_TEXT_SECONDARY
        )
        subtitle.pack(side="left", padx=(14, 0), pady=(3, 0))

        # Right Header: Ollama Status Badge + Refresh Button
        status_group = ctk.CTkFrame(inner_header, fg_color="transparent")
        status_group.pack(side="right")

        self.ollama_badge = StatusBadge(
            status_group,
            initial_status="checking",
            initial_text="Checking Ollama..."
        )
        self.ollama_badge.pack(side="left", padx=(0, 8))

        self.btn_refresh_models = ctk.CTkButton(
            status_group,
            text="↻ Refresh",
            width=80,
            height=30,
            font=get_font_caption(),
            fg_color="#2b314a",
            hover_color="#3d4566",
            command=self.refresh_ollama_models
        )
        self.btn_refresh_models.pack(side="left")

    # ==========================================================================
    # Main 2-Column Responsive Layout
    # ==========================================================================
    def _build_main_layout(self):
        main_grid = ctk.CTkFrame(self, fg_color="transparent")
        main_grid.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        main_grid.grid_columnconfigure(0, weight=4, minsize=480)
        main_grid.grid_columnconfigure(1, weight=6, minsize=560)
        main_grid.grid_rowconfigure(0, weight=1)

        # Left Column: Input & Configuration Card
        self.left_panel = CardFrame(main_grid)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        self._build_left_panel(self.left_panel)

        # Right Column: Progress, Script Studio, and Audio Player Card
        self.right_panel = CardFrame(main_grid)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        self._build_right_panel(self.right_panel)

    # ==========================================================================
    # Left Column: Input & Configuration Controls
    # ==========================================================================
    def _build_left_panel(self, parent: CardFrame):
        scroll_container = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_container.pack(fill="both", expand=True, padx=12, pady=12)

        # --- Section 1: Ingestion Source ---
        SectionHeader(
            scroll_container,
            title="Ingestion Source",
            subtitle="Choose source document, paste text, or write a topic prompt",
            icon="📄"
        ).pack(fill="x", pady=(0, 10))

        self.input_modality_var = ctk.StringVar(value="file")
        self.modality_segmented = ctk.CTkSegmentedButton(
            scroll_container,
            values=["Document (.txt/.md/.pdf)", "Pasted Text", "Topic Prompt (Scratch)"],
            command=self._on_modality_changed
        )
        self.modality_segmented.set("Document (.txt/.md/.pdf)")
        self.modality_segmented.pack(fill="x", pady=(0, 10))

        # File Input Container
        self.file_container = ctk.CTkFrame(scroll_container, fg_color="transparent")
        self.file_container.pack(fill="x", pady=(0, 12))

        file_row = ctk.CTkFrame(self.file_container, fg_color="transparent")
        file_row.pack(fill="x")
        self.file_entry = ctk.CTkEntry(
            file_row,
            placeholder_text="Select a .txt, .md, or .pdf file...",
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER
        )
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.btn_browse_file = ctk.CTkButton(
            file_row,
            text="Browse...",
            width=80,
            fg_color="#33384d",
            hover_color="#414868",
            command=self._browse_input_file
        )
        self.btn_browse_file.pack(side="right")

        self.file_info_label = ctk.CTkLabel(
            self.file_container,
            text="Ready to load document.",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w"
        )
        self.file_info_label.pack(anchor="w", pady=(4, 0))

        # Text & Topic Prompt Textbox Container
        self.text_container = ctk.CTkFrame(scroll_container, fg_color="transparent")
        self.text_input_box = ctk.CTkTextbox(
            self.text_container,
            height=120,
            font=get_font_body(),
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            border_width=1
        )
        self.text_input_box.pack(fill="both", expand=True)

        # --- Section 2: Podcast & Voice Configuration ---
        SectionHeader(
            scroll_container,
            title="Podcast & Voice Configuration",
            subtitle="Target language, personas, Ollama model, length, tone and rate",
            icon="⚙️"
        ).pack(fill="x", pady=(14, 10))

        cfg_grid = ctk.CTkFrame(scroll_container, fg_color="transparent")
        cfg_grid.pack(fill="x", pady=(0, 10))
        cfg_grid.grid_columnconfigure(1, weight=1)

        # Language Selector
        ctk.CTkLabel(cfg_grid, text="Language:", font=get_font_body(), text_color=COLOR_TEXT_PRIMARY).grid(
            row=0, column=0, sticky="w", pady=6
        )
        self.lang_menu = ctk.CTkOptionMenu(
            cfg_grid,
            values=["Norwegian Bokmål (Kari & Ola)", "English (Jenny & Guy)"],
            fg_color="#2b314a",
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER
        )
        self.lang_menu.set("Norwegian Bokmål (Kari & Ola)")
        self.lang_menu.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=6)

        # Ollama Model Dropdown
        ctk.CTkLabel(cfg_grid, text="Ollama Model:", font=get_font_body(), text_color=COLOR_TEXT_PRIMARY).grid(
            row=1, column=0, sticky="w", pady=6
        )
        model_row = ctk.CTkFrame(cfg_grid, fg_color="transparent")
        model_row.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=6)
        self.model_menu = ctk.CTkOptionMenu(
            model_row,
            values=["Checking models..."],
            fg_color="#2b314a",
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER
        )
        self.model_menu.pack(side="left", fill="x", expand=True)

        # Episode Length Preset
        ctk.CTkLabel(cfg_grid, text="Episode Length:", font=get_font_body(), text_color=COLOR_TEXT_PRIMARY).grid(
            row=2, column=0, sticky="w", pady=6
        )
        self.length_menu = ctk.CTkOptionMenu(
            cfg_grid,
            values=[
                "Quick Summary (6-8 turns, ~2-3 min)",
                "Standard Episode (12-16 turns, ~5-7 min)",
                "Deep Dive (20-26 turns, ~10-15 min)",
                "Extended In-Depth (45-60 turns, ~25-30 min)"
            ],
            fg_color="#2b314a",
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER
        )
        self.length_menu.set("Standard Episode (12-16 turns, ~5-7 min)")
        self.length_menu.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=6)

        # Tone / Style Preset
        ctk.CTkLabel(cfg_grid, text="Tone / Style:", font=get_font_body(), text_color=COLOR_TEXT_PRIMARY).grid(
            row=3, column=0, sticky="w", pady=6
        )
        self.tone_menu = ctk.CTkOptionMenu(
            cfg_grid,
            values=["Casual & Lively", "Analytical & Educational", "Lively Debate"],
            fg_color="#2b314a",
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER
        )
        self.tone_menu.set("Casual & Lively")
        self.tone_menu.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=6)

        # Voice Speaking Rate Slider (-10% to +15%)
        self.speed_slider = LabeledSlider(
            scroll_container,
            label="Speaking Speed:",
            from_=-10.0,
            to=15.0,
            number_of_steps=5,
            default_value=0.0
        )
        self.speed_slider.pack(fill="x", pady=(4, 10))

        # Output Folder Selector
        out_header = ctk.CTkFrame(scroll_container, fg_color="transparent")
        out_header.pack(fill="x", pady=(4, 4))
        ctk.CTkLabel(out_header, text="Output Directory:", font=get_font_body(), text_color=COLOR_TEXT_PRIMARY).pack(
            side="left"
        )

        out_row = ctk.CTkFrame(scroll_container, fg_color="transparent")
        out_row.pack(fill="x", pady=(0, 14))
        self.output_entry = ctk.CTkEntry(
            out_row,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER
        )
        default_out = os.path.abspath(os.path.join(os.getcwd(), "output"))
        self.output_entry.insert(0, default_out)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_browse_output = ctk.CTkButton(
            out_row,
            text="Browse...",
            width=80,
            fg_color="#33384d",
            hover_color="#414868",
            command=self._browse_output_dir
        )
        self.btn_browse_output.pack(side="right")

        # --- Section 3: Action Buttons ---
        SectionHeader(
            scroll_container,
            title="Generate & Actions",
            icon="🚀"
        ).pack(fill="x", pady=(6, 10))

        # Primary Action: Generate Full Podcast
        self.btn_generate_full = ctk.CTkButton(
            scroll_container,
            text="🎙️ Generate Full Podcast (Script + Audio)",
            height=44,
            font=get_font_body_bold(),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            command=lambda: self.start_generation(mode="full")
        )
        self.btn_generate_full.pack(fill="x", pady=(0, 8))

        # Secondary Action: Generate Script Only
        self.btn_generate_script = ctk.CTkButton(
            scroll_container,
            text="📝 Generate Script Only",
            height=36,
            font=get_font_body(),
            fg_color="#2b314a",
            hover_color="#3d4566",
            command=lambda: self.start_generation(mode="script_only")
        )
        self.btn_generate_script.pack(fill="x", pady=(0, 8))

        # Control Row: Cancel and Reset
        ctrl_row = ctk.CTkFrame(scroll_container, fg_color="transparent")
        ctrl_row.pack(fill="x", pady=(0, 8))

        self.btn_cancel = ctk.CTkButton(
            ctrl_row,
            text="⏹️ Cancel",
            font=get_font_body(),
            fg_color=COLOR_ERROR,
            hover_color="#db4b4b",
            state="disabled",
            command=self.cancel_generation
        )
        self.btn_cancel.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_reset = ctk.CTkButton(
            ctrl_row,
            text="🔄 Reset",
            font=get_font_body(),
            fg_color="#33384d",
            hover_color="#414868",
            command=self.reset_form
        )
        self.btn_reset.pack(side="right", fill="x", expand=True, padx=(4, 0))

    # ==========================================================================
    # Right Column: Progress, Interactive Script Studio & Audio Player
    # ==========================================================================
    def _build_right_panel(self, parent: CardFrame):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=14, pady=14)

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
            anchor="w"
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.progress_pct_label = ctk.CTkLabel(
            status_top,
            text="0%",
            font=get_font_caption(),
            text_color=COLOR_TEXT_SECONDARY
        )
        self.progress_pct_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            status_box,
            height=10,
            progress_color=COLOR_ACCENT,
            fg_color="#24283b"
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 10))

        # --- Section 2: Interactive Script Studio ---
        studio_header_row = ctk.CTkFrame(container, fg_color="transparent")
        studio_header_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            studio_header_row,
            text="Interactive Script Studio",
            font=get_font_heading(),
            text_color=COLOR_TEXT_PRIMARY
        ).pack(side="left")

        # Tabview for Formatted Dialogue vs. Editable Script
        self.script_tabs = ctk.CTkTabview(
            container,
            fg_color="#1a1c29",
            segmented_button_selected_color=COLOR_ACCENT,
            segmented_button_selected_hover_color=COLOR_ACCENT_HOVER
        )
        self.script_tabs.pack(fill="both", expand=True, pady=(0, 8))
        self.tab_formatted = self.script_tabs.add("Formatted Dialogue")
        self.tab_editable = self.script_tabs.add("Editable Script")

        # Formatted Dialogue Tab
        self.formatted_scroll = ctk.CTkScrollableFrame(self.tab_formatted, fg_color="transparent")
        self.formatted_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        self.empty_script_placeholder = ctk.CTkLabel(
            self.formatted_scroll,
            text="No dialogue script generated yet.\nGenerate a script to preview turns here.",
            font=get_font_body(),
            text_color=COLOR_TEXT_MUTED
        )
        self.empty_script_placeholder.pack(pady=40)

        # Editable Script Tab
        self.editable_script_box = ctk.CTkTextbox(
            self.tab_editable,
            font=get_font_code(),
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            border_width=1,
            text_color=COLOR_TEXT_PRIMARY
        )
        self.editable_script_box.pack(fill="both", expand=True, padx=4, pady=4)

        # Script Action Bar
        script_bar = ctk.CTkFrame(container, fg_color="transparent")
        script_bar.pack(fill="x", pady=(0, 10))

        self.btn_copy_script = ctk.CTkButton(
            script_bar,
            text="📋 Copy Script",
            width=100,
            fg_color="#2b314a",
            hover_color="#3d4566",
            font=get_font_caption(),
            command=self._copy_script_to_clipboard
        )
        self.btn_copy_script.pack(side="left", padx=(0, 6))

        self.btn_save_script_as = ctk.CTkButton(
            script_bar,
            text="💾 Save Script As...",
            width=120,
            fg_color="#2b314a",
            hover_color="#3d4566",
            font=get_font_caption(),
            command=self._save_script_as
        )
        self.btn_save_script_as.pack(side="left", padx=(0, 6))

        self.btn_synth_from_script = ctk.CTkButton(
            script_bar,
            text="🔊 Synthesize Audio from Script",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            font=get_font_body_bold(),
            command=self._synthesize_from_edited_script
        )
        self.btn_synth_from_script.pack(side="right")

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
            anchor="w"
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
            fg_color="#2b314a",
            hover_color="#3d4566",
            command=self._play_audio
        )
        self.btn_play.pack(side="left", padx=(0, 4))

        self.btn_pause = ctk.CTkButton(
            ctrl_bar,
            text="⏸ Pause",
            width=70,
            state="disabled",
            fg_color="#2b314a",
            hover_color="#3d4566",
            command=self._pause_audio
        )
        self.btn_pause.pack(side="left", padx=(0, 4))

        self.btn_stop = ctk.CTkButton(
            ctrl_bar,
            text="⏹ Stop",
            width=70,
            state="disabled",
            fg_color="#2b314a",
            hover_color="#3d4566",
            command=self._stop_audio
        )
        self.btn_stop.pack(side="left", padx=(0, 10))

        # Volume Slider
        ctk.CTkLabel(ctrl_bar, text="Vol:", font=get_font_caption(), text_color=COLOR_TEXT_SECONDARY).pack(
            side="left", padx=(0, 4)
        )
        self.volume_slider = ctk.CTkSlider(
            ctrl_bar,
            from_=0,
            to=100,
            width=90,
            button_color=COLOR_ACCENT,
            command=self._on_volume_changed
        )
        self.volume_slider.set(80)
        self.volume_slider.pack(side="left", padx=(0, 10))

        # Export & Folder buttons
        self.btn_export_mp3 = ctk.CTkButton(
            ctrl_bar,
            text="💾 Save MP3 As...",
            width=110,
            state="disabled",
            fg_color="#33384d",
            hover_color="#414868",
            font=get_font_caption(),
            command=self._save_mp3_as
        )
        self.btn_export_mp3.pack(side="right", padx=(4, 0))

        self.btn_open_folder = ctk.CTkButton(
            ctrl_bar,
            text="📁 Open Folder",
            width=100,
            fg_color="#33384d",
            hover_color="#414868",
            font=get_font_caption(),
            command=self._open_output_folder
        )
        self.btn_open_folder.pack(side="right")

    # ==========================================================================
    # Modality & Input Handlers
    # ==========================================================================
    def _on_modality_changed(self, value: str):
        if "Document" in value:
            self.input_modality_var.set("file")
            self.text_container.pack_forget()
            self.file_container.pack(fill="x", pady=(0, 12))
        elif "Pasted" in value:
            self.input_modality_var.set("text")
            self.file_container.pack_forget()
            self.text_container.pack(fill="both", expand=True, pady=(0, 12))
        else:  # Topic Prompt (Scratch)
            self.input_modality_var.set("topic")
            self.file_container.pack_forget()
            self.text_container.pack(fill="both", expand=True, pady=(0, 12))

    def _browse_input_file(self):
        filetypes = [
            ("Supported Documents", "*.txt;*.md;*.pdf"),
            ("Text Files (*.txt)", "*.txt"),
            ("Markdown Files (*.md)", "*.md"),
            ("PDF Documents (*.pdf)", "*.pdf"),
            ("All Files", "*.*")
        ]
        chosen = filedialog.askopenfilename(filetypes=filetypes)
        if chosen:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, chosen)
            try:
                size_kb = os.path.getsize(chosen) / 1024
                self.file_info_label.configure(
                    text=f"Selected: {os.path.basename(chosen)} ({size_kb:.1f} KB)",
                    text_color=COLOR_SUCCESS
                )
            except Exception:
                self.file_info_label.configure(text=f"Selected: {os.path.basename(chosen)}")

    def _browse_output_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.output_entry.get())
        if chosen:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, os.path.abspath(chosen))

    # ==========================================================================
    # Ollama Model Discovery (Non-Blocking)
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
            except Exception as err:
                self.msg_queue.put(("OLLAMA_STATUS", {"connected": False, "models": [], "error": str(err)}))

        threading.Thread(target=_bg_fetch, daemon=True).start()

    def _handle_ollama_status(self, data: Dict[str, Any]):
        self.btn_refresh_models.configure(state="normal")
        if data.get("connected") and data.get("models"):
            models = data["models"]
            self.model_menu.configure(values=models)

            # Smart preferred model selection
            preferred_order = [
                "llama3.1:8b", "mistral-nemo:latest", "qwen2.5:7b",
                "llama3:8b", "mistral:latest", "gemma2:9b", "phi3:medium"
            ]
            selected = models[0]
            for pref in preferred_order:
                matched = [m for m in models if pref in m]
                if matched:
                    selected = matched[0]
                    break
            self.model_menu.set(selected)
            self.ollama_badge.set_status("online", f"Ollama Connected ({len(models)} models)")
        else:
            self.model_menu.configure(values=["Ollama Offline (No models)"])
            self.model_menu.set("Ollama Offline (No models)")
            self.ollama_badge.set_status("offline", "Ollama Offline")

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
                    remedy="Click 'Browse...' in the left panel to choose a file."
                )
                return
            source_data = file_path
        else:
            text_data = self.text_input_box.get("1.0", "end-1c").strip()
            if not text_data:
                ActionableErrorDialog(
                    self,
                    title="Input Required",
                    message="Please enter some text or a topic prompt description in the input box."
                )
                return
            source_data = text_data

        selected_model = self.model_menu.get()
        if "Offline" in selected_model or "Checking" in selected_model or not selected_model:
            ActionableErrorDialog(
                self,
                title="Ollama Service Required",
                message="Local Ollama is offline or no models were found.\n\nPlease start Ollama and ensure you have pulled a model.",
                details="Run 'ollama serve' in terminal or launch Ollama from Windows tray.\nRun 'ollama pull llama3.1:8b' to install a model.",
                action_button_text="Refresh Ollama",
                action_callback=self.refresh_ollama_models
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

        # Prepare Worker
        self.cancel_event.clear()
        self._set_busy_state(True)
        self.progress_bar.set(0.02)
        self.status_label.configure(text="Initializing generation pipeline...")

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
            cancel_event=self.cancel_event
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
        raw_text = self.editable_script_box.get("1.0", "end-1c").strip()
        if not raw_text:
            ActionableErrorDialog(
                self,
                title="Empty Script",
                message="No dialogue script content found in the editor to synthesize."
            )
            return

        dialogue_turns: List[DialogueTurn] = []
        # Attempt JSON parsing first, then fallback to multi-tier dialogue parsing
        try:
            parsed_json = json.loads(raw_text)
            if isinstance(parsed_json, list):
                dialogue_turns = [
                    DialogueTurn(speaker=t.get("speaker", "Host 1"), text=t.get("text", ""))
                    for t in parsed_json if isinstance(t, dict)
                ]
        except Exception:
            pass

        if not dialogue_turns:
            dialogue_turns = DialogueParser.parse(raw_text)

        if not dialogue_turns:
            ActionableErrorDialog(
                self,
                title="Invalid Script Format",
                message="Could not parse dialogue turns from the script box.",
                details="Please ensure dialogue turns follow JSON or 'Host 1: ...' format."
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
            cancel_event=self.cancel_event
        )
        self.current_worker.start()

    # ==========================================================================
    # Queue Poller & Event Dispatch Loop
    # ==========================================================================
    def _start_queue_poller(self):
        self._process_queue()
        self.after(50, self._start_queue_poller)

    def _process_queue(self):
        while not self.msg_queue.empty():
            try:
                event_type, payload = self.msg_queue.get_nowait()
                self._handle_event(event_type, payload)
                self.msg_queue.task_done()
            except queue.Empty:
                break

    def _handle_event(self, event_type: str, payload: Any):
        if event_type == "STATUS":
            self.status_label.configure(text=str(payload))
        elif event_type == "PROGRESS":
            pct = float(payload)
            self.progress_bar.set(pct)
            self.progress_pct_label.configure(text=f"{int(pct * 100)}%")
        elif event_type == "SCRIPT_READY":
            self._render_transcript(payload)
        elif event_type == "GENERATION_DONE":
            self._on_generation_done(payload)
        elif event_type == "SCRIPT_ONLY_DONE":
            self._on_script_only_done(payload)
        elif event_type == "OLLAMA_STATUS":
            self._handle_ollama_status(payload)
        elif event_type == "CANCELLED":
            self._set_busy_state(False)
            self.status_label.configure(text=str(payload))
            self.progress_bar.set(0.0)
            self.progress_pct_label.configure(text="0%")
        elif event_type == "ERROR":
            self._set_busy_state(False)
            self.status_label.configure(text="Error encountered.")
            if isinstance(payload, dict):
                ActionableErrorDialog(
                    self,
                    title=payload.get("title", "Error"),
                    message=payload.get("message", "An error occurred."),
                    details=payload.get("details"),
                    action_button_text="Dismiss"
                )
            else:
                messagebox.showerror("Error", str(payload))

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

    def _render_transcript(self, dialogue: List[DialogueTurn]):
        self.current_dialogue = dialogue

        # Clear existing formatted dialogue cards
        for widget in self.formatted_scroll.winfo_children():
            widget.destroy()

        if not dialogue:
            self.empty_script_placeholder = ctk.CTkLabel(
                self.formatted_scroll,
                text="No dialogue turns available.",
                font=get_font_body(),
                text_color=COLOR_TEXT_MUTED
            )
            self.empty_script_placeholder.pack(pady=40)
            return

        for idx, turn in enumerate(dialogue, start=1):
            turn_card = DialogueTurnCard(
                self.formatted_scroll,
                turn_number=idx,
                speaker=turn.speaker,
                text=turn.text
            )
            turn_card.pack(fill="x", pady=4)

        # Update Editable Script Box with JSON representation
        self.editable_script_box.delete("1.0", "end")
        self.editable_script_box.insert("1.0", dialogue_to_json(dialogue))

    def _on_generation_done(self, result: Dict[str, Any]):
        self._set_busy_state(False)
        self.current_mp3_path = result.get("mp3_path")
        self.current_script_path = result.get("script_path")

        if self.current_mp3_path and os.path.exists(self.current_mp3_path):
            self.player_title_label.configure(
                text=f"Loaded: {os.path.basename(self.current_mp3_path)}"
            )
            self.player.open(self.current_mp3_path)
            self.btn_play.configure(state="normal")
            self.btn_pause.configure(state="normal")
            self.btn_stop.configure(state="normal")
            self.btn_export_mp3.configure(state="normal")

            # Update initial time slider
            tot_ms = self.player.get_length()
            self.time_slider.update_position(0, tot_ms, "Loaded")

    def _on_script_only_done(self, result: Dict[str, Any]):
        self._set_busy_state(False)
        self.current_script_path = result.get("script_path")
        messagebox.showinfo(
            "Script Ready",
            f"Podcast dialogue script generated successfully!\n\nSaved to: {os.path.basename(str(self.current_script_path))}"
        )

    # ==========================================================================
    # Audio Player & MCI Integration
    # ==========================================================================
    def _start_player_poller(self):
        self._update_player_position()
        self.after(250, self._start_player_poller)

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
            initialfile=os.path.basename(self.current_mp3_path)
        )
        if dest:
            try:
                export_audio_file(self.current_mp3_path, dest)
                messagebox.showinfo("Export Successful", f"Master podcast exported to:\n{dest}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Could not export MP3: {e}")

    def _open_output_folder(self):
        out_dir = self.output_entry.get().strip() or os.path.abspath("./output")
        os.makedirs(out_dir, exist_ok=True)
        if sys.platform == "win32":
            try:
                os.startfile(out_dir)
            except Exception:
                pass

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
                ("Plain Text", "*.txt")
            ],
            initialfile="podcast_dialogue.json"
        )
        if dest:
            try:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(text)
                messagebox.showinfo("Saved", f"Script saved to:\n{dest}")
            except Exception as e:
                messagebox.showerror("Save Failed", f"Could not save script: {e}")

    def reset_form(self):
        """Clears inputs and resets view."""
        self.file_entry.delete(0, "end")
        self.file_info_label.configure(text="Ready to load document.", text_color=COLOR_TEXT_SECONDARY)
        self.text_input_box.delete("1.0", "end")
        self.editable_script_box.delete("1.0", "end")
        self.progress_bar.set(0.0)
        self.progress_pct_label.configure(text="0%")
        self.status_label.configure(text="Ready to generate your podcast.")
        self._render_transcript([])

    def _on_close(self):
        """Safely cleans up player and background workers on application exit."""
        if self.player:
            self.player.close()
        if self.current_worker and self.current_worker.is_alive():
            self.cancel_event.set()
        self.destroy()
