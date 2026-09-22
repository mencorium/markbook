# /markbook/frontend/pages/attendance.py
"""Daily register per class."""
from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import QComboBox, QDateEdit, QGridLayout, QPushButton, QTableWidgetItem, QWidget

from backend.services import attendance as ATT

from .. import theme
from ..widgets import Page, Table, confirm, fill_combo, fmt, info, label, panel, row, safe


class AttendancePage(Page):
    def __init__(self, app):
        super().__init__(app, "Attendance")
        self.dirty = False
        self._loading = False
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        self.actions.addWidget(label("Class"))
        self.actions.addWidget(self.cls)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.dateChanged.connect(lambda _: self._date_changed())
        allp, save, delete = QPushButton("Everyone present"), QPushButton("Save attendance"), QPushButton("Delete this day")
        save.setObjectName("primary")
        delete.setObjectName("danger")
        allp.clicked.connect(lambda _=False: self.all_present())
        save.clicked.connect(lambda _=False: self.save())
        delete.clicked.connect(lambda _=False: self.delete())
        self.status = label("", "notice", wrap=True)
        self.register = Table(["Student", "Present"], stretch=0)
        self.register.itemChanged.connect(self._changed)
        g = QGridLayout()
        g.setSpacing(14)
        g.addWidget(panel(self.status, row(label("Date"), self.date, None, allp, save), self.register, row(delete, None), stretch_end=True), 0, 0, 2, 1)
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

    def refresh(self):
        gb = self.app.gb
        cid = self.app.ensure_class()
        fill_combo(self.cls, self.app.class_items(), cid)
        if not cid:
            self.subtitle.setText("Add students first.")
            return
        rate = gb.class_att(cid)
        self.subtitle.setText(f"{gb.class_name(cid)} · class rate {'not recorded yet' if rate is None else f'{round(rate)}%'}")
        existing = ATT.get_day(cid, self._day())
        absent = set(existing.absent) if existing else set()
        studs = gb.students_in(cid)
        self._loading = True
        self.register.setRowCount(len(studs))
        for r, s in enumerate(studs):
            n = QTableWidgetItem(s.name)
            n.setData(Qt.ItemDataRole.UserRole, s.id)
            self.register.setItem(r, 0, n)
            chk = QTableWidgetItem("Present" if s.id not in absent else "Absent")
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked if s.id in absent else Qt.CheckState.Checked)
            self.register.setItem(r, 1, chk)
        self.register.fit(60)
        self._loading = False
        self.dirty = False
        self._status(existing is not None)
        rates = sorted(((s, gb.att_rate(s)) for s in studs if gb.att_rate(s) is not None), key=lambda x: x[1])[:10]
        self.lowest.set_rows([[s.name, fmt(v, "%")] for s, v in rates], [s.id for s, _ in rates],
                             colors={(i, 1): (theme.PEN, None) for i, (_, v) in enumerate(rates) if v < 80}, fit_height=True)
        days = ATT.list_days(cid)[:30]
        self.days.set_rows([[d.date.isoformat(), f"{len(d.roster) - len(d.absent)}/{len(d.roster)}"] for d in days], [d.date for d in days], fit_height=True)

    def _status(self, exists: bool):
        total = self.register.rowCount()
        present = sum(1 for r in range(total) if self.register.item(r, 1).checkState() == Qt.CheckState.Checked)
        day = f"{self._day():%A %d %b %Y}"
        self.status.setObjectName("noticeDone" if exists else "notice")
        self.status.setStyleSheet("")               # re-apply the stylesheet for the new object name
        self.status.setText(f"{day} — " + ("already recorded; saving updates it. " if exists else "not recorded yet. ")
                            + f"{present} of {total} present, {total - present} absent.")

    def _changed(self, item):
        if self._loading or item.column() != 1:
            return
        self._loading = True
        item.setText("Present" if item.checkState() == Qt.CheckState.Checked else "Absent")
        self._loading = False
        self.dirty = True
        self._status(ATT.get_day(self.app.class_id, self._day()) is not None)

    def _open_day(self):
        d = self.days.current_id()
        if d and self.can_leave():
            self.date.setDate(QDate(d.year, d.month, d.day))

    def all_present(self):
        for r in range(self.register.rowCount()):
            self.register.item(r, 1).setCheckState(Qt.CheckState.Checked)

    @safe
    def save(self):
        roster, absent = [], set()
        for r in range(self.register.rowCount()):
            sid = self.register.item(r, 0).data(Qt.ItemDataRole.UserRole)
            roster.append(sid)
            if self.register.item(r, 1).checkState() != Qt.CheckState.Checked:
                absent.add(sid)
        ATT.save_day(self.app.class_id, self._day(), roster, absent)
        self.dirty = False
        self.app.reload()
        info(self, f"Attendance saved for {self._day():%d %b %Y}.")

    @safe
    def delete(self):
        if confirm(self, "Delete attendance for this day?"):
            ATT.delete_day(self.app.class_id, self._day())
            self.dirty = False
            self.app.reload()