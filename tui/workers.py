"""
LocalPodcastLLMStudio - Asynchronous Background Workers for Terminal UI
Provides dedicated, non-blocking background worker threads with cooperative cancellation,
real-time token streaming, multi-act episodic LLM generation, Piper TTS synthesis,
and zero-FFmpeg MP3 stitching communicating via typed TUIEvent queue and reactive state.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any

from core.exceptions import (
    DocumentExtractionError,
    OllamaConnectionError,
    StudioError,
)
from core.extractor import (
    DEFAULT_MAX_FILE_SIZE_MB,
    DEFAULT_MAX_PDF_PAGES,
    extract_text,
)
from core.io_utils import atomic_write_file
from core.mp3_stitcher import stitch_mp3_files
from core.ollama import (
    ModelPullProgress,
    OllamaClient,
    _validate_url,
    pull_model_stream,
    start_ollama_service,
)
from core.parser import (
    DialogueParser,
    DialogueTurn,
    SpeakerRole,
    dialogue_to_json,
    dialogue_to_markdown,
)
from core.prompts import (
    build_act_system_prompt,
    build_act_user_prompt,
    build_system_prompt,
    build_user_prompt,
    get_act_specs,
    normalize_language_code,
)
from core.tts import synthesize_dialogue_audio
from tui.state import (
    GenerationStatus,
    OllamaStatus,
    SynthesisStatus,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)

# ==============================================================================
# Base Worker Thread
# ==============================================================================


class BaseWorker(threading.Thread):
    """
    Abstract base background worker thread with cooperative cancellation support,
    typed TUIEvent dispatching, and reactive state synchronization.
    """

    def __init__(
        self,
        state: TUIState | None = None,
        event_queue: TUIEventQueue | None = None,
        cancel_event: threading.Event | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.state: TUIState | None = state
        self.event_queue: TUIEventQueue | None = event_queue
        self.cancel_event: threading.Event = cancel_event or threading.Event()

    def cancel(self) -> None:
        """Signals cancellation to the running worker thread."""
        self.cancel_event.set()

    def is_cancelled(self) -> bool:
        """Returns True if worker cancellation has been requested."""
        return self.cancel_event.is_set()

    def post_event(
        self,
        event_type: TUIEventType | str,
        payload: Any = None,
        error: str | None = None,
    ) -> None:
        """Safely enqueues a typed event to the central TUI event bus."""
        if self.event_queue is not None:
            self.event_queue.post_event(event_type=event_type, payload=payload, error=error)

    def _set_busy(self, is_busy: bool, task: str = "") -> None:
        """Updates UI busy state and dispatches busy event."""
        if self.state is not None:
            with self.state.lock:
                self.state.ui.is_busy = is_busy
                self.state.ui.busy_task = task if is_busy else ""
        self.post_event(
            TUIEventType.SET_BUSY,
            payload={"is_busy": is_busy, "task": task},
        )


# ==============================================================================
# Document Extraction Worker
# ==============================================================================


class ExtractionWorker(BaseWorker):
    """
    Dedicated worker thread for extracting text from files, raw text, or scratch prompts
    with DoS bounds enforcement (max 50 MB, max 200 PDF pages) and text normalization.
    """

    def __init__(
        self,
        source: str,
        is_raw_text: bool = False,
        is_topic: bool = False,
        state: TUIState | None = None,
        event_queue: TUIEventQueue | None = None,
        cancel_event: threading.Event | None = None,
        max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
        max_pdf_pages: int = DEFAULT_MAX_PDF_PAGES,
    ) -> None:
        super().__init__(
            state=state,
            event_queue=event_queue,
            cancel_event=cancel_event,
            name="ExtractionWorker",
        )
        self.source: str = source
        self.is_raw_text: bool = is_raw_text
        self.is_topic: bool = is_topic
        self.max_file_size_mb: int = max_file_size_mb
        self.max_pdf_pages: int = max_pdf_pages

    def run(self) -> None:
        if self.is_cancelled():
            return

        self._set_busy(True, "Extracting text content")
        try:
            extracted_text = extract_text(
                source=self.source,
                is_raw_text=self.is_raw_text,
                is_topic=self.is_topic,
                max_file_size_mb=self.max_file_size_mb,
                max_pages=self.max_pdf_pages,
            )

            if self.is_cancelled():
                return

            if self.state is not None:
                with self.state.lock:
                    self.state.ingestion.update_extracted(extracted_text)

            char_count = len(extracted_text)
            word_count = len(extracted_text.split()) if extracted_text else 0
            preview = (
                (extracted_text[:350].rsplit(" ", 1)[0] + "...")
                if char_count > 350
                else extracted_text
            )

            self.post_event(
                TUIEventType.INGESTION_EXTRACTED,
                payload={
                    "text": extracted_text,
                    "char_count": char_count,
                    "word_count": word_count,
                    "preview": preview,
                },
            )

        except (DocumentExtractionError, StudioError, ValueError, OSError, Exception) as exc:
            err_msg = str(exc)
            if self.state is not None:
                with self.state.lock:
                    self.state.ingestion.validation_error = err_msg
                    self.state.ingestion.is_valid = False
            self.post_event(
                TUIEventType.INGESTION_ERROR,
                payload={"source": self.source, "error": err_msg},
                error=err_msg,
            )
        finally:
            self._set_busy(False)


# ==============================================================================
# Ollama Connection Probe Worker
# ==============================================================================


class OllamaProbeWorker(BaseWorker):
    """
    Dedicated background worker for checking Ollama server reachability,
    fetching the installed model catalog, and auto-selecting the best model.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:11434",
        timeout: float = 3.0,
        state: TUIState | None = None,
        event_queue: TUIEventQueue | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__(
            state=state,
            event_queue=event_queue,
            cancel_event=cancel_event,
            name="OllamaProbeWorker",
        )
        self.server_url: str = server_url
        self.timeout: float = timeout

    def run(self) -> None:
        if self.is_cancelled():
            return

        try:
            clean_url = _validate_url(self.server_url)
            client = OllamaClient(base_url=clean_url)
            is_online = client.check_connection(timeout=self.timeout)

            if is_online:
                try:
                    models = client.list_models(timeout=self.timeout)
                except (OllamaConnectionError, TimeoutError, OSError):
                    models = []

                if self.state is not None:
                    with self.state.lock:
                        self.state.ollama.status = OllamaStatus.ONLINE
                        self.state.ollama.is_online = True
                        self.state.ollama.available_models = models
                        self.state.ollama.auto_select_model()
                        self.state.ollama.error_message = None

                self.post_event(
                    TUIEventType.OLLAMA_STATUS_UPDATE,
                    payload={"online": True, "url": clean_url},
                )
                self.post_event(
                    TUIEventType.OLLAMA_MODELS_LOADED,
                    payload={"models": models, "url": clean_url},
                )
            else:
                if self.state is not None:
                    with self.state.lock:
                        self.state.ollama.status = OllamaStatus.OFFLINE
                        self.state.ollama.is_online = False
                        self.state.ollama.available_models = []
                        self.state.ollama.error_message = "Ollama server unreachable."

                self.post_event(
                    TUIEventType.OLLAMA_STATUS_UPDATE,
                    payload={
                        "online": False,
                        "url": clean_url,
                        "error": "Ollama server unreachable.",
                    },
                )

        except Exception as exc:
            err_msg = str(exc)
            if self.state is not None:
                with self.state.lock:
                    self.state.ollama.status = OllamaStatus.ERROR
                    self.state.ollama.is_online = False
                    self.state.ollama.error_message = err_msg

            self.post_event(
                TUIEventType.OLLAMA_STATUS_UPDATE,
                payload={"online": False, "error": err_msg},
                error=err_msg,
            )


# ==============================================================================
# Ollama Background Service Launcher Worker
# ==============================================================================


class OllamaLaunchWorker(BaseWorker):
    """
    Dedicated worker thread for starting the local Ollama background daemon process
    without blocking the TUI event loop.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:11434",
        timeout: float = 10.0,
        state: TUIState | None = None,
        event_queue: TUIEventQueue | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__(
            state=state,
            event_queue=event_queue,
            cancel_event=cancel_event,
            name="OllamaLaunchWorker",
        )
        self.server_url: str = server_url
        self.timeout: float = timeout

    def run(self) -> None:
        if self.is_cancelled():
            return

        self._set_busy(True, "Starting Ollama service")
        if self.state is not None:
            with self.state.lock:
                self.state.ollama.status = OllamaStatus.STARTING

        self.post_event(
            TUIEventType.OLLAMA_SERVICE_LAUNCHING,
            payload={"status": "Starting Ollama background service..."},
        )

        try:
            clean_url = _validate_url(self.server_url)
            success, msg = start_ollama_service(
                timeout=self.timeout,
                base_url=clean_url,
                cancel_event=self.cancel_event,
            )

            if success:
                client = OllamaClient(base_url=clean_url)
                try:
                    models = client.list_models(timeout=3.0)
                except Exception:
                    models = []

                if self.state is not None:
                    with self.state.lock:
                        self.state.ollama.status = OllamaStatus.ONLINE
                        self.state.ollama.is_online = True
                        self.state.ollama.daemon_running = True
                        self.state.ollama.available_models = models
                        self.state.ollama.auto_select_model()
                        self.state.ollama.error_message = None

                self.post_event(
                    TUIEventType.OLLAMA_SERVICE_STARTED,
                    payload={"status": msg, "models": models},
                )
                self.post_event(
                    TUIEventType.OLLAMA_MODELS_LOADED,
                    payload={"models": models, "url": clean_url},
                )
            else:
                if self.state is not None:
                    with self.state.lock:
                        self.state.ollama.status = OllamaStatus.ERROR
                        self.state.ollama.is_online = False
                        self.state.ollama.error_message = msg

                self.post_event(
                    TUIEventType.OLLAMA_SERVICE_ERROR,
                    payload={
                        "error": msg,
                        "details": (
                            "Could not launch Ollama daemon. "
                            "Ensure Ollama is installed from https://ollama.com or start it manually."
                        ),
                    },
                    error=msg,
                )

        except Exception as exc:
            err_msg = str(exc)
            if self.state is not None:
                with self.state.lock:
                    self.state.ollama.status = OllamaStatus.ERROR
                    self.state.ollama.is_online = False
                    self.state.ollama.error_message = err_msg

            self.post_event(
                TUIEventType.OLLAMA_SERVICE_ERROR,
                payload={"error": err_msg, "details": f"Error starting Ollama service: {err_msg}"},
                error=err_msg,
            )
        finally:
            self._set_busy(False)


# ==============================================================================
# Streaming Model Pull Worker
# ==============================================================================


class ModelPullWorker(BaseWorker):
    """
    Dedicated worker thread for streaming Ollama model downloads with real-time
    progress callbacks, transfer speed calculations, and cancellation support.
    """

    def __init__(
        self,
        model_name: str,
        server_url: str = "http://localhost:11434",
        timeout: float = 3600.0,
        state: TUIState | None = None,
        event_queue: TUIEventQueue | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__(
            state=state,
            event_queue=event_queue,
            cancel_event=cancel_event,
            name=f"ModelPullWorker_{model_name}",
        )
        self.model_name: str = model_name
        self.server_url: str = server_url
        self.timeout: float = timeout

    def run(self) -> None:
        if self.is_cancelled():
            return

        self._set_busy(True, f"Downloading model {self.model_name}")
        if self.state is not None:
            with self.state.lock:
                self.state.ollama.status = OllamaStatus.PULLING
                self.state.ollama.pull_model_name = self.model_name

        self.post_event(
            TUIEventType.OLLAMA_PULL_START,
            payload={"model": self.model_name},
        )

        def progress_cb(progress: ModelPullProgress) -> None:
            if not self.is_cancelled():
                if self.state is not None:
                    with self.state.lock:
                        self.state.ollama.pull_progress = progress
                self.post_event(TUIEventType.OLLAMA_PULL_PROGRESS, payload=progress)

        try:
            clean_url = _validate_url(self.server_url)
            success = pull_model_stream(
                model=self.model_name,
                base_url=clean_url,
                progress_callback=progress_cb,
                cancel_event=self.cancel_event,
                timeout=self.timeout,
            )

            if success:
                client = OllamaClient(base_url=clean_url)
                try:
                    models = client.list_models(timeout=3.0)
                except Exception:
                    models = []

                if self.state is not None:
                    with self.state.lock:
                        self.state.ollama.status = OllamaStatus.ONLINE
                        self.state.ollama.available_models = models
                        self.state.ollama.selected_model = self.model_name
                        self.state.ollama.pull_progress = None
                        self.state.ollama.pull_model_name = ""

                self.post_event(
                    TUIEventType.OLLAMA_PULL_DONE,
                    payload={
                        "model": self.model_name,
                        "message": f"Model '{self.model_name}' installed and verified successfully.",
                    },
                )
                self.post_event(
                    TUIEventType.OLLAMA_MODELS_LOADED,
                    payload={"models": models, "url": clean_url},
                )

        except Exception as exc:
            if self.is_cancelled():
                if self.state is not None:
                    with self.state.lock:
                        self.state.ollama.status = (
                            OllamaStatus.ONLINE
                            if self.state.ollama.is_online
                            else OllamaStatus.OFFLINE
                        )
                        self.state.ollama.pull_progress = None
                        self.state.ollama.pull_model_name = ""
                self.post_event(
                    TUIEventType.OLLAMA_PULL_CANCELLED,
                    payload={"model": self.model_name},
                )
            else:
                err_msg = str(exc)
                if self.state is not None:
                    with self.state.lock:
                        self.state.ollama.status = OllamaStatus.ERROR
                        self.state.ollama.error_message = err_msg
                        self.state.ollama.pull_progress = None
                        self.state.ollama.pull_model_name = ""
                self.post_event(
                    TUIEventType.OLLAMA_PULL_ERROR,
                    payload={"model": self.model_name, "error": err_msg},
                    error=err_msg,
                )
        finally:
            self._set_busy(False)


# ==============================================================================
# End-to-End Dialogue Generation & Pipeline Worker
# ==============================================================================


class GenerationWorker(BaseWorker):
    """
    Dedicated background worker thread for executing full podcast generation workflows:
    - Phase 1: Source content extraction and validation.
    - Phase 2: Sequential multi-act LLM dialogue generation with live token streaming.
    - Phase 3: Atomic script persistence (JSON & Markdown).
    - Phase 4: Local Piper TTS neural speech synthesis.
    - Phase 5: Zero-FFmpeg MP3 frame concatenation and ID3v2 tagging.

    Supports 3 operational modes:
      1. 'full' (Script Generation -> Piper TTS -> MP3 Stitching)
      2. 'script_only' (Script Generation only -> Atomic JSON/MD persistence)
      3. 'audio_from_script' (Piper TTS -> MP3 Stitching from pre-existing dialogue turns)
    """

    def __init__(
        self,
        mode: str = "full",
        input_type: str = "document",
        input_data: Any = None,
        language: str = "nb-NO",
        model: str = "llama3.1:8b",
        format_type: str = "standard",
        tone: str = "casual",
        grounding_mode: str = "strict",
        speed_rate: str = "+0%",
        output_dir: str = "./output",
        ollama_url: str = "http://localhost:11434",
        temperature: float = 0.70,
        custom_system_prompt: str | None = None,
        state: TUIState | None = None,
        event_queue: TUIEventQueue | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__(
            state=state,
            event_queue=event_queue,
            cancel_event=cancel_event,
            name="GenerationWorker",
        )
        self.mode: str = mode
        self.input_type: str = input_type
        self.input_data: Any = input_data
        self.language: str = normalize_language_code(language)
        self.model: str = model
        self.format_type: str = format_type
        self.tone: str = tone
        self.grounding_mode: str = grounding_mode
        self.speed_rate: str = speed_rate
        self.output_dir: str = output_dir
        self.ollama_url: str = ollama_url
        self.temperature: float = temperature
        self.custom_system_prompt: str | None = custom_system_prompt
        self.temp_turn_files: list[str] = []

    def run(self) -> None:
        if self.is_cancelled():
            return

        self._set_busy(True, "Generating podcast")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        dialogue: list[DialogueTurn] = []

        if self.state is not None:
            with self.state.lock:
                self.state.generation.status = GenerationStatus.GENERATING
                self.state.generation.streamed_tokens = ""
                self.state.generation.turns = []
                self.state.generation.generation_error = None
                self.state.generation.elapsed_time_sec = 0.0
                self.state.generation.tokens_per_sec = 0.0

        self.post_event(
            TUIEventType.GEN_STARTED,
            payload={
                "mode": self.mode,
                "model": self.model,
                "format": self.format_type,
                "language": self.language,
            },
        )

        try:
            os.makedirs(self.output_dir, exist_ok=True)

            # ------------------------------------------------------------------
            # Phase 1 & 2: Dialogue Script Generation (if not audio_from_script)
            # ------------------------------------------------------------------
            if self.mode != "audio_from_script":
                if self.is_cancelled():
                    self._handle_cancellation()
                    return

                # Ingestion extraction
                is_raw = self.input_type in ("text", "pasted_text")
                is_topic = self.input_type in ("topic", "topic_prompt")
                source_content = self.input_data

                if source_content is None and self.state is not None:
                    source_content = self.state.ingestion.extracted_text

                if not source_content:
                    raise ValueError(
                        "Input content is missing. Please provide a document or topic prompt."
                    )

                if self.input_type == "dialogue" or isinstance(source_content, list):
                    extracted_text = ""
                    dialogue = list(source_content)
                else:
                    if self.input_type == "document" and os.path.isfile(str(source_content)):
                        extracted_text = extract_text(
                            source=str(source_content), is_raw_text=False, is_topic=False
                        )
                    elif is_raw:
                        extracted_text = extract_text(
                            source=str(source_content), is_raw_text=True, is_topic=False
                        )
                    elif is_topic:
                        extracted_text = extract_text(
                            source=str(source_content), is_raw_text=False, is_topic=True
                        )
                    else:
                        extracted_text = str(source_content)

                    if not extracted_text or len(extracted_text.strip()) < 10:
                        raise ValueError(
                            "Input content is too short (minimum 10 characters required)."
                        )

                if self.is_cancelled():
                    self._handle_cancellation()
                    return

                # Sequential multi-act LLM generation with live token streaming
                if not dialogue:
                    dialogue = self._execute_multi_act_generation(
                        content=extracted_text,
                        is_topic=is_topic,
                    )

                if not dialogue:
                    raise ValueError("Failed to parse dialogue turns from LLM generation.")

                # Save script files to output folder (.json and .md) atomically
                script_json_str = dialogue_to_json(dialogue)
                script_md_str = dialogue_to_markdown(dialogue)

                script_json_path = os.path.join(self.output_dir, f"podcast_script_{timestamp}.json")
                script_md_path = os.path.join(self.output_dir, f"podcast_transcript_{timestamp}.md")

                atomic_write_file(script_json_path, script_json_str)
                atomic_write_file(script_md_path, script_md_str)

                if self.state is not None:
                    with self.state.lock:
                        self.state.generation.turns = dialogue
                        self.state.generation.raw_json_script = script_json_str
                        self.state.generation.script_json_path = script_json_path
                        self.state.generation.script_md_path = script_md_path

                self.post_event(
                    TUIEventType.GEN_SCRIPT_PARSED,
                    payload={
                        "turns": dialogue,
                        "count": len(dialogue),
                        "json_path": script_json_path,
                        "md_path": script_md_path,
                    },
                )

                if self.mode == "script_only":
                    if self.state is not None:
                        with self.state.lock:
                            self.state.generation.status = GenerationStatus.COMPLETED

                    self.post_event(
                        TUIEventType.GEN_COMPLETED,
                        payload={
                            "mode": "script_only",
                            "dialogue": dialogue,
                            "script_json_path": script_json_path,
                            "script_md_path": script_md_path,
                        },
                    )
                    return
            else:
                # Mode: audio_from_script
                if isinstance(self.input_data, list) and self.input_data:
                    dialogue = list(self.input_data)
                elif self.state is not None and self.state.generation.turns:
                    dialogue = list(self.state.generation.turns)
                else:
                    raise ValueError("No dialogue turns provided for Audio-from-Script synthesis.")

            # ------------------------------------------------------------------
            # Phase 3 & 4: Local Piper TTS & Zero-FFmpeg MP3 Frame Stitching
            # ------------------------------------------------------------------
            if self.is_cancelled():
                self._handle_cancellation()
                return

            self._execute_tts_and_stitching(dialogue=dialogue, timestamp=timestamp)

        except Exception as exc:
            if self.is_cancelled():
                self._handle_cancellation()
            else:
                err_msg = str(exc)
                if self.state is not None:
                    with self.state.lock:
                        self.state.generation.status = GenerationStatus.FAILED
                        self.state.generation.generation_error = err_msg
                        self.state.audio.status = SynthesisStatus.FAILED
                        self.state.audio.synthesis_error = err_msg
                self.post_event(
                    TUIEventType.GEN_FAILED,
                    payload={"error": err_msg},
                    error=err_msg,
                )
        finally:
            self._set_busy(False)

    def _execute_multi_act_generation(
        self,
        content: str,
        is_topic: bool,
    ) -> list[DialogueTurn]:
        """Executes sequential multi-act generation with live token streaming."""
        clean_url = _validate_url(self.ollama_url)
        client = OllamaClient(base_url=clean_url)
        act_specs = get_act_specs(format_type=self.format_type, language=self.language)
        total_acts = len(act_specs)

        full_script: list[DialogueTurn] = []
        accumulated_tokens = ""
        token_count = 0
        start_time = time.time()

        def make_token_callback() -> Callable[[str], None]:
            def _cb(token: str) -> None:
                nonlocal accumulated_tokens, token_count
                accumulated_tokens += token
                token_count += 1
                elapsed = max(0.001, time.time() - start_time)
                tps = token_count / elapsed

                if self.state is not None:
                    with self.state.lock:
                        self.state.generation.streamed_tokens = accumulated_tokens
                        self.state.generation.elapsed_time_sec = elapsed
                        self.state.generation.tokens_per_sec = tps

                self.post_event(
                    TUIEventType.GEN_TOKEN_STREAM,
                    payload={
                        "token": token,
                        "accumulated": accumulated_tokens,
                        "elapsed": elapsed,
                        "tps": tps,
                    },
                )

            return _cb

        token_callback = make_token_callback()

        # 1. Single-Act Mode (e.g. quick summary)
        if total_acts <= 1:
            if self.is_cancelled():
                raise RuntimeError("Generation cancelled by user.")

            if self.state is not None:
                with self.state.lock:
                    self.state.generation.current_act = 1
                    self.state.generation.total_acts = 1
                    self.state.generation.act_title = "Episode Dialogue"

            self.post_event(
                TUIEventType.GEN_ACT_PROGRESS,
                payload={
                    "current_act": 1,
                    "total_acts": 1,
                    "act_title": "Episode Dialogue",
                },
            )

            if self.custom_system_prompt:
                sys_prompt = self.custom_system_prompt
            else:
                sys_prompt = build_system_prompt(
                    language=self.language,
                    format_type=self.format_type,
                    tone_style=self.tone,
                    grounding_mode=self.grounding_mode,
                )

            usr_prompt = build_user_prompt(
                content=content,
                language=self.language,
                grounding_mode=self.grounding_mode,
                is_topic=is_topic,
            )

            raw_response = client.generate(
                model=self.model,
                prompt=usr_prompt,
                system=sys_prompt,
                stream=True,
                temperature=self.temperature,
                cancel_event=self.cancel_event,
                callback=token_callback,
            )

            if not raw_response or not raw_response.strip():
                raise ValueError("Ollama returned an empty response.")

            return DialogueParser.parse(raw_response, default_language=self.language)

        # 2. Multi-Act Sequential Mode (Standard, Deep Dive, Extended In-Depth)
        for act_idx, act in enumerate(act_specs, 1):
            if self.is_cancelled():
                raise RuntimeError("Generation cancelled by user.")

            act_title = act.get("title", f"Act {act_idx}")

            if self.state is not None:
                with self.state.lock:
                    self.state.generation.current_act = act_idx
                    self.state.generation.total_acts = total_acts
                    self.state.generation.act_title = act_title

            self.post_event(
                TUIEventType.GEN_ACT_PROGRESS,
                payload={
                    "current_act": act_idx,
                    "total_acts": total_acts,
                    "act_title": act_title,
                },
            )

            next_speaker = SpeakerRole.HOST_1.value
            if full_script:
                next_speaker = SpeakerRole.get_alternate(full_script[-1].speaker)

            prev_dict_turns = [t.to_dict() for t in full_script[-2:]] if full_script else None
            act_sys = build_act_system_prompt(
                act=act,
                total_acts=total_acts,
                language=self.language,
                tone_style=self.tone,
                grounding_mode=self.grounding_mode,
                next_speaker=next_speaker,
            )
            act_usr = build_act_user_prompt(
                content=content,
                prev_turns=prev_dict_turns,
                language=self.language,
                grounding_mode=self.grounding_mode,
                is_topic=is_topic,
            )

            raw_act_response = client.generate(
                model=self.model,
                prompt=act_usr,
                system=act_sys,
                stream=True,
                temperature=self.temperature,
                cancel_event=self.cancel_event,
                callback=token_callback,
            )

            if raw_act_response and raw_act_response.strip():
                try:
                    act_turns = DialogueParser.parse(
                        raw_act_response, default_language=self.language
                    )
                    if act_turns:
                        for t in act_turns:
                            full_script.append(t)
                except ValueError:
                    if not full_script and act_idx == 1:
                        pass

        return full_script

    def _execute_tts_and_stitching(
        self,
        dialogue: list[DialogueTurn],
        timestamp: str,
    ) -> None:
        """Synthesizes turn audio with Piper TTS and stitches zero-FFmpeg master MP3."""
        if self.state is not None:
            with self.state.lock:
                self.state.audio.status = SynthesisStatus.SYNTHESIZING
                self.state.audio.total_turns = len(dialogue)
                self.state.audio.current_turn = 0
                self.state.audio.progress_pct = 0.0
                self.state.audio.synthesis_error = None

        self.post_event(
            TUIEventType.TTS_STARTED,
            payload={"total_turns": len(dialogue), "language": self.language},
        )

        temp_tts_dir = tempfile.mkdtemp(prefix="localpodcastllmstudio_tts_")

        def tts_progress_cb(curr: int, tot: int) -> None:
            if not self.is_cancelled():
                pct = (curr / max(1, tot)) * 100.0
                turn_speaker = dialogue[curr - 1].speaker if curr <= len(dialogue) else "Host"
                if self.state is not None:
                    with self.state.lock:
                        self.state.audio.current_turn = curr
                        self.state.audio.total_turns = tot
                        self.state.audio.current_speaker = turn_speaker
                        self.state.audio.progress_pct = pct

                self.post_event(
                    TUIEventType.TTS_TURN_PROGRESS,
                    payload={
                        "current": curr,
                        "total": tot,
                        "speaker": turn_speaker,
                        "pct": pct,
                    },
                )

        try:
            self.temp_turn_files = synthesize_dialogue_audio(
                dialogue=dialogue,
                language=self.language,
                rate=self.speed_rate,
                output_dir=temp_tts_dir,
                progress_cb=tts_progress_cb,
                cancel_event=self.cancel_event,
            )

            if self.is_cancelled():
                raise RuntimeError("Synthesis cancelled by user.")

            if self.state is not None:
                with self.state.lock:
                    self.state.audio.temp_turn_files = self.temp_turn_files

            # Zero-FFmpeg MP3 Stitching
            self.post_event(
                TUIEventType.TTS_STITCH_STARTED,
                payload={"turn_count": len(self.temp_turn_files)},
            )

            output_mp3_path = os.path.join(self.output_dir, f"podcast_{timestamp}.mp3")
            stitch_mp3_files(
                input_files_or_bytes=self.temp_turn_files,
                output_file_path=output_mp3_path,
                silence_duration_ms=350,
                title=f"Podcast {timestamp}",
                artist="LocalPodcastLLMStudio",
            )

            if self.state is not None:
                with self.state.lock:
                    self.state.generation.status = GenerationStatus.COMPLETED
                    self.state.audio.status = SynthesisStatus.COMPLETED
                    self.state.audio.master_mp3_path = output_mp3_path
                    self.state.player.current_file = output_mp3_path
                    self.state.player.is_loaded = True

            self.post_event(
                TUIEventType.TTS_COMPLETED,
                payload={"mp3_path": output_mp3_path, "turns": len(dialogue)},
            )
            self.post_event(
                TUIEventType.GEN_COMPLETED,
                payload={
                    "mode": self.mode,
                    "mp3_path": output_mp3_path,
                    "dialogue": dialogue,
                },
            )

        finally:
            if os.path.exists(temp_tts_dir):
                try:
                    shutil.rmtree(temp_tts_dir, ignore_errors=True)
                except OSError:
                    pass

    def _handle_cancellation(self) -> None:
        """Handles graceful cancellation updates."""
        if self.state is not None:
            with self.state.lock:
                self.state.generation.status = GenerationStatus.CANCELLED
                self.state.audio.status = SynthesisStatus.CANCELLED
        self.post_event(TUIEventType.GEN_CANCELLED, payload={"mode": self.mode})
        self.post_event(TUIEventType.TTS_CANCELLED, payload={})


# ==============================================================================
# Standalone Piper TTS & Stitching Worker
# ==============================================================================


class TTSSynthesisWorker(BaseWorker):
    """
    Dedicated worker thread for synthesizing pre-parsed dialogue turns into audio
    and stitching into a master MP3 with zero external FFmpeg dependencies.
    """

    def __init__(
        self,
        dialogue: list[DialogueTurn],
        language: str = "nb-NO",
        speed_rate: str = "+0%",
        output_dir: str = "./output",
        state: TUIState | None = None,
        event_queue: TUIEventQueue | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__(
            state=state,
            event_queue=event_queue,
            cancel_event=cancel_event,
            name="TTSSynthesisWorker",
        )
        self.dialogue: list[DialogueTurn] = dialogue
        self.language: str = normalize_language_code(language)
        self.speed_rate: str = speed_rate
        self.output_dir: str = output_dir
        self.temp_turn_files: list[str] = []

    def run(self) -> None:
        if self.is_cancelled():
            return

        if not self.dialogue:
            err_msg = "No dialogue turns provided for synthesis."
            if self.state is not None:
                with self.state.lock:
                    self.state.audio.status = SynthesisStatus.FAILED
                    self.state.audio.synthesis_error = err_msg
            self.post_event(TUIEventType.TTS_FAILED, payload={"error": err_msg}, error=err_msg)
            return

        self._set_busy(True, "Synthesizing dialogue audio")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        os.makedirs(self.output_dir, exist_ok=True)

        if self.state is not None:
            with self.state.lock:
                self.state.audio.status = SynthesisStatus.SYNTHESIZING
                self.state.audio.total_turns = len(self.dialogue)
                self.state.audio.current_turn = 0
                self.state.audio.progress_pct = 0.0
                self.state.audio.synthesis_error = None

        self.post_event(
            TUIEventType.TTS_STARTED,
            payload={"total_turns": len(self.dialogue), "language": self.language},
        )

        temp_tts_dir = tempfile.mkdtemp(prefix="localpodcastllmstudio_tts_")

        def tts_progress_cb(curr: int, tot: int) -> None:
            if not self.is_cancelled():
                pct = (curr / max(1, tot)) * 100.0
                turn_speaker = (
                    self.dialogue[curr - 1].speaker if curr <= len(self.dialogue) else "Host"
                )
                if self.state is not None:
                    with self.state.lock:
                        self.state.audio.current_turn = curr
                        self.state.audio.total_turns = tot
                        self.state.audio.current_speaker = turn_speaker
                        self.state.audio.progress_pct = pct

                self.post_event(
                    TUIEventType.TTS_TURN_PROGRESS,
                    payload={
                        "current": curr,
                        "total": tot,
                        "speaker": turn_speaker,
                        "pct": pct,
                    },
                )

        try:
            self.temp_turn_files = synthesize_dialogue_audio(
                dialogue=self.dialogue,
                language=self.language,
                rate=self.speed_rate,
                output_dir=temp_tts_dir,
                progress_cb=tts_progress_cb,
                cancel_event=self.cancel_event,
            )

            if self.is_cancelled():
                raise RuntimeError("Synthesis cancelled by user.")

            if self.state is not None:
                with self.state.lock:
                    self.state.audio.temp_turn_files = self.temp_turn_files

            # Zero-FFmpeg MP3 Stitching
            self.post_event(
                TUIEventType.TTS_STITCH_STARTED,
                payload={"turn_count": len(self.temp_turn_files)},
            )

            output_mp3_path = os.path.join(self.output_dir, f"podcast_{timestamp}.mp3")
            stitch_mp3_files(
                input_files_or_bytes=self.temp_turn_files,
                output_file_path=output_mp3_path,
                silence_duration_ms=350,
                title=f"Podcast {timestamp}",
                artist="LocalPodcastLLMStudio",
            )

            if self.state is not None:
                with self.state.lock:
                    self.state.audio.status = SynthesisStatus.COMPLETED
                    self.state.audio.master_mp3_path = output_mp3_path
                    self.state.player.current_file = output_mp3_path
                    self.state.player.is_loaded = True

            self.post_event(
                TUIEventType.TTS_COMPLETED,
                payload={"mp3_path": output_mp3_path, "turns": len(self.dialogue)},
            )

        except Exception as exc:
            if self.is_cancelled():
                if self.state is not None:
                    with self.state.lock:
                        self.state.audio.status = SynthesisStatus.CANCELLED
                self.post_event(TUIEventType.TTS_CANCELLED, payload={})
            else:
                err_msg = str(exc)
                if self.state is not None:
                    with self.state.lock:
                        self.state.audio.status = SynthesisStatus.FAILED
                        self.state.audio.synthesis_error = err_msg
                self.post_event(
                    TUIEventType.TTS_FAILED,
                    payload={"error": err_msg},
                    error=err_msg,
                )
        finally:
            if os.path.exists(temp_tts_dir):
                try:
                    shutil.rmtree(temp_tts_dir, ignore_errors=True)
                except OSError:
                    pass
            self._set_busy(False)
