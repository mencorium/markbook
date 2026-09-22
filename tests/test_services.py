# /markbook/tests/test_services.py
import datetime as dt

from backend import seed
from backend.services import assessments as A
from backend.services import comments, exports, imports, records as R, reports
from backend.services.analytics import Gradebook


def test_full_flow(tmp_path):
    seed.add_sample(seed=7)
    gb = Gradebook.load()
    cls = next(c for c in gb.classes.values() if c.name == seed.SAMPLE_CLASS)
    ranking = gb.ranking(cls.id)
    assert len(ranking) >= 12 and ranking[0].rank == 1
    top = ranking[0].student
    assert gb.summary(top).div is not None and gb.students[top.id].phone.startswith("+2557")

    exam = next(a for a in gb.assessments_for(cls.id) if a.is_paper)
    pa = gb.paper_analysis(exam)
    assert pa.sitters and pa.topics and all(q.marked for q in pa.questions)

    # exports + import round trip of a per-question sheet
    sheets = exports.single_sheets(gb, exam.id, "marks")
    assert [s.name for s in sheets][1:] == ["Topic analysis", "Question analysis", "Students by topic"]
    x = exports.write_xlsx(tmp_path / "exam.xlsx", sheets)
    p = imports.match_rows(imports.parse(imports.read_table(x), x.name), gb)
    assert p.kind == "marks" and len(p.qcols) == len(exam.questions) and p.choices
    res = imports.commit(p, gb)
    assert res["assessment_id"] == exam.id and res["added"] == 0

    exports.write_xlsx(tmp_path / "class.xlsx", exports.class_sheets(gb, cls.id, "grades"))
    exports.write_csv(tmp_path / "list.csv", exports.class_list_sheet(gb, cls.id))
    exports.write_xlsx(tmp_path / "progress.xlsx", exports.student_progress_sheets(gb, top.id))

    # comments + reports
    assert comments.fill_missing_comments(gb, cls.id) >= 12
    gb = Gradebook.load()
    assert gb.students[top.id].remarks
    reports.report_cards(gb, reports.class_order(gb, cls.id), tmp_path / "cards.pdf")
    reports.results_sheet(gb, cls.id, tmp_path / "results.pdf")
    reports.exam_analysis(gb, exam.id, tmp_path / "analysis.pdf")
    assert (tmp_path / "cards.pdf").stat().st_size > 20000


def test_paper_edit_and_moving_student():
    gb = Gradebook.load()
    cls = next(c for c in gb.classes.values() if c.name == seed.SAMPLE_CLASS)
    exam = next(a for a in gb.assessments_for(cls.id) if a.is_paper)
    secs = [{"key": s.id, "name": s.name, "pick": s.pick} for s in exam.sections]
    qs = [{"id": q.id, "label": q.label, "topic": q.topic, "max": q.max, "section_key": q.section_id} for q in exam.questions]
    qs.append({"id": None, "label": "Q8", "topic": "Recursion", "max": 5, "section_key": exam.sections[0].id})
    a = A.save_paper(exam.id, secs, qs)
    assert len(a.questions) == 8 and a.max_marks == exam.max_marks + 5 and "Recursion" in a.topics

    gb = Gradebook.load()                      # the paper total changed, so reload before measuring
    stu = gb.students_in(cls.id)[0]
    before = gb.summary(stu).overall
    R.save_student(stu.id, name=stu.name, class_name="Form Six", reg_no=stu.reg_no, phone="0755 111 222")
    gb2 = Gradebook.load()
    moved = gb2.students[stu.id]
    assert gb2.class_name(moved.class_id) == "Form Six" and moved.phone == "+255755111222"
    assert abs(gb2.summary(moved).overall - before) < 1e-6


def test_attendance_and_remove_sample():
    from backend.services import attendance as ATT
    gb = Gradebook.load()
    cls = next(c for c in gb.classes.values() if c.name == seed.SAMPLE_CLASS)
    ids = [s.id for s in gb.students_in(cls.id)]
    ATT.save_day(cls.id, dt.date.today(), ids, {ids[0]})
    day = ATT.get_day(cls.id, dt.date.today())
    assert day.absent == [ids[0]] and len(day.roster) == len(ids)
    seed.remove_sample()
    assert not any(c.name == seed.SAMPLE_CLASS for c in R.list_classes())


def test_archived_students_leave_results_but_keep_their_marks():
    seed.add_sample(seed=4)
    gb = Gradebook.load()
    cls = next(c for c in gb.classes.values() if c.name == seed.SAMPLE_CLASS)
    ids = [s.id for s in gb.students_in(cls.id)][:3]
    before_rank, before_marks = len(gb.ranking(cls.id)), sum(len(m) for m in gb.totals.values())

    assert R.archive_students(ids) == 3
    gb = Gradebook.load()
    assert len(gb.ranking(cls.id)) == before_rank - 3
    assert all(i not in gb.students for i in ids)
    assert sum(len(m) for m in gb.totals.values()) == before_marks        # nothing was deleted
    archived = R.list_students(archived=True)
    assert {s.id for s in archived} == set(ids) and all(s.archived_at for s in archived)
    assert R.archive_students(ids) == 0                                   # archiving twice changes nothing

    assert R.restore_students(ids) == 3
    gb = Gradebook.load()
    assert len(gb.ranking(cls.id)) == before_rank
    assert abs(sum(gb.summary(gb.students[i]).overall for i in ids)) > 0   # their results are back


def test_archived_subject_hides_its_assessments_only():
    gb = Gradebook.load()
    cls = next(c for c in gb.classes.values() if c.name == seed.SAMPLE_CLASS)
    subj = gb.class_subjects(cls.id)[0]
    others = len(gb.assessments_for(cls.id)) - len(gb.assessments_for(cls.id, subj.id))

    archived, hidden = R.archive_subjects([subj.id])
    assert (archived, hidden) == (1, 4)
    gb = Gradebook.load()
    assert subj.id not in gb.subjects and len(gb.assessments_for(cls.id)) == others
    assert not any(subj.id in gb.summary(s).subs for s in gb.students_in(cls.id))

    assert R.restore_subjects([subj.id]) == 1
    gb = Gradebook.load()
    assert subj.id in gb.subjects and len(gb.assessments_for(cls.id, subj.id)) == 4
    seed.remove_sample()


def test_delete_students_takes_their_marks_with_them():
    subj = R.save_subject(None, name="Deletion Test Subject", code="DEL")
    a, b = [R.save_student(None, name=n, class_name="Delete Test") for n in ("Temp One", "Temp Two")]
    ex = A.save_assessment(None, subject_id=subj.id, class_id=a.class_id, type="Test", name="T1", date=dt.date.today(), max_marks=20)
    A.save_totals(ex.id, {a.id: 15, b.id: 11})
    assert len(Gradebook.load().totals[ex.id]) == 2

    assert R.delete_students([a.id, b.id]) == 2
    gb = Gradebook.load()
    assert a.id not in gb.students and b.id not in gb.students
    assert not gb.totals.get(ex.id)                      # marks went with the students
    assert R.delete_students([a.id]) == 0                # deleting again is harmless


def test_delete_subjects_takes_their_assessments_with_them():
    keep = R.save_subject(None, name="Keeper Subject", code="KEEP")
    doomed = [R.save_subject(None, name=n, code=n[:4]) for n in ("Doomed One", "Doomed Two")]
    stu = R.save_student(None, name="Subject Test Student", class_name="Subject Delete Test")
    for subj in doomed + [keep]:
        a = A.save_assessment(None, subject_id=subj.id, class_id=stu.class_id, type="Test", name=f"{subj.code} T1",
                              date=dt.date.today(), max_marks=20)
        A.save_totals(a.id, {stu.id: 12})

    subjects, assessments = R.delete_subjects([d.id for d in doomed])
    assert (subjects, assessments) == (2, 2)
    gb = Gradebook.load()
    assert all(d.id not in gb.subjects for d in doomed)
    assert keep.id in gb.subjects and len(gb.assessments_for(subject_id=keep.id)) == 1
    assert not any(a.subject_id in {d.id for d in doomed} for a in gb.assessments)   # marks went with them
    assert R.delete_subjects([doomed[0].id]) == (0, 0)                               # deleting again is harmless


def test_create_class_with_its_own_grading():
    cls = R.get_or_create_class("Form Two North")
    R.save_class(cls.id, name="Form Two North", level="O", pass_mark=30, teacher="Mr. J. Mwaipopo")
    gb = Gradebook.load()
    saved = gb.classes[cls.id]
    assert (saved.name, saved.level, saved.teacher) == ("Form Two North", "O", "Mr. J. Mwaipopo")
    assert gb.scale(cls.id).best == 7                       # O-Level: division from the best 7 subjects
    assert R.get_or_create_class("form two north").id == cls.id      # same class, not a duplicate