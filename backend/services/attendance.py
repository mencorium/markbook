# /markbook/backend/services/attendance.py
"""Daily registers per class."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from .. import attendance_codes as AC
from ..db import session_scope
from ..models import AttendanceDay, AttendanceEntry
from ..schema import AttendanceDayInfo


def _info(d: AttendanceDay) -> AttendanceDayInfo:
    return AttendanceDayInfo(d.id, d.class_id, d.date, [e.student_id for e in d.entries],
                             [e.student_id for e in d.entries if not AC.is_present(e.status)],
                             d.term_id, d.slot_id, d.subject_id,
                             {e.student_id: e.status for e in d.entries},
                             {e.student_id: e.note or "" for e in d.entries if e.note})


def list_days(class_id: int | None = None, term_id: int | None = None, subject_id: int | None = None) -> list[AttendanceDayInfo]:
    with session_scope() as s:
        q = select(AttendanceDay).order_by(AttendanceDay.date.desc(), AttendanceDay.id.desc())
        if subject_id:
            q = q.where(AttendanceDay.subject_id == subject_id)
        if class_id:
            q = q.where(AttendanceDay.class_id == class_id)
        if term_id:
            q = q.where(AttendanceDay.term_id == term_id)
        return [_info(d) for d in s.scalars(q)]


def get_day(class_id: int, date: dt.date, slot_id: int | None = None) -> AttendanceDayInfo | None:
    """The register for one session, or the whole-day register when slot_id is None."""
    with session_scope() as s:
        d = s.scalar(select(AttendanceDay).where(AttendanceDay.class_id == class_id, AttendanceDay.date == date,
                                                 AttendanceDay.slot_id == slot_id if slot_id else AttendanceDay.slot_id.is_(None)))
        return _info(d) if d else None


def save_day(class_id: int, date: dt.date, roster: list[int], absent: set[int] | None = None, slot_id: int | None = None,
             subject_id: int | None = None, status: dict[int, str] | None = None,
             notes: dict[int, str] | None = None) -> AttendanceDayInfo:
    """roster = students expected at that session (the class list).

    status gives each student an attendance code (P, A, S, PM, SS). `absent` is still accepted
    for callers that only know present/absent — those students are recorded as plain absent."""
    with session_scope() as s:
        d = s.scalar(select(AttendanceDay).where(AttendanceDay.class_id == class_id, AttendanceDay.date == date,
                                                 AttendanceDay.slot_id == slot_id if slot_id else AttendanceDay.slot_id.is_(None)))
        if d is None:
            from .assessments import _term_for
            d = AttendanceDay(class_id=class_id, date=date, term_id=_term_for(date), slot_id=slot_id, subject_id=subject_id)
            s.add(d)
            s.flush()
        d.slot_id, d.subject_id = slot_id, subject_id
        absent = absent or set()
        codes = dict(status or {})
        for sid in roster:                          # callers passing only `absent` still work
            codes.setdefault(sid, AC.ABSENT if sid in absent else AC.PRESENT)
        existing = {e.student_id: e for e in d.entries}
        for sid in roster:
            code = AC.get(codes.get(sid)).code
            note = (notes or {}).get(sid, "")[:120]
            e = existing.pop(sid, None)
            if e is None:
                d.entries.append(AttendanceEntry(student_id=sid, status=code, note=note))
            else:
                e.status, e.note = code, note
        for e in existing.values():
            d.entries.remove(e)
        s.flush()
        return _info(d)


def delete_day(class_id: int, date: dt.date, slot_id: int | None = None) -> None:
    with session_scope() as s:
        d = s.scalar(select(AttendanceDay).where(AttendanceDay.class_id == class_id, AttendanceDay.date == date,
                                                 AttendanceDay.slot_id == slot_id if slot_id else AttendanceDay.slot_id.is_(None)))
        if d:
            s.delete(d)