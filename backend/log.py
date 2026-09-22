# /markbook/backend/log.py
"""Logging to a rotating file, so a problem a teacher hits can be looked at afterwards."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .paths import logs_dir

LOG_FILE = "markbook.log"
_configured = False


def log_path() -> Path:
    return logs_dir() / LOG_FILE


def setup(level: int = logging.INFO) -> Path:
    """Five files of 1 MB each. Safe to call more than once."""
    global _configured
    if _configured:
        return log_path()
    handler = logging.handlers.RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    console.setLevel(logging.WARNING)
    root.addHandler(console)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    _configured = True
    return log_path()


def install_excepthook() -> None:
    """Anything that escapes the UI still reaches the log instead of a console nobody sees."""
    previous = sys.excepthook

    def hook(kind, value, tb):
        logging.getLogger("markbook").critical("Unhandled exception", exc_info=(kind, value, tb))
        previous(kind, value, tb)
    sys.excepthook = hook


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"markbook.{name}")