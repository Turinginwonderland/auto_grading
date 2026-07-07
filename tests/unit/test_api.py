"""API 端到端测试：建题 → 评分 → 查结果 → 缓存命中。"""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # 用临时 sqlite
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("LLM_API_KEY", "")  # 强制 mock

    # 清缓存
    from app.core import config
    config.get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["llm_model"] == "mock-grader-v1"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["phase"] == "P1.0"


def test_create_and_get_problem(client):
    payload = {
        "problem_id": "ds-ch01-ex01",
        "title": "两数之和",
        "description": "给定数组与目标值，返回两个下标。",
        "difficulty": "easy",
        "reference_solution": "def two_sum(nums, t):\n    seen={}\n    for i,v in enumerate(nums):\n        if t-v in seen: return [seen[t-v],i]\n        seen[v]=i\n    return []",
    }
    r = client.post("/api/v1/problems", json=payload)
    assert r.status_code == 201, r.text
    r2 = client.get("/api/v1/problems/ds-ch01-ex01")
    assert r2.status_code == 200
    assert r2.json()["title"] == "两数之和"


def test_create_problem_duplicate_409(client):
    payload = {
        "problem_id": "ds-dup",
        "title": "x",
        "description": "x",
    }
    assert client.post("/api/v1/problems", json=payload).status_code == 201
    assert client.post("/api/v1/problems", json=payload).status_code == 409


def test_grade_unknown_problem_404(client):
    r = client.post(
        "/api/v1/grade",
        json={"problem_id": "nope", "code": "x=1\n", "language": "python"},
    )
    assert r.status_code == 404


def test_grade_empty_code_422(client):
    r = client.post(
        "/api/v1/grade",
        json={"problem_id": "ds-ch01-ex01", "code": "", "language": "python"},
    )
    assert r.status_code == 422


def test_grade_unsupported_language_422(client):
    r = client.post(
        "/api/v1/grade",
        json={"problem_id": "ds-ch01-ex01", "code": "x", "language": "brainfuck"},
    )
    assert r.status_code == 422


def test_full_grade_flow_and_cache(client):
    # 1. 建题
    client.post(
        "/api/v1/problems",
        json={
            "problem_id": "ds-flow-01",
            "title": "两数之和",
            "description": "返回两个下标。",
            "reference_solution": "def two_sum(nums, t):\n    seen={}\n    for i,v in enumerate(nums):\n        if t-v in seen: return [seen[t-v],i]\n        seen[v]=i\n    return []",
        },
    )

    code = (
        "from typing import List\n"
        "def two_sum(nums: List[int], target: int) -> List[int]:\n"
        "    seen = {}\n"
        "    for i, v in enumerate(nums):\n"
        "        if target - v in seen:\n"
        "            return [seen[target - v], i]\n"
        "        seen[v] = i\n"
        "    return []\n"
    )

    # 2. 评分
    r = client.post(
        "/api/v1/grade",
        json={"problem_id": "ds-flow-01", "code": code, "language": "python"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["cached"] is False
    assert 0 <= body["overall_score"] <= 100
    for dim in ("correctness", "standardization", "readability"):
        assert dim in body["dimensions"]
        assert "score" in body["dimensions"][dim]
        assert "weight" in body["dimensions"][dim]
        assert "max_score" in body["dimensions"][dim]
        assert "analysis" in body["dimensions"][dim]
    sid = body["submission_id"]

    # 3. 查询
    r2 = client.get(f"/api/v1/submissions/{sid}")
    assert r2.status_code == 200
    assert r2.json()["submission_id"] == sid

    # 4. 缓存命中：再评一次同样的代码
    r3 = client.post(
        "/api/v1/grade",
        json={"problem_id": "ds-flow-01", "code": code, "language": "python"},
    )
    assert r3.status_code == 200
    assert r3.json()["cached"] is True

    # 5. 列表
    r4 = client.get("/api/v1/submissions?problem_id=ds-flow-01")
    assert r4.status_code == 200
    assert len(r4.json()) >= 2
