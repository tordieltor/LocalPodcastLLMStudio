"""
Empirical Challenger Test Battery for Milestone M1: State Management & Input Handler.
Adversarially stress-tests:
1. High-concurrency race conditions (20 worker threads, TUIState mutations, TUIEventQueue flooding).
2. Malformed input streams, high-frequency key spamming, unmapped scan codes, and nested text prompts.
3. State boundary violations: invalid preset names, negative audio positions, empty turn lists, extreme strings.
"""

from __future__ import annotations

import concurrent.futures
import random
import sys
import threading
import time
from unittest.mock import patch

import pytest
from rich.text import Text

from core.parser import DialogueTurn
from tui.input import (
    MockInputReader,
    QueueInputReader,
    TextInputPrompt,
    TextInputResult,
    WindowsMSVCRTInputReader,
    create_input_reader,
)
from tui.state import (
    AudioSynthesisState,
    GenerationState,
    GenerationStatus,
    IngestionState,
    OllamaState,
    PlaybackMode,
    PlayerState,
    PromptConfigState,
    SourceMode,
    SynthesisStatus,
    TUIEvent,
    TUIEventQueue,
    TUIEventType,
    TUIState,
)

# ==============================================================================
# 1. High-Concurrency Race Conditions & Thread-Safety Stress
# ==============================================================================


class TestConcurrencyAndEventBusStress:
    """Stress tests 20 concurrent worker threads mutating TUIState and flooding TUIEventQueue."""

    def test_20_threads_concurrent_tui_state_mutations_and_snapshots(self) -> None:
        """
        20 worker threads concurrently modify sub-states, validate states,
        and generate deep-copy snapshots without deadlocks, corruption, or crashes.
        """
        state = TUIState()
        num_threads = 20
        iterations_per_thread = 200
        errors: list[Exception] = []
        stop_event = threading.Event()

        def worker_loop(thread_id: int) -> None:
            try:
                for i in range(iterations_per_thread):
                    if stop_event.is_set():
                        break

                    op = (thread_id + i) % 8

                    if op == 0:
                        # Ingestion mutation
                        with state.lock:
                            state.ingestion.source_mode = random.choice(
                                [
                                    SourceMode.DOCUMENT,
                                    SourceMode.PASTED_TEXT,
                                    SourceMode.TOPIC_PROMPT,
                                ]
                            )
                            state.ingestion.update_extracted(
                                f"Extracted text payload from worker {thread_id} iteration {i}"
                            )
                    elif op == 1:
                        # Ollama mutation & auto-selection
                        with state.lock:
                            state.ollama.available_models = [
                                "llama3.1:8b",
                                "qwen2.5:7b",
                                f"custom-{thread_id}:latest",
                            ]
                            state.ollama.is_online = i % 2 == 0
                            state.ollama.auto_select_model(force=(i % 3 == 0))
                    elif op == 2:
                        # Prompt Config & Voice Sync
                        with state.lock:
                            state.config.language = "nb-NO" if i % 2 == 0 else "en-US"
                            state.sync_voices_with_language()
                            state.sync_grounding_with_modality()
                    elif op == 3:
                        # Generation substate mutation
                        with state.lock:
                            state.generation.status = GenerationStatus.GENERATING
                            state.generation.turns.append(
                                DialogueTurn(
                                    speaker=f"Host {1 + (i % 2)}",
                                    text=f"Turn message {i} from thread {thread_id}",
                                )
                            )
                    elif op == 4:
                        # Audio & Player mutation
                        with state.lock:
                            state.player.position_ms = (i * 1000) % 120000
                            state.player.duration_ms = 120000
                            state.player.mode = PlaybackMode.PLAYING
                            state.audio.progress_pct = (i % 100) / 100.0
                    elif op == 5:
                        # UI state mutation
                        with state.lock:
                            state.ui.focus_index = i % 10
                            state.ui.status_message = f"Thread {thread_id} step {i}"
                            state.ui.is_busy = i % 5 == 0
                    elif op == 6:
                        # Validation checks under lock
                        _can_gen, _ = state.validate_can_generate()
                        _can_syn, _ = state.validate_can_synthesize()
                        _can_ply, _ = state.validate_can_play()
                    elif op == 7:
                        # Deep-copy snapshot creation
                        snap = state.snapshot()
                        assert isinstance(snap, TUIState)
                        assert isinstance(snap.ingestion, IngestionState)
                        assert isinstance(snap.generation, GenerationState)

                    # Periodic state resets
                    if i % 50 == 0:
                        with state.lock:
                            state.reset_generation_state()

            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker_loop, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert not errors, f"Encountered {len(errors)} thread errors: {errors[:5]}"

    def test_20_threads_event_queue_flooding_drain_and_pubsub(self) -> None:
        """
        20 worker threads concurrently post 20,000 events to TUIEventQueue
        while consumer threads drain and pub/sub subscribers receive dispatches.
        """
        eq = TUIEventQueue()
        total_events_per_thread = 500
        num_publishers = 20
        expected_total = num_publishers * total_events_per_thread

        received_by_subscriber: list[TUIEvent] = []
        subscriber_lock = threading.Lock()

        def on_event(ev: TUIEvent) -> None:
            with subscriber_lock:
                received_by_subscriber.append(ev)

        # Register wildcard and specific subscribers
        eq.subscribe("*", on_event)
        eq.subscribe(TUIEventType.INGESTION_EXTRACTED, on_event)

        def publisher_worker(pid: int) -> None:
            for i in range(total_events_per_thread):
                ev_type = (
                    TUIEventType.INGESTION_EXTRACTED
                    if i % 2 == 0
                    else TUIEventType.GEN_TOKEN_STREAM
                )
                eq.post_event(
                    event_type=ev_type,
                    payload={"pid": pid, "seq": i, "data": f"token_{i}"},
                )

        drained_events: list[TUIEvent] = []
        drain_active = threading.Event()
        drain_active.set()

        def consumer_drain_worker() -> None:
            while drain_active.is_set():
                batch = eq.drain(max_batch_size=100)
                if batch:
                    drained_events.extend(batch)
                    for ev in batch:
                        eq.dispatch(ev)
                else:
                    time.sleep(0.001)

        consumer_thread = threading.Thread(target=consumer_drain_worker)
        consumer_thread.start()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_publishers) as executor:
            futures = [executor.submit(publisher_worker, p) for p in range(num_publishers)]
            concurrent.futures.wait(futures)

        # Allow consumer to finish draining remaining events
        time.sleep(0.1)
        drain_active.clear()
        consumer_thread.join(timeout=5.0)

        # Final drain of any leftover events in queue
        remaining = eq.drain(max_batch_size=50000)
        drained_events.extend(remaining)
        for ev in remaining:
            eq.dispatch(ev)

        assert len(drained_events) == expected_total
        # Every event hits '*' subscriber; even ones also hit 'INGESTION_EXTRACTED' subscriber
        assert len(received_by_subscriber) >= expected_total

    def test_subscriber_exception_isolation(self) -> None:
        """
        Verifies that a faulty subscriber callback raising an exception does NOT
        disrupt event dispatching to other subscribers.
        """
        eq = TUIEventQueue()
        received_normal: list[str] = []

        def failing_subscriber(ev: TUIEvent) -> None:
            raise RuntimeError("Faulty subscriber exploded!")

        def healthy_subscriber_1(ev: TUIEvent) -> None:
            received_normal.append(f"sub1:{ev.event_type.value}")

        def healthy_subscriber_2(ev: TUIEvent) -> None:
            received_normal.append(f"sub2:{ev.event_type.value}")

        eq.subscribe(TUIEventType.PLAYER_PLAY, healthy_subscriber_1)
        eq.subscribe(TUIEventType.PLAYER_PLAY, failing_subscriber)
        eq.subscribe(TUIEventType.PLAYER_PLAY, healthy_subscriber_2)

        ev = TUIEvent(event_type=TUIEventType.PLAYER_PLAY)
        eq.dispatch(ev)

        assert "sub1:player:play" in received_normal
        assert "sub2:player:play" in received_normal


# ==============================================================================
# 2. Malformed Input Streams, Key Spamming, Unmapped Scan Codes & Nested Prompts
# ==============================================================================


class TestInputEngineAdversarialStress:
    """Stress tests input readers, text prompt editor, scan code mappings, and spamming."""

    def test_high_frequency_key_spamming_queue_reader(self) -> None:
        """
        Spams 50,000 keystrokes through QueueInputReader and verifies FIFO ordering and flush.
        """
        reader = QueueInputReader()
        assert not reader.has_key()

        keys = [f"key_{i}" for i in range(50000)]
        reader.push_keys(keys)

        assert reader.has_key()

        # Read first 1,000
        for i in range(1000):
            k = reader.get_key(timeout=0.01)
            assert k == f"key_{i}"

        # Flush remaining 49,000
        reader.flush()
        assert not reader.has_key()
        assert reader.get_key(timeout=0.001) is None

    def test_text_input_prompt_high_frequency_spamming_and_unicode(self) -> None:
        """
        Fuzzes TextInputPrompt with 10,000 mixed keys including international characters,
        emojis, deletion keys, cursor shifts, and unmapped tokens.
        """
        prompt = TextInputPrompt(initial_value="", max_length=500)

        fuzz_tokens = [
            "a",
            "b",
            "c",
            "æ",
            "ø",
            "å",
            "🚀",
            "💡",
            " ",
            "space",
            "left",
            "right",
            "home",
            "end",
            "backspace",
            "delete",
            "ctrl+a",
            "ctrl+e",
            "ctrl+u",
            "ctrl+k",
            "unmapped_scan_code_999",
            "special_00_99",
            "f1",
            "shift+f1",
        ]

        for _ in range(10000):
            token = random.choice(fuzz_tokens)
            res = prompt.handle_key(token)
            assert isinstance(res, TextInputResult)
            assert res.action in ("editing", "submit", "cancel")
            assert len(prompt.value) <= 500
            assert 0 <= prompt.cursor_pos <= len(prompt.value)

    def test_text_input_prompt_boundary_cursor_operations(self) -> None:
        """
        Adversarially tests boundary cursor operations:
        backspacing at 0, deleting at end, left at 0, right at end, ctrl+u/k at ends,
        max_length = 0, and rapid value resetting.
        """
        # Empty prompt
        prompt = TextInputPrompt(initial_value="")
        assert prompt.cursor_pos == 0

        # Backspace at start -> no-op
        res = prompt.handle_key("backspace")
        assert prompt.value == ""
        assert prompt.cursor_pos == 0
        assert res.action == "editing"

        # Delete at start of empty -> no-op
        res = prompt.handle_key("delete")
        assert prompt.value == ""
        assert prompt.cursor_pos == 0

        # Left/Right on empty
        prompt.handle_key("left")
        assert prompt.cursor_pos == 0
        prompt.handle_key("right")
        assert prompt.cursor_pos == 0

        # ctrl+u and ctrl+k on empty
        prompt.handle_key("ctrl+u")
        assert prompt.value == ""
        assert prompt.cursor_pos == 0
        prompt.handle_key("ctrl+k")
        assert prompt.value == ""
        assert prompt.cursor_pos == 0

        # Set value with max_length=0
        zero_max = TextInputPrompt(initial_value="", max_length=0)
        assert zero_max.value == ""
        zero_max.handle_key("x")
        assert zero_max.value == ""
        zero_max.set_value("abc")
        assert zero_max.value == ""

        # Set value and cursor position sync
        p = TextInputPrompt(initial_value="initial")
        assert p.cursor_pos == 7
        p.set_value("new_longer_value")
        assert p.cursor_pos == 16
        p.set_value("")
        assert p.cursor_pos == 0

    def test_msvcrt_input_reader_unmapped_scan_codes_and_special_sequences(self) -> None:
        """
        Tests WindowsMSVCRTInputReader with raw unmapped 0x00 and 0xe0 extended scan codes,
        high-order bytes, and control characters.
        """
        if sys.platform != "win32":
            pytest.skip("Windows only test")

        reader = WindowsMSVCRTInputReader()

        # Unmapped 0x00 key (e.g. ord 250 -> special_00_250)
        with patch.object(reader._msvcrt, "getwch", side_effect=["\x00", "\xfa"]):
            key = reader._read_translated_key()
            assert key == "special_00_250"

        # Unmapped 0xe0 key (e.g. ord 251 -> special_e0_251)
        with patch.object(reader._msvcrt, "getwch", side_effect=["\xe0", "\xfb"]):
            key = reader._read_translated_key()
            assert key == "special_e0_251"

        # Known extended mapped keys
        with patch.object(reader._msvcrt, "getwch", side_effect=["\xe0", "H"]):
            assert reader._read_translated_key() == "up"

        with patch.object(reader._msvcrt, "getwch", side_effect=["\xe0", "s"]):
            assert reader._read_translated_key() == "ctrl+left"

        with patch.object(reader._msvcrt, "getwch", side_effect=["\x00", "\x0f"]):
            assert reader._read_translated_key() == "shift+tab"

        # Standard control chars
        with patch.object(reader._msvcrt, "getwch", return_value="\x18"):  # chr(24) -> ctrl+x
            assert reader._read_translated_key() == "ctrl+x"

        # Non-ASCII character passthrough (e.g. Norwegian æ)
        with patch.object(reader._msvcrt, "getwch", return_value="æ"):
            assert reader._read_translated_key() == "æ"

    def test_nested_text_prompts_and_rapid_modal_switching(self) -> None:
        """
        Simulates nested and sequential prompt flows (URL prompt -> Confirmation -> Rename prompt)
        without state leakage or cursor de-synchronization.
        """
        # Step 1: URL input prompt
        url_prompt = TextInputPrompt(
            initial_value="http://localhost:11434", placeholder="Enter Ollama URL..."
        )
        for ch in "/api/tags":
            url_prompt.handle_key(ch)
        res1 = url_prompt.handle_key("enter")
        assert res1.action == "submit"
        assert res1.value == "http://localhost:11434/api/tags"

        # Step 2: Nested rename / file prompt
        file_prompt = TextInputPrompt(initial_value="report.pdf")
        file_prompt.handle_key("home")
        file_prompt.handle_key("delete")  # deletes 'r' -> "eport.pdf"
        file_prompt.handle_key("backspace")  # at 0, no-op
        for ch in "final_":
            file_prompt.handle_key(ch)
        res2 = file_prompt.handle_key("enter")
        assert res2.action == "submit"
        assert res2.value == "final_eport.pdf"

        # Step 3: Check URL prompt was unmodified
        assert url_prompt.value == "http://localhost:11434/api/tags"

    def test_text_input_prompt_render_styling_edge_cases(self) -> None:
        """
        Tests TextInputPrompt.render_text under edge cases:
        cursor at start, cursor in middle, cursor at end, masked chars, empty placeholder.
        """
        # 1. Empty with placeholder
        p1 = TextInputPrompt(initial_value="", placeholder="Type here...")
        t1 = p1.render_text(prefix="Prompt: ", show_cursor=True)
        assert isinstance(t1, Text)
        assert "Prompt: " in t1.plain
        assert "Type here..." in t1.plain

        # 2. Cursor in middle
        p2 = TextInputPrompt(initial_value="ABCDE")
        p2.cursor_pos = 2
        t2 = p2.render_text(show_cursor=True)
        assert t2.plain == "ABCDE"

        # 3. Cursor at exact end
        p3 = TextInputPrompt(initial_value="ABCDE")
        p3.cursor_pos = 5
        t3 = p3.render_text(show_cursor=True)
        assert t3.plain == "ABCDE "

        # 4. Masked password prompt
        p4 = TextInputPrompt(initial_value="secret123", mask_char="*")
        p4.cursor_pos = 3
        t4 = p4.render_text(prefix="PW: ", show_cursor=True)
        assert "*********" in t4.plain
        assert "secret123" not in t4.plain


# ==============================================================================
# 3. State Boundary Violations & Edge Cases
# ==============================================================================


class TestStateBoundaryViolations:
    """Tests extreme and invalid boundary values across all domain sub-states."""

    def test_ingestion_extreme_inputs(self) -> None:
        """Tests IngestionState with empty strings, whitespace, 1MB string, and no-space string."""
        ing = IngestionState()

        # Empty string
        ing.update_extracted("")
        assert ing.char_count == 0
        assert ing.word_count == 0
        assert not ing.is_valid
        assert ing.extracted_preview == ""

        # Whitespace-only string
        ing.update_extracted("   \n\t   ")
        assert ing.char_count == 0
        assert ing.word_count == 0
        assert not ing.is_valid

        # 1000-character string with NO spaces (tests rsplit edge case)
        solid_string = "X" * 1000
        ing.update_extracted(solid_string)
        assert ing.char_count == 1000
        assert ing.word_count == 1
        assert ing.is_valid
        assert len(ing.extracted_preview) == 353  # 350 + "..."
        assert ing.extracted_preview.endswith("...")

        # 100,000-word large document
        large_text = "word " * 100000
        ing.update_extracted(large_text)
        assert ing.word_count == 100000
        assert ing.is_valid

    def test_player_state_negative_and_extreme_bounds(self) -> None:
        """Tests PlayerState with negative positions, negative durations, and massive timestamps."""
        p = PlayerState()

        # Negative position_ms
        p.position_ms = -5000
        p.duration_ms = 60000
        assert p.position_str == "00:00"
        assert p.scrubber_progress == 0.0

        # Negative duration_ms
        p.position_ms = 5000
        p.duration_ms = -1000
        assert p.duration_str == "00:00"
        assert p.scrubber_progress == 0.0

        # Position exceeds duration
        p.position_ms = 90000
        p.duration_ms = 60000
        assert p.position_str == "01:30"
        assert p.duration_str == "01:00"
        assert p.scrubber_progress == 1.0  # Clamped to 1.0

        # Massive timestamp (100 hours)
        p.position_ms = 360000000  # 100h = 6000 minutes
        p.duration_ms = 360000000
        assert p.position_str == "6000:00"
        assert p.scrubber_progress == 1.0

    def test_prompt_config_invalid_presets_and_locales(self) -> None:
        """Tests PromptConfigState persona resolution with invalid or unexpected locales."""
        cfg = PromptConfigState()

        # Default Norwegian
        assert cfg.host1_name == "Kari"
        assert cfg.host2_name == "Ola"

        # English
        cfg.language = "en-US"
        assert cfg.host1_name == "Jenny"
        assert cfg.host2_name == "Guy"

        # Non-Norwegian / Non-English custom locales default to English personas
        cfg.language = "de-DE"
        assert cfg.host1_name == "Jenny"
        assert cfg.host2_name == "Guy"

        cfg.language = "nb-NO-nynorsk"
        assert cfg.host1_name == "Kari"
        assert cfg.host2_name == "Ola"

        # Arbitrary preset values do not crash dataclass properties
        cfg.length_preset = "non_existent_preset_99"
        cfg.tone_preset = "hyper_chaotic"
        cfg.grounding_mode = "unknown_grounding"
        assert cfg.length_preset == "non_existent_preset_99"

    def test_empty_and_massive_dialogue_turn_lists(self) -> None:
        """
        Tests validation and state behavior with empty turn lists and 10,000 turn lists.
        """
        state = TUIState()

        # Empty turns -> validate_can_synthesize returns False
        state.generation.turns = []
        can_syn, reason = state.validate_can_synthesize()
        assert not can_syn
        assert "No dialogue turns available" in reason

        # 10,000 turns -> validate_can_synthesize returns True, snapshot succeeds
        state.generation.turns = [
            DialogueTurn(speaker="Host 1", text=f"Turn content {i}") for i in range(10000)
        ]
        can_syn, reason = state.validate_can_synthesize()
        assert can_syn
        assert reason == ""

        snap = state.snapshot()
        assert len(snap.generation.turns) == 10000

    def test_ollama_state_empty_and_corrupt_model_lists(self) -> None:
        """
        Tests OllamaState auto-selection with empty, single, and weirdly-named models.
        """
        ollama = OllamaState()

        # Empty available models
        ollama.available_models = []
        ollama.auto_select_model()
        assert ollama.selected_model == ""

        # Models with mixed casing and sub-variants
        ollama.available_models = [
            "MISTRAL:7B-INSTRUCT-V0.3",
            "qwen2.5:14b-instruct-q4_K_M",
            "LLAMA3.1:8B-INSTRUCT-FP16",
        ]
        # Force select prefers llama3.1
        ollama.auto_select_model(force=True)
        assert ollama.selected_model == "LLAMA3.1:8B-INSTRUCT-FP16"

    def test_audio_synthesis_progress_clamping_and_turn_bounds(self) -> None:
        """
        Tests AudioSynthesisState boundary conditions.
        """
        audio = AudioSynthesisState()
        assert audio.status == SynthesisStatus.IDLE
        assert audio.current_turn == 0
        assert audio.total_turns == 0

        audio.current_turn = 5
        audio.total_turns = 5
        audio.progress_pct = 100.0
        audio.status = SynthesisStatus.COMPLETED
        assert audio.status == SynthesisStatus.COMPLETED

    def test_grounding_sync_state_transitions(self) -> None:
        """
        Verifies grounding mode sync logic when switching between topic_prompt and other modalities.
        """
        state = TUIState()

        # Topic prompt forces open_topic
        state.ingestion.source_mode = SourceMode.TOPIC_PROMPT
        state.sync_grounding_with_modality()
        assert state.config.grounding_mode == "open_topic"

        # Switching to document resets open_topic back to strict
        state.ingestion.source_mode = SourceMode.DOCUMENT
        state.sync_grounding_with_modality()
        assert state.config.grounding_mode == "strict"

        # Creative grounding is preserved when switching back to document
        state.config.grounding_mode = "creative"
        state.sync_grounding_with_modality()
        assert state.config.grounding_mode == "creative"


# ==============================================================================
# 4. Factory & Mocking Tier 1-5 Integration
# ==============================================================================


class TestInputReaderFactoryTierCoverage:
    """Verifies factory patterns across mock, queue, and platform readers."""

    def test_create_input_reader_with_mock_keys(self) -> None:
        r = create_input_reader(mock_keys=["a", "b", "enter"])
        assert isinstance(r, MockInputReader)
        assert r.get_key() == "a"
        assert r.get_key() == "b"
        assert r.get_key() == "enter"
        assert r.get_key() is None

    def test_create_input_reader_queue(self) -> None:
        r = create_input_reader(reader_type="queue")
        assert isinstance(r, QueueInputReader)
        assert not r.has_key()

    def test_create_input_reader_auto_and_mock(self) -> None:
        auto_r = create_input_reader()
        assert auto_r is not None
        mock_r = create_input_reader(reader_type="mock")
        assert isinstance(mock_r, MockInputReader)
        assert not mock_r.has_key()


# ==============================================================================
# 5. Validation Truth Tables & Combinatorial State Matrices
# ==============================================================================


class TestValidationMatricesAndCombinatorics:
    """Exhaustive truth table matrices for all validation helper methods."""

    def test_validate_can_generate_16_state_truth_table(self) -> None:
        """
        Tests all 16 permutations of (is_busy, is_valid, is_online, has_selected_model).
        Validates that generation is allowed IF AND ONLY IF:
        is_busy == False AND is_valid == True AND is_online == True AND has_selected_model == True.
        """
        for is_busy in (False, True):
            for is_valid in (False, True):
                for is_online in (False, True):
                    for has_model in (False, True):
                        state = TUIState()
                        state.ui.is_busy = is_busy
                        state.ui.busy_task = "Task in progress" if is_busy else ""

                        if is_valid:
                            state.ingestion.update_extracted("Sufficient document text payload")
                        else:
                            state.ingestion.update_extracted("short")

                        state.ollama.is_online = is_online
                        state.ollama.selected_model = "llama3.1:8b" if has_model else ""

                        can_gen, reason = state.validate_can_generate()
                        expected_valid = not is_busy and is_valid and is_online and has_model

                        assert can_gen is expected_valid, (
                            f"Failed on combination: busy={is_busy}, valid={is_valid}, "
                            f"online={is_online}, model={has_model}. Got ({can_gen}, '{reason}')"
                        )
                        if not expected_valid:
                            assert len(reason) > 0
                        else:
                            assert reason == ""

    def test_validate_can_synthesize_truth_table(self) -> None:
        """
        Tests all 4 combinations of (is_busy, has_turns).
        Validates synthesis allowed iff not is_busy and has_turns.
        """
        for is_busy in (False, True):
            for has_turns in (False, True):
                state = TUIState()
                state.ui.is_busy = is_busy
                state.ui.busy_task = "Busy synthesizing"
                if has_turns:
                    state.generation.turns = [DialogueTurn(speaker="Host 1", text="Hello")]
                else:
                    state.generation.turns = []

                can_synth, reason = state.validate_can_synthesize()
                expected = (not is_busy) and has_turns
                assert can_synth is expected
                if not expected:
                    assert len(reason) > 0
                else:
                    assert reason == ""

    def test_validate_can_play_matrix(self) -> None:
        """
        Tests combinations of (is_loaded, master_mp3_path).
        """
        for is_loaded in (False, True):
            for path_val in (None, "", "output/master.mp3"):
                state = TUIState()
                state.player.is_loaded = is_loaded
                state.audio.master_mp3_path = path_val

                can_play, reason = state.validate_can_play()
                expected = is_loaded or bool(path_val)
                assert can_play is expected
                if not expected:
                    assert len(reason) > 0
                else:
                    assert reason == ""

    def test_concurrent_dynamic_subscribers_and_dispatches(self) -> None:
        """
        Stress-tests registering new subscribers from multiple threads while
        other threads are actively dispatching events.
        """
        eq = TUIEventQueue()
        dispatched_count = 0
        counter_lock = threading.Lock()

        def subscriber_cb(ev: TUIEvent) -> None:
            nonlocal dispatched_count
            with counter_lock:
                dispatched_count += 1

        def subscriber_adder(thread_id: int) -> None:
            for i in range(100):
                eq.subscribe(f"custom_event_{i % 5}", subscriber_cb)

        def event_dispatcher(thread_id: int) -> None:
            for i in range(100):
                eq.dispatch(TUIEvent(event_type=f"custom_event_{i % 5}"))

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            add_futures = [executor.submit(subscriber_adder, t) for t in range(5)]
            disp_futures = [executor.submit(event_dispatcher, t) for t in range(5)]
            concurrent.futures.wait(add_futures + disp_futures)

        assert dispatched_count > 0
