# /markbook/backend/services/terms.py
"""Terms and academic years.

A term is whatever period the school teaches in — two six-month terms, three shorter ones,
or a short course. Marks and attendance belong to a term, so each term has its own averages,
positions and divisions, and last term stops dragging on this term's results.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from .. import audit
from ..db import session_scope
from ..models import Assessment, AttendanceDay, ClassGroup, Student, Term
from ..schema import TermInfo
from .records import ValidationError, get_settings, save_settings

ROLLOVER = {"promote": "Students move up to the next class", "continue": "Same class carries on",
            "group": "Short course — the group finishes"}


def _info(t: Term) -> TermInfo:
    return TermInfo(t.id, t.name, t.year, t.starts_on, t.ends_on, float(t.weight))


def list_terms(year: str | None = None) -> list[TermInfo]:
    with session_scope() as s:
        q = select(Term).order_by(Term.starts_on, Term.id)
        if year:
            q = q.where(Term.year == year)
        return [_info(t) for t in s.scalars(q)]


def years() -> list[str]:
    with session_scope() as s:
        return [y for (y,) in s.execute(select(Term.year).distinct().order_by(Term.year.desc()))]


def get_term(term_id: int | None) -> TermInfo | None:
    if not term_id:
        return None
    with session_scope() as s:
        t = s.get(Term, term_id)
        return _info(t) if t else None


def term_for_date(day: dt.date) -> TermInfo | None:
    with session_scope() as s:
        t = s.scalar(select(Term).where(Term.starts_on <= day, Term.ends_on >= day).order_by(Term.starts_on))
        return _info(t) if t else None


def current_term() -> TermInfo | None:
    """What Settings says, else the term covering today, else the most recent one."""
    chosen = get_settings().get("current_term")
    if chosen:
        t = get_term(int(chosen))
        if t:
            return t
    today = term_for_date(dt.date.today())
    if today:
        return today
    all_terms = list_terms()
    return all_terms[-1] if all_terms else None


def set_current(term_id: int | None) -> None:
    save_settings({"current_term": int(term_id) if term_id else ""})


def save_term(term_id: int | None, *, name: str, year: str, starts_on: dt.date, ends_on: dt.date, weight: float = 1) -> TermInfo:
    name, year = name.strip(), str(year).strip()
    if not name:
        raise ValidationError("Give the term a name, such as Term 1.")
    if not year:
        raise ValidationError("Enter the academic year, such as 2026 or 2026/2027.")
    if ends_on < starts_on:
        raise ValidationError("The term cannot end before it starts.")
    if weight <= 0:
        raise ValidationError("The weight in the annual result must be more than 0.")
    with session_scope() as s:
        clash = s.scalar(select(Term).where(func.lower(Term.name) == name.lower(), Term.year == year, Term.id != (term_id or 0)))
        if clash:
            raise ValidationError(f"{name} already exists in {year}.")
        overlap = s.scalar(select(Term).where(Term.id != (term_id or 0), Term.starts_on <= ends_on, Term.ends_on >= starts_on))
        if overlap:
            raise ValidationError(f"These dates overlap {overlap.name} ({overlap.year}), which runs "
                                  f"{overlap.starts_on:%d %b %Y} to {overlap.ends_on:%d %b %Y}.")
        t = s.get(Term, term_id) if term_id else Term()
        t.name, t.year, t.starts_on, t.ends_on, t.weight = name, year, starts_on, ends_on, weight
        s.add(t)
        s.flush()
        return _info(t)


def delete_term(term_id: int) -> None:
    with session_scope() as s:
        used = s.scalar(select(func.count()).select_from(Assessment).where(Assessment.term_id == term_id)) or 0
        used += s.scalar(select(func.count()).select_from(AttendanceDay).where(AttendanceDay.term_id == term_id)) or 0
        if used:
            raise ValidationError(f"{used} assessment(s) or register(s) belong to this term. Move or delete them first.")
        t = s.get(Term, term_id)
        if t:
            audit.log(s, "term.deleted", entity="term", entity_id=term_id, detail=f"{t.name} {t.year}")
            s.delete(t)
    if str(get_settings().get("current_term") or "") == str(term_id):
        set_current(None)


def counts(term_id: int) -> tuple[int, int]:
    """How much is recorded in a term: (assessments, registers)."""
    with session_scope() as s:
        return (s.scalar(select(func.count()).select_from(Assessment).where(Assessment.term_id == term_id)) or 0,
                s.scalar(select(func.count()).select_from(AttendanceDay).where(AttendanceDay.term_id == term_id)) or 0)


def assign_missing() -> int:
    """Any assessment or register without a term (an import, a restored backup, older data) is
    placed in the term covering its date, or a term is made for it. Marks must never be invisible."""
    with session_scope() as s:
        rows = list(s.scalars(select(Assessment).where(Assessment.term_id.is_(None))))
        days = list(s.scalars(select(AttendanceDay).where(AttendanceDay.term_id.is_(None))))
        if not rows and not days:
            return 0
        dates = [r.date for r in rows] + [d.date for d in days]
        terms = list(s.scalars(select(Term)))
        fixed = 0
        for item in rows + days:
            match = next((t for t in terms if t.starts_on <= item.date <= t.ends_on), None)
            if match is None:
                year = str(max(dates).year)
                match = Term(name="Term 1", year=year, starts_on=min(dates), ends_on=max(dates), weight=1)
                s.add(match)
                s.flush()
                terms.append(match)
                audit.log(s, "term.created", entity="term", entity_id=match.id,
                          detail=f"{match.name} {match.year} made automatically for work that had no term")
            item.term_id = match.id
            fixed += 1
        return fixed


def set_class_rollover(class_id: int, rule: str, year: str = "") -> None:
    if rule not in ROLLOVER:
        raise ValidationError("Choose what happens to this class at the end of the year.")
    with session_scope() as s:
        c = s.get(ClassGroup, class_id)
        c.rollover = rule
        if year:
            c.year = year


def next_class_name(name: str) -> str:
    """A sensible suggestion when promoting: Form Five -> Form Six, S3 -> S4, Grade 7 -> Grade 8."""
    words = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]
    lower = name.lower()
    hits = [(lower.find(w.lower()), i) for i, w in enumerate(words[:-1]) if lower.find(w.lower()) >= 0]
    if hits:
        at, i = min(hits)
        found, nxt = name[at: at + len(words[i])], words[i + 1]
        nxt = nxt.upper() if found.isupper() else nxt.lower() if found.islower() else nxt
        return name[:at] + nxt + name[at + len(words[i]):]
    digits = "".join(ch for ch in name if ch.isdigit())
    if digits:
        return name.replace(digits, str(int(digits) + 1), 1)
    return name


def start_term(*, name: str, year: str, starts_on: dt.date, ends_on: dt.date, weight: float = 1,
               plan: list[dict] | None = None) -> dict:
    """Create the next term and apply each class's rollover rule.

    plan: [{class_id, action ('promote'|'continue'|'group'), target ('Form Six')}].
    promote  - students move to the target class, and last term's marks stay with the old class
    continue - the class carries on into the new term
    group    - the course is over: its students are archived
    """
    term = save_term(None, name=name, year=year, starts_on=starts_on, ends_on=ends_on, weight=weight)
    moved = promoted = archived = continued = 0
    with session_scope() as s:
        audit.log(s, "term.started", entity="term", entity_id=term.id, detail=f"{term.name} {term.year}")
        for item in plan or []:
            cls = s.get(ClassGroup, item["class_id"])
            if not cls:
                continue
            action = item.get("action") or cls.rollover
            students = list(s.scalars(select(Student).where(Student.class_id == cls.id, Student.archived_at.is_(None))))
            if action == "promote":
                target_name = (item.get("target") or next_class_name(cls.name)).strip()
                target = s.scalar(select(ClassGroup).where(func.lower(ClassGroup.name) == target_name.lower()))
                if target is None:
                    target = ClassGroup(name=target_name, level=cls.level, pass_mark=cls.pass_mark, teacher=cls.teacher,
                                        scale=cls.scale, rollover=cls.rollover)
                    s.add(target)
                    s.flush()
                target.year = year
                for stu in students:
                    stu.class_id = target.id
                    moved += 1
                promoted += 1
                audit.log(s, "class.promoted", entity="class", entity_id=cls.id,
                          detail=f"{len(students)} student(s) moved from {cls.name} to {target.name} for {year}")
            elif action == "group":
                now = dt.datetime.now()
                for stu in students:
                    stu.archived_at = now
                archived += len(students)
                audit.log(s, "class.finished", entity="class", entity_id=cls.id,
                          detail=f"{cls.name}: {len(students)} student(s) archived at the end of the course")
            else:
                cls.year = year
                continued += 1
    set_current(term.id)
    return {"term": term, "moved": moved, "promoted": promoted, "archived": archived, "continued": continued}