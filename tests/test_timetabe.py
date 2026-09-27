# /markbook/tests/test_timetable.py
"""The weekly timetable, and attendance taken against its sessions."""
import datetime as dt

import pytest

from backend import seed
from backend.services import attendance as ATT
from backend.services import records as R
from backend.services import terms as T
from backend.services import timetable as TT
from backend.services.analytics import Gradebook


@pytest.fixture
def klass():
    seed.remove_sample()
    year = str(dt.date.today().year)
    term = next((t for t in T.list_terms(year) if t.name == "Term 1"), None) or \
        T.save_term(None, name="Term 1", year=year, starts_on=dt.date(int(year), 1, 1), ends_on=dt.date(int(year), 12, 31))
    T.set_current(term.id)
    seed.add_sample(seed=21)
    gb = Gradebook.load()
    cid = next(c.id for c in gb.classes.values() if c.name == seed.SAMPLE_CLASS)
    yield cid, gb.class_subjects(cid), term
    seed.remove_sample()


def _monday(term) -> dt.date:
    d = max(term.starts_on, dt.date(term.starts_on.year, 3, 1))
    while d.weekday() != 0:
        d += dt.timedelta(days=1)
    return d


def test_lessons_cannot_overlap_and_only_appear_on_their_weekday(klass):
    cid, subs, term = klass
    for s in TT.list_slots(cid, term.id):
        TT.delete_slot(s.id)
    TT.save_slot(None, class_id=cid, subject_id=subs[0].id, weekday=0, starts_at=dt.time(8, 0), ends_at=dt.time(9, 30), room="Lab 1")
    TT.save_slot(None, class_id=cid, subject_id=subs[1].id, weekday=0, starts_at=dt.time(10, 0), ends_at=dt.time(11, 0))

    with pytest.raises(R.ValidationError, match="already has a lesson"):
        TT.save_slot(None, class_id=cid, subject_id=subs[1].id, weekday=0, starts_at=dt.time(9, 0), ends_at=dt.time(10, 30))
    with pytest.raises(R.ValidationError, match="cannot end before"):
        TT.save_slot(None, class_id=cid, subject_id=subs[1].id, weekday=1, starts_at=dt.time(11, 0), ends_at=dt.time(10, 0))

    monday = _monday(term)
    assert [s.subject_id for s in TT.sessions_on(cid, monday, term.id)] == [subs[0].id, subs[1].id]
    assert TT.sessions_on(cid, monday + dt.timedelta(days=1), term.id) == []      # nothing on Tuesday
    assert TT.weekly_minutes(cid, subs[0].id, term.id) == 90


def test_attendance_belongs_to_a_session(klass):
    cid, subs, term = klass
    for d in ATT.list_days(cid):                                  # start with no registers at all
        ATT.delete_day(cid, d.date, d.slot_id)
    for s in TT.list_slots(cid, term.id):
        TT.delete_slot(s.id)
    first = TT.save_slot(None, class_id=cid, subject_id=subs[0].id, weekday=0, starts_at=dt.time(8, 0), ends_at=dt.time(9, 30))
    second = TT.save_slot(None, class_id=cid, subject_id=subs[1].id, weekday=0, starts_at=dt.time(10, 0), ends_at=dt.time(11, 0))
    monday = _monday(term)
    ids = [s.id for s in Gradebook.load().students_in(cid)]

    ATT.save_day(cid, monday, ids, {ids[0]}, slot_id=first.id, subject_id=first.subject_id)
    ATT.save_day(cid, monday, ids, {ids[1], ids[2]}, slot_id=second.id, subject_id=second.subject_id)

    one = ATT.get_day(cid, monday, first.id)
    two = ATT.get_day(cid, monday, second.id)
    assert one.absent == [ids[0]] and two.absent == [ids[1], ids[2]]     # two registers on one day
    assert one.id != two.id and one.subject_id == subs[0].id

    gb = Gradebook.load()
    absent_first = gb.students[ids[0]]
    assert gb.att_rate(absent_first, subject_id=first.subject_id) == 0.0
    assert gb.att_rate(absent_first, subject_id=second.subject_id) == 100.0
    assert 0 < gb.att_rate(absent_first) < 100                          # overall sits between them


def test_removing_a_lesson_keeps_its_registers(klass):
    cid, subs, term = klass
    slot = TT.save_slot(None, class_id=cid, subject_id=subs[0].id, weekday=3, starts_at=dt.time(14, 0), ends_at=dt.time(15, 0))
    day = _monday(term) + dt.timedelta(days=3)
    ids = [s.id for s in Gradebook.load().students_in(cid)]
    ATT.save_day(cid, day, ids, {ids[0]}, slot_id=slot.id, subject_id=slot.subject_id)

    assert TT.delete_slot(slot.id) == 1                                  # reports what it kept
    kept = [d for d in Gradebook.load().days if d.date == day]
    assert kept and kept[0].subject_id == subs[0].id and kept[0].slot_id is None


def test_timetable_can_be_copied_to_the_next_term(klass):
    cid, subs, term = klass
    year = str(dt.date.today().year + 5)
    later = T.save_term(None, name="Term 9", year=year, starts_on=dt.date(int(year), 1, 5), ends_on=dt.date(int(year), 6, 30))
    before = len(TT.list_slots(cid, term.id))
    assert before

    assert TT.copy_to_term(cid, term.id, later.id) == before
    assert len(TT.list_slots(cid, later.id)) == before
    assert TT.copy_to_term(cid, term.id, later.id) == 0                  # copying twice adds nothing
    with pytest.raises(R.ValidationError):
        TT.copy_to_term(cid, later.id, later.id)