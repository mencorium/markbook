# /markbook/backend/grading.py
"""Grade scales (NECTA A-Level, O-Level, custom), points and divisions. Pure functions, no database."""
from __future__ import annotations

from dataclasses import dataclass, field

PRESETS: dict[str, dict] = {
    "A": {
        "label": "NECTA A-Level", "pass_mark": 40, "best": 3, "best_note": "best 3 principal subjects",
        "rows": [("A", 80, 1), ("B", 70, 2), ("C", 60, 3), ("D", 50, 4), ("E", 40, 5), ("S", 35, 6), ("F", 0, 7)],
        "div": [(3, 9, "I"), (10, 12, "II"), (13, 17, "III"), (18, 19, "IV"), (20, 21, "0")],
    },
    "O": {
        "label": "NECTA O-Level", "pass_mark": 30, "best": 7, "best_note": "best 7 subjects",
        "rows": [("A", 75, 1), ("B", 65, 2), ("C", 45, 3), ("D", 30, 4), ("F", 0, 5)],
        "div": [(7, 17, "I"), (18, 21, "II"), (22, 25, "III"), (26, 33, "IV"), (34, 35, "0")],
    },
}
DIVISIONS = ["I", "II", "III", "IV", "0"]
LEVEL_LABELS = {"A": "NECTA A-Level", "O": "NECTA O-Level", "custom": "Custom scale"}


@dataclass(frozen=True)
class GradeRow:
    grade: str
    min: float
    points: int | None = None


@dataclass(frozen=True)
class Division:
    complete: bool
    points: int | None = None
    div: str | None = None
    need: int | None = None
    have: int | None = None

    def text(self) -> str:
        return f"Div {self.div} ({self.points})" if self.complete else f"Needs {self.need} subjects"


@dataclass
class Scale:
    level: str
    label: str
    pass_mark: float
    rows: list[GradeRow]                       # sorted best (highest min) first
    best: int | None = None
    div: list[tuple[int, int, str]] | None = None
    best_note: str = ""
    grades: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.rows = sorted(self.rows, key=lambda r: -r.min)
        self.grades = [r.grade for r in self.rows]

    def row(self, pct: float | None) -> GradeRow | None:
        if pct is None:
            return None
        for r in self.rows:
            if pct >= r.min:
                return r
        return self.rows[-1]

    def letter(self, pct: float | None) -> str:
        r = self.row(pct)
        return r.grade if r else "–"

    def points(self, pct: float | None) -> int | None:
        r = self.row(pct)
        return r.points if r else None

    def passing(self, pct: float | None) -> bool:
        return pct is not None and pct >= self.pass_mark

    def index(self, grade: str) -> int:
        return self.grades.index(grade) if grade in self.grades else len(self.grades)

    def division(self, entries: list[tuple[float, bool]]) -> Division | None:
        """entries: (percentage, is_subsidiary). A-Level ignores subsidiary subjects."""
        if not self.div or not self.best:
            return None
        pts = sorted(self.points(p) for p, sub in entries if not (self.level == "A" and sub) and p is not None)
        if len(pts) < self.best:
            return Division(False, need=self.best, have=len(pts))
        total = sum(pts[: self.best])
        for lo, hi, name in self.div:
            if lo <= total <= hi:
                return Division(True, points=total, div=name)
        return Division(True, points=total, div="0")

    def remark(self, grade: str) -> str:
        words = {"A": "Excellent", "B": "Very good", "C": "Good", "D": "Satisfactory", "E": "Pass", "S": "Weak pass", "F": "Fail"}
        if self.level != "custom" and grade in words:
            return "Pass" if (self.level == "O" and grade == "D") else words[grade]
        i = self.index(grade)
        if i >= len(self.rows):
            return ""
        if self.rows[i].min < self.pass_mark:
            return "Fail"
        return ["Excellent", "Very good", "Good", "Satisfactory", "Pass"][min(4, int(i / max(1, len(self.rows) - 1) * 5))]


def make_scale(level: str = "A", pass_mark: float | None = None, custom_rows: list | None = None) -> Scale:
    if level == "custom":
        rows = [GradeRow(r["grade"], float(r["min"]), r.get("points")) for r in (custom_rows or [])]
        if not rows:
            rows = [GradeRow(g, m, p) for g, m, p in PRESETS["A"]["rows"]]
        return Scale("custom", LEVEL_LABELS["custom"], 40 if pass_mark is None else float(pass_mark), rows)
    p = PRESETS.get(level, PRESETS["A"])
    return Scale(level if level in PRESETS else "A", p["label"], p["pass_mark"] if pass_mark is None else float(pass_mark),
                 [GradeRow(g, m, pts) for g, m, pts in p["rows"]], p["best"], p["div"], p["best_note"])