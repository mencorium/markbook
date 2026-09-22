# /markbook/backend/paths.py
"""Where Markbook keeps files outside the database: logs, autosaved drafts and backups."""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "Markbook"


def app_dir() -> Path:
    """%LOCALAPPDATA%\\Markbook on Windows, ~/.markbook elsewhere."""
    base = os.getenv("MARKBOOK_HOME")
    if base:
        d = Path(base)
    elif os.name == "nt":
        d = Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_DIR_NAME
    else:
        d = Path.home() / ".markbook"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sub_dir(name: str) -> Path:
    d = app_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    return sub_dir("logs")


def drafts_dir() -> Path:
    return sub_dir("drafts")


def backups_dir() -> Path:
    return sub_dir("backups")