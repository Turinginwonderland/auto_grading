"""人工抽检：抽 10% 题目导出 CSV，便于人工标注 confirm/edit/reject。

CSV 字段：
  problem_id, title, status(pending/confirmed/edited/rejected), editor, note, edited_json
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from ingestion import config as cfg


_FIELDS = ["problem_id", "title", "status", "editor", "note", "edited_json"]


def _read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def sample_for_review(
    problems: list[dict],
    *,
    ratio: float | None = None,
    seed: int = 42,
) -> list[dict]:
    """按比例抽题目（确定性随机）。"""
    ratio = ratio if ratio is not None else cfg.HUMAN_REVIEW_RATIO
    if not problems or ratio <= 0:
        return []
    k = max(1, int(len(problems) * ratio))
    rng = random.Random(seed)
    return rng.sample(problems, k)


def export_review_csv(
    problems: list[dict],
    csv_path: Path | None = None,
    *,
    ratio: float | None = None,
    append: bool = True,
) -> list[dict]:
    """把待抽检题目写入 CSV。返回写入的行列表。

    - append=True 时跳过已存在的 problem_id
    - status 默认 'pending'
    """
    csv_path = csv_path or cfg.HUMAN_REVIEW_CSV
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    sampled = sample_for_review(problems, ratio=ratio)
    existing = _read_existing(csv_path) if append else []
    existing_ids = {r["problem_id"] for r in existing if r.get("problem_id")}

    new_rows: list[dict] = []
    for p in sampled:
        if p["problem_id"] in existing_ids:
            continue
        new_rows.append(
            {
                "problem_id": p["problem_id"],
                "title": p.get("title", ""),
                "status": "pending",
                "editor": "",
                "note": "",
                "edited_json": "",
            }
        )

    all_rows = existing + new_rows
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    return new_rows


def apply_reviewed(
    problems: list[dict],
    csv_path: Path | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """根据抽检 CSV 调整题目列表。

    返回 (kept, edited, rejected)：
    - kept: status=confirmed 的原样保留
    - edited: status=edited 的，用 edited_json 替换
    - rejected: status=rejected 的，过滤掉
    """
    csv_path = csv_path or cfg.HUMAN_REVIEW_CSV
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return problems, [], []

    by_id = {p["problem_id"]: p for p in problems}
    reviewed = _read_existing(csv_path)
    reviewed_by_id = {r["problem_id"]: r for r in reviewed if r.get("status") and r["status"] != "pending"}

    kept: list[dict] = []
    edited: list[dict] = []
    rejected: list[dict] = []

    for pid, p in by_id.items():
        rev = reviewed_by_id.get(pid)
        if not rev:
            # 没被抽到 = 默认通过
            kept.append(p)
            continue
        status = rev.get("status", "pending")
        if status == "confirmed":
            kept.append(p)
        elif status == "edited" and rev.get("edited_json"):
            try:
                edited.append(json.loads(rev["edited_json"]))
            except json.JSONDecodeError:
                kept.append(p)  # JSON 坏就当原样
        elif status == "rejected":
            rejected.append(p)

    return kept, edited, rejected
