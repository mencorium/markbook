# /markbook/frontend/pages/mark_entry.py
"""One assessment: enter marks (total or per question), topic & question analysis, question-paper editor."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QPushButton, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from backend.services import assessments as A
from backend.services import charts, drafts, exports, reports
from backend.services.analytics import difficulty, discrimination_label
from backend.services.records import ConflictError

from .. import theme
from ..dialogs import AssessmentDialog
from ..widgets import Chart, Page, StatStrip, Table, confirm, error, fill_combo, fmt, heat, info, label, panel, row, safe

INVALID = QColor(theme.HEAT_LOW)


def _num(text: str):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return "bad"


class MarkEntryPage(Page):
    def __init__(self, app):
        super().__init__(app, "Assessment", actions_below=True)
        self.start_tab: str | None = None
        self.dirty = False
        self.paper_dirty = False
        self._loading = False
        back = QPushButton("← Tests && exams")
        back.clicked.connect(lambda _=False: app.show_page("assessments"))
        self.body.insertLayout(0, row(back, stretch_end=True))
        self.btn_pdf = QPushButton("Analysis report (PDF)")
        for text, fn, name, attr in [("Edit details", self.edit, None, None), ("Export Excel", lambda: self.export("xlsx"), None, None),
                                     ("Export CSV", lambda: self.export("csv"), None, None), (None, self.analysis_pdf, None, "btn_pdf"),
                                     ("Delete", self.delete, "danger", None)]:
            b = getattr(self, attr) if attr else QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(lambda _=False, f=fn: f())
            self.actions.addWidget(b)
        self.show_mode = QComboBox()
        self.show_mode.addItem("Export marks", "marks")
        self.show_mode.addItem("Export grades", "grades")
        self.actions.insertWidget(1, self.show_mode)
        self.strip = StatStrip()
        self.body.addWidget(self.strip)
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._tab_changed)
        self.body.addWidget(self.tabs, 1)
        # marks tab
        self.t_marks = QWidget()
        mv = QVBoxLayout(self.t_marks)
        mv.setContentsMargins(0, 8, 0, 0)
        self.draft_bar = QWidget()
        db_row = row(label("", "note", wrap=True), None, QPushButton("Discard recovered marks"))
        self.draft_note = db_row.itemAt(0).widget()
        self.draft_drop = db_row.itemAt(2).widget()
        self.draft_drop.clicked.connect(lambda _=False: self.discard_draft())
        self.draft_bar.setLayout(db_row)
        self.draft_bar.setVisible(False)
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(1500)
        self.autosave.timeout.connect(self._write_draft)
        self.sec_note = label("", "muted")
        self.grid = Table(["Student"], editable=True)
        self.grid.itemChanged.connect(self._cell_changed)
        save = QPushButton("Save marks")
        save.setObjectName("primary")
        save.clicked.connect(lambda _=False: self.save_marks())
        self.c_hist = Chart(2.4)
        mv.addWidget(panel(self.draft_bar, row(label("Marks", "h2"), None, save), self.sec_note, self.grid,
                           label("Empty box = not answered (or absent if the whole row is empty); 0 = answered and scored nothing.", "muted", wrap=True)))
        mv.addWidget(panel(self.c_hist, title="Score distribution"))
        mv.addStretch(1)
        self.tabs.addTab(self.t_marks, "Marks")
        # analysis tab
        self.t_an = QWidget()
        av = QVBoxLayout(self.t_an)
        av.setContentsMargins(0, 8, 0, 0)
        self.an_strip = StatStrip()
        self.c_topics = Chart(2.6)
        self.tbl_topics = Table(["Topic", "Questions", "Marks", "Answered", "Average", "Difficulty", "Students below pass"], stretch=6)
        self.tbl_q = Table(["Question", "Topic", "Marks", "Answered by", "Average", "Difficulty", "Separates strong/weak", "Full marks", "Scored 0"], stretch=1)
        self.heat = Table(["Student"])
        self.heat.doubleClicked.connect(lambda: app.open_student(self.heat.current_id()))
        av.addWidget(self.an_strip)
        av.addWidget(panel(self.c_topics, title="Topics, hardest first"))
        av.addWidget(panel(self.tbl_topics, title="Topic performance"))
        av.addWidget(panel(self.tbl_q, label("Average: mean % on the question (skipped compulsory = 0, skipped choice left out). "
                                             "'Separates strong/weak' compares the top and bottom 27%; weak or negative often means an unclear question or a marking slip.",
                                             "muted", wrap=True), title="Question analysis"))
        av.addWidget(panel(self.heat, label("Red below 40%, amber 40–69%, green 70%+. — means the student chose not to answer that topic.", "muted"),
                           title="Each student by topic"))
        av.addStretch(1)
        self.tabs.addTab(self.t_an, "Topic && question analysis")
        # paper tab
        self.t_paper = QWidget()
        pv = QVBoxLayout(self.t_paper)
        pv.setContentsMargins(0, 8, 0, 0)
        self.tbl_sec = Table(["Section name", "Rule"], stretch=0, editable=True)
        self.tbl_sec.itemChanged.connect(self._paper_edited)
        self.tbl_pq = Table(["Question", "Section", "Topic", "Marks"], stretch=2, editable=True)
        self.tbl_pq.itemChanged.connect(self._paper_edited)
        self.paper_total = label("", "h2")
        self.legacy_note = label("", "note", wrap=True)
        b_addq, b_delq, b_adds, b_dels = QPushButton("Add question"), QPushButton("Remove question"), QPushButton("Add section"), QPushButton("Remove section")
        b_save, self.b_stop = QPushButton("Save question paper"), QPushButton("Stop marking per question")
        b_save.setObjectName("primary")
        self.b_stop.setObjectName("danger")
        for b, f in [(b_addq, self.add_question), (b_delq, self.remove_question), (b_adds, self.add_section), (b_dels, self.remove_section),
                     (b_save, self.save_paper), (self.b_stop, self.stop_paper)]:
            b.clicked.connect(lambda _=False, fn=f: fn())
        pv.addWidget(panel(label("List each question with the topic it tests and its marks. Split a question into parts (2a, 2b) when the parts test different topics. "
                                 "Use a second section for choice questions, e.g. 'Section B — answer any 2'.", "muted", wrap=True),
                           self.legacy_note, label("Sections", "h2"), self.tbl_sec, row(b_adds, b_dels, None),
                           label("Questions", "h2"), self.tbl_pq, row(b_addq, b_delq, None, self.paper_total), row(b_save, self.b_stop, None),
                           title="Question paper"))
        pv.addStretch(1)
        self.tabs.addTab(self.t_paper, "Mark per question")

    # ---------------- state ----------------
    @property
    def a(self):
        return self.app.gb.by_id.get(self.app.assessment_id)

    def can_leave(self) -> bool:
        if self.dirty:
            self.autosave.stop()
            self._write_draft()
            if not confirm(self, "These marks are not saved to the database yet. Leave anyway?\n\n"
                                 "They are kept as a draft and will be offered back when you open this assessment again."):
                return False
        if self.paper_dirty and self.a and self.a.is_paper and not confirm(self, "Discard changes to the question paper?"):
            return False
        self.dirty = self.paper_dirty = False
        return True

    def refresh(self):
        a = self.a
        if not a:
            return
        gb = self.app.gb
        self.title.setText(a.name)
        self.subtitle.setText(f"{gb.subject_name(a.subject_id)} · {gb.class_name(a.class_id)} · {a.type} · {a.date:%d %b %Y} · out of {a.max_marks:g}"
                              + (f" · {len(a.questions)} questions" if a.is_paper else "") + (f" · {', '.join(a.topics)}" if a.topics else ""))
        st = gb.assess_stats(a)
        self.strip.set([(f"{st.n}/{len(self.roster())}", "marked"), (fmt(st.mean, "%"), "mean"), (fmt(st.hi, "%"), "highest"), (fmt(st.lo, "%"), "lowest"),
                        ("–" if st.pass_rate is None else f"{round(st.pass_rate)}%", f"passed ({gb.scale(a.class_id).pass_mark:g}%+)")])
        self.tabs.setTabVisible(1, a.is_paper)
        self.tabs.setTabText(2, "Question paper" if a.is_paper else "Mark per question")
        self.btn_pdf.setVisible(a.is_paper)
        self._load_grid()
        self._load_paper()
        if a.is_paper:
            self._load_analysis()
        self._draw_hist()
        if self.start_tab:
            self.tabs.setCurrentIndex({"marks": 0, "analysis": 1, "paper": 2}.get(self.start_tab, 0))
            self.start_tab = None

    def roster(self):
        gb, a = self.app.gb, self.a
        ids = set(gb.totals.get(a.id, {})) | set(gb.qmarks.get(a.id, {}))
        moved = [gb.students[i] for i in ids if i in gb.students and gb.students[i].class_id != a.class_id]
        return gb.students_in(a.class_id) + sorted(moved, key=lambda s: s.name)

    def _tab_changed(self, i):
        pass

    # ---------------- marks grid ----------------
    def _load_grid(self):
        gb, a = self.app.gb, self.a
        self._loading = True
        studs = self.roster()
        if a.is_paper:
            heads = ["Student", *[f"{q.label}\n{q.topic or '—'}\n/{q.max:g}{' · choice' if a.section_of(q).pick else ''}" for q in a.questions], f"Total\n/{a.max_marks:g}", "%", "Grade"]
            notes = [f"{s.name or 'Paper'}: answer any {s.pick} of {sum(1 for q in a.questions if a.section_of(q).id == s.id)}" for s in a.sections if s.pick]
            self.sec_note.setText(" · ".join(notes))
        else:
            heads = ["Student", f"Score (/{a.max_marks:g})", "%", "Grade"]
            self.sec_note.setText("")
        self.grid.set_headers(heads)
        self.grid.setRowCount(0)
        self.grid.setRowCount(len(studs))
        qrows = gb.qmarks.get(a.id, {})
        for r, s in enumerate(studs):
            name = QTableWidgetItem(s.name + ("  (moved class)" if s.class_id != a.class_id else ""))
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name.setData(Qt.ItemDataRole.UserRole, s.id)
            self.grid.setItem(r, 0, name)
            if a.is_paper:
                for c, q in enumerate(a.questions, start=1):
                    v = qrows.get(s.id, {}).get(q.id)
                    it = QTableWidgetItem("" if v is None else f"{v:g}")
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.grid.setItem(r, c, it)
            else:
                v = gb.score(a, s.id)
                it = QTableWidgetItem("" if v is None else f"{v:g}")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.grid.setItem(r, 1, it)
            self._update_row(r)
        # what the marks were when this page was loaded: checked on save so two windows cannot overwrite each other
        self.baseline = {self.grid.item(r, 0).data(Qt.ItemDataRole.UserRole): gb.score(a, self.grid.item(r, 0).data(Qt.ItemDataRole.UserRole))
                         for r in range(self.grid.rowCount())}
        self.grid.resizeColumnsToContents()
        self.grid.setColumnWidth(0, max(200, self.grid.columnWidth(0)))
        self.grid.fit(40)
        self._loading = False
        self.dirty = False
        self._recover_draft()

    def _update_row(self, r: int):
        gb, a = self.app.gb, self.a
        sc = gb.scale(a.class_id)
        n = len(a.questions)
        if a.is_paper:
            rowvals, bad = {}, False
            for c, q in enumerate(a.questions, start=1):
                it = self.grid.item(r, c)
                v = _num(it.text() if it else "")
                invalid = v == "bad" or (v is not None and not 0 <= v <= q.max)
                if it:
                    it.setBackground(INVALID if invalid else QColor(0, 0, 0, 0))
                    it.setToolTip(f"Enter 0 to {q.max:g}" if invalid else "")
                bad |= invalid
                if v not in (None, "bad") and not invalid:
                    rowvals[q.id] = v
            total, over = gb.paper_total(a, rowvals)
            sid = self.grid.item(r, 0).data(Qt.ItemDataRole.UserRole)
            if total is None and not rowvals and gb.score(a, sid) is not None and sid not in gb.qmarks.get(a.id, {}):
                total = gb.score(a, sid)              # total entered before the paper was split
            p = None if total is None else total / a.max_marks * 100
            cells = [fmt(total) + (" ⚠" if over else ""), fmt(p), sc.letter(p)]
            start = n + 1
        else:
            it = self.grid.item(r, 1)
            v = _num(it.text() if it else "")
            invalid = v == "bad" or (v is not None and not 0 <= v <= a.max_marks)
            if it:
                it.setBackground(INVALID if invalid else QColor(0, 0, 0, 0))
            p = None if v in (None, "bad") or invalid else v / a.max_marks * 100
            cells, start = [fmt(p), sc.letter(p)], 2
        for k, text in enumerate(cells):
            it = QTableWidgetItem(text)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if a.is_paper and k == 0 and "⚠" in text:
                it.setToolTip("More choice questions answered than allowed — the best ones are counted.")
            if k == len(cells) - 1 and p is not None and not sc.passing(p):
                it.setForeground(QColor(theme.PEN))
            self.grid.setItem(r, start + k, it)

    def _cell_changed(self, item):
        if self._loading:
            return
        self._loading = True
        self._update_row(item.row())
        self._loading = False
        self.dirty = True
        self.autosave.start()                    # autosaved to a draft a moment after typing stops

    def _collect(self) -> tuple[dict, list[str]]:
        """Read the grid: {student_id: score} or {student_id: {question_id: score}}, plus any unreadable cells."""
        a, rows, bad = self.a, {}, []
        for r in range(self.grid.rowCount()):
            name_item = self.grid.item(r, 0)
            if name_item is None:
                continue
            sid = name_item.data(Qt.ItemDataRole.UserRole)
            if a.is_paper:
                row_ = {}
                for c, q in enumerate(a.questions, start=1):
                    cell = self.grid.item(r, c)
                    v = _num(cell.text() if cell else "")
                    if v == "bad":
                        bad.append(f"{name_item.text()} — {q.label}")
                    else:
                        row_[q.id] = v
                rows[sid] = row_
            else:
                cell = self.grid.item(r, 1)
                v = _num(cell.text() if cell else "")
                if v == "bad":
                    bad.append(name_item.text())
                else:
                    rows[sid] = v
        return rows, bad

    def _write_draft(self):
        a = self.a
        if not a or not self.dirty:
            return
        values, _ = self._collect()
        try:
            drafts.save_draft(a.id, "paper" if a.is_paper else "total", values)
        except OSError as e:                     # a draft is a convenience: never interrupt marking
            self.draft_bar.setVisible(False)
            print("could not autosave draft:", e)

    def _recover_draft(self):
        """After filling the grid from the database, put back anything typed but never saved."""
        a = self.a
        draft = drafts.load_draft(a.id)
        self.draft_bar.setVisible(False)
        if not draft or draft["kind"] != ("paper" if a.is_paper else "total"):
            return
        changed = 0
        self._loading = True
        for r in range(self.grid.rowCount()):
            sid = self.grid.item(r, 0).data(Qt.ItemDataRole.UserRole)
            if sid not in draft["values"]:
                continue
            saved = draft["values"][sid]
            cells = [(c, saved.get(q.id)) for c, q in enumerate(a.questions, start=1)] if a.is_paper else [(1, saved)]
            for c, v in cells:
                text = "" if v is None else f"{float(v):g}"
                item = self.grid.item(r, c)
                if item is not None and item.text() != text:
                    item.setText(text)
                    changed += 1
            self._update_row(r)
        self._loading = False
        if changed:
            self.dirty = True
            self.draft_note.setText(f"{changed} mark{'s' if changed != 1 else ''} you typed on {draft['saved_at']:%d %b at %H:%M} "
                                    "were never saved. They are back in the grid below — press Save marks to keep them.")
            self.draft_bar.setVisible(True)
        else:
            drafts.delete_draft(a.id)            # the draft matches what is stored: nothing to recover

    @safe
    def discard_draft(self):
        if confirm(self, "Discard the recovered marks and show what is stored in the database?"):
            drafts.delete_draft(self.a.id)
            self.dirty = False
            self.draft_bar.setVisible(False)
            self._load_grid()

    @safe
    def save_marks(self):
        a = self.a
        self.autosave.stop()
        values, bad = self._collect()
        if bad:
            return error(self, "These entries are not numbers:\n\n" + "\n".join(bad[:8])
                         + (f"\n…and {len(bad) - 8} more" if len(bad) > 8 else ""))
        try:
            if a.is_paper:
                already = self.app.gb.qmarks.get(a.id, {})
                rows = {sid: row_ for sid, row_ in values.items() if any(v is not None for v in row_.values()) or sid in already}
                A.save_question_marks(a.id, rows, expected=self.baseline)
            else:
                A.save_totals(a.id, values, expected=self.baseline)
        except ConflictError as e:
            self._write_draft()                  # keep what was typed before showing the current marks
            if confirm(self, f"{e}\n\nReload now? The marks you typed are kept and put back in the grid."):
                self.app.reload()
            return
        self.dirty = False
        drafts.delete_draft(a.id)                # saved for real: the draft is no longer needed
        self.draft_bar.setVisible(False)
        self.app.reload()
        info(self, "Marks saved.")

    def _draw_hist(self):
        gb, a = self.app.gb, self.a
        st, pm = gb.assess_stats(a), gb.scale(a.class_id).pass_mark
        bins = [0] * 10
        for p in st.pcts:
            bins[min(9, int(p // 10))] += 1
        self.c_hist.draw_with(lambda ax: charts.counts(ax, [f"{i * 10}–{100 if i == 9 else i * 10 + 9}" for i in range(10)], bins,
                                                       [theme.GREEN if i * 10 >= pm else theme.PEN for i in range(10)]) if st.pcts else False)

    # ---------------- analysis ----------------
    def _load_analysis(self):
        gb, a = self.app.gb, self.a
        pa, sc = gb.paper_analysis(a), gb.scale(a.class_id)
        if not pa.sitters:
            self.an_strip.set([("0", "students with per-question marks — enter marks on the Marks tab")])
            for t in (self.tbl_topics, self.tbl_q, self.heat):
                t.setRowCount(0)
            self.c_topics.draw_with(lambda ax: False)
            return
        tagged = [t for t in pa.topics if t.facility is not None and t.topic != "Untagged"]
        choice = sorted((q for q in pa.questions if q.choice and q.marked), key=lambda q: -(q.att_rate or 0))
        stats = [(str(len(pa.sitters)), "students sat the paper")]
        if tagged:
            stats.append((tagged[0].topic, f"hardest topic · {fmt(tagged[0].facility, '%')} average"))
            if len(tagged) > 1:
                stats.append((tagged[-1].topic, f"easiest topic · {fmt(tagged[-1].facility, '%')} average"))
        if choice:
            stats += [(choice[0].q.label, f"most chosen · {round(choice[0].att_rate)}% answered"), (choice[-1].q.label, f"least chosen · {round(choice[-1].att_rate)}%")]
        self.an_strip.set(stats)
        self.c_topics.setMinimumHeight(max(200, 46 * len(pa.topics) + 60))
        self.c_topics.draw_with(lambda ax: charts.bars(ax, [t.topic for t in pa.topics], [t.facility for t in pa.topics], horizontal=True,
                                                       second=("Students who answered %", [t.att_rate for t in pa.topics])), bottom=0.12)
        names = lambda xs: ", ".join(gb.students[i].name for i, _ in xs[:5] if i in gb.students) + (f" and {len(xs) - 5} more" if len(xs) > 5 else "")
        self.tbl_topics.set_rows([[t.topic, ", ".join(t.questions), fmt(t.marks), f"{t.attempted}/{len(pa.sitters)}", fmt(t.facility, "%"), difficulty(t.facility),
                                   f"{len(t.struggling)}: {names(t.struggling)}" if t.struggling else "none"] for t in pa.topics],
                                 colors={(i, 5): ({"Hard": theme.PEN, "Moderate": theme.AMBER, "Easy": theme.GREEN}.get(difficulty(t.facility)), None) for i, t in enumerate(pa.topics)},
                                 fit_height=True, left=(6,))
        self.tbl_q.set_rows([[q.q.label + (f" ({a.section_of(q.q).name or 'choice'})" if q.choice else ""), q.q.topic or "—", fmt(q.q.max),
                              f"{q.attempted} ({fmt(q.att_rate, '%')})" if q.marked else "–", fmt(q.facility, "%") if q.marked else "not marked yet",
                              difficulty(q.facility), "needs 6+ students" if q.marked and q.disc is None else ("" if not q.marked else f"{discrimination_label(q.disc)} ({q.disc:.2f})"),
                              q.full, q.zero] for q in pa.questions], fit_height=True)
        studs = sorted((s for s in self.roster() if s.id in pa.sitters), key=lambda s: -(gb.score(a, s.id) or 0))
        self.heat.set_headers(["Student", *[t.topic for t in pa.topics], "Total", "Needs help with"], stretch=len(pa.topics) + 2)
        rows, colors = [], {}
        for r, s in enumerate(studs):
            vals = [t.per.get(s.id) for t in pa.topics]
            weak = [t.topic for t, v in zip(pa.topics, vals) if v is not None and not sc.passing(v)]
            rows.append([s.name, *["—" if v is None else f"{round(v)}%" for v in vals], fmt(gb.score(a, s.id)), ", ".join(weak) or "—"])
            for c, v in enumerate(vals, start=1):
                if v is not None:
                    colors[(r, c)] = (None, heat(v))
        self.heat.set_rows(rows, [s.id for s in studs], colors=colors, fit_height=True, left=(len(pa.topics) + 2,))

    # ---------------- question paper editor ----------------
    def _load_paper(self):
        a = self.a
        if a.is_paper:
            self.p_sections = [{"key": s.id, "name": s.name, "pick": s.pick} for s in a.sections]
            self.p_questions = [{"id": q.id, "label": q.label, "topic": q.topic, "max": q.max, "section_key": q.section_id} for q in a.questions]
        else:
            self.p_sections = [{"key": "new0", "name": "", "pick": None}]
            self.p_questions = [{"id": None, "label": f"Q{i}", "topic": "", "max": "", "section_key": "new0"} for i in range(1, 6)]
        n_total = len(self.app.gb.totals.get(a.id, {}))
        self.legacy_note.setVisible(not a.is_paper and n_total > 0)
        self.legacy_note.setText(f"{n_total} students already have a total mark. Those totals stay until you enter per-question marks for them.")
        self.b_stop.setVisible(a.is_paper)
        self._draw_paper()
        self.paper_dirty = False

    def _read_paper(self):
        for r, s in enumerate(self.p_sections):
            it = self.tbl_sec.item(r, 0)
            s["name"] = it.text() if it else s["name"]
            w = self.tbl_sec.cellWidget(r, 1)
            s["pick"] = w.currentData() if w else s["pick"]
        for r, q in enumerate(self.p_questions):
            for c, k in [(0, "label"), (2, "topic"), (3, "max")]:
                it = self.tbl_pq.item(r, c)
                if it:
                    q[k] = it.text()
            w = self.tbl_pq.cellWidget(r, 1)
            if w:
                q["section_key"] = w.currentData()

    def _draw_paper(self):
        self._loading = True
        self.tbl_sec.clear_cell_widgets()
        self.tbl_pq.clear_cell_widgets()
        self.tbl_sec.setRowCount(len(self.p_sections))
        for r, s in enumerate(self.p_sections):
            self.tbl_sec.setItem(r, 0, QTableWidgetItem(s["name"]))
            n = sum(1 for q in self.p_questions if q["section_key"] == s["key"])
            combo = QComboBox()
            fill_combo(combo, [(f"Answer any {k} of {n}", k) for k in range(1, n)], s["pick"], blank="Answer all questions")
            combo.currentIndexChanged.connect(lambda _: self._paper_edited())
            self.tbl_sec.setCellWidget(r, 1, combo)
        self.tbl_sec.fit()
        self.tbl_pq.setRowCount(len(self.p_questions))
        secs = [(s["name"] or f"Section {i + 1}", s["key"]) for i, s in enumerate(self.p_sections)]
        for r, q in enumerate(self.p_questions):
            self.tbl_pq.setItem(r, 0, QTableWidgetItem(str(q["label"])))
            self.tbl_pq.setItem(r, 2, QTableWidgetItem(str(q["topic"])))
            self.tbl_pq.setItem(r, 3, QTableWidgetItem("" if q["max"] in ("", None) else f"{float(q['max']):g}"))
            combo = QComboBox()
            fill_combo(combo, secs, q["section_key"])
            combo.currentIndexChanged.connect(lambda _: self._section_moved())
            self.tbl_pq.setCellWidget(r, 1, combo)
        self.tbl_pq.fit(30)
        self._loading = False
        self._update_total()

    def _update_total(self):
        from backend.paper import Q, Sec, paper_max
        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0
        secs = [Sec(s["key"], s["name"], s["pick"]) for s in self.p_sections]
        qs = [Q(i, q["label"], q["topic"], num(q["max"]), q["section_key"]) for i, q in enumerate(self.p_questions)]
        self.paper_total.setText(f"Paper total: {paper_max(secs, qs):g} marks")

    def _paper_edited(self, *_):
        if self._loading:
            return
        self._read_paper()
        self._update_total()
        self.paper_dirty = True

    def _section_moved(self):
        if self._loading:
            return
        self._read_paper()
        self.paper_dirty = True
        self._draw_paper()

    def add_question(self):
        self._read_paper()
        labels = {str(q["label"]).lower() for q in self.p_questions}
        n = len(self.p_questions) + 1
        while f"q{n}" in labels:
            n += 1
        last = self.p_questions[-1] if self.p_questions else None
        self.p_questions.append({"id": None, "label": f"Q{n}", "topic": "", "max": last["max"] if last else "", "section_key": self.p_sections[-1]["key"]})
        self.paper_dirty = True
        self._draw_paper()

    def remove_question(self):
        r = self.tbl_pq.currentRow()
        if r < 0:
            return error(self, "Select a question first.")
        self._read_paper()
        self.p_questions.pop(r)
        self.paper_dirty = True
        self._draw_paper()

    def add_section(self):
        self._read_paper()
        if len(self.p_sections) == 1 and not self.p_sections[0]["name"]:
            self.p_sections[0]["name"] = "Section A"
        self.p_sections.append({"key": f"new{len(self.p_sections)}x", "name": f"Section {chr(65 + len(self.p_sections))}", "pick": None})
        self.paper_dirty = True
        self._draw_paper()

    def remove_section(self):
        r = self.tbl_sec.currentRow()
        if r < 0 or len(self.p_sections) < 2:
            return error(self, "Select a section to remove (a paper needs at least one).")
        self._read_paper()
        gone = self.p_sections.pop(r)
        for q in self.p_questions:
            if q["section_key"] == gone["key"]:
                q["section_key"] = self.p_sections[0]["key"]
        self.paper_dirty = True
        self._draw_paper()

    @safe
    def save_paper(self):
        self._read_paper()
        qs = []
        for q in self.p_questions:
            try:
                mx = float(q["max"])
            except (TypeError, ValueError):
                return error(self, f"{q['label'] or 'A question'} needs marks greater than 0.")
            qs.append({**q, "max": mx})
        A.save_paper(self.a.id, self.p_sections, qs)
        self.paper_dirty = False
        self.start_tab = "marks"
        self.app.reload()
        info(self, "Question paper saved — now enter marks per question.")

    @safe
    def stop_paper(self):
        if confirm(self, "Stop marking per question? Each student's total is kept, but per-question marks and the topic analysis are deleted."):
            A.remove_paper(self.a.id)
            self.start_tab = "marks"
            self.app.reload()

    # ---------------- actions ----------------
    @safe
    def edit(self):
        gb, a = self.app.gb, self.a
        d = AssessmentDialog(self, sorted(gb.subjects.values(), key=lambda s: s.name), sorted(gb.classes.values(), key=lambda c: c.name), a)
        if d.exec():
            v = d.values()
            v.pop("paper")
            A.save_assessment(a.id, **v)
            self.app.reload()

    @safe
    def delete(self):
        if confirm(self, "Delete this assessment and all its marks?"):
            A.delete_assessment(self.a.id)
            self.dirty = self.paper_dirty = False
            self.app.gb = self.app.gb.load()
            self.app.show_page("assessments")

    @safe
    def export(self, kind: str):
        if self.dirty:
            return error(self, "Save marks first, then export.")
        a, gb = self.a, self.app.gb
        name = f"{gb.class_name(a.class_id)}-{gb.subject_short(a.subject_id)}-{a.name}".replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Export mark sheet", f"{name}.{kind}", "Excel (*.xlsx)" if kind == "xlsx" else "CSV (*.csv)")
        if not path:
            return
        sheets = exports.single_sheets(gb, a.id, self.show_mode.currentData(), True)
        exports.write_xlsx(path, sheets) if kind == "xlsx" else exports.write_csv(path, sheets[0])
        info(self, f"Saved {path}")

    @safe
    def analysis_pdf(self):
        a, gb = self.a, self.app.gb
        path, _ = QFileDialog.getSaveFileName(self, "Save analysis", f"{a.name}-analysis.pdf".replace(" ", "-"), "PDF (*.pdf)")
        if path:
            reports.exam_analysis(gb, a.id, path)
            info(self, f"Saved {path}")