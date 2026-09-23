# /markbook/tests/test_terms.py
"""Terms, academic years and class rollover."""
import datetime as dt

import pytest

from backend import seed
from backend.services import assessments as A
from backend.services import records as R
from backend.services import terms as T
from backend.services.analytics import Gradebook


def _sample_class(gb) -> int:
    return next(c.id for c in gb.classes.values() if c.name == seed.SAMPLE_CLASS)


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
    cls = _sample_class(gb)
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
    cls = _sample_class(gb)
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


def test_annual_result_combines_terms_by_weight(two_terms):
    from backend.services.annual import AnnualBook
    t1, t2 = two_terms
    gb = Gradebook.load(t1.id)
    cls = _sample_class(gb)
    subs = gb.class_subjects(cls)
    T.set_current(t2.id)
    for sub in subs:                                   # a second term of results
        a = A.save_assessment(None, subject_id=sub.id, class_id=cls, type="Exam", name="T2 Exam",
                              date=dt.date(int(t2.year), 9, 10), max_marks=100)
        A.save_totals(a.id, {s.id: min(100.0, (gb.summary(s).overall or 50) + 10) for s in gb.students_in(cls)})

    book = AnnualBook.load(t1.year, cls)
    assert [t.id for t in book.terms] == [t1.id, t2.id] and len(book.ranked) == len(gb.students_in(cls))
    top = book.ranked[0]
    assert top.rank == 1 and top.terms_sat == 2

    sub = book.subjects()[0]
    got = top.subjects[sub.id]
    first, second = got.per_term[t1.id], got.per_term[t2.id]
    assert abs(got.final - (first * t1.weight + second * t2.weight) / (t1.weight + t2.weight)) < 1e-6
    assert got.final > first                            # term 2 counts double and is the better term

    assert book.scale.letter(top.overall)
    pos, of = book.positions(sub.id)
    assert of == len(book.ranked) and pos[top.student.id] >= 1
    assert "weight" in book.weights_note()

    # a student who sat only one term still gets a year mark, from that term alone
    only_one = book.rows[0]
    assert all(s.terms_sat in (1, 2) for s in only_one.subjects.values())


def test_annual_outputs(two_terms, tmp_path):
    from backend.services import exports, reports
    from backend.services.annual import AnnualBook
    t1, _ = two_terms
    cls = _sample_class(Gradebook.load(t1.id))
    book = AnnualBook.load(t1.year, cls)
    if not book.ranked:
        pytest.skip("no annual results in this run")
    pdf = reports.annual_results_sheet(book, tmp_path / "annual.pdf")
    cards = reports.annual_report_cards(book, Gradebook.load(None), reports.annual_order(book)[:2], tmp_path / "cards.pdf")
    assert pdf.stat().st_size > 5000 and cards.stat().st_size > 10000
    sheets = exports.annual_sheets(book)
    assert sheets[0].name.startswith("Year") and len(sheets) == 1 + len(book.subjects())
    assert [h for h in sheets[1].head if "Term" in h]           # a column per term
    exports.write_xlsx(tmp_path / "annual.xlsx", sheets)