"""评分请求/响应 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_LANGUAGES = {"python", "java", "cpp", "c", "go", "javascript"}


class GradeRequest(BaseModel):
    problem_id: str = Field(..., min_length=1, max_length=64, description="题目 ID")
    code: str = Field(..., min_length=1, max_length=200_000, description="提交的源码")
    language: str = Field(default="python", description="编程语言")
    student_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("language")
    @classmethod
    def _check_lang(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ALLOWED_LANGUAGES:
            raise ValueError(f"unsupported language: {v}")
        return v

    @field_validator("problem_id")
    @classmethod
    def _check_pid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("problem_id is empty")
        return v


class DimensionScore(BaseModel):
    score: int
    weight: float
    max_score: int
    analysis: str


class DimensionsOut(BaseModel):
    correctness: DimensionScore
    standardization: DimensionScore
    readability: DimensionScore


class GradeResponse(BaseModel):
    submission_id: str
    problem_id: str
    overall_score: float
    dimensions: DimensionsOut
    llm_comment: str
    llm_model: str
    created_at: datetime
    status: str = "success"
    cached: bool = False
