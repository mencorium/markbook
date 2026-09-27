# /markbook/backend/about.py
"""Who made this, which version it is, and where to go for help.

One place for the facts that appear in the About screen, the window title, the log header
and the installer, so they can never drift apart.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass

APP_NAME = "Markbook"
VERSION = "1.0.0"
TAGLINE = "Student progress analysis for teachers"

TEAM = "Mencorium"
GITHUB_ORG = "mencorium"
GITHUB_REPO = "markbook"
GITHUB_URL = f"https://github.com/{GITHUB_ORG}/{GITHUB_REPO}"
ISSUES_URL = f"{GITHUB_URL}/issues"

DESCRIPTION = (
    "Markbook keeps a teacher's marks in one place and does the arithmetic that usually eats an "
    "evening: averages, positions, NECTA points and divisions, term and annual results, report "
    "cards and mark sheets. It records marks question by question, so a paper shows which topics "
    "the class actually found hard, and it ties attendance to the lessons on your timetable."
)


@dataclass(frozen=True)
class Build:
    """What is running right now — the first thing to ask for in a bug report."""
    app: str
    version: str
    python: str
    qt: str
    system: str
    database: str
    revision: str

    def as_text(self) -> str:
        return "\n".join([
            f"{self.app} {self.version}",
            f"Python {self.python}",
            f"Qt {self.qt}",
            f"System {self.system}",
            f"Database {self.database}",
            f"Schema {self.revision}",
        ])


def qt_version() -> str:
    try:
        from PyQt6.QtCore import QT_VERSION_STR
        return QT_VERSION_STR
    except Exception:  # noqa: BLE001 - about must never be the thing that crashes
        return "unknown"


def database_summary() -> str:
    """Server and database name, never the password."""
    try:
        from sqlalchemy.engine import make_url

        from .config import get_config
        url = make_url(get_config().database_url)
        return f"PostgreSQL at {url.host or 'localhost'}:{url.port or 5432}/{url.database}"
    except Exception:  # noqa: BLE001
        return "not configured"


def schema_revision() -> str:
    try:
        from .migrate import current_revision
        return current_revision() or "not created yet"
    except Exception:  # noqa: BLE001
        return "unknown"


def build() -> Build:
    return Build(
        app=APP_NAME,
        version=VERSION,
        python=platform.python_version(),
        qt=qt_version(),
        system=f"{platform.system()} {platform.release()} ({platform.machine()})",
        database=database_summary(),
        revision=schema_revision(),
    )


def frozen_note() -> str:
    return "installed build" if getattr(sys, "frozen", False) else "running from source"