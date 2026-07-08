"""评分服务：编排 LLM 调用、落库、缓存；异步化（HTTP 立即返 submission_id）。"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.db.database import SessionLocal
from app.models.problem import Problem
from app.models.submission import Submission
from app.prompts.rubric import DIMENSIONS, RUBRIC
from app.services import cache
from app.services.llm_service import grade_code
from app.utils.code_hash import sha256_code


def _load_problem(db: Session, problem_id: str) -> Problem | None:
    return db.query(Problem).filter(Problem.problem_id == problem_id).first()


def _new_pending_submission(
    db: Session,
    *,
    problem_id: str,
    code: str,
    language: str,
    student_id: str | None,
    code_h: str,
) -> Submission:
    """插入一条 status=pending 的占位记录，立刻 commit 让 GET 能看到。"""
    sub = Submission(
        problem_id=problem_id,
        student_id=student_id,
        code=code,
        language=language,
        code_hash=code_h,
        status="pending",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def _fill_submission_from_result(
    sub: Submission,
    *,
    problem: Problem,
    parsed: dict[str, Any],
    llm_model: str,
    raw: str,
    latency_ms: int,
    retry_count: int,
) -> tuple[float, dict[str, Any], str]:
    """把 LLM 结果写进 sub 并 commit。返回 (overall, dim_block, comment)。"""
    overall = float(parsed["_overall_score"])
    dim_scores = {d: parsed[d]["score"] for d in DIMENSIONS}
    dim_analysis = {d: parsed[d]["analysis"] for d in DIMENSIONS}
    dim_block = {
        "scores": dim_scores,
        "analysis": dim_analysis,
        "weights": {d: RUBRIC[d]["weight"] for d in DIMENSIONS},
        "max_scores": {d: RUBRIC[d]["max_score"] for d in DIMENSIONS},
    }
    comment = parsed.get("overall_comment", "")

    sub.status = "success"
    sub.overall_score = overall
    sub.dimension_scores_json = json.dumps(dim_block, ensure_ascii=False)
    sub.llm_comment = comment
    sub.llm_model = llm_model
    sub.llm_raw_output = raw
    sub.llm_latency_ms = latency_ms
    sub.retry_count = retry_count
    sub.error_message = None
    return overall, dim_block, comment


def _grade_submission_sync(
    db: Session,
    sub: Submission,
    *,
    problem_id: str,
    code: str,
    language: str,
    code_h: str,
) -> tuple[Submission, bool]:
    """同步核心：缓存命中直接写库；未命中调 LLM 写库并写缓存。返回 (sub, cached)。"""
    problem = _load_problem(db, problem_id)
    if problem is None:
        # 上层应该已经校验过；这里兜底
        sub.status = "failed"
        sub.error_message = f"problem not found: {problem_id}"
        db.commit()
        raise LookupError(f"problem not found: {problem_id}")

    ckey = cache.cache_key(problem_id, code_h, language)

    # 1) 缓存命中
    hit = cache.cache_get(ckey)
    if hit is not None:
        logger.info(f"cache HIT {ckey[:32]}...")
        sub.status = "success"
        sub.overall_score = hit["overall_score"]
        sub.dimension_scores_json = json.dumps(hit["dimension_scores"], ensure_ascii=False)
        sub.llm_comment = hit["llm_comment"]
        sub.llm_model = hit["llm_model"]
        sub.llm_raw_output = hit.get("llm_raw_output")
        sub.llm_latency_ms = 0
        sub.retry_count = 0
        db.commit()
        db.refresh(sub)
        return sub, True

    # 2) 调 LLM
    result = grade_code(
        problem_title=problem.title,
        problem_description=problem.description,
        language=language,
        code=code,
        reference_solution=problem.reference_solution or None,
    )
    parsed = result.parsed
    overall, _dim_block, _comment = _fill_submission_from_result(
        sub,
        problem=problem,
        parsed=parsed,
        llm_model=result.model,
        raw=result.raw,
        latency_ms=result.latency_ms,
        retry_count=result.retry_count,
    )
    db.commit()
    db.refresh(sub)

    # 3) 写缓存
    cache.cache_set(
        ckey,
        {
            "overall_score": overall,
            "dimension_scores": {
                "scores": {d: parsed[d]["score"] for d in DIMENSIONS},
                "analysis": {d: parsed[d]["analysis"] for d in DIMENSIONS},
                "weights": {d: RUBRIC[d]["weight"] for d in DIMENSIONS},
                "max_scores": {d: RUBRIC[d]["max_score"] for d in DIMENSIONS},
            },
            "llm_comment": parsed.get("overall_comment", ""),
            "llm_model": result.model,
            "llm_raw_output": result.raw,
        },
    )
    return sub, False


async def _run_grade_task(
    submission_id: str,
    *,
    problem_id: str,
    code: str,
    language: str,
    code_h: str,
) -> None:
    """后台 task：开新 session 跑同步核心，异常时写 failed。"""
    db = SessionLocal()
    try:
        sub = db.query(Submission).filter(Submission.submission_id == submission_id).first()
        if sub is None:
            logger.error(f"submission {submission_id} vanished before grading")
            return
        try:
            _grade_submission_sync(
                db,
                sub,
                problem_id=problem_id,
                code=code,
                language=language,
                code_h=code_h,
            )
            logger.info(f"submission {submission_id} graded (async)")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"submission {submission_id} failed")
            sub.status = "failed"
            sub.error_message = f"{type(e).__name__}: {e}"
            db.commit()
    finally:
        db.close()


def grade_submission(
    db: Session,
    *,
    problem_id: str,
    code: str,
    language: str,
    student_id: str | None = None,
) -> tuple[Submission, bool]:
    """
    异步入口：立即创建 pending 记录并返回。
    - 缓存命中：同步跑完（毫秒级），返回 (sub, True)
    - 缓存未命中：起 asyncio task 跑 LLM，返回 (sub, False) status=pending
    """
    problem = _load_problem(db, problem_id)
    if problem is None:
        raise LookupError(f"problem not found: {problem_id}")

    code_h = sha256_code(code)
    ckey = cache.cache_key(problem_id, code_h, language)

    # 缓存命中：走同步（毫秒级，无意义异步）
    if cache.cache_get(ckey) is not None:
        sub = _new_pending_submission(
            db,
            problem_id=problem_id,
            code=code,
            language=language,
            student_id=student_id,
            code_h=code_h,
        )
        return _grade_submission_sync(
            db,
            sub,
            problem_id=problem_id,
            code=code,
            language=language,
            code_h=code_h,
        )

    # 缓存未命中：先落 pending，立刻起 task
    sub = _new_pending_submission(
        db,
        problem_id=problem_id,
        code=code,
        language=language,
        student_id=student_id,
        code_h=code_h,
    )
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(
                _run_grade_task(
                    sub.submission_id,
                    problem_id=problem_id,
                    code=code,
                    language=language,
                    code_h=code_h,
                )
            )
        else:
            # 离线脚本 / 测试同步上下文：起新 loop 跑
            asyncio.run(
                _run_grade_task(
                    sub.submission_id,
                    problem_id=problem_id,
                    code=code,
                    language=language,
                    code_h=code_h,
                )
            )
    except RuntimeError:
        # 没 loop 也没法 get：极端兜底——同步跑完
        logger.warning("no event loop, falling back to sync grading")
        _grade_submission_sync(
            db,
            sub,
            problem_id=problem_id,
            code=code,
            language=language,
            code_h=code_h,
        )
    return sub, False


def submission_to_response(sub: Submission, cached: bool) -> dict[str, Any]:
    """把 Submission ORM 转 dict。pending 时 dimensions=None、overall_score=None。"""
    pending = sub.status != "success"
    dim_block = json.loads(sub.dimension_scores_json) if sub.dimension_scores_json else {}
    scores = dim_block.get("scores", {})
    analysis = dim_block.get("analysis", {})
    weights = dim_block.get("weights", {})
    max_scores = dim_block.get("max_scores", {})

    dimensions: dict[str, Any] | None
    if pending:
        dimensions = None
    else:
        dimensions = {
            d: {
                "score": scores.get(d, 0),
                "weight": weights.get(d, RUBRIC[d]["weight"]),
                "max_score": max_scores.get(d, RUBRIC[d]["max_score"]),
                "analysis": analysis.get(d, ""),
            }
            for d in DIMENSIONS
        }

    return {
        "submission_id": sub.submission_id,
        "problem_id": sub.problem_id,
        "status": sub.status,
        "overall_score": sub.overall_score,
        "dimensions": dimensions,
        "llm_comment": sub.llm_comment or "",
        "llm_model": sub.llm_model or "",
        "created_at": sub.created_at,
        "cached": cached,
    }
