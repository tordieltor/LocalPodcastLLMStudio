"""
LocalPodcastLLMStudio - Terminal Ollama Manager Screen
Provides server connection probe, model list dropdown/selection with preferred model sorting,
1-click detached background launcher (start_ollama_service), and streaming model downloader
(pull_model_stream) with real-time progress bar, download speed (MB/s), and ETA calculation.
"""

from __future__ import annotations

import threading

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

from core.exceptions import OllamaConnectionError
from core.ollama import (
    ModelPullProgress,
    OllamaClient,
    _validate_url,
    find_ollama_binary,
    pull_model_stream,
    start_ollama_service,
)
from tui.components import (
    CardFrame,
    HotkeyBar,
    KeyValueTable,
    SectionHeader,
    StatusBadge,
    TUIProgressBar,
)
from tui.input import TextInputPrompt, TextInputResult
from tui.state import (
    OllamaStatus,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.theme import (
    BOX_SQUARE,
    COLOR_ACCENT,
    COLOR_BUTTON_CLOSE,
    COLOR_BUTTON_DANGER,
    COLOR_BUTTON_SECONDARY,
    COLOR_BUTTON_SUCCESS,
    COLOR_CARD_BORDER,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    GLYPH_GEAR,
    GLYPH_WARN,
)

PREFERRED_MODELS: list[str] = [
    "llama3.1:8b",
    "llama3.1",
    "mistral-nemo:latest",
    "mistral-nemo",
    "qwen2.5:7b",
    "qwen2.5",
    "llama3:8b",
    "llama3",
    "mistral:latest",
    "mistral",
    "gemma2:9b",
    "gemma2",
    "phi3:medium",
    "phi3",
]


def sort_models_by_preference(models: list[str]) -> list[str]:
    """
    Sorts Ollama model tags prioritizing recommended models first, then alphabetical.

    Args:
        models: List of installed model tags.

    Returns:
        List[str]: Ranked and sorted model list.
    """

    def _rank(m: str) -> tuple[int, str]:
        m_lower = m.lower()
        for idx, pref in enumerate(PREFERRED_MODELS):
            if pref == m_lower:
                return (idx, m_lower)
            if pref in m_lower:
                return (idx + 100, m_lower)
        return (1000, m_lower)

    return sorted(models, key=_rank)


class OllamaManagerScreen:
    """
    Interactive Terminal Screen for local Ollama LLM management:
    1. Server health probe and dynamic URL configuration.
    2. Model catalog inspection, preferred sorting, and active model selection.
    3. 1-Click detached background daemon startup.
    4. Streaming model downloader with speed (MB/s), ETA (MM:SS), and cancel support.
    """

    def __init__(
        self,
        state: TUIState,
        event_queue: TUIEventQueue | None = None,
        server_url: str | None = None,
    ) -> None:
        self.state: TUIState = state
        self.event_queue: TUIEventQueue | None = event_queue

        initial_url = server_url or self.state.ollama.server_url
        try:
            clean_url = _validate_url(initial_url)
        except ValueError:
            clean_url = "http://localhost:11434"

        with self.state.lock:
            self.state.ollama.server_url = clean_url

        self.client: OllamaClient = OllamaClient(base_url=clean_url)

        self.url_prompt: TextInputPrompt = TextInputPrompt(
            initial_value=clean_url, placeholder="http://localhost:11434", max_length=200
        )
        self.pull_prompt: TextInputPrompt = TextInputPrompt(
            initial_value="llama3.1:8b",
            placeholder="Enter model tag (e.g. llama3.1:8b)...",
            max_length=100,
        )

        self.is_editing_url: bool = False
        self.is_editing_pull: bool = False
        self.selected_index: int = 0

        self.pull_thread: threading.Thread | None = None
        self.pull_cancel_event: threading.Event | None = None
        self.launcher_thread: threading.Thread | None = None

        self.status_message: str = "Ollama Manager Ready"
        self.status_level: str = "info"

    def set_server_url(self, url: str, probe: bool = True) -> tuple[bool, str]:
        """
        Updates Ollama server endpoint and optionally probes connectivity.

        Args:
            url: Target Ollama base URL.
            probe: Whether to immediately run a health check.

        Returns:
            Tuple[bool, str]: (success, status_or_error_message).
        """
        try:
            clean_url = _validate_url(url)
        except ValueError as err:
            err_msg = str(err)
            self.status_message = err_msg
            self.status_level = "error"
            return False, err_msg

        with self.state.lock:
            self.state.ollama.server_url = clean_url
        self.client = OllamaClient(base_url=clean_url)
        self.url_prompt.set_value(clean_url)

        if probe:
            is_online = self.probe_connection()
            if is_online:
                self.refresh_models()
                return True, f"Connected to Ollama at {clean_url}"
            return False, f"Ollama is offline at {clean_url}"

        return True, f"Server URL set to {clean_url}"

    def probe_connection(self, timeout: float = 3.0) -> bool:
        """
        Probes the Ollama endpoint and updates connection state.

        Args:
            timeout: Connection timeout in seconds.

        Returns:
            bool: True if reachable, False otherwise.
        """
        with self.state.lock:
            self.state.ollama.status = OllamaStatus.CHECKING

        is_online = self.client.check_connection(timeout=timeout)

        with self.state.lock:
            self.state.ollama.is_online = is_online
            if is_online:
                if self.state.ollama.status != OllamaStatus.PULLING:
                    self.state.ollama.status = OllamaStatus.ONLINE
                self.state.ollama.error_message = None
            else:
                if self.state.ollama.status != OllamaStatus.STARTING:
                    self.state.ollama.status = OllamaStatus.OFFLINE
                self.state.ollama.error_message = "Ollama service is unreachable."

        if self.event_queue:
            self.event_queue.post_event(
                TUIEventType.OLLAMA_STATUS_UPDATE,
                payload={
                    "connected": is_online,
                    "server_url": self.state.ollama.server_url,
                    "status": self.state.ollama.status.value,
                },
            )

        return is_online

    def refresh_models(self, timeout: float = 5.0) -> list[str]:
        """
        Queries installed Ollama models, ranks by preference, and updates state.

        Args:
            timeout: Query timeout in seconds.

        Returns:
            List[str]: List of installed model tags.
        """
        try:
            raw_models = self.client.list_models(timeout=timeout)
            sorted_models = sort_models_by_preference(raw_models)

            with self.state.lock:
                self.state.ollama.is_online = True
                if self.state.ollama.status != OllamaStatus.PULLING:
                    self.state.ollama.status = OllamaStatus.ONLINE
                self.state.ollama.available_models = sorted_models
                self.state.ollama.has_recommended = any(
                    "llama3.1" in m.lower() for m in sorted_models
                )
                self.state.ollama.auto_select_model()
                self.state.ollama.error_message = None

            # Keep index in bounds
            if self.selected_index >= len(sorted_models):
                self.selected_index = max(0, len(sorted_models) - 1)

            self.status_message = f"Found {len(sorted_models)} installed model(s)"
            self.status_level = "success"

            if self.event_queue:
                self.event_queue.post_event(
                    TUIEventType.OLLAMA_MODELS_LOADED, payload=sorted_models
                )

            return sorted_models

        except (OllamaConnectionError, TimeoutError, OSError) as err:
            err_msg = str(err)
            with self.state.lock:
                self.state.ollama.is_online = False
                self.state.ollama.status = OllamaStatus.OFFLINE
                self.state.ollama.available_models = []
                self.state.ollama.selected_model = ""
                self.state.ollama.has_recommended = False
                self.state.ollama.error_message = err_msg

            self.status_message = f"Cannot fetch models: {err_msg}"
            self.status_level = "error"

            if self.event_queue:
                self.event_queue.post_event(
                    TUIEventType.OLLAMA_STATUS_UPDATE,
                    payload={"connected": False, "error": err_msg},
                )

            return []

    def select_model(self, model_name: str) -> bool:
        """
        Selects an active model tag from available installed models.

        Args:
            model_name: Target model tag name.

        Returns:
            bool: True if selected successfully, False if not in available models.
        """
        with self.state.lock:
            if model_name in self.state.ollama.available_models:
                self.state.ollama.selected_model = model_name
                self.selected_index = self.state.ollama.available_models.index(model_name)
                success = True
            else:
                success = False

        if success:
            self.status_message = f"Active model set to '{model_name}'"
            self.status_level = "success"
            if self.event_queue:
                self.event_queue.post_event(TUIEventType.OLLAMA_MODEL_SELECTED, payload=model_name)
            return True

        return False

    def select_next_model(self) -> str | None:
        """Navigates to the next model in the list."""
        with self.state.lock:
            models = self.state.ollama.available_models
            if not models:
                return None
            self.selected_index = (self.selected_index + 1) % len(models)
            selected = models[self.selected_index]
            self.state.ollama.selected_model = selected

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.OLLAMA_MODEL_SELECTED, payload=selected)
        return selected

    def select_prev_model(self) -> str | None:
        """Navigates to the previous model in the list."""
        with self.state.lock:
            models = self.state.ollama.available_models
            if not models:
                return None
            self.selected_index = (self.selected_index - 1) % len(models)
            selected = models[self.selected_index]
            self.state.ollama.selected_model = selected

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.OLLAMA_MODEL_SELECTED, payload=selected)
        return selected

    def start_service(self, timeout: float = 10.0, async_launch: bool = False) -> tuple[bool, str]:
        """
        Launches the local Ollama daemon service in the background.

        Args:
            timeout: Startup wait timeout in seconds.
            async_launch: Whether to execute launcher in a background thread.

        Returns:
            Tuple[bool, str]: (success, status_or_error_message).
        """
        with self.state.lock:
            self.state.ollama.status = OllamaStatus.STARTING
        self.status_message = "Launching Ollama background service..."
        self.status_level = "warning"

        if self.event_queue:
            self.event_queue.post_event(
                TUIEventType.OLLAMA_SERVICE_LAUNCHING, payload={"status": "launching"}
            )

        def _run_launch() -> tuple[bool, str]:
            success, msg = start_ollama_service(
                timeout=timeout, base_url=self.state.ollama.server_url
            )
            with self.state.lock:
                if success:
                    self.state.ollama.is_online = True
                    self.state.ollama.status = OllamaStatus.ONLINE
                    self.state.ollama.daemon_running = True
                    self.state.ollama.error_message = None
                else:
                    self.state.ollama.is_online = False
                    self.state.ollama.status = OllamaStatus.ERROR
                    self.state.ollama.error_message = msg

            if success:
                self.refresh_models()
                self.status_message = f"Ollama service started: {msg}"
                self.status_level = "success"
                if self.event_queue:
                    self.event_queue.post_event(
                        TUIEventType.OLLAMA_SERVICE_STARTED,
                        payload={"status": msg, "models": self.state.ollama.available_models},
                    )
            else:
                self.status_message = f"Failed to start Ollama: {msg}"
                self.status_level = "error"
                if self.event_queue:
                    self.event_queue.post_event(
                        TUIEventType.OLLAMA_SERVICE_ERROR, error=msg, payload={"error": msg}
                    )

            return success, msg

        if async_launch:
            self.launcher_thread = threading.Thread(target=_run_launch, daemon=True)
            self.launcher_thread.start()
            return True, "Ollama service launch initiated in background."
        else:
            return _run_launch()

    def pull_model(
        self,
        model_name: str,
        async_pull: bool = False,
        timeout: float = 3600.0,
    ) -> bool:
        """
        Pulls an LLM model tag with streaming real-time progress callbacks.

        Args:
            model_name: Target model tag name (e.g. 'llama3.1:8b').
            async_pull: Whether to execute pull in a background thread.
            timeout: Max pull operation timeout in seconds.

        Returns:
            bool: True on successful completion (or start if async), False otherwise.
        """
        clean_model = model_name.strip()
        if not clean_model:
            self.status_message = "Model name cannot be empty."
            self.status_level = "error"
            return False

        self.pull_cancel_event = threading.Event()

        with self.state.lock:
            self.state.ollama.status = OllamaStatus.PULLING
            self.state.ollama.pull_model_name = clean_model
            self.state.ollama.pull_progress = ModelPullProgress(
                status=f"Connecting to pull {clean_model}...",
                is_done=False,
            )

        self.status_message = f"Downloading model '{clean_model}'..."
        self.status_level = "info"

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.OLLAMA_PULL_START, payload=clean_model)

        def _progress_cb(prog: ModelPullProgress) -> None:
            with self.state.lock:
                self.state.ollama.pull_progress = prog
            if self.event_queue:
                self.event_queue.post_event(TUIEventType.OLLAMA_PULL_PROGRESS, payload=prog)

        def _run_pull() -> bool:
            try:
                success = pull_model_stream(
                    model=clean_model,
                    base_url=self.state.ollama.server_url,
                    progress_callback=_progress_cb,
                    cancel_event=self.pull_cancel_event,
                    timeout=timeout,
                )
                if success:
                    with self.state.lock:
                        self.state.ollama.status = OllamaStatus.ONLINE
                        self.state.ollama.pull_progress = None
                    self.refresh_models()
                    self.select_model(clean_model)
                    self.status_message = f"Model '{clean_model}' downloaded successfully!"
                    self.status_level = "success"
                    if self.event_queue:
                        self.event_queue.post_event(
                            TUIEventType.OLLAMA_PULL_DONE,
                            payload={"model": clean_model, "message": "Success"},
                        )
                    return True
                return False
            except Exception as ex:
                is_cancelled = self.pull_cancel_event and self.pull_cancel_event.is_set()
                err_msg = str(ex)
                with self.state.lock:
                    self.state.ollama.status = (
                        OllamaStatus.ONLINE if self.state.ollama.is_online else OllamaStatus.OFFLINE
                    )
                    self.state.ollama.pull_progress = None
                    self.state.ollama.error_message = err_msg

                if is_cancelled:
                    self.status_message = f"Download of '{clean_model}' cancelled."
                    self.status_level = "warning"
                    if self.event_queue:
                        self.event_queue.post_event(
                            TUIEventType.OLLAMA_PULL_CANCELLED, payload={"model": clean_model}
                        )
                else:
                    self.status_message = f"Download failed: {err_msg}"
                    self.status_level = "error"
                    if self.event_queue:
                        self.event_queue.post_event(
                            TUIEventType.OLLAMA_PULL_ERROR,
                            error=err_msg,
                            payload={"model": clean_model, "error": err_msg},
                        )
                return False

        if async_pull:
            self.pull_thread = threading.Thread(target=_run_pull, daemon=True)
            self.pull_thread.start()
            return True
        else:
            return _run_pull()

    def cancel_pull(self) -> None:
        """Signals cancellation to active streaming model pull worker."""
        if self.pull_cancel_event:
            self.pull_cancel_event.set()
        self.status_message = "Cancelling model download..."
        self.status_level = "warning"

    def handle_key(self, key: str) -> str | None:
        """
        Processes interactive key events.

        Args:
            key: Standardized key token.

        Returns:
            Optional[str]: Navigation or action directive.
        """
        if self.is_editing_url:
            res: TextInputResult = self.url_prompt.handle_key(key)
            if res.action == "submit":
                self.is_editing_url = False
                self.set_server_url(res.value, probe=True)
                return "url:submitted"
            elif res.action == "cancel":
                self.is_editing_url = False
                self.status_message = "URL editing cancelled."
                return "url:cancelled"
            return None

        if self.is_editing_pull:
            res = self.pull_prompt.handle_key(key)
            if res.action == "submit":
                self.is_editing_pull = False
                target_model = res.value.strip() or "llama3.1:8b"
                self.pull_model(target_model, async_pull=True)
                return "pull:started"
            elif res.action == "cancel":
                self.is_editing_pull = False
                self.status_message = "Pull cancelled."
                return "pull:cancelled"
            return None

        # Standard navigation
        if key == "s":
            self.start_service(async_launch=True)
            return "action:start_service"
        elif key == "r":
            self.refresh_models()
            return "action:refresh"
        elif key in ("p", "d"):
            if self.state.ollama.status == OllamaStatus.PULLING:
                self.status_message = "Model pull already in progress. Press 'C' to cancel."
                return None
            self.is_editing_pull = True
            self.pull_prompt.set_value(self.state.ollama.recommended_model)
            self.status_message = "Enter model name to pull (Enter to download, Esc to cancel)..."
            return "pull:prompt"
        elif key in ("up", "k"):
            self.select_prev_model()
            return "select:prev"
        elif key in ("down", "j"):
            self.select_next_model()
            return "select:next"
        elif key == "u":
            self.is_editing_url = True
            self.url_prompt.set_value(self.state.ollama.server_url)
            self.status_message = "Edit server URL (Enter to probe, Esc to cancel)..."
            return "url:prompt"
        elif key in ("c", "x"):
            if self.state.ollama.status == OllamaStatus.PULLING:
                self.cancel_pull()
                return "pull:cancelled"
        elif key in ("escape", "b", "q"):
            return "navigate:dashboard"

        return None

    def render(self) -> RenderableType:
        """
        Renders the complete Tokyo Night Ollama Manager Screen.

        Returns:
            rich.console.RenderableType: Composed Rich layout.
        """
        items: list[RenderableType] = []

        # 1. Header with Connection Status Badge
        is_online = self.state.ollama.is_online
        status_enum = self.state.ollama.status

        badge_status = (
            "online"
            if is_online and status_enum == OllamaStatus.ONLINE
            else (
                "downloading"
                if status_enum == OllamaStatus.PULLING
                else ("starting" if status_enum == OllamaStatus.STARTING else "offline")
            )
        )
        badge_text = (
            f"Online ({len(self.state.ollama.available_models)} models)"
            if is_online
            else (
                "Downloading..."
                if status_enum == OllamaStatus.PULLING
                else ("Starting Service..." if status_enum == OllamaStatus.STARTING else "Offline")
            )
        )

        header = SectionHeader(
            title="Ollama Local LLM Service & Model Manager",
            subtitle="Manage local Ollama server connection, daemon lifecycle, and models",
            icon=GLYPH_GEAR,
        )
        items.append(header)
        items.append(Text(""))

        # Status Banner
        top_table = Table.grid(padding=(0, 2))
        badge = StatusBadge(status=badge_status, text=badge_text)
        top_table.add_row(
            badge.render(),
            Text.from_markup(
                f"[{COLOR_TEXT_SECONDARY}]Endpoint:[/] [bold {COLOR_ACCENT}]{self.state.ollama.server_url}[/]"
            ),
        )
        items.append(top_table)
        items.append(Text(""))

        # 2. Server Connection & Controls Card
        conn_items: list[RenderableType] = []
        if self.is_editing_url:
            conn_items.append(
                self.url_prompt.render_text(
                    prefix="Server URL: ",
                    style_text=COLOR_TEXT_PRIMARY,
                    style_cursor=f"reverse bold {COLOR_ACCENT}",
                )
            )
        else:
            conn_table = KeyValueTable()
            conn_table.add_row("Server URL", self.state.ollama.server_url)
            conn_table.add_row("Service Status", status_enum.value.upper())
            bin_path = find_ollama_binary()
            conn_table.add_row("Binary Path", bin_path or "Not found on PATH")
            conn_items.append(conn_table.__rich__())

        btn_row = Table.grid(padding=(0, 2))
        start_btn = (
            f"[bold {COLOR_TEXT_DARK} on {COLOR_BUTTON_SUCCESS}] [S] Start Ollama Service [/]"
            if not is_online
            else f"[{COLOR_TEXT_MUTED} on {COLOR_CARD_BORDER}] [S] Service Running [/]"
        )
        refresh_btn = (
            f"[bold {COLOR_TEXT_PRIMARY} on {COLOR_BUTTON_SECONDARY}] [R] Refresh Models [/]"
        )
        pull_btn = f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [P] Pull / Download Model [/]"
        url_btn = f"[{COLOR_TEXT_PRIMARY} on {COLOR_BUTTON_CLOSE}] [U] Edit URL [/]"

        btn_row.add_row(start_btn, refresh_btn, pull_btn, url_btn)
        conn_items.append(Text(""))
        conn_items.append(btn_row)

        items.append(CardFrame(Group(*conn_items), title="Ollama Server & Connection"))
        items.append(Text(""))

        # 3. Streaming Model Pull Card (if pulling or editing pull)
        if self.is_editing_pull:
            pull_prompt_group = Group(
                Text(
                    "Enter the Ollama model tag you wish to pull from library:",
                    style=COLOR_TEXT_PRIMARY,
                ),
                self.pull_prompt.render_text(
                    prefix="Model: ",
                    style_text=COLOR_TEXT_PRIMARY,
                    style_cursor=f"reverse bold {COLOR_ACCENT}",
                ),
            )
            items.append(CardFrame(pull_prompt_group, title="Download New Model (api/pull)"))
            items.append(Text(""))

        elif status_enum == OllamaStatus.PULLING and self.state.ollama.pull_progress:
            prog = self.state.ollama.pull_progress
            pull_items: list[RenderableType] = []
            pull_items.append(
                Text.from_markup(
                    f"Pulling model: [bold {COLOR_ACCENT}]{self.state.ollama.pull_model_name}[/]  "
                    f"[{COLOR_TEXT_SECONDARY}]Status:[/] [bold {COLOR_INFO}]{prog.status}[/]"
                )
            )

            p_bar = TUIProgressBar(
                completed=float(prog.completed),
                total=float(prog.total) if prog.total > 0 else 100.0,
                description="Progress:",
                status_text=prog.progress_str or None,
                width=35,
            )
            pull_items.append(p_bar.__rich__())

            # Speed & ETA
            metrics_table = Table.grid(padding=(0, 2))
            speed_txt = prog.speed_str or "Calculating..."
            eta_txt = prog.eta_str or "--:--"
            metrics_table.add_row(
                Text(f"Speed: {speed_txt}", style=f"bold {COLOR_INFO}"),
                Text(f"ETA: {eta_txt}", style=f"bold {COLOR_WARNING}"),
                Text("[C] Cancel Download", style=COLOR_BUTTON_DANGER),
            )
            pull_items.append(metrics_table)

            items.append(CardFrame(Group(*pull_items), title="Live Model Download Stream"))
            items.append(Text(""))

        # 4. Installed Models Catalog Card
        models = self.state.ollama.available_models
        models_group_items: list[RenderableType] = []

        if not is_online:
            models_group_items.append(
                Text(
                    f"{GLYPH_WARN} Ollama service is offline. Press 'S' to launch the background service.",
                    style=COLOR_WARNING,
                )
            )
        elif not models:
            models_group_items.append(
                Text(
                    f"{GLYPH_WARN} No LLM models found in local Ollama library. Press 'P' to pull '{self.state.ollama.recommended_model}'.",
                    style=COLOR_WARNING,
                )
            )
        else:
            model_table = Table(
                box=BOX_SQUARE,
                expand=True,
                show_header=True,
                header_style=f"bold {COLOR_ACCENT}",
                border_style=COLOR_CARD_BORDER,
            )
            model_table.add_column("Sel", width=4, justify="center")
            model_table.add_column("Model Tag", style=COLOR_TEXT_PRIMARY)
            model_table.add_column("Type / Tier", style=COLOR_TEXT_SECONDARY)
            model_table.add_column("Recommended", width=16, justify="center")

            selected_model = self.state.ollama.selected_model

            for _idx, m in enumerate(models):
                is_selected = m == selected_model
                sel_glyph = f"[bold {COLOR_ACCENT}]▶[/]" if is_selected else " "
                tag_style = f"bold {COLOR_ACCENT}" if is_selected else COLOR_TEXT_PRIMARY

                is_rec = any(pref in m.lower() for pref in ("llama3.1", "qwen2.5", "mistral-nemo"))
                rec_badge = f"[bold {COLOR_SUCCESS}]★ Recommended[/]" if is_rec else ""

                tier = (
                    "8B Parameters"
                    if "8b" in m.lower()
                    else ("7B Parameters" if "7b" in m.lower() else "LLM")
                )

                model_table.add_row(sel_glyph, f"[{tag_style}]{m}[/]", tier, rec_badge)

            models_group_items.append(model_table)
            models_group_items.append(
                Text(
                    f"Use [↑/↓] or [K/J] to select model. Currently active: '{selected_model or 'None'}'",
                    style=COLOR_TEXT_SECONDARY,
                )
            )

        items.append(CardFrame(Group(*models_group_items), title="Installed Models Catalog"))
        items.append(Text(""))

        # 5. Hotkey Footer
        hotkeys = HotkeyBar(
            [
                ("S", "Start Service"),
                ("R", "Refresh"),
                ("P", "Pull Model"),
                ("↑/↓", "Select Model"),
                ("U", "Change URL"),
                ("Esc", "Back to Dashboard"),
            ]
        )
        items.append(hotkeys)

        return Group(*items)

    def __rich__(self) -> RenderableType:
        return self.render()

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.render()
