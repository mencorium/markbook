# /markbook/frontend/main_window.py
"""Main window: sidebar + stacked pages. Holds the shared Gradebook snapshot and the selected class."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QStackedWidget,
                             QVBoxLayout, QWidget)

import datetime as dt

from PyQt6.QtGui import QGuiApplication

from backend.config import get_config
from backend.log import get as get_logger
from backend.services import backup as BK
from backend.services import records as R
from backend.services import terms as T
from backend.services.analytics import Gradebook

from . import theme
from .pages.activity import ActivityPage
from .pages.assessments import AssessmentsPage
from .pages.attendance import AttendancePage
from .pages.dashboard import DashboardPage
from .pages.help import HelpPage
from .pages.import_export import ImportExportPage
from .pages.mark_entry import MarkEntryPage
from .pages.results import ResultsPage
from .pages.settings import SettingsPage
from .pages.student_detail import StudentDetailPage
from .pages.students import StudentsPage
from .pages.subject_detail import SubjectDetailPage
from .pages.subjects import SubjectsPage
from .pages.timetable import TimetablePage
from .pages.topics import TopicsPage
from .widgets import fill_combo, label

NAV = [("dashboard", "Overview"), ("students", "Students"), ("subjects", "Subjects"), ("assessments", "Tests & exams"),
       ("timetable", "Timetable"), ("attendance", "Attendance"), ("topics", "Topics"), ("results", "Results & reports"), ("io", "Import & export"), ("activity", "Activity"), ("settings", "Settings"), ("help", "Help & about")]


class MainWindow(QMainWindow):
    def __init__(self, splash=None):
        super().__init__()
        self._splash = splash
        from backend import about
        self.setWindowTitle(f"{about.APP_NAME} {about.VERSION} — {about.TAGLINE}")
        self.resize(1320, 860)
        self.gb: Gradebook = Gradebook.load()
        self.term_id: int | None = self.gb.term.id if self.gb.term else None
        self.class_id: int | None = None
        self.subject_id: int | None = None
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
        self.term_box = QComboBox()
        self.term_box.currentIndexChanged.connect(self._term_changed)
        picker = QWidget()
        pv = QVBoxLayout(picker)
        pv.setContentsMargins(12, 0, 12, 10)
        pv.setSpacing(3)
        pv.addWidget(label("TERM", "statLabel"))
        pv.addWidget(self.term_box)
        picker.setStyleSheet(f"background: {theme.SURFACE};")
        sv.addWidget(picker)
        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        for key, text in NAV:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(it)
        sv.addWidget(self.nav, 1)
        find = QPushButton("🔍  Find a student")
        find.setToolTip("Ctrl+K")
        find.clicked.connect(lambda _=False: self.find_student())
        helper = QPushButton("？  Help")
        helper.setToolTip("F1 — help for the screen you are on")
        helper.clicked.connect(lambda _=False: self.open_help())
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(12, 0, 12, 8)
        hv.setSpacing(6)
        hv.addWidget(find)
        hv.addWidget(helper)
        holder.setStyleSheet(f"background: {theme.SURFACE};")
        sv.addWidget(holder)
        db = get_config().database_url.rsplit("@", 1)[-1]
        sv.addWidget(label(f"PostgreSQL · {db}", "storeNote", wrap=True))
        h.addWidget(side)

        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self._say("Building the screens…", 80)
        self.pages = {
            "dashboard": DashboardPage(self), "students": StudentsPage(self), "student": StudentDetailPage(self),
            "subjects": SubjectsPage(self), "subject": SubjectDetailPage(self), "assessments": AssessmentsPage(self), "entry": MarkEntryPage(self),
            "timetable": TimetablePage(self), "attendance": AttendancePage(self), "topics": TopicsPage(self), "results": ResultsPage(self),
            "io": ImportExportPage(self), "activity": ActivityPage(self), "settings": SettingsPage(self), "help": HelpPage(self),
        }
        self._say("Almost there…", 92)
        for p in self.pages.values():
            self.stack.addWidget(p)
        self._fill_terms()
        self.history: list[tuple[str, dict, str]] = []       # where "back" goes, newest last
        for keys, fn in [(("Ctrl+K", "Ctrl+F"), self.find_student)]:
            for key in keys:
                QShortcut(QKeySequence(key), self, activated=fn)
        # Alt+Left only: Backspace would be swallowed here while marks are being typed
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.go_back)
        QShortcut(QKeySequence("F1"), self, activated=self.open_help)
        self.current = "dashboard"
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.nav.setCurrentRow(0)

    def _say(self, what: str, percent: int) -> None:
        """Report progress while starting, if a splash is showing."""
        if self._splash is not None:
            self._splash.step(what, percent)

    # ---------------- terms ----------------
    def _fill_terms(self) -> None:
        items = [(t.label, t.id) for t in T.list_terms()] + [("All terms", None)]
        fill_combo(self.term_box, items, self.term_id)
        if self.term_box.currentIndex() < 0:
            self.term_box.setCurrentIndex(0)

    def _term_changed(self) -> None:
        chosen = self.term_box.currentData()
        if chosen == self.term_id:
            return
        if not self._leave_ok():
            self._fill_terms()
            return
        self.term_id = chosen
        if chosen:
            T.set_current(chosen)                 # the app opens on this term next time
        self.reload()

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
        return {"student": "students", "entry": "assessments", "subject": "subjects"}.get(key, key)

    def _leave_ok(self) -> bool:
        page = self.pages.get(self.current)
        return page.can_leave() if hasattr(page, "can_leave") else True

    # ---------------- history ----------------
    def _context(self) -> dict:
        return {"class_id": self.class_id, "subject_id": self.subject_id, "student_id": self.student_id,
                "assessment_id": self.assessment_id, "term_id": self.term_id}

    def _remember(self) -> None:
        """Record the page being left, with what it was showing, so back returns to exactly that."""
        page = self.pages.get(self.current)
        title = page.title.text() if page is not None else self.current
        if self.history and self.history[-1][0] == self.current and self.history[-1][1] == self._context():
            return
        self.history.append((self.current, self._context(), title))
        del self.history[:-30]

    def back_target(self) -> str:
        """The name shown on a back button: the page that would be returned to."""
        return self.history[-1][2] if self.history else "Overview"

    def _still_valid(self, key: str, ctx: dict) -> bool:
        if key == "student":
            return ctx["student_id"] in self.gb.students
        if key == "entry":
            return ctx["assessment_id"] in self.gb.by_id
        if key == "subject":
            return ctx["subject_id"] in self.gb.subjects
        return True

    def go_back(self) -> None:
        if not self._leave_ok():
            return
        while self.history:
            key, ctx, _ = self.history.pop()
            if ctx["term_id"] != self.term_id:               # the page was viewed in another term
                self.term_id = ctx["term_id"]
                self.gb = Gradebook.load(self.term_id)
                self._fill_terms()
            self.class_id, self.subject_id = ctx["class_id"], ctx["subject_id"]
            self.student_id, self.assessment_id = ctx["student_id"], ctx["assessment_id"]
            if self._still_valid(key, ctx):                  # skip pages whose record has gone
                self.show_page(key, remember=False)
                return
        self.show_page("dashboard", remember=False)

    def show_page(self, key: str, remember: bool = True) -> None:
        if remember and key != self.current:
            self._remember()
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

    def open_subject(self, subject_id: int) -> None:
        if subject_id is not None and self._leave_ok():
            self.subject_id = subject_id
            self.show_page("subject")

    def open_help(self, topic: str | None = None) -> None:
        """F1 from anywhere: help opens at the topic for the screen you were on."""
        page = self.current
        if not self._leave_ok():
            return
        self.show_page("help")
        helper = self.pages["help"]
        helper.open_topic(topic) if topic else helper.open_for_page(page)

    def find_student(self) -> None:
        """Ctrl+K from anywhere."""
        from .quick_find import QuickFind
        QuickFind(self).exec()

    def open_assessment(self, assessment_id: int, tab: str | None = None) -> None:
        if assessment_id is not None and self._leave_ok():
            self.assessment_id = assessment_id
            self.pages["entry"].start_tab = tab
            self.show_page("entry")

    # ---------------- shared state ----------------
    def reload(self) -> None:
        """Re-read the database after a change and redraw the current page."""
        self.gb = Gradebook.load(self.term_id)
        self._fill_terms()
        self.pages[self.current].refresh()

    def closeEvent(self, event):
        """Back up once a day on the way out, unless it is switched off in Settings."""
        if not self._leave_ok():
            event.ignore()
            return
        s = self.gb.settings
        today = dt.date.today().isoformat()
        if s.get("auto_backup", True) and s.get("last_backup", "")[:10] != today and BK.tools_available() and self.gb.students:
            try:
                QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                path = BK.backup(s.get("backup_dir") or None, "onclose")
                BK.prune(20, s.get("backup_dir") or None)
                R.save_settings({"last_backup": dt.datetime.now().isoformat(timespec="seconds")})
                get_logger("app").info("automatic backup on close: %s", path)
            except Exception:  # noqa: BLE001 - never block closing over a backup
                get_logger("app").exception("automatic backup failed")
            finally:
                QGuiApplication.restoreOverrideCursor()
        event.accept()

    def class_items(self) -> list[tuple[str, int]]:
        return [(c.name, c.id) for c in sorted(self.gb.classes.values(), key=lambda c: c.name.lower())]

    def ensure_class(self) -> int | None:
        ids = [cid for _, cid in self.class_items()]
        if self.class_id not in ids:
            self.class_id = ids[0] if ids else None
        return self.class_id