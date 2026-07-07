"""rubric 单元测试。"""
from app.prompts.rubric import (
    DIMENSIONS,
    RUBRIC,
    calc_overall,
    validate_score,
)


def test_dimensions_present():
    assert set(DIMENSIONS) == {"correctness", "standardization", "readability"}


def test_weights_sum_to_one():
    s = sum(RUBRIC[d]["weight"] for d in DIMENSIONS)
    assert abs(s - 1.0) < 1e-9


def test_weight_equals_max_over_100():
    # 权重等同于 max_score / 100（即该维度占满分的比例）
    for d in DIMENSIONS:
        assert abs(RUBRIC[d]["weight"] - RUBRIC[d]["max_score"] / 100.0) < 1e-9


def test_max_scores_sum_to_100():
    total = sum(RUBRIC[d]["max_score"] for d in DIMENSIONS)
    assert total == 100


def test_validate_score_in_range():
    assert validate_score("correctness", 0) is True
    assert validate_score("correctness", 50) is True
    assert validate_score("correctness", 51) is False
    assert validate_score("standardization", 30) is True
    assert validate_score("standardization", 31) is False
    assert validate_score("readability", 20) is True
    assert validate_score("readability", 21) is False


def test_validate_score_invalid_dim():
    assert validate_score("nope", 10) is False


def test_calc_overall_full_marks():
    s = {d: RUBRIC[d]["max_score"] for d in DIMENSIONS}
    assert calc_overall(s) == 100.0


def test_calc_overall_zero():
    assert calc_overall({d: 0 for d in DIMENSIONS}) == 0.0


def test_calc_overall_weighted():
    # 50 + 30 + 20 = 100 维度；25+15+10=50
    s = {"correctness": 25, "standardization": 15, "readability": 10}
    assert calc_overall(s) == 50.0


def test_calc_overall_rejects_out_of_range():
    import pytest

    with pytest.raises(ValueError):
        calc_overall({"correctness": 51, "standardization": 15, "readability": 10})


def test_calc_overall_rejects_unknown_dim():
    import pytest

    with pytest.raises(KeyError):
        calc_overall({"correctness": 25, "no_such_dim": 10})
