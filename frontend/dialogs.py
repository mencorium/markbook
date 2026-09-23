# /markbook/frontend/dialogs.py
"""Add/edit dialogs. They collect input only; pages call the backend services."""
from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLineEdit,
                             QPlainTextEdit, QTableWidgetItem, QVBoxLayout)

from backend.grading import LEVEL_LABELS, PRESETS
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
        self.form.addRow("", label("Used later for automated messages. Stored as +255…", "muted", wrap=True))
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


class TermDialog(_Form):
    """Create or edit a term: any length the school uses."""
    def __init__(self, parent, term=None, suggestion: dict | None = None):
        super().__init__(parent, "Edit term" if term else "Add a term")
        sug = suggestion or {}
        self.name = QLineEdit(term.name if term else sug.get("name", "Term 1"))
        self.year = QLineEdit(term.year if term else sug.get("year", str(dt.date.today().year)))
        self.year.setPlaceholderText("2026 or 2026/2027")
        self.starts = QDateEdit()
        self.ends = QDateEdit()
        for w, value in ((self.starts, term.starts_on if term else sug.get("starts", dt.date.today())),
                         (self.ends, term.ends_on if term else sug.get("ends", dt.date.today() + dt.timedelta(days=180)))):
            w.setCalendarPopup(True)
            w.setDate(QDate(value.year, value.month, value.day))
        self.weight = QDoubleSpinBox()
        self.weight.setRange(0.1, 10)
        self.weight.setSingleStep(0.5)
        self.weight.setValue(term.weight if term else 1)
        self.form.addRow("Name", self.name)
        self.form.addRow("Academic year", self.year)
        self.form.addRow("Starts", self.starts)
        self.form.addRow("Ends", self.ends)
        self.form.addRow("Weight in the annual result", self.weight)
        self.form.addRow("", label("A term is whatever period you teach in — two six-month terms, three shorter ones, or a short course. "
                                   "Marks and attendance belong to the term their date falls in.", "muted", wrap=True))
        self.finish()

    def validate(self):
        if not self.name.text().strip():
            return "Give the term a name, such as Term 1."
        if not self.year.text().strip():
            return "Enter the academic year."
        if self.ends.date() < self.starts.date():
            return "The term cannot end before it starts."
        return None

    def values(self) -> dict:
        d = lambda w: dt.date(w.date().year(), w.date().month(), w.date().day())
        return {"name": self.name.text().strip(), "year": self.year.text().strip(),
                "starts_on": d(self.starts), "ends_on": d(self.ends), "weight": self.weight.value()}


class StartTermDialog(TermDialog):
    """The next term, plus what happens to each class: promote, carry on, or finish."""
    def __init__(self, parent, classes: list, suggestion: dict | None = None):
        super().__init__(parent, None, suggestion)
        self.setWindowTitle("Start the next term")
        from backend.services.terms import ROLLOVER, next_class_name
        self.rows = []
        self.table = Table(["Class", "At the end of the year", "Moves to"], stretch=0, editable=True)
        self.table.setRowCount(len(classes))
        for r, c in enumerate(classes):
            item = QTableWidgetItem(c.name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, item)
            combo = QComboBox()
            for key, text in ROLLOVER.items():
                combo.addItem(text, key)
            combo.setCurrentIndex(max(0, combo.findData(c.rollover or "promote")))
            self.table.setCellWidget(r, 1, combo)
            self.table.setItem(r, 2, QTableWidgetItem(next_class_name(c.name)))
            self.rows.append((c, combo))
        self.table.fit()
        self.lay.insertWidget(1, label("What happens to each class", "h2"))
        self.lay.insertWidget(2, self.table)
        self.lay.insertWidget(3, label("Promoted students move to the next class; the marks they already have stay with the old class and term. "
                                       "A finished course archives its students, who can be restored at any time.", "muted", wrap=True))
        self.resize(720, 560)

    def plan(self) -> list[dict]:
        out = []
        for r, (cls, combo) in enumerate(self.rows):
            target = self.table.item(r, 2)
            out.append({"class_id": cls.id, "action": combo.currentData(), "target": target.text().strip() if target else ""})
        return out


class ClassDialog(_Form):
    """Create a class (or edit its name, teacher and grading)."""
    def __init__(self, parent, existing_names: list[str], cls=None):
        super().__init__(parent, "Edit class" if cls else "Add a class")
        self.existing = [n.lower() for n in existing_names if not cls or n.lower() != cls.name.lower()]
        self.name = QLineEdit(cls.name if cls else "")
        self.name.setPlaceholderText("e.g. Form Five A")
        self.teacher = QLineEdit(cls.teacher if cls else "")
        self.teacher.setPlaceholderText("optional")
        self.level = QComboBox()
        for key, text in LEVEL_LABELS.items():
            self.level.addItem(text, key)
        self.pass_mark = QDoubleSpinBox()
        self.pass_mark.setRange(0, 100)
        self.pass_mark.setSuffix("%")
        from backend.services.terms import ROLLOVER
        self.rollover = QComboBox()
        for key, text in ROLLOVER.items():
            self.rollover.addItem(text, key)
        self.rollover.setCurrentIndex(max(0, self.rollover.findData(cls.rollover if cls else "promote")))
        self.level.currentIndexChanged.connect(self._level_changed)
        self.level.setCurrentIndex(max(0, self.level.findData(cls.level if cls else "A")))
        self.pass_mark.setValue(cls.pass_mark if cls and cls.pass_mark is not None else self._default_pass())
        self.form.addRow("Class name", self.name)
        self.form.addRow("Class teacher", self.teacher)
        self.form.addRow("Grading", self.level)
        self.form.addRow("Pass mark", self.pass_mark)
        self.form.addRow("At the end of the year", self.rollover)
        self.form.addRow("", label("A-Level takes the division from the best 3 principal subjects, O-Level from the best 7. "
                                   "A custom scale can be set up afterwards in Settings.", "muted", wrap=True))
        self.finish()

    def _default_pass(self) -> float:
        key = self.level.currentData()
        return PRESETS[key]["pass_mark"] if key in PRESETS else 40

    def _level_changed(self):
        self.pass_mark.setValue(self._default_pass())

    def validate(self):
        name = self.name.text().strip()
        if not name:
            return "Enter a class name."
        if name.lower() in self.existing:
            return f"A class called {name} already exists."
        return None

    def values(self) -> dict:
        return {"name": self.name.text().strip(), "teacher": self.teacher.text().strip(),
                "level": self.level.currentData(), "pass_mark": self.pass_mark.value(), "rollover": self.rollover.currentData()}


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