# /markbook/frontend/pages/timetable.py
"""The weekly timetable for a class. Attendance is taken against these sessions."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QPushButton, QTableWidgetItem

from backend.services import timetable as TT
from backend.services import terms as T

from .. import theme
from ..dialogs import SlotDialog
from ..widgets import Page, Table, confirm, error, fill_combo, info, label, panel, row, safe


class TimetablePage(Page):
    def __init__(self, app):
        super().__init__(app, "Timetable")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        add = QPushButton("Add lesson")
        add.setObjectName("primary")
        add.clicked.connect(lambda _=False: self.add())
        copy = QPushButton("Copy from another term…")
        copy.clicked.connect(lambda _=False: self.copy_term())
        for w in (label("Class"), self.cls, copy, add):
            self.actions.addWidget(w)
        self.note = label("", "notice", wrap=True)
        self.grid = Table(["Time"], stretch=None)
        self.body.addWidget(panel(self.note, self.grid, title="The week"))
        self.list = Table(["Day", "Time", "Subject", "Room", "Minutes", "Registers taken"], stretch=2)
        self.list.doubleClicked.connect(lambda: self.edit())
        edit, delete = QPushButton("Edit"), QPushButton("Remove lesson")
        delete.setObjectName("danger")
        edit.clicked.connect(lambda _=False: self.edit())
        delete.clicked.connect(lambda _=False: self.delete())
        self.body.addWidget(panel(self.list, row(edit, delete, None),
                                  label("Double-click a lesson to change its day, time or subject. Removing a lesson keeps any "
                                        "registers already taken for it.", "muted", wrap=True),
                                  title="Lessons"))
        self.body.addStretch(1)

    def _class_changed(self):
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def refresh(self):
        gb = self.app.gb
        cid = self.app.ensure_class()
        fill_combo(self.cls, self.app.class_items(), cid)
        term = gb.term
        self.subtitle.setText(f"{gb.class_name(cid)} · {gb.term_label}" if cid else "Add a class first.")
        slots = TT.list_slots(cid, term.id if term else None) if cid else []
        self.note.setObjectName("noticeDone" if slots else "note")
        self.note.setStyleSheet("")
        if not term:
            self.note.setText("A timetable belongs to a term. Choose a term at the top left, or add one in Settings.")
        elif slots:
            total = sum(s.minutes for s in slots)
            self.note.setText(f"{len(slots)} lesson(s) a week, {total // 60}h {total % 60:02d}m of teaching. "
                              "Attendance is taken against these sessions.")
        else:
            self.note.setText("No lessons set for this class yet. Add them here, then attendance can be recorded "
                              "against a real lesson instead of a bare date.")
        days = sorted({s.weekday for s in slots}) or [0, 1, 2, 3, 4]
        times = sorted({(s.starts_at, s.ends_at) for s in slots})
        self.grid.set_headers(["Time", *[TT.DAYS[d] for d in days]], stretch=None)
        self.grid.setRowCount(len(times))
        for r, (start, end) in enumerate(times):
            self.grid.setItem(r, 0, QTableWidgetItem(f"{start:%H:%M}–{end:%H:%M}"))
            for c, day in enumerate(days, start=1):
                here = [s for s in slots if s.weekday == day and (s.starts_at, s.ends_at) == (start, end)]
                text = "\n".join(f"{gb.subject_name(s.subject_id)}" + (f"\n{s.room}" if s.room else "") for s in here)
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if here:
                    cell.setForeground(theme.q(theme.INK))
                self.grid.setItem(r, c, cell)
        self.grid.resizeColumnsToContents()
        self.grid.resizeRowsToContents()
        self.grid.fit(12)
        taken = {}
        for d in gb.days:
            if d.slot_id:
                taken[d.slot_id] = taken.get(d.slot_id, 0) + 1
        self.list.set_rows([[TT.DAYS[s.weekday], s.time_label, gb.subject_name(s.subject_id), s.room or "–",
                             s.minutes, taken.get(s.id, 0)] for s in slots], [s.id for s in slots], fit_height=True)

    def _subjects(self):
        gb = self.app.gb
        subs = gb.class_subjects(self.app.class_id)
        return subs or sorted(gb.subjects.values(), key=lambda s: s.name.lower())

    @safe
    def add(self):
        if not self.app.class_id or not self._subjects():
            return error(self, "Add a class and at least one subject first.")
        d = SlotDialog(self, self._subjects())
        if d.exec():
            TT.save_slot(None, class_id=self.app.class_id, **d.values())
            self.app.reload()

    @safe
    def edit(self):
        sid = self.list.current_id()
        if sid is None:
            return error(self, "Select a lesson first.")
        slot = next((s for s in TT.list_slots(self.app.class_id, None) if s.id == sid), None)
        d = SlotDialog(self, self._subjects(), slot)
        if d.exec():
            TT.save_slot(sid, class_id=self.app.class_id, term_id=slot.term_id, **d.values())
            self.app.reload()

    @safe
    def delete(self):
        sid = self.list.current_id()
        if sid is None:
            return error(self, "Select a lesson first.")
        if confirm(self, "Remove this lesson from the timetable?\n\nRegisters already taken for it are kept, "
                         "and still count towards attendance."):
            kept = TT.delete_slot(sid)
            self.app.reload()
            info(self, f"Lesson removed. {kept} register(s) kept." if kept else "Lesson removed.")

    @safe
    def copy_term(self):
        term = self.app.gb.term
        if not term:
            return error(self, "Choose a term first.")
        others = [t for t in T.list_terms() if t.id != term.id]
        if not others:
            return error(self, "There is no other term to copy from.")
        from ..dialogs import ChooseDialog
        d = ChooseDialog(self, "Copy a timetable", f"Copy lessons into {term.label} from:",
                         [(t.label, t.id) for t in others])
        if d.exec():
            made = TT.copy_to_term(self.app.class_id, d.value(), term.id)
            self.app.reload()
            info(self, f"Copied {made} lesson(s) into {term.label}.")