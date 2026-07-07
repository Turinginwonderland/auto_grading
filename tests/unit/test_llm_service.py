"""llm_service 单元测试（mock 模式，不依赖网络）。"""
import json

from app.core.config import get_settings
from app.services.llm_service import _mock_grade, _parse_and_validate, grade_code


def test_mock_grade_returns_valid_shape():
    s = get_settings()
    assert not s.use_real_llm  # 没配 key 应该是 mock

    out = _mock_grade(
        problem_title="两数之和",
        problem_description="返回两个下标使 nums[i]+nums[j]==target",
        language="python",
        code=(
            "from typing import List\n"
            "def two_sum(nums: List[int], target: int) -> List[int]:\n"
            "    seen = {}\n"
            "    for i, v in enumerate(nums):\n"
            "        if target - v in seen:\n"
            "            return [seen[target - v], i]\n"
            "        seen[v] = i\n"
            "    return []\n"
        ),
        reference_solution=None,
    )
    assert "correctness" in out
    assert "standardization" in out
    assert "readability" in out
    assert 0 <= out["correctness"]["score"] <= 50
    assert 0 <= out["standardization"]["score"] <= 30
    assert 0 <= out["readability"]["score"] <= 20
    assert 0.0 <= out["_overall_score"] <= 100.0


def test_parse_and_validate_accepts_valid_json():
    obj = {
        "thought_summary": "ok",
        "correctness": {"score": 40, "analysis": "good"},
        "standardization": {"score": 22, "analysis": "ok"},
        "readability": {"score": 16, "analysis": "ok"},
        "overall_comment": "fine",
    }
    parsed = _parse_and_validate(json.dumps(obj))
    assert parsed["_overall_score"] > 0


def test_parse_and_validate_strips_json_fence():
    text = "```json\n" + json.dumps(
        {
            "thought_summary": "ok",
            "correctness": {"score": 40, "analysis": "good"},
            "standardization": {"score": 22, "analysis": "ok"},
            "readability": {"score": 16, "analysis": "ok"},
            "overall_comment": "fine",
        },
        ensure_ascii=False,
    ) + "\n```"
    parsed = _parse_and_validate(text)
    assert parsed["correctness"]["score"] == 40


def test_parse_and_validate_rejects_out_of_range():
    bad = json.dumps(
        {
            "thought_summary": "ok",
            "correctness": {"score": 99, "analysis": "bad"},
            "standardization": {"score": 22, "analysis": "ok"},
            "readability": {"score": 16, "analysis": "ok"},
            "overall_comment": "fine",
        }
    )
    import pytest

    with pytest.raises(ValueError):
        _parse_and_validate(bad)


def test_parse_and_validate_rejects_missing_dim():
    bad = json.dumps(
        {
            "thought_summary": "ok",
            "correctness": {"score": 40, "analysis": "good"},
            "readability": {"score": 16, "analysis": "ok"},
            "overall_comment": "fine",
        }
    )
    import pytest

    with pytest.raises(ValueError):
        _parse_and_validate(bad)


def test_grade_code_entry_uses_mock():
    r = grade_code(
        problem_title="t",
        problem_description="d",
        language="python",
        code="def f(): return 1\n",
        reference_solution=None,
    )
    assert r.model == "mock-grader-v1"
    assert 0 <= r.parsed["_overall_score"] <= 100
