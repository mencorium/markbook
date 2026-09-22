# /markbook/backend/seed.py
"""Sample A-Level class with tests, a per-question midterm exam, attendance, targets and phone numbers.
Run:  python -m backend.seed        (add --remove to delete the sample data)"""
from __future__ import annotations

import datetime as dt
import random
import sys

from sqlalchemy import delete, select

from .db import create_schema, session_scope
from .models import (Assessment, AttendanceDay, AttendanceEntry, ClassGroup, Mark, PaperSection, Question, QuestionMark, Student,
                     Subject)
from .paper import Q, Sec, paper_max, paper_total

SAMPLE_CLASS = "Form Five (sample)"
NAMES = ["Neema Mwakalinga", "Baraka Mwansasu", "Rehema Kibona", "Joseph Mwaipopo", "Upendo Sanga", "Emmanuel Mbilinyi", "Grace Mwakyusa",
         "Daudi Kyando", "Faraja Mwasomola", "Salma Juma", "Elia Mwakasege", "Happiness Ngonyani", "Isaya Mwamfupe", "Winfrida Haule"]
SUBJECTS = [("Computer Science", "CS", False, ["Algorithms", "Programming", "Data structures", "Databases", "Networking"]),
            ("Advanced Mathematics", "MATH", False, ["Calculus", "Algebra", "Statistics", "Vectors"]),
            ("Physics", "PHY", False, ["Mechanics", "Electricity", "Waves", "Thermodynamics"]),
            ("General Studies", "GS", True, ["Civics", "Philosophy", "Economics"])]


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def add_sample(seed: int | None = None) -> None:
    rnd = random.Random(seed)
    create_schema()
    yr = dt.date.today().year
    with session_scope() as s:
        if s.scalar(select(ClassGroup).where(ClassGroup.name == SAMPLE_CLASS)):
            return
        cls = ClassGroup(name=SAMPLE_CLASS, level="A", teacher="Ms. R. Kibona", is_sample=True)
        s.add(cls)
        s.flush()
        studs = []
        for i, n in enumerate(NAMES):
            st = Student(name=n, reg_no=None if i % 5 == 3 else f"S{yr}-{101 + i}", phone=f"+2557{rnd.randint(10000000, 99999999)}",
                         class_id=cls.id, remarks="", targets={}, is_sample=True)
            s.add(st)
            studs.append(st)
        s.flush()
        ability = [45 + rnd.random() * 40 for _ in studs]
        drift = [(rnd.random() - .45) * 6 for _ in studs]
        presence = [.72 + rnd.random() * .27 for _ in studs]
        plan = [("Test 1", "Test", (1, 20), 50), ("Test 2", "Test", (2, 24), 50), ("Test 3", "Test", (4, 7), 50), ("Midterm Exam", "Exam", (5, 19), 100)]
        for name, code, subsidiary, topics in SUBJECTS:
            sub = s.scalar(select(Subject).where(Subject.name == name))
            if not sub:
                sub = Subject(name=name, code=code, subsidiary=subsidiary, is_sample=True)
                s.add(sub)
                s.flush()
            off = (rnd.random() - .5) * 16
            topic_off = {t: (rnd.random() - .5) * 36 for t in topics}
            stu_topic = [{t: (rnd.random() - .5) * 24 for t in topics} for _ in studs]
            for k, (an, typ, (m, d), mx) in enumerate(plan):
                base = lambda i: ability[i] + off + drift[i] * k + (presence[i] - .85) * 40
                a = Assessment(subject_id=sub.id, class_id=cls.id, type=typ, name=an, date=dt.date(yr, m, d), max_marks=mx, topics=[], is_sample=True)
                s.add(a)
                s.flush()
                if typ == "Exam":
                    sa = PaperSection(assessment_id=a.id, name="Section A", position=0)
                    sb = PaperSection(assessment_id=a.id, name="Section B", pick=2, position=1)
                    s.add_all([sa, sb])
                    s.flush()
                    qs = [Question(assessment_id=a.id, section_id=sa.id, label=f"Q{j + 1}", topic=topics[j % len(topics)], max_marks=10, position=j) for j in range(4)]
                    qs += [Question(assessment_id=a.id, section_id=sb.id, label=f"Q{j + 5}", topic=topics[(j + 1) % len(topics)], max_marks=30, position=4 + j) for j in range(3)]
                    s.add_all(qs)
                    s.flush()
                    secs = [Sec(sa.id, sa.name), Sec(sb.id, sb.name, 2)]
                    pq = [Q(q.id, q.label, q.topic, float(q.max_marks), q.section_id) for q in qs]
                    a.max_marks = paper_max(secs, pq)
                    a.topics = sorted({q.topic for q in qs})
                    for i, st in enumerate(studs):
                        if rnd.random() < .05:
                            continue
                        row = {}
                        score = lambda q: clamp(base(i) + topic_off[q.topic] + stu_topic[i][q.topic] + (rnd.random() - .5) * 20)
                        for q in qs[:4]:
                            if rnd.random() >= .04:
                                row[q.id] = round(score(q) / 100 * float(q.max_marks))
                        pref = sorted(qs[4:], key=lambda q: -(topic_off[q.topic] + stu_topic[i][q.topic] + (rnd.random() - .5) * 14))
                        for q in pref[: 3 if rnd.random() < .08 else 2]:
                            row[q.id] = round(score(q) / 100 * float(q.max_marks))
                        for qid, v in row.items():
                            s.add(QuestionMark(question_id=qid, student_id=st.id, score=v))
                        total, _ = paper_total(secs, pq, row)
                        if total is not None:
                            s.add(Mark(assessment_id=a.id, student_id=st.id, score=total))
                else:
                    tp = [topics[k % len(topics)], topics[(k + 1) % len(topics)]]
                    a.topics = tp
                    for i, st in enumerate(studs):
                        if rnd.random() < .05:
                            continue
                        p = clamp(base(i) + (topic_off[tp[0]] + topic_off[tp[1]]) / 2 + (rnd.random() - .5) * 18, 5, 98)
                        s.add(Mark(assessment_id=a.id, student_id=st.id, score=round(p / 100 * mx)))
        start = dt.date(yr, 1, 13)
        for w in range(20):
            day = AttendanceDay(class_id=cls.id, date=start + dt.timedelta(days=7 * w), is_sample=True)
            s.add(day)
            s.flush()
            for i, st in enumerate(studs):
                s.add(AttendanceEntry(day_id=day.id, student_id=st.id, present=rnd.random() <= presence[i]))
        math = s.scalar(select(Subject).where(Subject.code == "MATH"))
        for st in studs[:4]:
            st.targets = {str(math.id): "A"}


def remove_sample() -> None:
    with session_scope() as s:
        cls = s.scalar(select(ClassGroup).where(ClassGroup.name == SAMPLE_CLASS))
        if cls:
            s.execute(delete(Assessment).where(Assessment.class_id == cls.id))
            s.execute(delete(AttendanceDay).where(AttendanceDay.class_id == cls.id))
            s.execute(delete(Student).where(Student.class_id == cls.id))
            s.delete(cls)
        s.flush()
        for sub in s.scalars(select(Subject).where(Subject.is_sample.is_(True))):
            if not s.scalar(select(Assessment.id).where(Assessment.subject_id == sub.id).limit(1)):
                s.delete(sub)


if __name__ == "__main__":
    remove_sample() if "--remove" in sys.argv else add_sample()
    print("Sample data removed." if "--remove" in sys.argv else f"Sample data added: {SAMPLE_CLASS}")