# /markbook/backend/services/timetable.py
"""The weekly timetable: which subject a class has, on which day, at what time.

Attendance is taken against these sessions, so a register always says which lesson it belongs to
and you cannot record one for a day the class was never taught.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from .. import audit
from ..db import session_scope
from ..models import AttendanceDay, TimetableSlot
from ..schema import SlotInfo
from .records import ValidationError
from .terms import current_term, term_for_date

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _info(s: TimetableSlot) -> SlotInfo:
    return SlotInfo(s.id, s.class_id, s.subject_id, s.term_id, s.weekday, s.starts_at, s.ends_at, s.room or "")


def list_slots(class_id: int | None = None, term_id: int | None = -1, subject_id: int | None = None) -> list[SlotInfo]:
    """term_id: an id, None for every term, or -1 (default) for the current term."""
    term = current_term() if term_id == -1 else None
    wanted = term.id if term else (term_id if term_id not in (-1, None) else None)
    with session_scope() as s:
        q = select(TimetableSlot).order_by(TimetableSlot.weekday, TimetableSlot.starts_at)
        if class_id:
            q = q.where(TimetableSlot.class_id == class_id)
        if subject_id:
            q = q.where(TimetableSlot.subject_id == subject_id)
        if wanted:
            q = q.where(TimetableSlot.term_id == wanted)
        return [_info(x) for x in s.scalars(q)]


def save_slot(slot_id: int | None, *, class_id: int, subject_id: int, weekday: int, starts_at: dt.time,
              ends_at: dt.time, room: str = "", term_id: int | None = -1) -> SlotInfo:
    if not 0 <= weekday <= 6:
        raise ValidationError("Choose a day of the week.")
    if ends_at <= starts_at:
        raise ValidationError("The lesson cannot end before it starts.")
    term = current_term() if term_id == -1 else None
    tid = term.id if term else term_id
    with session_scope() as s:
        clash = s.scalar(select(TimetableSlot).where(
            TimetableSlot.class_id == class_id, TimetableSlot.weekday == weekday, TimetableSlot.id != (slot_id or 0),
            TimetableSlot.term_id == tid, TimetableSlot.starts_at < ends_at, TimetableSlot.ends_at > starts_at))
        if clash:
            raise ValidationError(f"This class already has a lesson on {DAYS[weekday]} from "
                                  f"{clash.starts_at:%H:%M} to {clash.ends_at:%H:%M}.")
        x = s.get(TimetableSlot, slot_id) if slot_id else TimetableSlot()
        x.class_id, x.subject_id, x.term_id = class_id, subject_id, tid
        x.weekday, x.starts_at, x.ends_at, x.room = weekday, starts_at, ends_at, room.strip()[:40]
        s.add(x)
        s.flush()
        return _info(x)


def delete_slot(slot_id: int) -> int:
    """The lesson goes; registers already taken for it stay, and keep their subject."""
    with session_scope() as s:
        kept = s.scalar(select(func.count()).select_from(AttendanceDay).where(AttendanceDay.slot_id == slot_id)) or 0
        x = s.get(TimetableSlot, slot_id)
        if x:
            audit.log(s, "timetable.removed", entity="timetable", entity_id=slot_id,
                      detail=f"{DAYS[x.weekday]} {x.starts_at:%H:%M}")
            s.delete(x)
        return kept


def sessions_on(class_id: int, date: dt.date, term_id: int | None = -1) -> list[SlotInfo]:
    """The lessons this class has on that date, earliest first."""
    if term_id == -1:
        term = term_for_date(date) or current_term()
        term_id = term.id if term else None
    return [x for x in list_slots(class_id, term_id) if x.weekday == date.weekday()]


def copy_to_term(class_id: int, from_term_id: int, to_term_id: int) -> int:
    """Reuse last term's timetable instead of typing it again."""
    if from_term_id == to_term_id:
        raise ValidationError("Choose a different term to copy from.")
    source = list_slots(class_id, from_term_id)
    if not source:
        raise ValidationError("That term has no timetable for this class.")
    existing = {(x.weekday, x.starts_at, x.ends_at) for x in list_slots(class_id, to_term_id)}
    made = 0
    for x in source:
        if (x.weekday, x.starts_at, x.ends_at) in existing:
            continue
        save_slot(None, class_id=class_id, subject_id=x.subject_id, weekday=x.weekday, starts_at=x.starts_at,
                  ends_at=x.ends_at, room=x.room, term_id=to_term_id)
        made += 1
    return made


def weekly_minutes(class_id: int, subject_id: int, term_id: int | None = -1) -> int:
    total = 0
    for x in list_slots(class_id, term_id, subject_id):
        total += int((dt.datetime.combine(dt.date.today(), x.ends_at) - dt.datetime.combine(dt.date.today(), x.starts_at)).total_seconds() // 60)
    return total