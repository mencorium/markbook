# /markbook/backend/services/assessments.py
"""Assessments, question papers (sections + questions) and marks."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select

from ..db import session_scope
from ..models import Assessment, Mark, PaperSection, Question, QuestionMark
from ..paper import Q, Sec, paper_max, paper_total
from .records import ValidationError
from ..schema import AssessmentInfo, SectionInfo, QuestionInfo

TYPES = ["Test", "Quiz", "Assignment", "Exam"]


def _info(a: Assessment) -> AssessmentInfo:
    return AssessmentInfo(
        a.id, a.subject_id, a.class_id, a.type, a.name, a.date, float(a.max_marks), list(a.topics or []),
        [SectionInfo(s.id, s.name, s.pick) for s in a.sections],
        [QuestionInfo(q.id, q.label, q.topic, float(q.max_marks), q.section_id) for q in a.questions],
    )


def list_assessments(class_id: int | None = None, subject_id: int | None = None) -> list[AssessmentInfo]:
    with session_scope() as s:
        q = select(Assessment).order_by(Assessment.date, Assessment.name)
        if class_id:
            q = q.where(Assessment.class_id == class_id)
        if subject_id:
            q = q.where(Assessment.subject_id == subject_id)
        return [_info(a) for a in s.scalars(q)]


def get_assessment(assessment_id: int) -> AssessmentInfo | None:
    with session_scope() as s:
        a = s.get(Assessment, assessment_id)
        return _info(a) if a else None


def save_assessment(assessment_id: int | None, *, subject_id: int, class_id: int, type: str, name: str,
                    date: dt.date, max_marks: float | None = None, topics: list[str] | None = None) -> AssessmentInfo:
    if not name.strip():
        raise ValidationError("Give the assessment a name, such as Test 2.")
    if type not in TYPES:
        raise ValidationError("Choose a type.")
    with session_scope() as s:
        a = s.get(Assessment, assessment_id) if assessment_id else Assessment(topics=[])
        a.subject_id, a.class_id, a.type, a.name, a.date = subject_id, class_id, type, name.strip(), date
        if not a.questions:                               # papers derive max and topics from their questions
            if not max_marks or max_marks <= 0:
                raise ValidationError("'Out of' must be more than 0.")
            a.max_marks = max_marks
            a.topics = sorted({t.strip() for t in (topics or []) if t.strip()})
        s.add(a)
        s.flush()
        s.refresh(a)
        return _info(a)


def delete_assessment(assessment_id: int) -> None:
    with session_scope() as s:
        s.delete(s.get(Assessment, assessment_id))


# ---------------- marks ----------------
def get_marks(assessment_id: int) -> tuple[dict[int, float], dict[int, dict]]:
    """Returns (totals {student_id: score}, per-question {student_id: {question_id: score}})."""
    with session_scope() as s:
        totals = {m.student_id: float(m.score) for m in s.scalars(select(Mark).where(Mark.assessment_id == assessment_id))}
        qrows: dict[int, dict] = {}
        rows = s.execute(select(QuestionMark).join(Question, Question.id == QuestionMark.question_id)
                         .where(Question.assessment_id == assessment_id)).scalars()
        for qm in rows:
            qrows.setdefault(qm.student_id, {})[qm.question_id] = float(qm.score)
        return totals, qrows


def save_totals(assessment_id: int, totals: dict[int, float | None]) -> int:
    """Simple (non-paper) assessments. None removes a mark (absent)."""
    with session_scope() as s:
        a = s.get(Assessment, assessment_id)
        for sid, v in totals.items():
            if v is not None and not 0 <= v <= a.max_marks:
                raise ValidationError(f"Scores must be between 0 and {a.max_marks:g}.")
        existing = {m.student_id: m for m in s.scalars(select(Mark).where(Mark.assessment_id == assessment_id))}
        n = 0
        for sid, v in totals.items():
            m = existing.get(sid)
            if v is None:
                if m:
                    s.delete(m)
            elif m:
                m.score = v
                n += 1
            else:
                s.add(Mark(assessment_id=assessment_id, student_id=sid, score=v))
                n += 1
        return n


def _paper_parts(a: Assessment) -> tuple[list[Sec], list[Q]]:
    return ([Sec(x.id, x.name, x.pick) for x in a.sections],
            [Q(q.id, q.label, q.topic, float(q.max_marks), q.section_id) for q in a.questions])


def save_question_marks(assessment_id: int, rows: dict[int, dict[int, float | None]]) -> int:
    """rows: {student_id: {question_id: score or None}}. Blank = not answered. Totals are recomputed."""
    with session_scope() as s:
        a = s.get(Assessment, assessment_id)
        secs, qs = _paper_parts(a)
        qmax = {q.id: q.max for q in qs}
        for sid, row in rows.items():
            for qid, v in row.items():
                if v is not None and not 0 <= v <= qmax.get(qid, 0):
                    raise ValidationError(f"A mark of {v:g} is outside the range 0–{qmax.get(qid, 0):g} for its question.")
        existing = {(m.student_id, m.question_id): m for m in s.execute(
            select(QuestionMark).join(Question, Question.id == QuestionMark.question_id).where(Question.assessment_id == assessment_id)).scalars()}
        totals = {m.student_id: m for m in s.scalars(select(Mark).where(Mark.assessment_id == assessment_id))}
        n = 0
        for sid, row in rows.items():
            for qid, v in row.items():
                m = existing.get((sid, qid))
                if v is None:
                    if m:
                        s.delete(m)
                elif m:
                    m.score = v
                else:
                    s.add(QuestionMark(question_id=qid, student_id=sid, score=v))
            clean = {qid: v for qid, v in row.items() if v is not None}
            total, _ = paper_total(secs, qs, clean)
            t = totals.get(sid)
            if total is None:
                if t:
                    s.delete(t)
            elif t:
                t.score = total
                n += 1
            else:
                s.add(Mark(assessment_id=assessment_id, student_id=sid, score=total))
                n += 1
        return n


# ---------------- question paper ----------------
def save_paper(assessment_id: int, sections: list[dict], questions: list[dict]) -> AssessmentInfo:
    """sections: [{key, name, pick}], questions: [{id (existing or None), label, topic, max, section_key}].
    Existing question ids keep their marks; removed questions lose theirs. Totals are recomputed."""
    labels = [q["label"].strip() for q in questions]
    if not questions:
        raise ValidationError("Add at least one question.")
    if any(not l for l in labels):
        raise ValidationError("Every question needs a label, such as Q1 or 2a.")
    dup = next((l for i, l in enumerate(labels) if l.lower() in [x.lower() for x in labels[:i]]), None)
    if dup:
        raise ValidationError(f"Two questions are labelled {dup}.")
    if any(float(q.get("max") or 0) <= 0 for q in questions):
        raise ValidationError("Every question needs marks greater than 0.")
    with session_scope() as s:
        a = s.get(Assessment, assessment_id)
        old_q = {q.id: q for q in a.questions}
        old_sec = {x.id: x for x in a.sections}
        live = [x for x in sections if any(q["section_key"] == x["key"] for q in questions)]
        key_to_sec: dict = {}
        for pos, x in enumerate(live):
            n = sum(1 for q in questions if q["section_key"] == x["key"])
            pick = int(x["pick"]) if x.get("pick") else None
            sec = old_sec.get(x["key"])
            if sec is None:
                sec = PaperSection(assessment_id=a.id)
                s.add(sec)
            sec.name, sec.pick, sec.position = (x.get("name") or "").strip(), (pick if pick and pick < n else None), pos
            s.flush()
            key_to_sec[x["key"]] = sec
        keep = set()
        for pos, qd in enumerate(questions):
            q = old_q.get(qd.get("id")) if qd.get("id") else None
            if q is None:
                q = Question(assessment_id=a.id)
                s.add(q)
            q.label, q.topic, q.max_marks, q.position = qd["label"].strip(), (qd.get("topic") or "").strip(), float(qd["max"]), pos
            q.section_id = key_to_sec[qd["section_key"]].id
            s.flush()
            keep.add(q.id)
        for qid, q in old_q.items():
            if qid not in keep:
                s.delete(q)
        s.flush()
        used = {sec.id for sec in key_to_sec.values()}
        for sid, sec in old_sec.items():
            if sid not in used:
                s.delete(sec)
        s.flush()
        s.expire(a)
        secs, qs = _paper_parts(a)
        a.max_marks = paper_max(secs, qs)
        a.topics = sorted({q.topic for q in qs if q.topic})
        _recompute_totals(s, a)
        s.flush()
        s.expire(a)
        return _info(a)


def _recompute_totals(s, a: Assessment) -> None:
    secs, qs = _paper_parts(a)
    rows: dict[int, dict] = {}
    for qm in s.execute(select(QuestionMark).join(Question, Question.id == QuestionMark.question_id)
                        .where(Question.assessment_id == a.id)).scalars():
        rows.setdefault(qm.student_id, {})[qm.question_id] = float(qm.score)
    totals = {m.student_id: m for m in s.scalars(select(Mark).where(Mark.assessment_id == a.id))}
    for sid, row in rows.items():
        total, _ = paper_total(secs, qs, row)
        if sid in totals:
            totals[sid].score = total
        else:
            s.add(Mark(assessment_id=a.id, student_id=sid, score=total))


def remove_paper(assessment_id: int) -> AssessmentInfo:
    """Back to total marks only; each student's total is kept."""
    with session_scope() as s:
        a = s.get(Assessment, assessment_id)
        secs, qs = _paper_parts(a)
        a.max_marks = paper_max(secs, qs) if qs else a.max_marks
        s.execute(delete(Question).where(Question.assessment_id == a.id))
        s.execute(delete(PaperSection).where(PaperSection.assessment_id == a.id))
        s.flush()
        s.refresh(a)
        return _info(a)