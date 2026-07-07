"""评分服务：编排 LLM 调用、落库、缓存。"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.problem import Problem
from app.models.submission import Submission
from app.prompts.rubric import DIMENSIONS, RUBRIC
from app.services import cache
from app.services.llm_service import grade_code
from app.utils.code_hash import sha256_code


def _load_problem(db: Session, problem_id: str) -> Problem | None:
    return db.query(Problem).filter(Problem.problem_id == problem_id).first()


def grade_submission(
    db: Session,
    *,
    problem_id: str,
    code: str,
    language: str,
    student_id: str | None = None,
) -> tuple[Submission, bool]:
    """评分并落库。返回 (submission, cached)。"""
    problem = _load_problem(db, problem_id)
    if problem is None:
        raise LookupError(f"problem not found: {problem_id}")

    code_h = sha256_code(code)
    ckey = cache.cache_key(problem_id, code_h, language)

    # 1) 缓存命中
    hit = cache.cache_get(ckey)
    if hit is not None:
        logger.info(f"cache HIT {ckey[:32]}...")
        sub = Submission(
            problem_id=problem_id,
            student_id=student_id,
            code=code,
            language=language,
            code_hash=code_h,
            status="success",
            overall_score=hit["overall_score"],
            dimension_scores_json=json.dumps(hit["dimension_scores"], ensure_ascii=False),
            llm_comment=hit["llm_comment"],
            llm_model=hit["llm_model"],
            llm_raw_output=hit.get("llm_raw_output"),
            llm_latency_ms=0,
            retry_count=0,
        )
        db.add(sub)
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
    overall = float(parsed["_overall_score"])
    dim_scores = {d: parsed[d]["score"] for d in DIMENSIONS}
    dim_analysis = {d: parsed[d]["analysis"] for d in DIMENSIONS}

    # 3) 落库
    sub = Submission(
        problem_id=problem_id,
        student_id=student_id,
        code=code,
        language=language,
        code_hash=code_h,
        status="success",
        overall_score=overall,
        dimension_scores_json=json.dumps(
            {
                "scores": dim_scores,
                "analysis": dim_analysis,
                "weights": {d: RUBRIC[d]["weight"] for d in DIMENSIONS},
                "max_scores": {d: RUBRIC[d]["max_score"] for d in DIMENSIONS},
            },
            ensure_ascii=False,
        ),
        llm_comment=parsed.get("overall_comment", ""),
        llm_model=result.model,
        llm_raw_output=result.raw,
        llm_latency_ms=result.latency_ms,
        retry_count=result.retry_count,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    # 4) 写缓存
    cache.cache_set(
        ckey,
        {
            "overall_score": overall,
            "dimension_scores": {
                "scores": dim_scores,
                "analysis": dim_analysis,
                "weights": {d: RUBRIC[d]["weight"] for d in DIMENSIONS},
                "max_scores": {d: RUBRIC[d]["max_score"] for d in DIMENSIONS},
            },
            "llm_comment": parsed.get("overall_comment", ""),
            "llm_model": result.model,
            "llm_raw_output": result.raw,
        },
    )

    return sub, False


def submission_to_response(sub: Submission, cached: bool) -> dict[str, Any]:
    dim_block = json.loads(sub.dimension_scores_json) if sub.dimension_scores_json else {}
    scores = dim_block.get("scores", {})
    analysis = dim_block.get("analysis", {})
    weights = dim_block.get("weights", {})
    max_scores = dim_block.get("max_scores", {})

    return {
        "submission_id": sub.submission_id,
        "problem_id": sub.problem_id,
        "overall_score": sub.overall_score,
        "dimensions": {
            d: {
                "score": scores.get(d, 0),
                "weight": weights.get(d, RUBRIC[d]["weight"]),
                "max_score": max_scores.get(d, RUBRIC[d]["max_score"]),
                "analysis": analysis.get(d, ""),
            }
            for d in DIMENSIONS
        },
        "llm_comment": sub.llm_comment or "",
        "llm_model": sub.llm_model or "",
        "created_at": sub.created_at,
        "status": sub.status,
        "cached": cached,
    }
