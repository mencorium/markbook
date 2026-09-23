# /markbook/frontend/pages/settings.py
"""School details, report-card settings, per-class grading and sample data."""
from __future__ import annotations

from PyQt6.QtCore import QDate, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFileDialog, QFormLayout, QLineEdit, QPushButton,
                             QSpinBox, QWidget)

from backend import audit, log, migrate, seed
from backend.config import get_config
from backend.grading import LEVEL_LABELS, PRESETS
from backend.services import backup as BK
from backend.services import records as R
from backend.services import terms as T

import datetime as dt
from pathlib import Path

from ..dialogs import ClassDialog, ScaleDialog, StartTermDialog, TermDialog
from ..widgets import Page, Table, confirm, error, fill_combo, info, label, panel, row, safe


class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Settings")
        # ---- school ----
        w = QWidget()
        f = QFormLayout(w)
        self.school, self.head = QLineEdit(), QLineEdit()
        self.school.setPlaceholderText("e.g. Mbeya Secondary School")
        self.next_term = QDateEdit()
        self.next_term.setCalendarPopup(True)
        self.next_term.setSpecialValueText("not set")
        self.next_term.setMinimumDate(QDate(2000, 1, 1))
        self.who = QLineEdit()
        self.ca = QSpinBox()
        self.ca.setRange(0, 100)
        self.ca.setSuffix("%")
        for lab, x in [("School name", self.school), ("Head teacher", self.head), ("Next term begins", self.next_term),
                       ("Tests count for", self.ca), ("Changes recorded as", self.who)]:
            f.addRow(lab, x)
        f.addRow("", label("Final mark = tests share + exam share. With no exam yet, the final mark is the test average. "
                           "The name is written against every change on the Activity page.", "muted", wrap=True))
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.clicked.connect(lambda _=False: self.save_settings())
        self.body.addWidget(panel(w, row(save, None), title="School & report cards"))
        # ---- terms ----
        self.terms = Table(["Term", "Year", "Starts", "Ends", "Weight", "Assessments", "Registers"], stretch=0)
        self.terms.doubleClicked.connect(lambda: self.edit_term())
        add_t, edit_t, del_t = QPushButton("Add term"), QPushButton("Edit"), QPushButton("Delete")
        start_t = QPushButton("Start the next term…")
        start_t.setObjectName("primary")
        del_t.setObjectName("danger")
        for b, fn in [(add_t, self.add_term), (edit_t, self.edit_term), (del_t, self.delete_term), (start_t, self.start_term)]:
            b.clicked.connect(lambda _=False, f=fn: f())
        self.terms_note = label("", "notice", wrap=True)
        self.body.addWidget(panel(self.terms_note, self.terms, row(add_t, edit_t, del_t, None, start_t),
                                  label("Each term has its own averages, positions and divisions. Marks land in the term their date falls in. "
                                        "Weight decides how much a term counts towards the annual result. "
                                        "Starting the next term also moves each class on according to its rule.", "muted", wrap=True),
                                  title="Terms & academic years", stretch_end=True))

        # ---- classes ----
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(lambda _: self._load_class())
        self.b_new = QPushButton("Add class")
        self.b_new.clicked.connect(lambda _=False: self.add_class())
        cw = QWidget()
        cf = QFormLayout(cw)
        self.c_name, self.c_teacher = QLineEdit(), QLineEdit()
        self.c_level = QComboBox()
        fill_combo(self.c_level, [(v, k) for k, v in LEVEL_LABELS.items()])
        self.c_level.currentIndexChanged.connect(lambda _: self._level_changed())
        self.c_pass = QDoubleSpinBox()
        self.c_pass.setRange(0, 100)
        self.c_pass.setSuffix("%")
        self.c_rollover = QComboBox()
        for key, text in T.ROLLOVER.items():
            self.c_rollover.addItem(text, key)
        self.b_scale = QPushButton("Edit custom grade scale…")
        self.b_scale.clicked.connect(lambda _=False: self.edit_scale())
        self.scale_view = Table(["Grade", "From", "Points"])
        for lab, x in [("Class", row(self.cls, self.b_new, None)), ("Class name", self.c_name), ("Class teacher", self.c_teacher),
                       ("Grading", self.c_level), ("Pass mark", self.c_pass), ("At the end of the year", self.c_rollover)]:
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
        # ---- backups ----
        self.auto = QCheckBox("Back up automatically when I close Markbook (once a day)")
        self.auto.toggled.connect(lambda on: self._save_backup_prefs())
        self.folder = QLineEdit()
        self.folder.setReadOnly(True)
        browse = QPushButton("Change folder…")
        browse.clicked.connect(lambda _=False: self.pick_folder())
        open_folder = QPushButton("Open folder")
        open_folder.clicked.connect(lambda _=False: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folder()))))
        now = QPushButton("Back up now")
        now.setObjectName("primary")
        now.clicked.connect(lambda _=False: self.backup_now())
        self.b_locate = QPushButton("Locate PostgreSQL tools…")
        self.b_locate.clicked.connect(lambda _=False: self.locate_tools())
        self.b_restore = QPushButton("Restore selected backup")
        self.b_restore.setObjectName("danger")
        self.b_restore.clicked.connect(lambda _=False: self.restore_selected())
        self.backup_status = label("", "notice", wrap=True)
        self.backups = Table(["When", "File", "Size"], stretch=1)
        self.body.addWidget(panel(self.backup_status, self.auto, row(label("Folder"), self.folder, browse, open_folder),
                                  row(now, self.b_restore, self.b_locate, None), self.backups,
                                  label("A backup is one .dump file holding everything: students, marks, attendance and settings. "
                                        "Restoring replaces the current contents of the database with that file. The newest 20 backups are kept.",
                                        "muted", wrap=True),
                                  title="Backups", stretch_end=True))
        # ---- data & logs ----
        add, rem = QPushButton("Add sample class"), QPushButton("Remove sample data")
        rem.setObjectName("danger")
        add.clicked.connect(lambda _=False: self.sample(True))
        rem.clicked.connect(lambda _=False: self.sample(False))
        logs = QPushButton("Open logs folder")
        logs.clicked.connect(lambda _=False: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log.log_path().parent))))
        self.db_label = label("", "muted", wrap=True)
        self.log_label = label("", "muted", wrap=True)
        self.body.addWidget(panel(self.db_label, row(add, rem, None), self.log_label, row(logs, None), title="Data & logs"))
        self.body.addStretch(1)

    # ---------------- terms ----------------
    def _load_terms(self):
        rows, ids = [], []
        for t in T.list_terms():
            a, d = T.counts(t.id)
            rows.append([t.name, t.year, f"{t.starts_on:%d %b %Y}", f"{t.ends_on:%d %b %Y}", f"{t.weight:g}", a, d])
            ids.append(t.id)
        self.terms.set_rows(rows, ids, center_from=1, fit_height=True)
        current = self.app.gb.term
        self.terms_note.setObjectName("noticeDone" if current else "note")
        self.terms_note.setStyleSheet("")
        self.terms_note.setText(f"Working in {current.label} ({current.starts_on:%d %b %Y} – {current.ends_on:%d %b %Y}). "
                                "Switch term at the top left." if current else
                                "No term is set up yet. Add one so each term's results stay separate.")

    @safe
    def add_term(self):
        last = T.list_terms()
        suggestion = {}
        if last:
            prev = last[-1]
            span = (prev.ends_on - prev.starts_on).days or 180
            starts = prev.ends_on + dt.timedelta(days=1)
            suggestion = {"name": T.next_class_name(prev.name), "year": prev.year, "starts": starts,
                          "ends": starts + dt.timedelta(days=span)}
        d = TermDialog(self, suggestion=suggestion)
        if d.exec():
            term = T.save_term(None, **d.values())
            if len(T.list_terms()) == 1:
                T.set_current(term.id)
                self.app.term_id = term.id
            self.app.reload()

    @safe
    def edit_term(self):
        tid = self.terms.current_id()
        if tid is None:
            return error(self, "Select a term first.")
        d = TermDialog(self, T.get_term(tid))
        if d.exec():
            T.save_term(tid, **d.values())
            self.app.reload()

    @safe
    def delete_term(self):
        tid = self.terms.current_id()
        if tid is None:
            return error(self, "Select a term first.")
        term = T.get_term(tid)
        if confirm(self, f"Delete {term.label}? It must have no assessments or registers in it."):
            T.delete_term(tid)
            if self.app.term_id == tid:
                self.app.term_id = None
            self.app.reload()

    @safe
    def start_term(self):
        classes = sorted(self.app.gb.classes.values(), key=lambda c: c.name.lower())
        last = T.list_terms()
        suggestion = {}
        if last:
            prev = last[-1]
            span = (prev.ends_on - prev.starts_on).days or 180
            starts = prev.ends_on + dt.timedelta(days=1)
            year = str(int(prev.year[:4]) + 1) if starts.year > prev.ends_on.year else prev.year
            suggestion = {"name": "Term 1" if year != prev.year else T.next_class_name(prev.name), "year": year,
                          "starts": starts, "ends": starts + dt.timedelta(days=span)}
        d = StartTermDialog(self, classes, suggestion)
        if not d.exec():
            return
        res = T.start_term(**d.values(), plan=d.plan())
        self.app.term_id = res["term"].id
        self.app.class_id = None
        self.app.reload()
        info(self, f"{res['term'].label} started."
                   + (f" {res['moved']} student(s) promoted." if res["moved"] else "")
                   + (f" {res['continued']} class(es) carried on." if res["continued"] else "")
                   + (f" {res['archived']} student(s) archived as their course finished." if res["archived"] else "")
                   + "\n\nLast term's marks stay where they are — switch term at the top left to see them.")

    # ---------------- backups ----------------
    def _folder(self):
        from backend.paths import backups_dir
        return self.app.gb.settings.get("backup_dir") or backups_dir()

    def _save_backup_prefs(self):
        R.save_settings({"auto_backup": self.auto.isChecked(), "backup_dir": self.folder.text()})
        self.app.gb.settings["auto_backup"] = self.auto.isChecked()
        self.app.gb.settings["backup_dir"] = self.folder.text()

    def _load_backups(self):
        s = self.app.gb.settings
        self.auto.blockSignals(True)
        self.auto.setChecked(bool(s.get("auto_backup", True)))
        self.auto.blockSignals(False)
        self.folder.setText(str(self._folder()))
        files = BK.list_backups(self._folder())
        self.backups.set_rows([[f"{b.when:%d %b %Y, %H:%M}", b.path.name, b.size_text] for b in files],
                              [str(b.path) for b in files], center_from=2, fit_height=True)
        self.b_restore.setEnabled(bool(files))
        last = s.get("last_backup") or ""
        found = BK.find_tool("pg_dump")
        self.b_locate.setVisible(True)
        if not BK.tools_available():
            self.backup_status.setObjectName("note")
            text = ("PostgreSQL's pg_dump was not found, so backups cannot run yet. Press \"Locate PostgreSQL tools…\" "
                    "and choose the 'bin' folder of your PostgreSQL installation (for example C:\\Program Files\\PostgreSQL\\16\\bin).")
        elif files:
            self.backup_status.setObjectName("noticeDone")
            text = f"Last backup: {files[0].when:%d %b %Y at %H:%M} · {len(files)} kept in this folder. Using {found}."
        else:
            self.backup_status.setObjectName("notice")
            text = "No backups yet. Press Back up now, or leave the automatic backup switched on." + (f" Last recorded: {last}." if last else "")
        self.backup_status.setStyleSheet("")
        self.backup_status.setText(text)

    @safe
    def pick_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Where should backups be kept?", self.folder.text())
        if chosen:
            self.folder.setText(chosen)
            self._save_backup_prefs()
            self._load_backups()

    @safe
    def locate_tools(self):
        """Point Markbook at the PostgreSQL bin folder when it is not on PATH (common on Windows)."""
        start = BK.configured_bin_dir() or (str(Path(BK.find_tool("pg_dump")).parent) if BK.find_tool("pg_dump") else "")
        chosen = QFileDialog.getExistingDirectory(self, "Choose the PostgreSQL 'bin' folder", start)
        if not chosen:
            return
        complaint = BK.check_bin_dir(chosen)
        if complaint:
            return error(self, complaint + "\n\nLook for a folder called 'bin' inside your PostgreSQL installation, "
                                "for example C:\\Program Files\\PostgreSQL\\16\\bin.")
        R.save_settings({"pg_bin_dir": chosen})
        self.app.reload()
        info(self, f"Using the PostgreSQL tools in {chosen}. Backups can run now.")

    @safe
    def backup_now(self):
        import datetime as dt
        path = BK.backup(self._folder())
        BK.prune(20, self._folder())
        R.save_settings({"last_backup": dt.datetime.now().isoformat(timespec="seconds")})
        self.app.reload()
        info(self, f"Backup saved:\n{path}")

    @safe
    def restore_selected(self):
        path = self.backups.current_id()
        if not path:
            return error(self, "Select a backup in the list first.")
        if not confirm(self, f"Restore {path.split('/')[-1].split(chr(92))[-1]}?\n\n"
                             "Everything currently in the database — students, marks, attendance and settings — is replaced "
                             "by the contents of this backup. Anything recorded since it was made will be lost.\n\nThis cannot be undone."):
            return
        BK.backup(self._folder(), "before-restore")          # safety net for the restore itself
        BK.restore(path)
        audit.record("database.restored", entity="database", detail=Path(path).name)
        self.app.class_id = None
        self.app.reload()
        info(self, "Backup restored. A copy of the previous data was saved first, labelled 'before-restore'.")

    def refresh(self):
        s = self.app.gb.settings
        self.school.setText(s.get("school", ""))
        self.head.setText(s.get("head_teacher", ""))
        nt = QDate.fromString(s.get("next_term") or "", "yyyy-MM-dd")
        self.next_term.setDate(nt if nt.isValid() else self.next_term.minimumDate())
        self.ca.setValue(int(s.get("ca_weight", 40)))
        self.who.setText(s.get("user_name") or "")
        self.who.setPlaceholderText(audit.machine_user())
        fill_combo(self.cls, self.app.class_items(), self.app.ensure_class())
        self._load_terms()
        self._load_class()
        url = get_config().database_url
        self.db_label.setText(f"Data is stored in PostgreSQL at {url.rsplit('@', 1)[-1]} (schema revision {migrate.current_revision() or 'unknown'}). "
                              f"The sample class ('{seed.SAMPLE_CLASS}') can be removed at any time without touching your own data.")
        self.log_label.setText(f"Problems are written to {log.log_path()} — send this file along if you report a bug.")
        self._load_backups()

    def _load_class(self):
        c = self.app.gb.classes.get(self.cls.currentData())
        for wdg in (self.c_name, self.c_teacher, self.c_level, self.c_pass, self.c_rollover):
            wdg.setEnabled(c is not None)
        if not c:
            return
        self.c_name.setText(c.name)
        self.c_teacher.setText(c.teacher)
        self.custom_rows = c.scale
        fill_combo(self.c_level, [(v, k) for k, v in LEVEL_LABELS.items()], c.level)
        self.c_pass.setValue(c.pass_mark if c.pass_mark is not None else self._default_pass(c.level))
        self.c_rollover.setCurrentIndex(max(0, self.c_rollover.findData(c.rollover or "promote")))
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
        R.save_settings({"school": self.school.text().strip(), "head_teacher": self.head.text().strip(),
                         "next_term": "" if nt == self.next_term.minimumDate() else nt.toString("yyyy-MM-dd"), "ca_weight": self.ca.value(),
                         "user_name": self.who.text().strip()})
        self.app.reload()
        info(self, "Settings saved.")

    @safe
    def add_class(self):
        d = ClassDialog(self, [n for n, _ in self.app.class_items()])
        if d.exec():
            v = d.values()
            cls = R.get_or_create_class(v["name"])
            R.save_class(cls.id, name=v["name"], level=v["level"], pass_mark=v["pass_mark"], teacher=v["teacher"], scale=None,
                         rollover=v.get("rollover"))
            self.app.class_id = cls.id
            self.app.reload()
            info(self, f"Class {v['name']} added. Add students to it from the Students page.")

    @safe
    def save_class(self):
        cid = self.cls.currentData()
        if cid is None:
            return
        lvl = self.c_level.currentData()
        R.save_class(cid, name=self.c_name.text(), level=lvl, pass_mark=self.c_pass.value(), teacher=self.c_teacher.text(),
                     scale=self.custom_rows if lvl == "custom" else None, rollover=self.c_rollover.currentData())
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