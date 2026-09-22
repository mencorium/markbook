# /markbook/frontend/pages/results.py
"""Class result sheet (divisions, ranking, subject performance) and report cards for the whole class."""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QPushButton

from backend.grading import DIVISIONS
from backend.services import comments, reports

from .. import theme
from ..widgets import Page, StatStrip, Table, confirm, error, fill_combo, fmt, info, label, panel, row, safe


class ResultsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Results & reports")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        sheet = QPushButton("Result sheet (PDF)")
        sheet.clicked.connect(lambda _=False: self.result_sheet())
        for w in (label("Class"), self.cls, sheet):
            self.actions.addWidget(w)
        self.strip = StatStrip()
        self.note = label("", "note", wrap=True)
        self.ranked = Table(["Pos"], stretch=2)
        self.ranked.doubleClicked.connect(lambda: app.open_student(self.ranked.current_id()))
        self.perf = Table(["Subject"], stretch=0)
        self.body.addWidget(self.strip)
        self.body.addWidget(self.note)
        self.body.addWidget(panel(self.ranked, title="Ranked results"))
        self.body.addWidget(panel(self.perf, title="Subject performance"))
        # report cards
        self.hist = QCheckBox("Include test history per subject")
        self.hist.setChecked(True)
        allc, fill, one = QPushButton("Download all report cards (PDF)"), QPushButton("Write suggested comments for students without one"), QPushButton("Report card for selected student")
        allc.setObjectName("primary")
        allc.clicked.connect(lambda _=False: self.all_cards())
        fill.clicked.connect(lambda _=False: self.fill())
        one.clicked.connect(lambda _=False: self.one_card())
        self.cards_note = label("", "muted", wrap=True)
        self.cards = Table(["Pos", "Student", "Total marks", "Average", "Class teacher's comment"], stretch=4)
        self.cards.doubleClicked.connect(lambda: app.open_student(self.cards.current_id()))
        self.body.addWidget(panel(label("Each card shows every subject with tests, exam, total, grade and position; total marks and position in class; a progress chart; "
                                        "weakest topics; and class teacher's and head teacher's comments. Set teacher names and next term's date in Settings.", "muted", wrap=True),
                                  row(self.hist, None, one, allc), self.cards_note, row(fill, None), self.cards, title="Report cards"))
        self.body.addStretch(1)

    def _class_changed(self):
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def refresh(self):
        gb = self.app.gb
        cid = self.app.ensure_class()
        fill_combo(self.cls, self.app.class_items(), cid)
        if not cid:
            self.subtitle.setText("Add students and record marks first.")
            return
        sc, rank, subs = gb.scale(cid), gb.ranking(cid), gb.class_subjects(cid)
        self.subtitle.setText(f"{gb.class_name(cid)} · {sc.label}" + (f" · division from {sc.best_note}" if sc.div else ""))
        inc = sum(1 for r in rank if not (r.summary.div and r.summary.div.complete))
        if sc.div:
            self.strip.set([(str(sum(1 for r in rank if r.summary.div and r.summary.div.complete and r.summary.div.div == d)), f"Division {d}") for d in DIVISIONS]
                           + ([(str(inc), "incomplete")] if inc else []))
        else:
            self.strip.set([(str(len(rank)), "students with results")])
        self.note.setVisible(bool(sc.div and inc))
        self.note.setText(f"{inc} student(s) have results in fewer than {sc.best} {'principal ' if sc.level == 'A' else ''}subjects, so no division yet. "
                          "They are ranked after complete students, by average.")
        head = ["Pos", "Reg. no.", "Name", *[s.short for s in subs], *(["Points", "Div"] if sc.div else []), "Total", "Average"]
        self.ranked.set_headers(head, stretch=2)
        rows, colors = [], {}
        for i, r in enumerate(rank):
            cells = []
            for j, s in enumerate(subs):
                res = r.summary.subs.get(s.id)
                cells.append(sc.letter(res.final) if res else "–")
                if res and not sc.passing(res.final):
                    colors[(i, 3 + j)] = (theme.PEN, None)
            d = r.summary.div
            rows.append([r.rank, r.student.reg_no or "", r.student.name, *cells,
                         *([d.points if d and d.complete else "–", d.div if d and d.complete else "–"] if sc.div else []),
                         f"{gb.total_marks(r.student)[0]:.1f}", fmt(r.summary.overall, "%")])
        self.ranked.set_rows(rows, [r.student.id for r in rank], center_from=3, colors=colors, fit_height=True)
        self.perf.set_headers(["Subject", *sc.grades, "Average", "Pass rate"], stretch=0)
        prow = []
        for s in subs:
            fs = [r.summary.subs[s.id].final for r in rank if s.id in r.summary.subs]
            prow.append([s.name, *[sum(1 for f in fs if sc.letter(f) == g) or "" for g in sc.grades], fmt(sum(fs) / len(fs), "%") if fs else "–",
                         f"{round(sum(1 for f in fs if sc.passing(f)) / len(fs) * 100)}%" if fs else "–"])
        self.perf.set_rows(prow, fit_height=True)
        studs = gb.students_in(cid)
        pos = {r.student.id: r.rank for r in rank}
        missing = sum(1 for s in studs if not s.remarks.strip())
        self.cards_note.setText(f"{missing} of {len(studs)} students have no class teacher's comment yet." if missing else "Every student has a class teacher's comment.")
        order = sorted(studs, key=lambda s: pos.get(s.id, 10 ** 6))
        self.cards.set_rows([[pos.get(s.id, "–"), s.name, (lambda t: f"{t[0]:.1f} / {t[1] * 100}" if t[1] else "–")(gb.total_marks(s)),
                              fmt(gb.summary(s).overall, "%"), (s.remarks[:90] + ("…" if len(s.remarks) > 90 else "")) if s.remarks.strip() else "Missing"] for s in order],
                            [s.id for s in order], colors={(i, 4): (theme.AMBER, None) for i, s in enumerate(order) if not s.remarks.strip()}, fit_height=True, left=(1, 4))

    @safe
    def fill(self):
        if confirm(self, "Write suggested comments for students without one? You can edit each on the student's page before printing."):
            n = comments.fill_missing_comments(self.app.gb, self.app.class_id)
            self.app.reload()
            info(self, f"Wrote {n} comments.")

    @safe
    def result_sheet(self):
        gb = self.app.gb
        if not gb.ranking(self.app.class_id):
            return error(self, "No marks recorded for this class yet.")
        path, _ = QFileDialog.getSaveFileName(self, "Save result sheet", f"{gb.class_name(self.app.class_id)}-results.pdf".replace(" ", "-"), "PDF (*.pdf)")
        if path:
            reports.results_sheet(gb, self.app.class_id, path)
            info(self, f"Saved {path}")

    @safe
    def all_cards(self):
        gb = self.app.gb
        ids = reports.class_order(gb, self.app.class_id)
        if not ids:
            return error(self, "No marks recorded for this class yet.")
        path, _ = QFileDialog.getSaveFileName(self, "Save report cards", f"report-cards-{gb.class_name(self.app.class_id)}.pdf".replace(" ", "-"), "PDF (*.pdf)")
        if path:
            reports.report_cards(gb, ids, path, self.hist.isChecked())
            info(self, f"Saved {len(ids)} report cards to {path}")

    @safe
    def one_card(self):
        sid = self.cards.current_id()
        if sid is None:
            return error(self, "Select a student in the list first.")
        gb = self.app.gb
        path, _ = QFileDialog.getSaveFileName(self, "Save report card", f"report-{gb.students[sid].name}.pdf".replace(" ", "-"), "PDF (*.pdf)")
        if path:
            reports.report_cards(gb, [sid], path, self.hist.isChecked())
            info(self, f"Saved {path}")