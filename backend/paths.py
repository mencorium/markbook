# /markbook/backend/paths.py
"""Where Markbook keeps files outside the database: logs, autosaved drafts and backups."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "Markbook"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def frozen() -> bool:
    """True when running from a PyInstaller build rather than the source tree."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Read-only files shipped with the app: migrations, alembic.ini, the icon."""
    return Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))


def resource(*parts: str) -> Path:
    return resource_dir().joinpath(*parts)


def install_dir() -> Path:
    """Where the app is installed: the folder holding markbook.exe, or the project root."""
    return Path(sys.executable).resolve().parent if frozen() else PROJECT_ROOT


def icon_path() -> Path | None:
    for name in ("markbook.ico", "markbook.png"):
        p = resource("assets", name)
        if p.exists():
            return p
    return None


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