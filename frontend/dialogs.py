# /markbook/frontend/dialogs.py
"""Add/edit dialogs. They collect input only; pages call the backend services."""
from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLineEdit,
                             QPlainTextEdit, QTableWidgetItem, QVBoxLayout)

from backend.phone import PhoneError, display_phone, normalize_phone
from backend.services.assessments import TYPES

from .widgets import Table, error, label


class _Form(QDialog):
    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.lay = QVBoxLayout(self)
        self.form = QFormLayout()
        self.lay.addLayout(self.form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._ok)
        self.buttons.rejected.connect(self.reject)

    def finish(self):
        self.lay.addWidget(self.buttons)

    def _ok(self):
        msg = self.validate()
        if msg:
            error(self, msg)
        else:
            self.accept()

    def validate(self) -> str | None:
        return None


class StudentDialog(_Form):
    def __init__(self, parent, classes: list[str], student=None, class_name: str = ""):
        super().__init__(parent, "Edit student" if student else "Add a student")
        self.name = QLineEdit(student.name if student else "")
        self.reg = QLineEdit((student.reg_no or "") if student else "")
        self.reg.setPlaceholderText("optional")
        self.phone = QLineEdit(display_phone(student.phone) if student else "")
        self.phone.setPlaceholderText("e.g. 0712 345 678")
        self.cls = QComboBox()
        self.cls.setEditable(True)
        self.cls.addItems(classes)
        self.cls.setCurrentText(class_name)
        self.form.addRow("Full name", self.name)
        self.form.addRow("Reg. number", self.reg)
        self.form.addRow("Phone number", self.phone)
        self.form.addRow("", label("Used later for automated messages. Stored as +255…", "muted"))
        self.form.addRow("Class", self.cls)
        if student:
            self.form.addRow("", label("Moving a student to another class keeps their marks and attendance.", "muted", wrap=True))
        self.finish()

    def validate(self):
        if not self.name.text().strip():
            return "Enter the student's name."
        if not self.cls.currentText().strip():
            return "Enter a class."
        try:
            normalize_phone(self.phone.text())
        except PhoneError as e:
            return str(e)
        return None

    def values(self) -> dict:
        return {"name": self.name.text(), "reg_no": self.reg.text(), "phone": self.phone.text(), "class_name": self.cls.currentText()}


class BulkStudentsDialog(_Form):
    def __init__(self, parent, classes: list[str], class_name: str = ""):
        super().__init__(parent, "Add many students")
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Neema Mwakalinga, 2024-017, 0712 345 678\nBaraka Mwansasu, 2024-018")
        self.cls = QComboBox()
        self.cls.setEditable(True)
        self.cls.addItems(classes)
        self.cls.setCurrentText(class_name)
        self.form.addRow(label("One student per line: name, then optional reg. number and phone, separated by commas.", "muted", wrap=True))
        self.form.addRow(self.text)
        self.form.addRow("Class", self.cls)
        self.finish()

    def validate(self):
        return None if self.text.toPlainText().strip() and self.cls.currentText().strip() else "Enter at least one name and a class."


class SubjectDialog(_Form):
    def __init__(self, parent, subject=None):
        super().__init__(parent, "Edit subject" if subject else "Add a subject")
        self.name = QLineEdit(subject.name if subject else "")
        self.code = QLineEdit(subject.code if subject else "")
        self.code.setMaxLength(6)
        self.sub = QCheckBox("Subsidiary subject (not counted in the A-Level division)")
        self.sub.setChecked(bool(subject and subject.subsidiary))
        self.form.addRow("Subject name", self.name)
        self.form.addRow("Short code", self.code)
        self.form.addRow("", self.sub)
        self.finish()

    def validate(self):
        return None if self.name.text().strip() else "Enter a subject name."

    def values(self) -> dict:
        return {"name": self.name.text(), "code": self.code.text(), "subsidiary": self.sub.isChecked()}


class AssessmentDialog(_Form):
    def __init__(self, parent, subjects, classes, a=None, class_id=None, topics_for=None):
        super().__init__(parent, "Edit assessment" if a else "New assessment")
        self.subject = QComboBox()
        for s in subjects:
            self.subject.addItem(s.name, s.id)
        self.cls = QComboBox()
        for c in classes:
            self.cls.addItem(c.name, c.id)
        self.type = QComboBox()
        self.type.addItems(TYPES)
        self.name = QLineEdit(a.name if a else "")
        self.name.setPlaceholderText("e.g. Test 2, Midterm")
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        d = a.date if a else dt.date.today()
        self.date.setDate(QDate(d.year, d.month, d.day))
        self.max = QDoubleSpinBox()
        self.max.setRange(0.5, 1000)
        self.max.setValue(a.max_marks if a else 100)
        self.topics = QLineEdit(", ".join(a.topics) if a else "")
        self.topics.setPlaceholderText("e.g. Arrays, Sorting")
        self.paper = QCheckBox("Mark per question, with a topic for each question")
        if a:
            self.subject.setCurrentIndex(max(0, self.subject.findData(a.subject_id)))
            self.cls.setCurrentIndex(max(0, self.cls.findData(a.class_id)))
            self.type.setCurrentText(a.type)
            self.cls.setEnabled(False)
        elif class_id:
            self.cls.setCurrentIndex(max(0, self.cls.findData(class_id)))
        is_paper = bool(a and a.is_paper)
        self.max.setEnabled(not is_paper)
        self.topics.setEnabled(not is_paper)
        self.form.addRow("Subject", self.subject)
        self.form.addRow("Class", self.cls)
        self.form.addRow("Type", self.type)
        self.form.addRow("Name", self.name)
        self.form.addRow("Date", self.date)
        self.form.addRow("Out of", self.max)
        self.form.addRow("Topics covered", self.topics)
        if is_paper:
            self.form.addRow("", label("Out of and topics come from the question paper.", "muted"))
        if not a:
            self.form.addRow("", self.paper)
        self.form.addRow("", label("Exams count as the exam part of the final mark; tests, quizzes and assignments as continuous assessment.", "muted", wrap=True))
        self.finish()

    def validate(self):
        if not self.name.text().strip():
            return "Give the assessment a name."
        if self.subject.currentData() is None or self.cls.currentData() is None:
            return "Add a subject and a class first."
        return None

    def values(self) -> dict:
        q = self.date.date()
        return {"subject_id": self.subject.currentData(), "class_id": self.cls.currentData(), "type": self.type.currentText(),
                "name": self.name.text(), "date": dt.date(q.year(), q.month(), q.day()), "max_marks": self.max.value(),
                "topics": [t.strip() for t in self.topics.text().split(",") if t.strip()], "paper": self.paper.isChecked()}


class ScaleDialog(_Form):
    """Custom grade scale: grade letter, minimum %, points."""
    def __init__(self, parent, rows: list | None):
        super().__init__(parent, "Custom grade scale")
        self.table = Table(["Grade", "Minimum %", "Points"], editable=True)
        data = rows or [{"grade": g, "min": m, "points": p} for g, m, p in [("A", 80, 1), ("B", 70, 2), ("C", 60, 3), ("D", 50, 4), ("E", 40, 5), ("F", 0, 6)]]
        self.table.setRowCount(len(data) + 3)
        for r, d in enumerate(data):
            for c, k in enumerate(["grade", "min", "points"]):
                self.table.setItem(r, c, QTableWidgetItem("" if d.get(k) is None else str(d.get(k))))
        self.form.addRow(label("Leave a grade blank to remove it. Custom scales show grades and averages but no NECTA division.", "muted", wrap=True))
        self.form.addRow(self.table)
        self.finish()

    def rows(self) -> list[dict]:
        out = []
        for r in range(self.table.rowCount()):
            cell = lambda c: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
            g = cell(0)
            if not g:
                continue
            try:
                out.append({"grade": g, "min": float(cell(1) or 0), "points": int(cell(2)) if cell(2) else None})
            except ValueError:
                continue
        return sorted(out, key=lambda x: -x["min"])

    def validate(self):
        return None if self.rows() else "Add at least one grade."