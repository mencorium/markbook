# /markbook/backend/attendance_codes.py
"""What the marks in a register mean.

A single present/absent flag cannot tell a sick student from one who stayed away, so each entry
carries a code. Whether an absence is *excused* is what decides the figures Markbook judges a
student on: a child off sick should never have their report card say attendance must improve.
"""
from __future__ import annotations

from dataclasses import dataclass

PRESENT = "P"
ABSENT = "A"
SICK = "S"
PERMIT = "PM"
SUSPENDED = "SS"


@dataclass(frozen=True)
class Code:
    code: str
    name: str
    meaning: str
    here: bool                      # was the student in the lesson?
    excused: bool                   # if not, was the absence authorised?

    @property
    def label(self) -> str:
        return f"{self.code} — {self.name}"

    @property
    def counts_against(self) -> bool:
        """An unexcused absence: the only kind that should drag a student's record down."""
        return not self.here and not self.excused


CODES: list[Code] = [
    Code(PRESENT, "Present", "In the lesson.", here=True, excused=False),
    Code(ABSENT, "Absent", "Away, with no reason given.", here=False, excused=False),
    Code(SICK, "Sick", "Away unwell.", here=False, excused=True),
    Code(PERMIT, "Permit", "Away with permission.", here=False, excused=True),
    Code(SUSPENDED, "Suspended", "Not allowed to attend.", here=False, excused=True),
]

BY_CODE = {c.code: c for c in CODES}
ORDER = [c.code for c in CODES]
DEFAULT = PRESENT


def get(code: str | None) -> Code:
    """Unknown codes read as absent rather than silently counting as present."""
    return BY_CODE.get((code or "").strip().upper(), BY_CODE[ABSENT])


def is_present(code: str | None) -> bool:
    return get(code).here


def is_excused(code: str | None) -> bool:
    c = get(code)
    return not c.here and c.excused


def counts_against(code: str | None) -> bool:
    return get(code).counts_against


def name(code: str | None) -> str:
    return get(code).name


def legend() -> str:
    return "   ".join(f"{c.code} {c.name.lower()}" for c in CODES)


def from_present(present: bool) -> str:
    """For rows written before codes existed."""
    return PRESENT if present else ABSENT