# /markbook/tests/test_terms.py
"""Terms, academic years and class rollover."""
import datetime as dt

import pytest

from backend import seed
from backend.services import assessments as A
from backend.services import records as R
from backend.services import terms as T
from backend.services.analytics import Gradebook


def _ensure(name: str, year: str, starts: dt.date, ends: dt.date, weight: float = 1):
    """Reuse a term another test left behind (it may hold their assessments), else make it."""
    for t in T.list_terms(year):
        if t.name.lower() == name.lower():
            return t
    return T.save_term(None, name=name, year=year, starts_on=starts, ends_on=ends, weight=weight)


@pytest.fixture
def two_terms():
    seed.remove_sample()                    # start from a clean slate whatever ran before
    year = str(dt.date.today().year)
    t1 = _ensure("Term 1", year, dt.date(int(year), 1, 1), dt.date(int(year), 6, 30))
    t2 = _ensure("Term 2", year, dt.date(int(year), 7, 1), dt.date(int(year), 12, 31), weight=2)
    T.set_current(t1.id)
    seed.add_sample(seed=6)                 # the sample runs Jan–May, so it lands in Term 1
    yield t1, t2
    seed.remove_sample()


def test_each_term_has_its_own_results(two_terms):
    t1, t2 = two_terms
    gb = Gradebook.load()
    assert gb.term.id == t1.id and gb.assessments and gb.days
    cls = next(iter(gb.classes))
    stu = gb.students_in(cls)[0]
    first = gb.summary(stu).overall

    T.set_current(t2.id)                    # a new term starts empty
    a = A.save_assessment(None, subject_id=next(iter(gb.subjects)), class_id=cls, type="Test",
                          name="T2 Test 1", date=dt.date(int(t2.year), 8, 15), max_marks=50)
    assert a.term_id == t2.id               # the date decides the term
    A.save_totals(a.id, {stu.id: 20.0})

    second = Gradebook.load(t2.id)
    assert a.id in {x.id for x in second.assessments} and second.summary(stu).overall == 40.0
    assert Gradebook.load(t1.id).summary(stu).overall == first        # last term is untouched
    assert len(Gradebook.load(None).assessments) > len(Gradebook.load(t1.id).assessments)


def test_terms_cannot_overlap_or_be_deleted_while_in_use(two_terms):
    t1, _ = two_terms
    year = int(t1.year)
    with pytest.raises(R.ValidationError, match="overlap"):
        T.save_term(None, name="Clash", year=t1.year, starts_on=dt.date(year, 6, 1), ends_on=dt.date(year, 8, 1))
    with pytest.raises(R.ValidationError, match="belong to this term"):
        T.delete_term(t1.id)
    assert T.term_for_date(dt.date(year, 3, 3)).id == t1.id
    assert T.term_for_date(dt.date(year + 9, 3, 3)) is None


def test_work_without_a_term_is_placed_in_one(two_terms):
    t1, _ = two_terms
    from sqlalchemy import text

    from backend import db
    with db.engine().begin() as c:                       # as if restored from an older backup
        c.execute(text("UPDATE assessments SET term_id = NULL WHERE term_id = :t"), {"t": t1.id})
    assert not Gradebook.load(t1.id).assessments
    assert T.assign_missing() > 0
    assert Gradebook.load(t1.id).assessments             # visible again
    assert T.assign_missing() == 0                       # and nothing left to do


@pytest.mark.parametrize("name,expected", [("Form Five", "Form Six"), ("form four", "form five"),
                                           ("S3", "S4"), ("Grade 7", "Grade 8"), ("Evening group", "Evening group")])
def test_promotion_suggests_the_next_class(name, expected):
    assert T.next_class_name(name) == expected


def test_rollover_rules(two_terms):
    gb = Gradebook.load()
    cls = next(iter(gb.classes))
    before = gb.summary(gb.students_in(cls)[0]).overall
    students = [s.id for s in gb.students_in(cls)]

    nxt = dt.date.today().year + 1
    res = T.start_term(name="Term 1", year=str(nxt), starts_on=dt.date(nxt, 1, 10), ends_on=dt.date(nxt, 6, 30),
                       plan=[{"class_id": cls, "action": "promote", "target": "Form Six (sample)"}])
    assert res["moved"] == len(students) and res["promoted"] == 1
    new = Gradebook.load()
    assert new.term.year == str(nxt) and not new.assessments                 # a fresh term
    assert new.class_name(new.students[students[0]].class_id) == "Form Six (sample)"
    assert Gradebook.load(two_terms[0].id).summary(Gradebook.load(two_terms[0].id).students[students[0]]).overall == before

    finished = T.start_term(name="Short course", year=str(nxt), starts_on=dt.date(nxt, 7, 1), ends_on=dt.date(nxt, 9, 30),
                            plan=[{"class_id": new.students[students[0]].class_id, "action": "group"}])
    assert finished["archived"] == len(students)
    after = Gradebook.load().students
    assert not any(sid in after for sid in students)                        # the group is done
    R.restore_students(students)