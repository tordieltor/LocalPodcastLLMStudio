"""
LocalPodcastLLMStudio - Logger Subsystem Unit & Integration Tests (tests/test_logger.py)
=======================================================================================
Verifies core.logger log path resolution, root logger setup, rotating file handler
initialization, child logger naming hierarchy, and UI log file opener.
"""

import logging
import os
from unittest.mock import MagicMock, patch

from core.logger import (
    get_log_file_path,
    get_logger,
    resolve_log_directory,
    setup_logging,
)
from ui.main_window import MainWindow


class TestLoggerSubsystem:
    """Verifies logger resolution, handler attachment, and message formatting."""

    def test_resolve_log_directory_creates_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        d = resolve_log_directory()
        assert os.path.exists(d)

    def test_get_log_file_path_returns_app_log(self):
        p = get_log_file_path()
        assert p.endswith("app.log")
        assert os.path.isabs(p)

    def test_setup_logging_and_get_logger(self, tmp_path):
        log_file = str(tmp_path / "test_run.log")
        root = setup_logging(log_level=logging.DEBUG, log_file=log_file, force=True)
        assert root.name == "localpodcastllmstudio"

        logger_child = get_logger("core.engine")
        assert logger_child.name == "localpodcastllmstudio.core.engine"

        # Log some messages
        logger_child.info("Test info message for verification")
        logger_child.debug("Test debug message")

        assert os.path.exists(log_file)
        with open(log_file, encoding="utf-8") as f:
            content = f.read()
        assert "Test info message for verification" in content
        assert "[INFO ]" in content or "[INFO]" in content

    def test_get_logger_prefix_idempotence(self):
        l1 = get_logger("localpodcastllmstudio.subsystem")
        assert l1.name == "localpodcastllmstudio.subsystem"

        l2 = get_logger("subsystem")
        assert l2.name == "localpodcastllmstudio.subsystem"

    def test_main_window_open_logs(self):
        mock_win = MagicMock(spec=MainWindow)
        with patch("os.path.isfile", return_value=True), patch("os.startfile") as mock_startfile:
            MainWindow._open_logs(mock_win)
            mock_startfile.assert_called_once()
