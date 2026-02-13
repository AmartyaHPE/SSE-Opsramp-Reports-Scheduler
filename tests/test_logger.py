"""Tests for the logger utility."""

import logging

from opsramp_automation.utils.logger import setup_logger, get_logger


class TestSetupLogger:
    """setup_logger should configure handlers and level correctly."""

    def test_returns_logger_with_client_name(self):
        logger = setup_logger("test-logger-1", level="DEBUG")
        assert logger.name == "test-logger-1"
        assert logger.level == logging.DEBUG

    def test_console_handler_attached(self):
        logger = setup_logger("test-logger-2", level="INFO")
        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler in handler_types

    def test_file_handler_attached(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        logger = setup_logger("test-logger-3", level="INFO", log_file=log_file)
        handler_types = [type(h) for h in logger.handlers]
        assert logging.FileHandler in handler_types

    def test_no_duplicate_handlers_on_repeated_calls(self):
        logger1 = setup_logger("test-logger-4", level="INFO")
        count = len(logger1.handlers)
        logger2 = setup_logger("test-logger-4", level="INFO")
        assert len(logger2.handlers) == count
        assert logger1 is logger2

    def test_log_message_written_to_file(self, tmp_path):
        log_file = str(tmp_path / "output.log")
        logger = setup_logger("test-logger-5", level="INFO", log_file=log_file)
        logger.info("hello from test")

        with open(log_file, "r") as f:
            content = f.read()
        assert "hello from test" in content
        assert "test-logger-5" in content

    def test_propagate_disabled(self):
        logger = setup_logger("test-logger-6")
        assert logger.propagate is False


class TestGetLogger:
    """get_logger should return the same logger created by setup_logger."""

    def test_retrieves_existing_logger(self):
        original = setup_logger("test-logger-7", level="WARNING")
        retrieved = get_logger("test-logger-7")
        assert retrieved is original
        assert retrieved.level == logging.WARNING
