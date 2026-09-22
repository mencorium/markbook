# /markbook/frontend/pages/import_export.py
"""Import class lists / mark sheets and export mark sheets, cumulative progress and class lists."""
from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFileDialog, QFormLayout, QLineEdit, QPushButton,
                             QRadioButton, QWidget)

from backend.services import assessments as A
from backend.services import exports, imports

from .. import theme
from ..widgets import Page, Table, error, fill_combo, info, label, panel, row, safe

SCOPES = [("single", "Single test or exam"), ("subject", "Cumulative — one subject"), ("class", "Cumulative — all subjects"), ("list", "Class list with phones")]


class ImportExportPage(Page):
    def __init__(self, app):
        super().__init__(app, "Import & export", "Bring in class lists and mark sheets, or save them for Excel")
        self.preview: imports.ImportPreview | None = None
        # ---- import ----
        choose = QPushButton("Choose Excel or CSV file…")
        choose.clicked.connect(lambda _=False: self.choose())
        self.imp_info = label("", "muted", wrap=True)
        self.imp_form = QWidget()
        f = QFormLayout(self.imp_form)
        self.i_class = QComboBox()
        self.i_class.setEditable(True)
        self.i_subject = QComboBox()
        self.i_name = QLineEdit()
        self.i_type = QComboBox()
        self.i_type.addItems(A.TYPES)
        self.i_date = QDateEdit()
        self.i_date.setCalendarPopup(True)
        self.i_max = QDoubleSpinBox()
        self.i_max.setRange(0.5, 1000)
        self.i_add = QCheckBox("Add students who aren't in the class yet")
        self.i_add.setChecked(True)
        for lab, w in [("Class", self.i_class), ("Subject", self.i_subject), ("Assessment", self.i_name), ("Type", self.i_type), ("Date", self.i_date), ("Out of", self.i_max), ("", self.i_add)]:
            f.addRow(lab, w)
        self.i_class.currentTextChanged.connect(lambda _: self._rematch())
        self.imp_table = Table(["Name", "Reg. no.", "Phone", "Mark", "Status"], stretch=0)
        self.b_import = QPushButton("Import")
        self.b_import.setObjectName("primary")
        self.b_import.clicked.connect(lambda _=False: self.do_import())
        self.body.addWidget(panel(label("Upload a class list or a mark sheet. Sheets exported from here import straight back, including per-question marks. "
                                        "Other sheets work if they have a Student Name column, plus Reg. No., Phone and Marks columns where you have them.", "muted", wrap=True),
                                  row(choose, None), self.imp_info, self.imp_form, self.imp_table, row(self.b_import, None), title="Import"))
        # ---- export ----
        self.scope = QButtonGroup(self)
        srow = row()
        for i, (key, text) in enumerate(SCOPES):
            rb = QRadioButton(text)
            rb.setProperty("key", key)
            self.scope.addButton(rb, i)
            srow.addWidget(rb)
        srow.addStretch(1)
        self.scope.button(0).setChecked(True)
        self.scope.idToggled.connect(lambda _i, on: on and self._export_controls())
        self.e_class, self.e_subject, self.e_kind, self.e_assess = QComboBox(), QComboBox(), QComboBox(), QComboBox()
        fill_combo(self.e_kind, [("Tests and exams", None), ("Tests only", "test"), ("Exams only", "exam")])
        self.e_show, self.e_null, self.e_fmt = QComboBox(), QComboBox(), QComboBox()
        fill_combo(self.e_show, [("Marks", "marks"), ("Grades", "grades")])
        fill_combo(self.e_null, [("Write null", True), ("Leave blank", False)])
        fill_combo(self.e_fmt, [("Excel (.xlsx)", "xlsx"), ("CSV", "csv")])
        for c in (self.e_class, self.e_subject, self.e_kind):
            c.currentIndexChanged.connect(lambda _: self._export_controls())
        b_export = QPushButton("Save…")
        b_export.setObjectName("primary")
        b_export.clicked.connect(lambda _=False: self.do_export())
        self.e_rows = [row(label("Class"), self.e_class, label("Subject"), self.e_subject, label("Show"), self.e_kind, label("Assessment"), self.e_assess, None)]
        self.e_prev = Table(["Preview"])
        self.body.addWidget(panel(label("What to export", "muted"), srow, *self.e_rows,
                                  row(label("Columns show"), self.e_show, label("Missing reg. no."), self.e_null, label("Format"), self.e_fmt, None, b_export),
                                  label("Columns show marks or grades, never both. The Excel file has a centred title block, styled header and summary rows; "
                                        "all-subject exports add one sheet per subject.", "muted", wrap=True),
                                  self.e_prev, title="Export"))
        self.body.addStretch(1)

    # ---------------- import ----------------
    def refresh(self):
        cid = self.app.ensure_class()
        fill_combo(self.e_class, self.app.class_items(), self.e_class.currentData() or cid)
        self._export_controls()
        self._show_preview()

    @safe
    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a sheet", "", "Spreadsheets (*.xlsx *.csv *.txt)")
        if path:
            self.load_file(path)

    def load_file(self, path: str):
        gb = self.app.gb
        self.preview = imports.parse(imports.read_table(path), path, gb.class_name(self.app.class_id) if self.app.class_id else "")
        p = self.preview
        fill_combo(self.i_class, [(n, n) for n, _ in self.app.class_items()])
        self.i_class.setCurrentText(p.class_name)
        subs = sorted(gb.subjects.values(), key=lambda s: s.name)
        match = next((s for s in subs if imports.norm(s.name) == imports.norm(p.subject_name) or imports.norm(s.code) == imports.norm(p.subject_name)), None)
        fill_combo(self.i_subject, [(s.name, s.id) for s in subs] + [(f"New subject: {p.subject_name or 'Imported subject'}", -1)], match.id if match else -1)
        self.i_name.setText(p.assessment)
        self.i_type.setCurrentText(p.type)
        self.i_date.setDate(QDate(p.date.year, p.date.month, p.date.day))
        self.i_max.setValue(p.max_marks)
        self._show_preview()

    def _rematch(self):
        if self.preview:
            self.preview.class_name = self.i_class.currentText()
            self._show_preview()

    def _show_preview(self):
        p = self.preview
        self.imp_form.setVisible(bool(p))
        self.imp_table.setVisible(bool(p))
        self.b_import.setVisible(bool(p))
        if not p:
            self.imp_info.setText("")
            return
        marks = p.kind == "marks"
        for w in (self.i_subject, self.i_name, self.i_type, self.i_date, self.i_max):
            w.setEnabled(marks)
        imports.match_rows(p, self.app.gb)
        new = sum(1 for r in p.rows if r.match_id is None)
        msg = f"{'Mark sheet' if marks else 'Class list'} · {p.file_name} · {len(p.rows)} students · {new} new."
        if p.qcols:
            msg += f" Marks for {len(p.qcols)} questions ({', '.join(q['label'] for q in p.qcols)}) will be imported per question."
        bad_phone = sum(1 for r in p.rows if not r.phone_ok)
        if bad_phone:
            msg += f" {bad_phone} phone number(s) are not valid and will be left empty."
        self.imp_info.setText(msg)
        rows, colors = [], {}
        for i, r in enumerate(p.rows[:200]):
            status = ("Matched" if marks else "Already listed") if r.match_id else ("Will be added" if self.i_add.isChecked() else "Skipped")
            rows.append([r.name, r.reg, r.phone + ("" if r.phone_ok else "  (invalid)"), "invalid" if r.bad else ("absent" if r.mark is None and marks else (f"{r.mark:g}" if r.mark is not None else "")), status])
            colors[(i, 4)] = (theme.GREEN if r.match_id else theme.AMBER, None)
        self.imp_table.set_rows(rows, colors=colors, fit_height=True)

    @safe
    def do_import(self):
        p = self.preview
        q = self.i_date.date()
        p.class_name, p.assessment, p.type = self.i_class.currentText().strip(), self.i_name.text().strip(), self.i_type.currentText()
        p.date, p.max_marks = dt.date(q.year(), q.month(), q.day()), self.i_max.value()
        sid = self.i_subject.currentData()
        res = imports.commit(p, self.app.gb, self.i_add.isChecked(), None if sid in (None, -1) else sid)
        self.preview = None
        self.app.reload()
        info(self, f"Imported {res['marks']} marks and added {res['added']} students." if p.kind == "marks" else f"Added {res['added']} students.")
        if res["assessment_id"]:
            self.app.open_assessment(res["assessment_id"])

    # ---------------- export ----------------
    def _key(self) -> str:
        return self.scope.checkedButton().property("key")

    def _export_controls(self):
        gb, key, cid = self.app.gb, self._key(), self.e_class.currentData()
        subs = gb.class_subjects(cid) if cid else []
        fill_combo(self.e_subject, [(s.name, s.id) for s in subs], self.e_subject.currentData())
        as_ = gb.assessments_for(cid, self.e_subject.currentData(), self.e_kind.currentData())[::-1] if cid and self.e_subject.currentData() else []
        fill_combo(self.e_assess, [(f"{a.name} · {a.type} · {a.date:%d %b}", a.id) for a in as_], self.e_assess.currentData())
        self.e_subject.setEnabled(key in ("single", "subject"))
        self.e_kind.setEnabled(key == "single")
        self.e_assess.setEnabled(key == "single")
        self.e_show.setEnabled(key != "list")
        sheets = self._sheets()
        if sheets:
            sh = sheets[0]
            self.e_prev.set_headers(sh.head)
            self.e_prev.set_rows(sh.body[:12], center_from=3, fit_height=True)
        else:
            self.e_prev.set_headers(["Preview"])
            self.e_prev.setRowCount(0)

    def _sheets(self):
        gb, key, cid = self.app.gb, self._key(), self.e_class.currentData()
        show, null = self.e_show.currentData(), self.e_null.currentData()
        if not cid:
            return []
        if key == "single":
            aid = self.e_assess.currentData()
            return exports.single_sheets(gb, aid, show, null) if aid else []
        if key == "subject":
            sid = self.e_subject.currentData()
            return [exports.subject_sheet(gb, cid, sid, show, null)] if sid else []
        if key == "class":
            return exports.class_sheets(gb, cid, show, null) if gb.class_subjects(cid) else []
        return [exports.class_list_sheet(gb, cid, null)]

    @safe
    def do_export(self):
        sheets = self._sheets()
        if not sheets:
            return error(self, "Choose what to export first.")
        kind = self.e_fmt.currentData()
        name = f"{self.app.gb.class_name(self.e_class.currentData())}-{sheets[0].name}".replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"{name}.{kind}", "Excel (*.xlsx)" if kind == "xlsx" else "CSV (*.csv)")
        if path:
            exports.write_xlsx(path, sheets) if kind == "xlsx" else exports.write_csv(path, sheets[0])
            info(self, f"Saved {path}")