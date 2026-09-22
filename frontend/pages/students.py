# /markbook/frontend/pages/students.py
"""Class list: add students (with phone), bulk add, search, open a profile."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QLineEdit, QMenu, QPushButton

from backend.phone import display_phone
from backend.services import records as R
from backend.services.analytics import TREND_WORDS

from ..dialogs import BulkStudentsDialog, StudentDialog
from ..widgets import Page, Table, confirm, error, fill_combo, fmt, info, label, panel, row, safe


class StudentsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Students")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        add, bulk = QPushButton("Add student"), QPushButton("Add many")
        self.b_del = QPushButton("Delete")
        add.setObjectName("primary")
        self.b_del.setObjectName("danger")
        self.b_del.setEnabled(False)
        add.clicked.connect(lambda _=False: self.add())
        bulk.clicked.connect(lambda _=False: self.bulk())
        self.b_del.clicked.connect(lambda _=False: self.delete_selected())
        for w in (label("Class"), self.cls, self.b_del, bulk, add):
            self.actions.addWidget(w)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, reg. no. or phone")
        self.search.textChanged.connect(lambda _: self.refresh())
        self.table = Table(["Name", "Reg. no.", "Phone", "Class", "Average", "Grade", "Division", "Attendance", "Trend"], stretch=0, multi=True)
        self.table.doubleClicked.connect(lambda: app.open_student(self.table.current_id()))
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.body.addWidget(panel(row(self.search, None), self.table,
                                  label("Double-click a student to open their profile. Select rows (Ctrl or Shift to pick several, Ctrl+A for all) "
                                        "and press Delete, or right-click for more.", "muted", wrap=True)))
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
            self.delete_selected()
            return True
        return super().eventFilter(obj, event)

    def _selection_changed(self):
        n = len(self.table.selected_ids())
        self.b_del.setEnabled(bool(n))
        self.b_del.setText("Delete" if n < 2 else f"Delete {n} students")

    def _menu(self, pos):
        ids = self.table.selected_ids()
        if not ids:
            return
        m = QMenu(self)
        one = len(ids) == 1
        act_open = m.addAction("Open profile") if one else None
        act_edit = m.addAction("Edit details") if one else None
        act_del = m.addAction("Delete" if one else f"Delete {len(ids)} students")
        chosen = m.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_open:
            self.app.open_student(ids[0])
        elif chosen is act_edit:
            self.edit(ids[0])
        elif chosen is act_del:
            self.delete_selected()

    @safe
    def edit(self, student_id: int):
        stu = self.app.gb.students[student_id]
        d = StudentDialog(self, self._class_names(), stu, self.app.gb.class_name(stu.class_id))
        if d.exec():
            R.save_student(stu.id, **d.values())
            self.app.reload()

    @safe
    def delete_selected(self):
        gb = self.app.gb
        ids = self.table.selected_ids()
        if not ids:
            return error(self, "Select one or more students first.")
        names = [gb.students[i].name for i in ids if i in gb.students]
        if len(ids) == 1:
            text = f"Remove {names[0]}? Their marks and attendance will be deleted too."
        else:
            shown = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
            text = f"Remove these {len(ids)} students?\n\n{shown}\n\nTheir marks and attendance will be deleted too."
        if confirm(self, text):
            n = R.delete_students(ids)
            self.app.reload()
            info(self, f"Removed {n} student{'s' if n != 1 else ''}.")

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
        self._selection_changed()
        self.subtitle.setText(f"{len(studs)} student{'s' if len(studs) != 1 else ''}")