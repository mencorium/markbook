# /markbook/backend/schemas.py
"""Plain data objects handed to the frontend. The UI never touches ORM objects or sessions,
so this service layer can later sit behind a REST API without changing the screens."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class TermInfo:
    id: int
    name: str
    year: str
    starts_on: dt.date
    ends_on: dt.date
    weight: float = 1.0

    @property
    def label(self) -> str:
        return f"{self.name} · {self.year}"

    def covers(self, day: dt.date) -> bool:
        return self.starts_on <= day <= self.ends_on


@dataclass
class ClassInfo:
    id: int
    name: str
    level: str = "A"
    pass_mark: float | None = None
    teacher: str = ""
    scale: list | None = None
    year: str = ""
    rollover: str = "promote"


@dataclass
class SubjectInfo:
    id: int
    name: str
    code: str = ""
    subsidiary: bool = False
    archived_at: dt.datetime | None = None

    @property
    def short(self) -> str:
        return self.code or self.name


@dataclass
class StudentInfo:
    id: int
    name: str
    class_id: int
    reg_no: str | None = None
    phone: str | None = None
    remarks: str = ""
    targets: dict = field(default_factory=dict)      # {subject_id(str): grade}
    archived_at: dt.datetime | None = None


@dataclass
class SectionInfo:
    id: int | str
    name: str = ""
    pick: int | None = None


@dataclass
class QuestionInfo:
    id: int | str
    label: str
    topic: str
    max: float
    section_id: int | str


@dataclass
class AssessmentInfo:
    id: int
    subject_id: int
    class_id: int
    type: str
    name: str
    date: dt.date
    max_marks: float
    topics: list = field(default_factory=list)
    sections: list[SectionInfo] = field(default_factory=list)
    questions: list[QuestionInfo] = field(default_factory=list)
    term_id: int | None = None

    @property
    def is_paper(self) -> bool:
        return bool(self.questions)

    @property
    def is_exam(self) -> bool:
        return self.type == "Exam"

    def section_of(self, q: QuestionInfo) -> SectionInfo:
        for s in self.sections:
            if s.id == q.section_id:
                return s
        return self.sections[0] if self.sections else SectionInfo("main")


@dataclass
class AttendanceDayInfo:
    id: int
    class_id: int
    date: dt.date
    roster: list[int]
    absent: list[int]
    term_id: int | None = None