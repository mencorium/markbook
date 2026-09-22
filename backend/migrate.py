# /markbook/backend/migrate.py
"""Bring the database up to date at startup.

A database created before migrations existed has the tables but no alembic_version row;
it is stamped at the baseline first, so the same upgrade path works for everyone.

Each step commits on its own: if the app is interrupted part way, whatever finished stays
done and the next start carries on from there.
"""
from __future__ import annotations

import time
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from .db import engine
from .log import get
from .models import Base

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "0001_initial"
LOCK_TIMEOUT = "15s"          # rather fail with a message than hang on a lock another session holds
log = get("migrate")


class MigrationError(RuntimeError):
    """Message is written for the person using the app."""


def _config() -> Config:
    ini, scripts = ROOT / "alembic.ini", ROOT / "migrations"
    if not scripts.is_dir():
        raise MigrationError(f"The migrations folder is missing from {ROOT}. Copy it from the project and start again.")
    cfg = Config(str(ini) if ini.exists() else None)
    cfg.set_main_option("script_location", str(scripts))
    return cfg


def _stamp_target(connection) -> str:
    """Which revision an untracked schema really matches: the newest one if it already looks
    like the current models, otherwise the baseline so the migrations can bring it forward."""
    differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    if not differences:
        return "head"
    log.info("untracked schema differs from the current models in %d place(s): starting from the baseline", len(differences))
    return BASELINE


def _guard(connection) -> None:
    """Postgres only: don't wait forever behind another connection's lock."""
    if connection.dialect.name == "postgresql":
        connection.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))


def current_revision() -> str | None:
    with engine().connect() as c:
        return MigrationContext.configure(c).get_current_revision()


def head_revision() -> str | None:
    return ScriptDirectory.from_config(_config()).get_current_head()


def pending() -> bool:
    return current_revision() != head_revision()


def upgrade() -> str | None:
    """Create or migrate the schema. Returns the revision now in place. Safe to run again after an interruption."""
    cfg = _config()
    started = time.monotonic()
    with engine().connect() as c:
        at = MigrationContext.configure(c).get_current_revision()
        legacy = at is None and inspect(c).has_table("students")

    try:
        if legacy:
            with engine().begin() as connection:          # committed on its own, before any migration runs
                _guard(connection)
                target = _stamp_target(connection)
                log.info("existing database without a migration history: stamping %s", target)
                cfg.attributes["connection"] = connection
                command.stamp(cfg, target)
            at = current_revision()
            log.info("stamped at %s", at)

        head = head_revision()
        if at == head:
            log.info("database already at %s", head)
            return at
        log.info("migrating database: %s -> %s", at or "empty", head)
        with engine().begin() as connection:
            _guard(connection)
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
        after = current_revision()
        log.info("database migrated to %s in %.1fs", after, time.monotonic() - started)
        return after
    except OperationalError as e:
        if "lock" in str(e).lower():
            log.error("migration blocked by another connection: %s", e)
            raise MigrationError(
                "The database is in use by another program, so it could not be updated.\n\n"
                "Close any other copy of Markbook, pgAdmin or psql that is connected, then start again.") from e
        raise
    except KeyboardInterrupt:
        log.warning("migration interrupted; nothing unfinished was committed — starting again is safe")
        raise