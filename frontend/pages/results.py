# /markbook/frontend/pages/results.py
"""Class result sheet (divisions, ranking, subject performance) and report cards for the whole class."""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QPushButton

from backend.grading import DIVISIONS
from backend.services import comments, exports, reports
from backend.services import terms as T
from backend.services.annual import AnnualBook

from .. import theme
from ..widgets import Page, StatStrip, Table, confirm, error, fill_combo, fmt, info, label, panel, row, safe


class ResultsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Results & reports")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        self.scope = QComboBox()
        self.scope.addItem("This term", "term")
        self.scope.addItem("Whole year", "year")
        self.scope.currentIndexChanged.connect(lambda _: self.refresh())
        sheet = QPushButton("Result sheet (PDF)")
        sheet.clicked.connect(lambda _=False: self.result_sheet())
        excel = QPushButton("Export (Excel)")
        excel.clicked.connect(lambda _=False: self.export_excel())
        for w in (label("Class"), self.cls, label("Show"), self.scope, excel, sheet):
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

    def annual_mode(self) -> bool:
        return self.scope.currentData() == "year"

    def _book(self):
        """The year the current term belongs to, or every term if none is selected."""
        gb = self.app.gb
        year = gb.term.year if gb.term else (T.years()[0] if T.years() else "")
        return AnnualBook.load(year, self.app.class_id) if year and self.app.class_id else None

    def refresh(self):
        gb = self.app.gb
        cid = self.app.ensure_class()
        fill_combo(self.cls, self.app.class_items(), cid)
        if not cid:
            self.subtitle.setText("Add students and record marks first.")
            return
        if self.annual_mode():
            return self._refresh_annual()
        sc, rank, subs = gb.scale(cid), gb.ranking(cid), gb.class_subjects(cid)
        self.subtitle.setText(f"{gb.class_name(cid)} · {gb.term_label} · {sc.label}" + (f" · division from {sc.best_note}" if sc.div else ""))
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

    def _refresh_annual(self):
        book = self._book()
        if book is None or not book.ranked:
            self.subtitle.setText("No results for this year yet.")
            self.strip.set([])
            self.ranked.set_rows([])
            self.perf.set_rows([])
            self.cards.set_rows([])
            self.note.setVisible(False)
            return
        sc, subs = book.scale, book.subjects()
        self.subtitle.setText(f"{book.class_name} · {book.year} · {', '.join(t.name for t in book.terms)} · {sc.label}")
        inc = sum(1 for r in book.ranked if not (r.div and r.div.complete))
        if sc.div:
            self.strip.set([(str(sum(1 for r in book.ranked if r.div and r.div.complete and r.div.div == d)), f"Division {d}") for d in DIVISIONS]
                           + ([(str(inc), "incomplete")] if inc else []))
        else:
            self.strip.set([(str(len(book.ranked)), "students with results")])
        self.note.setVisible(True)
        self.note.setText(book.weights_note() + " Marks stay in their own term; this view combines them.")
        head = ["Pos", "Reg. no.", "Name", *[s.short for s in subs], *(["Points", "Div"] if sc.div else []), "Total", "Year %"]
        self.ranked.set_headers(head, stretch=2)
        rows, colors = [], {}
        for i, r in enumerate(book.ranked):
            cells = []
            for j, s in enumerate(subs):
                got = r.subjects.get(s.id)
                cells.append(sc.letter(got.final) if got else "–")
                if got and not sc.passing(got.final):
                    colors[(i, 3 + j)] = (theme.PEN, None)
            rows.append([r.rank, r.student.reg_no or "", r.student.name, *cells,
                         *([r.div.points if r.div and r.div.complete else "–", r.div.div if r.div and r.div.complete else "–"] if sc.div else []),
                         f"{r.total:.1f}", fmt(r.overall, "%")])
        self.ranked.set_rows(rows, [r.student.id for r in book.ranked], center_from=3, colors=colors, fit_height=True)
        self.perf.set_headers(["Subject", *[f"{t.name} avg" for t in book.terms], "Year avg", "Pass rate"], stretch=0)
        prow = []
        for x in subs:
            finals = [r.subjects[x.id].final for r in book.ranked if x.id in r.subjects]
            per_term = []
            for t in book.terms:
                vals = [r.subjects[x.id].per_term[t.id] for r in book.ranked if x.id in r.subjects and t.id in r.subjects[x.id].per_term]
                per_term.append(fmt(sum(vals) / len(vals) if vals else None, "%"))
            prow.append([x.name, *per_term, fmt(sum(finals) / len(finals) if finals else None, "%"),
                         f"{round(sum(1 for f in finals if sc.passing(f)) / len(finals) * 100)}%" if finals else "–"])
        self.perf.set_rows(prow, fit_height=True)
        self.cards_note.setText("Annual report cards show every term side by side, then the year mark, position and division.")
        self.cards.set_rows([[r.rank, r.student.name, f"{r.total:.1f}", fmt(r.overall, "%"),
                              f"{r.terms_sat} of {len(book.terms)} term(s) sat"] for r in book.ranked],
                            [r.student.id for r in book.ranked], center_from=2, fit_height=True)

    @safe
    def fill(self):
        if confirm(self, "Write suggested comments for students without one? You can edit each on the student's page before printing."):
            n = comments.fill_missing_comments(self.app.gb, self.app.class_id)
            self.app.reload()
            info(self, f"Wrote {n} comments.")

    @safe
    def export_excel(self):
        gb = self.app.gb
        book = self._book() if self.annual_mode() else None
        if self.annual_mode() and (book is None or not book.ranked):
            return error(self, "No results for this year yet.")
        sheets = exports.annual_sheets(book) if self.annual_mode() else exports.class_sheets(gb, self.app.class_id, "marks")
        if not sheets:
            return error(self, "No marks recorded for this class yet.")
        name = f"{gb.class_name(self.app.class_id)}-{'year-' + book.year if self.annual_mode() else 'term'}".replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Export results", f"{name}.xlsx", "Excel (*.xlsx)")
        if path:
            exports.write_xlsx(path, sheets)
            info(self, f"Saved {path}")

    @safe
    def result_sheet(self):
        gb = self.app.gb
        if self.annual_mode():
            book = self._book()
            if book is None or not book.ranked:
                return error(self, "No results for this year yet.")
            path, _ = QFileDialog.getSaveFileName(self, "Save annual result sheet",
                                                  f"{book.class_name}-{book.year}-annual.pdf".replace(" ", "-"), "PDF (*.pdf)")
            if path:
                reports.annual_results_sheet(book, path)
                info(self, f"Saved {path}")
            return
        if not gb.ranking(self.app.class_id):
            return error(self, "No marks recorded for this class yet.")
        path, _ = QFileDialog.getSaveFileName(self, "Save result sheet", f"{gb.class_name(self.app.class_id)}-results.pdf".replace(" ", "-"), "PDF (*.pdf)")
        if path:
            reports.results_sheet(gb, self.app.class_id, path)
            info(self, f"Saved {path}")

    def _annual_cards(self, ids: list[int] | None = None):
        book = self._book()
        if book is None or not book.ranked:
            return error(self, "No results for this year yet.")
        ids = ids or reports.annual_order(book)
        from backend.services.analytics import Gradebook
        path, _ = QFileDialog.getSaveFileName(self, "Save annual report cards",
                                              f"annual-report-cards-{book.class_name}-{book.year}.pdf".replace(" ", "-"), "PDF (*.pdf)")
        if path:
            reports.annual_report_cards(book, Gradebook.load(None), ids, path)
            info(self, f"Saved {len(ids)} annual report card(s) to {path}")

    @safe
    def all_cards(self):
        gb = self.app.gb
        if self.annual_mode():
            return self._annual_cards()
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
        if self.annual_mode():
            return self._annual_cards([sid])
        gb = self.app.gb
        path, _ = QFileDialog.getSaveFileName(self, "Save report card", f"report-{gb.students[sid].name}.pdf".replace(" ", "-"), "PDF (*.pdf)")
        if path:
            reports.report_cards(gb, [sid], path, self.hist.isChecked())
            info(self, f"Saved {path}")