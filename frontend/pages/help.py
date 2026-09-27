# /markbook/frontend/pages/help.py
"""Help and About: searchable topics on the left, the text on the right.

F1 from any screen opens this at the topic for that screen.
"""
from __future__ import annotations

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QTextBrowser

from backend import about, log
from backend.paths import icon_path

from .. import theme
from ..help_topics import TOPICS, Topic, for_page, search
from ..widgets import Page, info, label, panel, row

ABOUT_KEY = "__about__"


def _about_topic() -> Topic:
    b = about.build()
    rows = "".join(f"<tr><td style='padding:2px 14px 2px 0;color:{theme.MUTED}'>{k}</td>"
                   f"<td style='padding:2px 0'>{v}</td></tr>"
                   for k, v in [("Version", f"{b.version} ({about.frozen_note()})"), ("Python", b.python),
                                ("Qt", b.qt), ("System", b.system), ("Database", b.database),
                                ("Schema", b.revision), ("Log file", log.log_path())])
    return Topic(
        ABOUT_KEY, f"About {about.APP_NAME}", about.TAGLINE,
        f"<p style='font-size:13pt'><b>{about.APP_NAME} {about.VERSION}</b> — {about.TAGLINE}</p>"
        f"<p>{about.DESCRIPTION}</p>"
        f"<p><b>Made by {about.TEAM}.</b> The source, releases and issue tracker are on GitHub at "
        f"<a href='{about.GITHUB_URL}'>{about.GITHUB_URL}</a>. Problems and requests are welcome "
        f"there — the build details below are what a report needs.</p>"
        "<p><b>Built with</b> Python, PyQt6, PostgreSQL, SQLAlchemy and Alembic, with ReportLab for "
        "the PDFs, openpyxl for Excel and matplotlib for the charts.</p>"
        f"<p><b>This build</b></p><table>{rows}</table>",
        keywords=["about", "version", "credits", about.TEAM.lower(), "github", "licence", "license", "contact"],
    )


class HelpPage(Page):
    def __init__(self, app):
        super().__init__(app, "Help", f"{about.APP_NAME} {about.VERSION} · {about.TAGLINE}")
        self.topics: list[Topic] = []
        self._about = _about_topic()

        github = QPushButton("Open on GitHub")
        github.clicked.connect(lambda _=False: QDesktopServices.openUrl(QUrl(about.GITHUB_URL)))
        report = QPushButton("Report a problem")
        report.clicked.connect(lambda _=False: QDesktopServices.openUrl(QUrl(about.ISSUES_URL)))
        copy = QPushButton("Copy build details")
        copy.clicked.connect(lambda _=False: self.copy_build())
        for w in (copy, report, github):
            self.actions.addWidget(w)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search help — try 'division', 'backup' or 'absent'")
        self.search.setFixedWidth(290)
        self.search.textChanged.connect(self._filter)
        self.list = QListWidget()
        self.list.setObjectName("helpList")
        self.list.setFixedWidth(290)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._show)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.setObjectName("helpText")

        split = QHBoxLayout()
        split.setSpacing(14)
        split.addWidget(self.list)
        split.addWidget(self.text, 1)
        self.body.addWidget(panel(row(self.search, None), split,
                                  label(f"Made by {about.TEAM} · {about.GITHUB_URL} · press F1 on any screen to come "
                                        "straight here.", "muted", wrap=True)))

    # ---------------- list ----------------
    def _filter(self, _=None):
        query = self.search.text().strip()
        found = search(query)
        show_about = (not query) or self._about.matches(query)
        self.topics = found + ([self._about] if show_about else [])
        self.list.blockSignals(True)
        self.list.clear()
        for t in self.topics:
            item = QListWidgetItem(t.title)
            item.setToolTip(t.summary)
            item.setData(Qt.ItemDataRole.UserRole, t.key)
            self.list.addItem(item)
        self.list.blockSignals(False)
        if self.topics:
            self.list.setCurrentRow(0)
        else:
            self.text.setHtml(f"<p style='color:{theme.MUTED}'>Nothing matches “{query}”. "
                              "Try a single word, such as <b>division</b>, <b>backup</b> or <b>absent</b>.</p>")

    def _show(self, index: int):
        if 0 <= index < len(self.topics):
            t = self.topics[index]
            self.text.setHtml(f"<h2 style='color:{theme.INK}'>{t.title}</h2>"
                              f"<p style='color:{theme.MUTED}'><i>{t.summary}</i></p>{t.body}")
            self.text.verticalScrollBar().setValue(0)

    # ---------------- entry points ----------------
    def open_topic(self, key: str):
        """Show one topic, clearing any search that would hide it."""
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._filter()
        for i, t in enumerate(self.topics):
            if t.key == key:
                self.list.setCurrentRow(i)
                return
        self.list.setCurrentRow(0)

    def open_for_page(self, page: str | None):
        self.open_topic(for_page(page))

    def open_about(self):
        self.open_topic(ABOUT_KEY)

    def copy_build(self):
        text = f"{about.APP_NAME} {about.VERSION} ({about.frozen_note()})\n{about.build().as_text()}\nLog: {log.log_path()}"
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        info(self, "Build details copied — paste them into your problem report.")

    def refresh(self):
        self._about = _about_topic()            # the schema revision can change while running
        if not self.topics:
            self._filter()
        if icon_path():
            self.subtitle.setText(f"{about.APP_NAME} {about.VERSION} · {about.TAGLINE} · by {about.TEAM}")


__all__ = ["HelpPage", "TOPICS"]