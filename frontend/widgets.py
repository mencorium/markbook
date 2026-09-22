# /markbook/frontend/widgets.py
"""Reusable widgets: page scaffold, stat strip, tables, chart canvas, message helpers."""
from __future__ import annotations

import functools

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QScrollArea,
                             QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from backend.log import get as get_logger
from backend.services.backup import BackupError
from backend.services.imports import ImportError_
from backend.services.records import ValidationError

from . import theme


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    if not wrap:
        # keep a one-line label at its natural height: otherwise spare space in a
        # column is handed to the label and it pushes the widgets below it down
        w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    return w


def panel(*widgets, title: str | None = None, layout: str = "v", stretch_end: bool = False) -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    lay = QVBoxLayout(f) if layout == "v" else QHBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    if title:
        lay.addWidget(label(title, "h2"))
    for w in widgets:
        lay.addWidget(w) if isinstance(w, QWidget) else lay.addLayout(w)
    if stretch_end:                 # spare height collects at the bottom, not around the contents
        lay.addStretch(1)
    return f


def row(*items, stretch_end: bool = False, spacing: int = 8) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setSpacing(spacing)
    for it in items:
        if it is None:
            h.addStretch(1)
        elif isinstance(it, QWidget):
            h.addWidget(it)
        else:
            h.addLayout(it)
    if stretch_end:
        h.addStretch(1)
    return h


class Page(QWidget):
    """Scrollable page with a title row. Subclasses fill self.body and implement refresh()."""
    def __init__(self, app, title: str, subtitle: str = "", actions_below: bool = False):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("page")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(28, 22, 28, 28)
        self.body.setSpacing(14)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        self.title = label(title, "title")
        self.subtitle = label(subtitle, "subtitle", wrap=True)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)      # the title column takes the spare width, so subtitles wrap late
        self.actions = QHBoxLayout()
        self.body.addLayout(head)
        if actions_below:                 # many buttons: give them their own row so the page never scrolls sideways
            self.actions.addStretch(0)
            below = QHBoxLayout()
            below.addLayout(self.actions)
            below.addStretch(1)
            self.body.addLayout(below)
        else:
            head.addLayout(self.actions)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def refresh(self) -> None:          # pragma: no cover - overridden
        pass


class StatStrip(QWidget):
    def __init__(self):
        super().__init__()
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(10)

    def set(self, stats: list[tuple[str, str]]) -> None:
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for value, text in stats:
            f = QFrame()
            f.setObjectName("stat")
            v = QVBoxLayout(f)
            v.setContentsMargins(14, 10, 14, 10)
            v.addWidget(label(value, "statValue"))
            v.addWidget(label(text, "statLabel", wrap=True))
            self.lay.addWidget(f, 1)


class Table(QTableWidget):
    """Read-only table by default. set_rows() fills it; row ids are stored for double-click navigation."""
    def __init__(self, headers: list[str], stretch: int | None = None, editable: bool = False, multi: bool = False):
        super().__init__(0, len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        if multi:
            self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        if not editable:
            self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if stretch is not None:
            hh.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
        self.ids: list = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_headers(self, headers: list[str], stretch: int | None = None) -> None:
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        hh = self.horizontalHeader()
        for c in range(len(headers)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch if c == stretch else QHeaderView.ResizeMode.ResizeToContents)

    def set_rows(self, rows: list[list], ids: list | None = None, center_from: int = 1, colors: dict | None = None,
                 fit_height: bool = False, left: tuple = ()) -> None:
        self.clear_cell_widgets()
        self.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, v in enumerate(values):
                it = QTableWidgetItem("" if v is None else str(v))
                if c >= center_from and c not in left:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if colors and (r, c) in colors:
                    fg, bg = colors[(r, c)]
                    if fg:
                        it.setForeground(QColor(fg))
                        f = QFont()
                        f.setBold(True)
                        it.setFont(f)
                    if bg:
                        it.setBackground(QColor(bg))
                self.setItem(r, c, it)
        self.ids = ids or []
        if fit_height:
            self.fit()

    def clear_cell_widgets(self) -> None:
        """Hide and drop embedded widgets (combos) before redrawing, so stale ones are never painted."""
        for r in range(self.rowCount()):
            for c in range(self.columnCount()):
                w = self.cellWidget(r, c)
                if w is not None:
                    w.hide()
                    self.removeCellWidget(r, c)
        self.setRowCount(0)

    def fit(self, max_rows: int = 18) -> None:
        h = self.horizontalHeader().height() + 4 + sum(self.rowHeight(r) for r in range(min(self.rowCount(), max_rows)))
        self.setMinimumHeight(min(h, 620))
        self.setMaximumHeight(h if self.rowCount() <= max_rows else 16777215)

    def current_id(self):
        r = self.currentRow()
        return self.ids[r] if 0 <= r < len(self.ids) else None

    def selected_ids(self) -> list:
        """Ids of every selected row, in the order shown."""
        return [self.ids[r] for r in sorted({i.row() for i in self.selectedIndexes()}) if r < len(self.ids)]


class Chart(FigureCanvasQTAgg):
    def __init__(self, height: float = 2.8):
        self.fig = Figure(figsize=(6, height), dpi=100, facecolor="white")
        super().__init__(self.fig)
        self.setMinimumHeight(int(height * 90))

    def draw_with(self, fn, bottom: float = 0.2) -> None:
        """bottom is kept for callers that need extra room under the axes (rotated labels, legends below)."""
        self.fig.clear()
        self.fig.set_layout_engine("constrained", h_pad=0.03, w_pad=0.03)   # sizes margins from the real text
        ax = self.fig.add_subplot(111)
        ok = fn(ax)
        if ok is False:
            ax.set_axis_off()
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center", color=theme.MUTED)
        self.draw_idle()


def fill_combo(combo: QComboBox, items: list[tuple[str, object]], current=None, blank: str | None = None) -> None:
    combo.blockSignals(True)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    combo.setMinimumContentsLength(8)
    combo.clear()
    if blank is not None:
        combo.addItem(blank, None)
    for text, data in items:
        combo.addItem(text, data)
    if current is not None:
        i = combo.findData(current)
        if i >= 0:
            combo.setCurrentIndex(i)
    combo.blockSignals(False)


def info(parent, text: str) -> None:
    QMessageBox.information(parent, "Markbook", text)


def error(parent, text: str) -> None:
    QMessageBox.warning(parent, "Markbook", text)


def confirm(parent, text: str) -> bool:
    return QMessageBox.question(parent, "Markbook", text) == QMessageBox.StandardButton.Yes


def safe(fn):
    """Show expected problems as a message; log anything unexpected and tell the user where the log is."""
    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        try:
            return fn(self, *a, **k)
        except (ValidationError, ImportError_, BackupError) as e:
            get_logger("ui").info("%s refused: %s", fn.__qualname__, e)
            error(self, str(e))
        except Exception as e:  # noqa: BLE001
            from backend.log import log_path
            get_logger("ui").exception("unexpected error in %s", fn.__qualname__)
            error(self, f"Something went wrong: {e}\n\nDetails were written to {log_path()}")
    return wrapper


def fmt(v, suffix: str = "") -> str:
    return "–" if v is None else f"{v:.1f}".rstrip("0").rstrip(".") + suffix


def heat(v: float | None) -> str | None:
    return None if v is None else theme.HEAT_LOW if v < 40 else theme.HEAT_MID if v < 70 else theme.HEAT_HIGH