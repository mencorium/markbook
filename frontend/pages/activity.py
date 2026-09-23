# /markbook/frontend/pages/activity.py
"""Who changed what, and when. Marks get questioned weeks later, so every change is kept here."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QLineEdit

from backend import audit
from backend.services import records as R

from ..widgets import Page, Table, fill_combo, label, panel, row

WORDS = {
    "mark.added": "Mark entered", "mark.changed": "Mark changed", "mark.removed": "Mark removed",
    "student.archived": "Student archived", "student.restored": "Student restored", "student.deleted": "Student deleted",
    "subject.archived": "Subject archived", "subject.restored": "Subject restored", "subject.deleted": "Subject deleted",
    "assessment.deleted": "Assessment deleted", "marks.imported": "Marks imported", "database.restored": "Backup restored",
}
FILTERS = [("Everything", None), ("Marks only", "mark."), ("Students", "student."), ("Subjects", "subject.")]


class ActivityPage(Page):
    def __init__(self, app):
        super().__init__(app, "Activity", "Every change to a mark, and every archive, restore or deletion")
        self.kind = QComboBox()
        fill_combo(self.kind, FILTERS)
        self.kind.currentIndexChanged.connect(lambda _: self.refresh())
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search student, assessment or person")
        self.search.textChanged.connect(lambda _: self.refresh())
        for w in (label("Show"), self.kind):
            self.actions.addWidget(w)
        self.table = Table(["When", "Who", "What", "Student", "Details"], stretch=4)
        self.table.doubleClicked.connect(self._open)
        self.body.addWidget(panel(row(self.search, None), self.table,
                                  label("Double-click a row to open the student. History is kept even after a student, subject or "
                                        "assessment is deleted, so an old mark can always be accounted for.", "muted", wrap=True)))

    def _open(self):
        sid = self.table.current_id()
        if sid and sid in self.app.gb.students:
            self.app.open_student(sid)

    def refresh(self):
        names = {s.id: s.name for s in R.list_students()} | {s.id: f"{s.name} (archived)" for s in R.list_students(archived=True)}
        entries = audit.recent(500, action_prefix=self.kind.currentData())
        q = self.search.text().strip().lower()
        rows, ids = [], []
        for e in entries:
            who_for = names.get(e.student_id, "(deleted student)" if e.student_id else "")
            change = ("absent" if e.old_value is None else e.old_value) + " → " + ("absent" if e.new_value is None else e.new_value) \
                if e.entity == "mark" else ""
            detail = " · ".join(x for x in (e.detail, change) if x)
            text = " ".join([e.who, WORDS.get(e.action, e.action), who_for, detail]).lower()
            if q and q not in text:
                continue
            rows.append([f"{e.at:%d %b %Y, %H:%M}", e.who, WORDS.get(e.action, e.action), who_for, detail])
            ids.append(e.student_id)
        self.table.set_rows(rows, ids, center_from=5, fit_height=True)
        shown = f"{len(rows)} of {len(entries)}" if q else str(len(rows))
        self.subtitle.setText(f"{shown} change{'s' if len(rows) != 1 else ''}, most recent first. "
                              f"Changes are recorded as “{audit.current_user()}” — set the name in Settings.")