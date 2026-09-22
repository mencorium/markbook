# /markbook_desktop/backend/services/charts.py
"""Chart drawing shared by the desktop screens and the PDF reports (matplotlib Axes in, nothing out)."""
from __future__ import annotations

import io

from .analytics import Gradebook

PALETTE = ["#2458A6", "#C8322B", "#2E7D4F", "#A8691A", "#7A4FB5", "#1D8A99", "#B5487A", "#5B6B2E", "#D0701F", "#3C5A8C"]
RED, AMBER, GREEN, INK, MUTED, ATT = "#C8322B", "#A8691A", "#2E7D4F", "#16263D", "#56657A", "#C9D6E6"


def subject_color(gb: Gradebook, subject_id: int) -> str:
    ids = sorted(gb.subjects, key=lambda i: gb.subjects[i].name.lower())
    return PALETTE[ids.index(subject_id) % len(PALETTE)] if subject_id in ids else PALETTE[0]


def style(ax, pct_axis: str | None = "y") -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#B8C2CF")
    ax.spines["bottom"].set_color("#B8C2CF")
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y" if pct_axis != "x" else "x", color="#E5E9EE", linewidth=0.8)
    ax.set_axisbelow(True)
    if pct_axis == "y":
        ax.set_ylim(0, 100)
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    elif pct_axis == "x":
        ax.set_xlim(0, 100)
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")


def progress(ax, gb: Gradebook, student_id: int, subject_id: int | None = None, attendance: bool = True) -> bool:
    """Line per subject across assessments; tests sharing a name and date share an x point. Returns False if no data."""
    stu = gb.students[student_id]
    as_ = [a for a in gb.student_assessments(stu, subject_id) if gb.has_score(a, stu.id)]
    if not as_:
        return False
    keys = list(dict.fromkeys((a.date, a.name.lower()) for a in as_))
    first = {k: next(a for a in as_ if (a.date, a.name.lower()) == k) for k in keys}
    xs = range(len(keys))
    if attendance:
        att = [gb.att_rate(stu, first[keys[i - 1]].date if i else None, first[k].date) for i, k in enumerate(keys)]
        if any(v is not None for v in att):
            ax2 = ax.twinx()
            ax2.bar(xs, [v or 0 for v in att], color=ATT, width=0.5, zorder=0, label="Attendance")
            ax2.set_ylim(0, 100)
            ax2.tick_params(colors=MUTED, labelsize=7)
            ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
            for side in ("top",):
                ax2.spines[side].set_visible(False)
            ax.set_zorder(ax2.get_zorder() + 1)
            ax.patch.set_visible(False)
    for sid in dict.fromkeys(a.subject_id for a in as_):
        ys = [None] * len(keys)
        for a in as_:
            if a.subject_id == sid:
                ys[keys.index((a.date, a.name.lower()))] = gb.pct(a, stu.id)
        pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", markersize=4, linewidth=2, color=subject_color(gb, sid), label=gb.subject_name(sid))
    if subject_id:
        means = [gb.assess_stats(first[k]).mean for k in keys]
        ax.plot(list(xs), means, linestyle="--", color=MUTED, linewidth=1.2, label="Class mean")
    ax.axhline(gb.scale(stu.class_id).pass_mark, color=RED, linestyle=":", linewidth=1.2, label="Pass mark")
    style(ax)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{first[k].name}\n{first[k].date:%d %b}" for k in keys], fontsize=7)
    ax.legend(fontsize=7, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.42), ncol=5)
    return True


def bars(ax, labels: list[str], values: list[float | None], colors=None, horizontal=False, pass_mark: float | None = None, second=None) -> None:
    vals = [v or 0 for v in values]
    cols = colors or [(RED if v < 40 else AMBER if v < 70 else GREEN) for v in vals]
    pos = range(len(labels))
    if horizontal:
        if second:
            ax.barh([p + 0.2 for p in pos], [v or 0 for v in second[1]], height=0.38, color=ATT, label=second[0])
            ax.barh([p - 0.2 for p in pos], vals, height=0.38, color=cols, label="Average score")
            ax.legend(fontsize=7, frameon=False)
        else:
            ax.barh(list(pos), vals, color=cols)
        ax.set_yticks(list(pos))
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        style(ax, "x")
    else:
        ax.bar(list(pos), vals, color=cols)
        ax.set_xticks(list(pos))
        ax.set_xticklabels(labels, fontsize=8)
        style(ax, "y")
    if pass_mark is not None:
        (ax.axvline if horizontal else ax.axhline)(pass_mark, color=RED, linestyle=":", linewidth=1)


def counts(ax, labels: list[str], values: list[int], colors: list[str]) -> None:
    ax.bar(range(len(labels)), values, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    style(ax, None)
    ax.yaxis.get_major_locator().set_params(integer=True)


def figure_png(draw, width_in=7.2, height_in=2.6, dpi=160) -> bytes | None:
    """Render a drawing function to PNG bytes for PDFs. draw(ax) returns False to skip."""
    from matplotlib.figure import Figure
    fig = Figure(figsize=(width_in, height_in), dpi=dpi)
    ax = fig.add_subplot(111)
    if draw(ax) is False:
        return None
    fig.subplots_adjust(left=0.07, right=0.94, top=0.95, bottom=0.34)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    return buf.getvalue()