# /markbook/frontend/pages/subjects.py
"""Subjects: add, edit (name, code, subsidiary), delete."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QCheckBox, QMenu, QPushButton

from backend.services import records as R
from backend.services.analytics import avg

from ..dialogs import SubjectDialog
from ..widgets import Page, Table, confirm, error, fmt, info, label, panel, safe


class SubjectsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Subjects", "Subsidiary subjects (e.g. General Studies, BAM) are graded but not counted in the A-Level division.")
        add = QPushButton("Add subject")
        self.b_del = QPushButton("Archive")
        self.b_restore = QPushButton("Restore")
        self.b_restore.clicked.connect(lambda _=False: self.restore_selected())
        self.b_restore.setVisible(False)
        self.show_archived = QCheckBox("Show archived")
        self.show_archived.toggled.connect(lambda _: self.refresh())
        add.setObjectName("primary")
        self.b_del.setObjectName("danger")
        self.b_del.setEnabled(False)
        add.clicked.connect(lambda _=False: self.add())
        self.b_del.clicked.connect(lambda _=False: self.remove_selected())
        for wdg in (self.show_archived, self.b_restore, self.b_del, add):
            self.actions.addWidget(wdg)
        self.table = Table(["Subject", "Code", "Kind", "Assessments", "Average"], stretch=0, multi=True)
        self.table.doubleClicked.connect(lambda: self.edit(self.table.current_id()))
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.installEventFilter(self)
        self.hint = label("", "muted", wrap=True)
        self.body.addWidget(panel(self.table, self.hint))
        self.body.addStretch(1)

    def eventFilter(self, obj, event):
        """Delete key removes the selected subjects."""
        if obj is self.table and event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_selected()
            return True
        return super().eventFilter(obj, event)

    def archived_mode(self) -> bool:
        return self.show_archived.isChecked()

    def _selection_changed(self):
        n = len(self.table.selected_ids())
        self.b_del.setEnabled(bool(n))
        self.b_restore.setEnabled(bool(n))
        word = "Delete permanently" if self.archived_mode() else "Archive"
        self.b_del.setText(word if n < 2 else f"{word} ({n})")
        self.b_restore.setText("Restore" if n < 2 else f"Restore {n} subjects")

    def _menu(self, pos):
        ids = self.table.selected_ids()
        if not ids:
            return
        m = QMenu(self)
        one, archived = len(ids) == 1, self.archived_mode()
        act_edit = m.addAction("Edit details") if one and not archived else None
        act_restore = m.addAction("Restore" if one else f"Restore {len(ids)} subjects") if archived else None
        word = "Delete permanently" if archived else "Archive"
        act_del = m.addAction(word if one else f"{word} ({len(ids)})")
        chosen = m.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_edit:
            self.edit(ids[0])
        elif chosen is act_restore:
            self.restore_selected()
        elif chosen is act_del:
            self.remove_selected()

    def refresh(self):
        gb = self.app.gb
        archived = self.archived_mode()
        self.b_restore.setVisible(archived)
        if archived:
            subs = R.list_subjects(archived=True)
            self.table.set_headers(["Subject", "Code", "Kind", "Archived"], stretch=0)
            rows = [[s.name, s.code, "Subsidiary" if s.subsidiary else "Principal",
                     f"{s.archived_at:%d %b %Y}" if s.archived_at else ""] for s in subs]
            self._assessments = {s.id: len(gb.assessments_for(subject_id=s.id)) for s in subs}
            self.hint.setText("Archived subjects keep their assessments and marks, but are left out of results, report cards and exports. "
                              "Select rows to restore them, or to delete them for good.")
        else:
            subs = sorted(gb.subjects.values(), key=lambda s: s.name.lower())
            self.table.set_headers(["Subject", "Code", "Kind", "Assessments", "Average"], stretch=0)
            rows = []
            for s in subs:
                as_ = gb.assessments_for(subject_id=s.id)
                rows.append([s.name, s.code, "Subsidiary" if s.subsidiary else "Principal", len(as_),
                             fmt(avg(gb.assess_stats(a).mean for a in as_), "%")])
            self._assessments = {}
            self.hint.setText("Double-click a subject to edit it. Select rows (Ctrl or Shift to pick several, Ctrl+A for all) "
                              "and press Delete to archive, or right-click for more.")
        self._name_of = {s.id: s.name for s in subs}
        self.table.set_rows(rows, [s.id for s in subs], fit_height=True)
        self._selection_changed()
        n_arch = len(R.list_subjects(archived=True))
        self.subtitle.setText(("Archived subjects are hidden from results until restored." if archived else
                               "Subsidiary subjects (e.g. General Studies, BAM) are graded but not counted in the A-Level division.")
                              + (f"  ·  {n_arch} archived" if n_arch and not archived else ""))

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

    def _names(self, ids: list[int]) -> str:
        names = [self._name_of.get(i, "?") for i in ids]
        return ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")

    @safe
    def remove_selected(self):
        ids = self.table.selected_ids()
        if not ids:
            return error(self, "Select one or more subjects first.")
        if self.archived_mode():
            n = sum(self._assessments.get(i, 0) for i in ids)
            tail = (f"\n\nThis also deletes {n} assessment{'s' if n != 1 else ''} and every mark recorded in "
                    + ("them." if n != 1 else "it.")) if n else ""
            if confirm(self, f"Delete {self._names(ids)} for good?{tail}\n\nThis cannot be undone."):
                subjects, assessments = R.delete_subjects(ids)
                self.app.reload()
                info(self, f"Deleted {subjects} subject{'s' if subjects != 1 else ''}"
                           + (f" and {assessments} assessment{'s' if assessments != 1 else ''}." if assessments else "."))
        else:
            n = sum(len(self.app.gb.assessments_for(subject_id=i)) for i in ids)
            if confirm(self, f"Archive {self._names(ids)}?\n\n"
                             + (f"Its {n} assessment{'s' if n != 1 else ''} and all their marks are kept but hidden from results, "
                                if n else "Nothing is deleted, ")
                             + "report cards and exports. Tick 'Show archived' to restore them later."):
                subjects, assessments = R.archive_subjects(ids)
                self.app.reload()
                info(self, f"Archived {subjects} subject{'s' if subjects != 1 else ''}"
                           + (f", hiding {assessments} assessment{'s' if assessments != 1 else ''}." if assessments else "."))

    @safe
    def restore_selected(self):
        ids = self.table.selected_ids()
        if not ids:
            return error(self, "Select one or more subjects first.")
        n = R.restore_subjects(ids)
        self.app.reload()
        info(self, f"Restored {n} subject{'s' if n != 1 else ''}.")