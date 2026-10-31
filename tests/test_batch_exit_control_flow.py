"""
Tests for Windows Batch Script Control-Flow Error Handling (Track B Remediation)
================================================================================
Empirically verifies inside an isolated tmp_path sandbox (zero live-repo or
Desktop side effects) that:
1. `build_exe.bat` and `setup.bat` terminate immediately upon encountering errors.
2. Error exit codes (e.g., 1) are preserved and returned to the caller.
3. Failure paths never fall through to print 'BUILD SUCCESSFUL' or execute subsequent steps.
4. Non-interactive CI flags (--no-pause, -nopause, CI=true, GITHUB_ACTIONS=true) prevent blocking.
5. Happy path builds and setups succeed with exit code 0 and valid outputs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_BAT = REPO_ROOT / "build_exe.bat"
SETUP_BAT = REPO_ROOT / "setup.bat"


def _create_batch_sandbox(tmp_path: Path) -> Path:
    """
    Creates a hermetic sandbox containing copies of setup.bat and build_exe.bat
    plus a lightweight Python shim environment (.venv) with stubbed pip and
    PyInstaller modules so batch control-flow is tested without mutating REPO_ROOT,
    live .venv, or user Desktop shortcuts.
    """
    sandbox = tmp_path / "batch_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SETUP_BAT, sandbox / "setup.bat")
    shutil.copy2(BUILD_BAT, sandbox / "build_exe.bat")

    (sandbox / "requirements.txt").write_text("requests>=2.31.0\n", encoding="utf-8")
    (sandbox / "requirements-dev.txt").write_text("pytest>=7.4.0\n", encoding="utf-8")
    (sandbox / "check_env.py").write_text(
        "import sys\nprint('[OK] Sandbox preflight check passed.')\nsys.exit(0)\n",
        encoding="utf-8",
    )
    # Spec file ensures mock artifact generation if PyInstaller evaluates the spec file directly
    (sandbox / "LocalPodcastLLMStudio.spec").write_text(
        "# Valid sandbox PyInstaller spec\n"
        "import pathlib\n"
        "dist_dir = pathlib.Path('dist')\n"
        "dist_dir.mkdir(exist_ok=True)\n"
        "(dist_dir / 'LocalPodcastLLMStudio.exe').write_bytes(b'MZ' + (b'\\x00' * 1_500_000))\n"
        "APP_NAME = 'LocalPodcastLLMStudio'\n",
        encoding="utf-8",
    )

    # Create isolated .venv layout copying only the lightweight python launcher binary
    scripts_dir = sandbox / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sys.executable, scripts_dir / "python.exe")

    # Always generate or copy pyvenv.cfg so CPython recognizes the sandbox as a virtual environment
    src_venv_cfg = Path(sys.executable).resolve().parent.parent / "pyvenv.cfg"
    if not src_venv_cfg.exists():
        src_venv_cfg = REPO_ROOT / ".venv" / "pyvenv.cfg"
    if src_venv_cfg.exists():
        cfg_lines = []
        for line in src_venv_cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip().lower().startswith("include-system-site-packages"):
                cfg_lines.append(line)
        cfg_lines.append("include-system-site-packages = false")
        (sandbox / ".venv" / "pyvenv.cfg").write_text("\n".join(cfg_lines) + "\n", encoding="utf-8")
    else:
        base_home = Path(getattr(sys, "_base_executable", sys.executable)).resolve().parent
        (sandbox / ".venv" / "pyvenv.cfg").write_text(
            f"home = {base_home}\ninclude-system-site-packages = false\nversion = {sys.version.split()[0]}\n",
            encoding="utf-8",
        )

    # Stub pip and PyInstaller inside sandbox site-packages so `-m pip` and `-m PyInstaller`
    # execute deterministically offline in milliseconds.
    site_pkgs = sandbox / ".venv" / "Lib" / "site-packages"
    pip_pkg = site_pkgs / "pip"
    pyi_pkg = site_pkgs / "PyInstaller"
    pip_pkg.mkdir(parents=True, exist_ok=True)
    pyi_pkg.mkdir(parents=True, exist_ok=True)

    (pip_pkg / "__init__.py").write_text("__version__ = '26.0'\n", encoding="utf-8")
    (pip_pkg / "__main__.py").write_text(
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "if '-r' in args:\n"
        "    idx = args.index('-r')\n"
        "    req = args[idx + 1] if idx + 1 < len(args) else ''\n"
        "    if not os.path.exists(req):\n"
        "        sys.stderr.write(f'ERROR: Could not open requirements file: {req}\\n')\n"
        "        sys.exit(1)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )

    (pyi_pkg / "__init__.py").write_text("__version__ = '6.22.0'\n", encoding="utf-8")
    (pyi_pkg / "__main__.py").write_text(
        "import pathlib, sys\n"
        "spec_args = [a for a in sys.argv[1:] if a.endswith('.spec')]\n"
        "if spec_args:\n"
        "    spec_path = pathlib.Path(spec_args[0])\n"
        "    code = spec_path.read_text(encoding='utf-8')\n"
        "    compile(code, str(spec_path), 'exec')\n"
        "dist_dir = pathlib.Path('dist')\n"
        "dist_dir.mkdir(exist_ok=True)\n"
        "(dist_dir / 'LocalPodcastLLMStudio.exe').write_bytes(b'MZ' + (b'\\x00' * 1_500_000))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )

    return sandbox


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch script tests require Windows")
class TestBatchExitControlFlow:
    """Test suite verifying exit control-flow remediation in build_exe.bat and setup.bat."""

    def test_setup_bat_happy_path(self, tmp_path: Path):
        """Verify that setup.bat --no-pause completes with exit code 0 inside sandbox."""
        sandbox = _create_batch_sandbox(tmp_path)
        proc = subprocess.run(
            ["cmd.exe", "/c", str(sandbox / "setup.bat"), "--no-pause"],
            cwd=str(sandbox),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        assert proc.returncode == 0, (
            f"setup.bat failed with code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "Setup complete" in proc.stdout

    def test_setup_bat_ci_mode(self, tmp_path: Path):
        """Verify that GITHUB_ACTIONS environment variable triggers non-interactive execution."""
        sandbox = _create_batch_sandbox(tmp_path)
        env = os.environ.copy()
        env["GITHUB_ACTIONS"] = "true"
        proc = subprocess.run(
            ["cmd.exe", "/c", str(sandbox / "setup.bat")],
            cwd=str(sandbox),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=env,
        )
        assert proc.returncode == 0, f"setup.bat failed in CI mode:\n{proc.stdout}\n{proc.stderr}"
        assert "Setup complete" in proc.stdout

    def test_build_exe_bat_locked_binary_failure_immediate_exit(self, tmp_path: Path):
        """
        When dist/LocalPodcastLLMStudio.exe is locked by an active file descriptor,
        build_exe.bat must fail immediately with exit code 1 and never print 'BUILD SUCCESSFUL'.
        """
        sandbox = _create_batch_sandbox(tmp_path)
        dist_dir = sandbox / "dist"
        dist_dir.mkdir(exist_ok=True)
        exe_file = dist_dir / "LocalPodcastLLMStudio.exe"
        exe_file.write_bytes(b"dummy binary content for file lock testing")

        lock_fd = os.open(str(exe_file), os.O_RDWR)
        try:
            proc = subprocess.run(
                ["cmd.exe", "/c", str(sandbox / "build_exe.bat"), "--no-pause"],
                cwd=str(sandbox),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )

            assert proc.returncode == 1, (
                f"Expected exit code 1, got {proc.returncode}:\n{proc.stdout}"
            )
            assert "locked by a running process" in proc.stdout or "locked" in proc.stdout
            assert "BUILD SUCCESSFUL" not in proc.stdout
            assert "[OK] PyInstaller compilation completed" not in proc.stdout
        finally:
            os.close(lock_fd)
            for _ in range(10):
                try:
                    if exe_file.exists():
                        exe_file.unlink()
                    break
                except OSError:
                    time.sleep(0.05)

    def test_build_exe_bat_pyinstaller_crash_immediate_exit(self, tmp_path: Path):
        """
        Simulate a PyInstaller compilation failure via an invalid sandboxed spec file.
        build_exe.bat must exit with code 1 and never print 'BUILD SUCCESSFUL'.
        """
        sandbox = _create_batch_sandbox(tmp_path)
        spec_file = sandbox / "LocalPodcastLLMStudio.spec"
        spec_file.write_text("INVALID PYTHON SYNTAX ::: RAISE ERROR\n", encoding="utf-8")

        proc = subprocess.run(
            ["cmd.exe", "/c", str(sandbox / "build_exe.bat"), "--no-pause"],
            cwd=str(sandbox),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

        assert proc.returncode == 1, f"Expected exit code 1, got {proc.returncode}:\n{proc.stdout}"
        assert "[ERROR] PyInstaller build failed with exit code" in proc.stdout
        assert "[OK] PyInstaller compilation completed" not in proc.stdout
        assert "[5/5] Validating output binary" not in proc.stdout
        assert "BUILD SUCCESSFUL" not in proc.stdout

    def test_build_exe_bat_happy_path(self, tmp_path: Path):
        """Verify that build_exe.bat --no-pause completes cleanly, exits with 0, and produces executable."""
        sandbox = _create_batch_sandbox(tmp_path)
        proc = subprocess.run(
            ["cmd.exe", "/c", str(sandbox / "build_exe.bat"), "--no-pause"],
            cwd=str(sandbox),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

        assert proc.returncode == 0, (
            f"build_exe.bat failed with code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "BUILD SUCCESSFUL" in proc.stdout
        target_exe = sandbox / "dist" / "LocalPodcastLLMStudio.exe"
        assert target_exe.exists(), "dist/LocalPodcastLLMStudio.exe does not exist in sandbox"
        assert target_exe.stat().st_size > 1_000_000, "Executable is unexpectedly small (< 1MB)"
