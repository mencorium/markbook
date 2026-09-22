# /markbook/backend/migrate.py
"""Bring the database up to date at startup.

A database created before migrations existed has the tables but no alembic_version row;
it is stamped at the baseline first, so the same upgrade path works for everyone.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from .db import engine
from .log import get

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "0001_initial"
log = get("migrate")


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def current_revision() -> str | None:
    with engine().connect() as c:
        return MigrationContext.configure(c).get_current_revision()


def head_revision() -> str | None:
    return ScriptDirectory.from_config(_config()).get_current_head()


def pending() -> bool:
    return current_revision() != head_revision()


def upgrade() -> str | None:
    """Create or migrate the schema. Returns the revision now in place."""
    cfg = _config()
    with engine().begin() as connection:
        cfg.attributes["connection"] = connection
        at = MigrationContext.configure(connection).get_current_revision()
        if at is None and inspect(connection).has_table("students"):
            log.info("existing database without a migration history: stamping %s", BASELINE)
            command.stamp(cfg, BASELINE)
        before = at
        command.upgrade(cfg, "head")
        after = MigrationContext.configure(connection).get_current_revision()
    if before != after:
        log.info("database migrated: %s -> %s", before or "empty", after)
    return after