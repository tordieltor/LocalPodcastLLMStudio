"""
LocalPodcastLLMStudio - Terminal Ingestion Screen
Provides multi-modal source ingestion (Document file path browser with PDF/TXT/MD validation,
Pasted raw text input, and Topic/Prompt-only mode with zero document required).
Automatically synchronizes GroundingMode and enforces 50MB and 200 PDF page bounds via core.extractor.
"""

from __future__ import annotations

import os

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

from core.exceptions import DocumentExtractionError
from core.extractor import (
    DEFAULT_MAX_FILE_SIZE_MB,
    DEFAULT_MAX_PDF_PAGES,
    extract_text,
    extract_text_from_file,
)
from tui.components import CardFrame, HotkeyBar, KeyValueTable, SectionHeader, StatusBadge
from tui.input import TextInputPrompt, TextInputResult
from tui.state import IngestionState, SourceMode, TUIEventQueue, TUIEventType, TUIState
from tui.theme import (
    BOX_CARD,
    COLOR_ACCENT,
    COLOR_CARD_BORDER,
    COLOR_INFO,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    GLYPH_INFO,
    GLYPH_PACKAGE,
)


class IngestionScreen:
    """
    Interactive Terminal Screen for podcast source material ingestion.
    Supports 3 distinct modalities:
      1. Document File Browser / Path (.pdf, .txt, .md, .csv, .json, .rst, .log)
      2. Direct Pasted Text Entry
      3. Topic Prompt / Scratch Generation Mode (Zero Document Required)

    Enforces 50 MB file size limit and 200 PDF page bounds via core.extractor,
    and automatically coordinates GroundingMode with the central TUIState container.
    """

    SUPPORTED_EXTENSIONS: tuple[str, ...] = (
        ".pdf",
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        ".log",
        ".json",
        ".csv",
        ".text",
    )

    def __init__(
        self,
        state: TUIState,
        event_queue: TUIEventQueue | None = None,
        max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
        max_pdf_pages: int = DEFAULT_MAX_PDF_PAGES,
    ) -> None:
        self.state: TUIState = state
        self.event_queue: TUIEventQueue | None = event_queue
        self.max_file_size_mb: int = max_file_size_mb
        self.max_pdf_pages: int = max_pdf_pages

        self.text_prompt: TextInputPrompt = TextInputPrompt(
            placeholder="Enter file path or text...", max_length=4000
        )
        self.is_editing: bool = False
        self.active_field: str = "input"
        self.status_message: str = "Select input modality ([1] Document, [2] Text, [3] Topic)"
        self.status_level: str = "info"

    def set_mode(self, mode: SourceMode | str) -> None:
        """
        Switches active input modality and synchronizes GroundingMode in TUIState.

        Args:
            mode: SourceMode enum or string ('document', 'pasted_text', 'topic_prompt').
        """
        target_mode: SourceMode
        if isinstance(mode, SourceMode):
            target_mode = mode
        else:
            raw = str(mode).lower().strip().replace(" ", "_").replace("-", "_")
            if "topic" in raw or "scratch" in raw or "prompt" in raw:
                target_mode = SourceMode.TOPIC_PROMPT
            elif "paste" in raw or "raw" in raw or "text" in raw:
                target_mode = SourceMode.PASTED_TEXT
            else:
                target_mode = SourceMode.DOCUMENT

        with self.state.lock:
            self.state.ingestion.source_mode = target_mode
            old_grounding = self.state.config.grounding_mode
            self.state.sync_grounding_with_modality()
            new_grounding = self.state.config.grounding_mode

        if self.event_queue:
            self.event_queue.post_event(
                TUIEventType.INGESTION_MODE_CHANGED, payload=target_mode.value
            )
            if old_grounding != new_grounding:
                self.event_queue.post_event(
                    TUIEventType.CONFIG_GROUNDING_CHANGED, payload=new_grounding
                )

        self.validate()

    def set_file_path(self, path: str, auto_extract: bool = True) -> tuple[bool, str]:
        """
        Sets document file path and optionally extracts text with validation and bounds checking.

        Args:
            path: Target document filesystem path.
            auto_extract: Whether to immediately run extraction and normalization.

        Returns:
            Tuple[bool, str]: (success, status_or_error_message).
        """
        clean_path = path.strip().strip('"').strip("'")
        with self.state.lock:
            self.state.ingestion.file_path = clean_path

        if not clean_path:
            with self.state.lock:
                self.state.ingestion.extracted_text = ""
                self.state.ingestion.extracted_preview = ""
                self.state.ingestion.char_count = 0
                self.state.ingestion.word_count = 0
                self.state.ingestion.is_valid = False
                self.state.ingestion.validation_error = "File path is required."
            return False, "File path is required."

        if not auto_extract:
            is_valid, msg = self.validate()
            return is_valid, msg

        try:
            extracted = extract_text_from_file(
                clean_path,
                max_file_size_mb=self.max_file_size_mb,
                max_pages=self.max_pdf_pages,
            )
            with self.state.lock:
                self.state.ingestion.update_extracted(extracted)
                self.state.ingestion.validation_error = None
                self.state.ingestion.is_valid = len(extracted) >= 10

            self.status_message = f"Successfully extracted {len(extracted):,} chars ({len(extracted.split()):,} words)"
            self.status_level = "success"

            if self.event_queue:
                self.event_queue.post_event(
                    TUIEventType.INGESTION_FILE_SELECTED, payload=clean_path
                )
                self.event_queue.post_event(TUIEventType.INGESTION_EXTRACTED, payload=extracted)

            return True, self.status_message

        except DocumentExtractionError as err:
            err_msg = str(err)
            with self.state.lock:
                self.state.ingestion.extracted_text = ""
                self.state.ingestion.extracted_preview = ""
                self.state.ingestion.char_count = 0
                self.state.ingestion.word_count = 0
                self.state.ingestion.is_valid = False
                self.state.ingestion.validation_error = err_msg

            self.status_message = f"Extraction error: {err_msg}"
            self.status_level = "error"

            if self.event_queue:
                self.event_queue.post_event(
                    TUIEventType.INGESTION_ERROR, error=err_msg, payload=clean_path
                )

            return False, err_msg
        except Exception as ex:
            err_msg = f"Unexpected file error: {ex}"
            with self.state.lock:
                self.state.ingestion.is_valid = False
                self.state.ingestion.validation_error = err_msg
            return False, err_msg

    def set_raw_text(self, text: str, auto_extract: bool = True) -> tuple[bool, str]:
        """
        Sets directly pasted text and normalizes text content.

        Args:
            text: Raw input text string.
            auto_extract: Whether to run normalization and extraction bounds.

        Returns:
            Tuple[bool, str]: (success, status_or_error_message).
        """
        with self.state.lock:
            self.state.ingestion.raw_text = text

        if not auto_extract:
            return self.validate()

        try:
            extracted = extract_text(text, is_raw_text=True)
            with self.state.lock:
                self.state.ingestion.update_extracted(extracted)
                self.state.ingestion.validation_error = None
                self.state.ingestion.is_valid = len(extracted) >= 10

            self.status_message = f"Pasted text normalized: {len(extracted):,} chars ({len(extracted.split()):,} words)"
            self.status_level = "success"

            if self.event_queue:
                self.event_queue.post_event(TUIEventType.INGESTION_TEXT_CHANGED, payload=text)
                self.event_queue.post_event(TUIEventType.INGESTION_EXTRACTED, payload=extracted)

            return True, self.status_message

        except DocumentExtractionError as err:
            err_msg = str(err)
            with self.state.lock:
                self.state.ingestion.extracted_text = ""
                self.state.ingestion.extracted_preview = ""
                self.state.ingestion.char_count = 0
                self.state.ingestion.word_count = 0
                self.state.ingestion.is_valid = False
                self.state.ingestion.validation_error = err_msg

            self.status_message = err_msg
            self.status_level = "error"

            if self.event_queue:
                self.event_queue.post_event(TUIEventType.INGESTION_ERROR, error=err_msg)

            return False, err_msg

    def set_topic_prompt(self, topic: str, auto_extract: bool = True) -> tuple[bool, str]:
        """
        Sets topic/prompt for Scratch generation mode with validation.

        Args:
            topic: Topic prompt string.
            auto_extract: Whether to validate topic prompt.

        Returns:
            Tuple[bool, str]: (success, status_or_error_message).
        """
        with self.state.lock:
            self.state.ingestion.topic_prompt = topic

        if not auto_extract:
            return self.validate()

        try:
            extracted = extract_text(topic, is_topic=True)
            with self.state.lock:
                self.state.ingestion.update_extracted(extracted)
                self.state.ingestion.validation_error = None
                self.state.ingestion.is_valid = len(extracted) >= 3

            self.status_message = f"Topic prompt accepted: '{extracted[:50]}...'"
            self.status_level = "success"

            if self.event_queue:
                self.event_queue.post_event(TUIEventType.INGESTION_TOPIC_CHANGED, payload=topic)
                self.event_queue.post_event(TUIEventType.INGESTION_EXTRACTED, payload=extracted)

            return True, self.status_message

        except DocumentExtractionError as err:
            err_msg = str(err)
            with self.state.lock:
                self.state.ingestion.extracted_text = ""
                self.state.ingestion.extracted_preview = ""
                self.state.ingestion.char_count = 0
                self.state.ingestion.word_count = 0
                self.state.ingestion.is_valid = False
                self.state.ingestion.validation_error = err_msg

            self.status_message = err_msg
            self.status_level = "error"

            if self.event_queue:
                self.event_queue.post_event(TUIEventType.INGESTION_ERROR, error=err_msg)

            return False, err_msg

    def validate(self) -> tuple[bool, str]:
        """
        Validates current input based on the active modality.

        Returns:
            Tuple[bool, str]: (is_valid, validation_message).
        """
        with self.state.lock:
            mode = self.state.ingestion.source_mode

            if mode == SourceMode.DOCUMENT:
                path = self.state.ingestion.file_path.strip()
                if not path:
                    self.state.ingestion.is_valid = False
                    self.state.ingestion.validation_error = "Please specify a document file path."
                    return False, self.state.ingestion.validation_error

                if not os.path.exists(path):
                    self.state.ingestion.is_valid = False
                    self.state.ingestion.validation_error = f"File does not exist: {path}"
                    return False, self.state.ingestion.validation_error

                ext = os.path.splitext(path)[1].lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    self.state.ingestion.is_valid = False
                    self.state.ingestion.validation_error = f"Unsupported format '{ext}'. Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
                    return False, self.state.ingestion.validation_error

                try:
                    size = os.path.getsize(path)
                    max_bytes = self.max_file_size_mb * 1024 * 1024
                    if size > max_bytes:
                        self.state.ingestion.is_valid = False
                        self.state.ingestion.validation_error = f"File exceeds {self.max_file_size_mb} MB limit ({size / (1024 * 1024):.1f} MB)."
                        return False, self.state.ingestion.validation_error
                except OSError as e:
                    self.state.ingestion.is_valid = False
                    self.state.ingestion.validation_error = f"Cannot access file: {e}"
                    return False, self.state.ingestion.validation_error

                if self.state.ingestion.extracted_text:
                    if len(self.state.ingestion.extracted_text) < 10:
                        self.state.ingestion.is_valid = False
                        self.state.ingestion.validation_error = (
                            "Extracted content is too short (min 10 characters required)."
                        )
                        return False, self.state.ingestion.validation_error
                    self.state.ingestion.is_valid = True
                    self.state.ingestion.validation_error = None
                    return True, "Document is valid and extracted."

                self.state.ingestion.is_valid = False
                self.state.ingestion.validation_error = "Document has not been extracted yet."
                return False, self.state.ingestion.validation_error

            elif mode == SourceMode.PASTED_TEXT:
                text = self.state.ingestion.raw_text.strip()
                if not text or len(text) < 5:
                    self.state.ingestion.is_valid = False
                    self.state.ingestion.validation_error = (
                        "Pasted text is too short (minimum 5 characters required)."
                    )
                    return False, self.state.ingestion.validation_error

                if self.state.ingestion.char_count < 10:
                    self.state.ingestion.is_valid = False
                    self.state.ingestion.validation_error = (
                        "Normalized text is too short (minimum 10 characters required)."
                    )
                    return False, self.state.ingestion.validation_error

                self.state.ingestion.is_valid = True
                self.state.ingestion.validation_error = None
                return True, "Pasted text is valid."

            elif mode == SourceMode.TOPIC_PROMPT:
                topic = self.state.ingestion.topic_prompt.strip()
                if not topic or len(topic) < 3:
                    self.state.ingestion.is_valid = False
                    self.state.ingestion.validation_error = (
                        "Topic prompt is too short (minimum 3 characters required)."
                    )
                    return False, self.state.ingestion.validation_error

                self.state.ingestion.is_valid = True
                self.state.ingestion.validation_error = None
                return True, "Topic prompt is valid."

            self.state.ingestion.is_valid = False
            return False, "Unknown ingestion modality."

    def clear(self) -> None:
        """Resets all ingestion input fields and extracted data."""
        with self.state.lock:
            self.state.ingestion = IngestionState(source_mode=self.state.ingestion.source_mode)
            self.state.sync_grounding_with_modality()
        self.status_message = "Ingestion fields cleared."
        self.status_level = "info"

    def handle_key(self, key: str) -> str | None:
        """
        Handles keyboard input events for interactive navigation and text editing.

        Args:
            key: Standardized key token string.

        Returns:
            Optional[str]: Action directive (e.g. 'navigate:dashboard', None).
        """
        if self.is_editing:
            res: TextInputResult = self.text_prompt.handle_key(key)
            if res.action == "submit":
                val = res.value
                self.is_editing = False
                mode = self.state.ingestion.source_mode
                if mode == SourceMode.DOCUMENT:
                    self.set_file_path(val)
                elif mode == SourceMode.PASTED_TEXT:
                    self.set_raw_text(val)
                elif mode == SourceMode.TOPIC_PROMPT:
                    self.set_topic_prompt(val)
                return "input:submitted"
            elif res.action == "cancel":
                self.is_editing = False
                self.status_message = "Editing cancelled."
                return "input:cancelled"
            return None

        # Standard navigation keys when not actively typing into prompt
        if key == "1":
            self.set_mode(SourceMode.DOCUMENT)
            self.status_message = "Switched to Document Ingestion mode."
            return "mode:document"
        elif key == "2":
            self.set_mode(SourceMode.PASTED_TEXT)
            self.status_message = "Switched to Pasted Text mode."
            return "mode:pasted_text"
        elif key == "3":
            self.set_mode(SourceMode.TOPIC_PROMPT)
            self.status_message = (
                "Switched to Topic Prompt mode (Grounding set to Open Topic / Scratch)."
            )
            return "mode:topic_prompt"
        elif key in ("e", "enter", "i"):
            # Open inline text editor for current field
            mode = self.state.ingestion.source_mode
            current_val = ""
            placeholder = ""
            if mode == SourceMode.DOCUMENT:
                current_val = self.state.ingestion.file_path
                placeholder = "Enter file path (.pdf, .txt, .md)..."
            elif mode == SourceMode.PASTED_TEXT:
                current_val = self.state.ingestion.raw_text
                placeholder = "Paste or type text content..."
            elif mode == SourceMode.TOPIC_PROMPT:
                current_val = self.state.ingestion.topic_prompt
                placeholder = "Enter podcast topic or discussion prompt..."

            self.text_prompt = TextInputPrompt(
                initial_value=current_val, placeholder=placeholder, max_length=4000
            )
            self.is_editing = True
            self.status_message = "Editing input buffer (Enter to submit, Esc to cancel)..."
            return "editing:started"
        elif key in ("c", "x"):
            self.clear()
            return "action:cleared"
        elif key in ("v", "p"):
            mode = self.state.ingestion.source_mode
            if mode == SourceMode.DOCUMENT and self.state.ingestion.file_path:
                self.set_file_path(self.state.ingestion.file_path, auto_extract=True)
            else:
                self.validate()
            return "action:validated"
        elif key == "tab":
            # Cycle modality
            modes = [SourceMode.DOCUMENT, SourceMode.PASTED_TEXT, SourceMode.TOPIC_PROMPT]
            cur_idx = modes.index(self.state.ingestion.source_mode)
            next_mode = modes[(cur_idx + 1) % len(modes)]
            self.set_mode(next_mode)
            return f"mode:{next_mode.value}"
        elif key in ("escape", "b", "q"):
            return "navigate:dashboard"

        return None

    def render(self) -> RenderableType:
        """
        Renders the complete Tokyo Night Ingestion Screen.

        Returns:
            rich.console.RenderableType: Rich layout composition.
        """
        items: list[RenderableType] = []

        # 1. Header & Modality Selector
        mode = self.state.ingestion.source_mode
        header = SectionHeader(
            title="Podcast Content Ingestion & Text Extraction",
            subtitle="Choose an ingestion modality to load source material or topic",
            icon=GLYPH_PACKAGE,
        )
        items.append(header)
        items.append(Text(""))

        # Modality Selector Buttons
        modality_table = Table.grid(padding=(0, 2))
        doc_btn = (
            f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [1] Document File (.pdf/.txt/.md) [/]"
            if mode == SourceMode.DOCUMENT
            else f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [1] Document File [/]"
        )
        paste_btn = (
            f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [2] Pasted Text Entry [/]"
            if mode == SourceMode.PASTED_TEXT
            else f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [2] Pasted Text [/]"
        )
        topic_btn = (
            f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [3] Topic Prompt (Scratch) [/]"
            if mode == SourceMode.TOPIC_PROMPT
            else f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [3] Topic Prompt [/]"
        )
        modality_table.add_row(doc_btn, paste_btn, topic_btn)
        items.append(modality_table)
        items.append(Text(""))

        # 2. Main Input Card based on active modality
        input_items: list[RenderableType] = []

        if mode == SourceMode.DOCUMENT:
            input_items.append(
                Text(
                    f"Selected Document File (Max {self.max_file_size_mb} MB, {self.max_pdf_pages} PDF pages):",
                    style=f"bold {COLOR_TEXT_PRIMARY}",
                )
            )

            if self.is_editing:
                input_items.append(
                    self.text_prompt.render_text(
                        prefix="Path: ",
                        style_text=COLOR_TEXT_PRIMARY,
                        style_cursor=f"reverse bold {COLOR_ACCENT}",
                    )
                )
            else:
                p_text = (
                    self.state.ingestion.file_path or "[No file selected — press 'E' to enter path]"
                )
                style_p = COLOR_TEXT_PRIMARY if self.state.ingestion.file_path else COLOR_TEXT_MUTED
                input_items.append(
                    Text.from_markup(f"[bold {COLOR_ACCENT}]Path:[/] {p_text}", style=style_p)
                )

            if self.state.ingestion.file_path and os.path.exists(self.state.ingestion.file_path):
                try:
                    sz_bytes = os.path.getsize(self.state.ingestion.file_path)
                    sz_kb = sz_bytes / 1024
                    sz_mb = sz_kb / 1024
                    size_desc = (
                        f"{sz_mb:.2f} MB ({sz_kb:.1f} KB)" if sz_mb >= 1.0 else f"{sz_kb:.1f} KB"
                    )
                    input_items.append(Text(f"File size: {size_desc}", style=COLOR_TEXT_SECONDARY))
                except OSError:
                    pass

        elif mode == SourceMode.PASTED_TEXT:
            input_items.append(
                Text(
                    "Pasted Raw Text Content (Min 5 characters):",
                    style=f"bold {COLOR_TEXT_PRIMARY}",
                )
            )

            if self.is_editing:
                input_items.append(
                    self.text_prompt.render_text(
                        prefix="Text: ",
                        style_text=COLOR_TEXT_PRIMARY,
                        style_cursor=f"reverse bold {COLOR_ACCENT}",
                    )
                )
            else:
                raw_preview = (
                    self.state.ingestion.raw_text[:200] + "..."
                    if len(self.state.ingestion.raw_text) > 200
                    else self.state.ingestion.raw_text
                )
                display_t = raw_preview or "[No text pasted — press 'E' to paste or type text]"
                style_t = COLOR_TEXT_PRIMARY if self.state.ingestion.raw_text else COLOR_TEXT_MUTED
                input_items.append(Text(display_t, style=style_t))

        elif mode == SourceMode.TOPIC_PROMPT:
            input_items.append(
                Text(
                    "Topic / Discussion Prompt for 'Generate from Scratch' Mode (Min 3 characters):",
                    style=f"bold {COLOR_TEXT_PRIMARY}",
                )
            )

            if self.is_editing:
                input_items.append(
                    self.text_prompt.render_text(
                        prefix="Topic: ",
                        style_text=COLOR_TEXT_PRIMARY,
                        style_cursor=f"reverse bold {COLOR_ACCENT}",
                    )
                )
            else:
                top_display = (
                    self.state.ingestion.topic_prompt
                    or "[No topic specified — press 'E' to enter podcast topic]"
                )
                style_top = (
                    COLOR_TEXT_PRIMARY if self.state.ingestion.topic_prompt else COLOR_TEXT_MUTED
                )
                input_items.append(
                    Text.from_markup(
                        f"[bold {COLOR_ACCENT}]Topic:[/] {top_display}", style=style_top
                    )
                )

            input_items.append(
                Text(
                    f"{GLYPH_INFO} Automatically synchronizes Grounding Mode to 'Open Topic / Scratch'.",
                    style=COLOR_INFO,
                )
            )

        card_title = (
            "Document File Path"
            if mode == SourceMode.DOCUMENT
            else (
                "Direct Pasted Text" if mode == SourceMode.PASTED_TEXT else "Topic Prompt (Scratch)"
            )
        )
        items.append(CardFrame(Group(*input_items), title=card_title, box_style=BOX_CARD))
        items.append(Text(""))

        # 3. Extraction & Validation Status Card
        ext_items: list[RenderableType] = []

        is_valid = self.state.ingestion.is_valid
        val_err = self.state.ingestion.validation_error

        status_badge = StatusBadge(
            status="online" if is_valid else ("error" if val_err else "checking"),
            text="Ready & Validated"
            if is_valid
            else (f"Invalid: {val_err}" if val_err else "Awaiting Input"),
        )
        ext_items.append(status_badge.render())
        ext_items.append(Text(""))

        # Metrics Table
        stats_table = KeyValueTable()
        stats_table.add_row("Extracted Characters", f"{self.state.ingestion.char_count:,}")
        stats_table.add_row("Extracted Words", f"{self.state.ingestion.word_count:,}")
        stats_table.add_row(
            "Grounding Mode",
            f"{self.state.config.grounding_mode.upper()} (Auto-synced)",
        )
        ext_items.append(stats_table.__rich__())

        if self.state.ingestion.extracted_preview:
            ext_items.append(Text(""))
            ext_items.append(Text("Extracted Content Preview:", style=f"bold {COLOR_ACCENT}"))
            preview_card = CardFrame(
                Text(self.state.ingestion.extracted_preview, style=COLOR_TEXT_SECONDARY),
                title="Preview",
                border_style=COLOR_CARD_BORDER,
                padding=(0, 1),
            )
            ext_items.append(preview_card.__rich__())

        items.append(CardFrame(Group(*ext_items), title="Extraction Status & Preview"))
        items.append(Text(""))

        # 4. Footer Hotkey Bar
        hotkeys = HotkeyBar(
            [
                ("1", "Doc Mode"),
                ("2", "Text Mode"),
                ("3", "Topic Mode"),
                ("E/Enter", "Edit Input"),
                ("V", "Extract/Validate"),
                ("C", "Clear"),
                ("Esc", "Back to Dashboard"),
            ]
        )
        items.append(hotkeys)

        return Group(*items)

    def __rich__(self) -> RenderableType:
        return self.render()

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.render()
