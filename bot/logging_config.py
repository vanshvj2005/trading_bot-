"""Logging configuration for the trading bot.

Sets up a single logger that writes to both ``logs/trading_bot.log`` (full
detail, including stack traces) and, optionally, stderr. The log directory is
created on demand. INFO is used for normal flow; ERROR (with ``exc_info``) is
used for failures.

Security note: this module never logs API secrets. Callers are responsible for
not passing secrets into log messages; see :func:`redact_secret` for masking
helper used when a value must be referenced.
"""

from __future__ import annotations

import logging
import os
from logging import Logger
from pathlib import Path

LOGGER_NAME = "trading_bot"
DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
DEFAULT_LOG_FILE = "trading_bot.log"

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def redact_secret(value: str | None) -> str:
    """Return a masked representation of a sensitive value, safe to log.

    Shows only that a value is present and its length class, never the value
    itself. ``None`` or empty strings render as ``"<unset>"``.

    Args:
        value: The sensitive string (e.g. an API key) to mask.

    Returns:
        A redacted, log-safe string such as ``"****(set, len=64)"``.
    """
    if not value:
        return "<unset>"
    return f"****(set, len={len(value)})"


def setup_logging(
    log_dir: Path | str = DEFAULT_LOG_DIR,
    log_file: str = DEFAULT_LOG_FILE,
    level: int = logging.INFO,
    console: bool = False,
) -> Logger:
    """Configure and return the shared trading-bot logger.

    Idempotent: calling it more than once will not attach duplicate handlers.

    Args:
        log_dir: Directory for the log file; created if it does not exist.
        log_file: Log file name within ``log_dir``.
        level: Minimum level for the file handler (default ``INFO``).
        console: If ``True``, also emit WARNING+ records to stderr. The CLI
            handles human-facing console output itself, so this defaults to
            ``False`` to avoid double-printing.

    Returns:
        The configured :class:`logging.Logger` named ``"trading_bot"``.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    # Prevent records from also bubbling to the root logger's handlers.
    logger.propagate = False

    if logger.handlers:
        # Already configured in this process; reuse it.
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.WARNING)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


def get_logger() -> Logger:
    """Return the shared trading-bot logger, configuring it if needed.

    Returns:
        The :class:`logging.Logger` named ``"trading_bot"``.
    """
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        return setup_logging()
    return logger
