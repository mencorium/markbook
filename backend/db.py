# /markbook/backend/db.py
"""Engine, session factory and schema creation."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_config
from .models import Base

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def init_engine(url: str | None = None) -> Engine:
    """Create (or replace) the global engine. Tests pass their own URL."""
    global _engine, _Session
    _engine = create_engine(url or get_config().database_url, pool_pre_ping=True, future=True)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def engine() -> Engine:
    return _engine or init_engine()


def create_schema() -> None:
    Base.metadata.create_all(engine())


def drop_schema() -> None:
    Base.metadata.drop_all(engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    """One transaction per call: commit on success, roll back on error."""
    if _Session is None:
        init_engine()
    assert _Session is not None
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()