"""批量导入题目到 problems 表。

支持来源：
1. JSON 文件（list[dict]，字段与 schemas.problem.ProblemCreate 对齐）
2. CSV 文件（columns: problem_id, title, description, difficulty, reference_solution, source_chapter, source_page, ...）

用法：
    python -m scripts.seed_problems --json ingestion/cache/structured.json
    python -m scripts.seed_problems --json data/sample_problems.json --upsert
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _normalize_problem(raw: dict[str, Any]) -> dict[str, Any]:
    """把不同来源的 dict 统一成 ProblemCreate 字段集。"""
    defaults = {
        "input_format": None,
        "output_format": None,
        "examples": [],
        "constraints": None,
        "reference_solution": "",
        "test_cases": [],
        "scoring_rules": {
            "correctness_weight": 0.5,
            "standardization_weight": 0.3,
            "readability_weight": 0.2,
        },
        "source_book": None,
        "source_chapter": None,
        "source_page": None,
        "ocr_raw": None,
        "difficulty": "medium",
    }
    out = {**defaults, **raw}
    # problem_id / title / description 必填
    for k in ("problem_id", "title", "description"):
        if not out.get(k):
            raise ValueError(f"problem missing required field: {k}")
    return out


def seed_from_list(problems: list[dict], *, upsert: bool = False) -> tuple[int, int]:
    """把题目列表写入 DB。返回 (created, updated) 数量。"""
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.db.database import SessionLocal, init_db
    from app.models.problem import Problem

    get_settings()  # 触发配置加载
    init_db()

    created = updated = 0
    with SessionLocal() as db:  # type: Session
        for raw in problems:
            try:
                p = _normalize_problem(raw)
            except ValueError as e:
                print(f"[skip] {e}: {raw.get('problem_id')}", file=sys.stderr)
                continue
            row = db.query(Problem).filter(Problem.problem_id == p["problem_id"]).first()
            if row:
                if not upsert:
                    continue
                for k, v in p.items():
                    if k == "scoring_rules":
                        setattr(row, "scoring_rules_json", json.dumps(v, ensure_ascii=False))
                    elif k == "examples":
                        setattr(row, "examples_json", json.dumps(v, ensure_ascii=False))
                    elif k == "test_cases":
                        setattr(row, "test_cases_json", json.dumps(v, ensure_ascii=False))
                    else:
                        setattr(row, k, v)
                updated += 1
            else:
                row = Problem(
                    problem_id=p["problem_id"],
                    title=p["title"],
                    description=p["description"],
                    difficulty=p["difficulty"],
                    input_format=p["input_format"],
                    output_format=p["output_format"],
                    examples_json=json.dumps(p["examples"], ensure_ascii=False),
                    constraints=p["constraints"],
                    reference_solution=p["reference_solution"],
                    test_cases_json=json.dumps(p["test_cases"], ensure_ascii=False),
                    scoring_rules_json=json.dumps(p["scoring_rules"], ensure_ascii=False),
                    source_book=p["source_book"],
                    source_chapter=p["source_chapter"],
                    source_page=p["source_page"],
                    ocr_raw=p["ocr_raw"],
                )
                db.add(row)
                created += 1
        db.commit()
    return created, updated


def load_json(path: Path) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, dict) and "problems" in obj:
        return obj["problems"]
    if not isinstance(obj, list):
        raise ValueError("JSON must be list[...] or {problems: [...]}")
    return obj


def load_csv(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            # 简单解析：examples 走 JSON 字符串，scoring_rules 走 JSON
            try:
                row["examples"] = json.loads(row.get("examples") or "[]")
            except json.JSONDecodeError:
                row["examples"] = []
            try:
                row["scoring_rules"] = json.loads(row.get("scoring_rules") or "{}")
            except json.JSONDecodeError:
                row["scoring_rules"] = {}
            try:
                row["source_page"] = int(row["source_page"]) if row.get("source_page") else None
            except (ValueError, KeyError):
                row["source_page"] = None
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", help="JSON 文件路径")
    parser.add_argument("--csv", dest="csv_path", help="CSV 文件路径")
    parser.add_argument("--upsert", action="store_true", help="存在则更新")
    args = parser.parse_args()

    if not (args.json_path or args.csv_path):
        parser.error("必须提供 --json 或 --csv")

    if args.json_path:
        problems = load_json(Path(args.json_path))
    else:
        problems = load_csv(Path(args.csv_path))

    created, updated = seed_from_list(problems, upsert=args.upsert)
    print(f"created={created} updated={updated} total_input={len(problems)}")


if __name__ == "__main__":
    main()
