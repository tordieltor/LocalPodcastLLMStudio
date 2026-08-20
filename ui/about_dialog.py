"""
LocalPodcastLLMStudio - About Dialog Window
Modern Fluent Dark modal dialog providing comprehensive information on the
technology stack, how the pipeline works, and system limitations/prerequisites.
"""

from typing import Any

import customtkinter as ctk

from ui.theme import (
    CARD_RADIUS,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_BG,
    COLOR_CARD,
    COLOR_CARD_BORDER,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    get_font_body,
    get_font_body_bold,
    get_font_caption,
    get_font_heading,
    get_font_title,
)


class AboutDialog(ctk.CTkToplevel):
    """
    Windows 11 Fluent Dark modal window explaining the architecture,
    technology components, end-to-end pipeline, and limitations.
    """

    def __init__(self, parent: Any):
        super().__init__(parent)

        self.title("About LocalPodcastLLMStudio")
        self.geometry("740x620")
        self.minsize(680, 540)
        self.configure(fg_color=COLOR_BG)

        # Modal focus configuration
        self.transient(parent)
        self.grab_set()

        # Center on parent window if available
        self._center_on_parent(parent)

        # Build UI Sections
        self._build_header()
        self._build_tabview()
        self._build_footer()

    def _center_on_parent(self, parent: Any):
        """Centers dialog relative to parent geometry."""
        try:
            parent.update_idletasks()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()

            w = 740
            h = 620
            x = max(50, px + (pw - w) // 2)
            y = max(50, py + (ph - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    # ==========================================================================
    # Header Section
    # ==========================================================================
    def _build_header(self):
        header_card = ctk.CTkFrame(
            self, fg_color="#1f2335", corner_radius=0, border_width=0, height=85
        )
        header_card.pack(fill="x", padx=0, pady=(0, 10))

        inner = ctk.CTkFrame(header_card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=12)

        # Icon & Title Group
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x")

        title_label = ctk.CTkLabel(
            top_row, text="🎙️ LocalPodcastLLMStudio", font=get_font_title(), text_color=COLOR_ACCENT
        )
        title_label.pack(side="left")

        version_badge = ctk.CTkLabel(
            top_row,
            text=" v1.0.0 • Standalone Executable ",
            font=get_font_caption(),
            text_color="#7aa2f7",
            fg_color="#24283b",
            corner_radius=6,
        )
        version_badge.pack(side="left", padx=(12, 0), pady=(3, 0))

        # Tagline
        subtitle_label = ctk.CTkLabel(
            inner,
            text="100% Local AI Two-Host Podcast Generator • Zero Cloud API Cost",
            font=get_font_body(),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        subtitle_label.pack(anchor="w", fill="x", pady=(4, 0))

    # ==========================================================================
    # Tabview Content Section
    # ==========================================================================
    def _build_tabview(self):
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=COLOR_CARD,
            segmented_button_selected_color=COLOR_ACCENT,
            segmented_button_selected_hover_color=COLOR_ACCENT_HOVER,
            corner_radius=CARD_RADIUS,
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # Create Tabs
        tab_tech = self.tabview.add("⚙️ Tech Stack")
        tab_pipeline = self.tabview.add("🔄 How It Works")
        tab_limits = self.tabview.add("⚠️ Limitations & Requirements")

        self._populate_tech_tab(tab_tech)
        self._populate_pipeline_tab(tab_pipeline)
        self._populate_limits_tab(tab_limits)

    # --------------------------------------------------------------------------
    # Tab 1: Tech Stack
    # --------------------------------------------------------------------------
    def _populate_tech_tab(self, parent: Any):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=6)

        tech_items = [
            (
                "🧠 Local LLM Dialogue Engine",
                "Ollama REST API (http://localhost:11434)",
                "Generates engaging, dynamic two-host podcast conversations entirely on your local machine with complete privacy and zero API costs. Compatible with Llama 3.1, Qwen 2.5, Mistral, Gemma 2, and Phi-3 models.",
                COLOR_ACCENT,
            ),
            (
                "🗣️ Neural Text-to-Speech (TTS)",
                "Microsoft Edge-TTS Async Engine",
                "Provides ultra-natural, multi-speaker neural voice synthesis. Features native Norwegian Bokmål (Kari / Finn & Pernille) and American English (Jenny & Guy) voices with adjustable speaking rates (-10% to +15%).",
                COLOR_SUCCESS,
            ),
            (
                "🎵 Zero-FFmpeg MP3 Stitcher",
                "Pure Python Binary MPEG Frame Stitcher",
                "Concatenates individual turn audio files into a unified master MP3 without requiring FFmpeg or external binaries. Automatically strips ID3v2 tags, aligns MPEG audio frames, and injects natural 350ms silence intervals.",
                COLOR_WARNING,
            ),
            (
                "🖥️ Fluent Dark Desktop Interface",
                "CustomTkinter & Windows 11 DWM Integration",
                "Modern, responsive Windows 11 Fluent Dark UI (Tokyo Night palette) with asynchronous background worker threads, thread-safe FIFO message queues, live progress tracking, and immersive dark title bar support.",
                COLOR_INFO,
            ),
            (
                "📻 Native Audio Playback Engine",
                "Microsoft Windows MCI (winmm.dll)",
                "Integrated, lightweight Windows Media Control Interface audio player. Supports instant play, pause, resume, timeline scrubbing, volume adjustments, and direct MP3 export.",
                COLOR_ACCENT,
            ),
            (
                "📄 Multi-Format Document Ingestion",
                "pypdf & Multi-Encoding Fallback Loader",
                "Extracts and normalizes text from .txt, .md, and .pdf documents with automatic encoding detection (UTF-8, UTF-8-BOM, CP1252, Latin-1), de-hyphenation, and whitespace cleanup.",
                COLOR_TEXT_PRIMARY,
            ),
        ]

        for title, subtitle, desc, accent in tech_items:
            card = ctk.CTkFrame(
                scroll,
                fg_color="#1a1c29",
                corner_radius=8,
                border_color=COLOR_CARD_BORDER,
                border_width=1,
            )
            card.pack(fill="x", pady=5)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=12, pady=(10, 2))

            ctk.CTkLabel(
                header, text=title, font=get_font_heading(), text_color=accent, anchor="w"
            ).pack(side="left")

            ctk.CTkLabel(
                header,
                text=subtitle,
                font=get_font_caption(),
                text_color=COLOR_TEXT_SECONDARY,
                anchor="e",
            ).pack(side="right")

            ctk.CTkLabel(
                card,
                text=desc,
                font=get_font_body(),
                text_color=COLOR_TEXT_PRIMARY,
                wraplength=640,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 10))

    # --------------------------------------------------------------------------
    # Tab 2: How It Works
    # --------------------------------------------------------------------------
    def _populate_pipeline_tab(self, parent: Any):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=6)

        steps = [
            (
                "1. Document Ingestion & Preparation",
                "The application extracts text from uploaded PDF, Markdown, or Text files, pasted clipboard content, or user topic prompts. It normalizes line breaks, eliminates hyphenation artifacts, and validates minimum character lengths.",
                "📄",
            ),
            (
                "2. Multi-Act Structured Prompting",
                "A system prompt formats the content into a multi-act podcast structure (Introduction, Deep Dive, Counterpoints, Summary) tailored to your selected language (Norwegian/English), episode length, and tone (Casual, Analytical, Debate).",
                "📝",
            ),
            (
                "3. Resilient 6-Tier Script Parsing",
                "The local Ollama model generates dialogue. The resilient multi-tier parser extracts dialogue turns even if the LLM output includes markdown code fences, explanatory notes, or formatting imperfections.",
                "⚙️",
            ),
            (
                "4. Neural Voice Audio Synthesis",
                "Each dialogue turn is individually synthesized into an MP3 audio segment via Edge-TTS neural voices, streaming async chunks in parallel to ensure rapid generation.",
                "🎙️",
            ),
            (
                "5. Zero-FFmpeg Audio Frame Assembly",
                "Individual dialogue MP3 segments are parsed at the binary MPEG frame level, stripped of header tags, aligned to frame boundaries, stitched with natural conversational pauses (350ms), and saved as a master podcast MP3.",
                "🎧",
            ),
            (
                "6. Interactive Studio & Audio Player",
                "The final episode is automatically loaded into the integrated player. You can listen, scrub the timeline, copy/save transcripts, or edit turns in the Interactive Script Studio to re-synthesize on demand.",
                "✨",
            ),
        ]

        for title, desc, icon in steps:
            card = ctk.CTkFrame(
                scroll,
                fg_color="#1a1c29",
                corner_radius=8,
                border_color=COLOR_CARD_BORDER,
                border_width=1,
            )
            card.pack(fill="x", pady=5)

            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(fill="x", padx=12, pady=(10, 4))

            ctk.CTkLabel(
                hdr,
                text=f"{icon}  {title}",
                font=get_font_heading(),
                text_color=COLOR_ACCENT,
                anchor="w",
            ).pack(side="left")

            ctk.CTkLabel(
                card,
                text=desc,
                font=get_font_body(),
                text_color=COLOR_TEXT_PRIMARY,
                wraplength=640,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 10))

    # --------------------------------------------------------------------------
    # Tab 3: Limitations & Requirements
    # --------------------------------------------------------------------------
    def _populate_limits_tab(self, parent: Any):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=6)

        limits = [
            (
                "Ollama Service Requirement",
                "LocalPodcastLLMStudio requires a locally running Ollama instance (http://localhost:11434). Ensure Ollama is installed and at least one dialogue model is pulled (e.g., 'ollama pull llama3.1:8b' or 'ollama pull qwen2.5:7b').",
                "⚠️",
                COLOR_WARNING,
            ),
            (
                "Internet Connection for Voice Synthesis",
                "While LLM dialogue generation and MP3 stitching are 100% local, Microsoft Edge-TTS requires an active internet connection to communicate with the neural voice synthesis endpoint.",
                "🌐",
                COLOR_INFO,
            ),
            (
                "PDF Text Layer Required",
                "PDF documents must contain extractable text layers. Scanned documents or image-only PDFs without an OCR text layer cannot be parsed by pypdf.",
                "📑",
                COLOR_WARNING,
            ),
            (
                "Hardware Performance & VRAM",
                "Dialogue generation speed depends on your local hardware. A dedicated GPU with 6GB+ VRAM is recommended for 8B models (e.g., Llama 3.1 8B, Qwen 2.5 7B). CPU inference is supported but may take 30-90 seconds.",
                "⚡",
                COLOR_INFO,
            ),
            (
                "Single-File Standalone Execution",
                "LocalPodcastLLMStudio is compiled as a self-contained Windows executable (.exe). It does not require Python or any pre-installed system dependencies to run.",
                "📦",
                COLOR_SUCCESS,
            ),
        ]

        for title, desc, icon, color in limits:
            card = ctk.CTkFrame(
                scroll,
                fg_color="#1a1c29",
                corner_radius=8,
                border_color=COLOR_CARD_BORDER,
                border_width=1,
            )
            card.pack(fill="x", pady=5)

            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(fill="x", padx=12, pady=(10, 4))

            ctk.CTkLabel(
                hdr, text=f"{icon}  {title}", font=get_font_heading(), text_color=color, anchor="w"
            ).pack(side="left")

            ctk.CTkLabel(
                card,
                text=desc,
                font=get_font_body(),
                text_color=COLOR_TEXT_PRIMARY,
                wraplength=640,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 10))

    # ==========================================================================
    # Footer Section
    # ==========================================================================
    def _build_footer(self):
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.pack(fill="x", padx=16, pady=(0, 14))

        info_label = ctk.CTkLabel(
            footer_frame,
            text="LocalPodcastLLMStudio • 100% Free & Open-Source • Windows 10 / 11",
            font=get_font_caption(),
            text_color=COLOR_TEXT_MUTED,
        )
        info_label.pack(side="left")

        btn_close = ctk.CTkButton(
            footer_frame,
            text="Close",
            width=100,
            height=32,
            font=get_font_body_bold(),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            command=self.destroy,
        )
        btn_close.pack(side="right")
