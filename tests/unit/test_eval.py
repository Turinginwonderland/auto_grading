"""评测脚本单元测试：用临时 DB 跑评测，验证 gate 判定 + 报告生成。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "tests" / "eval"

# 让 tests.eval.run_eval 可正常 import
if str(EVAL_DIR.parent) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR.parent))

from tests.eval import run_eval as ev  # noqa: E402


@pytest.fixture()
def eval_db(tmp_path, monkeypatch):
    db_file = tmp_path / "eval.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("LLM_API_KEY", "")
    from app.core import config
    config.get_settings.cache_clear()
    return db_file


def test_run_eval_passes_gate(eval_db, monkeypatch):
    """端到端跑评测，验证 mock 下 gate PASS。"""
    # 把 report 写到临时目录
    out_json = eval_db.parent / "report.json"
    out_md = eval_db.parent / "report.md"
    monkeypatch.setattr(ev, "REPORT_JSON", out_json)
    monkeypatch.setattr(ev, "REPORT_MD", out_md)

    report = ev.run(runs=1, json_only=True)
    s = report["summary"]

    assert s["total"] == 20
    assert s["overall_pass_rate"] >= 0.80
    assert s["gate_pass"] is True
    assert len(report["samples"]) == 20
    for r in report["samples"]:
        assert "overall_pass" in r
        assert isinstance(r["actual_overall"], (int, float))

    # 报告文件确实写出来了
    assert out_json.exists()


def test_evaluate_one_returns_full_dimensions(eval_db):
    """单条样本评测返回 3 维度分。"""
    from app.db.database import SessionLocal

    sample = {
        "id": "test_x",
        "problem_id": "ds-test-x",
        "language": "python",
        "code": "def f():\n    return 1\n",
        "tag": "high",
        "expected_overall": [0, 100],
        "expected_correctness": [0, 50],
        "expected_standardization": [0, 30],
        "expected_readability": [0, 20],
    }

    db = SessionLocal()
    try:
        ev._setup_problems(db, {"ds-test-x"})
        ev._reset_submissions(db)
        result = ev.evaluate_one(db, sample)
    finally:
        db.close()

    assert result.sample_id == "test_x"
    assert result.overall_pass is True
    assert set(result.dimensions.keys()) == {"correctness", "standardization", "readability"}
    for dim, info in result.dimensions.items():
        assert "expected" in info
        assert "actual" in info
        assert "pass" in info
        assert "diff" in info


def test_aggregate_empty_results():
    """空列表不崩。"""
    s = ev.aggregate([])
    assert s["total"] == 0
    assert s["overall_pass_rate"] == 0.0


def test_in_range():
    """区间判定。"""
    assert ev._in_range(50.0, [0, 100]) is True
    assert ev._in_range(0, [0, 100]) is True
    assert ev._in_range(100, [0, 100]) is True
    assert ev._in_range(-1, [0, 100]) is False
    assert ev._in_range(101, [0, 100]) is False
    assert ev._in_range(50, [0, 1]) is False
    # 区间长度不对
    assert ev._in_range(50, [0]) is False
