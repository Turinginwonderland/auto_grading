"""评分一致性评测：跑 labeled_samples.json，与 expected 区间对比，输出报告。

用法：
    python tests/eval/run_eval.py
    python tests/eval/run_eval.py --runs 3     # 跑 3 轮算方差
    python tests/eval/run_eval.py --json-only  # 只写 JSON 报告

吻合判定：actual 在 [min, max] 内算通过；overall 阈值用 5 分宽容度（每个维度单独判定）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# 允许从项目根跑
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.db.database import SessionLocal, init_db
from app.models.problem import Problem
from app.models.submission import Submission
from app.services.grading_service import _grade_submission_sync
from app.utils.code_hash import sha256_code

EVAL_DIR = Path(__file__).resolve().parent
SAMPLES_FILE = EVAL_DIR / "labeled_samples.json"
REPORT_JSON = EVAL_DIR / "report.json"
REPORT_MD = EVAL_DIR / "report.md"
PASS_THRESHOLD = 0.80  # 规划要求 <80% 不许过 P1


@dataclass
class SampleResult:
    sample_id: str
    problem_id: str
    tag: str
    expected_overall: list[int]
    actual_overall: float
    overall_pass: bool
    dimensions: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: str = ""


def _setup_problems(db: Session, problem_ids: set[str]) -> None:
    """评测用的题库里没的题就插占位题（mock 不看 description 文本）。"""
    existing = {p.problem_id for p in db.query(Problem).all()}
    for pid in problem_ids:
        if pid in existing:
            continue
        db.add(
            Problem(
                problem_id=pid,
                title=pid,
                description=f"[eval placeholder for {pid}]",
                difficulty="medium",
                reference_solution="# placeholder",
            )
        )
    db.commit()


def _reset_submissions(db: Session) -> None:
    """清空 submissions 表，避免 ID 冲突。"""
    db.query(Submission).delete()
    db.commit()


def _in_range(value: float, range_: list[int]) -> bool:
    if len(range_) != 2:
        return False
    return range_[0] <= value <= range_[1]


def evaluate_one(
    db: Session, sample: dict[str, Any]
) -> SampleResult:
    """对单条样本跑一次评分，返回结果。"""
    code = sample["code"]
    language = sample.get("language", "python")
    code_h = sha256_code(code)

    # 插一条 pending 占位
    sub = Submission(
        problem_id=sample["problem_id"],
        code=code,
        language=language,
        code_hash=code_h,
        status="pending",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    _grade_submission_sync(
        db,
        sub,
        problem_id=sample["problem_id"],
        code=code,
        language=language,
        code_h=code_h,
    )
    db.refresh(sub)

    dim_block = json.loads(sub.dimension_scores_json or "{}")
    scores = dim_block.get("scores", {})
    actual_overall = float(sub.overall_score)

    dimensions: dict[str, dict[str, Any]] = {}
    for dim in ("correctness", "standardization", "readability"):
        exp_key = f"expected_{dim}"
        expected_range = sample.get(exp_key)
        actual = scores.get(dim)
        if expected_range and actual is not None:
            dim_pass = _in_range(actual, expected_range)
            dim_diff = actual - (expected_range[0] + expected_range[1]) / 2
            dimensions[dim] = {
                "expected": expected_range,
                "actual": actual,
                "pass": dim_pass,
                "diff": round(dim_diff, 1),
            }

    return SampleResult(
        sample_id=sample["id"],
        problem_id=sample["problem_id"],
        tag=sample.get("tag", ""),
        expected_overall=sample.get("expected_overall", [0, 100]),
        actual_overall=actual_overall,
        overall_pass=_in_range(actual_overall, sample.get("expected_overall", [0, 100])),
        dimensions=dimensions,
        notes=sample.get("notes", ""),
    )


def aggregate(results: list[SampleResult]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {"total": 0, "overall_pass_rate": 0.0, "all_dim_pass_rate": 0.0}
    overall_pass = sum(1 for r in results if r.overall_pass)
    by_tag = Counter(r.tag for r in results)
    tag_pass = Counter(r.tag for r in results if r.overall_pass)

    # 维度级
    dim_stats: dict[str, dict[str, Any]] = {}
    for dim in ("correctness", "standardization", "readability"):
        rows = [r.dimensions[dim] for r in results if dim in r.dimensions]
        if not rows:
            continue
        passed = sum(1 for r in rows if r["pass"])
        avg_diff = sum(r["diff"] for r in rows) / len(rows)
        dim_stats[dim] = {
            "total": len(rows),
            "pass": passed,
            "pass_rate": round(passed / len(rows), 3),
            "avg_diff_from_mid": round(avg_diff, 2),
        }

    # "全维度都通过"率
    full_pass = sum(
        1
        for r in results
        if r.overall_pass
        and all(r.dimensions.get(d, {}).get("pass") for d in ("correctness", "standardization", "readability"))
    )

    return {
        "total": n,
        "overall_pass": overall_pass,
        "overall_pass_rate": round(overall_pass / n, 3),
        "all_dim_pass": full_pass,
        "all_dim_pass_rate": round(full_pass / n, 3),
        "by_tag": {
            t: {
                "total": by_tag[t],
                "pass": tag_pass.get(t, 0),
                "pass_rate": round(tag_pass.get(t, 0) / by_tag[t], 3),
            }
            for t in sorted(by_tag)
        },
        "by_dimension": dim_stats,
        "gate_pass": (overall_pass / n) >= PASS_THRESHOLD,
    }


def render_markdown(results: list[SampleResult], summary: dict[str, Any]) -> str:
    lines = ["# Code Grader 评分一致性评测报告\n"]
    lines.append(f"**样本数**: {summary['total']}  ")
    lines.append(f"**Overall 吻合率**: {summary['overall_pass_rate'] * 100:.1f}% ({summary['overall_pass']}/{summary['total']})  ")
    lines.append(f"**全维度吻合率**: {summary['all_dim_pass_rate'] * 100:.1f}% ({summary['all_dim_pass']}/{summary['total']})  ")
    lines.append(f"**Gate ({PASS_THRESHOLD * 100:.0f}%)**: {'✅ 通过' if summary['gate_pass'] else '❌ 未通过'}\n")

    lines.append("## 按标签\n")
    lines.append("| Tag | Total | Pass | Rate |")
    lines.append("|---|---|---|---|")
    for tag, info in summary.get("by_tag", {}).items():
        lines.append(f"| {tag} | {info['total']} | {info['pass']} | {info['pass_rate'] * 100:.1f}% |")
    lines.append("")

    lines.append("## 按维度\n")
    lines.append("| Dimension | Pass/Total | Rate | Avg Diff From Mid |")
    lines.append("|---|---|---|---|")
    for dim, info in summary.get("by_dimension", {}).items():
        lines.append(
            f"| {dim} | {info['pass']}/{info['total']} | {info['pass_rate'] * 100:.1f}% | {info['avg_diff_from_mid']:+.1f} |"
        )
    lines.append("")

    lines.append("## 样本明细\n")
    lines.append("| ID | Tag | Expected | Actual | Pass |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        exp = f"[{r.expected_overall[0]}, {r.expected_overall[1]}]"
        lines.append(
            f"| {r.sample_id} | {r.tag} | {exp} | {r.actual_overall:.1f} | {'✅' if r.overall_pass else '❌'} |"
        )
    lines.append("")

    fails = [r for r in results if not r.overall_pass]
    if fails:
        lines.append("## ❌ 失败样本\n")
        for r in fails:
            lines.append(f"### {r.sample_id} (tag={r.tag})")
            lines.append(f"- Expected: [{r.expected_overall[0]}, {r.expected_overall[1]}], Actual: {r.actual_overall:.1f}")
            for dim, info in r.dimensions.items():
                mark = "✅" if info["pass"] else "❌"
                lines.append(f"  - {dim}: {mark} actual={info['actual']} expected={info['expected']} diff={info['diff']:+.1f}")
            if r.notes:
                lines.append(f"- Note: {r.notes}")
            lines.append("")

    return "\n".join(lines)


def run(runs: int = 1, json_only: bool = False) -> dict[str, Any]:
    samples = json.loads(SAMPLES_FILE.read_text(encoding="utf-8"))["samples"]
    problem_ids = {s["problem_id"] for s in samples}

    init_db()
    db = SessionLocal()
    try:
        _setup_problems(db, problem_ids)
        _reset_submissions(db)

        all_runs: list[list[SampleResult]] = []
        for run_idx in range(runs):
            run_results: list[SampleResult] = []
            for sample in samples:
                try:
                    run_results.append(evaluate_one(db, sample))
                except Exception as e:  # noqa: BLE001
                    run_results.append(
                        SampleResult(
                            sample_id=sample["id"],
                            problem_id=sample["problem_id"],
                            tag=sample.get("tag", ""),
                            expected_overall=sample.get("expected_overall", [0, 100]),
                            actual_overall=0.0,
                            overall_pass=False,
                            notes=f"ERR: {type(e).__name__}: {e}",
                        )
                    )
            all_runs.append(run_results)
    finally:
        db.close()

    # 多轮跑：取最后一轮的结果作为主报告（方差信息单独记录）
    last = all_runs[-1]
    summary = aggregate(last)

    if runs > 1:
        # 算每个样本的 overall 跨轮方差
        variances: list[dict[str, Any]] = []
        for i, sample in enumerate(samples):
            vals = [r[i].actual_overall for r in all_runs]
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            variances.append(
                {
                    "sample_id": sample["id"],
                    "values": vals,
                    "mean": round(mean, 2),
                    "variance": round(var, 2),
                }
            )
        summary["multi_run"] = {
            "runs": runs,
            "per_sample_variance": variances,
            "max_variance": max((v["variance"] for v in variances), default=0),
        }

    report = {
        "summary": summary,
        "samples": [asdict(r) for r in last],
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not json_only:
        REPORT_MD.write_text(render_markdown(last, summary), encoding="utf-8")

    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=1, help="每条样本跑几轮（取最后一轮做主报告，前面的算方差）")
    p.add_argument("--json-only", action="store_true", help="只写 report.json 不写 markdown")
    args = p.parse_args()

    report = run(runs=args.runs, json_only=args.json_only)
    s = report["summary"]
    print(f"samples={s['total']}  overall_pass={s['overall_pass_rate'] * 100:.1f}%  all_dim_pass={s['all_dim_pass_rate'] * 100:.1f}%  gate={'PASS' if s['gate_pass'] else 'FAIL'}")
    if "multi_run" in s:
        print(f"max_variance={s['multi_run']['max_variance']:.2f}")
    return 0 if s["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
