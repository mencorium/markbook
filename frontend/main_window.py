# /markbook/frontend/main_window.py
"""Main window: sidebar + stacked pages. Holds the shared Gradebook snapshot and the selected class."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from backend.config import get_config
from backend.services.analytics import Gradebook

from .pages.assessments import AssessmentsPage
from .pages.attendance import AttendancePage
from .pages.dashboard import DashboardPage
from .pages.import_export import ImportExportPage
from .pages.mark_entry import MarkEntryPage
from .pages.results import ResultsPage
from .pages.settings import SettingsPage
from .pages.student_detail import StudentDetailPage
from .pages.students import StudentsPage
from .pages.subjects import SubjectsPage
from .pages.topics import TopicsPage
from .widgets import label

NAV = [("dashboard", "Overview"), ("students", "Students"), ("subjects", "Subjects"), ("assessments", "Tests & exams"),
       ("attendance", "Attendance"), ("topics", "Topics"), ("results", "Results & reports"), ("io", "Import & export"), ("settings", "Settings")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Markbook — student progress")
        self.resize(1320, 860)
        self.gb: Gradebook = Gradebook.load()
        self.class_id: int | None = None
        self.student_id: int | None = None
        self.assessment_id: int | None = None

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QWidget()
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        sv.addWidget(label("✓ Markbook", "brand"))
        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        for key, text in NAV:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(it)
        sv.addWidget(self.nav, 1)
        db = get_config().database_url.rsplit("@", 1)[-1]
        sv.addWidget(label(f"PostgreSQL · {db}", "storeNote", wrap=True))
        h.addWidget(side)

        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.pages = {
            "dashboard": DashboardPage(self), "students": StudentsPage(self), "student": StudentDetailPage(self),
            "subjects": SubjectsPage(self), "assessments": AssessmentsPage(self), "entry": MarkEntryPage(self),
            "attendance": AttendancePage(self), "topics": TopicsPage(self), "results": ResultsPage(self),
            "io": ImportExportPage(self), "settings": SettingsPage(self),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)
        self.current = "dashboard"
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.nav.setCurrentRow(0)

    # ---------------- navigation ----------------
    def _nav_changed(self, row: int) -> None:
        if row < 0:
            return
        key = self.nav.item(row).data(Qt.ItemDataRole.UserRole)
        if key != self.current and not self._leave_ok():
            self.nav.blockSignals(True)
            self.nav.setCurrentRow([k for k, _ in NAV].index(self._nav_key(self.current)))
            self.nav.blockSignals(False)
            return
        self.show_page(key)

    def _nav_key(self, key: str) -> str:
        return {"student": "students", "entry": "assessments"}.get(key, key)

    def _leave_ok(self) -> bool:
        page = self.pages.get(self.current)
        return page.can_leave() if hasattr(page, "can_leave") else True

    def show_page(self, key: str) -> None:
        self.current = key
        self.nav.blockSignals(True)
        self.nav.setCurrentRow([k for k, _ in NAV].index(self._nav_key(key)))
        self.nav.blockSignals(False)
        page = self.pages[key]
        page.refresh()
        self.stack.setCurrentWidget(page)

    def open_student(self, student_id: int) -> None:
        if student_id is not None and self._leave_ok():
            self.student_id = student_id
            self.show_page("student")

    def open_assessment(self, assessment_id: int, tab: str | None = None) -> None:
        if assessment_id is not None and self._leave_ok():
            self.assessment_id = assessment_id
            self.pages["entry"].start_tab = tab
            self.show_page("entry")

    # ---------------- shared state ----------------
    def reload(self) -> None:
        """Re-read the database after a change and redraw the current page."""
        self.gb = Gradebook.load()
        self.pages[self.current].refresh()

    def class_items(self) -> list[tuple[str, int]]:
        return [(c.name, c.id) for c in sorted(self.gb.classes.values(), key=lambda c: c.name.lower())]

    def ensure_class(self) -> int | None:
        ids = [cid for _, cid in self.class_items()]
        if self.class_id not in ids:
            self.class_id = ids[0] if ids else None
        return self.class_id