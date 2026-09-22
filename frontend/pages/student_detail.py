# /markbook/frontend/pages/student_detail.py
"""One student: results, progress chart, targets, weakest topics, comments, report card and progress export."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QPushButton, QTextEdit, QWidget

from backend.phone import display_phone
from backend.services import charts, comments, exports, records as R, reports
from backend.services.analytics import TREND_WORDS, avg

from .. import theme
from ..dialogs import StudentDialog
from ..widgets import Chart, Page, StatStrip, Table, confirm, fill_combo, fmt, info, label, panel, row, safe


class StudentDetailPage(Page):
    def __init__(self, app):
        super().__init__(app, "Student")
        back = QPushButton("← Students")
        back.clicked.connect(lambda _=False: app.show_page("students"))
        self.body.insertLayout(0, row(back, stretch_end=True))
        for text, fn, name in [("Edit details", self.edit, None), ("Report card (PDF)", self.report, None),
                               ("Progress (Excel)", self.progress_xlsx, None), ("Remove", self.remove, "danger")]:
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(lambda _=False, f=fn: f())
            self.actions.addWidget(b)
        self.mark = label("", "bigMark")
        head = QHBoxLayout()
        head.addWidget(self.mark)
        self.info = label("", "subtitle", wrap=True)
        head.addWidget(self.info, 1)
        self.body.addLayout(head)
        self.strip = StatStrip()
        self.body.addWidget(self.strip)
        self.subj = QComboBox()
        self.subj.currentIndexChanged.connect(lambda _: self._draw_progress())
        self.c_prog = Chart(3.2)
        self.body.addWidget(panel(row(label("Progress over time", "h2"), None, label("Subject"), self.subj), self.c_prog,
                                  label("Shaded bars show attendance in the days before each assessment.", "muted")))
        g = QGridLayout()
        g.setSpacing(14)
        self.c_vs = Chart()
        self.topics = Table(["Topic", "Subject", "Score", "Grade"], stretch=0)
        g.addWidget(panel(self.c_vs, title="Compared with class average"), 0, 0)
        g.addWidget(panel(self.topics, title="Weakest topics"), 0, 1)
        holder = QWidget()
        holder.setLayout(g)
        self.body.addWidget(holder)
        self.results = Table(["Subject", "Tests", "Exam", "Final", "Grade", "Predicted", "Target", "Status", "Position", "Trend"], stretch=0)
        self.results_note = label("", "muted", wrap=True)
        self.body.addWidget(panel(self.results, self.results_note, title="Results by subject"))
        self.recent = Table(["Date", "Assessment", "Subject", "Score", "Grade"], stretch=1)
        self.body.addWidget(panel(self.recent, title="Latest results"))
        self.remarks = QTextEdit()
        self.remarks.setPlaceholderText("Class teacher's comment for the report card")
        self.remarks.setMinimumHeight(110)
        sug, save = QPushButton("Suggest a comment"), QPushButton("Save comment")
        save.setObjectName("primary")
        sug.clicked.connect(lambda _=False: self.suggest())
        save.clicked.connect(lambda _=False: self.save_remarks())
        self.body.addWidget(panel(row(label("Class teacher's comment", "h2"), None, sug, save), self.remarks))
        self.body.addStretch(1)

    @property
    def stu(self):
        return self.app.gb.students.get(self.app.student_id)

    def refresh(self):
        gb, stu = self.app.gb, self.stu
        if not stu:
            return
        sm, sc = gb.summary(stu), gb.scale(stu.class_id)
        rank, n = gb.position(stu)
        total, k = gb.total_marks(stu)
        self.title.setText(stu.name)
        self.subtitle.setText(f"{gb.class_name(stu.class_id)} · {sc.label}")
        big = sm.div.div if sm.div and sm.div.complete else sc.letter(sm.overall)
        self.mark.setText(big)
        self.info.setText(f"Reg. no.: {stu.reg_no or '–'}    Phone: {display_phone(stu.phone) or '–'}\n"
                          + (f"Division {sm.div.div} · {sm.div.points} points ({sc.best_note})" if sm.div and sm.div.complete else
                             f"Grade {sc.letter(sm.overall)}" + (f" · {sm.div.text()}" if sm.div else "")) + f"   ·   {TREND_WORDS[sm.trend]}")
        self.strip.set([(fmt(sm.overall, "%"), f"average, grade {sc.letter(sm.overall)}"), (f"{rank or '–'} of {n}", "position in class"),
                        (f"{total:.1f} / {k * 100}" if k else "–", "total marks"),
                        *([(f"Div {sm.pred_div.div}" if sm.pred_div and sm.pred_div.complete else "–", "predicted division")] if sc.div else []),
                        (fmt(sm.att, "%"), "attendance")])
        subs = sorted(sm.subs, key=gb.subject_name)
        fill_combo(self.subj, [(gb.subject_name(s), s) for s in subs], self.subj.currentData(), blank="All subjects")
        self._draw_progress()
        self.c_vs.draw_with(lambda ax: self._vs(ax, subs))
        weak = gb.student_topics(stu)[:6]
        self.topics.set_rows([[t.topic, gb.subject_short(t.subject_id), fmt(t.mean, "%"), sc.letter(t.mean)] for t in weak],
                             colors={(i, 3): (theme.PEN, None) for i, t in enumerate(weak) if not sc.passing(t.mean)})
        self._results(subs)
        as_ = [a for a in gb.student_assessments(stu) if gb.has_score(a, stu.id)][::-1][:10]
        self.recent.set_rows([[a.date.isoformat(), a.name, gb.subject_name(a.subject_id), fmt(gb.pct(a, stu.id), "%"), sc.letter(gb.pct(a, stu.id))] for a in as_],
                             center_from=3, fit_height=True)
        self.remarks.setPlainText(stu.remarks)

    def _draw_progress(self):
        if self.stu:
            self.c_prog.draw_with(lambda ax: charts.progress(ax, self.app.gb, self.stu.id, self.subj.currentData()), bottom=0.3)

    def _vs(self, ax, subs):
        gb, stu = self.app.gb, self.stu
        if not subs:
            return False
        me = [gb.summary(stu).subs[s].final for s in subs]
        cls = [avg(r.final for p in gb.students_in(stu.class_id) if (r := gb.subject_result(p, s))) for s in subs]
        xs = range(len(subs))
        ax.bar([x - 0.2 for x in xs], me, width=0.4, color=theme.BLUE, label=stu.name.split()[0])
        ax.bar([x + 0.2 for x in xs], [c or 0 for c in cls], width=0.4, color="#C9D6E6", label="Class average")
        charts.style(ax)
        ax.set_xticks(list(xs))
        ax.set_xticklabels([gb.subject_short(s) for s in subs], fontsize=8)
        ax.legend(fontsize=7, frameon=False)

    def _results(self, subs):
        gb, stu = self.app.gb, self.stu
        sm, sc = gb.summary(stu), gb.scale(stu.class_id)
        rows, colors = [], {}
        for i, sid in enumerate(subs):
            r = sm.subs[sid]
            pos, of = gb.subject_positions(stu.class_id, sid)
            pg, t = sc.letter(r.predicted), stu.targets.get(str(sid), "")
            status = "" if not t else ("On track" if sc.index(pg) <= sc.index(t) else "Behind")
            rows.append([gb.subject_name(sid) + (" (subsidiary)" if gb.subjects[sid].subsidiary else ""), fmt(r.ca), fmt(r.ex),
                         fmt(r.final) + (" *" if r.provisional else ""), sc.letter(r.final), f"{pg} ({fmt(r.predicted)}%)" if r.provisional else "final",
                         "", status, f"{pos.get(stu.id, '–')} of {of}", TREND_WORDS[r.trend] if r.n >= 3 else "–"])
            if not sc.passing(r.final):
                colors[(i, 4)] = (theme.PEN, None)
            if status:
                colors[(i, 7)] = (theme.GREEN if status == "On track" else theme.AMBER, None)
        self.results.set_rows(rows, subs, colors=colors, fit_height=True)
        for i, sid in enumerate(subs):
            combo = QComboBox()
            fill_combo(combo, [(g, g) for g in sc.grades], stu.targets.get(str(sid)), blank="—")
            combo.currentIndexChanged.connect(lambda _, s=sid, c=combo: self.set_target(s, c.currentData()))
            self.results.setCellWidget(i, 6, combo)
        w = gb.settings.get("ca_weight", 40)
        self.results_note.setText(f"Final = tests {w}% + exam {100 - int(w)}%. * no exam yet. Predictions project the exam score from the trend so far.")

    @safe
    def set_target(self, subject_id, grade):
        R.set_target(self.stu.id, subject_id, grade)
        self.app.reload()

    @safe
    def edit(self):
        stu = self.stu
        d = StudentDialog(self, [n for n, _ in self.app.class_items()], stu, self.app.gb.class_name(stu.class_id))
        if d.exec():
            R.save_student(stu.id, **d.values())
            self.app.reload()

    @safe
    def remove(self):
        if confirm(self, f"Remove {self.stu.name}? Their marks will be deleted too."):
            R.delete_student(self.stu.id)
            self.app.gb = self.app.gb.load()
            self.app.show_page("students")

    def suggest(self):
        c = comments.auto_comment(self.app.gb, self.stu.id)
        if c:
            self.remarks.setPlainText(c)

    @safe
    def save_remarks(self):
        R.set_remarks(self.stu.id, self.remarks.toPlainText())
        self.app.reload()
        info(self, "Comment saved.")

    @safe
    def report(self):
        R.set_remarks(self.stu.id, self.remarks.toPlainText())
        self.app.gb = self.app.gb.load()
        path, _ = QFileDialog.getSaveFileName(self, "Save report card", f"report-{self.stu.name}.pdf", "PDF (*.pdf)")
        if path:
            reports.report_cards(self.app.gb, [self.stu.id], path)
            info(self, f"Saved {path}")

    @safe
    def progress_xlsx(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save progress", f"progress-{self.stu.name}.xlsx", "Excel (*.xlsx)")
        if path:
            exports.write_xlsx(path, exports.student_progress_sheets(self.app.gb, self.stu.id))
            info(self, f"Saved {path}")