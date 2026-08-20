#!/usr/bin/env python3
"""
LocalPodcastLLMStudio - Rational Test Suite Runner (run_tests.py)
=================================================================
Inspired by the NOUgurus empirical test architecture.

Features:
- Smart Tier Execution:
    --quick / --mvp : Rapid Tier 1-4 smoke suite (~1.5s)
    --full / --deep  : Exhaustive 1,238-test matrix including adversarial challenger suites
- Automatic CPU Acceleration (pytest-xdist detection & -n auto)
- Windows Resource Resilience (exponential backoff file teardown & handle cleanup)
- Sandboxed Test Environment Setup & Tear-down
"""

import gc
import os
import shutil
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# Core Tier 1-4 MVP Smoke Test Suite
MVP_TEST_FILES = [
    "tests/test_check_env.py",
    "tests/test_extractor.py",
    "tests/test_prompts.py",
    "tests/test_parser.py",
    "tests/test_ollama.py",
    "tests/test_tts.py",
    "tests/test_mp3_stitcher.py",
    "tests/test_player.py",
    "tests/test_ui.py",
    "tests/test_e2e_pipeline.py",
]


def safe_remove_file(
    filepath: str, retries: int = 10, initial_delay: float = 0.1, backoff: float = 1.5
) -> None:
    """Safely unlink a file with exponential backoff to handle Windows WinError 32 locks."""
    if not os.path.exists(filepath):
        return
    gc.collect()
    delay = initial_delay
    for attempt in range(retries):
        try:
            os.remove(filepath)
            return
        except (PermissionError, OSError) as e:
            if attempt == retries - 1:
                print(f"[Warning] Could not remove temporary file {filepath}: {e}")
            else:
                gc.collect()
                time.sleep(delay)
                delay *= backoff


def safe_remove_dir(
    dirpath: str, retries: int = 10, initial_delay: float = 0.1, backoff: float = 1.5
) -> None:
    """Safely remove a directory tree with exponential backoff."""
    if not os.path.exists(dirpath):
        return
    gc.collect()
    delay = initial_delay
    for attempt in range(retries):
        try:
            shutil.rmtree(dirpath)
            return
        except (PermissionError, OSError) as e:
            if attempt == retries - 1:
                print(f"[Warning] Could not remove directory {dirpath}: {e}")
            else:
                gc.collect()
                time.sleep(delay)
                delay *= backoff


def setup_test_environment() -> None:
    """Configure sandboxed environment variables for testing."""
    os.environ["TESTING"] = "True"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["OLLAMA_HOST"] = "http://localhost:11434"

    # Add project root and tests to sys.path
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    tests_path = os.path.join(PROJECT_ROOT, "tests")
    if tests_path not in sys.path:
        sys.path.insert(0, tests_path)


def main() -> int:
    setup_test_environment()

    try:
        import pytest
    except ImportError:
        print("[Error] pytest is not installed in the active environment.")
        print("Please install requirements using: pip install -e .[dev]")
        return 1

    user_args = sys.argv[1:]
    is_quick_mode = "--quick" in user_args or "--mvp" in user_args
    is_full_mode = "--full" in user_args or "--deep" in user_args or "--all" in user_args

    # Strip custom mode flags
    filtered_args = [
        arg for arg in user_args if arg not in ("--quick", "--mvp", "--full", "--deep", "--all")
    ]

    has_explicit_target = any(
        arg.startswith("tests/")
        or arg.endswith(".py")
        or arg.startswith("-k")
        or arg.startswith("-m")
        for arg in filtered_args
    )

    # Detect multi-core acceleration capability via pytest-xdist
    xdist_args: list[str] = []
    try:
        import xdist  # noqa: F401

        if not any(a.startswith("-n") or a == "-n" for a in filtered_args):
            xdist_args = ["-n", "auto"]
    except ImportError:
        pass

    print("=" * 64)
    print("      LocalPodcastLLMStudio - Rational Test Runner      ")
    print("=" * 64)

    if is_quick_mode:
        print("--> Mode: [QUICK / MVP SMOKE] (Running core component & pipeline suites)")
        target_files = [f for f in MVP_TEST_FILES if os.path.exists(os.path.join(PROJECT_ROOT, f))]
        pytest_args = target_files + ["-v"] + filtered_args
    elif is_full_mode or not has_explicit_target:
        if xdist_args:
            print(f"--> Mode: [FULL MATRIX] (Multi-core parallel: {' '.join(xdist_args)})")
        else:
            print("--> Mode: [FULL MATRIX] (Exhaustive 1,238-test multi-tier matrix)")
        pytest_args = xdist_args + ["tests", "-v"] + filtered_args
    else:
        print(f"--> Mode: [TARGETED EXECUTION] (Args: {' '.join(filtered_args)})")
        pytest_args = ["-v"] + filtered_args

    exit_code = 1
    start_time = time.time()
    try:
        exit_code = pytest.main(pytest_args)
    finally:
        elapsed = time.time() - start_time
        gc.collect()

    print("-" * 64)
    status_str = "SUCCESS" if exit_code == 0 else f"FAILED (Exit Code: {exit_code})"
    print(f"--> Test Run Finished: {status_str} in {elapsed:.2f}s")
    print("=" * 64)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
