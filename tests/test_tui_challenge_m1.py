"""
Adversarial empirical challenge suite for Milestone M1 Rich UI components,
Tokyo Night theme, and terminal lifecycle management.
"""

from __future__ import annotations

import io
import signal
import time
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.errors import MarkupError
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
from tui.terminal import (
    TerminalManager,
    configure_utf8_streams,
    enable_virtual_terminal_processing,
    get_terminal_dimensions,
    restore_console_mode,
)
from tui.theme import (
    TOKYO_NIGHT_THEME,
)


def _render_to_buffer(renderable: object, width: int = 80, height: int = 24) -> str:
    """Helper that renders any Rich renderable into an in-memory UTF-8 text buffer."""
    buf = io.StringIO()
    console = Console(
        file=buf, width=width, height=height, theme=TOKYO_NIGHT_THEME, legacy_windows=False
    )
    console.print(renderable)
    return buf.getvalue()


# ==============================================================================
# Tier 1 & 2: Extreme Terminal Dimension Stress Testing
# ==============================================================================


@pytest.mark.parametrize("width", [10, 20, 40, 80, 160, 500, 1000])
@pytest.mark.parametrize("height", [2, 5, 10, 24, 100, 200])
def test_all_components_render_under_extreme_dimensions(width: int, height: int) -> None:
    """
    Stress-tests all 10 core TUI renderables across a combinatorial matrix of
    extreme terminal widths (10..1000) and heights (2..200).
    """
    components = [
        CardFrame(Text("Card Body"), title="Title", subtitle="Sub"),
        StatusBadge(status="online", text="Connected to Ollama"),
        LabeledSlider("Speed", from_=-10.0, to=15.0, default_value=2.5, width=15),
        TUIProgressBar(
            completed=45.0, total=100.0, description="Pulling Layer", status_text="4.5/10 GB"
        ),
        TimeSlider(current_ms=75000, total_ms=150000, mode_str="Playing"),
        DialogueTurnCard(
            turn_number=1,
            speaker="Host 1",
            text="Hei og velkommen til podcasten!",
            language="nb-NO",
        ),
        DialogueTurnCard(
            turn_number=2, speaker="Host 2", text="Thank you, excited to be here!", language="en-US"
        ),
        ActionableModal(
            title="Warning",
            message="Model missing",
            details="Run ollama pull",
            actions=[
                {"text": "Download", "style": "success"},
                {"text": "Cancel", "style": "danger"},
            ],
        ),
        SectionHeader(title="Configuration", subtitle="Select options", icon="⚙️"),
        HotkeyBar([("1", "Ingest"), ("2", "Ollama"), ("Space", "Play/Pause"), ("Q", "Quit")]),
    ]

    # Populate KeyValueTable
    kv = KeyValueTable()
    kv.add_row("Language", "Norwegian (Bokmål)")
    kv.add_row("Model", "llama3.1:8b")
    kv.add_row("Piper Voice Host 1", "nb_NO-kari-medium")
    components.append(kv)

    for comp in components:
        rendered = _render_to_buffer(comp, width=width, height=height)
        assert isinstance(rendered, str)
        assert len(rendered) > 0


# ==============================================================================
# Tier 2 & 5: Adversarial Payloads & Malicious Content in Dialogue Cards
# ==============================================================================


def test_dialogue_turn_card_giant_payload_100k_characters() -> None:
    """
    Stress-tests DialogueTurnCard with a massive 100,000-character monoblock and
    multi-paragraph text to verify memory bounds and linear render latency.
    """
    # Continuous unbroken monoblock
    giant_monoblock = "A" * 100000
    card_mono = DialogueTurnCard(
        turn_number=1,
        speaker="Host 1",
        text=giant_monoblock,
        language="nb-NO",
        audio_status="Pending",
    )
    t0 = time.perf_counter()
    out_mono = _render_to_buffer(card_mono, width=80)
    latency_mono = time.perf_counter() - t0

    assert "Turn #1" in out_mono
    assert "Host 1 (Kari)" in out_mono
    assert len(out_mono) >= 100000
    assert latency_mono < 2.0  # Render under 2 seconds

    # Giant multi-paragraph payload
    giant_multiline = (
        "Dette er et langt avsnitt med tekst for å simulere en episode.\n\n" * 1500
    ) + "Slutt."
    card_multi = DialogueTurnCard(
        turn_number=2,
        speaker="Host 2",
        text=giant_multiline,
        language="nb-NO",
    )
    t1 = time.perf_counter()
    out_multi = _render_to_buffer(card_multi, width=80)
    latency_multi = time.perf_counter() - t1

    assert "Turn #2" in out_multi
    assert "Host 2 (Ola)" in out_multi
    assert len(out_multi) >= 50000
    assert latency_multi < 2.0


def test_dialogue_turn_card_resilience_to_malicious_and_adversarial_markup() -> None:
    """
    Verifies that DialogueTurnCard does NOT parse raw dialogue as Rich markup,
    safely handling unmatched closing tags, unclosed brackets, null bytes,
    zero-width spaces, and malicious ANSI escapes.
    """
    adversarial_inputs = [
        "[/]",
        "[/bold][/red]",
        "[bold red]Unclosed markup with [italic]nested tags",
        "[color=invalid_color]Malformed tag[/color]",
        "[[[[[[[[brackets]]]]]]]]",
        "\x1b[31;1mANSI RED\x1b[0m \x1b[2J \x1b[?1049h \x1b]0;hacked\x07",
        "\x00\x01\x02\x08\x0b\x0c\x1f\x7f\x00\x00",
        "\u200b\u200c\u200d\ufeff\u2060Zero\u200bWidth\u200bChars",
        "العربية / עברית / 日本語 / 한국어 / 🎙️✨ / 👨‍👩‍👧‍👦 / 👩🏽‍💻",
        "Line 1\r\nLine 2\rLine 3\nLine 4\tTabbed",
    ]

    for idx, payload in enumerate(adversarial_inputs, start=1):
        card = DialogueTurnCard(
            turn_number=idx,
            speaker=f"Host 1 {payload}",
            text=f"Dialogue payload: {payload}",
            language="nb-NO",
            audio_status=f"Status {payload}",
        )
        # Must render cleanly without raising MarkupError or any exception
        rendered = _render_to_buffer(card, width=80)
        assert isinstance(rendered, str)
        assert f"Turn #{idx}" in rendered


def test_card_frame_markup_handling_and_text_safety() -> None:
    """
    Tests CardFrame title and subtitle handling with both plain strings,
    markup strings, and explicit Text instances.
    """
    # Plain strings with standard text
    card1 = CardFrame(Text("Body"), title="Plain Title", subtitle="Plain Subtitle")
    out1 = _render_to_buffer(card1)
    assert "Plain Title" in out1
    assert "Plain Subtitle" in out1

    # Explicit Text objects containing bracketed strings (bypasses markup parsing safely)
    safe_title = Text("[Unclosed Brackets & Tags]")
    safe_subtitle = Text("[/][/bold]")
    card2 = CardFrame(Text("Body"), title=safe_title, subtitle=safe_subtitle)
    out2 = _render_to_buffer(card2)
    assert "[Unclosed Brackets & Tags]" in out2
    assert "[/][/bold]" in out2

    # String title containing unmatched closing tag causes MarkupError
    with pytest.raises(MarkupError):
        card_bad = CardFrame(Text("Body"), title="[/]")
        _render_to_buffer(card_bad)


def test_actionable_modal_adversarial_matrix() -> None:
    """
    Tests ActionableModal across modal types, button styles, long descriptions,
    empty actions, and large button matrices.
    """
    modal_types = ["error", "warning", "info", "prerequisite", "custom_fallback_type"]
    button_styles = [
        "primary",
        "accent",
        "success",
        "ready",
        "danger",
        "error",
        "secondary",
        "neutral",
        "unknown",
    ]

    for mtype in modal_types:
        actions = [{"text": f"Btn_{s}", "style": s} for s in button_styles[:3]]
        modal = ActionableModal(
            title=f"Modal {mtype.upper()}",
            message="This is a test notification message.",
            details="Detailed remediation instruction step 1.\nStep 2.\nStep 3.",
            actions=actions,
            modal_type=mtype,
            close_text="Dismiss",
            width=80,
        )
        out = _render_to_buffer(modal, width=100)
        assert f"Modal {mtype.upper()}" in out
        assert "This is a test notification message." in out
        assert "Dismiss" in out
        assert "[1]" in out
        assert "[2]" in out
        assert "[3]" in out

    # Test modal with empty actions and None details
    empty_modal = ActionableModal(
        title="Empty Modal", message="Simple info", details=None, actions=[]
    )
    out_empty = _render_to_buffer(empty_modal)
    assert "Empty Modal" in out_empty
    assert "[Esc] Close" in out_empty


# ==============================================================================
# Tier 2: Numeric Boundaries & Clamping on Sliders & Progress Bars
# ==============================================================================


def test_labeled_slider_adversarial_boundaries() -> None:
    """
    Verifies LabeledSlider behavior under inverted limits (from_ > to),
    zero-width track, extreme step counts, and massive clamping values.
    """
    # Inverted boundaries
    slider_inv = LabeledSlider("Inverted", from_=100.0, to=10.0, default_value=50.0, width=10)
    out_inv = _render_to_buffer(slider_inv)
    assert "Inverted" in out_inv

    # Zero and single width
    slider_zero = LabeledSlider("ZeroWidth", from_=0.0, to=10.0, default_value=5.0, width=0)
    out_zero = _render_to_buffer(slider_zero)
    assert "ZeroWidth" in out_zero

    slider_one = LabeledSlider("OneWidth", from_=0.0, to=10.0, default_value=5.0, width=1)
    out_one = _render_to_buffer(slider_one)
    assert "OneWidth" in out_one

    # Extreme value clamping
    slider = LabeledSlider("Speed", from_=-10.0, to=15.0, number_of_steps=5, default_value=0.0)
    slider.set(1e9)
    assert slider.get() == 15.0
    slider.set(-1e9)
    assert slider.get() == -10.0

    # Rapid step up past maximum
    for _ in range(20):
        slider.step_up()
    assert slider.get() == 15.0

    # Rapid step down past minimum
    for _ in range(20):
        slider.step_down()
    assert slider.get() == -10.0


def test_tui_progress_bar_adversarial_boundaries() -> None:
    """
    Verifies TUIProgressBar handling of negative completion, completion > total,
    zero total, zero width, and giant status descriptions.
    """
    # Zero total handled gracefully
    pbar_zero = TUIProgressBar(completed=10.0, total=0.0, width=0)
    out_zero = _render_to_buffer(pbar_zero)
    assert "100%" in out_zero

    # Negative completion clamped to 0%
    pbar_neg = TUIProgressBar(completed=-50.0, total=100.0, width=20)
    out_neg = _render_to_buffer(pbar_neg)
    assert "0%" in out_neg

    # Over-completion clamped to 100%
    pbar_over = TUIProgressBar(completed=500.0, total=100.0, width=20)
    out_over = _render_to_buffer(pbar_over)
    assert "100%" in out_over

    # Giant description and status text
    pbar_giant = TUIProgressBar(
        completed=50.0,
        total=100.0,
        description="X" * 1000,
        status_text="Y" * 1000,
        width=50,
    )
    out_giant = _render_to_buffer(pbar_giant, width=200)
    assert "50%" in out_giant


def test_time_slider_adversarial_timestamps() -> None:
    """
    Verifies TimeSlider timeline scrubber under negative ms, 0/0 ms,
    multi-day millisecond timestamps, and all playback mode variants.
    """
    # 0 / 0 ms
    ts_zero = TimeSlider(current_ms=0, total_ms=0, mode_str="Stopped")
    out_zero = _render_to_buffer(ts_zero)
    assert "00:00 / 00:00" in out_zero
    assert "Stopped" in out_zero

    # Negative current and total ms
    ts_neg = TimeSlider(current_ms=-5000, total_ms=-10000, mode_str="Unknown")
    out_neg = _render_to_buffer(ts_neg)
    assert "00:00 / 00:00" in out_neg

    # 100 hours timestamp formatting (360,000,000 ms = 6000 minutes)
    ts_huge = TimeSlider(current_ms=360000000, total_ms=720000000, mode_str="Playing")
    out_huge = _render_to_buffer(ts_huge)
    assert "6000:00 / 12000:00" in out_huge
    assert "Playing" in out_huge

    # Playback modes
    for mode in ["Playing", "PLAYING", "Paused", "PAUSED", "Stopped", "STOPPED", "Custom"]:
        ts = TimeSlider(current_ms=10000, total_ms=20000, mode_str=mode)
        out = _render_to_buffer(ts)
        assert "00:10 / 00:20" in out


# ==============================================================================
# Tier 3 & 5: TerminalManager Lifecycle, Signals & Reentrancy Stress
# ==============================================================================


def test_terminal_manager_rapid_start_restore_cycles() -> None:
    """
    Stress-tests TerminalManager with 100 rapid sequential start and restore cycles
    to verify deterministic state transitions and absence of handle/state corruption.
    """
    tm = TerminalManager(
        use_alternate_screen=True,
        hide_cursor_on_enter=True,
        install_signal_handlers=True,
    )

    with patch("sys.stdout.write"), patch("sys.stdout.flush"), patch("signal.signal"):
        for _ in range(100):
            assert tm.is_active is False
            assert tm.in_alternate_screen is False
            assert tm.cursor_hidden is False

            tm.start()
            assert tm.is_active is True
            assert tm.in_alternate_screen is True
            assert tm.cursor_hidden is True

            tm.restore()
            assert tm.is_active is False
            assert tm.in_alternate_screen is False
            assert tm.cursor_hidden is False


def test_terminal_manager_idempotency() -> None:
    """
    Verifies that calling start() multiple times or restore() multiple times
    is safe, idempotent, and does not alter terminal manager state.
    """
    tm = TerminalManager(
        use_alternate_screen=True,
        hide_cursor_on_enter=True,
        install_signal_handlers=False,
    )

    with patch("sys.stdout.write"), patch("sys.stdout.flush"):
        # Multiple starts
        res1 = tm.start()
        res2 = tm.start()
        res3 = tm.start()
        assert res1 is tm and res2 is tm and res3 is tm
        assert tm.is_active is True

        # Multiple restores
        tm.restore()
        assert tm.is_active is False
        tm.restore()
        tm.restore()
        assert tm.is_active is False


def test_terminal_manager_signal_trap_behavior() -> None:
    """
    Empirically verifies the signal handling behavior of TerminalManager:
    When a signal (SIGINT/SIGTERM/SIGBREAK) is trapped, TerminalManager restores
    the console and falls through to sys.exit(128 + signum).
    """
    tm = TerminalManager(install_signal_handlers=True)

    with patch("sys.stdout.write"), patch("sys.stdout.flush"), patch("signal.signal"):
        tm.start()
        assert tm.is_active is True

        with patch("sys.exit") as mock_exit:
            tm._handle_signal(signal.SIGINT, None)
            assert tm.is_active is False
            mock_exit.assert_called_once_with(128 + signal.SIGINT)

        # Test SIGTERM
        tm.start()
        with patch("sys.exit") as mock_exit_term:
            tm._handle_signal(signal.SIGTERM, None)
            assert tm.is_active is False
            mock_exit_term.assert_called_once_with(128 + signal.SIGTERM)


def test_terminal_manager_prior_signal_handler_cleared_anomaly() -> None:
    """
    Empirically documents and verifies the finding that _restore_signals()
    clears _prev_signal_handlers before _handle_signal can retrieve 'prev'.
    As a result, custom prior handlers are bypassed and sys.exit is called.
    """
    custom_handler = MagicMock()
    tm = TerminalManager(install_signal_handlers=True)

    with patch("signal.signal") as mock_sig:
        mock_sig.return_value = custom_handler
        tm.start()

        # Prior handler was successfully recorded
        assert tm._prev_signal_handlers.get(signal.SIGINT) == custom_handler

        with patch("sys.exit") as mock_exit:
            tm._handle_signal(signal.SIGINT, None)
            # Demonstrates that custom_handler was not called because restore() cleared the dict
            assert custom_handler.called is False
            mock_exit.assert_called_once_with(128 + signal.SIGINT)


def test_terminal_dimensions_clamping_and_fallback_resilience() -> None:
    """
    Verifies that get_terminal_dimensions() clamps to minimum (20, 10) under
    degenerate OS terminal queries (0x0, negative, or exceptions).
    """
    # Zero dimensions returned by OS
    with patch("shutil.get_terminal_size", return_value=os_terminal_size(0, 0)):
        cols, lines = get_terminal_dimensions()
        assert cols == 20
        assert lines == 10

    # Negative dimensions returned by OS
    with patch("shutil.get_terminal_size", return_value=os_terminal_size(-5, -5)):
        cols, lines = get_terminal_dimensions()
        assert cols == 20
        assert lines == 10

    # Huge dimensions
    with patch("shutil.get_terminal_size", return_value=os_terminal_size(400, 150)):
        cols, lines = get_terminal_dimensions()
        assert cols == 400
        assert lines == 150


class os_terminal_size:
    """Mock helper representing os.terminal_size."""

    def __init__(self, columns: int, lines: int) -> None:
        self.columns = columns
        self.lines = lines


def test_vtp_and_utf8_configuration_resilience() -> None:
    """
    Verifies that configure_utf8_streams() and enable_virtual_terminal_processing()
    handle mock failures gracefully without raising uncaught exceptions.
    """
    # Stream with no reconfigure method
    dummy_stream = object()
    with (
        patch("sys.stdout", dummy_stream),
        patch("sys.stdin", dummy_stream),
        patch("sys.stderr", dummy_stream),
    ):
        res = configure_utf8_streams()
        assert isinstance(res, bool)

    # Windows VTP mock failure path
    with patch("sys.platform", "win32"), patch("ctypes.windll", create=True) as mock_windll:
        mock_kernel32 = MagicMock()
        mock_windll.kernel32 = mock_kernel32
        mock_kernel32.GetStdHandle.return_value = -1  # Invalid handle
        success, orig_mode = enable_virtual_terminal_processing()
        assert success is False
        assert orig_mode is None

    # restore_console_mode with invalid handle or exception
    with patch("sys.platform", "win32"), patch("ctypes.windll", create=True) as mock_windll:
        mock_kernel32 = MagicMock()
        mock_windll.kernel32 = mock_kernel32
        mock_kernel32.GetStdHandle.return_value = -1
        assert restore_console_mode(0x0007) is False
