# /markbook/tests/test_gui_smoke.py
"""Opens every screen offscreen with sample data, edits a per-question mark and saves it."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


def test_every_page_opens(monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"warning shown: {a[2]}"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    app = QApplication.instance() or QApplication([])
    from backend import seed
    from frontend.main_window import NAV, MainWindow

    seed.add_sample(seed=11)
    w = MainWindow()
    for key, _ in NAV:
        w.show_page(key)
        app.processEvents()
    stu = w.gb.students_in(w.ensure_class())[0]
    w.open_student(stu.id)
    exam = next(a for a in w.gb.assessments if a.is_paper)
    w.open_assessment(exam.id)
    page = w.pages["entry"]
    for i in range(3):
        page.tabs.setCurrentIndex(i)
        app.processEvents()
    sid = page.grid.item(0, 0).data(Qt.ItemDataRole.UserRole)
    new = 3 if page.grid.item(0, 1).text() != "3" else 4       # must differ from the seeded value
    page.grid.item(0, 1).setText(str(new))
    assert page.dirty
    page.save_marks()
    assert w.gb.qmarks[exam.id][sid][exam.questions[0].id] == new

    # delete students from the class list: one selected row, then several
    w.show_page("students")
    students = w.pages["students"]
    table = students.table
    before = table.rowCount()
    assert not students.b_del.isEnabled()                       # nothing selected yet
    table.selectRow(0)
    assert students.b_del.isEnabled() and students.b_del.text() == "Delete"
    students.delete_selected()
    assert table.rowCount() == before - 1

    sel = table.selectionModel()
    for r in (0, 1, 2):
        sel.select(table.model().index(r, 0), sel.SelectionFlag.Select | sel.SelectionFlag.Rows)
    assert students.b_del.text() == "Delete 3 students"
    gone = set(table.selected_ids())
    students.delete_selected()
    assert table.rowCount() == before - 4
    assert not gone & set(w.gb.students)
    assert not any(sid in gone for marks in w.gb.totals.values() for sid in marks)

    # delete subjects the same way, taking their assessments with them
    w.show_page("subjects")
    subjects = w.pages["subjects"]
    stable = subjects.table
    assert not subjects.b_del.isEnabled()
    sel = stable.selectionModel()
    for r in (0, 1):
        sel.select(stable.model().index(r, 0), sel.SelectionFlag.Select | sel.SelectionFlag.Rows)
    assert subjects.b_del.text() == "Delete 2 subjects"
    dropped = set(stable.selected_ids())
    rows, assessments = stable.rowCount(), len(w.gb.assessments)
    subjects.delete_selected()
    assert stable.rowCount() == rows - 2
    assert not dropped & set(w.gb.subjects)
    assert len(w.gb.assessments) < assessments

    seed.remove_sample()