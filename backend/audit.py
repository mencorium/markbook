# /markbook/backend/audit.py
"""The record of who changed what.

Marks are the kind of thing that gets questioned weeks later ("this was 65, not 45"),
so every change to a total, and every archive, restore or deletion, is written here.
"""
from __future__ import annotations

import datetime as dt
import getpass
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog

_user: str | None = None


def machine_user() -> str:
    try:
        return getpass.getuser()[:80] or "teacher"
    except Exception:  # noqa: BLE001 - some environments have no user name at all
        return "teacher"


def current_user() -> str:
    """The name written against each change: from Settings, else the computer's user name."""
    global _user
    if _user is None:
        try:
            from .services.records import get_settings
            _user = (get_settings().get("user_name") or "").strip() or machine_user()
        except Exception:  # noqa: BLE001 - settings unreadable at startup
            return machine_user()
    return _user


def forget_user() -> None:
    """Called when the name is changed in Settings."""
    global _user
    _user = None


def log(s: Session, action: str, *, entity: str, entity_id: int | None = None, student_id: int | None = None,
        assessment_id: int | None = None, old=None, new=None, detail: str = "", who: str | None = None) -> None:
    """Write one entry inside the caller's transaction, so history and change commit together."""
    fmt = lambda v: None if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))[:60]
    s.add(AuditLog(at=dt.datetime.now(), who=(who or current_user())[:80], action=action, entity=entity, entity_id=entity_id,
                   student_id=student_id, assessment_id=assessment_id, old_value=fmt(old), new_value=fmt(new), detail=detail[:2000]))


def record(action: str, **kw) -> None:
    """Write one entry in its own transaction, for events outside a service call."""
    from .db import session_scope
    with session_scope() as s:
        log(s, action, **kw)


@dataclass
class Entry:
    at: dt.datetime
    who: str
    action: str
    entity: str
    entity_id: int | None
    student_id: int | None
    assessment_id: int | None
    old_value: str | None
    new_value: str | None
    detail: str


def recent(limit: int = 400, *, action_prefix: str | None = None, student_id: int | None = None,
           assessment_id: int | None = None, session: Session | None = None) -> list[Entry]:
    from .db import session_scope

    def query(s: Session) -> list[Entry]:
        q = select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(limit)
        if action_prefix:
            q = q.where(AuditLog.action.startswith(action_prefix))
        if student_id:
            q = q.where(AuditLog.student_id == student_id)
        if assessment_id:
            q = q.where(AuditLog.assessment_id == assessment_id)
        return [Entry(r.at, r.who, r.action, r.entity, r.entity_id, r.student_id, r.assessment_id,
                      r.old_value, r.new_value, r.detail or "") for r in s.scalars(q)]
    if session is not None:
        return query(session)
    with session_scope() as s:
        return query(s)