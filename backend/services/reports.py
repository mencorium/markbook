# /markbook/backend/services/reports.py
"""PDF documents: student report cards (one or a whole class), class result sheet, exam analysis."""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, HRFlowable, Image, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from ..grading import DIVISIONS
from . import charts
from .analytics import Gradebook, difficulty, discrimination_label

NAVY = colors.HexColor("#16263D")
LINE = colors.HexColor("#C8D0DA")
SOFT = colors.HexColor("#EEF2F6")
BAND = colors.HexColor("#DCE3EB")
RED = colors.HexColor("#C8322B")
SLATE = colors.HexColor("#56657A")

ss = getSampleStyleSheet()
P = ParagraphStyle("p", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)
SMALL = ParagraphStyle("s", parent=P, fontSize=7.5, leading=10, textColor=colors.HexColor("#666666"))
H2 = ParagraphStyle("h2", parent=P, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4, textColor=NAVY)
TITLE = ParagraphStyle("t", parent=P, fontName="Helvetica-Bold", fontSize=16, leading=20, alignment=TA_CENTER, textColor=NAVY)
SUB = ParagraphStyle("st", parent=P, fontName="Helvetica-Bold", fontSize=12, leading=15, alignment=TA_CENTER, textColor=NAVY)
CENTER = ParagraphStyle("c", parent=P, alignment=TA_CENTER, textColor=colors.HexColor("#555555"))


def f1(v) -> str:
    return "–" if v is None else f"{v:.1f}".rstrip("0").rstrip(".")


def grid(data, widths=None, head=True, foot=False, zebra=True, align_left=(0,), extra=()):
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.5, LINE), ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
          ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    for c in align_left:
        st.append(("ALIGN", (c, 0), (c, -1), "LEFT"))
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5)]
    if zebra:
        for r in range(1 if head else 0, len(data) - (1 if foot else 0)):
            if r % 2 == 0:
                st.append(("BACKGROUND", (0, r), (-1, r), SOFT))
    if foot:
        st += [("BACKGROUND", (0, -1), (-1, -1), BAND), ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5)]
    t.setStyle(TableStyle(st + list(extra)))
    return t


class _Label(Flowable):
    """Invisible marker that tells the page footer whose report this page belongs to."""
    def __init__(self, text):
        super().__init__()
        self.text = text
        self.width = self.height = 0

    def draw(self):
        self.canv._report_label = self.text


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#777777"))
    label = getattr(canvas, "_report_label", "")
    w, _ = doc.pagesize
    canvas.drawString(15 * mm, 10 * mm, f"{label}  —  generated {dt.date.today().isoformat()}".strip(" —"))
    canvas.drawRightString(w - 15 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


class _Doc(BaseDocTemplate):
    """Footer is drawn at the END of each page, after the page's _Label marker has run."""
    def __init__(self, path, pagesize=A4):
        super().__init__(str(path), pagesize=pagesize, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=18 * mm,
                         title="Markbook report", author="Markbook")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        self.addPageTemplates([PageTemplate(id="page", frames=[frame], onPageEnd=_footer)])


def _doc(path, pagesize=A4):
    return _Doc(path, pagesize)


def _header(gb: Gradebook, title: str, sub: str) -> list:
    school = (gb.settings.get("school") or "School").upper()
    return [Paragraph(school, TITLE), Paragraph(title, SUB), Paragraph(sub, CENTER), Spacer(1, 3),
            HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=8)]


# ---------------- report cards ----------------
def _report_story(gb: Gradebook, student_id: int, history: bool, width: float) -> list:
    stu = gb.students[student_id]
    sm, sc = gb.summary(stu), gb.scale(stu.class_id)
    rank, n = gb.position(stu)
    total, k = gb.total_marks(stu)
    cls = gb.classes.get(stu.class_id)
    term = gb.term.label if gb.term else (gb.settings.get("term") or "")
    story: list = [_Label(stu.name)] + _header(gb, "STUDENT PROGRESS REPORT", "  —  ".join(x for x in [gb.class_name(stu.class_id), term] if x))
    pos = f"{rank} out of {n}" if rank else "–"
    avg_txt = "–" if sm.overall is None else f"{sm.overall:.1f}%  (grade {sc.letter(sm.overall)})"
    div_txt = (f"{sm.div.div}  ({sm.div.points} points)" if sm.div.complete else sm.div.text()) if sm.div else None
    att_txt = "–" if sm.att is None else f"{round(sm.att)}%"
    info = [["Name", stu.name, "Reg. No.", stu.reg_no or "–"],
            ["Class", gb.class_name(stu.class_id), "Students in class", str(len(gb.students_in(stu.class_id)))],
            ["Total marks", f"{total:.1f} out of {k * 100}" if k else "–", "Position in class", pos],
            ["Average", avg_txt, "Division" if sc.div else "Attendance", div_txt or att_txt if sc.div else att_txt]]
    if sc.div:
        info.append(["Attendance", att_txt, "Grading", sc.label])
    half = (width - 62 * mm) / 2
    it = Table(info, colWidths=[28 * mm, half, 34 * mm, half])
    it.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                            ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9), ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9),
                            ("BACKGROUND", (0, 0), (0, -1), SOFT), ("BACKGROUND", (2, 0), (2, -1), SOFT),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [it, Spacer(1, 8)]
    w = gb.settings.get("ca_weight", 40)
    head = ["Subject", f"Tests ({w}%)", f"Exam ({100 - int(w)}%)", "Total %", "Grade", *(["Points"] if sc.div else []), "Position", "Remark"]
    rows, fails = [head], []
    subs = sorted(sm.subs.items(), key=lambda x: gb.subject_name(x[0]))
    for i, (sid, r) in enumerate(subs, start=1):
        g = sc.letter(r.final)
        p, of = gb.subject_positions(stu.class_id, sid)
        if not sc.passing(r.final):
            fails.append(i)
        rows.append([gb.subject_name(sid) + (" (sub.)" if gb.subjects[sid].subsidiary else ""), f1(r.ca), f1(r.ex),
                     f1(r.final) + (" *" if r.provisional else ""), g, *([str(sc.points(r.final))] if sc.div else []), f"{p.get(stu.id, '–')} / {of}", sc.remark(g)])
    rows.append(["Total / Average", "", "", f"{total:.1f} / {f1(sm.overall)}%" if k else "–", sc.letter(sm.overall),
                 *([str(sm.div.points) if sm.div and sm.div.complete else "–"] if sc.div else []), pos, sc.remark(sc.letter(sm.overall)) if sm.overall is not None else ""])
    rest = (width - 46 * mm) / (len(head) - 1)
    story.append(grid(rows, [46 * mm] + [rest] * (len(head) - 1), foot=True, extra=[("TEXTCOLOR", (4, r), (4, r), RED) for r in fails]))
    notes = []
    if any(r.provisional for _, r in subs):
        notes.append("* No exam sat yet — total based on tests only.")
    if sc.div:
        notes.append(f"Division from {sc.best_note}" + ("; subsidiary (sub.) subjects are not counted." if sc.level == "A" else "."))
    if notes:
        story.append(Paragraph("   ".join(notes), SMALL))
    png = charts.figure_png(lambda ax: charts.progress(ax, gb, stu.id, attendance=False), 7.4, 2.5)
    if png:
        story += [Paragraph("Progress through the term", H2), Image(io.BytesIO(png), width=width, height=width * 2.5 / 7.4)]
    weak = [t for t in gb.student_topics(stu) if not sc.passing(t.mean) or t.mean < 60][:4]
    if weak:
        story += [Paragraph("Areas to improve", H2), Paragraph("  •  ".join(f"{t.topic} ({gb.subject_short(t.subject_id)}, {round(t.mean)}%)" for t in weak), P)]

    def comment(title, text, name):
        box = Table([[Paragraph(text or "&nbsp;", P)]], colWidths=[width], rowHeights=[None if text else 16 * mm])
        box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#AAB4C0")), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
        sig = Table([[f"Name: {name or '______________________'}", "Signature: ____________________"]], colWidths=[width / 2, width / 2])
        sig.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return KeepTogether([Paragraph(title, H2), box, Spacer(1, 4), sig])
    story += [comment("Class teacher's comments", stu.remarks, cls.teacher if cls else ""),
              comment("Head teacher's comments", "", gb.settings.get("head_teacher", ""))]
    nt = gb.settings.get("next_term") or ""
    try:
        nt = dt.date.fromisoformat(nt).strftime("%d %B %Y") if nt else ""
    except ValueError:
        pass
    last = Table([[f"Next term begins: {nt or '____________________'}", "Parent's signature: ____________________"]], colWidths=[width / 2, width / 2])
    last.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 10)]))
    story.append(last)
    if history and subs:
        story += [PageBreak(), Paragraph(f"Progress per subject — {stu.name}", ParagraphStyle("h", parent=H2, fontSize=13))]
        for sid, r in subs:
            data = [["Date", "Assessment", "Type", "Marks", "%", "Grade", "Class average"]]
            for a in gb.student_assessments(stu, sid):
                p = gb.pct(a, stu.id)
                data.append([a.date.isoformat(), a.name, a.type, f"{f1(gb.score(a, stu.id))} / {a.max_marks:g}" if p is not None else "Absent",
                             f1(p), sc.letter(p) if p is not None else "–", f"{f1(gb.assess_stats(a).mean)}%"])
            story.append(KeepTogether([Paragraph(f"{gb.subject_name(sid)} — total {f1(r.final)}% ({sc.letter(r.final)})", ParagraphStyle("h3", parent=P, fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=3)),
                                       grid(data, [24 * mm, width - 128 * mm, 22 * mm, 24 * mm, 16 * mm, 16 * mm, 26 * mm], align_left=(1,))]))
    return story


def report_cards(gb: Gradebook, student_ids: list[int], path: str | Path, history: bool = True) -> Path:
    """One or many report cards in a single PDF (whole class: pass ids in position order)."""
    doc = _doc(path)
    story: list = []
    for i, sid in enumerate(student_ids):
        if i:
            story.append(PageBreak())
        story += _report_story(gb, sid, history, doc.width)
    doc.build(story)
    return Path(path)


def class_order(gb: Gradebook, class_id: int) -> list[int]:
    ranked = [r.student.id for r in gb.ranking(class_id)]
    return ranked + [s.id for s in gb.students_in(class_id) if s.id not in ranked and gb.summary(s).overall is not None]


# ---------------- annual (end of year) ----------------
def annual_report_cards(book, whole_year: Gradebook, student_ids: list[int], path: str | Path) -> Path:
    """One card per student for the whole year: every term's mark side by side, then the year mark."""
    doc = _doc(path)
    story: list = []
    for i, sid in enumerate(student_ids):
        if i:
            story.append(PageBreak())
        story += _annual_story(book, whole_year, sid, doc.width)
    doc.build(story)
    return Path(path)


def _annual_story(book, whole_year: Gradebook, student_id: int, width: float) -> list:
    row = book.row_for(student_id)
    stu, sc = row.student, book.scale
    gb = book.any
    story: list = [_Label(stu.name)] + _header(gb, "ANNUAL PROGRESS REPORT", f"{book.class_name}  —  {book.year}")
    of = len(book.ranked)
    info = [["Name", stu.name, "Reg. No.", stu.reg_no or "–"],
            ["Class", book.class_name, "Students in class", str(len(book.rows))],
            ["Year average", "–" if row.overall is None else f"{row.overall:.1f}%  (grade {sc.letter(row.overall)})",
             "Position in class", f"{row.rank} out of {of}" if row.rank else "–"],
            ["Terms sat", f"{row.terms_sat} of {len(book.terms)}",
             "Division" if sc.div else "Attendance",
             (row.div.text() if row.div else "–") if sc.div else ("–" if row.att is None else f"{round(row.att)}%")]]
    if sc.div:
        info.append(["Attendance", "–" if row.att is None else f"{round(row.att)}%", "Grading", sc.label])
    half = (width - 62 * mm) / 2
    it = Table(info, colWidths=[28 * mm, half, 34 * mm, half])
    it.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                            ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9), ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9),
                            ("BACKGROUND", (0, 0), (0, -1), SOFT), ("BACKGROUND", (2, 0), (2, -1), SOFT),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [it, Spacer(1, 8)]
    head = ["Subject", *[f"{t.name} %" for t in book.terms], "Year %", "Grade", *(["Points"] if sc.div else []), "Position", "Remark"]
    rows, fails = [head], []
    for i, sub in enumerate(book.subjects(), start=1):
        got = row.subjects.get(sub.id)
        if not got:
            continue
        pos, of_sub = book.positions(sub.id)
        g = sc.letter(got.final)
        if not sc.passing(got.final):
            fails.append(len(rows))
        rows.append([sub.name + (" (sub.)" if sub.subsidiary else ""),
                     *[f1(got.per_term.get(t.id)) for t in book.terms], f1(got.final), g,
                     *([str(sc.points(got.final))] if sc.div else []), f"{pos.get(stu.id, '–')} / {of_sub}", sc.remark(g)])
    rows.append(["Total / Average", *[""] * len(book.terms), f"{row.total:.1f} / {f1(row.overall)}%", sc.letter(row.overall),
                 *([str(row.div.points) if row.div and row.div.complete else "–"] if sc.div else []),
                 f"{row.rank} / {of}" if row.rank else "–", sc.remark(sc.letter(row.overall)) if row.overall is not None else ""])
    rest = (width - 46 * mm) / (len(head) - 1)
    story.append(grid(rows, [46 * mm] + [rest] * (len(head) - 1), foot=True, extra=[("TEXTCOLOR", (len(book.terms) + 2, r), (len(book.terms) + 2, r), RED) for r in fails]))
    notes = [book.weights_note()]
    if sc.div:
        notes.append(f"Division from {sc.best_note}" + ("; subsidiary (sub.) subjects are not counted." if sc.level == "A" else "."))
    story.append(Paragraph("   ".join(notes), SMALL))
    png = charts.figure_png(lambda ax: charts.progress(ax, whole_year, stu.id, attendance=False), 7.4, 2.5)
    if png:
        story += [Paragraph("Progress through the year", H2), Image(io.BytesIO(png), width=width, height=width * 2.5 / 7.4)]
    cls = gb.classes.get(stu.class_id)

    def comment(title, text, name):
        box = Table([[Paragraph(text or "&nbsp;", P)]], colWidths=[width], rowHeights=[None if text else 16 * mm])
        box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#AAB4C0")), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
        sig = Table([[f"Name: {name or '______________________'}", "Signature: ____________________"]], colWidths=[width / 2, width / 2])
        sig.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return KeepTogether([Paragraph(title, H2), box, Spacer(1, 4), sig])
    story += [comment("Class teacher's comments", stu.remarks, cls.teacher if cls else ""),
              comment("Head teacher's comments", "", gb.settings.get("head_teacher", ""))]
    last = Table([["Promoted to: ____________________", "Parent's signature: ____________________"]], colWidths=[width / 2, width / 2])
    last.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 10)]))
    story.append(last)
    return story


def annual_results_sheet(book, path: str | Path) -> Path:
    """The whole class for the year: one row per student, one column per subject."""
    doc = _doc(path, landscape(A4))
    sc, subs = book.scale, book.subjects()
    gb = book.any
    story: list = [_Label(book.class_name)] + _header(gb, "ANNUAL RESULTS", f"{book.class_name}  —  {book.year}  —  {sc.label}")
    if sc.div:
        cnt = [sum(1 for r in book.ranked if r.div and r.div.complete and r.div.div == d) for d in DIVISIONS]
        inc = sum(1 for r in book.ranked if not (r.div and r.div.complete))
        story += [grid([[f"Division {d}" for d in DIVISIONS] + ["Incomplete", "Total"], cnt + [inc, len(book.ranked)]], zebra=False, align_left=()),
                  Spacer(1, 10)]
    head = ["Pos", "Reg. No.", "Student Name", *[x.short for x in subs], *(["Points", "Div"] if sc.div else []), "Total", "Year %"]
    data = [head] + [[r.rank, r.student.reg_no or "", r.student.name,
                      *[sc.letter(r.subjects[x.id].final) if x.id in r.subjects else "–" for x in subs],
                      *([r.div.points, r.div.div] if sc.div and r.div and r.div.complete else ["–", "–"] if sc.div else []),
                      f"{r.total:.1f}", f1(r.overall)] for r in book.ranked]
    story += [grid(data, [12 * mm, 26 * mm, 52 * mm] + [(doc.width - 90 * mm) / (len(head) - 3)] * (len(head) - 3), align_left=(1, 2)),
              Spacer(1, 10), Paragraph(book.weights_note(), SMALL), Spacer(1, 8)]
    perf = [["Subject", *[f"{t.name} avg %" for t in book.terms], "Year avg %", "Pass rate"]]
    for x in subs:
        finals = [r.subjects[x.id].final for r in book.ranked if x.id in r.subjects]
        per_term = []
        for t in book.terms:
            vals = [r.subjects[x.id].per_term[t.id] for r in book.ranked if x.id in r.subjects and t.id in r.subjects[x.id].per_term]
            per_term.append(f1(sum(vals) / len(vals)) if vals else "–")
        perf.append([x.name, *per_term, f1(sum(finals) / len(finals)) if finals else "–",
                     f"{round(sum(1 for f in finals if sc.passing(f)) / len(finals) * 100)}%" if finals else "–"])
    story.append(KeepTogether([Paragraph("Subject performance", H2),
                               grid(perf, [60 * mm] + [(doc.width - 60 * mm) / (len(perf[0]) - 1)] * (len(perf[0]) - 1))]))
    doc.build(story)
    return Path(path)


def annual_order(book) -> list[int]:
    return [r.student.id for r in book.ranked]


# ---------------- class result sheet ----------------
def results_sheet(gb: Gradebook, class_id: int, path: str | Path) -> Path:
    doc = _doc(path, landscape(A4))
    sc, rank, subs = gb.scale(class_id), gb.ranking(class_id), gb.class_subjects(class_id)
    story: list = [_Label(gb.class_name(class_id))] + _header(gb, "CLASS RESULTS", "  —  ".join(x for x in [gb.class_name(class_id), gb.term.label if gb.term else "", sc.label] if x))
    if sc.div:
        cnt = [sum(1 for r in rank if r.summary.div and r.summary.div.complete and r.summary.div.div == d) for d in DIVISIONS]
        inc = sum(1 for r in rank if not (r.summary.div and r.summary.div.complete))
        story += [grid([[f"Division {d}" for d in DIVISIONS] + ["Incomplete", "Total"], cnt + [inc, len(rank)]], zebra=False, align_left=()), Spacer(1, 10)]
    head = ["Pos", "Reg. No.", "Student Name", *[x.short for x in subs], *(["Points", "Div"] if sc.div else []), "Total", "Avg %"]
    data = [head] + [[r.rank, r.student.reg_no or "", r.student.name,
                      *[sc.letter(r.summary.subs[x.id].final) if x.id in r.summary.subs else "–" for x in subs],
                      *([r.summary.div.points, r.summary.div.div] if sc.div and r.summary.div and r.summary.div.complete else ["–", "–"] if sc.div else []),
                      f"{gb.total_marks(r.student)[0]:.1f}", f1(r.summary.overall)] for r in rank]
    story += [grid(data, [12 * mm, 26 * mm, 52 * mm] + [(doc.width - 90 * mm) / (len(head) - 3)] * (len(head) - 3), align_left=(1, 2)), Spacer(1, 12)]
    perf = [["Subject", *sc.grades, "Average %", "Pass rate"]]
    for x in subs:
        fs = [r.summary.subs[x.id].final for r in rank if x.id in r.summary.subs]
        perf.append([x.name, *[sum(1 for f in fs if sc.letter(f) == g) for g in sc.grades], f1(sum(fs) / len(fs)) if fs else "–",
                     f"{round(sum(1 for f in fs if sc.passing(f)) / len(fs) * 100)}%" if fs else "–"])
    story.append(KeepTogether([Paragraph("Subject performance", H2),
                               grid(perf, [60 * mm] + [(doc.width - 60 * mm) / (len(perf[0]) - 1)] * (len(perf[0]) - 1))]))
    doc.build(story)
    return Path(path)


# ---------------- exam analysis ----------------
def exam_analysis(gb: Gradebook, assessment_id: int, path: str | Path) -> Path:
    a = gb.by_id[assessment_id]
    pa, st = gb.paper_analysis(a), gb.assess_stats(a)
    doc = _doc(path)
    story: list = [_Label(a.name)] + _header(gb, "EXAM ANALYSIS", f"{gb.subject_name(a.subject_id)} — {a.name} ({a.type}) — {gb.class_name(a.class_id)} — {a.date.isoformat()}")
    story += [grid([["Sat", "Mean %", "Highest %", "Lowest %", "Pass rate", "Out of"],
                    [len(pa.sitters), f1(st.mean), f1(st.hi), f1(st.lo), f"{round(st.pass_rate)}%" if st.pass_rate is not None else "–", f"{a.max_marks:g}"]], zebra=False, align_left=())]
    names = lambda xs: ", ".join(gb.students[i].name for i, _ in xs if i in gb.students) or "none"
    story += [Paragraph("Topics, hardest first", H2),
              grid([["Topic", "Questions", "Answered", "Average %", "Difficulty", "Students below pass"]] +
                   [[t.topic, ", ".join(t.questions), f"{t.attempted}/{len(pa.sitters)}", f1(t.facility), difficulty(t.facility), Paragraph(names(t.struggling), SMALL)] for t in pa.topics],
                   [34 * mm, 26 * mm, 20 * mm, 20 * mm, 20 * mm, doc.width - 120 * mm], align_left=(0, 1, 5))]
    png = charts.figure_png(lambda ax: charts.bars(ax, [t.topic for t in pa.topics], [t.facility for t in pa.topics], horizontal=True,
                                                   second=("Students who answered %", [t.att_rate for t in pa.topics])) if pa.topics else False, 7.2, max(1.8, 0.45 * len(pa.topics) + 0.8))
    if png:
        story.append(Image(io.BytesIO(png), width=doc.width, height=doc.width * max(1.8, 0.45 * len(pa.topics) + 0.8) / 7.2))
    story += [Paragraph("Questions", H2),
              grid([["Question", "Topic", "Marks", "Answered %", "Average %", "Difficulty", "Discrimination"]] +
                   [[q.q.label + (" (choice)" if q.choice else ""), q.q.topic or "–", f"{q.q.max:g}", f1(q.att_rate), f1(q.facility), difficulty(q.facility),
                     "–" if q.disc is None else f"{q.disc:.2f} {discrimination_label(q.disc)}"] for q in pa.questions], align_left=(0, 1)),
              Spacer(1, 6),
              Paragraph("Average: mean score as a percentage (skipped compulsory questions count as 0). Difficulty: Easy 70%+, Moderate 40–69%, Hard below 40%. "
                        "Discrimination compares the top and bottom 27% of students; below 0.2 suggests the question did not separate strong from weak students.", SMALL)]
    doc.build(story)
    return Path(path)