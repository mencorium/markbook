# /markbook/backend/services/groups.py
"""Putting a class into groups for subject work.

Forming fair groups by hand is slow and hard to defend to students. The default here is a snake
draft down the class ranking — best to worst, then worst to best — which gives every group a
comparable spread of ability without anyone having to argue about it. Rules the teacher sets
(a minimum number of strong students, pairs to keep together or apart) are applied afterwards,
and anything that could not be satisfied is reported rather than quietly ignored.
"""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

from sqlalchemy import func, select

from .. import audit
from ..db import session_scope
from ..models import GroupMember, GroupRule, GroupSet, StudentGroup
from ..schema import GroupInfo, GroupSetInfo
from .analytics import Gradebook
from .records import ValidationError

BALANCED, SIMILAR, RANDOM, MANUAL = "balanced", "similar", "random", "manual"
STRATEGIES = {
    BALANCED: "Balanced — every group gets a spread of ability",
    SIMILAR: "Similar ability — groups of students at the same level",
    RANDOM: "Random — no regard to marks",
    MANUAL: "Empty — I will put students in myself",
}
TOGETHER, APART = "together", "apart"


@dataclass
class Ranked:
    student_id: int
    name: str
    mark: float | None                  # in the subject, else overall, else None
    grade: str = ""
    strong: bool = False


@dataclass
class Plan:
    """A proposed set of groups, before it is saved."""
    groups: list[list[int]]
    ranked: list[Ranked]
    warnings: list[str] = field(default_factory=list)

    def by_id(self) -> dict[int, Ranked]:
        return {r.student_id: r for r in self.ranked}

    def average(self, members: list[int]) -> float | None:
        marks = [r.mark for r in self.ranked if r.student_id in members and r.mark is not None]
        return sum(marks) / len(marks) if marks else None

    def strong_in(self, members: list[int]) -> int:
        return sum(1 for r in self.ranked if r.student_id in members and r.strong)


# ---------------- ranking ----------------
def rank_students(gb: Gradebook, class_id: int, subject_id: int, strong_grade: str | None = None) -> list[Ranked]:
    """Best first. A student with no mark in this subject falls back to their overall average,
    and one with no marks at all sits at the end — they still have to go somewhere."""
    scale = gb.scale(class_id)
    out: list[Ranked] = []
    for stu in gb.students_in(class_id):
        result = gb.subject_result(stu, subject_id)
        mark = result.final if result else gb.summary(stu).overall
        out.append(Ranked(stu.id, stu.name, mark, scale.letter(mark) if mark is not None else ""))
    out.sort(key=lambda r: (-(r.mark if r.mark is not None else -1), r.name.lower()))
    cut = scale.index(strong_grade) if strong_grade else None
    for r in out:
        r.strong = bool(r.mark is not None and cut is not None and scale.index(scale.letter(r.mark)) <= cut)
    return out


def group_count(total: int, size: int | None, count: int | None) -> int:
    if count:
        return max(1, min(count, total))
    if size:
        return max(1, -(-total // size))            # round up: no one left over
    return max(1, -(-total // 4))


# ---------------- forming ----------------
def _snake(ranked: list[Ranked], k: int) -> list[list[int]]:
    """Deal 1→k, then k→1, and so on, so each group gets a strong, a weak and middles."""
    groups: list[list[int]] = [[] for _ in range(k)]
    for i, r in enumerate(ranked):
        row, seat = divmod(i, k)
        groups[seat if row % 2 == 0 else k - 1 - seat].append(r.student_id)
    return groups


def _banded(ranked: list[Ranked], k: int) -> list[list[int]]:
    """Consecutive ranks together, for work pitched at a level."""
    groups: list[list[int]] = [[] for _ in range(k)]
    per = -(-len(ranked) // k)
    for i, r in enumerate(ranked):
        groups[min(k - 1, i // per)].append(r.student_id)
    return groups


def _random(ranked: list[Ranked], k: int, seed: int | None = None) -> list[list[int]]:
    ids = [r.student_id for r in ranked]
    random.Random(seed).shuffle(ids)
    groups: list[list[int]] = [[] for _ in range(k)]
    for i, sid in enumerate(ids):
        groups[i % k].append(sid)
    return groups


def _pairs(class_id: int, subject_id: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    with session_scope() as s:
        rules = list(s.scalars(select(GroupRule).where(
            GroupRule.class_id == class_id,
            (GroupRule.subject_id == subject_id) | (GroupRule.subject_id.is_(None)))))
        return ([(r.student_a, r.student_b) for r in rules if r.kind == TOGETHER],
                [(r.student_a, r.student_b) for r in rules if r.kind == APART])


def _where(groups: list[list[int]], sid: int) -> int | None:
    return next((i for i, g in enumerate(groups) if sid in g), None)


def _apply_together(groups: list[list[int]], pairs: list[tuple[int, int]], warnings: list[str], names: dict[int, str]) -> None:
    for a, b in pairs:
        ga, gb_ = _where(groups, a), _where(groups, b)
        if ga is None or gb_ is None or ga == gb_:
            continue
        if len(groups[ga]) >= len(groups[gb_]):      # move into the smaller group to keep sizes even
            ga, gb_, a, b = gb_, ga, b, a
        groups[gb_].remove(b)
        groups[ga].append(b)


def _apply_apart(groups: list[list[int]], pairs: list[tuple[int, int]], warnings: list[str], names: dict[int, str]) -> None:
    for a, b in pairs:
        ga, gb_ = _where(groups, a), _where(groups, b)
        if ga is None or gb_ is None or ga != gb_:
            continue
        others = sorted((i for i in range(len(groups)) if i != ga), key=lambda i: len(groups[i]))
        if not others:
            warnings.append(f"{names.get(a, '?')} and {names.get(b, '?')} must be apart, but there is only one group.")
            continue
        groups[ga].remove(b)
        groups[others[0]].append(b)


def _meet_strong(plan_groups: list[list[int]], ranked: list[Ranked], want: int, warnings: list[str]) -> None:
    """Move strong students from groups that have spare ones into groups that are short."""
    if want <= 0:
        return
    strong = {r.student_id for r in ranked if r.strong}
    if len(strong) < want * len(plan_groups):
        warnings.append(f"Only {len(strong)} student(s) meet the standard you set, so {len(plan_groups)} group(s) "
                        f"cannot each have {want}. They are spread as evenly as possible.")
    for _ in range(len(plan_groups) * 3):            # a few passes is plenty; never loop for ever
        short = [i for i, g in enumerate(plan_groups) if sum(1 for s in g if s in strong) < want]
        spare = [i for i, g in enumerate(plan_groups) if sum(1 for s in g if s in strong) > want]
        if not short or not spare:
            return
        give, take = spare[0], short[0]
        mover = next(s for s in plan_groups[give] if s in strong)
        swap = next((s for s in plan_groups[take] if s not in strong), None)
        plan_groups[give].remove(mover)
        plan_groups[take].append(mover)
        if swap is not None:                          # trade back, so group sizes stay even
            plan_groups[take].remove(swap)
            plan_groups[give].append(swap)


def plan_groups(gb: Gradebook, class_id: int, subject_id: int, *, strategy: str = BALANCED,
                size: int | None = None, count: int | None = None, min_strong: int = 0,
                strong_grade: str | None = None, seed: int | None = None) -> Plan:
    """Work out the groups without saving anything, so they can be shown first."""
    ranked = rank_students(gb, class_id, subject_id, strong_grade)
    if not ranked:
        raise ValidationError("This class has no students to put into groups.")
    k = group_count(len(ranked), size, count)
    warnings: list[str] = []
    if strategy == SIMILAR:
        groups = _banded(ranked, k)
    elif strategy == RANDOM:
        groups = _random(ranked, k, seed)
    elif strategy == MANUAL:
        groups = [[] for _ in range(k)]
    else:
        groups = _snake(ranked, k)
    if strategy != MANUAL:
        names = {r.student_id: r.name for r in ranked}
        together, apart = _pairs(class_id, subject_id)
        _apply_together(groups, together, warnings, names)
        _apply_apart(groups, apart, warnings, names)
        if min_strong and strategy != SIMILAR:
            _meet_strong(groups, ranked, min_strong, warnings)
        elif min_strong:
            warnings.append("A minimum number of strong students does not apply when groups are formed by "
                            "similar ability — that is the opposite arrangement.")
    if any(r.mark is None for r in ranked) and strategy in (BALANCED, SIMILAR):
        n = sum(1 for r in ranked if r.mark is None)
        warnings.append(f"{n} student(s) have no marks in this subject yet, so they were placed last.")
    return Plan(groups, ranked, warnings)


# ---------------- storing ----------------
def _info(gs: GroupSet) -> GroupSetInfo:
    return GroupSetInfo(gs.id, gs.name, gs.class_id, gs.subject_id, gs.term_id, gs.made_by, dict(gs.rules or {}),
                        gs.created_at, [GroupInfo(g.id, g.name, g.position, [m.student_id for m in g.members],
                                                  next((m.student_id for m in g.members if m.is_leader), None))
                                        for g in gs.groups])


def list_sets(class_id: int | None = None, subject_id: int | None = None, term_id: int | None = None) -> list[GroupSetInfo]:
    with session_scope() as s:
        q = select(GroupSet).order_by(GroupSet.created_at.desc(), GroupSet.id.desc())
        if class_id:
            q = q.where(GroupSet.class_id == class_id)
        if subject_id:
            q = q.where(GroupSet.subject_id == subject_id)
        if term_id:
            q = q.where(GroupSet.term_id == term_id)
        return [_info(x) for x in s.scalars(q)]


def get_set(set_id: int) -> GroupSetInfo | None:
    with session_scope() as s:
        gs = s.get(GroupSet, set_id)
        return _info(gs) if gs else None


def save_set(set_id: int | None, *, name: str, class_id: int, subject_id: int, term_id: int | None,
             groups: list[list[int]], made_by: str = BALANCED, rules: dict | None = None,
             names: list[str] | None = None) -> GroupSetInfo:
    """Create or replace a set. Group names default to Group 1, Group 2, …"""
    name = name.strip()
    if not name:
        raise ValidationError("Give this set of groups a name, such as “Project groups”.")
    if not groups:
        raise ValidationError("There are no groups to save.")
    seen: set[int] = set()
    for g in groups:
        for sid in g:
            if sid in seen:
                raise ValidationError("A student cannot be in two groups of the same set.")
            seen.add(sid)
    with session_scope() as s:
        gs = s.get(GroupSet, set_id) if set_id else GroupSet(created_at=dt.datetime.now())
        gs.name, gs.class_id, gs.subject_id, gs.term_id = name, class_id, subject_id, term_id
        gs.made_by, gs.rules = made_by, rules or {}
        s.add(gs)
        s.flush()
        for old in list(gs.groups):
            s.delete(old)
        s.flush()
        for i, members in enumerate(groups):
            g = StudentGroup(set_id=gs.id, name=(names[i] if names and i < len(names) else f"Group {i + 1}"), position=i)
            s.add(g)
            s.flush()
            for sid in members:
                s.add(GroupMember(group_id=g.id, student_id=sid))
        s.flush()
        audit.log(s, "groups.saved" if set_id else "groups.created", entity="groups", entity_id=gs.id,
                  detail=f"{gs.name}: {len(groups)} group(s), {len(seen)} student(s)")
        s.expire(gs)
        return _info(gs)


def rename_group(group_id: int, name: str) -> None:
    if not name.strip():
        raise ValidationError("A group needs a name.")
    with session_scope() as s:
        s.get(StudentGroup, group_id).name = name.strip()[:80]


def move_student(set_id: int, student_id: int, to_group_id: int | None) -> None:
    """Move one student to another group in the same set, or out of the set when to_group_id is None."""
    with session_scope() as s:
        gs = s.get(GroupSet, set_id)
        ids = {g.id for g in gs.groups}
        if to_group_id is not None and to_group_id not in ids:
            raise ValidationError("That group belongs to another set.")
        for g in gs.groups:
            for m in list(g.members):
                if m.student_id == student_id:
                    g.members.remove(m)
        s.flush()
        if to_group_id is not None:
            s.add(GroupMember(group_id=to_group_id, student_id=student_id))


def set_leader(group_id: int, student_id: int | None) -> None:
    with session_scope() as s:
        g = s.get(StudentGroup, group_id)
        for m in g.members:
            m.is_leader = (m.student_id == student_id)


def delete_set(set_id: int) -> None:
    with session_scope() as s:
        gs = s.get(GroupSet, set_id)
        if gs:
            audit.log(s, "groups.deleted", entity="groups", entity_id=set_id, detail=gs.name)
            s.delete(gs)


# ---------------- keep together / apart ----------------
def list_rules(class_id: int, subject_id: int | None = None) -> list[tuple[int, str, int, int]]:
    with session_scope() as s:
        q = select(GroupRule).where(GroupRule.class_id == class_id)
        if subject_id:
            q = q.where((GroupRule.subject_id == subject_id) | (GroupRule.subject_id.is_(None)))
        return [(r.id, r.kind, r.student_a, r.student_b) for r in s.scalars(q)]


def add_rule(class_id: int, kind: str, student_a: int, student_b: int, subject_id: int | None = None) -> None:
    if kind not in (TOGETHER, APART):
        raise ValidationError("Choose whether the two students should be kept together or apart.")
    if student_a == student_b:
        raise ValidationError("Pick two different students.")
    with session_scope() as s:
        pair = tuple(sorted((student_a, student_b)))
        exists = s.scalar(select(func.count()).select_from(GroupRule).where(
            GroupRule.class_id == class_id, GroupRule.student_a == pair[0], GroupRule.student_b == pair[1]))
        if exists:
            raise ValidationError("There is already a rule for those two students.")
        s.add(GroupRule(class_id=class_id, subject_id=subject_id, kind=kind, student_a=pair[0], student_b=pair[1]))


def delete_rule(rule_id: int) -> None:
    with session_scope() as s:
        r = s.get(GroupRule, rule_id)
        if r:
            s.delete(r)