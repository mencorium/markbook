# /markbook/frontend/pages/subjects.py
"""Subjects: add, edit (name, code, subsidiary), delete."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QMenu, QPushButton

from backend.services import records as R
from backend.services.analytics import avg

from ..dialogs import SubjectDialog
from ..widgets import Page, Table, confirm, error, fmt, info, label, panel, safe


class SubjectsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Subjects", "Subsidiary subjects (e.g. General Studies, BAM) are graded but not counted in the A-Level division.")
        add = QPushButton("Add subject")
        self.b_del = QPushButton("Delete")
        add.setObjectName("primary")
        self.b_del.setObjectName("danger")
        self.b_del.setEnabled(False)
        add.clicked.connect(lambda _=False: self.add())
        self.b_del.clicked.connect(lambda _=False: self.delete_selected())
        self.actions.addWidget(self.b_del)
        self.actions.addWidget(add)
        self.table = Table(["Subject", "Code", "Kind", "Assessments", "Average"], stretch=0, multi=True)
        self.table.doubleClicked.connect(lambda: self.edit(self.table.current_id()))
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.installEventFilter(self)
        self.body.addWidget(panel(self.table, label("Double-click a subject to edit it. Select rows (Ctrl or Shift to pick several, Ctrl+A for all) "
                                                    "and press Delete, or right-click for more.", "muted", wrap=True)))
        self.body.addStretch(1)

    def eventFilter(self, obj, event):
        """Delete key removes the selected subjects."""
        if obj is self.table and event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            return True
        return super().eventFilter(obj, event)

    def _selection_changed(self):
        n = len(self.table.selected_ids())
        self.b_del.setEnabled(bool(n))
        self.b_del.setText("Delete" if n < 2 else f"Delete {n} subjects")

    def _menu(self, pos):
        ids = self.table.selected_ids()
        if not ids:
            return
        m = QMenu(self)
        act_edit = m.addAction("Edit details") if len(ids) == 1 else None
        act_del = m.addAction("Delete" if len(ids) == 1 else f"Delete {len(ids)} subjects")
        chosen = m.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_edit:
            self.edit(ids[0])
        elif chosen is act_del:
            self.delete_selected()

    def refresh(self):
        gb = self.app.gb
        subs = sorted(gb.subjects.values(), key=lambda s: s.name.lower())
        rows = []
        for s in subs:
            as_ = gb.assessments_for(subject_id=s.id)
            rows.append([s.name, s.code, "Subsidiary" if s.subsidiary else "Principal", len(as_), fmt(avg(gb.assess_stats(a).mean for a in as_), "%")])
        self.table.set_rows(rows, [s.id for s in subs], fit_height=True)
        self._selection_changed()

    @safe
    def add(self):
        d = SubjectDialog(self)
        if d.exec():
            R.save_subject(None, **d.values())
            self.app.reload()

    @safe
    def edit(self, sid=None):
        sid = sid if sid is not None else self.table.current_id()
        if sid is None:
            return
        d = SubjectDialog(self, self.app.gb.subjects[sid])
        if d.exec():
            R.save_subject(sid, **d.values())
            self.app.reload()

    @safe
    def delete_selected(self):
        gb = self.app.gb
        ids = self.table.selected_ids()
        if not ids:
            return error(self, "Select one or more subjects first.")
        names = [gb.subject_name(i) for i in ids]
        n = sum(len(gb.assessments_for(subject_id=i)) for i in ids)
        what = f"{names[0]}" if len(ids) == 1 else f"these {len(ids)} subjects?\n\n" + ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
        tail = (f"\n\nThis also deletes {n} assessment{'s' if n != 1 else ''} and every mark recorded in "
                + ("them." if n != 1 else "it.")) if n else ""
        if confirm(self, f"Delete {what}{'?' if len(ids) == 1 else ''}{tail}\n\nThis cannot be undone."):
            subjects, assessments = R.delete_subjects(ids)
            self.app.reload()
            info(self, f"Deleted {subjects} subject{'s' if subjects != 1 else ''}"
                       + (f" and {assessments} assessment{'s' if assessments != 1 else ''}." if assessments else "."))