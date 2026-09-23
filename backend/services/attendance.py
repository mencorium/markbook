# /markbook/backend/services/attendance.py
"""Daily registers per class."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from ..db import session_scope
from ..models import AttendanceDay, AttendanceEntry
from ..schema import AttendanceDayInfo


def _info(d: AttendanceDay) -> AttendanceDayInfo:
    return AttendanceDayInfo(d.id, d.class_id, d.date, [e.student_id for e in d.entries],
                             [e.student_id for e in d.entries if not e.present], d.term_id)


def list_days(class_id: int | None = None, term_id: int | None = None) -> list[AttendanceDayInfo]:
    with session_scope() as s:
        q = select(AttendanceDay).order_by(AttendanceDay.date.desc())
        if class_id:
            q = q.where(AttendanceDay.class_id == class_id)
        if term_id:
            q = q.where(AttendanceDay.term_id == term_id)
        return [_info(d) for d in s.scalars(q)]


def get_day(class_id: int, date: dt.date) -> AttendanceDayInfo | None:
    with session_scope() as s:
        d = s.scalar(select(AttendanceDay).where(AttendanceDay.class_id == class_id, AttendanceDay.date == date))
        return _info(d) if d else None


def save_day(class_id: int, date: dt.date, roster: list[int], absent: set[int]) -> AttendanceDayInfo:
    """roster = students expected that day (the class list); absent ⊆ roster."""
    with session_scope() as s:
        d = s.scalar(select(AttendanceDay).where(AttendanceDay.class_id == class_id, AttendanceDay.date == date))
        if d is None:
            from .assessments import _term_for
            d = AttendanceDay(class_id=class_id, date=date, term_id=_term_for(date))
            s.add(d)
            s.flush()
        existing = {e.student_id: e for e in d.entries}
        for sid in roster:
            e = existing.pop(sid, None)
            if e is None:
                d.entries.append(AttendanceEntry(student_id=sid, present=sid not in absent))
            else:
                e.present = sid not in absent
        for e in existing.values():
            d.entries.remove(e)
        s.flush()
        return _info(d)


def delete_day(class_id: int, date: dt.date) -> None:
    with session_scope() as s:
        d = s.scalar(select(AttendanceDay).where(AttendanceDay.class_id == class_id, AttendanceDay.date == date))
        if d:
            s.delete(d)