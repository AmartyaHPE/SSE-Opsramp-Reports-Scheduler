"""
Central logging configuration.

Provides a single `setup_logger()` function that every module uses.
Each client run gets its own logger tagged with the client name,
so logs from multiple containers or runs are easily distinguishable.
"""

import logging
import sys
from typing import Optional


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    client_name: str,
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configure and return a logger for a specific client run.

    Args:
        client_name: Used as the logger name — appears in every log line.
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional file path to also write logs to disk.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(client_name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console handler — always present
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler — optional
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent log propagation to root logger
    logger.propagate = False

    return logger


def get_logger(client_name: str) -> logging.Logger:
    """
    Retrieve an existing logger by client name.
    Use this in sub-modules after `setup_logger()` has been called in main.
    """
    return logging.getLogger(client_name)
