# /markbook/backend/services/comments.py
"""Suggested class-teacher comments written from a student's actual results. Teachers edit before printing."""
from __future__ import annotations

from .analytics import Gradebook
from .records import set_remarks


def auto_comment(gb: Gradebook, student_id: int) -> str:
    stu = gb.students[student_id]
    s, sc = gb.summary(stu), gb.scale(stu.class_id)
    if s.overall is None:
        return ""
    first = stu.name.split()[0]
    p = s.overall
    band = ("excellent" if p >= 80 else "very good" if p >= 70 else "good" if p >= 60 else "fair" if p >= 50
            else "below average" if sc.passing(p) else "weak")
    div = f" and Division {s.div.div}" if s.div and s.div.complete else ""
    out = [f"{first} has shown {band} performance this term, with an average of {p:.1f}% (grade {sc.letter(p)}){div}."]
    ranked = sorted(((gb.subjects[k], r.final) for k, r in s.subs.items()), key=lambda x: -x[1])
    if len(ranked) > 1:
        extra = f" and {ranked[1][0].name}" if ranked[0][1] - ranked[1][1] < 3 else ""
        out.append(f"{first} did best in {ranked[0][0].name}{extra}.")
        worst, wf = ranked[-1]
        if wf < ranked[0][1] - 8 or not sc.passing(wf):
            topics = sorted(gb.topic_map(stu, worst.id), key=lambda t: t.mean)
            topic = f", especially {topics[0].topic}" if topics and not sc.passing(topics[0].mean) else ""
            out.append(f"More effort is needed in {worst.name}{topic}.")
    if s.trend == "up":
        out.append("Results have improved steadily through the term — keep it up.")
    elif s.trend == "down":
        out.append("Results have dropped recently, so regular revision is advised.")
    if s.att is not None and s.att < 85:
        out.append(f"Attendance of {round(s.att)}% must improve.")
    out.append(("Keep up the good work." if p >= 70 else "With steady effort, better results are within reach.")
               if sc.passing(p) else "Consistent effort and extra practice are needed to reach the pass mark.")
    return " ".join(out)


def fill_missing_comments(gb: Gradebook, class_id: int) -> int:
    n = 0
    for stu in gb.students_in(class_id):
        if not stu.remarks.strip():
            c = auto_comment(gb, stu.id)
            if c:
                set_remarks(stu.id, c)
                n += 1
    return n