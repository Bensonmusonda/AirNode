"""Structured logging configuration for AirNode.

Provides a rotating file logger plus console output. All modules should
use ``get_logger(__name__)`` instead of ``print()`` so errors are captured
to disk with rotation and timestamps.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from paths import get_data_dir


_LOG_DIR = get_data_dir()
_LOG_FILE = _LOG_DIR / "airnode.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 3  # keep airnode.log, airnode.log.1, airnode.log.2, airnode.log.3

_configured = False


def _ensure_log_dir() -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def setup_logging(verbose: bool = False) -> None:
    """Configure the root logger once. Safe to call multiple times."""
    global _configured
    if _configured:
        return
    _configured = True

    _ensure_log_dir()

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler with rotation
    try:
        file_handler = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)
    except OSError:
        # If the log file can't be created (e.g. read-only dir), fall back
        # to console-only logging rather than crashing at startup.
        pass

    # Console handler — skipped when running windowed (console=False), where
    # sys.stdout may be None or a null sink; the file handler above is the
    # real destination in that case.
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(fmt)
        console_handler.setLevel(logging.INFO)
        root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name."""
    return logging.getLogger(name)