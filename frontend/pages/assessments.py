# /markbook/frontend/pages/assessments.py
"""Tests and exams: create an assessment, open it to enter marks."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QPushButton

from backend.services import assessments as A

from ..dialogs import AssessmentDialog
from ..widgets import Page, Table, error, fill_combo, fmt, label, panel, safe


class AssessmentsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Tests & exams", "Create an assessment, then enter each student's marks. Tick 'Mark per question' to analyse topics.")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        new = QPushButton("New assessment")
        new.setObjectName("primary")
        new.clicked.connect(lambda _=False: self.new())
        for w in (label("Class"), self.cls, new):
            self.actions.addWidget(w)
        self.table = Table(["Date", "Assessment", "Subject", "Class", "Type", "Topics", "Marked", "Mean"], stretch=5)
        self.table.doubleClicked.connect(lambda: app.open_assessment(self.table.current_id()))
        self.body.addWidget(panel(self.table, label("Double-click an assessment to enter marks, set up its question paper or see its analysis.", "muted")))

    def _class_changed(self):
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def refresh(self):
        gb = self.app.gb
        fill_combo(self.cls, self.app.class_items(), self.app.class_id, blank="All classes")
        as_ = gb.assessments_for(self.app.class_id)[::-1]
        rows = []
        for a in as_:
            st = gb.assess_stats(a)
            topics = (f"{len(a.questions)} questions · " if a.is_paper else "") + ", ".join(a.topics)
            rows.append([a.date.isoformat(), a.name, gb.subject_name(a.subject_id), gb.class_name(a.class_id), a.type, topics,
                         f"{st.n}/{len(gb.students_in(a.class_id))}", fmt(st.mean, "%")])
        self.table.set_rows(rows, [a.id for a in as_], center_from=4)

    @safe
    def new(self):
        gb = self.app.gb
        if not gb.subjects or not gb.classes:
            return error(self, "Add at least one subject and one student (which creates the class) first.")
        d = AssessmentDialog(self, sorted(gb.subjects.values(), key=lambda s: s.name), sorted(gb.classes.values(), key=lambda c: c.name),
                             class_id=self.app.class_id)
        if d.exec():
            v = d.values()
            paper = v.pop("paper")
            a = A.save_assessment(None, **v)
            self.app.gb = gb.load()
            self.app.open_assessment(a.id, "paper" if paper else "marks")