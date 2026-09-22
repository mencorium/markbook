# /markbook/frontend/pages/students.py
"""Class list: add students (with phone), bulk add, search, open a profile."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QLineEdit, QPushButton

from backend.phone import display_phone
from backend.services import records as R
from backend.services.analytics import TREND_WORDS

from ..dialogs import BulkStudentsDialog, StudentDialog
from ..widgets import Page, Table, fill_combo, fmt, info, label, panel, row, safe


class StudentsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Students")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        add, bulk = QPushButton("Add student"), QPushButton("Add many")
        add.setObjectName("primary")
        add.clicked.connect(lambda _=False: self.add())
        bulk.clicked.connect(lambda _=False: self.bulk())
        for w in (label("Class"), self.cls, bulk, add):
            self.actions.addWidget(w)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, reg. no. or phone")
        self.search.textChanged.connect(lambda _: self.refresh())
        self.table = Table(["Name", "Reg. no.", "Phone", "Class", "Average", "Grade", "Division", "Attendance", "Trend"], stretch=0)
        self.table.doubleClicked.connect(lambda: app.open_student(self.table.current_id()))
        self.body.addWidget(panel(row(self.search, None), self.table, label("Double-click a student to open their profile.", "muted")))

    def _class_changed(self):
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def _class_names(self):
        return [n for n, _ in self.app.class_items()]

    def _current_name(self):
        return self.app.gb.class_name(self.app.class_id) if self.app.class_id else ""

    @safe
    def add(self):
        d = StudentDialog(self, self._class_names(), class_name=self._current_name())
        if d.exec():
            s = R.save_student(None, **d.values())
            self.app.class_id = s.class_id
            self.app.reload()

    @safe
    def bulk(self):
        d = BulkStudentsDialog(self, self._class_names(), self._current_name())
        if d.exec():
            n = R.bulk_add_students(d.text.toPlainText(), d.cls.currentText())
            self.app.reload()
            info(self, f"Added {n} students.")

    def refresh(self):
        gb = self.app.gb
        fill_combo(self.cls, self.app.class_items(), self.app.class_id, blank="All classes")
        q = self.search.text().strip().lower()
        studs = [s for s in gb.students_in(self.app.class_id)
                 if not q or q in s.name.lower() or q in (s.reg_no or "").lower() or q in (s.phone or "")]
        rows = []
        for s in studs:
            sm, sc = gb.summary(s), gb.scale(s.class_id)
            rows.append([s.name, s.reg_no or "", display_phone(s.phone), gb.class_name(s.class_id), fmt(sm.overall, "%"), sc.letter(sm.overall),
                         sm.div.text() if sm.div and sm.div.complete else "–", fmt(sm.att, "%"), TREND_WORDS[sm.trend] if sm.series else ""])
        self.table.set_rows(rows, [s.id for s in studs], center_from=4)
        self.subtitle.setText(f"{len(studs)} student{'s' if len(studs) != 1 else ''}")