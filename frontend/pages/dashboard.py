# /markbook/frontend/pages/dashboard.py
"""Class overview: key numbers, charts, top students and who needs attention."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QGridLayout, QPushButton

from backend import seed
from backend.grading import DIVISIONS
from backend.services import charts
from backend.services.analytics import TREND_WORDS, avg

from .. import theme
from ..widgets import Chart, Page, StatStrip, Table, fill_combo, fmt, label, panel, row, safe


class DashboardPage(Page):
    def __init__(self, app):
        super().__init__(app, "Class overview")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        self.actions.addWidget(label("Class"))
        self.actions.addWidget(self.cls)
        self.empty = panel(label("Start your markbook", "h2"),
                           label("Add your subjects, then your students, then record each test or exam. Charts build themselves as marks come in.", "muted", wrap=True),
                           row(self._btn("Add subjects", lambda: app.show_page("subjects"), True), self._btn("Add students", lambda: app.show_page("students")),
                               self._btn("Import from Excel", lambda: app.show_page("io")), self._btn("Try with sample data", self.sample), stretch_end=True))
        self.body.addWidget(self.empty)
        self.strip = StatStrip()
        self.body.addWidget(self.strip)
        g = QGridLayout()
        g.setSpacing(14)
        self.c_sub, self.c_time, self.c_spread = Chart(), Chart(), Chart()
        self.spread_title = label("Division spread", "h2")
        self.top = Table(["Pos", "Student", "Result"], stretch=1)
        self.top.doubleClicked.connect(lambda: app.open_student(self.top.current_id()))
        g.addWidget(panel(self.c_sub, title="Average by subject"), 0, 0)
        g.addWidget(panel(self.c_time, title="Class average across assessments"), 0, 1)
        g.addWidget(panel(self.spread_title, self.c_spread), 1, 0)
        g.addWidget(panel(self.top, title="Top of the class"), 1, 1)
        self.grid_holder = panel(layout="v")
        self.grid_holder.layout().addLayout(g)
        self.grid_holder.setObjectName("")
        self.body.addWidget(self.grid_holder)
        self.risk = Table(["Student", "Average", "Trend", "Why"], stretch=3)
        self.risk.doubleClicked.connect(lambda: app.open_student(self.risk.current_id()))
        self.body.addWidget(panel(self.risk, title="Needs attention"))
        self.body.addStretch(1)

    def _btn(self, text, fn, primary=False):
        b = QPushButton(text)
        if primary:
            b.setObjectName("primary")
        b.clicked.connect(lambda _=False: fn())
        return b

    @safe
    def sample(self):
        seed.add_sample()
        self.app.reload()

    def _class_changed(self):
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def refresh(self):
        gb, has = self.app.gb, bool(self.app.gb.students)
        self.empty.setVisible(not has)
        for w in (self.strip, self.grid_holder, self.risk.parentWidget()):
            w.setVisible(has)
        if not has:
            self.title.setText("Class overview")
            return
        cid = self.app.ensure_class()
        fill_combo(self.cls, self.app.class_items(), cid)
        sc, rank = gb.scale(cid), gb.ranking(cid)
        self.title.setText(gb.settings.get("school") or "Class overview")
        self.subtitle.setText(f"{gb.class_name(cid)} · {sc.label} · {gb.term_label}")
        overall = [r.summary.overall for r in rank]
        ca = avg(overall)
        passing = [p for p in overall if sc.passing(p)]
        att = gb.class_att(cid)
        self.strip.set([(str(len(gb.students_in(cid))), "students"), (str(len(gb.assessments_for(cid))), "tests and exams"),
                        (fmt(ca, "%"), f"class average, grade {sc.letter(ca)}"),
                        ("–" if not overall else f"{round(len(passing) / len(overall) * 100)}%", "passing overall"),
                        ("–" if att is None else f"{round(att)}%", "attendance")])
        subs = gb.class_subjects(cid)
        self.c_sub.draw_with(lambda ax: charts.bars(ax, [s.short for s in subs], [avg(r.summary.subs[s.id].final for r in rank if s.id in r.summary.subs) for s in subs],
                                                    colors=[charts.subject_color(gb, s.id) for s in subs], pass_mark=sc.pass_mark) if subs else False)
        as_ = [a for a in gb.assessments_for(cid) if gb.assess_stats(a).n]
        keys = list(dict.fromkeys((a.date, a.name.lower()) for a in as_))

        def time(ax):
            if not as_:
                return False
            for sub in subs:
                pts = [(keys.index((a.date, a.name.lower())), gb.assess_stats(a).mean) for a in as_ if a.subject_id == sub.id]
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", markersize=4, linewidth=2, color=charts.subject_color(gb, sub.id), label=sub.short)
            ax.axhline(sc.pass_mark, color=theme.PEN, linestyle=":")
            charts.style(ax)
            first = {k: next(a for a in as_ if (a.date, a.name.lower()) == k) for k in keys}
            ax.set_xticks(range(len(keys)))
            ax.set_xticklabels([f"{first[k].name}\n{first[k].date:%d %b}" for k in keys], fontsize=7)
            ax.legend(fontsize=7, frameon=False, ncol=4, loc="lower center")
        self.c_time.draw_with(time, bottom=0.2)
        if sc.div:
            self.spread_title.setText("Division spread")
            cnt = [sum(1 for r in rank if r.summary.div and r.summary.div.complete and r.summary.div.div == d) for d in DIVISIONS]
            inc = sum(1 for r in rank if not (r.summary.div and r.summary.div.complete))
            self.c_spread.draw_with(lambda ax: charts.counts(ax, [f"Div {d}" for d in DIVISIONS] + ["Incomplete"], cnt + [inc],
                                                             [theme.GREEN, theme.GREEN, theme.BLUE, theme.AMBER, theme.PEN, "#C9D6E6"]))
        else:
            self.spread_title.setText("Grade spread")
            self.c_spread.draw_with(lambda ax: charts.counts(ax, sc.grades, [sum(1 for p in overall if sc.letter(p) == g) for g in sc.grades],
                                                             [theme.GREEN if r.min >= sc.pass_mark else theme.PEN for r in sc.rows]))
        self.top.set_rows([[r.rank, r.student.name, r.summary.div.text() if r.summary.div and r.summary.div.complete else f"{fmt(r.summary.overall, '%')} · {sc.letter(r.summary.overall)}"]
                           for r in rank[:8]], [r.student.id for r in rank[:8]], center_from=2)
        risky = [(r, gb.at_risk(r.student)) for r in rank]
        risky = [(r, w) for r, w in risky if w]
        self.risk.set_rows([[r.student.name, fmt(r.summary.overall, "%"), TREND_WORDS[r.summary.trend], "; ".join(w)] for r, w in risky],
                           [r.student.id for r, _ in risky], fit_height=True, left=(3,))