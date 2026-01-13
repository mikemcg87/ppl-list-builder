"""Logging setup and configuration."""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(
    log_dir: str = "logs",
    log_level: int = logging.INFO,
    log_to_console: bool = True
) -> logging.Logger:
    """Set up logging for the application.

    Args:
        log_dir: Directory for log files
        log_level: Logging level (logging.DEBUG, logging.INFO, etc.)
        log_to_console: Also log to console/stdout

    Returns:
        Configured logger instance
    """
    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger("ppl-list-builder")
    logger.setLevel(log_level)

    # Clear existing handlers
    logger.handlers = []

    # Log filename with timestamp
    log_filename = log_path / f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # File handler
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    if log_to_console:
        logger.addHandler(console_handler)

    return logger
