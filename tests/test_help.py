# /markbook/tests/test_help.py
"""The help topics, the About details, and F1 landing on the right page."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from backend import about  # noqa: E402
from frontend import help_topics  # noqa: E402

_app = None            # a QApplication must outlive the tests, or Qt aborts


@pytest.fixture
def window(monkeypatch):
    global _app
    from PyQt6.QtWidgets import QApplication, QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"warning shown: {a[2]}"))
    _app = QApplication.instance() or QApplication([])
    from backend import seed
    from frontend import theme
    from frontend.main_window import MainWindow
    theme.apply(_app)
    seed.add_sample(seed=31)
    yield MainWindow()
    seed.remove_sample()


def test_every_topic_is_complete_and_points_at_a_real_page():
    from frontend.main_window import NAV
    pages = {key for key, _ in NAV}
    assert len(help_topics.TOPICS) >= 12
    keys = [t.key for t in help_topics.TOPICS]
    assert len(keys) == len(set(keys))                       # no duplicate topics
    for t in help_topics.TOPICS:
        assert t.title and t.summary and len(t.body) > 200   # each one says something
        assert t.keywords, f"{t.key} has no search words"
        assert t.page is None or t.page in pages, f"{t.key} points at a page that does not exist"


def test_search_puts_the_obvious_topic_first():
    assert help_topics.search("division")[0].key == "results"
    assert help_topics.search("backup")[0].key == "safety"
    assert help_topics.search("timetable")[0].key == "timetable"
    assert help_topics.search("import excel")[0].key == "io"
    assert help_topics.search("zzzznothing") == []
    assert len(help_topics.search("")) == len(help_topics.TOPICS)


def test_about_reports_the_build_and_the_team():
    assert about.TEAM == "Mencorium"
    assert about.GITHUB_URL == "https://github.com/mencorium/markbook"
    build = about.build()
    assert build.version == about.VERSION and build.python and build.qt
    assert "PostgreSQL" in build.database
    assert "password" not in build.database.lower()          # never leak the connection password
    text = build.as_text()
    assert about.APP_NAME in text and build.revision in text


def test_f1_opens_help_at_the_topic_for_the_screen(window):
    w = window
    for page, expected in [("students", "students"), ("timetable", "timetable"),
                           ("results", "results"), ("io", "io"), ("settings", "terms")]:
        w.show_page(page)
        w.open_help()
        assert w.current == "help"
        helper = w.pages["help"]
        assert helper.topics[helper.list.currentRow()].key == expected


def test_about_section_names_the_team_and_this_build(window):
    w = window
    w.show_page("help")
    helper = w.pages["help"]
    helper.open_about()
    shown = helper.text.toPlainText()
    assert about.TEAM in shown and about.GITHUB_URL in shown
    assert about.VERSION in shown and "Log file" in shown

    helper.search.setText("mencorium")                       # findable by the team name
    assert [t.title for t in helper.topics] == [f"About {about.APP_NAME}"]
    helper.search.setText("zzzznothing")
    assert helper.topics == [] and "Nothing matches" in helper.text.toPlainText()