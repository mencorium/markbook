# /markbook/frontend/pages/groups.py
"""Groups for subject work: generate them by a rule, see the balance, then move anyone by hand."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QFileDialog, QMenu, QPushButton

from backend.services import exports
from backend.services import groups as G

from .. import theme
from ..dialogs import GroupRuleDialog, GroupSetDialog
from ..widgets import Page, Table, confirm, error, fill_combo, fmt, info, label, panel, row, safe


class GroupsPage(Page):
    def __init__(self, app):
        super().__init__(app, "Groups", "Groups for subject work, balanced by results rather than by hand",
                         actions_below=True)
        self.plan: G.Plan | None = None
        self.cls, self.subj, self.sets = QComboBox(), QComboBox(), QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        self.subj.currentIndexChanged.connect(self._subject_changed)
        self.sets.currentIndexChanged.connect(lambda _: self._show_set())
        make = QPushButton("Make groups…")
        make.setObjectName("primary")
        make.clicked.connect(lambda _=False: self.make())
        for w in (label("Class"), self.cls, label("Subject"), self.subj, label("Set"), self.sets, make):
            self.actions.addWidget(w)

        self.note = label("", "notice", wrap=True)
        self.warn = label("", "note", wrap=True)
        self.table = Table(["Group", "Students", "Average", "Strong", "Members"], stretch=4)
        self.table.doubleClicked.connect(lambda: self.rename())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        rename, export, delete = QPushButton("Rename group"), QPushButton("Export (Excel)"), QPushButton("Delete this set")
        delete.setObjectName("danger")
        rename.clicked.connect(lambda _=False: self.rename())
        export.clicked.connect(lambda _=False: self.export())
        delete.clicked.connect(lambda _=False: self.delete_set())
        self.body.addWidget(panel(self.note, self.warn, self.table,
                                  label("Right-click a group to move a student into it. Double-click to rename.", "muted"),
                                  row(rename, export, None, delete), title="The groups"))

        self.members = Table(["Student", "Group", "Mark in this subject", "Grade"], stretch=0)
        self.members.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.members.customContextMenuRequested.connect(self._member_menu)
        self.body.addWidget(panel(self.members, label("Right-click a student to move them to another group.", "muted"),
                                  title="Every student"))

        self.rules = Table(["Rule", "Students"], stretch=1)
        add_rule, drop_rule = QPushButton("Add a rule"), QPushButton("Remove rule")
        drop_rule.setObjectName("danger")
        add_rule.clicked.connect(lambda _=False: self.add_rule())
        drop_rule.clicked.connect(lambda _=False: self.drop_rule())
        self.body.addWidget(panel(self.rules, row(add_rule, drop_rule, None),
                                  label("Students kept together or apart are honoured every time groups are made for this "
                                        "subject.", "muted", wrap=True), title="Keep together / keep apart"))
        self.body.addStretch(1)

    # ---------------- selection ----------------
    def _class_changed(self):
        self.app.class_id = self.cls.currentData()
        self.refresh()

    def _subject_changed(self):
        self.app.subject_id = self.subj.currentData()
        self._load_sets()

    def _term_id(self):
        return self.app.gb.term.id if self.app.gb.term else None

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
        self._load_sets()

    def _load_sets(self):
        cid, sid = self.app.class_id, self.app.subject_id
        found = G.list_sets(cid, sid, self._term_id()) if cid and sid else []
        fill_combo(self.sets, [(f"{x.name} · {len(x.groups)} groups", x.id) for x in found], self.sets.currentData())
        self._show_set()
        self._load_rules()

    # ---------------- display ----------------
    def _current(self) -> G.GroupSetInfo | None:
        sid = self.sets.currentData()
        return G.get_set(sid) if sid else None

    def _show_set(self):
        gb = self.app.gb
        gs = self._current()
        self.warn.setVisible(False)
        if gs is None:
            self.note.setObjectName("note")
            self.note.setStyleSheet("")
            self.note.setText("No groups yet for this subject and term. Press “Make groups…” and Markbook will form them "
                              "from the class results — balanced, banded or at random — then you can move anyone by hand.")
            self.table.set_rows([])
            self.members.set_rows([])
            self.subtitle.setText("Groups for subject work, balanced by results rather than by hand")
            return
        ranked = {r.student_id: r for r in G.rank_students(gb, gs.class_id, gs.subject_id, gs.rules.get("strong_grade"))}
        sc = gb.scale(gs.class_id)
        averages = []
        rows, ids = [], []
        for g in gs.groups:
            marks = [ranked[s].mark for s in g.members if s in ranked and ranked[s].mark is not None]
            avg = sum(marks) / len(marks) if marks else None
            averages.append(avg)
            strong = sum(1 for s in g.members if s in ranked and ranked[s].strong)
            names = ", ".join(ranked[s].name for s in g.members if s in ranked)
            rows.append([g.name, len(g.members), fmt(avg, "%"), strong, names])
            ids.append(g.id)
        self.table.set_rows(rows, ids, center_from=1, fit_height=True, left=(4,))
        real = [a for a in averages if a is not None]
        spread = max(real) - min(real) if len(real) > 1 else 0
        self.note.setObjectName("noticeDone")
        self.note.setStyleSheet("")
        how = G.STRATEGIES.get(gs.made_by, gs.made_by).split("—")[0].strip().lower()
        self.note.setText(f"“{gs.name}” — {len(gs.groups)} groups of {gs.size} students, made {how}. "
                          f"Group averages run from {min(real):.0f}% to {max(real):.0f}%, a spread of {spread:.0f} points."
                          if real else f"“{gs.name}” — {len(gs.groups)} groups, no marks in this subject yet.")
        self.subtitle.setText(f"{gb.class_name(gs.class_id)} · {gb.subject_name(gs.subject_id)} · {gb.term_label}")
        where = {s: g.name for g in gs.groups for s in g.members}
        people = sorted(ranked.values(), key=lambda r: r.name.lower())
        self.members.set_rows([[r.name, where.get(r.student_id, "— not in a group —"), fmt(r.mark, "%"),
                                sc.letter(r.mark) if r.mark is not None else "–"] for r in people],
                              [r.student_id for r in people], center_from=1,
                              colors={(i, 1): (theme.AMBER, None) for i, r in enumerate(people)
                                      if r.student_id not in where}, fit_height=True)

    def _load_rules(self):
        gb, cid = self.app.gb, self.app.class_id
        found = G.list_rules(cid, self.app.subject_id) if cid else []
        name = lambda sid: gb.students[sid].name if sid in gb.students else "(removed student)"
        self.rules.set_rows([["Keep together" if kind == G.TOGETHER else "Keep apart", f"{name(a)}  and  {name(b)}"]
                             for _, kind, a, b in found], [r[0] for r in found], center_from=2, fit_height=True)

    # ---------------- actions ----------------
    @safe
    def make(self):
        gb, cid, sid = self.app.gb, self.app.class_id, self.app.subject_id
        if not cid or not sid:
            return error(self, "Choose a class and subject first.")
        if not gb.students_in(cid):
            return error(self, "This class has no students yet.")
        d = GroupSetDialog(self, gb, cid, sid)
        if not d.exec():
            return
        v = d.values()
        plan = G.plan_groups(gb, cid, sid, strategy=v["strategy"], size=v["size"], count=v["count"],
                             min_strong=v["min_strong"], strong_grade=v["strong_grade"])
        gs = G.save_set(None, name=v["name"], class_id=cid, subject_id=sid, term_id=self._term_id(),
                        groups=plan.groups, made_by=v["strategy"],
                        rules={k: v[k] for k in ("size", "count", "min_strong", "strong_grade")})
        self.app.reload()
        i = self.sets.findData(gs.id)
        if i >= 0:
            self.sets.setCurrentIndex(i)
        self._show_set()
        if plan.warnings:
            self.warn.setVisible(True)
            self.warn.setText("  ".join(plan.warnings))

    def _menu(self, pos):
        gid = self.table.current_id()
        if gid is None:
            return
        m = QMenu(self)
        act_rename = m.addAction("Rename group")
        chosen = m.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_rename:
            self.rename()

    def _member_menu(self, pos):
        gs, sid = self._current(), self.members.current_id()
        if gs is None or sid is None:
            return
        m = QMenu(self)
        actions = {m.addAction(f"Move to {g.name}"): g.id for g in gs.groups if sid not in g.members}
        m.addSeparator()
        out = m.addAction("Take out of every group")
        chosen = m.exec(self.members.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        self._move(gs.id, sid, None if chosen is out else actions.get(chosen))

    @safe
    def _move(self, set_id: int, student_id: int, group_id: int | None):
        G.move_student(set_id, student_id, group_id)
        self._show_set()

    @safe
    def rename(self):
        gid = self.table.current_id()
        if gid is None:
            return error(self, "Select a group first.")
        gs = self._current()
        old = next((g.name for g in gs.groups if g.id == gid), "")
        from ..dialogs import TextDialog
        d = TextDialog(self, "Rename group", "Group name", old)
        if d.exec():
            G.rename_group(gid, d.value())
            self._show_set()

    @safe
    def delete_set(self):
        gs = self._current()
        if gs is None:
            return error(self, "There is no set of groups to delete.")
        if confirm(self, f"Delete “{gs.name}”?\n\nThe groups go; no marks are affected. An assignment that used them "
                         "keeps the marks already entered."):
            G.delete_set(gs.id)
            self.app.reload()

    @safe
    def add_rule(self):
        gb, cid = self.app.gb, self.app.class_id
        studs = gb.students_in(cid)
        if len(studs) < 2:
            return error(self, "You need at least two students to make a rule.")
        d = GroupRuleDialog(self, studs)
        if d.exec():
            v = d.values()
            G.add_rule(cid, v["kind"], v["a"], v["b"], self.app.subject_id)
            self._load_rules()

    @safe
    def drop_rule(self):
        rid = self.rules.current_id()
        if rid is None:
            return error(self, "Select a rule first.")
        G.delete_rule(rid)
        self._load_rules()

    @safe
    def export(self):
        gb, gs = self.app.gb, self._current()
        if gs is None:
            return error(self, "There are no groups to export.")
        name = f"{gb.class_name(gs.class_id)}-{gb.subject_short(gs.subject_id)}-groups".replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Export groups", f"{name}.xlsx", "Excel (*.xlsx)")
        if path:
            exports.write_xlsx(path, [exports.groups_sheet(gb, gs)])
            info(self, f"Saved {path}")