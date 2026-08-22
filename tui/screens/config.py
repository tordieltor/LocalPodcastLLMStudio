"""
LocalPodcastLLMStudio - Terminal Podcast & Generation Configuration Screen
Provides bilingual language toggle (NB/EN), 4 length presets (Quick, Standard, Deep Dive, Extended),
3 tone presets (Casual, Analytical, Debate), 3 grounding modes (Strict, Creative, Open Topic),
custom host persona names, custom system prompts, fine-grained temperature settings, and TTS speed tuning.
"""

from __future__ import annotations

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

from core.prompts import (
    GROUNDING_MODE_PRESETS,
    TONE_DESCRIPTIONS,
    build_system_prompt,
    get_format_config,
    normalize_grounding_mode,
    normalize_language_code,
)
from tui.components import (
    CardFrame,
    HotkeyBar,
    KeyValueTable,
    LabeledSlider,
    SectionHeader,
)
from tui.input import TextInputPrompt, TextInputResult
from tui.state import TUIEventQueue, TUIEventType, TUIState
from tui.theme import (
    COLOR_ACCENT,
    COLOR_CARD_BORDER,
    COLOR_HOST1,
    COLOR_HOST2,
    COLOR_SUCCESS,
    COLOR_TEXT_DARK,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    GLYPH_GEAR,
)


class ConfigScreen:
    """
    Interactive Terminal Screen for full podcast generation configuration:
    - Language selector (Norwegian Bokmål vs English)
    - 4 Episode length presets with turn bounds and estimated duration
    - 3 Tone & style presets
    - 3 Grounding modes & anti-hallucination levels with dynamic localized explainer
    - Host persona names & Piper TTS neural voice mapping
    - LLM generation temperature & TTS speaking rate adjustment
    - Output directory management and system prompt preview
    """

    LENGTH_KEYS: list[str] = ["quick", "standard", "deep_dive", "extended"]
    TONE_KEYS: list[str] = ["casual", "analytical", "debate"]
    GROUNDING_KEYS: list[str] = ["strict", "creative", "open_topic"]

    def __init__(
        self,
        state: TUIState,
        event_queue: TUIEventQueue | None = None,
    ) -> None:
        self.state: TUIState = state
        self.event_queue: TUIEventQueue | None = event_queue

        self.temperature: float = 0.70
        self.custom_host1_name: str | None = None
        self.custom_host2_name: str | None = None
        self.custom_system_prompt: str | None = None

        self.outdir_prompt: TextInputPrompt = TextInputPrompt(
            initial_value=self.state.config.output_dir,
            placeholder="./output",
            max_length=250,
        )
        self.host1_prompt: TextInputPrompt = TextInputPrompt(
            initial_value=self.state.config.host1_name,
            placeholder="Host 1 Name...",
            max_length=50,
        )
        self.host2_prompt: TextInputPrompt = TextInputPrompt(
            initial_value=self.state.config.host2_name,
            placeholder="Host 2 Name...",
            max_length=50,
        )
        self.prompt_prompt: TextInputPrompt = TextInputPrompt(
            initial_value="",
            placeholder="Custom system prompt...",
            max_length=5000,
        )

        self.is_editing_outdir: bool = False
        self.is_editing_host1: bool = False
        self.is_editing_host2: bool = False
        self.is_editing_prompt: bool = False

        self.speed_slider: LabeledSlider = LabeledSlider(
            label="Speaking Speed",
            from_=-10.0,
            to=15.0,
            number_of_steps=10,
            default_value=self.state.audio.speaking_speed,
            width=20,
        )

        self.status_message: str = "Podcast Configuration Ready"
        self.status_level: str = "info"

    def set_language(self, language: str) -> str:
        """
        Updates generation language and synchronizes voice models and persona names.

        Args:
            language: Language code or name (e.g. 'nb-NO', 'en-US', 'Norwegian').

        Returns:
            str: Normalized language code ('nb-NO' or 'en-US').
        """
        norm_lang = normalize_language_code(language)
        with self.state.lock:
            self.state.config.language = norm_lang
            self.state.sync_voices_with_language()

        self.status_message = f"Language set to {'Norwegian Bokmål (nb-NO)' if norm_lang == 'nb-NO' else 'English (en-US)'}"
        self.status_level = "success"

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.CONFIG_LANGUAGE_CHANGED, payload=norm_lang)

        return norm_lang

    def toggle_language(self) -> str:
        """Toggles between Norwegian Bokmål and English."""
        current = self.state.config.language
        new_lang = "en-US" if "nb" in current.lower() else "nb-NO"
        return self.set_language(new_lang)

    def set_length_preset(self, preset: str) -> str:
        """
        Sets episode length preset from the 4 available presets.

        Args:
            preset: Preset key ('quick', 'standard', 'deep_dive', 'extended').

        Returns:
            str: Selected preset identifier.
        """
        raw = str(preset).lower().strip().replace(" ", "_").replace("-", "_")
        target = raw if raw in self.LENGTH_KEYS else "standard"

        with self.state.lock:
            self.state.config.length_preset = target

        fmt = get_format_config(target)
        self.status_message = (
            f"Length set to {fmt['name']} ({fmt['target_turns']} turns, {fmt['duration']})"
        )
        self.status_level = "success"

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.CONFIG_LENGTH_CHANGED, payload=target)

        return target

    def cycle_length_preset(self) -> str:
        """Cycles to the next length preset in order."""
        cur = self.state.config.length_preset
        idx = self.LENGTH_KEYS.index(cur) if cur in self.LENGTH_KEYS else 1
        next_preset = self.LENGTH_KEYS[(idx + 1) % len(self.LENGTH_KEYS)]
        return self.set_length_preset(next_preset)

    def set_tone_preset(self, tone: str) -> str:
        """
        Sets conversation tone style from the 3 available presets.

        Args:
            tone: Tone style key ('casual', 'analytical', 'debate').

        Returns:
            str: Selected tone key.
        """
        raw = str(tone).lower().strip().replace(" ", "_").replace("-", "_")
        target = raw if raw in self.TONE_KEYS else "casual"

        with self.state.lock:
            self.state.config.tone_preset = target

        tone_dict = TONE_DESCRIPTIONS.get(target, TONE_DESCRIPTIONS["casual"])
        self.status_message = f"Tone set to {tone_dict['name']}"
        self.status_level = "success"

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.CONFIG_TONE_CHANGED, payload=target)

        return target

    def cycle_tone_preset(self) -> str:
        """Cycles to the next tone preset."""
        cur = self.state.config.tone_preset
        idx = self.TONE_KEYS.index(cur) if cur in self.TONE_KEYS else 0
        next_tone = self.TONE_KEYS[(idx + 1) % len(self.TONE_KEYS)]
        return self.set_tone_preset(next_tone)

    def set_grounding_mode(self, mode: str) -> str:
        """
        Sets grounding mode and anti-hallucination level.

        Args:
            mode: Mode key ('strict', 'creative', 'open_topic').

        Returns:
            str: Normalized grounding mode key.
        """
        norm = normalize_grounding_mode(mode)
        with self.state.lock:
            self.state.config.grounding_mode = norm

        preset_data = GROUNDING_MODE_PRESETS.get(norm, GROUNDING_MODE_PRESETS["strict"])
        self.status_message = f"Grounding set to {preset_data['name_en']} ({preset_data['badge']})"
        self.status_level = "success"

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.CONFIG_GROUNDING_CHANGED, payload=norm)

        return norm

    def cycle_grounding_mode(self) -> str:
        """Cycles to the next grounding mode."""
        cur = self.state.config.grounding_mode
        idx = self.GROUNDING_KEYS.index(cur) if cur in self.GROUNDING_KEYS else 0
        next_mode = self.GROUNDING_KEYS[(idx + 1) % len(self.GROUNDING_KEYS)]
        return self.set_grounding_mode(next_mode)

    def set_temperature(self, temp: float) -> float:
        """
        Sets LLM sampling temperature clamped to [0.0, 1.0].

        Args:
            temp: Temperature float value.

        Returns:
            float: Clamped temperature.
        """
        clamped = max(0.0, min(1.0, temp))
        self.temperature = round(clamped, 2)
        self.status_message = f"Temperature set to {self.temperature:.2f}"
        self.status_level = "info"
        return self.temperature

    def adjust_temperature(self, delta: float) -> float:
        """Increments or decrements temperature by delta."""
        return self.set_temperature(self.temperature + delta)

    def set_speaking_speed(self, speed: float) -> float:
        """
        Sets Piper TTS speaking speed percentage clamped to [-10.0, +15.0].

        Args:
            speed: Percentage adjustment.

        Returns:
            float: Clamped speaking speed.
        """
        clamped = max(-10.0, min(15.0, speed))
        with self.state.lock:
            self.state.audio.speaking_speed = clamped
        speed_fmt = f"{int(clamped):+d}%" if clamped.is_integer() else f"{clamped:+.1f}%"
        self.status_message = f"Speaking speed set to {speed_fmt}"
        self.status_level = "info"

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.CONFIG_SPEED_CHANGED, payload=clamped)

        return clamped

    def adjust_speaking_speed(self, delta: float) -> float:
        """Steps speaking speed by delta."""
        cur = self.state.audio.speaking_speed
        return self.set_speaking_speed(cur + delta)

    def set_output_dir(self, path: str) -> str:
        """
        Sets output artifact directory path.

        Args:
            path: Target directory path.

        Returns:
            str: Updated directory path.
        """
        clean = path.strip().strip('"').strip("'") or "./output"
        with self.state.lock:
            self.state.config.output_dir = clean
        self.outdir_prompt.set_value(clean)
        self.status_message = f"Output directory set to '{clean}'"
        self.status_level = "info"

        if self.event_queue:
            self.event_queue.post_event(TUIEventType.CONFIG_OUTPUT_DIR_CHANGED, payload=clean)

        return clean

    def set_host_names(self, host1: str | None, host2: str | None) -> None:
        """
        Sets custom persona display names for Host 1 and Host 2.

        Args:
            host1: Custom Host 1 name or None for default.
            host2: Custom Host 2 name or None for default.
        """
        self.custom_host1_name = host1.strip() if host1 else None
        self.custom_host2_name = host2.strip() if host2 else None
        self.status_message = (
            f"Host names set: Host 1 = {self.get_host1_name()}, Host 2 = {self.get_host2_name()}"
        )
        self.status_level = "info"

    def get_host1_name(self) -> str:
        """Returns the active Host 1 persona name."""
        return self.custom_host1_name or self.state.config.host1_name

    def get_host2_name(self) -> str:
        """Returns the active Host 2 persona name."""
        return self.custom_host2_name or self.state.config.host2_name

    def set_custom_system_prompt(self, prompt: str | None) -> None:
        """Sets custom system prompt override or clears to use standard template."""
        self.custom_system_prompt = prompt.strip() if prompt else None
        if self.custom_system_prompt:
            self.status_message = "Custom system prompt override applied."
        else:
            self.status_message = "Reverted to dynamic bilingual prompt generator."
        self.status_level = "info"

    def get_active_system_prompt(self) -> str:
        """
        Generates or retrieves the complete system prompt for current configuration.

        Returns:
            str: Full LLM system prompt text.
        """
        if self.custom_system_prompt:
            return self.custom_system_prompt

        return build_system_prompt(
            language=self.state.config.language,
            format_type=self.state.config.length_preset,
            tone_style=self.state.config.tone_preset,
            grounding_mode=self.state.config.grounding_mode,
        )

    def get_grounding_description(self) -> str:
        """
        Returns localized explanation of active Grounding Mode.

        Returns:
            str: Localized description string.
        """
        mode = self.state.config.grounding_mode
        preset = GROUNDING_MODE_PRESETS.get(mode, GROUNDING_MODE_PRESETS["strict"])
        is_nb = "nb" in self.state.config.language.lower()
        return str(preset["description_nb"] if is_nb else preset["description_en"])

    def reset_to_defaults(self) -> None:
        """Resets all configuration values to project defaults."""
        with self.state.lock:
            self.state.config.language = "nb-NO"
            self.state.config.length_preset = "standard"
            self.state.config.tone_preset = "casual"
            self.state.config.grounding_mode = "strict"
            self.state.config.output_dir = "./output"
            self.state.audio.speaking_speed = 0.0
            self.state.sync_voices_with_language()

        self.temperature = 0.70
        self.custom_host1_name = None
        self.custom_host2_name = None
        self.custom_system_prompt = None
        self.speed_slider.set(0.0)
        self.outdir_prompt.set_value("./output")

        self.status_message = "All configurations reset to defaults."
        self.status_level = "info"

    def handle_key(self, key: str) -> str | None:
        """
        Handles interactive key events for configuration parameters.

        Args:
            key: Standardized key token.

        Returns:
            Optional[str]: Navigation or action directive.
        """
        if self.is_editing_outdir:
            res: TextInputResult = self.outdir_prompt.handle_key(key)
            if res.action == "submit":
                self.is_editing_outdir = False
                self.set_output_dir(res.value)
                return "outdir:submitted"
            elif res.action == "cancel":
                self.is_editing_outdir = False
                self.status_message = "Output directory edit cancelled."
                return "outdir:cancelled"
            return None

        if self.is_editing_host1:
            res = self.host1_prompt.handle_key(key)
            if res.action == "submit":
                self.is_editing_host1 = False
                self.custom_host1_name = res.value.strip() or None
                return "host1:submitted"
            elif res.action == "cancel":
                self.is_editing_host1 = False
                return "host1:cancelled"
            return None

        if self.is_editing_host2:
            res = self.host2_prompt.handle_key(key)
            if res.action == "submit":
                self.is_editing_host2 = False
                self.custom_host2_name = res.value.strip() or None
                return "host2:submitted"
            elif res.action == "cancel":
                self.is_editing_host2 = False
                return "host2:cancelled"
            return None

        if self.is_editing_prompt:
            res = self.prompt_prompt.handle_key(key)
            if res.action == "submit":
                self.is_editing_prompt = False
                self.set_custom_system_prompt(res.value)
                return "prompt:submitted"
            elif res.action == "cancel":
                self.is_editing_prompt = False
                return "prompt:cancelled"
            return None

        # Standard navigation and configuration shortcuts
        if key == "l":
            self.toggle_language()
            return "config:language"
        elif key == "1":
            self.set_length_preset("quick")
            return "config:length:quick"
        elif key == "2":
            self.set_length_preset("standard")
            return "config:length:standard"
        elif key == "3":
            self.set_length_preset("deep_dive")
            return "config:length:deep_dive"
        elif key == "4":
            self.set_length_preset("extended")
            return "config:length:extended"
        elif key == "f":
            self.cycle_length_preset()
            return "config:length:cycle"
        elif key == "t":
            self.cycle_tone_preset()
            return "config:tone:cycle"
        elif key == "g":
            self.cycle_grounding_mode()
            return "config:grounding:cycle"
        elif key in ("+", "="):
            self.adjust_temperature(+0.05)
            return "config:temp:up"
        elif key in ("-", "_"):
            self.adjust_temperature(-0.05)
            return "config:temp:down"
        elif key in ("]", "}"):
            self.adjust_speaking_speed(+2.5)
            return "config:speed:up"
        elif key in ("[", "{"):
            self.adjust_speaking_speed(-2.5)
            return "config:speed:down"
        elif key == "o":
            self.is_editing_outdir = True
            self.outdir_prompt.set_value(self.state.config.output_dir)
            self.status_message = "Enter output directory (Enter to save, Esc to cancel)..."
            return "outdir:prompt"
        elif key == "p":
            self.is_editing_prompt = True
            self.prompt_prompt.set_value(self.custom_system_prompt or "")
            self.status_message = "Edit custom system prompt (Enter to save, Esc to cancel)..."
            return "prompt:edit"
        elif key == "r":
            self.reset_to_defaults()
            return "config:reset"
        elif key in ("escape", "b", "q"):
            return "navigate:dashboard"

        return None

    def render(self) -> RenderableType:
        """
        Renders the complete Tokyo Night Podcast Configuration Screen.

        Returns:
            rich.console.RenderableType: Composed Rich layout.
        """
        items: list[RenderableType] = []

        # 1. Header
        header = SectionHeader(
            title="Podcast & Generation Settings",
            subtitle="Configure language, personas, episode format, tone, and grounding fidelity",
            icon=GLYPH_GEAR,
        )
        items.append(header)
        items.append(Text(""))

        lang = self.state.config.language
        is_nb = "nb" in lang.lower()

        # 2. Language & Persona Cards Row
        lang_group_items: list[RenderableType] = []

        lang_btn_nb = (
            f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [L] Norwegian Bokmål (Kari & Ola) [/]"
            if is_nb
            else f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [L] Norwegian Bokmål [/]"
        )
        lang_btn_en = (
            f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [L] English (Jenny & Guy) [/]"
            if not is_nb
            else f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [L] English [/]"
        )

        lang_table = Table.grid(padding=(0, 2))
        lang_table.add_row(lang_btn_nb, lang_btn_en)
        lang_group_items.append(lang_table)
        lang_group_items.append(Text(""))

        # Persona Details Table
        h1_name = self.get_host1_name()
        h2_name = self.get_host2_name()
        h1_voice = self.state.audio.host1_voice
        h2_voice = self.state.audio.host2_voice

        persona_table = KeyValueTable()
        persona_table.add_row(
            "Host 1 (Curious Interviewer)", f"[{COLOR_HOST1} bold]{h1_name}[/] (Voice: {h1_voice})"
        )
        persona_table.add_row(
            "Host 2 (Domain Expert)", f"[{COLOR_HOST2} bold]{h2_name}[/] (Voice: {h2_voice})"
        )
        lang_group_items.append(persona_table.__rich__())

        items.append(CardFrame(Group(*lang_group_items), title="Language & Host Personas"))
        items.append(Text(""))

        # 3. Episode Format (Length) & Tone Card
        format_items: list[RenderableType] = []

        cur_length = self.state.config.length_preset
        format_table = Table.grid(padding=(0, 1))

        presets_row: list[str] = []
        for idx, key in enumerate(self.LENGTH_KEYS, start=1):
            cfg = get_format_config(key)
            is_cur = key == cur_length
            if is_cur:
                btn = f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [{idx}] {cfg['name']} ({cfg['target_turns']}t, {cfg['duration']}) [/]"
            else:
                btn = f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] [{idx}] {cfg['name']} [/]"
            presets_row.append(btn)

        format_table.add_row(*presets_row)
        format_items.append(format_table)
        format_items.append(Text(""))

        # Tone Selector Row
        cur_tone = self.state.config.tone_preset
        tone_table = Table.grid(padding=(0, 2))
        tone_row: list[str] = []
        for key in self.TONE_KEYS:
            t_cfg = TONE_DESCRIPTIONS.get(key, TONE_DESCRIPTIONS["casual"])
            is_cur_t = key == cur_tone
            if is_cur_t:
                btn_t = f"[bold {COLOR_TEXT_DARK} on {COLOR_SUCCESS}] [T] {t_cfg['name']} [/]"
            else:
                btn_t = f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] {t_cfg['name']} [/]"
            tone_row.append(btn_t)

        tone_table.add_row(*tone_row)
        format_items.append(
            Text("Tone & Style (Press 'T' to cycle):", style=f"bold {COLOR_TEXT_PRIMARY}")
        )
        format_items.append(tone_table)

        items.append(CardFrame(Group(*format_items), title="Episode Length & Tone Presets"))
        items.append(Text(""))

        # 4. Grounding Mode & Anti-Hallucination Card
        grounding_items: list[RenderableType] = []
        cur_g = self.state.config.grounding_mode

        g_table = Table.grid(padding=(0, 2))
        g_row: list[str] = []
        for key in self.GROUNDING_KEYS:
            g_cfg = GROUNDING_MODE_PRESETS.get(key, GROUNDING_MODE_PRESETS["strict"])
            is_cur_g = key == cur_g
            name = g_cfg["name_nb"] if is_nb else g_cfg["name_en"]
            if is_cur_g:
                btn_g = f"[bold {COLOR_TEXT_DARK} on {COLOR_ACCENT}] [G] {name} [/]"
            else:
                btn_g = f"[{COLOR_TEXT_PRIMARY} on {COLOR_CARD_BORDER}] {name} [/]"
            g_row.append(btn_g)

        g_table.add_row(*g_row)
        grounding_items.append(g_table)
        grounding_items.append(Text(""))

        # Explainer caption banner
        desc = self.get_grounding_description()
        active_preset = GROUNDING_MODE_PRESETS.get(cur_g, GROUNDING_MODE_PRESETS["strict"])
        caption_panel = CardFrame(
            Text(desc, style=COLOR_TEXT_SECONDARY),
            title=f"Anti-Hallucination Directive: {active_preset['badge']}",
            border_style=COLOR_CARD_BORDER,
            padding=(0, 1),
        )
        grounding_items.append(caption_panel.__rich__())

        items.append(CardFrame(Group(*grounding_items), title="Document Grounding & Fidelity Mode"))
        items.append(Text(""))

        # 5. Advanced Tuning Card (Temperature, TTS Speed, Output Dir)
        adv_items: list[RenderableType] = []

        adv_table = Table.grid(padding=(0, 3))
        temp_str = f"{self.temperature:.2f}"
        adv_table.add_row(
            Text.from_markup(
                f"[{COLOR_TEXT_PRIMARY}]Temperature:[/] [bold {COLOR_ACCENT}]{temp_str}[/]  [dim]([+/-] 0.05)[/]"
            ),
            self.speed_slider.render(),
        )
        adv_items.append(adv_table)
        adv_items.append(Text(""))

        if self.is_editing_outdir:
            adv_items.append(
                self.outdir_prompt.render_text(
                    prefix="Output Dir: ",
                    style_text=COLOR_TEXT_PRIMARY,
                    style_cursor=f"reverse bold {COLOR_ACCENT}",
                )
            )
        else:
            out_t = KeyValueTable()
            out_t.add_row(
                "Output Directory", f"{self.state.config.output_dir}  [dim](Press 'O' to edit)[/]"
            )
            adv_items.append(out_t.__rich__())

        items.append(CardFrame(Group(*adv_items), title="Generation Tuning & Output Directory"))
        items.append(Text(""))

        # 6. Hotkey Footer
        hotkeys = HotkeyBar(
            [
                ("L", "Language"),
                ("1-4", "Length"),
                ("T", "Tone"),
                ("G", "Grounding"),
                ("+/-", "Temp"),
                ("[/]", "TTS Speed"),
                ("O", "Output Dir"),
                ("R", "Reset Defaults"),
                ("Esc", "Back to Dashboard"),
            ]
        )
        items.append(hotkeys)

        return Group(*items)

    def __rich__(self) -> RenderableType:
        return self.render()

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.render()
