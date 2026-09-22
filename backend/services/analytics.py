# /markbook/backend/services/analytics.py
"""All calculations. A Gradebook is an in-memory snapshot of the database; screens load one,
read from it, and reload after saving. Nothing here writes to the database."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from statistics import mean

from sqlalchemy import select

from ..db import session_scope
from ..grading import Division, Scale, make_scale
from ..models import Assessment, AttendanceDay, ClassGroup, Mark, Question, QuestionMark, Student, Subject
from ..paper import Q, Sec, paper_total
from ..schema import AssessmentInfo, AttendanceDayInfo, ClassInfo, QuestionInfo, SectionInfo, StudentInfo, SubjectInfo
from .records import get_settings


def avg(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return mean(xs) if xs else None


def slope(ys: list[float]) -> float:
    n = len(ys)
    if n < 2:
        return 0.0
    mx, my = (n - 1) / 2, mean(ys)
    den = sum((x - mx) ** 2 for x in range(n))
    return sum((x - mx) * (y - my) for x, y in enumerate(ys)) / den if den else 0.0


def trend_of(ys: list[float]) -> str:
    if len(ys) < 3:
        return "flat"
    s = slope(ys)
    return "up" if s > 1.5 else "down" if s < -1.5 else "flat"


TREND_WORDS = {"up": "Improving", "down": "Dropping", "flat": "Steady"}


@dataclass
class SubjectResult:
    ca: float | None
    ex: float | None
    final: float
    provisional: bool
    n: int
    trend: str
    predicted: float


@dataclass
class Summary:
    subs: dict[int, SubjectResult]
    overall: float | None
    series: list[float]
    trend: str
    att: float | None
    div: Division | None
    pred_div: Division | None
    behind: list[str]


@dataclass
class RankRow:
    student: StudentInfo
    summary: Summary
    rank: int = 0


@dataclass
class Stats:
    n: int
    mean: float | None
    hi: float | None
    lo: float | None
    pass_rate: float | None
    pcts: list[float]


@dataclass
class QuestionStat:
    q: QuestionInfo
    choice: bool
    marked: bool
    attempted: int = 0
    att_rate: float | None = None
    facility: float | None = None
    disc: float | None = None
    full: int = 0
    zero: int = 0


@dataclass
class TopicStat:
    topic: str
    questions: list[str]
    marks: float
    facility: float | None
    attempted: int
    att_rate: float | None
    per: dict[int, float]                       # student_id -> % of topic marks
    struggling: list[tuple[int, float]]


@dataclass
class PaperAnalysis:
    sitters: list[int]
    questions: list[QuestionStat]
    topics: list[TopicStat]                     # hardest first


@dataclass
class TopicScore:
    subject_id: int
    topic: str
    earned: float = 0.0
    possible: float = 0.0
    assessments: set = field(default_factory=set)

    @property
    def mean(self) -> float:
        return self.earned / self.possible * 100 if self.possible else 0.0


@dataclass
class ClassTopicStat:
    topic: str
    assessments: int
    mean: float | None
    per: list[tuple[StudentInfo, float]]        # weakest first
    below: int


def difficulty(f: float | None) -> str:
    return "–" if f is None else "Easy" if f >= 70 else "Moderate" if f >= 40 else "Hard"


def discrimination_label(d: float | None) -> str:
    return "–" if d is None else "Good" if d >= 0.3 else "Fair" if d >= 0.2 else "Weak" if d >= 0 else "Check marking"


class Gradebook:
    def __init__(self, settings, classes, subjects, students, assessments, totals, qmarks, days):
        self.settings: dict = settings
        self.classes: dict[int, ClassInfo] = classes
        self.subjects: dict[int, SubjectInfo] = subjects
        self.students: dict[int, StudentInfo] = students
        self.assessments: list[AssessmentInfo] = sorted(assessments, key=lambda a: (a.date, a.name.lower()))
        self.by_id = {a.id: a for a in self.assessments}
        self.totals: dict[int, dict[int, float]] = totals
        self.qmarks: dict[int, dict[int, dict]] = qmarks
        self.days: list[AttendanceDayInfo] = days
        self._c: dict = {}

    # ---------------- loading ----------------
    @classmethod
    def load(cls) -> "Gradebook":
        with session_scope() as s:
            classes = {c.id: ClassInfo(c.id, c.name, c.level, c.pass_mark, c.teacher or "", c.scale) for c in s.scalars(select(ClassGroup))}
            # archived students and subjects stay in the database but take no part in any calculation
            subjects = {x.id: SubjectInfo(x.id, x.name, x.code, x.subsidiary) for x in s.scalars(select(Subject).where(Subject.archived_at.is_(None)))}
            students = {x.id: StudentInfo(x.id, x.name, x.class_id, x.reg_no, x.phone, x.remarks or "", dict(x.targets or {}))
                        for x in s.scalars(select(Student).where(Student.archived_at.is_(None)))}
            assessments = [AssessmentInfo(a.id, a.subject_id, a.class_id, a.type, a.name, a.date, float(a.max_marks), list(a.topics or []),
                                          [SectionInfo(x.id, x.name, x.pick) for x in a.sections],
                                          [QuestionInfo(q.id, q.label, q.topic, float(q.max_marks), q.section_id) for q in a.questions])
                           for a in s.scalars(select(Assessment)) if a.subject_id in subjects]   # archived subjects drop out here
            totals: dict[int, dict[int, float]] = {}
            for m in s.scalars(select(Mark)):
                totals.setdefault(m.assessment_id, {})[m.student_id] = float(m.score)
            qmarks: dict[int, dict[int, dict]] = {}
            for qm, aid in s.execute(select(QuestionMark, Question.assessment_id).join(Question, Question.id == QuestionMark.question_id)):
                qmarks.setdefault(aid, {}).setdefault(qm.student_id, {})[qm.question_id] = float(qm.score)
            days = [AttendanceDayInfo(d.id, d.class_id, d.date, [e.student_id for e in d.entries], [e.student_id for e in d.entries if not e.present])
                    for d in s.scalars(select(AttendanceDay))]
        return cls(get_settings(), classes, subjects, students, assessments, totals, qmarks, days)

    def _m(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    # ---------------- basics ----------------
    @property
    def ca_weight(self) -> float:
        return float(self.settings.get("ca_weight", 40)) / 100

    def scale(self, class_id: int) -> Scale:
        def build():
            c = self.classes.get(class_id)
            return make_scale(c.level, c.pass_mark, c.scale) if c else make_scale("A")
        return self._m(("scale", class_id), build)

    def class_name(self, class_id: int) -> str:
        c = self.classes.get(class_id)
        return c.name if c else "?"

    def subject_name(self, sid: int) -> str:
        return self.subjects[sid].name if sid in self.subjects else "Unknown"

    def subject_short(self, sid: int) -> str:
        return self.subjects[sid].short if sid in self.subjects else "?"

    def students_in(self, class_id: int | None) -> list[StudentInfo]:
        return self._m(("st", class_id), lambda: sorted((s for s in self.students.values() if not class_id or s.class_id == class_id), key=lambda s: s.name.lower()))

    def assessments_for(self, class_id=None, subject_id=None, kind: str | None = None) -> list[AssessmentInfo]:
        return [a for a in self.assessments if a.subject_id in self.subjects and (not class_id or a.class_id == class_id)
                and (not subject_id or a.subject_id == subject_id)
                and (kind is None or (kind == "exam") == a.is_exam)]

    def class_subjects(self, class_id: int) -> list[SubjectInfo]:
        ids = {a.subject_id for a in self.assessments_for(class_id)}
        return sorted((self.subjects[i] for i in ids if i in self.subjects), key=lambda x: x.name.lower())

    def all_topics(self, subject_id: int) -> list[str]:
        out = set()
        for a in self.assessments_for(subject_id=subject_id):
            out.update(q.topic for q in a.questions if q.topic) if a.is_paper else out.update(a.topics)
        return sorted(out)

    def has_score(self, a: AssessmentInfo, sid: int) -> bool:
        return sid in self.totals.get(a.id, {})

    def score(self, a: AssessmentInfo, sid: int) -> float | None:
        return self.totals.get(a.id, {}).get(sid)

    def pct(self, a: AssessmentInfo, sid: int) -> float | None:
        v = self.score(a, sid)
        return None if v is None else v / a.max_marks * 100

    def student_assessments(self, stu: StudentInfo, subject_id: int | None = None) -> list[AssessmentInfo]:
        """Assessments of the student's current class plus any they sat elsewhere (moved students keep history)."""
        return [a for a in self.assessments_for(subject_id=subject_id) if a.class_id == stu.class_id or self.has_score(a, stu.id)]

    # ---------------- results ----------------
    def subject_result(self, stu: StudentInfo, subject_id: int) -> SubjectResult | None:
        def build():
            tests, exams, ser = [], [], []
            for a in self.student_assessments(stu, subject_id):
                p = self.pct(a, stu.id)
                if p is not None:
                    (exams if a.is_exam else tests).append(p)
                    ser.append(p)
            if not ser:
                return None
            w, ca, ex = self.ca_weight, avg(tests), avg(exams)
            final = ca * w + ex * (1 - w) if ca is not None and ex is not None else (ca if ca is not None else ex)
            n, my = len(ser), mean(ser)
            proj = max(0.0, min(100.0, my + 0.5 * slope(ser) * (n - (n - 1) / 2))) if n >= 2 else my
            predicted = (ca * w + proj * (1 - w) if ca is not None else proj) if ex is None else final
            return SubjectResult(ca, ex, final, ex is None, n, trend_of(ser), predicted)
        return self._m(("sr", stu.id, subject_id), build)

    def summary(self, stu: StudentInfo) -> Summary:
        def build():
            sc = self.scale(stu.class_id)
            subs, behind = {}, []
            for sid, sub in self.subjects.items():
                r = self.subject_result(stu, sid)
                if not r:
                    continue
                subs[sid] = r
                t = stu.targets.get(str(sid))
                if t and sc.index(sc.letter(r.predicted)) > sc.index(t):
                    behind.append(sub.name)
            series = [p for a in self.student_assessments(stu) if (p := self.pct(a, stu.id)) is not None]
            ents = [(r.final, self.subjects[sid].subsidiary) for sid, r in subs.items()]
            pents = [(r.predicted, self.subjects[sid].subsidiary) for sid, r in subs.items()]
            return Summary(subs, avg(r.final for r in subs.values()), series, trend_of(series), self.att_rate(stu),
                           sc.division(ents), sc.division(pents), behind)
        return self._m(("sum", stu.id), build)

    def total_marks(self, stu: StudentInfo) -> tuple[float, int]:
        f = [r.final for r in self.summary(stu).subs.values()]
        return sum(f), len(f)

    def ranking(self, class_id: int) -> list[RankRow]:
        """Complete divisions first by points, then by average; others after, by average."""
        def build():
            rows = [RankRow(s, self.summary(s)) for s in self.students_in(class_id)]
            rows = [r for r in rows if r.summary.overall is not None]

            def key(r: RankRow):
                d = r.summary.div
                return (0 if d and d.complete else 1, d.points if d and d.complete else 0, -round(r.summary.overall, 6))
            rows.sort(key=key)
            prev, rank = None, 0
            for i, r in enumerate(rows):
                if key(r) != prev:
                    rank = i + 1
                r.rank, prev = rank, key(r)
            return rows
        return self._m(("rank", class_id), build)

    def position(self, stu: StudentInfo) -> tuple[int | None, int]:
        rows = self.ranking(stu.class_id)
        me = next((r for r in rows if r.student.id == stu.id), None)
        return (me.rank if me else None), len(rows)

    def subject_positions(self, class_id: int, subject_id: int) -> tuple[dict[int, int], int]:
        def build():
            res = sorted(((s.id, r.final) for s in self.students_in(class_id) if (r := self.subject_result(s, subject_id))), key=lambda x: -x[1])
            pos, prev, rank = {}, None, 0
            for i, (sid, f) in enumerate(res):
                if prev is None or abs(f - prev) > 1e-9:
                    rank = i + 1
                pos[sid], prev = rank, f
            return pos, len(res)
        return self._m(("sp", class_id, subject_id), build)

    def assess_stats(self, a: AssessmentInfo) -> Stats:
        def build():
            sc = self.scale(a.class_id)
            ps = [v / a.max_marks * 100 for sid, v in self.totals.get(a.id, {}).items() if sid in self.students]
            return Stats(len(ps), avg(ps), max(ps) if ps else None, min(ps) if ps else None,
                         (sum(1 for p in ps if sc.passing(p)) / len(ps) * 100) if ps else None, ps)
        return self._m(("ast", a.id), build)

    # ---------------- attendance ----------------
    def att_rate(self, stu: StudentInfo, after=None, upto=None) -> float | None:
        exp = pres = 0
        for d in self.days:
            if stu.id not in d.roster or (after and d.date <= after) or (upto and d.date > upto):
                continue
            exp += 1
            pres += stu.id not in d.absent
        return pres / exp * 100 if exp else None

    def class_att(self, class_id: int) -> float | None:
        exp = pres = 0
        for d in self.days:
            if d.class_id != class_id:
                continue
            r = [sid for sid in d.roster if sid in self.students]
            exp += len(r)
            pres += sum(1 for sid in r if sid not in d.absent)
        return pres / exp * 100 if exp else None

    def at_risk(self, stu: StudentInfo) -> list[str]:
        sc, s, why = self.scale(stu.class_id), self.summary(stu), []
        if s.overall is not None and not sc.passing(s.overall):
            why.append("below pass mark")
        if s.trend == "down":
            why.append("scores dropping")
        fails = [self.subject_name(k) for k, r in s.subs.items() if not sc.passing(r.final)]
        if fails and sc.passing(s.overall):
            why.append("failing " + ", ".join(fails))
        if s.att is not None and s.att < 80:
            why.append(f"attendance {round(s.att)}%")
        if s.behind:
            why.append("behind target in " + ", ".join(s.behind))
        return why

    # ---------------- question papers ----------------
    @staticmethod
    def _parts(a: AssessmentInfo):
        return ([Sec(x.id, x.name, x.pick) for x in a.sections] or [Sec("main")],
                [Q(q.id, q.label, q.topic, q.max, q.section_id) for q in a.questions])

    def paper_total(self, a: AssessmentInfo, row: dict) -> tuple[float | None, list[str]]:
        secs, qs = self._parts(a)
        return paper_total(secs, qs, row)

    def marked_questions(self, a: AssessmentInfo) -> set:
        return self._m(("mq", a.id), lambda: {qid for row in self.qmarks.get(a.id, {}).values() for qid in row})

    def paper_analysis(self, a: AssessmentInfo) -> PaperAnalysis:
        def build():
            Qm = {sid: row for sid, row in self.qmarks.get(a.id, {}).items() if sid in self.students}
            sitters = [sid for sid, row in Qm.items() if row]
            tot = sorted(((sid, self.paper_total(a, Qm[sid])[0]) for sid in sitters), key=lambda x: -(x[1] or 0))
            k = max(1, round(len(tot) * 0.27))
            upper, lower = {x[0] for x in tot[:k]}, {x[0] for x in tot[-k:]}
            marked, sc = self.marked_questions(a), self.scale(a.class_id)
            qstats = []
            for q in a.questions:
                choice = bool(a.section_of(q).pick)
                if q.id not in marked:
                    qstats.append(QuestionStat(q, choice, False))
                    continue
                att = [sid for sid in sitters if q.id in Qm[sid]]
                pool = att if choice else sitters                        # compulsory blank = 0
                pc = lambda sid: Qm[sid].get(q.id, 0) / q.max * 100
                up, lo = avg(pc(x) for x in pool if x in upper), avg(pc(x) for x in pool if x in lower)
                qstats.append(QuestionStat(q, choice, True, len(att), len(att) / len(sitters) * 100 if sitters else None,
                                           avg(pc(x) for x in pool), (up - lo) / 100 if len(tot) >= 6 and up is not None and lo is not None else None,
                                           sum(1 for x in att if pc(x) >= 99.99), sum(1 for x in att if pc(x) == 0)))
            mq = [q for q in a.questions if q.id in marked]
            topics = []
            for t in dict.fromkeys(q.topic or "Untagged" for q in mq):
                tq = [q for q in mq if (q.topic or "Untagged") == t]
                per = {}
                for sid in sitters:
                    e = p = 0.0
                    for q in tq:
                        v = Qm[sid].get(q.id)
                        if a.section_of(q).pick and v is None:
                            continue
                        p += q.max
                        e += v or 0
                    if p:
                        per[sid] = e / p * 100
                attempted = sum(1 for sid in sitters if any(q.id in Qm[sid] for q in tq))
                topics.append(TopicStat(t, [q.label for q in tq], sum(q.max for q in tq), avg(per.values()), attempted,
                                        attempted / len(sitters) * 100 if sitters else None, per,
                                        sorted(((sid, v) for sid, v in per.items() if not sc.passing(v)), key=lambda x: x[1])))
            topics.sort(key=lambda t: t.facility if t.facility is not None else 999)
            return PaperAnalysis(sitters, qstats, topics)
        return self._m(("pa", a.id), build)

    # ---------------- topics ----------------
    def topic_map(self, stu: StudentInfo, subject_id: int | None = None) -> list[TopicScore]:
        """Per-student topic mastery: question-level on papers, whole-test tags otherwise."""
        def build():
            m: dict[tuple, TopicScore] = {}

            def add(a, t, e, p):
                ts = m.setdefault((a.subject_id, t), TopicScore(a.subject_id, t))
                ts.earned += e
                ts.possible += p
                ts.assessments.add(a.id)
            for a in self.student_assessments(stu, subject_id):
                if a.is_paper:
                    row = self.qmarks.get(a.id, {}).get(stu.id)
                    if not row:
                        continue
                    marked = self.marked_questions(a)
                    for q in a.questions:
                        if not q.topic or q.id not in marked:
                            continue
                        v = row.get(q.id)
                        if a.section_of(q).pick and v is None:
                            continue
                        add(a, q.topic, v or 0, q.max)
                elif self.has_score(a, stu.id):
                    for t in a.topics:
                        add(a, t, self.score(a, stu.id), a.max_marks)
            return [t for t in m.values() if t.possible > 0]
        return self._m(("tm", stu.id, subject_id), build)

    def student_topics(self, stu: StudentInfo) -> list[TopicScore]:
        return sorted(self.topic_map(stu), key=lambda t: t.mean)

    def topic_stats(self, class_id: int, subject_id: int) -> list[ClassTopicStat]:
        agg: dict[str, dict] = {}
        for st in self.students_in(class_id):
            for t in self.topic_map(st, subject_id):
                d = agg.setdefault(t.topic, {"per": [], "as": set()})
                d["per"].append((st, t.mean))
                d["as"].update(t.assessments)
        sc = self.scale(class_id)
        out = [ClassTopicStat(k, len(v["as"]), avg(p for _, p in v["per"]), sorted(v["per"], key=lambda x: x[1]),
                              sum(1 for _, p in v["per"] if not sc.passing(p))) for k, v in agg.items()]
        return sorted(out, key=lambda x: x.mean if x.mean is not None else 999)

    @cached_property
    def has_data(self) -> bool:
        return bool(self.students)