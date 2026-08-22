"""
Tests for Windows Batch Script Control-Flow Error Handling (Track B Remediation)
================================================================================
Empirically verifies that:
1. `build_exe.bat` and `setup.bat` terminate immediately upon encountering errors.
2. Error exit codes (e.g., 1) are preserved and returned to the caller.
3. Failure paths never fall through to print 'BUILD SUCCESSFUL' or execute subsequent steps.
4. Non-interactive CI flags (--no-pause, -nopause, CI=true, GITHUB_ACTIONS=true) prevent blocking.
5. Happy path builds and setups succeed with exit code 0 and valid outputs.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_BAT = REPO_ROOT / "build_exe.bat"
SETUP_BAT = REPO_ROOT / "setup.bat"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch script tests require Windows")
class TestBatchExitControlFlow:
    """Test suite verifying exit control-flow remediation in build_exe.bat and setup.bat."""

    def test_setup_bat_happy_path(self):
        """Verify that setup.bat --no-pause completes with exit code 0."""
        assert SETUP_BAT.exists(), f"setup.bat not found at {SETUP_BAT}"
        proc = subprocess.run(
            ["cmd.exe", "/c", str(SETUP_BAT), "--no-pause"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"setup.bat failed with code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "Setup complete" in proc.stdout

    def test_setup_bat_ci_mode(self):
        """Verify that GITHUB_ACTIONS environment variable triggers non-interactive execution."""
        env = os.environ.copy()
        env["GITHUB_ACTIONS"] = "true"
        proc = subprocess.run(
            ["cmd.exe", "/c", str(SETUP_BAT)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=env,
        )
        assert proc.returncode == 0, f"setup.bat failed in CI mode:\n{proc.stdout}\n{proc.stderr}"
        assert "Setup complete" in proc.stdout

    def test_build_exe_bat_locked_binary_failure_immediate_exit(self):
        """
        Adversarial test:
        When dist/LocalPodcastLLMStudio.exe is locked by an active process,
        build_exe.bat must fail immediately with non-zero exit code (1),
        must NOT continue to PyInstaller compilation, and must NOT print 'BUILD SUCCESSFUL'.
        """
        assert BUILD_BAT.exists(), f"build_exe.bat not found at {BUILD_BAT}"
        dist_dir = REPO_ROOT / "dist"
        dist_dir.mkdir(exist_ok=True)
        exe_file = dist_dir / "LocalPodcastLLMStudio.exe"
        if not exe_file.exists():
            exe_file.write_bytes(b"dummy binary content for file lock testing")

        # Open file in exclusive write mode to simulate process lock
        lock_fd = os.open(str(exe_file), os.O_RDWR)
        try:
            proc = subprocess.run(
                ["cmd.exe", "/c", str(BUILD_BAT), "--no-pause"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )

            # Must return non-zero exit code
            assert proc.returncode != 0, f"Expected non-zero exit code, got {proc.returncode}"
            assert proc.returncode == 1, f"Expected exit code 1, got {proc.returncode}"

            # Must contain lock error message
            assert "locked by a running process" in proc.stdout or "locked" in proc.stdout

            # Must NOT contain success banner or PyInstaller completion message
            assert "BUILD SUCCESSFUL" not in proc.stdout
            assert "[OK] PyInstaller compilation completed" not in proc.stdout
        finally:
            os.close(lock_fd)
            # Ensure file is completely released by kernel and unlinked
            for _ in range(20):
                try:
                    if exe_file.exists():
                        exe_file.unlink()
                    break
                except OSError:
                    time.sleep(0.2)
            time.sleep(0.5)

    def test_build_exe_bat_pyinstaller_crash_immediate_exit(self):
        """
        Adversarial test:
        Simulate a PyInstaller compilation failure by temporarily providing an invalid spec file.
        build_exe.bat must immediately exit with non-zero exit code, and must NEVER
        print '[OK] PyInstaller compilation completed' or 'BUILD SUCCESSFUL'.
        """
        spec_file = REPO_ROOT / "LocalPodcastLLMStudio.spec"
        original_spec = spec_file.read_text(encoding="utf-8")
        assert len(original_spec) > 100

        try:
            spec_file.write_text("INVALID PYTHON SYNTAX ::: RAISE ERROR\n", encoding="utf-8")
            proc = subprocess.run(
                ["cmd.exe", "/c", str(BUILD_BAT), "--no-pause"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )

            # Must return non-zero error code
            assert proc.returncode != 0, f"Expected non-zero exit code, got {proc.returncode}"
            assert proc.returncode == 1, f"Expected exit code 1, got {proc.returncode}"

            # Must report PyInstaller failure
            assert "[ERROR] PyInstaller build failed with exit code" in proc.stdout

            # Must NOT fall through to post-compilation steps
            assert "[OK] PyInstaller compilation completed" not in proc.stdout
            assert "[5/5] Validating output binary" not in proc.stdout
            assert "BUILD SUCCESSFUL" not in proc.stdout
        finally:
            for _ in range(50):
                try:
                    spec_file.write_text(original_spec, encoding="utf-8")
                    if spec_file.read_text(encoding="utf-8") == original_spec:
                        break
                except Exception:
                    time.sleep(0.1)
            time.sleep(1.0)

    @pytest.mark.slow
    def test_build_exe_bat_happy_path(self):
        """Verify that build_exe.bat --no-pause completes cleanly, exits with 0, and produces executable."""
        if os.environ.get("SKIP_SLOW_PACKAGING_TESTS") == "1":
            pytest.skip("Skipping slow PyInstaller packaging test (SKIP_SLOW_PACKAGING_TESTS=1)")
        last_proc = None
        for _attempt in range(3):
            time.sleep(1.0)
            proc = subprocess.run(
                ["cmd.exe", "/c", str(BUILD_BAT), "--no-pause"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=240,
            )
            last_proc = proc
            if proc.returncode == 0:
                break

        assert last_proc is not None
        assert last_proc.returncode == 0, (
            f"build_exe.bat failed with code {last_proc.returncode}:\n{last_proc.stdout}\n{last_proc.stderr}"
        )
        assert "BUILD SUCCESSFUL" in last_proc.stdout
        target_exe = REPO_ROOT / "dist" / "LocalPodcastLLMStudio.exe"
        assert target_exe.exists(), "dist/LocalPodcastLLMStudio.exe does not exist"
        assert target_exe.stat().st_size > 1_000_000, "Executable is unexpectedly small (< 1MB)"
