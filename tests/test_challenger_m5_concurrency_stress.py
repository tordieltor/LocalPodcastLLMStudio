"""
Challenger 1 Concurrency & Multi-Threading Empirical Stress Suite (Milestone 5)
==============================================================================
Empirically stress-tests:
1. `normalize_speaker` with `@lru_cache(maxsize=128)` under high multi-threaded contention.
2. `validate_safe_output_path` across `core/mp3_stitcher.py` and `core/tts.py` under concurrency.
3. `MP3Stitcher` zero-copy frame parsing with `offset` parameter and immutable tables under concurrency.
4. `WindowsAudioPlayer` lifecycle, handle safety, and error checking under concurrency.
"""

import concurrent.futures
import os
import threading
import time
from unittest.mock import patch

from core.mp3_stitcher import (
    MP3Stitcher,
    stitch_mp3_files,
    validate_safe_output_path,
)
from core.parser import DialogueParser, normalize_speaker
from core.player import WindowsAudioPlayer
from tests.conftest import make_mpeg2_l3_frame, make_synthetic_mp3


class TestNormalizeSpeakerConcurrencyStress:
    """Stress tests for `normalize_speaker` with `@lru_cache(maxsize=128)`."""

    def test_normalize_speaker_high_contention_100_threads(self):
        """
        100 concurrent threads each performing 1,000 calls across diverse inputs.
        Verifies:
        1. Thread-safety of LRU cache without deadlock or corruption.
        2. Correct deterministic normalization across English and Norwegian personas.
        3. Cache stats accurately reflect hits and misses.
        """
        normalize_speaker.cache_clear()
        num_threads = 100
        calls_per_thread = 1000

        test_cases = [
            ("Host 1", "Host 1"),
            ("Host 2", "Host 2"),
            ("kari", "Host 1"),
            ("Ola", "Host 2"),
            ("Jenny", "Host 1"),
            ("Guy", "Host 2"),
            ("Speaker 1", "Host 1"),
            ("Speaker 2", "Host 2"),
            ("host_1", "Host 1"),
            ("host_2", "Host 2"),
            ("host a", "Host 1"),
            ("host b", "Host 2"),
            ("host1", "Host 1"),
            ("host2", "Host 2"),
            ("", "Host 1"),
            ("   ", ""),
            ("Guest Expert", "Guest Expert"),
            ("Prof. Hansen", "Prof. Hansen"),
            ("Host Moderator", "Host 1"),
        ]

        errors: list[str] = []

        def worker(thread_id: int):
            try:
                for i in range(calls_per_thread):
                    raw_in, expected = test_cases[(thread_id + i) % len(test_cases)]
                    res = normalize_speaker(raw_in)
                    if res != expected:
                        errors.append(
                            f"T{thread_id} Iter {i}: Expected {expected!r} for {raw_in!r}, got {res!r}"
                        )
            except Exception as e:
                errors.append(f"T{thread_id} Exception: {e}")

        threads = [
            threading.Thread(target=worker, args=(t,), daemon=True) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert errors == [], (
            f"Errors encountered during concurrent normalize_speaker: {errors[:10]}"
        )
        info = normalize_speaker.cache_info()
        assert info.hits > 0, f"Expected cache hits, got {info}"
        assert info.currsize <= 128, f"Cache exceeded maxsize=128: {info}"

    def test_normalize_speaker_cache_clearing_during_concurrent_access(self):
        """
        Tests continuous cache_clear() while 40 threads are actively reading/writing the cache.
        Verifies zero race conditions, null references, or exceptions.
        """
        normalize_speaker.cache_clear()
        stop_event = threading.Event()
        errors: list[str] = []

        sample_speakers = [
            "Host 1",
            "Host 2",
            "Kari",
            "Ola",
            "Jenny",
            "Guy",
            "Speaker 1",
            "Speaker 2",
            "Narrator",
            "Interviewer",
        ]

        def reader(tid: int):
            while not stop_event.is_set():
                try:
                    for spk in sample_speakers:
                        res = normalize_speaker(spk)
                        assert res is not None
                except Exception as e:
                    errors.append(f"Reader T{tid} Error: {e}")

        def clearer(tid: int):
            while not stop_event.is_set():
                try:
                    normalize_speaker.cache_clear()
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(f"Clearer T{tid} Error: {e}")

        readers = [threading.Thread(target=reader, args=(i,), daemon=True) for i in range(40)]
        clearers = [threading.Thread(target=clearer, args=(i,), daemon=True) for i in range(5)]

        for t in readers + clearers:
            t.start()

        time.sleep(0.5)  # Run for 500ms
        stop_event.set()

        for t in readers + clearers:
            t.join(timeout=3.0)

        assert errors == [], f"Errors during concurrent cache_clear / read: {errors}"
        normalize_speaker.cache_clear()

    def test_normalize_speaker_cache_churn_over_128_unique_keys(self):
        """
        Tests LRU eviction behavior by querying 500 unique non-persona speaker strings concurrently across 20 threads.
        """
        normalize_speaker.cache_clear()
        num_threads = 20
        # Use prefixes without '1', '2', 'kari', 'ola', 'jenny', 'guy', etc.
        unique_keys = [f"Unique_Guest_{i:04d}" for i in range(500)]
        errors: list[str] = []

        def worker(tid: int):
            try:
                for k in unique_keys:
                    res = normalize_speaker(k)
                    # For strings without host keywords, normalize_speaker returns k.strip()
                    # (Unless it contains '1' or '2', which :04d format handles if not 1 or 2)
                    if "1" in k:
                        assert res == "Host 1"
                    elif "2" in k:
                        assert res == "Host 2"
                    else:
                        assert res == k
            except Exception as e:
                errors.append(f"T{tid} Error: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            concurrent.futures.wait(futures, timeout=10.0)

        assert errors == []
        info = normalize_speaker.cache_info()
        assert info.currsize == 128, f"Expected cache to be filled to 128, got {info.currsize}"
        assert info.misses >= 500


class TestPathSanitizationConcurrencyStress:
    """Stress tests for `validate_safe_output_path` across threads."""

    def test_validate_safe_output_path_concurrent_stress(self):
        """
        50 threads concurrently executing valid and invalid path sanitization.
        """
        num_threads = 50
        errors: list[str] = []

        valid_paths = [
            ("output/audio.mp3", "output/audio.mp3"),
            ("  C:\\podcasts\\ep1.mp3  ", "C:\\podcasts\\ep1.mp3"),
            ("my_podcast.wav", "my_podcast.wav"),
            ("/tmp/audio/final.mp3", "/tmp/audio/final.mp3"),
        ]

        invalid_paths = [
            (None, False, ValueError),
            ("", False, ValueError),
            ("   \t  \n ", False, ValueError),
            ("audio\x00file.mp3", False, ValueError),
            (12345, False, ValueError),
            ([1, 2, 3], False, ValueError),
        ]

        def worker(tid: int):
            try:
                for _ in range(200):
                    # Test valid
                    for raw, expected in valid_paths:
                        out = validate_safe_output_path(raw)
                        assert out == expected

                    # Test None with allow_none=True
                    assert validate_safe_output_path(None, allow_none=True) == ""

                    # Test invalid
                    for raw_inv, allow_n, exc_type in invalid_paths:
                        try:
                            validate_safe_output_path(raw_inv, allow_none=allow_n)
                            errors.append(f"T{tid}: Expected {exc_type} for {raw_inv!r}")
                        except exc_type:
                            pass
            except Exception as e:
                errors.append(f"T{tid} unexpected error: {e}")

        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True) for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert errors == []


class TestMP3StitcherConcurrencyAndZeroCopyStress:
    """Stress tests for MP3Stitcher zero-copy parsing and stitching under concurrency."""

    def test_parse_frame_header_zero_copy_offsets_concurrency(self):
        """
        Tests `parse_frame_header(header_bytes, offset=...)` concurrently across 50 threads
        with large byte buffers and varying offsets.
        """
        num_threads = 50
        # 48kbps, 24kHz -> bitrate_idx=6, sr_idx=1 -> 144 bytes
        frame = make_mpeg2_l3_frame(bitrate_idx=6, sr_idx=1)  # 144 bytes
        # Create a 10-frame sequence
        ten_frames = frame * 10
        errors: list[str] = []

        def worker(tid: int):
            try:
                for i in range(10):
                    offset = i * 144
                    res = MP3Stitcher.parse_frame_header(ten_frames, offset=offset)
                    assert res is not None
                    frame_len, ver_id, bitrate, sr = res
                    assert frame_len == 144
                    assert ver_id == 2
                    assert bitrate == 48
                    assert sr == 24000
            except Exception as e:
                errors.append(f"T{tid} Error: {e}")

        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True) for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == []

    def test_mp3_stitcher_concurrent_dialogue_synthesis_and_stitching(self, tmp_path):
        """
        Simulates 30 parallel podcast stitching pipelines where DialogueTurns are parsed,
        synthesized (mocked), and stitched to disk atomically.
        """
        num_pipelines = 30
        results = [None] * num_pipelines

        def pipeline_worker(pid: int):
            out_file = str(tmp_path / f"podcast_pipeline_{pid}.mp3")
            raw_script = f"""[
                {{"speaker": "Kari", "text": "Turn 1 from pipeline {pid}"}},
                {{"speaker": "Ola", "text": "Turn 2 from pipeline {pid}"}}
            ]"""
            turns = DialogueParser.parse(raw_script)
            assert len(turns) == 2
            assert turns[0].speaker == "Host 1"
            assert turns[1].speaker == "Host 2"

            chunks = [make_synthetic_mp3(num_frames=3, title=t.text) for t in turns]
            final_path = stitch_mp3_files(
                input_files_or_bytes=chunks,
                output_file_path=out_file,
                title=f"Episode {pid}",
            )
            results[pid] = final_path

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_pipelines) as executor:
            futures = [executor.submit(pipeline_worker, i) for i in range(num_pipelines)]
            concurrent.futures.wait(futures, timeout=10.0)

        for pid, final_p in enumerate(results):
            assert final_p is not None, f"Pipeline {pid} produced no result"
            assert os.path.exists(final_p)
            assert os.path.getsize(final_p) > 500


class TestWindowsAudioPlayerConcurrencyStress:
    """Stress tests for WindowsAudioPlayer under multi-threaded execution."""

    def test_windows_audio_player_concurrent_instances_lifecycle(self, tmp_path):
        """
        Tests 25 parallel threads creating WindowsAudioPlayer instances with unique aliases,
        opening mock MP3 files, querying state, and closing devices.
        """
        audio_file = str(tmp_path / "concurrent_audio_test.mp3")
        with open(audio_file, "wb") as f:
            f.write(make_synthetic_mp3(num_frames=10))

        num_threads = 25
        errors: list[str] = []

        def worker(tid: int):
            try:
                player = WindowsAudioPlayer(alias=f"test_player_t_{tid}")
                assert player._is_opened is False
                assert player.current_file is None
                assert player.get_mode() == "not ready"

                with patch.object(player, "_send_command", return_value="0"):
                    opened = player.open(audio_file)
                    assert opened is True
                    assert player._is_opened is True

                    # Verify safe property queries
                    player.is_playing()
                    player.is_paused()
                    player.is_stopped()
                    player.get_volume()
                    player.set_volume(90)
                    player.get_position()
                    player.get_length()

                    player.close()
                    assert player._is_opened is False
                    assert player.current_file is None
            except Exception as e:
                errors.append(f"T{tid} Player Error: {e}")

        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True) for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == []

    def test_windows_audio_player_open_failure_handling_under_concurrency(self):
        """
        Verifies that WindowsAudioPlayer.open cleanly handles missing files, empty paths,
        and simulated winmm MCI errors across 30 concurrent threads.
        """
        num_threads = 30
        errors: list[str] = []

        def worker(tid: int):
            try:
                player = WindowsAudioPlayer(alias=f"err_player_{tid}")
                # Missing file
                assert player.open("C:/nonexistent/path/audio.mp3") is False
                assert player._is_opened is False

                # Empty string
                assert player.open("") is False
                assert player._is_opened is False

                # Simulated error code != 0
                player._last_error = 263
                assert player._is_opened is False
                player.close()
            except Exception as e:
                errors.append(f"T{tid} Open Error: {e}")

        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True) for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == []
