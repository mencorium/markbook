# /markbook/frontend/pages/settings.py
"""School details, report-card settings, per-class grading and sample data."""
from __future__ import annotations

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QComboBox, QDateEdit, QDoubleSpinBox, QFormLayout, QLineEdit, QPushButton, QSpinBox, QWidget

from backend import seed
from backend.config import get_config
from backend.grading import LEVEL_LABELS, PRESETS
from backend.services import records as R

from ..dialogs import ScaleDialog
from ..widgets import Page, Table, confirm, fill_combo, info, label, panel, row, safe


class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Settings")
        # ---- school ----
        w = QWidget()
        f = QFormLayout(w)
        self.school, self.term, self.head = QLineEdit(), QLineEdit(), QLineEdit()
        self.school.setPlaceholderText("e.g. Mbeya Secondary School")
        self.term.setPlaceholderText("e.g. Term 1, 2026")
        self.next_term = QDateEdit()
        self.next_term.setCalendarPopup(True)
        self.next_term.setSpecialValueText("not set")
        self.next_term.setMinimumDate(QDate(2000, 1, 1))
        self.ca = QSpinBox()
        self.ca.setRange(0, 100)
        self.ca.setSuffix("%")
        for lab, x in [("School name", self.school), ("Term", self.term), ("Head teacher", self.head), ("Next term begins", self.next_term),
                       ("Tests count for", self.ca)]:
            f.addRow(lab, x)
        f.addRow("", label("Final mark = tests share + exam share. With no exam yet, the final mark is the test average.", "muted", wrap=True))
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.clicked.connect(lambda _=False: self.save_settings())
        self.body.addWidget(panel(w, row(save, None), title="School & report cards"))
        # ---- classes ----
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(lambda _: self._load_class())
        cw = QWidget()
        cf = QFormLayout(cw)
        self.c_name, self.c_teacher = QLineEdit(), QLineEdit()
        self.c_level = QComboBox()
        fill_combo(self.c_level, [(v, k) for k, v in LEVEL_LABELS.items()])
        self.c_level.currentIndexChanged.connect(lambda _: self._level_changed())
        self.c_pass = QDoubleSpinBox()
        self.c_pass.setRange(0, 100)
        self.c_pass.setSuffix("%")
        self.b_scale = QPushButton("Edit custom grade scale…")
        self.b_scale.clicked.connect(lambda _=False: self.edit_scale())
        self.scale_view = Table(["Grade", "From", "Points"])
        for lab, x in [("Class", self.cls), ("Class name", self.c_name), ("Class teacher", self.c_teacher), ("Grading", self.c_level), ("Pass mark", self.c_pass)]:
            cf.addRow(lab, x)
        cf.addRow("", self.b_scale)
        csave, cdel = QPushButton("Save class"), QPushButton("Delete class")
        csave.setObjectName("primary")
        cdel.setObjectName("danger")
        csave.clicked.connect(lambda _=False: self.save_class())
        cdel.clicked.connect(lambda _=False: self.delete_class())
        self.custom_rows: list | None = None
        self.body.addWidget(panel(cw, self.scale_view, row(csave, cdel, None),
                                  label("NECTA presets: A-Level division from best 3 principal subjects (subsidiaries excluded); O-Level from best 7 subjects.", "muted", wrap=True),
                                  title="Classes & grading"))
        # ---- data ----
        add, rem = QPushButton("Add sample class"), QPushButton("Remove sample data")
        rem.setObjectName("danger")
        add.clicked.connect(lambda _=False: self.sample(True))
        rem.clicked.connect(lambda _=False: self.sample(False))
        self.db_label = label("", "muted", wrap=True)
        self.body.addWidget(panel(self.db_label, row(add, rem, None), title="Data"))
        self.body.addStretch(1)

    def refresh(self):
        s = self.app.gb.settings
        self.school.setText(s.get("school", ""))
        self.term.setText(s.get("term", ""))
        self.head.setText(s.get("head_teacher", ""))
        nt = QDate.fromString(s.get("next_term") or "", "yyyy-MM-dd")
        self.next_term.setDate(nt if nt.isValid() else self.next_term.minimumDate())
        self.ca.setValue(int(s.get("ca_weight", 40)))
        fill_combo(self.cls, self.app.class_items(), self.app.ensure_class())
        self._load_class()
        url = get_config().database_url
        self.db_label.setText(f"Data is stored in PostgreSQL at {url.rsplit('@', 1)[-1]}. Back it up with pg_dump. "
                              f"The sample class ('{seed.SAMPLE_CLASS}') can be removed at any time without touching your own data.")

    def _load_class(self):
        c = self.app.gb.classes.get(self.cls.currentData())
        for wdg in (self.c_name, self.c_teacher, self.c_level, self.c_pass):
            wdg.setEnabled(c is not None)
        if not c:
            return
        self.c_name.setText(c.name)
        self.c_teacher.setText(c.teacher)
        self.custom_rows = c.scale
        fill_combo(self.c_level, [(v, k) for k, v in LEVEL_LABELS.items()], c.level)
        self.c_pass.setValue(c.pass_mark if c.pass_mark is not None else self._default_pass(c.level))
        self._show_scale()

    def _default_pass(self, level):
        return PRESETS[level]["pass_mark"] if level in PRESETS else 40

    def _level_changed(self):
        lvl = self.c_level.currentData()
        self.c_pass.setValue(self._default_pass(lvl))
        self._show_scale()

    def _show_scale(self):
        from backend.grading import make_scale
        lvl = self.c_level.currentData() or "A"
        self.b_scale.setVisible(lvl == "custom")
        sc = make_scale(lvl, self.c_pass.value(), self.custom_rows)
        self.scale_view.set_rows([[r.grade, f"{r.min:g}%", "" if r.points is None else r.points] for r in sc.rows], center_from=0, fit_height=True)

    def edit_scale(self):
        d = ScaleDialog(self, self.custom_rows)
        if d.exec():
            self.custom_rows = d.rows()
            self._show_scale()

    @safe
    def save_settings(self):
        nt = self.next_term.date()
        R.save_settings({"school": self.school.text().strip(), "term": self.term.text().strip(), "head_teacher": self.head.text().strip(),
                         "next_term": "" if nt == self.next_term.minimumDate() else nt.toString("yyyy-MM-dd"), "ca_weight": self.ca.value()})
        self.app.reload()
        info(self, "Settings saved.")

    @safe
    def save_class(self):
        cid = self.cls.currentData()
        if cid is None:
            return
        lvl = self.c_level.currentData()
        R.save_class(cid, name=self.c_name.text(), level=lvl, pass_mark=self.c_pass.value(), teacher=self.c_teacher.text(),
                     scale=self.custom_rows if lvl == "custom" else None)
        self.app.reload()
        info(self, "Class saved.")

    @safe
    def delete_class(self):
        cid = self.cls.currentData()
        if cid is not None and confirm(self, f"Delete {self.app.gb.class_name(cid)} and its assessments?"):
            R.delete_class(cid)
            self.app.class_id = None
            self.app.reload()

    @safe
    def sample(self, add: bool):
        if add:
            seed.add_sample()
        elif confirm(self, "Remove the sample class and everything in it?"):
            seed.remove_sample()
        self.app.reload()