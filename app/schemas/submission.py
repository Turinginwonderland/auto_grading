"""提交记录 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class SubmissionOut(BaseModel):
    submission_id: str
    problem_id: str
    student_id: Optional[str]
    language: str
    status: str
    overall_score: Optional[float]
    dimension_scores: Optional[dict[str, Any]]
    llm_comment: Optional[str]
    llm_model: Optional[str]
    llm_latency_ms: Optional[int]
    retry_count: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
