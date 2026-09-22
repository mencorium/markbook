# /markbook/frontend/pages/students.py
"""Class list: add students (with phone), bulk add, search, open a profile."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QMenu, QPushButton

from backend.phone import display_phone
from backend.services import records as R
from backend.services.analytics import TREND_WORDS

from ..dialogs import BulkStudentsDialog, ClassDialog, StudentDialog
from ..widgets import Page, Table, confirm, error, fill_combo, fmt, info, label, panel, row, safe


class StudentsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Students")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        add, bulk = QPushButton("Add student"), QPushButton("Add many")
        self.b_del = QPushButton("Archive")
        add.setObjectName("primary")
        self.b_del.setObjectName("danger")
        self.b_del.setEnabled(False)
        add.clicked.connect(lambda _=False: self.add())
        bulk.clicked.connect(lambda _=False: self.bulk())
        self.b_del.clicked.connect(lambda _=False: self.delete_selected())
        new_class = QPushButton("Add class")
        new_class.clicked.connect(lambda _=False: self.add_class())
        self.b_restore = QPushButton("Restore")
        self.b_restore.clicked.connect(lambda _=False: self.restore_selected())
        self.b_restore.setVisible(False)
        self.show_archived = QCheckBox("Show archived")
        self.show_archived.toggled.connect(lambda _: self.refresh())
        for w in (label("Class"), self.cls, new_class, self.show_archived, self.b_restore, self.b_del, bulk, add):
            self.actions.addWidget(w)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, reg. no. or phone")
        self.search.textChanged.connect(lambda _: self.refresh())
        self.table = Table(["Name", "Reg. no.", "Phone", "Class", "Average", "Grade", "Division", "Attendance", "Trend"], stretch=0, multi=True)
        self.table.doubleClicked.connect(lambda: app.open_student(self.table.current_id()))
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.hint = label("", "muted", wrap=True)
        self.body.addWidget(panel(row(self.search, None), self.table, self.hint))
        self.table.installEventFilter(self)

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
    def add_class(self):
        d = ClassDialog(self, [n for n, _ in self.app.class_items()])
        if d.exec():
            v = d.values()
            cls = R.get_or_create_class(v["name"])
            R.save_class(cls.id, name=v["name"], level=v["level"], pass_mark=v["pass_mark"], teacher=v["teacher"], scale=None)
            self.app.class_id = cls.id
            self.app.reload()

    @safe
    def bulk(self):
        d = BulkStudentsDialog(self, self._class_names(), self._current_name())
        if d.exec():
            n = R.bulk_add_students(d.text.toPlainText(), d.cls.currentText())
            self.app.reload()
            info(self, f"Added {n} students.")

    def eventFilter(self, obj, event):
        """Delete key removes the selected students."""
        from PyQt6.QtCore import QEvent
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
        self.b_restore.setText("Restore" if n < 2 else f"Restore {n} students")

    def _menu(self, pos):
        ids = self.table.selected_ids()
        if not ids:
            return
        m = QMenu(self)
        one, archived = len(ids) == 1, self.archived_mode()
        act_open = m.addAction("Open profile") if one and not archived else None
        act_edit = m.addAction("Edit details") if one and not archived else None
        act_restore = m.addAction("Restore" if one else f"Restore {len(ids)} students") if archived else None
        word = "Delete permanently" if archived else "Archive"
        act_del = m.addAction(word if one else f"{word} ({len(ids)})")
        chosen = m.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_open:
            self.app.open_student(ids[0])
        elif chosen is act_edit:
            self.edit(ids[0])
        elif chosen is act_restore:
            self.restore_selected()
        elif chosen is act_del:
            self.remove_selected()

    @safe
    def edit(self, student_id: int):
        stu = self.app.gb.students[student_id]
        d = StudentDialog(self, self._class_names(), stu, self.app.gb.class_name(stu.class_id))
        if d.exec():
            R.save_student(stu.id, **d.values())
            self.app.reload()

    def _names(self, ids: list[int]) -> str:
        names = [self._name_of.get(i, "?") for i in ids]
        return ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")

    @safe
    def remove_selected(self):
        ids = self.table.selected_ids()
        if not ids:
            return error(self, "Select one or more students first.")
        if self.archived_mode():
            if confirm(self, f"Delete {self._names(ids)} for good?\n\nEvery mark and attendance record for "
                             f"{'this student' if len(ids) == 1 else 'these students'} is deleted with them.\n\nThis cannot be undone."):
                n = R.delete_students(ids)
                self.app.reload()
                info(self, f"Deleted {n} student{'s' if n != 1 else ''} for good.")
        elif confirm(self, f"Archive {self._names(ids)}?\n\nThey leave the class list, results and exports, but their marks "
                           "and attendance are kept. Tick 'Show archived' to restore them later."):
            n = R.archive_students(ids)
            self.app.reload()
            info(self, f"Archived {n} student{'s' if n != 1 else ''}.")

    @safe
    def restore_selected(self):
        ids = self.table.selected_ids()
        if not ids:
            return error(self, "Select one or more students first.")
        n = R.restore_students(ids)
        self.app.reload()
        info(self, f"Restored {n} student{'s' if n != 1 else ''} to their class.")

    def refresh(self):
        gb = self.app.gb
        fill_combo(self.cls, self.app.class_items(), self.app.class_id, blank="All classes")
        q = self.search.text().strip().lower()
        archived = self.archived_mode()
        self.b_restore.setVisible(archived)
        matches = lambda s: not q or q in s.name.lower() or q in (s.reg_no or "").lower() or q in (s.phone or "")
        if archived:
            studs = [s for s in R.list_students(self.app.class_id, archived=True) if matches(s)]
            self.table.set_headers(["Name", "Reg. no.", "Phone", "Class", "Archived"], stretch=0)
            rows = [[s.name, s.reg_no or "", display_phone(s.phone), gb.class_name(s.class_id),
                     f"{s.archived_at:%d %b %Y}" if s.archived_at else ""] for s in studs]
            self.hint.setText("Archived students keep their marks but take no part in results, positions or exports. "
                              "Select rows to restore them, or to delete them for good.")
        else:
            studs = [s for s in gb.students_in(self.app.class_id) if matches(s)]
            self.table.set_headers(["Name", "Reg. no.", "Phone", "Class", "Average", "Grade", "Division", "Attendance", "Trend"], stretch=0)
            rows = []
            for s in studs:
                sm, sc = gb.summary(s), gb.scale(s.class_id)
                rows.append([s.name, s.reg_no or "", display_phone(s.phone), gb.class_name(s.class_id), fmt(sm.overall, "%"), sc.letter(sm.overall),
                             sm.div.text() if sm.div and sm.div.complete else "–", fmt(sm.att, "%"), TREND_WORDS[sm.trend] if sm.series else ""])
            self.hint.setText("Double-click a student to open their profile. Select rows (Ctrl or Shift to pick several, Ctrl+A for all) "
                              "and press Delete to archive, or right-click for more.")
        self._name_of = {s.id: s.name for s in studs}
        self.table.set_rows(rows, [s.id for s in studs], center_from=4)
        self._selection_changed()
        n_arch = len(R.list_students(archived=True))
        self.subtitle.setText(f"{len(studs)} {'archived ' if archived else ''}student{'s' if len(studs) != 1 else ''}"
                              + (f" · {n_arch} archived" if n_arch and not archived else ""))