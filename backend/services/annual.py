# /markbook/backend/services/annual.py
"""End-of-year results: each term's subject result combined by the term's weight.

A student's year mark in a subject is the weighted mean of the finals they earned in each term,
counting only terms they actually sat. Division, position and grade then follow from those year
marks, exactly as they do within a term.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..grading import Division, Scale
from ..schema import StudentInfo, SubjectInfo, TermInfo
from .analytics import Gradebook, avg
from .terms import list_terms


@dataclass
class AnnualSubject:
    subject: SubjectInfo
    per_term: dict[int, float]            # term id -> that term's final
    final: float                          # weighted across the terms sat
    terms_sat: int


@dataclass
class AnnualRow:
    student: StudentInfo
    subjects: dict[int, AnnualSubject] = field(default_factory=dict)
    overall: float | None = None
    total: float = 0.0
    div: Division | None = None
    att: float | None = None
    rank: int = 0
    terms_sat: int = 0


class AnnualBook:
    """One academic year for one class, built from a Gradebook per term."""

    def __init__(self, year: str, class_id: int, terms: list[TermInfo], books: dict[int, Gradebook]):
        self.year, self.class_id, self.terms, self.books = year, class_id, terms, books
        self.any: Gradebook = books[terms[0].id]
        self.scale: Scale = self.any.scale(class_id)
        self.rows: list[AnnualRow] = []
        self._build()

    @classmethod
    def load(cls, year: str, class_id: int) -> "AnnualBook | None":
        terms = list_terms(year)
        if not terms:
            return None
        return cls(year, class_id, terms, {t.id: Gradebook.load(t.id) for t in terms})

    @property
    def class_name(self) -> str:
        return self.any.class_name(self.class_id)

    def subjects(self) -> list[SubjectInfo]:
        seen: dict[int, SubjectInfo] = {}
        for t in self.terms:
            for s in self.books[t.id].class_subjects(self.class_id):
                seen.setdefault(s.id, s)
        return sorted(seen.values(), key=lambda s: s.name.lower())

    def term_label(self, term_id: int) -> str:
        return next((t.name for t in self.terms if t.id == term_id), "")

    def _build(self) -> None:
        students = {s.id: s for t in self.terms for s in self.books[t.id].students_in(self.class_id)}
        for stu in sorted(students.values(), key=lambda s: s.name.lower()):
            row = AnnualRow(stu)
            for sub in self.subjects():
                per_term, weighted, weights = {}, 0.0, 0.0
                for t in self.terms:
                    gb = self.books[t.id]
                    mine = gb.students.get(stu.id)
                    result = gb.subject_result(mine, sub.id) if mine else None
                    if result:
                        per_term[t.id] = result.final
                        weighted += result.final * t.weight
                        weights += t.weight
                if weights:
                    row.subjects[sub.id] = AnnualSubject(sub, per_term, weighted / weights, len(per_term))
            if row.subjects:
                row.overall = avg(s.final for s in row.subjects.values())
                row.total = sum(s.final for s in row.subjects.values())
                row.div = self.scale.division([(s.final, s.subject.subsidiary) for s in row.subjects.values()])
                row.terms_sat = max((s.terms_sat for s in row.subjects.values()), default=0)
                rates = [r for r in (self.books[t.id].att_rate(stu) for t in self.terms) if r is not None]
                row.att = avg(rates)
            self.rows.append(row)
        self._rank()

    def _rank(self) -> None:
        ranked = [r for r in self.rows if r.overall is not None]

        def key(r: AnnualRow):
            complete = bool(r.div and r.div.complete)
            return (0 if complete else 1, r.div.points if complete else 0, -round(r.overall, 6))
        ranked.sort(key=key)
        prev, rank = None, 0
        for i, r in enumerate(ranked):
            if key(r) != prev:
                rank = i + 1
            r.rank, prev = rank, key(r)
        self.ranked = ranked

    def row_for(self, student_id: int) -> AnnualRow | None:
        return next((r for r in self.rows if r.student.id == student_id), None)

    def positions(self, subject_id: int) -> tuple[dict[int, int], int]:
        got = sorted(((r.student.id, r.subjects[subject_id].final) for r in self.rows if subject_id in r.subjects), key=lambda x: -x[1])
        out, prev, rank = {}, None, 0
        for i, (sid, final) in enumerate(got):
            if prev is None or abs(final - prev) > 1e-9:
                rank = i + 1
            out[sid], prev = rank, final
        return out, len(got)

    def weights_note(self) -> str:
        if len({t.weight for t in self.terms}) == 1:
            return f"Year mark: the average of {len(self.terms)} term(s)."
        parts = ", ".join(f"{t.name} ×{t.weight:g}" for t in self.terms)
        return f"Year mark: terms combined by weight ({parts})."