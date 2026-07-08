"""POST /grade, GET /submissions, GET /submissions/{id}"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.db.database import get_db
from app.models.submission import Submission
from app.schemas.grade import GradeRequest, GradeResponse
from app.schemas.submission import SubmissionOut
from app.services.grading_service import grade_submission, submission_to_response

router = APIRouter()


@router.post("/grade", response_model=GradeResponse)
def post_grade(req: GradeRequest, db: Session = Depends(get_db)) -> GradeResponse:
    """
    提交评分。
    - 缓存命中：同步完成，status="success"
    - 缓存未命中：起后台 asyncio task，status="pending"，前端轮询 GET /submissions/{id}
    """
    try:
        sub, cached = grade_submission(
            db,
            problem_id=req.problem_id,
            code=req.code,
            language=req.language,
            student_id=req.student_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("grade submit failed")
        raise HTTPException(status_code=500, detail=f"grade submit failed: {e}")

    payload = submission_to_response(sub, cached)
    return GradeResponse(**payload)


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: str, db: Session = Depends(get_db)) -> SubmissionOut:
    sub = db.query(Submission).filter(Submission.submission_id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="submission not found")

    dim = None
    if sub.dimension_scores_json:
        dim = json.loads(sub.dimension_scores_json)
    return SubmissionOut(
        submission_id=sub.submission_id,
        problem_id=sub.problem_id,
        student_id=sub.student_id,
        language=sub.language,
        status=sub.status,
        overall_score=sub.overall_score,
        dimension_scores=dim,
        llm_comment=sub.llm_comment,
        llm_model=sub.llm_model,
        llm_latency_ms=sub.llm_latency_ms,
        retry_count=sub.retry_count,
        error_message=sub.error_message,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    problem_id: str | None = Query(default=None),
    student_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[SubmissionOut]:
    q = db.query(Submission)
    if problem_id:
        q = q.filter(Submission.problem_id == problem_id)
    if student_id:
        q = q.filter(Submission.student_id == student_id)
    rows = q.order_by(Submission.created_at.desc()).limit(limit).offset(offset).all()

    results: list[SubmissionOut] = []
    for sub in rows:
        dim = json.loads(sub.dimension_scores_json) if sub.dimension_scores_json else None
        results.append(
            SubmissionOut(
                submission_id=sub.submission_id,
                problem_id=sub.problem_id,
                student_id=sub.student_id,
                language=sub.language,
                status=sub.status,
                overall_score=sub.overall_score,
                dimension_scores=dim,
                llm_comment=sub.llm_comment,
                llm_model=sub.llm_model,
                llm_latency_ms=sub.llm_latency_ms,
                retry_count=sub.retry_count,
                error_message=sub.error_message,
                created_at=sub.created_at,
                updated_at=sub.updated_at,
            )
        )
    return results
