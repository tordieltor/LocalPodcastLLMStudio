"""
Unit tests for tui/components.py: Rich terminal UI components, badges, sliders, cards, modals.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tui.components import (
    ActionableModal,
    CardFrame,
    DialogueTurnCard,
    HotkeyBar,
    KeyValueTable,
    LabeledSlider,
    SectionHeader,
    StatusBadge,
    TimeSlider,
    TUIProgressBar,
)
from tui.theme import (
    BOX_CARD,
    COLOR_SUCCESS,
)


def _render_to_string(renderable: object) -> str:
    """Helper that renders any Rich renderable to a plain string."""
    console = Console(width=100, record=True)
    console.print(renderable)
    return console.export_text()


def test_card_frame_rendering() -> None:
    """Verifies CardFrame wraps contents in a Panel with title and subtitle."""
    card = CardFrame(
        Text("Inner Content"),
        title="My Card",
        subtitle="Subtitle Info",
        box_style=BOX_CARD,
    )
    panel = card.__rich__()
    assert isinstance(panel, Panel)
    output = _render_to_string(card)
    assert "My Card" in output
    assert "Subtitle Info" in output
    assert "Inner Content" in output


def test_status_badge_rendering() -> None:
    """Verifies StatusBadge rendering across status categories and custom overrides."""
    badge = StatusBadge(status="online", text="Ollama Ready")
    assert "Ollama Ready" in badge.render().plain

    badge.set_status("error", "Connection Failed")
    assert "Connection Failed" in badge.render().plain

    badge.set_status("custom", "Custom State", dot_color=COLOR_SUCCESS, dot_glyph="★")
    rendered = badge.render()
    assert "Custom State" in rendered.plain
    assert "★" in rendered.plain


def test_labeled_slider_controls_and_clamping() -> None:
    """Verifies LabeledSlider stepping, clamping, and visual line rendering."""
    slider = LabeledSlider(
        label="Speed Rate",
        from_=-10.0,
        to=15.0,
        number_of_steps=5,
        default_value=0.0,
    )
    assert slider.get() == 0.0

    # Step up (+5.0)
    slider.step_up()
    assert slider.get() == 5.0

    # Step down (-5.0)
    slider.step_down()
    slider.step_down()
    assert slider.get() == -5.0

    # Boundary clamping
    slider.set(50.0)
    assert slider.get() == 15.0
    slider.set(-50.0)
    assert slider.get() == -10.0

    rendered = slider.render()
    assert isinstance(rendered, Text)
    assert "Speed Rate" in rendered.plain
    assert "-10%" in rendered.plain
    assert "+15%" in rendered.plain


def test_tui_progress_bar_metrics() -> None:
    """Verifies TUIProgressBar completion percentage and rendered layout."""
    pbar = TUIProgressBar(completed=25.0, total=100.0, description="Pulling Layer")
    out = _render_to_string(pbar)
    assert "Pulling Layer" in out
    assert "25%" in out

    pbar.update(completed=100.0, status_text="Complete")
    out_complete = _render_to_string(pbar)
    assert "100%" in out_complete
    assert "Complete" in out_complete


def test_time_slider_scrubber() -> None:
    """Verifies TimeSlider timeline formatting and mode indicators."""
    ts = TimeSlider(current_ms=65000, total_ms=130000, mode_str="Playing")
    assert TimeSlider.format_ms(65000) == "01:05"
    assert TimeSlider.format_ms(130000) == "02:10"

    out = _render_to_string(ts)
    assert "Playing" in out
    assert "01:05 / 02:10" in out
    assert "50%" in out

    ts.update_position(0, 130000, mode_str="Paused")
    out_paused = _render_to_string(ts)
    assert "Paused" in out_paused
    assert "00:00 / 02:10" in out_paused


def test_dialogue_turn_card_personas() -> None:
    """Verifies DialogueTurnCard styling for Host 1 (Kari/Jenny) vs Host 2 (Ola/Guy)."""
    # Norwegian Kari
    card_h1_nb = DialogueTurnCard(
        turn_number=1,
        speaker="Host 1",
        text="Velkommen til podcasten!",
        language="nb-NO",
        audio_status="Ready",
    )
    out_h1 = _render_to_string(card_h1_nb)
    assert "Host 1 (Kari)" in out_h1
    assert "Turn #1" in out_h1
    assert "Velkommen til podcasten!" in out_h1

    # English Guy
    card_h2_en = DialogueTurnCard(
        turn_number=2,
        speaker="Host 2",
        text="Glad to be here today!",
        language="en-US",
    )
    out_h2 = _render_to_string(card_h2_en)
    assert "Host 2 (Guy)" in out_h2
    assert "Turn #2" in out_h2
    assert "Glad to be here today!" in out_h2


def test_actionable_modal_rendering() -> None:
    """Verifies ActionableModal layout, remediation details, and button actions."""
    modal = ActionableModal(
        title="Ollama Missing Model",
        message="The requested model 'llama3.1:8b' is not installed locally.",
        details="Run 'ollama pull llama3.1:8b' or click Download Model.",
        actions=[
            {"text": "Download Model", "style": "success"},
            {"text": "Select Other", "style": "secondary"},
        ],
        modal_type="warning",
        close_text="Dismiss",
    )
    out = _render_to_string(modal)
    assert "Ollama Missing Model" in out
    assert "The requested model 'llama3.1:8b' is not installed locally." in out
    assert "Download Model" in out
    assert "Select Other" in out
    assert "Dismiss" in out


def test_section_header_key_value_table_and_hotkey_bar() -> None:
    """Verifies SectionHeader, KeyValueTable, and HotkeyBar render without errors."""
    header = SectionHeader(title="Settings", subtitle="Configure Generation", icon="⚙️")
    out_header = _render_to_string(header)
    assert "Settings" in out_header
    assert "Configure Generation" in out_header

    kv_table = KeyValueTable()
    kv_table.add_row("Model", "llama3.1:8b")
    kv_table.add_row("Language", "Norwegian (Bokmål)")
    assert isinstance(kv_table.__rich__(), Table)
    out_kv = _render_to_string(kv_table)
    assert "Model:" in out_kv
    assert "llama3.1:8b" in out_kv

    hotkeys = HotkeyBar(
        [
            ("1", "Ingestion"),
            ("2", "Ollama"),
            ("3", "Generate"),
            ("Q", "Quit"),
        ]
    )
    out_hk = _render_to_string(hotkeys)
    assert "1" in out_hk
    assert "Ingestion" in out_hk
    assert "Quit" in out_hk
