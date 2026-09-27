# /markbook/frontend/pages/subject_detail.py
"""One subject in one class: every assessment in it, and the cumulative result per student."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFileDialog, QGridLayout, QPushButton, QWidget

from backend.services import charts, exports
from backend.services.analytics import TREND_WORDS, avg

from .. import theme
from ..widgets import Chart, Page, StatStrip, Table, error, fill_combo, fmt, info, label, panel, row, safe


class SubjectDetailPage(Page):
    def __init__(self, app):
        super().__init__(app, "Subject")
        self.back = QPushButton("← Back")
        self.back.setToolTip("Alt+Left")
        self.back.clicked.connect(lambda _=False: app.go_back())
        self.body.insertLayout(0, row(self.back, stretch_end=True))
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        self.subj = QComboBox()
        self.subj.currentIndexChanged.connect(self._subject_changed)
        xls = QPushButton("Export (Excel)")
        xls.clicked.connect(lambda _=False: self.export())
        for w in (label("Class"), self.cls, label("Subject"), self.subj, xls):
            self.actions.addWidget(w)
        self.strip = StatStrip()
        self.body.addWidget(self.strip)

        g = QGridLayout()
        g.setSpacing(14)
        self.c_time, self.c_grades = Chart(2.6), Chart(2.6)
        g.addWidget(panel(self.c_time, title="Class average across this subject"), 0, 0)
        g.addWidget(panel(self.c_grades, title="Final grades in this subject"), 0, 1)
        holder = QWidget()
        holder.setLayout(g)
        self.body.addWidget(holder)

        self.tests = Table(["Date", "Assessment", "Type", "Out of", "Marked", "Mean", "Highest", "Lowest", "Passed"], stretch=1)
        self.tests.doubleClicked.connect(lambda: app.open_assessment(self.tests.current_id()))
        self.body.addWidget(panel(self.tests, label("Double-click an assessment to enter or review its marks.", "muted"),
                                  title="Tests and exams in this subject"))

        self.cumulative = Table(["Student"], stretch=0)
        self.cumulative.doubleClicked.connect(lambda: app.open_student(self.cumulative.current_id()))
        self.cum_note = label("", "muted", wrap=True)
        self.body.addWidget(panel(self.cumulative, self.cum_note, title="Cumulative results"))

        self.topics = Table(["Topic", "Assessments", "Class average", "Below pass", "Struggling most"], stretch=4)
        self.topics_panel = panel(self.topics, label("From topics tagged on tests, and from the topic of each question on papers.",
                                                     "muted", wrap=True), title="Topics in this subject")
        self.body.addWidget(self.topics_panel)
        self.body.addStretch(1)

    # ---------------- selection ----------------
    def _class_changed(self):
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def _subject_changed(self):
        self.app.subject_id = self.subj.currentData()
        self._draw()

    def refresh(self):
        gb = self.app.gb
        cid = self.app.ensure_class()
        fill_combo(self.cls, self.app.class_items(), cid)
        subs = gb.class_subjects(cid) if cid else []
        if not subs:
            subs = sorted(gb.subjects.values(), key=lambda s: s.name.lower())
        current = self.app.subject_id if any(s.id == self.app.subject_id for s in subs) else (subs[0].id if subs else None)
        self.app.subject_id = current
        fill_combo(self.subj, [(s.name, s.id) for s in subs], current)
        self._draw()

    # ---------------- content ----------------
    def _draw(self):
        gb, cid, sid = self.app.gb, self.app.class_id, self.app.subject_id
        if not cid or not sid or sid not in gb.subjects:
            self.back.setText(f"← {self.app.back_target()}")
            self.title.setText("Subject")
            self.subtitle.setText("Add a subject and record some marks first.")
            for t in (self.tests, self.cumulative, self.topics):
                t.set_rows([])
            self.strip.set([])
            return
        sub, sc = gb.subjects[sid], gb.scale(cid)
        as_ = gb.assessments_for(cid, sid)
        studs = gb.students_in(cid)
        results = {s.id: gb.subject_result(s, sid) for s in studs}
        finals = [r.final for r in results.values() if r]
        self.back.setText(f"← {self.app.back_target()}")
        self.title.setText(sub.name)
        self.subtitle.setText(f"{gb.class_name(cid)} · {gb.term_label} · {sc.label}"
                              + ("  ·  subsidiary subject" if sub.subsidiary else ""))
        passing = [f for f in finals if sc.passing(f)]
        best = max(((r.final, s) for s, r in results.items() if r), default=None)
        from backend.services import timetable as TT
        minutes = TT.weekly_minutes(cid, sid, gb.term.id if gb.term else None)
        att = gb.class_att(cid, sid)
        self.strip.set([(str(len(as_)), "tests and exams"), (fmt(avg(finals), "%"), "class average"),
                        (f"{round(len(passing) / len(finals) * 100)}%" if finals else "–", f"passing ({sc.pass_mark:g}%+)"),
                        (gb.students[best[1]].name.split()[0] if best else "–", "top of the subject"),
                        ("–" if att is None else f"{round(att)}%", "attendance in this subject"),
                        (f"{minutes // 60}h{minutes % 60:02d}" if minutes else "–", "timetabled each week")])

        marked = [a for a in as_ if gb.assess_stats(a).n]

        def timeline(ax):
            if not marked:
                return False
            ax.plot(range(len(marked)), [gb.assess_stats(a).mean for a in marked], marker="o", linewidth=2,
                    color=charts.subject_color(gb, sid), label="Class average")
            ax.axhline(sc.pass_mark, color=theme.PEN, linestyle=":", linewidth=1.2, label="Pass mark")
            charts.style(ax)
            ax.set_xticks(range(len(marked)))
            ax.set_xticklabels([f"{a.name}\n{a.date:%d %b}" for a in marked], fontsize=7)
            ax.legend(fontsize=7, frameon=False)
        self.c_time.draw_with(timeline, bottom=0.28)
        self.c_grades.draw_with(lambda ax: charts.counts(ax, sc.grades, [sum(1 for f in finals if sc.letter(f) == g) for g in sc.grades],
                                                         [theme.GREEN if r.min >= sc.pass_mark else theme.PEN for r in sc.rows])
                                if finals else False)

        rows, colors = [], {}
        for i, a in enumerate(as_):
            st = gb.assess_stats(a)
            rows.append([a.date.isoformat(), a.name + (f"  ·  {len(a.questions)} questions" if a.is_paper else ""), a.type,
                         f"{a.max_marks:g}", f"{st.n}/{len(studs)}", fmt(st.mean, "%"), fmt(st.hi, "%"), fmt(st.lo, "%"),
                         f"{round(st.pass_rate)}%" if st.pass_rate is not None else "–"])
            if st.pass_rate is not None and st.pass_rate < 50:
                colors[(i, 8)] = (theme.PEN, None)
        self.tests.set_rows(rows, [a.id for a in as_], center_from=2, colors=colors, fit_height=True)

        pos, of = gb.subject_positions(cid, sid)
        w = int(gb.settings.get("ca_weight", 40))
        self.cumulative.set_headers(["Student", "Reg. no.", *[f"{a.name}\n(/{a.max_marks:g})" for a in as_],
                                     f"Tests {w}%", f"Exams {100 - w}%", "Final %", "Grade", "Position", "Trend"])
        crows, ccolors = [], {}
        for i, s in enumerate(studs):
            r = results[s.id]
            marks = [(f"{gb.score(a, s.id):g}" if gb.has_score(a, s.id) else "ABS") for a in as_]
            for j, a in enumerate(as_):
                if gb.has_score(a, s.id):
                    p = gb.pct(a, s.id)
                    if not sc.passing(p):
                        ccolors[(i, 2 + j)] = (theme.PEN, None)
                else:
                    ccolors[(i, 2 + j)] = (theme.MUTED, None)
            crows.append([s.name, s.reg_no or "", *marks,
                          fmt(r.ca) if r else "–", fmt(r.ex) if r else "–", fmt(r.final) if r else "–",
                          sc.letter(r.final) if r else "–", f"{pos.get(s.id, '–')} of {of}",
                          TREND_WORDS[r.trend] if r and r.n >= 3 else "–"])
            if r and not sc.passing(r.final):
                ccolors[(i, len(as_) + 5)] = (theme.PEN, None)
        self.cumulative.set_rows(crows, [s.id for s in studs], center_from=1, colors=ccolors, fit_height=True)
        self.cumulative.resizeColumnsToContents()
        self.cumulative.setColumnWidth(0, max(190, self.cumulative.columnWidth(0)))
        self.cum_note.setText(f"Final % = tests {w}% + exams {100 - w}%. A student with no exam yet is marked from tests alone. "
                              "ABS means no mark was recorded. Double-click a student to open their profile.")

        ts = gb.topic_stats(cid, sid)
        self.topics_panel.setVisible(bool(ts))
        self.topics.set_rows([[t.topic, t.assessments, fmt(t.mean, "%"), f"{t.below} of {len(t.per)}",
                               ", ".join(f"{s.name} ({round(p)}%)" for s, p in t.per[:3])] for t in ts],
                             colors={(i, 2): (theme.PEN, None) for i, t in enumerate(ts) if not sc.passing(t.mean)},
                             center_from=1, fit_height=True, left=(4,))

    @safe
    def export(self):
        gb, cid, sid = self.app.gb, self.app.class_id, self.app.subject_id
        if not cid or not sid:
            return error(self, "Choose a class and subject first.")
        name = f"{gb.class_name(cid)}-{gb.subject_short(sid)}".replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Export subject results", f"{name}.xlsx", "Excel (*.xlsx)")
        if path:
            exports.write_xlsx(path, [exports.subject_sheet(gb, cid, sid, "marks", True)])
            info(self, f"Saved {path}")