# /markbook/backend/services/exports.py
"""Mark sheets for Excel and CSV. A Sheet is a centred title block + table + optional summary lines.
Columns show either marks or grades, never both."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..phone import display_phone
from .analytics import TREND_WORDS, Gradebook, difficulty, discrimination_label


@dataclass
class Sheet:
    name: str
    meta: list[str]
    head: list[str]
    body: list[list]
    foot: list[tuple[str, object]] = field(default_factory=list)
    left: tuple[int, ...] = (1, 2)            # left-aligned columns; others centred

    def rows(self) -> list[list]:
        out = [[m] for m in self.meta] + [[], self.head] + self.body
        if self.foot:
            out += [[]] + [[k, "", "", v] for k, v in self.foot]
        return out


def r1(v):
    return "" if v is None else num(round(v, 1))


def num(v):
    """9.0 -> 9 so sheets show whole marks cleanly."""
    return int(v) if isinstance(v, float) and v.is_integer() else v


def reg_of(reg: str | None, null_reg: bool) -> str:
    return reg if reg else ("null" if null_reg else "")


def _meta(gb: Gradebook, class_id: int, *lines: str) -> list[str]:
    """The Class line must stay exactly the class name: these sheets import back into the app."""
    school = (gb.settings.get("school") or "").strip()
    term = [f"Term: {gb.term.label}"] if gb.term else []
    return ([school.upper()] if school else []) + [f"Class: {gb.class_name(class_id)}", *term, *lines]


# ---------------- builders ----------------
def single_sheets(gb: Gradebook, assessment_id: int, show: str = "marks", null_reg: bool = True) -> list[Sheet]:
    a = gb.by_id[assessment_id]
    st, sc, grades = gb.assess_stats(a), gb.scale(a.class_id), show == "grades"
    studs = gb.students_in(a.class_id)
    lines = [f"Subject: {gb.subject_name(a.subject_id)}", f"Assessment: {a.name}", f"Type: {a.type}", f"Date: {a.date.isoformat()}"]
    if grades:
        foot = [(f"Grade {g}", sum(1 for p in st.pcts if sc.letter(p) == g)) for g in sc.grades]
    else:
        mk = lambda v: r1(None if v is None else v * a.max_marks / 100)
        foot = [("Students marked", st.n), ("Mean mark", mk(st.mean)), ("Highest mark", mk(st.hi)), ("Lowest mark", mk(st.lo)), ("Pass rate %", r1(st.pass_rate))]
    fname = f"{gb.subject_short(a.subject_id)} {a.name}"
    if not a.is_paper:
        body = [[i + 1, reg_of(s.reg_no, null_reg), s.name,
                 (sc.letter(gb.pct(a, s.id)) if grades else num(gb.score(a, s.id))) if gb.has_score(a, s.id) else "ABS"] for i, s in enumerate(studs)]
        return [Sheet(fname, _meta(gb, a.class_id, *lines), ["S/N", "Reg. No.", "Student Name", "Grade" if grades else f"Marks (/{a.max_marks:g})"], body, foot)]
    # question paper
    pa, Qm = gb.paper_analysis(a), gb.qmarks.get(a.id, {})
    choice = "; ".join(f"{x.name or 'Section'} answer any {x.pick} of {', '.join(q.label for q in a.questions if a.section_of(q).id == x.id)}"
                       for x in a.sections if x.pick)
    if choice:
        lines.append(f"Choice: {choice}")
    topics = [t.topic for t in pa.topics]
    if grades:
        head = ["S/N", "Reg. No.", "Student Name", *topics, "Grade"]
        body = [[i + 1, reg_of(s.reg_no, null_reg), s.name,
                 *[("" if s.id not in pa.sitters else "–" if t.per.get(s.id) is None else sc.letter(t.per[s.id])) for t in pa.topics],
                 sc.letter(gb.pct(a, s.id)) if gb.has_score(a, s.id) else "ABS"] for i, s in enumerate(studs)]
    else:
        head = ["S/N", "Reg. No.", "Student Name", *[f"{q.label}{' · ' + q.topic if q.topic else ''} (/{q.max:g})" for q in a.questions], f"Total Marks (/{a.max_marks:g})"]
        body = [[i + 1, reg_of(s.reg_no, null_reg), s.name, *[num(Qm.get(s.id, {}).get(q.id, "")) for q in a.questions],
                 num(gb.score(a, s.id)) if gb.has_score(a, s.id) else "ABS"] for i, s in enumerate(studs)]
    sheets = [Sheet(fname, _meta(gb, a.class_id, *lines), head, body, foot)]
    names = lambda ids: ", ".join(gb.students[i].name for i, _ in ids if i in gb.students)
    sheets.append(Sheet("Topic analysis", _meta(gb, a.class_id, *lines[:2], "Report: Topic analysis (hardest first)"),
                        ["Topic", "Questions", "Marks", "Answered by", "Answered %", "Average %", "Difficulty", "Below pass", "Students below pass"],
                        [[t.topic, ", ".join(t.questions), t.marks, t.attempted, r1(t.att_rate), r1(t.facility), difficulty(t.facility), len(t.struggling), names(t.struggling)] for t in pa.topics],
                        left=(0, 1, 8)))
    sheets.append(Sheet("Question analysis", _meta(gb, a.class_id, *lines[:2], "Report: Question analysis"),
                        ["Question", "Section", "Topic", "Marks", "Answered by", "Answered %", "Average %", "Difficulty", "Discrimination", "Full marks", "Scored 0"],
                        [[q.q.label, a.section_of(q.q).name or ("Choice" if q.choice else "Compulsory"), q.q.topic, q.q.max, q.attempted, r1(q.att_rate), r1(q.facility),
                          difficulty(q.facility), "" if q.disc is None else f"{q.disc:.2f} {discrimination_label(q.disc)}", q.full, q.zero] for q in pa.questions],
                        left=(0, 1, 2)))
    if not grades:
        sheets.append(Sheet("Students by topic", _meta(gb, a.class_id, *lines[:2], "Report: Each student by topic (% of topic marks)"),
                            ["S/N", "Reg. No.", "Student Name", *topics, "Needs help with"],
                            [[i + 1, reg_of(s.reg_no, null_reg), s.name,
                              *[("ABS" if s.id not in pa.sitters else "–" if t.per.get(s.id) is None else r1(t.per[s.id])) for t in pa.topics],
                              ", ".join(t.topic for t in pa.topics if t.per.get(s.id) is not None and not sc.passing(t.per[s.id]))] for i, s in enumerate(studs)],
                            left=(1, 2, len(topics) + 3)))
    return sheets


def subject_sheet(gb: Gradebook, class_id: int, subject_id: int, show: str = "marks", null_reg: bool = True) -> Sheet:
    as_, (pos, _), w, grades, sc = gb.assessments_for(class_id, subject_id), gb.subject_positions(class_id, subject_id), gb.settings.get("ca_weight", 40), show == "grades", gb.scale(class_id)
    head = ["S/N", "Reg. No.", "Student Name", *[a.name if grades else f"{a.name} (/{a.max_marks:g})" for a in as_],
            *(["Final Grade"] if grades else ["Tests %", "Exam %", "Final %"]), "Position", "Trend"]
    body = []
    for i, s in enumerate(gb.students_in(class_id)):
        r = gb.subject_result(s, subject_id)
        cells = [(sc.letter(gb.pct(a, s.id)) if grades else num(gb.score(a, s.id))) if gb.has_score(a, s.id) else "ABS" for a in as_]
        tail = [sc.letter(r.final) if r else ""] if grades else [r1(r.ca) if r else "", r1(r.ex) if r else "", r1(r.final) if r else ""]
        body.append([i + 1, reg_of(s.reg_no, null_reg), s.name, *cells, *tail, pos.get(s.id, ""), TREND_WORDS[r.trend] if r and r.n >= 3 else ""])
    return Sheet(gb.subject_short(subject_id), _meta(gb, class_id, f"Subject: {gb.subject_name(subject_id)}", "Report: Cumulative progress",
                                                     f"Final mark: Tests {w}% + Exams {100 - int(w)}%"), head, body)


def class_sheets(gb: Gradebook, class_id: int, show: str = "marks", null_reg: bool = True) -> list[Sheet]:
    subs, sc, grades = gb.class_subjects(class_id), gb.scale(class_id), show == "grades"
    ranks = {r.student.id: r.rank for r in gb.ranking(class_id)}
    head = ["S/N", "Reg. No.", "Student Name", *[x.short for x in subs],
            *((["Points", "Division"] if sc.div else ["Grade"]) if grades else ["Total", "Average %"]), "Position"]
    body = []
    for i, s in enumerate(gb.students_in(class_id)):
        sm = gb.summary(s)
        cells = [("" if x.id not in sm.subs else sc.letter(sm.subs[x.id].final) if grades else r1(sm.subs[x.id].final)) for x in subs]
        if grades:
            tail = [sm.div.points if sm.div and sm.div.complete else "", sm.div.div if sm.div and sm.div.complete else ""] if sc.div else [sc.letter(sm.overall)]
        else:
            tail = [r1(gb.total_marks(s)[0]) if sm.subs else "", r1(sm.overall)]
        body.append([i + 1, reg_of(s.reg_no, null_reg), s.name, *cells, *tail, ranks.get(s.id, "")])
    summary = Sheet("Class summary", _meta(gb, class_id, "Subject: All subjects", "Report: Cumulative class summary", f"Grading: {sc.label}"), head, body)
    return [summary, *[subject_sheet(gb, class_id, x.id, show, null_reg) for x in subs]]


def class_list_sheet(gb: Gradebook, class_id: int, null_reg: bool = True) -> Sheet:
    return Sheet("Class list", _meta(gb, class_id, "Report: Class list"), ["S/N", "Reg. No.", "Student Name", "Phone"],
                 [[i + 1, reg_of(s.reg_no, null_reg), s.name, display_phone(s.phone)] for i, s in enumerate(gb.students_in(class_id))], left=(1, 2, 3))


def student_progress_sheets(gb: Gradebook, student_id: int) -> list[Sheet]:
    stu = gb.students[student_id]
    sm, sc = gb.summary(stu), gb.scale(stu.class_id)
    rank, n = gb.position(stu)
    total, k = gb.total_marks(stu)
    info = [f"Student: {stu.name}", f"Reg. No.: {stu.reg_no or 'null'}",
            f"Position: {rank or '-'} of {n}  |  Total marks: {total:.1f} of {k * 100}  |  Average: {r1(sm.overall)}% ({sc.letter(sm.overall)})"
            + (f"  |  Division {sm.div.div} ({sm.div.points} points)" if sm.div and sm.div.complete else "")]
    rows = []
    for sid, r in sorted(sm.subs.items(), key=lambda x: gb.subject_name(x[0])):
        pos, of = gb.subject_positions(stu.class_id, sid)
        g = sc.letter(r.final)
        rows.append([gb.subject_name(sid), r1(r.ca), r1(r.ex), r1(r.final), g, *([sc.points(r.final)] if sc.div else []),
                     f"{pos.get(stu.id, '-')} of {of}", TREND_WORDS[r.trend] if r.n >= 3 else "", sc.remark(g)])
    main = Sheet("Summary", _meta(gb, stu.class_id, *info, "Report: Progress per subject"),
                 ["Subject", "Tests %", "Exam %", "Total %", "Grade", *(["Points"] if sc.div else []), "Position", "Trend", "Remark"], rows,
                 [("Total marks", f"{total:.1f} of {k * 100}"), ("Average %", r1(sm.overall)), ("Position", f"{rank or '-'} of {n}")], left=(0,))
    out = [main]
    for sid in sorted(sm.subs, key=gb.subject_name):
        out.append(Sheet(gb.subject_short(sid), _meta(gb, stu.class_id, f"Student: {stu.name}", f"Subject: {gb.subject_name(sid)}"),
                         ["Date", "Assessment", "Type", "Marks", "Out of", "%", "Grade", "Class average %"],
                         [[a.date.isoformat(), a.name, a.type, num(gb.score(a, stu.id)) if gb.has_score(a, stu.id) else "ABS", num(a.max_marks),
                           r1(gb.pct(a, stu.id)), sc.letter(gb.pct(a, stu.id)) if gb.has_score(a, stu.id) else "", r1(gb.assess_stats(a).mean)]
                          for a in gb.student_assessments(stu, sid)], left=(1,)))
    return out


# ---------------- writers ----------------
NAVY, GREY, ZEBRA, RED = "16263D", "DCE3EB", "EEF2F6", "C8322B"
_thin = Side(style="thin", color="8A97A8")
_box = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


def write_xlsx(path: str | Path, sheets: list[Sheet]) -> Path:
    wb, used = Workbook(), set()
    wb.remove(wb.active)
    for sh in sheets:
        title = "".join(c for c in sh.name if c not in '[]:*?/\\')[:31] or "Sheet"
        base, k = title, 2
        while title in used:
            title = f"{base[:28]} {k}"
            k += 1
        used.add(title)
        ws = wb.create_sheet(title)
        width = len(sh.head)
        for r, line in enumerate(sh.meta, start=1):
            ws.cell(r, 1, line)
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=width)
            big = r == 1 and line.isupper() and not line.startswith("CLASS:")
            ws.cell(r, 1).font = Font(name="Calibri", size=15 if big else 11, bold=True, color=NAVY)
            ws.cell(r, 1).alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[r].height = 24 if big else 17
        h = len(sh.meta) + 2
        for c, text in enumerate(sh.head, start=1):
            cell = ws.cell(h, c, text)
            cell.font = Font(name="Calibri", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=NAVY)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = _box
        ws.row_dimensions[h].height = 30
        for i, row in enumerate(sh.body):
            for c in range(width):
                v = row[c] if c < len(row) else ""
                cell = ws.cell(h + 1 + i, c + 1, v)
                cell.border = _box
                cell.alignment = Alignment(horizontal="left" if c in sh.left else "center", vertical="center")
                cell.font = Font(name="Calibri", bold=v == "ABS", color=RED if v == "ABS" else "000000")
                if i % 2:
                    cell.fill = PatternFill("solid", fgColor=ZEBRA)
        f0 = h + len(sh.body) + 2
        for i, (k, v) in enumerate(sh.foot):
            r = f0 + i
            ws.cell(r, 1, k)
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
            for c in range(1, 4):
                ws.cell(r, c).fill = PatternFill("solid", fgColor=GREY)
                ws.cell(r, c).border = _box
            ws.cell(r, 1).font = Font(name="Calibri", bold=True)
            vc = ws.cell(r, 4, v)
            vc.font, vc.border, vc.alignment = Font(name="Calibri", bold=True), _box, Alignment(horizontal="center")
        for c in range(width):
            lens = [len(str(r[c])) for r in sh.body if c < len(r)]
            ws.column_dimensions[get_column_letter(c + 1)].width = min(40, max(6 if c == 0 else 9, min(16, len(str(sh.head[c])) + 2), *(l + 2 for l in lens)))
        ws.page_setup.orientation = "landscape" if width > 8 else "portrait"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_title_rows = f"{h}:{h}"
    path = Path(path)
    wb.save(path)
    return path


def write_csv(path: str | Path, sheet: Sheet) -> Path:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(sheet.rows())
    return path