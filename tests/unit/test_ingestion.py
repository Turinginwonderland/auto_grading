"""ingestion 子包测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 把项目根加入 sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.backends import get_backend  # noqa: E402
from ingestion.human_review import apply_reviewed, export_review_csv, sample_for_review  # noqa: E402
from ingestion.llm_structurer import (  # noqa: E402
    _match_problem_start,
    split_into_problem_blocks,
    structure_mock,
)


# ---------- backends ----------

def test_mock_backend_returns_text():
    b = get_backend("mock")
    txt = b.recognize("ingestion/cache/pages/page_0005.png")
    assert isinstance(txt, str)
    assert len(txt) > 0


def test_get_backend_invalid():
    with pytest.raises(ValueError):
        get_backend("no_such_backend")


# ---------- structurer 规则 ----------

def test_match_problem_start():
    assert _match_problem_start("1.2  题目") == "1.2"
    assert _match_problem_start("习题 2-3") == "2.3"
    assert _match_problem_start("例 1.1 链表反转") == "1.1"
    assert _match_problem_start("hello world") is None
    assert _match_problem_start("") is None


def test_split_blocks_basic():
    pages = [
        {"page_no": 1, "chapter": "第1章", "text": "前言部分\n"},
        {"page_no": 2, "chapter": "第1章", "text": "1.1 题目 A\n描述 A\n1.2 题目 B\n描述 B\n"},
        {"page_no": 3, "chapter": "第1章", "text": "1.3 题目 C\n描述 C\n"},
    ]
    blocks = split_into_problem_blocks(pages)
    assert len(blocks) == 3
    assert blocks[0]["problem_no"] == "1.1"
    assert blocks[2]["end_page"] == 3


def test_structure_mock():
    pages = [
        {"page_no": 1, "chapter": "线性表", "text": "1.1 反转链表\n1.2 合并链表\n"},
        {"page_no": 2, "chapter": "线性表", "text": "1.3 删除节点\n"},
    ]
    blocks = split_into_problem_blocks(pages)
    probs = structure_mock(blocks)
    assert len(probs) == 3
    for p in probs:
        assert p["problem_id"].startswith("ds-")
        assert p["source_chapter"] == "线性表"
        assert p["source_page"] in (1, 2)


# ---------- human_review ----------

def test_sample_for_review():
    probs = [{"problem_id": f"p-{i}", "title": str(i)} for i in range(20)]
    s = sample_for_review(probs, ratio=0.1)
    assert len(s) == 2  # 20 * 0.1 = 2


def test_sample_for_review_deterministic():
    probs = [{"problem_id": f"p-{i}", "title": str(i)} for i in range(20)]
    a = sample_for_review(probs, ratio=0.2, seed=7)
    b = sample_for_review(probs, ratio=0.2, seed=7)
    assert [p["problem_id"] for p in a] == [p["problem_id"] for p in b]


def test_export_and_apply_review(tmp_path):
    probs = [
        {"problem_id": "p1", "title": "A"},
        {"problem_id": "p2", "title": "B"},
        {"problem_id": "p3", "title": "C"},
    ]
    csv = tmp_path / "review.csv"
    rows = export_review_csv(probs, csv_path=csv, ratio=1.0, append=False)
    assert len(rows) == 3
    # 默认 pending → 全保留
    kept, edited, rejected = apply_reviewed(probs, csv_path=csv)
    assert len(kept) == 3
    assert edited == [] and rejected == []

    # 手工改 CSV（用 csv 模块保证转义正确）
    import csv as _csv
    with csv.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(
            f, fieldnames=["problem_id", "title", "status", "editor", "note", "edited_json"]
        )
        w.writeheader()
        w.writerow({"problem_id": "p1", "title": "A", "status": "rejected", "editor": "me", "note": "", "edited_json": ""})
        w.writerow({
            "problem_id": "p2", "title": "B", "status": "edited", "editor": "me", "note": "ok",
            "edited_json": '{"problem_id": "p2", "title": "B-new"}',
        })
        w.writerow({"problem_id": "p3", "title": "C", "status": "pending", "editor": "", "note": "", "edited_json": ""})

    kept, edited, rejected = apply_reviewed(probs, csv_path=csv)
    assert len(kept) == 1
    assert kept[0]["problem_id"] == "p3"
    assert len(edited) == 1 and edited[0]["title"] == "B-new"
    assert len(rejected) == 1 and rejected[0]["problem_id"] == "p1"


def test_export_append_skips_existing(tmp_path):
    probs = [{"problem_id": "p1", "title": "A"}, {"problem_id": "p2", "title": "B"}]
    csv = tmp_path / "review.csv"
    export_review_csv(probs, csv_path=csv, ratio=1.0, append=False)
    new_rows = export_review_csv(probs, csv_path=csv, ratio=1.0, append=True)
    assert new_rows == []  # 全部已存在


# ---------- ocr_pipeline 烟测（用 mock 后端）----------

def test_ocr_pipeline_with_mock(tmp_path, monkeypatch):
    """起一个最小可跑 OCR pipeline：写一张测试图，跑 mock 后端。"""
    monkeypatch.setenv("INGESTION_OCR_BACKEND", "mock")
    from PIL import Image

    img_dir = tmp_path / "pages"
    img_dir.mkdir()
    img = Image.new("RGB", (200, 200), color="white")
    img.save(img_dir / "page_0001.png")

    from ingestion import ocr_pipeline  # noqa: E402

    fake_page = type("P", (), {
        "page_no": 1, "chapter": "测试章", "chapter_level": 1,
        "text": "", "image_path": str(img_dir / "page_0001.png"),
        "is_blank": False, "has_text": False,
    })()
    # ocr_pipeline 里 `split_pdf` 是 from-import 出来的名字，patch 它本身
    monkeypatch.setattr(ocr_pipeline, "split_pdf", lambda *_a, **_kw: [fake_page])

    out_json = tmp_path / "ocr.json"
    res = ocr_pipeline.ocr_pdf("fake.pdf", output_json=out_json, backend="mock")
    assert len(res) == 1
    assert "mock" in res[0]["source"]
    assert out_json.exists()
    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(saved) == 1
