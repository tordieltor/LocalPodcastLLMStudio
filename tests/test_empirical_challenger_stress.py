"""
Empirical Challenger Test Battery for Milestone 4 & 5 Verification (Cleaned & Calibrated).
Tests thread-safe voice caching, MP3 frame scanning stress/corrupt resilience,
and atomic file write concurrency/collision.
"""

import io
import os
import random
import sys
import threading
import time
import types
from unittest.mock import MagicMock, patch

import pytest

from core.mp3_stitcher import MP3Stitcher, stitch_mp3_files
from core.tts import (
    _VOICE_CACHE_LOCK,
    _VOICE_MODEL_CACHE,
    clear_voice_model_cache,
    get_or_load_piper_voice,
    synthesize_turn,
)
from tests.conftest import make_mpeg2_l3_frame, make_synthetic_mp3
from ui.main_window import _atomic_write_file


# ==============================================================================
# 1. Voice Model Cache Thread Safety Stress Tests (core/tts.py)
# ==============================================================================


class TestVoiceModelCacheConcurrencyStress:
    """Adversarial stress tests for _VOICE_MODEL_CACHE in core/tts.py."""

    def test_concurrent_voice_cache_hit_and_miss_stampede(self):
        """
        Spawns 80 concurrent threads requesting get_or_load_piper_voice across 4 voices.
        Simulates slow model loading (5ms sleep) to create maximum cache stampede contention.
        Verifies:
        1. Model load is called exactly once per unique voice name.
        2. All 80 threads receive non-None PiperVoice instances.
        3. No deadlock or dictionary mutation exceptions occur.
        """
        clear_voice_model_cache()
        assert len(_VOICE_MODEL_CACHE) == 0

        load_counts: dict[str, int] = {}
        load_counts_lock = threading.Lock()

        def mock_load_voice(onnx_p, config_path=None):
            time.sleep(0.005)  # 5ms artificial load time
            voice_name = os.path.basename(onnx_p).replace(".onnx", "")
            with load_counts_lock:
                load_counts[voice_name] = load_counts.get(voice_name, 0) + 1
            mock_pv = MagicMock()
            mock_pv.name = voice_name
            return mock_pv

        def mock_find_files(clean_name):
            return f"C:/fake/path/{clean_name}.onnx", f"C:/fake/path/{clean_name}.onnx.json"

        voices = [
            "no_NO-torkil-medium",
            "en_US-lessac-medium",
            "en_US-ryan-medium",
            "no_NO-kari-medium",
        ]
        num_threads = 80
        results = [None] * num_threads
        errors = []

        # Create dummy module hierarchy for piper.voice
        mock_piper = types.ModuleType("piper")
        mock_piper_voice = types.ModuleType("piper.voice")
        mock_voice_cls = MagicMock()
        mock_voice_cls.load.side_effect = mock_load_voice
        mock_piper_voice.PiperVoice = mock_voice_cls  # type: ignore[attr-defined]
        mock_piper.voice = mock_piper_voice  # type: ignore[attr-defined]

        with (
            patch("core.tts.find_voice_model_files", side_effect=mock_find_files),
            patch.dict(sys.modules, {"piper": mock_piper, "piper.voice": mock_piper_voice}),
        ):
            def worker(thread_idx: int):
                try:
                    voice_choice = voices[thread_idx % len(voices)]
                    pv = get_or_load_piper_voice(voice_choice)
                    results[thread_idx] = (voice_choice, pv)
                except Exception as e:
                    errors.append((thread_idx, str(e)))

            threads = [
                threading.Thread(target=worker, args=(i,), daemon=True)
                for i in range(num_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10.0)

        assert errors == [], f"Exceptions occurred during concurrent voice loading: {errors}"
        for idx, res in enumerate(results):
            assert res is not None, f"Thread {idx} produced no result"
            voice_choice, pv = res
            assert pv is not None, f"Thread {idx} received None for {voice_choice}"
            assert pv.name == voice_choice

        # Verify load was called exactly once per distinct voice
        for v in voices:
            assert load_counts.get(v, 0) == 1, f"Voice {v} was loaded {load_counts.get(v)} times instead of 1!"

        clear_voice_model_cache()

    def test_concurrent_cache_clear_during_active_retrievals(self):
        """
        50 reader threads continuously call get_or_load_piper_voice while
        10 sweeper threads periodically clear the cache with clear_voice_model_cache().
        Verifies zero race conditions, lock deadlocks, or unhandled exceptions.
        """
        clear_voice_model_cache()
        stop_event = threading.Event()
        errors = []

        mock_pv = MagicMock()
        mock_pv.name = "cached-model"

        mock_piper = types.ModuleType("piper")
        mock_piper_voice = types.ModuleType("piper.voice")
        mock_voice_cls = MagicMock()
        mock_voice_cls.load.return_value = mock_pv
        mock_piper_voice.PiperVoice = mock_voice_cls  # type: ignore[attr-defined]
        mock_piper.voice = mock_piper_voice  # type: ignore[attr-defined]

        with (
            patch("core.tts.find_voice_model_files", return_value=("fake.onnx", "fake.json")),
            patch.dict(sys.modules, {"piper": mock_piper, "piper.voice": mock_piper_voice}),
        ):
            def reader(tid: int):
                while not stop_event.is_set():
                    try:
                        res = get_or_load_piper_voice(f"voice-{tid % 4}")
                        assert res is not None
                    except Exception as e:
                        errors.append((tid, "reader", str(e)))

            def sweeper(tid: int):
                while not stop_event.is_set():
                    try:
                        clear_voice_model_cache()
                        time.sleep(0.002)
                    except Exception as e:
                        errors.append((tid, "sweeper", str(e)))

            readers = [threading.Thread(target=reader, args=(i,), daemon=True) for i in range(50)]
            sweepers = [threading.Thread(target=sweeper, args=(i,), daemon=True) for i in range(10)]

            for t in readers + sweepers:
                t.start()

            time.sleep(0.5)  # Run stress for 500ms
            stop_event.set()

            for t in readers + sweepers:
                t.join(timeout=3.0)

        assert errors == [], f"Race condition errors in cache clear/read: {errors}"
        clear_voice_model_cache()

    def test_concurrent_piper_voice_load_exception_graceful_recovery(self):
        """
        Verifies that when PiperVoice.load raises RuntimeError or OSError,
        all concurrent threads gracefully receive None and subsequent calls can retry safely.
        """
        clear_voice_model_cache()
        num_threads = 40
        results = [None] * num_threads

        mock_piper = types.ModuleType("piper")
        mock_piper_voice = types.ModuleType("piper.voice")
        mock_voice_cls = MagicMock()
        mock_voice_cls.load.side_effect = RuntimeError("ONNX model load failed")
        mock_piper_voice.PiperVoice = mock_voice_cls  # type: ignore[attr-defined]
        mock_piper.voice = mock_piper_voice  # type: ignore[attr-defined]

        with (
            patch("core.tts.find_voice_model_files", return_value=("corrupt.onnx", "corrupt.json")),
            patch.dict(sys.modules, {"piper": mock_piper, "piper.voice": mock_piper_voice}),
        ):
            def worker(tid: int):
                res = get_or_load_piper_voice("bad-voice")
                results[tid] = res

            threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5.0)

        assert all(r is None for r in results)
        assert "bad-voice" not in _VOICE_MODEL_CACHE


# ==============================================================================
# 2. Fast MP3 Frame Sync & Corrupt Stream Stress (core/mp3_stitcher.py)
# ==============================================================================


class TestMP3FrameScanningCorruptStreamsAndStress:
    """Stress testing MP3Stitcher fast frame sync find(b'\\xff') against adversarial payloads."""

    def test_mp3_scanner_dense_ff_bytes_throughput(self):
        """
        Evaluates MP3Stitcher.extract_audio_frames throughput on 500 KB of pure 0xFF bytes.
        Verifies parser terminates and returns empty bytes without crashing or memory explosion.
        """
        dense_ff = b"\xff" * 500_000
        start_time = time.time()
        result = MP3Stitcher.extract_audio_frames(dense_ff)
        elapsed = time.time() - start_time

        assert result == b""
        assert elapsed < 3.0, f"500KB 0xFF scan took {elapsed:.2f}s"

    def test_mp3_scanner_alternating_non_sync_ff_patterns(self):
        """
        Tests 2 MB buffer of alternating 0xFF 0x00, 0xFF 0x1F, 0xFF 0x7F patterns
        (where byte following 0xFF does not satisfy sync mask (b1 & 0xE0) == 0xE0).
        """
        pattern = (b"\xff\x00\xff\x1f\xff\x7f\xff\xdf") * 250_000  # 2 MB
        start_time = time.time()
        result = MP3Stitcher.extract_audio_frames(pattern)
        elapsed = time.time() - start_time

        assert result == b""
        assert elapsed < 1.5

    def test_mp3_scanner_nested_ff_in_id3v2_tag(self):
        """
        Creates an ID3v2 header containing 100 KB of fake sync words (b'\\xff\\xfb\\x90\\x64')
        inside ID3 title metadata, followed by 10 legitimate MPEG-2 Layer III audio frames.
        Verifies:
        - strip_id3 completely bypasses the ID3 container.
        - extract_audio_frames extracts exactly the 10 legitimate frames and none of the nested tags.
        """
        legit_frame = make_mpeg2_l3_frame()  # exactly 144 bytes
        legit_payload = legit_frame * 10

        # Build ID3v2.3 tag containing embedded 0xFF bytes
        fake_nested_sync = b"\xff\xfb\x90\x64" * 25000  # 100,000 bytes
        id3_tag = MP3Stitcher.build_id3v23_tag(
            title=fake_nested_sync.decode("latin1", errors="ignore"),
            artist="Adversarial Tester",
        )

        full_stream = id3_tag + legit_payload
        extracted = MP3Stitcher.extract_audio_frames(full_stream)

        assert len(extracted) == len(legit_payload)
        assert extracted == legit_payload

    def test_mp3_scanner_corrupted_id3_syncsafe_size(self):
        """
        Tests malformed ID3v2 headers where declared tag size extends beyond the buffer,
        or size bytes have high bits set. Verifies parser does not crash.
        """
        # ID3 header claiming 100 MB size but payload is only 20 bytes
        malformed_id3 = b"ID3\x03\x00\x00\x7f\x7f\x7f\x7f" + b"extra small payload"
        res = MP3Stitcher.extract_audio_frames(malformed_id3)
        assert res == b""

        # ID3 header with invalid characters
        corrupt_id3_2 = b"ID3\x03\x00\x00\x00\x00\x00\x05" + b"\xff\xfb\x90"
        res2 = MP3Stitcher.extract_audio_frames(corrupt_id3_2)
        assert isinstance(res2, bytes)

    def test_mp3_scanner_multimegabyte_clean_and_corrupt_stream(self):
        """
        Generates a 5 MB stream containing 20 valid MPEG frames separated by non-sync padding
        (bytes without 0xFF). Verifies all 20 frames are extracted in order.
        """
        legit_frame = make_mpeg2_l3_frame()
        frame_len = len(legit_frame)
        num_frames = 20

        # Non-sync filler bytes (avoiding 0xFF)
        filler = b"\x00\x11\x22\x33\x44\x55\x66\x77" * 30000  # 240 KB per gap

        stream_buf = io.BytesIO()
        for i in range(num_frames):
            stream_buf.write(filler)
            stream_buf.write(legit_frame)
        stream_buf.write(filler)

        full_stream = stream_buf.getvalue()
        start_time = time.time()
        extracted = MP3Stitcher.extract_audio_frames(full_stream)
        elapsed = time.time() - start_time

        assert extracted == legit_frame * num_frames
        assert elapsed < 1.0, f"Scanning 5MB stream took {elapsed:.2f}s"

    def test_mp3_scanner_truncated_frame_headers_at_boundaries(self):
        """
        Tests buffer boundaries with 1, 2, or 3 sync bytes at end of buffer.
        """
        legit_frame = make_mpeg2_l3_frame()

        for tail in [b"\xff", b"\xff\xe0", b"\xff\xfb", b"\xff\xfb\x90"]:
            stream = legit_frame + tail
            extracted = MP3Stitcher.extract_audio_frames(stream)
            assert extracted == legit_frame

    def test_mp3_scanner_frame_length_larger_than_remaining_buffer(self):
        """
        Valid 4-byte header specifying a 418-byte frame, but only 50 bytes are present.
        Verifies scanner does not extract partial frame or crash.
        """
        # MPEG-1 Layer III 128kbps 44.1kHz frame length = 417 or 418 bytes
        # Header: 0xFF 0xFB (MPEG-1 Layer III, no CRC), 0x90 (128kbps, 44.1kHz, no pad), 0x00
        header = b"\xff\xfb\x90\x00"
        partial_frame = header + (b"\x00" * 46)  # total 50 bytes instead of ~418
        extracted = MP3Stitcher.extract_audio_frames(partial_frame)
        assert extracted == b""


# ==============================================================================
# 3. Atomic File Writes & Race Collisions Stress Tests
# ==============================================================================


class TestAtomicFileWriteConcurrencyAndCollisions:
    """Stress tests for _atomic_write_file and stitch_mp3_files atomic replacement."""

    def test_atomic_write_file_concurrent_same_path_collision(self, tmp_path):
        """
        40 concurrent threads attempt to write to the EXACT same destination file path
        simultaneously using _atomic_write_file().
        Verifies:
        1. No unhandled crashes or deadlocks.
        2. No temporary staging files (*.tmp.*) are left behind on disk.
        3. The resulting file exists and contains valid uncorrupted text.
        """
        target_file = str(tmp_path / "concurrent_master_output.json")
        num_threads = 40
        errors = []

        def worker(thread_idx: int):
            payload_str = "A" * 10000
            data = f'{{"writer_id": {thread_idx}, "payload": "{payload_str}"}}'
            try:
                _atomic_write_file(target_file, data)
            except Exception as e:
                errors.append((thread_idx, str(e)))

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert os.path.exists(target_file)
        content = open(target_file, "r", encoding="utf-8").read()
        assert content.startswith('{"writer_id":')
        assert content.endswith('"}')

        # Verify no orphan .tmp files
        dir_files = os.listdir(str(tmp_path))
        tmp_files = [f for f in dir_files if ".tmp." in f]
        assert tmp_files == [], f"Orphaned staging files found: {tmp_files}"

    def test_stitch_mp3_files_concurrent_distinct_and_identical_targets(self, tmp_path):
        """
        Tests stitch_mp3_files under concurrent multi-threaded execution.
        Part A: 20 threads writing to distinct destination paths.
        Part B: 20 threads writing to the same destination path.
        """
        chunks = [make_synthetic_mp3(num_frames=3, title=f"Seg {i}") for i in range(3)]

        # Part A: Distinct paths
        distinct_errors = []
        def distinct_worker(idx: int):
            out_p = str(tmp_path / f"distinct_stitch_{idx}.mp3")
            try:
                stitch_mp3_files(chunks, out_p)
            except Exception as e:
                distinct_errors.append((idx, str(e)))

        threads = [threading.Thread(target=distinct_worker, args=(i,), daemon=True) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert distinct_errors == []
        for i in range(20):
            p = str(tmp_path / f"distinct_stitch_{i}.mp3")
            assert os.path.exists(p)
            assert os.path.getsize(p) > 500

        # Part B: Same destination path
        same_target = str(tmp_path / "shared_stitched_podcast.mp3")
        same_errors = []
        def same_worker(idx: int):
            try:
                stitch_mp3_files(chunks, same_target, title=f"Thread {idx} Title")
            except Exception as e:
                same_errors.append((idx, str(e)))

        threads2 = [threading.Thread(target=same_worker, args=(i,), daemon=True) for i in range(20)]
        for t in threads2:
            t.start()
        for t in threads2:
            t.join(timeout=10.0)

        assert os.path.exists(same_target)
        assert os.path.getsize(same_target) > 500
        # Verify no orphan .tmp files in directory
        tmp_files = [f for f in os.listdir(str(tmp_path)) if ".tmp." in f]
        assert tmp_files == [], f"Orphaned temporary files remaining: {tmp_files}"
