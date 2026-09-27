# /markbook/frontend/splash.py
"""The window shown while Markbook starts: icon, name, what it is doing, and a rotating tip.

Startup does real work — migrating the database, reading a term's marks, building the screens —
so it is worth showing progress rather than an empty desktop.
"""
from __future__ import annotations

import random

from PyQt6.QtCore import QElapsedTimer, QEventLoop, QPropertyAnimation, Qt, QTimer, pyqtProperty
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QLabel, QProgressBar, QVBoxLayout, QWidget)

from backend import about
from backend.paths import icon_path

from . import theme

TIPS = [
    "Press Ctrl+K anywhere to jump straight to a student.",
    "Mark an exam question by question to see which topics are weak.",
    "Each term keeps its own averages, positions and divisions.",
    "Attendance is taken against the lessons in your timetable.",
    "Double-click a subject to see every test and the totals.",
    "Marks you type are autosaved, so a power cut costs nothing.",
    "Removing a student archives them — their marks are kept.",
    "Every change to a mark records who made it, and when.",
    "Report cards draft their own comments from the results.",
    "Set a target grade and see who is falling behind it.",
    "Sheets exported to Excel import straight back again.",
    "Results & reports can combine every term into a year mark.",
    "Markbook backs itself up each day when you close it.",
    "A paper can have an 'answer any 2 of 3' section.",
    "Import a class list from Excel: name, reg. number, phone.",
    "Alt+Left goes back to wherever you came from.",
    "Tag tests with topics to see what the class finds hardest.",
]


class Splash(QWidget):
    def __init__(self, tips: list[str] | None = None):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(620, 380)
        self.setObjectName("splash")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)      # so the rounded corners show
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(38)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)
        self._tips = list(tips or TIPS)
        random.shuffle(self._tips)
        self._tip = 0
        self._fade_value = 1.0
        self._clock = QElapsedTimer()
        self._clock.start()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 16)        # room for the shadow to fall into
        card = QFrame()
        card.setObjectName("splashCard")
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(36, 30, 36, 24)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = icon_path()
        if path:
            # QIcon picks the best frame out of a multi-size .ico; QPixmap would take the first
            pixmap = QIcon(str(path)).pixmap(96, 96)
            if not pixmap.isNull():
                self.icon.setPixmap(pixmap)
        lay.addStretch(1)
        lay.addWidget(self.icon)
        title = QLabel(about.APP_NAME)
        title.setObjectName("splashTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        self.what = QLabel(f"version {about.VERSION}  ·  by {about.TEAM}")
        self.what.setObjectName("splashWhat")
        self.what.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.what)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        lay.addWidget(self.bar)
        lay.addStretch(1)
        self.tip = QLabel()
        self.tip.setObjectName("splashTip")
        self.tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tip.setWordWrap(False)                   # one line, like a loading tip in a game
        lay.addWidget(self.tip)
        self.tip.setText(self._elided(self._tips[0]) if self._tips else "")

        self.rotation = QTimer(self)
        self.rotation.setInterval(3500)
        self.rotation.timeout.connect(self.next_tip)
        self.rotation.start()
        self._centre()

    def _centre(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            middle = screen.availableGeometry().center()
            self.move(middle.x() - self.width() // 2, middle.y() - self.height() // 2)

    # ---------------- tips ----------------
    def _get_fade(self) -> float:
        return self._fade_value

    def _set_fade(self, value: float) -> None:
        """Fade by colour, not by a graphics effect: Qt will not paint a child effect
        inside the parent's drop shadow, and the tip would simply vanish."""
        self._fade_value = value
        base = QColor(theme.MUTED)
        mix = QColor(theme.SURFACE)
        blend = lambda a, b: int(b + (a - b) * value)
        self.tip.setStyleSheet("#splashTip { color: rgb(%d, %d, %d); }" % (
            blend(base.red(), mix.red()), blend(base.green(), mix.green()), blend(base.blue(), mix.blue())))

    fade = pyqtProperty(float, fget=_get_fade, fset=_set_fade)

    def next_tip(self) -> None:
        if len(self._tips) < 2:
            return
        self._tip = (self._tip + 1) % len(self._tips)
        text = self._tips[self._tip]
        out = QPropertyAnimation(self, b"fade", self)
        out.setDuration(220)
        out.setStartValue(1.0)
        out.setEndValue(0.0)

        def swap():
            self.tip.setText(self._elided(text))
            back = QPropertyAnimation(self, b"fade", self)
            back.setDuration(300)
            back.setStartValue(0.0)
            back.setEndValue(1.0)
            back.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
            self._animation = back
        out.finished.connect(swap)
        out.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._out = out

    def _elided(self, text: str) -> str:
        metrics = self.tip.fontMetrics()
        return metrics.elidedText(text, Qt.TextElideMode.ElideRight, self.width() - 100)

    # ---------------- progress ----------------
    def step(self, what: str, percent: int) -> None:
        """Say what is happening and how far along it is; repaint straight away."""
        self.what.setText(what)
        self.bar.setValue(max(0, min(100, percent)))
        app = QApplication.instance()
        if app:
            app.processEvents()

    def finish(self, window=None, minimum_ms: int = 1200) -> None:
        """Stay up long enough to be read, then hand over to the main window."""
        self.step("Ready", 100)
        app = QApplication.instance()
        while app is not None and self._clock.elapsed() < minimum_ms:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 40)
        self.rotation.stop()
        if window is not None:
            window.show()
            window.raise_()
            window.activateWindow()
        self.close()