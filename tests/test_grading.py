# /markbook_desktop/tests/test_grading.py
import pytest

from backend.grading import make_scale
from backend.paper import Q, Sec, paper_max, paper_total
from backend.phone import PhoneError, normalize_phone


def test_a_level_grades_and_division():
    sc = make_scale("A")
    assert sc.letter(80) == "A" and sc.letter(79.9) == "B" and sc.letter(34) == "F"
    d = sc.division([(85, False), (72, False), (61, False), (90, True)])   # 1 + 2 + 3, subsidiary ignored
    assert d.complete and d.points == 6 and d.div == "I"
    assert not sc.division([(85, False), (72, False)]).complete


def test_o_level_division_needs_seven():
    sc = make_scale("O")
    d = sc.division([(76, False)] * 7)
    assert d.points == 7 and d.div == "I"
    assert sc.remark("D") == "Pass"


def test_paper_best_of_choice_section():
    secs = [Sec("A"), Sec("B", "Section B", 2)]
    qs = [Q(1, "Q1", "x", 10, "A"), Q(2, "Q2", "y", 30, "B"), Q(3, "Q3", "y", 30, "B"), Q(4, "Q4", "z", 30, "B")]
    assert paper_max(secs, qs) == 70
    total, over = paper_total(secs, qs, {1: 8, 2: 20, 3: 25, 4: 10})
    assert total == 53 and over == ["Section B"]
    assert paper_total(secs, qs, {})[0] is None


@pytest.mark.parametrize("raw", ["0712 345 678", "712345678", "255712345678", "+255 712-345-678"])
def test_phone_normalised(raw):
    assert normalize_phone(raw, "255") == "+255712345678"


def test_phone_rejects_bad_tz_number():
    with pytest.raises(PhoneError):
        normalize_phone("0212345678", "255")