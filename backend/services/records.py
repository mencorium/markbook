# /markbook/backend/services/records.py
"""Settings, classes, subjects and students."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from ..db import session_scope
from ..models import Assessment, ClassGroup, Setting, Student, Subject
from ..phone import normalize_phone
from ..schema import ClassInfo, StudentInfo, SubjectInfo


class ValidationError(ValueError):
    """Raised with a message that can be shown to the user as-is."""


# ---------------- settings ----------------
DEFAULT_SETTINGS = {"school": "", "term": "", "ca_weight": 40, "head_teacher": "", "next_term": "",
                    "auto_backup": True, "backup_dir": "", "last_backup": "", "pg_bin_dir": ""}


def get_settings() -> dict:
    with session_scope() as s:
        rows = {r.key: r.value for r in s.scalars(select(Setting))}
    return {**DEFAULT_SETTINGS, **rows}


def save_settings(values: dict) -> None:
    with session_scope() as s:
        for k, v in values.items():
            if k not in DEFAULT_SETTINGS:
                continue
            row = s.get(Setting, k)
            if row:
                row.value = v
            else:
                s.add(Setting(key=k, value=v))


# ---------------- classes ----------------
def _class_info(c: ClassGroup) -> ClassInfo:
    return ClassInfo(c.id, c.name, c.level, c.pass_mark, c.teacher or "", c.scale)


def list_classes() -> list[ClassInfo]:
    with session_scope() as s:
        return [_class_info(c) for c in s.scalars(select(ClassGroup).order_by(ClassGroup.name))]


def get_or_create_class(name: str) -> ClassInfo:
    name = name.strip()
    if not name:
        raise ValidationError("Enter a class name.")
    with session_scope() as s:
        c = s.scalar(select(ClassGroup).where(func.lower(ClassGroup.name) == name.lower()))
        if not c:
            c = ClassGroup(name=name, level="A")
            s.add(c)
            s.flush()
        return _class_info(c)


def save_class(class_id: int, *, name: str, level: str, pass_mark: float | None, teacher: str, scale: list | None = None) -> ClassInfo:
    name = name.strip()
    if not name:
        raise ValidationError("Enter a class name.")
    if level not in ("A", "O", "custom"):
        raise ValidationError("Choose a grading level.")
    with session_scope() as s:
        clash = s.scalar(select(ClassGroup).where(func.lower(ClassGroup.name) == name.lower(), ClassGroup.id != class_id))
        if clash:
            raise ValidationError(f"A class called {name} already exists.")
        c = s.get(ClassGroup, class_id)
        c.name, c.level, c.pass_mark, c.teacher = name, level, pass_mark, teacher.strip()
        c.scale = scale if level == "custom" else None
        return _class_info(c)


def delete_class(class_id: int) -> None:
    with session_scope() as s:
        if s.scalar(select(func.count()).select_from(Student).where(Student.class_id == class_id)):
            raise ValidationError("Move, archive or remove the students in this class first "
                                  "(archived students still belong to their class).")
        s.delete(s.get(ClassGroup, class_id))


# ---------------- subjects ----------------
def list_subjects(archived: bool = False) -> list[SubjectInfo]:
    with session_scope() as s:
        q = select(Subject).where(Subject.archived_at.is_not(None) if archived else Subject.archived_at.is_(None)).order_by(Subject.name)
        return [SubjectInfo(x.id, x.name, x.code, x.subsidiary, x.archived_at) for x in s.scalars(q)]


def archive_subjects(subject_ids: list[int]) -> tuple[int, int]:
    """Hide subjects and their assessments from results and exports, without deleting any marks.
    Returns (subjects archived, assessments hidden)."""
    now = dt.datetime.now()
    with session_scope() as s:
        subjects = assessments = 0
        for sid in subject_ids:
            x = s.get(Subject, sid)
            if x and x.archived_at is None:
                x.archived_at = now
                assessments += s.scalar(select(func.count()).select_from(Assessment).where(Assessment.subject_id == sid)) or 0
                subjects += 1
        return subjects, assessments


def restore_subjects(subject_ids: list[int]) -> int:
    with session_scope() as s:
        n = 0
        for sid in subject_ids:
            x = s.get(Subject, sid)
            if x and x.archived_at is not None:
                x.archived_at = None
                n += 1
        return n


def save_subject(subject_id: int | None, *, name: str, code: str = "", subsidiary: bool = False) -> SubjectInfo:
    name = name.strip()
    if not name:
        raise ValidationError("Enter a subject name.")
    with session_scope() as s:
        clash = s.scalar(select(Subject).where(func.lower(Subject.name) == name.lower(), Subject.id != (subject_id or 0)))
        if clash:
            raise ValidationError(f"{name} already exists.")
        x = s.get(Subject, subject_id) if subject_id else Subject()
        x.name, x.code, x.subsidiary = name, code.strip().upper()[:10], subsidiary
        s.add(x)
        s.flush()
        return SubjectInfo(x.id, x.name, x.code, x.subsidiary, x.archived_at)


def delete_subject(subject_id: int) -> int:
    """Deletes the subject and (by cascade) its assessments and marks. Returns the number of assessments removed."""
    return delete_subjects([subject_id])[1]


def delete_subjects(subject_ids: list[int]) -> tuple[int, int]:
    """Delete one or many subjects in a single transaction.
    Returns (subjects deleted, assessments deleted) — the marks go with the assessments."""
    with session_scope() as s:
        subjects = assessments = 0
        for sid in subject_ids:
            x = s.get(Subject, sid)
            if not x:
                continue
            assessments += s.scalar(select(func.count()).select_from(Assessment).where(Assessment.subject_id == sid)) or 0
            s.delete(x)
            subjects += 1
        return subjects, assessments


# ---------------- students ----------------
def _student_info(x: Student) -> StudentInfo:
    return StudentInfo(x.id, x.name, x.class_id, x.reg_no, x.phone, x.remarks or "", dict(x.targets or {}), x.archived_at)


def list_students(class_id: int | None = None, archived: bool = False) -> list[StudentInfo]:
    with session_scope() as s:
        q = select(Student).where(Student.archived_at.is_not(None) if archived else Student.archived_at.is_(None))
        q = q.order_by(Student.archived_at.desc(), Student.name) if archived else q.order_by(Student.name)
        if class_id:
            q = q.where(Student.class_id == class_id)
        return [_student_info(x) for x in s.scalars(q)]


def archive_students(student_ids: list[int]) -> int:
    """Hide students from class lists, results and exports. Their marks and attendance stay."""
    now = dt.datetime.now()
    with session_scope() as s:
        n = 0
        for sid in student_ids:
            x = s.get(Student, sid)
            if x and x.archived_at is None:
                x.archived_at = now
                n += 1
        return n


def restore_students(student_ids: list[int]) -> int:
    with session_scope() as s:
        n = 0
        for sid in student_ids:
            x = s.get(Student, sid)
            if x and x.archived_at is not None:
                x.archived_at = None
                n += 1
        return n


def get_student(student_id: int) -> StudentInfo | None:
    with session_scope() as s:
        x = s.get(Student, student_id)
        return _student_info(x) if x else None


def save_student(student_id: int | None, *, name: str, class_name: str, reg_no: str | None = None, phone: str | None = None) -> StudentInfo:
    """Create or update. Moving a student to another class keeps all their marks and attendance."""
    name = " ".join(name.split())
    if not name:
        raise ValidationError("Enter the student's name.")
    try:
        phone_e164 = normalize_phone(phone)
    except ValueError as e:
        raise ValidationError(str(e)) from e
    reg = (reg_no or "").strip() or None
    if reg and reg.lower() == "null":
        reg = None
    cls = get_or_create_class(class_name)
    with session_scope() as s:
        if reg and s.scalar(select(Student).where(func.lower(Student.reg_no) == reg.lower(), Student.id != (student_id or 0))):
            raise ValidationError(f"Reg. number {reg} already belongs to another student.")
        x = s.get(Student, student_id) if student_id else Student(targets={}, remarks="")
        x.name, x.reg_no, x.phone, x.class_id = name, reg, phone_e164, cls.id
        s.add(x)
        s.flush()
        return _student_info(x)


def set_remarks(student_id: int, remarks: str) -> None:
    with session_scope() as s:
        s.get(Student, student_id).remarks = remarks.strip()


def set_target(student_id: int, subject_id: int, grade: str | None) -> None:
    with session_scope() as s:
        x = s.get(Student, student_id)
        t = dict(x.targets or {})
        if grade:
            t[str(subject_id)] = grade
        else:
            t.pop(str(subject_id), None)
        x.targets = t


def delete_student(student_id: int) -> int:
    return delete_students([student_id])


def delete_students(student_ids: list[int]) -> int:
    """Delete one or many students in a single transaction; their marks and attendance go with them."""
    with session_scope() as s:
        n = 0
        for sid in student_ids:
            x = s.get(Student, sid)
            if x:
                s.delete(x)
                n += 1
        return n


def bulk_add_students(lines: str, class_name: str) -> int:
    """One student per line: 'Name, RegNo, Phone' (reg and phone optional)."""
    n = 0
    for line in lines.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if parts and parts[0]:
            save_student(None, name=parts[0], class_name=class_name,
                         reg_no=parts[1] if len(parts) > 1 else None, phone=parts[2] if len(parts) > 2 else None)
            n += 1
    return n