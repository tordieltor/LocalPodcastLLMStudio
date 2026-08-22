"""
LocalPodcastLLMStudio - Terminal User Interface Main Application Controller
Provides the central TUIApplication coordinating TerminalManager (VTP / Alternate Screen),
InputReader (msvcrt / queue / mock), TUIState container, TUIEventQueue bus, and Rich Live rendering.
"""

from __future__ import annotations

import sys
import time
from typing import Any, cast

from rich.console import Console, RenderableType
from rich.live import Live

from tui.components import ActionableModal
from tui.input import InputReader, create_input_reader
from tui.screens.config import ConfigScreen
from tui.screens.dashboard import DashboardScreen
from tui.screens.generation import GenerationScreen
from tui.screens.help import HelpScreen
from tui.screens.ingestion import IngestionScreen
from tui.screens.ollama_mgr import OllamaManagerScreen
from tui.screens.player import AudioPlayerScreen
from tui.screens.script_studio import ScriptStudioScreen
from tui.state import (
    ModalType,
    ScreenMode,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)
from tui.terminal import TerminalManager, get_terminal_dimensions
from tui.theme import TOKYO_NIGHT_THEME
from tui.workers import OllamaProbeWorker


class TUIApplication:
    """
    Master Application Controller for LocalPodcastLLMStudio Interactive TUI:
    - Manages terminal lifecycle via TerminalManager
    - Polling and translation of keyboard input via InputReader
    - Reactive state model (TUIState) and typed event bus (TUIEventQueue)
    - Screen routing and rendering via rich.live.Live
    - Background worker orchestration and audio playback synchronization
    """

    def __init__(
        self,
        state: TUIState | None = None,
        event_queue: TUIEventQueue | None = None,
        input_reader: InputReader | None = None,
        console: Console | None = None,
        refresh_rate: int = 15,
        auto_probe_ollama: bool = True,
        initial_screen: ScreenMode = ScreenMode.DASHBOARD,
    ) -> None:
        self.state: TUIState = state or TUIState()
        self.event_queue: TUIEventQueue = event_queue or TUIEventQueue()
        self.input_reader: InputReader = input_reader or create_input_reader()
        self.console: Console = console or Console(theme=TOKYO_NIGHT_THEME, legacy_windows=False)
        self.refresh_rate: int = max(1, min(60, refresh_rate))
        self.auto_probe_ollama: bool = auto_probe_ollama
        self.terminal_manager: TerminalManager = TerminalManager()

        self._is_running: bool = False
        self._exit_code: int = 0

        # Initialize screen controllers
        self.dashboard_screen: DashboardScreen = DashboardScreen(self.state, self.event_queue)
        self.ingestion_screen: IngestionScreen = IngestionScreen(self.state, self.event_queue)
        self.ollama_screen: OllamaManagerScreen = OllamaManagerScreen(self.state, self.event_queue)
        self.config_screen: ConfigScreen = ConfigScreen(self.state, self.event_queue)
        self.generation_screen: GenerationScreen = GenerationScreen(self.state, self.event_queue)
        self.script_studio_screen: ScriptStudioScreen = ScriptStudioScreen(
            self.state, self.event_queue
        )
        self.player_screen: AudioPlayerScreen = AudioPlayerScreen(self.state, self.event_queue)
        self.help_screen: HelpScreen = HelpScreen(self.state, self.event_queue)

        self.screens: dict[ScreenMode, Any] = {
            ScreenMode.DASHBOARD: self.dashboard_screen,
            ScreenMode.INGESTION: self.ingestion_screen,
            ScreenMode.OLLAMA: self.ollama_screen,
            ScreenMode.CONFIG: self.config_screen,
            ScreenMode.GENERATION: self.generation_screen,
            ScreenMode.SCRIPT_STUDIO: self.script_studio_screen,
            ScreenMode.PLAYER: self.player_screen,
            ScreenMode.HELP: self.help_screen,
        }

        self.state.ui.active_screen = initial_screen

        # Register event handlers
        self._register_event_subscriptions()

    # ==========================================================================
    # Screen Navigation & Modal Management
    # ==========================================================================

    def navigate_to(self, screen_mode: ScreenMode | str) -> None:
        """
        Navigates the UI to the target screen.

        Args:
            screen_mode: ScreenMode enum or string name.
        """
        target = (
            screen_mode
            if isinstance(screen_mode, ScreenMode)
            else ScreenMode(str(screen_mode).lower())
        )
        with self.state.lock:
            self.state.ui.active_screen = target

    def get_active_screen_instance(self) -> Any:
        """Returns the controller instance of the currently active screen."""
        with self.state.lock:
            mode = self.state.ui.active_screen
        return self.screens.get(mode, self.dashboard_screen)

    def open_modal(self, modal_type: ModalType | str, data: dict[str, Any] | None = None) -> None:
        """Opens a modal overlay dialog."""
        target = (
            modal_type if isinstance(modal_type, ModalType) else ModalType(str(modal_type).lower())
        )
        with self.state.lock:
            self.state.ui.active_modal = target
            self.state.ui.modal_data = data or {}

    def close_modal(self) -> None:
        """Closes the active modal overlay dialog."""
        with self.state.lock:
            self.state.ui.active_modal = ModalType.NONE
            self.state.ui.modal_data.clear()

    # ==========================================================================
    # Event Bus Subscription & Dispatch
    # ==========================================================================

    def _register_event_subscriptions(self) -> None:
        """Subscribes core lifecycle handlers to the central event queue."""
        self.event_queue.subscribe(TUIEventType.NAVIGATE_SCREEN, self._on_navigate_event)
        self.event_queue.subscribe(TUIEventType.OPEN_MODAL, self._on_open_modal_event)
        self.event_queue.subscribe(TUIEventType.CLOSE_MODAL, self._on_close_modal_event)
        self.event_queue.subscribe(TUIEventType.QUIT_REQUESTED, self._on_quit_event)

    def _on_navigate_event(self, event: Any) -> None:
        payload = event.payload or {}
        screen_name = payload.get("screen") if isinstance(payload, dict) else str(payload)
        if screen_name:
            try:
                self.navigate_to(ScreenMode(screen_name))
                if isinstance(payload, dict) and payload.get("auto_start"):
                    # Auto start generation if requested
                    self.generation_screen.start_generation(mode="full")
            except ValueError:
                pass

    def _on_open_modal_event(self, event: Any) -> None:
        payload = event.payload or {}
        modal_name = payload.get("modal") if isinstance(payload, dict) else str(payload)
        data = payload.get("data") if isinstance(payload, dict) else None
        if modal_name:
            try:
                self.open_modal(ModalType(modal_name), data)
            except ValueError:
                pass

    def _on_close_modal_event(self, event: Any) -> None:
        self.close_modal()

    def _on_quit_event(self, event: Any) -> None:
        self.request_quit()

    def process_events(self, max_batch: int = 50) -> list[Any]:
        """
        Drains pending events from the queue and dispatches to registered handlers and active screen.

        Returns:
            List of processed events.
        """
        events = self.event_queue.drain(max_batch_size=max_batch)
        for ev in events:
            # 1. Internal Pub/Sub dispatch
            self.event_queue.dispatch(ev)

            # 2. Forward to all screen controllers that implement handle_event
            for screen in self.screens.values():
                if hasattr(screen, "handle_event"):
                    try:
                        screen.handle_event(ev.event_type, ev.payload)
                    except Exception:  # nosec B110
                        pass

        return events

    # ==========================================================================
    # Key Routing & Application Stepping
    # ==========================================================================

    def handle_global_key(self, key: str) -> bool:
        """
        Handles top-level application navigation hotkeys (F1-F8, Ctrl+C, Ctrl+Q, Quit).

        Args:
            key: Standardized key token.

        Returns:
            bool: True if key was consumed globally.
        """
        k = key.lower().strip()

        # Quit Hotkeys
        if k in ("ctrl+c", "ctrl+q"):
            self.request_quit()
            return True

        # Global Function Keys Screen Switching
        f_map = {
            "f1": ScreenMode.DASHBOARD,
            "f2": ScreenMode.INGESTION,
            "f3": ScreenMode.OLLAMA,
            "f4": ScreenMode.CONFIG,
            "f5": ScreenMode.GENERATION,
            "f6": ScreenMode.SCRIPT_STUDIO,
            "f7": ScreenMode.PLAYER,
            "f8": ScreenMode.HELP,
        }

        if k in f_map:
            self.navigate_to(f_map[k])
            return True

        # Global Quit on Dashboard if not editing
        if k == "q" and self.state.ui.active_screen == ScreenMode.DASHBOARD:
            self.request_quit()
            return True

        return False

    def step(self, key: str | None = None) -> bool:
        """
        Executes a single discrete tick of the application:
        1. Queries dimensions and updates terminal state.
        2. Polls and processes pending background events.
        3. Polls audio player status.
        4. Routes key input to global handler or active screen.

        Args:
            key: Optional simulated key token for automated testing.

        Returns:
            bool: True if application is continuing, False if quit was requested.
        """
        # 1. Update dimensions
        cols, lines = get_terminal_dimensions()
        with self.state.lock:
            self.state.ui.terminal_width = cols
            self.state.ui.terminal_height = lines

        # 2. Process background worker events
        self.process_events()

        # 3. Poll audio playback engine
        self.player_screen.update_player_status()

        # 4. Handle Key Input
        input_key = key if key is not None else self.input_reader.get_key(timeout=0.01)
        if input_key is not None:
            if not self.handle_global_key(input_key):
                active_screen = self.get_active_screen_instance()
                if hasattr(active_screen, "handle_key"):
                    try:
                        active_screen.handle_key(input_key)
                    except Exception as exc:
                        with self.state.lock:
                            self.state.ui.status_message = f"Error handling key: {exc}"
                            self.state.ui.status_level = "error"

        return self._is_running

    # ==========================================================================
    # Live Rendering Protocol
    # ==========================================================================

    def render(self) -> RenderableType:
        """
        Builds the active screen or modal renderable.

        Returns:
            rich.console.RenderableType: Composed Rich layout.
        """
        with self.state.lock:
            modal = self.state.ui.active_modal
            modal_data = dict(self.state.ui.modal_data)

        if modal != ModalType.NONE:
            return ActionableModal(
                title=modal_data.get("title", f"{modal.value.capitalize()} Dialog"),
                message=modal_data.get("message", ""),
                details=modal_data.get("details"),
                modal_type=modal_data.get("type", "info"),
            ).__rich__()

        active_screen = self.get_active_screen_instance()
        return cast(
            RenderableType,
            active_screen.render() if hasattr(active_screen, "render") else active_screen,
        )

    # ==========================================================================
    # Main Application Lifecycle
    # ==========================================================================

    def request_quit(self, exit_code: int = 0) -> None:
        """Signals the main event loop to terminate cleanly."""
        self._is_running = False
        self._exit_code = exit_code

    def run(self) -> int:
        """
        Launches the interactive TUI application inside TerminalManager context.

        Returns:
            int: Process exit code (0 for normal exit).
        """
        self._is_running = True

        # Optional initial probe of Ollama server
        if self.auto_probe_ollama:
            probe_worker = OllamaProbeWorker(
                server_url=self.state.ollama.server_url,
                state=self.state,
                event_queue=self.event_queue,
            )
            probe_worker.start()

        try:
            with self.terminal_manager.start():
                with Live(
                    self.render(),
                    console=self.console,
                    refresh_per_second=self.refresh_rate,
                    transient=False,
                    auto_refresh=False,
                ) as live:
                    while self._is_running:
                        try:
                            self.step()
                            live.update(self.render(), refresh=True)
                            time.sleep(1.0 / self.refresh_rate)
                        except KeyboardInterrupt:
                            self.request_quit()
                            break

        except Exception as exc:
            self._exit_code = 1
            print(f"\n[LocalPodcastLLMStudio Fatal Error]: {exc}", file=sys.stderr)
        finally:
            self.shutdown()

        return self._exit_code

    def shutdown(self) -> None:
        """Releases player handles and restores terminal."""
        try:
            self.player_screen.player.close()
        except Exception:  # nosec B110
            pass
        self.terminal_manager.restore()
