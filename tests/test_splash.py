# /markbook/tests/test_splash.py
"""The start-up window: progress, and the rotating tip."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

_app = None            # a QApplication must outlive the tests, or Qt aborts


@pytest.fixture
def app():
    global _app
    from PyQt6.QtWidgets import QApplication
    from frontend import theme
    _app = QApplication.instance() or QApplication([])
    theme.apply(_app)
    return _app


def _spin(app, ms: int):
    from PyQt6.QtCore import QElapsedTimer, QEventLoop
    clock = QElapsedTimer()
    clock.start()
    while clock.elapsed() < ms:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 15)


def test_splash_shows_the_icon_name_and_progress(app):
    from frontend.splash import Splash
    splash = Splash()
    splash.show()
    app.processEvents()
    assert not splash.icon.pixmap().isNull()                 # the app icon, at its best size
    assert splash.bar.value() == 0

    splash.step("Opening the database…", 25)
    assert splash.what.text() == "Opening the database…" and splash.bar.value() == 25
    splash.step("Done", 500)
    assert splash.bar.value() == 100                         # clamped, never past the end
    splash.close()


def test_tip_changes_and_always_fits_on_one_line(app):
    from frontend.splash import TIPS, Splash
    splash = Splash()
    splash.show()
    app.processEvents()

    metrics = splash.tip.fontMetrics()
    room = splash.width() - 100
    assert all(metrics.horizontalAdvance(t) <= room for t in TIPS)   # no tip is cut off
    assert not splash.tip.wordWrap()

    seen = {splash.tip.text()}
    for _ in range(3):
        splash.next_tip()
        _spin(app, 700)
        seen.add(splash.tip.text())
    assert len(seen) == 4                                    # a different tip each time
    assert splash.fade == 1.0                                # and fully faded back in
    splash.close()


def test_finish_hands_over_to_the_window(app):
    from PyQt6.QtWidgets import QWidget
    from frontend.splash import Splash
    splash = Splash()
    splash.show()
    window = QWidget()
    splash.finish(window, minimum_ms=0)
    assert not splash.isVisible() and window.isVisible()
    assert not splash.rotation.isActive()                    # nothing left ticking
    window.close()