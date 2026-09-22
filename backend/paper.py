# /markbook/backend/paper.py
"""Question-paper arithmetic: paper maximum and a student's total, honouring 'answer any N' sections."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Sec:
    id: int | str
    name: str = ""
    pick: int | None = None


@dataclass
class Q:
    id: int | str
    label: str
    topic: str
    max: float
    section_id: int | str


def paper_max(sections: list[Sec], questions: list[Q]) -> float:
    total = 0.0
    for s in sections:
        maxes = sorted((q.max for q in questions if q.section_id == s.id), reverse=True)
        total += sum(maxes[: s.pick] if s.pick else maxes)
    return round(total, 2)


def paper_total(sections: list[Sec], questions: list[Q], row: dict) -> tuple[float | None, list[str]]:
    """row: {question_id: score}. Returns (total or None when nothing entered, sections answered beyond their pick)."""
    if not any(row.get(q.id) is not None for q in questions):
        return None, []
    total, over = 0.0, []
    for s in sections:
        got = sorted((float(row[q.id]) for q in questions if q.section_id == s.id and row.get(q.id) is not None), reverse=True)
        if s.pick and len(got) > s.pick:
            over.append(s.name or "the paper")
            got = got[: s.pick]
        total += sum(got)
    return round(total, 2), over