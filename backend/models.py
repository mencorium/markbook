# /markbook/backend/models.py
"""Database tables (SQLAlchemy 2.0 ORM)."""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")
Score = Numeric(7, 2, asdecimal=False)


class Base(DeclarativeBase):
    pass


class Setting(Base):
    """Key/value settings: school, term, ca_weight, head_teacher, next_term."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType, nullable=True)


class Term(Base):
    """A teaching period with its own results. Length is up to the school: two six-month terms,
    three shorter ones, or anything else. Several terms make an academic year."""
    __tablename__ = "terms"
    __table_args__ = (UniqueConstraint("name", "year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))                 # "Term 1"
    year: Mapped[str] = mapped_column(String(20))                 # "2026" or "2026/2027"
    starts_on: Mapped[dt.date] = mapped_column(Date)
    ends_on: Mapped[dt.date] = mapped_column(Date)
    weight: Mapped[float] = mapped_column(Score, default=1)        # share in the annual result
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class ClassGroup(Base):
    __tablename__ = "classes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    level: Mapped[str] = mapped_column(String(10), default="A")          # 'A', 'O' or 'custom'
    pass_mark: Mapped[float | None] = mapped_column(Score, nullable=True)
    teacher: Mapped[str] = mapped_column(String(120), default="")
    scale: Mapped[Any] = mapped_column(JSONType, nullable=True)            # custom scale rows
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    year: Mapped[str] = mapped_column(String(20), default="")              # academic year this class is running in
    rollover: Mapped[str] = mapped_column(String(10), default="promote")   # promote | continue | group

    students: Mapped[list["Student"]] = relationship(back_populates="class_group")


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str] = mapped_column(String(10), default="")
    subsidiary: Mapped[bool] = mapped_column(Boolean, default=False)       # not counted in A-Level division
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)   # hidden, not deleted


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    reg_no: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # E.164, for messaging later
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="RESTRICT"))
    remarks: Mapped[str] = mapped_column(Text, default="")
    targets: Mapped[Any] = mapped_column(JSONType, default=dict)           # {subject_id: grade}
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)   # left the class, records kept

    class_group: Mapped[ClassGroup] = relationship(back_populates="students")


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20), default="Test")          # Test, Quiz, Assignment, Exam
    name: Mapped[str] = mapped_column(String(120))
    date: Mapped[dt.date] = mapped_column(Date)
    max_marks: Mapped[float] = mapped_column(Score, default=100)
    topics: Mapped[Any] = mapped_column(JSONType, default=list)            # whole-test tags (non-paper)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="RESTRICT"), nullable=True, index=True)

    sections: Mapped[list["PaperSection"]] = relationship(cascade="all, delete-orphan", order_by="PaperSection.position")
    questions: Mapped[list["Question"]] = relationship(cascade="all, delete-orphan", order_by="Question.position")


class PaperSection(Base):
    """A section of a question paper. pick=N means 'answer any N'."""
    __tablename__ = "paper_sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(60), default="")
    pick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    section_id: Mapped[int] = mapped_column(ForeignKey("paper_sections.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(20))
    topic: Mapped[str] = mapped_column(String(120), default="")
    max_marks: Mapped[float] = mapped_column(Score)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Mark(Base):
    """Total mark for a student on an assessment (computed from questions on papers)."""
    __tablename__ = "marks"
    __table_args__ = (UniqueConstraint("assessment_id", "student_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Score)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)


class QuestionMark(Base):
    __tablename__ = "question_marks"
    __table_args__ = (UniqueConstraint("question_id", "student_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Score)


class AttendanceDay(Base):
    __tablename__ = "attendance_days"
    __table_args__ = (UniqueConstraint("class_id", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    date: Mapped[dt.date] = mapped_column(Date)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="RESTRICT"), nullable=True, index=True)
    entries: Mapped[list["AttendanceEntry"]] = relationship(cascade="all, delete-orphan")


class AttendanceEntry(Base):
    """One row per student expected that day (the roster); present=False means absent."""
    __tablename__ = "attendance_entries"
    day_id: Mapped[int] = mapped_column(ForeignKey("attendance_days.id", ondelete="CASCADE"), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), primary_key=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    """Who changed what, and when. Rows are never updated or deleted by the app, and hold no
    foreign keys, so the history of a mark survives the student or assessment being removed."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    who: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40), index=True)     # mark.changed, student.archived, …
    entity: Mapped[str] = mapped_column(String(20))                 # mark, student, subject, assessment, database
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    student_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    assessment_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    old_value: Mapped[str | None] = mapped_column(String(60), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(60), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")