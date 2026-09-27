# /markbook/frontend/quick_find.py
"""Ctrl+K: type a few letters, press Enter, land on the student.

Scrolling a class list to find one student is the thing you do fifty times a day, so this
searches every class at once — name, reg. number or phone. Words can be typed in any order and
shortened ("mwa nee" finds Neema Mwakalinga), and a phone can be typed the way it is dialled
(0793…) even though it is stored as +255793….
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from backend.phone import display_phone
from backend.services import records as R

from .widgets import label


def haystack(student, class_name: str) -> str:
    phone = student.phone or ""
    local = "0" + phone[4:] if phone.startswith("+255") else ""      # typed as 0793…, stored as +255793…
    return f"{student.name} {student.reg_no or ''} {phone} {local} {class_name}".lower()


def score(student, class_name: str, query: str) -> int | None:
    """Lower is better; None means no match. Whole-word starts rank above matches inside a word."""
    hay = haystack(student, class_name)
    words = hay.split()
    total = 0
    for part in query.lower().split():
        if any(w.startswith(part) for w in words):
            total += 0
        elif part in hay:
            total += 5
        else:
            return None
    if student.name.lower().startswith(query.lower()):
        total -= 3
    return total


class QuickFind(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("Find a student")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        self.box = QLineEdit()
        self.box.setPlaceholderText("Name, reg. number or phone — then Enter")
        self.box.textChanged.connect(self._search)
        self.box.returnPressed.connect(self._open)
        self.list = QListWidget()
        self.list.itemActivated.connect(lambda _: self._open())
        self.list.itemDoubleClicked.connect(lambda _: self._open())
        self.hint = label("", "muted", wrap=True)
        lay.addWidget(self.box)
        lay.addWidget(self.list)
        lay.addWidget(self.hint)
        self.students = R.list_students()
        self.archived = {s.id for s in R.list_students(archived=True)}
        self.students += R.list_students(archived=True)
        self._search("")

    def keyPressEvent(self, event):
        """Down from the box moves into the list, so it is all keyboard."""
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.box.hasFocus() and self.list.count():
            self.list.setFocus()
            self.list.setCurrentRow(0 if event.key() == Qt.Key.Key_Down else self.list.count() - 1)
            return
        super().keyPressEvent(event)

    def _search(self, text: str = ""):
        gb = self.app.gb
        self.list.clear()
        query = text.strip()
        matches = []
        for s in self.students:
            class_name = gb.class_name(s.class_id)
            rank = 0 if not query else score(s, class_name, query)
            if rank is None:
                continue
            matches.append((rank + (20 if s.id in self.archived else 0), s.name.lower(), s, class_name))
        matches.sort(key=lambda m: (m[0], m[1]))
        for _, _, s, class_name in matches[:40]:
            bits = [class_name] + [x for x in (s.reg_no, display_phone(s.phone)) if x]
            if s.id in self.archived:
                bits.append("archived")
            item = QListWidgetItem(f"{s.name}   —   {'  ·  '.join(bits)}")
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        shown = self.list.count()
        self.hint.setText(f"{shown} of {len(self.students)} students" + (", showing the first 40" if len(matches) > 40 else "")
                          if query else f"{len(self.students)} students — start typing")

    def _open(self):
        item = self.list.currentItem()
        if item is None:
            return
        self.accept()
        self.app.open_student(item.data(Qt.ItemDataRole.UserRole))