# /markbook/frontend/pages/topics.py
"""Class-wide topic strengths and weaknesses for a subject."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from backend.services import charts

from .. import theme
from ..widgets import Chart, Page, Table, fill_combo, fmt, label, panel


class TopicsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Topics", "Which topics the class finds hardest, weakest first")
        self.cls, self.subj = QComboBox(), QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        self.subj.currentIndexChanged.connect(lambda _: self._draw())
        for w in (label("Class"), self.cls, label("Subject"), self.subj):
            self.actions.addWidget(w)
        self.chart = Chart(3)
        self.table = Table(["Topic", "Assessments", "Class average", "Grade", "Below pass", "Struggling most"], stretch=5)
        self.empty = label("No topics yet for this subject. Tag tests with topics, or mark a paper per question with a topic for each question.", "note", wrap=True)
        self.body.addWidget(self.empty)
        self.body.addWidget(panel(self.chart, title="Class average by topic"))
        self.body.addWidget(panel(self.table, label("On papers marked per question each question counts only toward its own topic; "
                                                    "on other tests the whole mark counts toward every tagged topic.", "muted", wrap=True)))
        self.body.addStretch(1)

    def _class_changed(self):
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def refresh(self):
        gb = self.app.gb
        cid = self.app.ensure_class()
        fill_combo(self.cls, self.app.class_items(), cid)
        fill_combo(self.subj, [(s.name, s.id) for s in gb.class_subjects(cid)] if cid else [], self.subj.currentData())
        self._draw()

    def _draw(self):
        gb, cid, sid = self.app.gb, self.app.class_id, self.subj.currentData()
        ts = gb.topic_stats(cid, sid) if cid and sid else []
        self.empty.setVisible(not ts)
        sc = gb.scale(cid) if cid else None
        self.chart.setMinimumHeight(max(200, 38 * len(ts) + 60))
        self.chart.draw_with(lambda ax: charts.bars(ax, [t.topic for t in ts], [t.mean for t in ts], horizontal=True, pass_mark=sc.pass_mark if sc else None)
                             if ts else False, bottom=0.12)
        self.table.set_rows([[t.topic, t.assessments, fmt(t.mean, "%"), sc.letter(t.mean), f"{t.below} of {len(t.per)}",
                              ", ".join(f"{s.name} ({round(p)}%)" for s, p in t.per[:3])] for t in ts],
                            colors={(i, 3): (theme.PEN, None) for i, t in enumerate(ts) if not sc.passing(t.mean)}, fit_height=True, left=(5,))