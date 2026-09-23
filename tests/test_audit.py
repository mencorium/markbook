# /markbook/tests/test_audit.py
"""The change history, and refusing to overwrite marks changed elsewhere."""
import datetime as dt

import pytest

from backend import audit, seed
from backend.services import assessments as A
from backend.services import records as R
from backend.services.analytics import Gradebook


@pytest.fixture
def sample():
    seed.add_sample(seed=8)
    R.save_settings({"user_name": "Joel"})
    audit.forget_user()
    yield Gradebook.load()
    seed.remove_sample()
    R.save_settings({"user_name": ""})
    audit.forget_user()


def _assessment(gb):
    a = next(x for x in gb.assessments if not x.is_paper and gb.totals.get(x.id))
    return a, next(iter(gb.totals[a.id]))


def test_every_mark_change_is_recorded_with_who_and_what(sample):
    a, sid = _assessment(sample)
    was = sample.totals[a.id][sid]

    A.save_totals(a.id, {sid: 41.0}, expected={sid: was})
    entry = audit.recent(1, student_id=sid)[0]
    assert entry.action == "mark.changed" and entry.who == "Joel"
    assert entry.old_value == f"{was:g}" and entry.new_value == "41"
    assert entry.assessment_id == a.id and isinstance(entry.at, dt.datetime)

    A.save_totals(a.id, {sid: None}, expected={sid: 41.0})            # marked absent
    assert audit.recent(1, student_id=sid)[0].action == "mark.removed"
    A.save_totals(a.id, {sid: 33.0}, expected={sid: None})
    assert audit.recent(1, student_id=sid)[0].action == "mark.added"
    assert len(audit.recent(50, action_prefix="mark.", student_id=sid)) == 3


def test_saving_stale_marks_is_refused_and_writes_nothing(sample):
    a, sid = _assessment(sample)
    was = sample.totals[a.id][sid]
    A.save_totals(a.id, {sid: 30.0})                                   # another window saves first
    before = len(audit.recent(200))

    with pytest.raises(R.ConflictError) as e:
        A.save_totals(a.id, {sid: 44.0}, expected={sid: was})          # we still think it is the old value
    assert "changed elsewhere" in str(e.value) and f"{was:g}" in str(e.value)
    assert Gradebook.load().totals[a.id][sid] == 30.0                  # the other person's mark stands
    assert len(audit.recent(200)) == before                            # and nothing was logged

    A.save_totals(a.id, {sid: 44.0}, expected={sid: 30.0})             # saving against what is really there works
    assert Gradebook.load().totals[a.id][sid] == 44.0


def test_per_question_marks_are_checked_and_audited_by_total(sample):
    gb = sample
    a = next(x for x in gb.assessments if x.is_paper)
    sid = next(iter(gb.qmarks[a.id]))
    row = dict(gb.qmarks[a.id][sid])
    first = a.questions[0]
    row[first.id] = (row.get(first.id) or 0) + 1 if (row.get(first.id) or 0) < first.max else first.max - 1

    A.save_question_marks(a.id, {sid: row}, expected={sid: gb.totals[a.id][sid]})
    entry = audit.recent(1, student_id=sid)[0]
    assert entry.action == "mark.changed" and "per question" in entry.detail

    with pytest.raises(R.ConflictError):
        A.save_question_marks(a.id, {sid: row}, expected={sid: -1})    # a total nobody ever had


def test_history_outlives_the_student_and_covers_removals(sample):
    gb = sample
    stu = gb.students_in(next(iter(gb.classes)))[0]
    R.archive_students([stu.id])
    R.restore_students([stu.id])
    subj = next(iter(gb.subjects))
    R.archive_subjects([subj])
    R.restore_subjects([subj])
    actions = [e.action for e in audit.recent(20)]
    assert {"student.archived", "student.restored", "subject.archived", "subject.restored"} <= set(actions)

    R.delete_students([stu.id])
    kept = audit.recent(20, student_id=stu.id)
    assert kept and kept[0].action == "student.deleted" and stu.name in kept[0].detail
    assert any(e.action.startswith("mark.") or e.action.startswith("student.") for e in kept)


def test_the_name_comes_from_settings_then_the_computer():
    R.save_settings({"user_name": "  Mr. Mwaipopo "})
    audit.forget_user()
    assert audit.current_user() == "Mr. Mwaipopo"
    R.save_settings({"user_name": ""})
    audit.forget_user()
    assert audit.current_user() == audit.machine_user()