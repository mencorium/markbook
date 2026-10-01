# /markbook/frontend/pages/attendance.py
"""Daily register per class."""
from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import QComboBox, QDateEdit, QGridLayout, QPushButton, QTableWidgetItem, QWidget

from backend import attendance_codes as AC
from backend.services import attendance as ATT
from backend.services import timetable as TT

from .. import theme
from ..widgets import Page, Table, confirm, fill_combo, fmt, info, label, panel, row, safe


class AttendancePage(Page):
    def __init__(self, app):
        super().__init__(app, "Attendance")
        self.dirty = False
        self._loading = False
        self._sessions = []
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        self.actions.addWidget(label("Class"))
        self.actions.addWidget(self.cls)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.dateChanged.connect(lambda _: self._date_changed())
        allp, save, delete = QPushButton("Everyone present"), QPushButton("Save attendance"), QPushButton("Delete this register")
        save.setObjectName("primary")
        delete.setObjectName("danger")
        allp.clicked.connect(lambda _=False: self.all_present())
        save.clicked.connect(lambda _=False: self.save())
        delete.clicked.connect(lambda _=False: self.delete())
        self.status = label("", "notice", wrap=True)
        self.sessions = Table(["Time", "Subject", "Room", "Register"], stretch=1)
        self.sessions.itemSelectionChanged.connect(self._session_picked)
        self.whole_day = QPushButton("Whole-day register instead")
        self.whole_day.setCheckable(True)
        self.whole_day.toggled.connect(lambda _: self._session_picked())
        self.to_timetable = QPushButton("Open the timetable")
        self.to_timetable.clicked.connect(lambda _=False: app.show_page("timetable"))
        self.register = Table(["Student", "Attendance", "Note"], stretch=0, editable=True)
        self.register.itemChanged.connect(self._changed)
        self.legend = label("", "muted", wrap=True)
        g = QGridLayout()
        g.setSpacing(14)
        g.addWidget(panel(self.status, row(label("Date"), self.date, None, self.whole_day, self.to_timetable),
                          label("Lessons on this day", "h2"), self.sessions,
                          row(label("Register", "h2"), None, allp, save), self.register, self.legend, row(delete, None),
                          stretch_end=True), 0, 0, 2, 1)
        self.lowest = Table(["Student", "Attendance"], stretch=0)
        self.lowest.doubleClicked.connect(lambda: app.open_student(self.lowest.current_id()))
        self.days = Table(["Date", "Present"], stretch=0)
        self.days.doubleClicked.connect(self._open_day)
        g.addWidget(panel(self.lowest, title="Lowest attendance", stretch_end=True), 0, 1)
        g.addWidget(panel(self.days, title="Recorded days (double-click to open)", stretch_end=True), 1, 1)
        g.setColumnStretch(0, 3)
        g.setColumnStretch(1, 2)
        w = QWidget()
        w.setLayout(g)
        self.body.addWidget(w)
        self.body.addStretch(1)

    def can_leave(self):
        if self.dirty and not confirm(self, "Discard unsaved attendance?"):
            return False
        self.dirty = False
        return True

    def _class_changed(self):
        if not self.can_leave():
            return
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def _date_changed(self):
        if self.dirty and not confirm(self, "Discard unsaved attendance for this day?"):
            return
        self.dirty = False
        self.refresh()

    def _day(self) -> dt.date:
        q = self.date.date()
        return dt.date(q.year(), q.month(), q.day())

    def _slot(self):
        """The lesson whose register is on screen, or None for a whole-day register."""
        if self.whole_day.isChecked():
            return None
        sid = self.sessions.current_id()
        return next((s for s in self._sessions if s.id == sid), None)

    def _load_sessions(self):
        gb, cid, day = self.app.gb, self.app.class_id, self._day()
        self._sessions = TT.sessions_on(cid, day, gb.term.id if gb.term else None) if cid else []
        rows = []
        for s in self._sessions:
            recorded = ATT.get_day(cid, day, s.id)
            rows.append([s.time_label, gb.subject_name(s.subject_id), s.room or "–",
                         f"{len(recorded.roster) - len(recorded.absent)}/{len(recorded.roster)} present" if recorded else "not taken"])
        self.sessions.set_rows(rows, [s.id for s in self._sessions],
                               colors={(i, 3): (theme.GREEN if "present" in r[3] else theme.AMBER, None) for i, r in enumerate(rows)},
                               fit_height=True)
        self.sessions.setVisible(bool(self._sessions))
        self.to_timetable.setVisible(not self._sessions)
        self.whole_day.blockSignals(True)
        # each day starts on its first lesson; whole-day is a deliberate choice, never a leftover
        self.whole_day.setChecked(not self._sessions)
        self.whole_day.setEnabled(bool(self._sessions))
        self.whole_day.blockSignals(False)
        if self._sessions:
            self.sessions.selectRow(0)

    def _session_picked(self):
        if not self._loading:
            self._load_register()

    def refresh(self):
        gb = self.app.gb
        cid = self.app.ensure_class()
        fill_combo(self.cls, self.app.class_items(), cid)
        if not cid:
            self.subtitle.setText("Add students first.")
            return
        rate = gb.class_att(cid)
        self.subtitle.setText(f"{gb.class_name(cid)} · {gb.term_label} · class rate "
                              + ("not recorded yet" if rate is None else f"{round(rate)}%"))
        self._loading = True
        self._load_sessions()
        self._loading = False
        self._load_register()
        self._load_side()

    def _load_register(self):
        gb, cid = self.app.gb, self.app.class_id
        slot = self._slot()
        existing = ATT.get_day(cid, self._day(), slot.id if slot else None)
        studs = gb.students_in(cid)
        self._loading = True
        self.register.clear_cell_widgets()
        self.register.setRowCount(len(studs))
        for r, s in enumerate(studs):
            n = QTableWidgetItem(s.name)
            n.setFlags(n.flags() & ~Qt.ItemFlag.ItemIsEditable)
            n.setData(Qt.ItemDataRole.UserRole, s.id)
            self.register.setItem(r, 0, n)
            code = existing.code(s.id) if existing else AC.DEFAULT
            combo = QComboBox()
            for c in AC.CODES:
                combo.addItem(c.label, c.code)
            combo.setCurrentIndex(max(0, combo.findData(AC.get(code).code)))
            combo.currentIndexChanged.connect(self._code_changed)
            self.register.setCellWidget(r, 1, combo)
            self.register.setItem(r, 2, QTableWidgetItem((existing.notes.get(s.id, "") if existing else "")))
        self.register.resizeColumnsToContents()
        self.register.setColumnWidth(0, max(200, self.register.columnWidth(0)))
        self.register.setColumnWidth(1, max(190, self.register.columnWidth(1)))
        self.register.fit(60)
        self._loading = False
        self.dirty = False
        self.legend.setText("Pick a code for anyone not present. " + AC.legend()
                            + ".  Sick, permit and suspended are excused: they do not count against a student's "
                              "attendance, but are still recorded. Use the Note column for a reason.")
        self._status(existing is not None)

    def _codes(self) -> dict:
        out = {}
        for r in range(self.register.rowCount()):
            combo = self.register.cellWidget(r, 1)
            sid = self.register.item(r, 0).data(Qt.ItemDataRole.UserRole)
            out[sid] = combo.currentData() if combo else AC.DEFAULT
        return out

    def _code_changed(self, _=None):
        if self._loading:
            return
        self.dirty = True
        slot = self._slot()
        self._status(ATT.get_day(self.app.class_id, self._day(), slot.id if slot else None) is not None)

    def _load_side(self):
        gb, cid = self.app.gb, self.app.class_id
        studs = gb.students_in(cid)
        rates = sorted(((s, gb.att_rate(s)) for s in studs if gb.att_rate(s) is not None), key=lambda x: x[1])[:10]
        self.lowest.set_rows([[s.name, fmt(v, "%")] for s, v in rates], [s.id for s, _ in rates],
                             colors={(i, 1): (theme.PEN, None) for i, (_, v) in enumerate(rates) if v < 80}, fit_height=True)
        days = ATT.list_days(cid, gb.term.id if gb.term else None)[:30]
        self.days.set_headers(["Date", "Lesson", "Present"], stretch=1)
        self.days.set_rows([[d.date.isoformat(), gb.subject_name(d.subject_id) if d.subject_id else "whole day",
                             f"{len(d.roster) - len(d.absent)}/{len(d.roster)}"] for d in days],
                           [(d.date, d.slot_id) for d in days], fit_height=True)

    def _status(self, exists: bool):
        """Say which lesson this register belongs to, so it is never ambiguous later."""
        gb = self.app.gb
        total = self.register.rowCount()
        codes = self._codes() if total else {}
        tally = {c.code: sum(1 for v in codes.values() if v == c.code) for c in AC.CODES}
        present = tally.get(AC.PRESENT, 0)
        slot = self._slot()
        day = f"{self._day():%A %d %b %Y}"
        if slot:
            what = f"{day}, {slot.time_label} {gb.subject_name(slot.subject_id)}"
            style = "noticeDone" if exists else "notice"
        elif self._sessions:
            what = f"{day} — whole-day register, not tied to a lesson"
            style = "note"
        else:
            what = f"{day} — nothing is timetabled for this class on a {self._day():%A}"
            style = "note"
        self.status.setObjectName(style)
        self.status.setStyleSheet("")               # re-apply the stylesheet for the new object name
        detail = ", ".join(f"{n} {AC.name(code).lower()}" for code, n in tally.items() if n and code != AC.PRESENT)
        self.status.setText(f"{what}. " + ("Already recorded; saving updates it. " if exists else "Not recorded yet. ")
                            + f"{present} of {total} present" + (f" — {detail}." if detail else "."))

    def _changed(self, item):
        if self._loading or item.column() != 2:      # only the note column is typed into
            return
        self.dirty = True
        slot = self._slot()
        self._status(ATT.get_day(self.app.class_id, self._day(), slot.id if slot else None) is not None)

    def _open_day(self):
        chosen = self.days.current_id()
        if not chosen or not self.can_leave():
            return
        day, slot_id = chosen
        self.date.setDate(QDate(day.year, day.month, day.day))
        self.whole_day.setChecked(slot_id is None)
        if slot_id is not None:
            row = next((i for i, s in enumerate(self._sessions) if s.id == slot_id), None)
            if row is not None:
                self.sessions.selectRow(row)

    def all_present(self):
        self._loading = True
        for r in range(self.register.rowCount()):
            combo = self.register.cellWidget(r, 1)
            if combo:
                combo.setCurrentIndex(max(0, combo.findData(AC.PRESENT)))
        self._loading = False
        self._code_changed()

    @safe
    def save(self):
        codes = self._codes()
        roster = list(codes)
        notes = {}
        for r in range(self.register.rowCount()):
            sid = self.register.item(r, 0).data(Qt.ItemDataRole.UserRole)
            cell = self.register.item(r, 2)
            if cell and cell.text().strip():
                notes[sid] = cell.text().strip()
        slot = self._slot()
        ATT.save_day(self.app.class_id, self._day(), roster, status=codes, notes=notes,
                     slot_id=slot.id if slot else None, subject_id=slot.subject_id if slot else None)
        self.dirty = False
        self.app.reload()
        info(self, f"Attendance saved for {self._day():%d %b %Y}"
                   + (f", {slot.time_label} {self.app.gb.subject_name(slot.subject_id)}." if slot else "."))

    @safe
    def delete(self):
        if confirm(self, "Delete attendance for this day?"):
            slot = self._slot()
            ATT.delete_day(self.app.class_id, self._day(), slot.id if slot else None)
            self.dirty = False
            self.app.reload()