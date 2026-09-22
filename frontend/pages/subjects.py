# /markbook/frontend/pages/subjects.py
"""Subjects: add, edit (name, code, subsidiary), delete."""
from __future__ import annotations

from PyQt6.QtWidgets import QPushButton

from backend.services import records as R
from backend.services.analytics import avg

from ..dialogs import SubjectDialog
from ..widgets import Page, Table, confirm, fmt, label, panel, row, safe


class SubjectsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Subjects", "Subsidiary subjects (e.g. General Studies, BAM) are graded but not counted in the A-Level division.")
        add, edit, delete = QPushButton("Add subject"), QPushButton("Edit"), QPushButton("Delete")
        add.setObjectName("primary")
        delete.setObjectName("danger")
        add.clicked.connect(lambda _=False: self.add())
        edit.clicked.connect(lambda _=False: self.edit())
        delete.clicked.connect(lambda _=False: self.delete())
        self.actions.addWidget(add)
        self.table = Table(["Subject", "Code", "Kind", "Assessments", "Average"], stretch=0)
        self.table.doubleClicked.connect(lambda: self.edit())
        self.body.addWidget(panel(self.table, row(edit, delete, None), label("Double-click a subject to edit it.", "muted")))
        self.body.addStretch(1)

    def refresh(self):
        gb = self.app.gb
        subs = sorted(gb.subjects.values(), key=lambda s: s.name.lower())
        rows = []
        for s in subs:
            as_ = gb.assessments_for(subject_id=s.id)
            rows.append([s.name, s.code, "Subsidiary" if s.subsidiary else "Principal", len(as_), fmt(avg(gb.assess_stats(a).mean for a in as_), "%")])
        self.table.set_rows(rows, [s.id for s in subs], fit_height=True)

    @safe
    def add(self):
        d = SubjectDialog(self)
        if d.exec():
            R.save_subject(None, **d.values())
            self.app.reload()

    @safe
    def edit(self):
        sid = self.table.current_id()
        if sid is None:
            return
        d = SubjectDialog(self, self.app.gb.subjects[sid])
        if d.exec():
            R.save_subject(sid, **d.values())
            self.app.reload()

    @safe
    def delete(self):
        sid = self.table.current_id()
        if sid is None:
            return
        n = len(self.app.gb.assessments_for(subject_id=sid))
        if confirm(self, f"Delete {self.app.gb.subject_name(sid)}" + (f" and its {n} assessments with all marks" if n else "") + "? This cannot be undone."):
            R.delete_subject(sid)
            self.app.reload()