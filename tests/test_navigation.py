# /markbook/tests/test_navigation.py
"""The subject results view and the quick student search."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")


_app = None            # a QApplication must outlive the tests, or Qt aborts


@pytest.fixture
def window(monkeypatch):
    global _app
    from PyQt6.QtWidgets import QApplication, QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"warning shown: {a[2]}"))
    _app = QApplication.instance() or QApplication([])
    from backend import seed
    from frontend.main_window import MainWindow
    seed.add_sample(seed=12)
    yield MainWindow()
    seed.remove_sample()


def test_subject_page_shows_its_assessments_and_cumulative_results(window):
    w = window
    w.show_page("subjects")
    subjects = w.pages["subjects"]
    subjects.table.selectRow(0)
    sid = subjects.table.current_id()
    subjects._open(sid)                                   # double-clicking a subject opens its results
    assert w.current == "subject"

    page = w.pages["subject"]
    gb = w.gb
    expected = gb.assessments_for(w.class_id, sid)
    assert page.title.text() == gb.subject_name(sid)
    assert page.tests.rowCount() == len(expected) and page.tests.ids == [a.id for a in expected]
    assert page.cumulative.rowCount() == len(gb.students_in(w.class_id))
    headers = [page.cumulative.horizontalHeaderItem(c).text() for c in range(page.cumulative.columnCount())]
    assert all(any(a.name in h for h in headers) for a in expected)       # a column per assessment
    assert any("Final" in h for h in headers) and any("Position" in h for h in headers)

    page.tests.selectRow(0)                                # and an assessment opens from here
    w.open_assessment(page.tests.current_id())
    assert w.current == "entry" and w.pages["entry"].a.subject_id == sid


def test_subject_page_follows_the_chosen_subject(window):
    w = window
    gb = w.gb
    subs = gb.class_subjects(w.ensure_class())
    w.open_subject(subs[-1].id)
    page = w.pages["subject"]
    assert page.title.text() == subs[-1].name
    page.subj.setCurrentIndex(page.subj.findData(subs[0].id))
    assert w.subject_id == subs[0].id and page.title.text() == subs[0].name


def test_quick_find_matches_name_reg_and_phone(window):
    from frontend.quick_find import QuickFind
    w = window
    stu = next(s for s in w.gb.students.values() if s.reg_no and s.phone)
    first, last = stu.name.split()[0], stu.name.split()[-1]
    q = QuickFind(w)

    def names(text):
        q.box.setText(text)
        return [q.list.item(i).text().split("   —   ")[0] for i in range(q.list.count())]

    assert stu.name in names(first)
    assert stu.name in names(f"{last[:3]} {first[:3]}")          # any order, shortened
    assert names(stu.reg_no) == [stu.name]
    assert stu.name in names("0" + stu.phone[4:8])               # typed as dialled, stored as +255…
    assert names("zzzznothing") == []

    q.box.setText(first)
    q._open()                                                     # Enter opens the student
    assert w.current == "student" and w.student_id == stu.id


def test_quick_find_puts_archived_students_last(window):
    from backend.services import records as R
    from frontend.quick_find import QuickFind
    w = window
    students = sorted(w.gb.students.values(), key=lambda s: s.name)
    archived = students[0]
    R.archive_students([archived.id])
    try:
        q = QuickFind(w)
        q.box.setText(archived.name.split()[-1][:3])
        shown = [q.list.item(i).text() for i in range(q.list.count())]
        assert any(archived.name in t and "archived" in t for t in shown)
        assert not shown[0].startswith(archived.name) or len(shown) == 1
    finally:
        R.restore_students([archived.id])


def test_back_returns_to_where_you_came_from(window):
    """The reported bug: an exam opened from a subject went 'back' to Tests & exams."""
    w = window
    gb = w.gb
    sid = gb.class_subjects(w.ensure_class())[0].id
    w.show_page("subjects")
    w.open_subject(sid)
    subject_page = w.pages["subject"]
    assert subject_page.back.text() == "← Subjects"          # how we arrived

    aid = subject_page.tests.ids[0]
    w.open_assessment(aid)
    assert w.current == "entry"
    assert w.pages["entry"].back.text() == f"← {gb.subject_name(sid)}"

    w.go_back()
    assert w.current == "subject" and w.subject_id == sid    # back to the subject, not Tests & exams

    w.go_back()
    assert w.current == "subjects"


def test_back_follows_the_other_route_too(window):
    w = window
    w.show_page("assessments")
    page = w.pages["assessments"]
    w.open_assessment(page.table.ids[0])
    assert w.pages["entry"].back.text() == "← Tests & exams"
    w.go_back()
    assert w.current == "assessments"

    stu = w.gb.students_in(w.ensure_class())[0]
    w.show_page("students")
    w.open_student(stu.id)
    assert w.pages["student"].back.text() == "← Students"
    w.go_back()
    assert w.current == "students"


def test_back_skips_a_record_that_has_gone(window):
    from backend.services import records as R
    w = window
    stu = w.gb.students_in(w.ensure_class())[0]
    w.show_page("subjects")
    w.open_student(stu.id)
    w.show_page("dashboard")

    R.delete_students([stu.id])                               # the student in the history no longer exists
    w.gb = w.gb.load(w.term_id)
    w.go_back()
    assert w.current == "subjects" and w.student_id == stu.id or w.current != "student"