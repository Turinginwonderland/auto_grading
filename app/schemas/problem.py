"""题目 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProblemCreate(BaseModel):
    problem_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=256)
    description: str
    difficulty: str = "medium"
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    examples: list[dict[str, Any]] = Field(default_factory=list)
    constraints: Optional[str] = None
    reference_solution: str = ""
    test_cases: list[dict[str, Any]] = Field(default_factory=list)
    scoring_rules: dict[str, Any] = Field(default_factory=dict)
    source_book: Optional[str] = None
    source_chapter: Optional[str] = None
    source_page: Optional[int] = None
    ocr_raw: Optional[str] = None


class ProblemOut(BaseModel):
    problem_id: str
    title: str
    description: str
    difficulty: str
    input_format: Optional[str]
    output_format: Optional[str]
    examples: list[dict[str, Any]]
    constraints: Optional[str]
    reference_solution: str
    test_cases: list[dict[str, Any]]
    scoring_rules: dict[str, Any]
    source_book: Optional[str]
    source_chapter: Optional[str]
    source_page: Optional[int]
    created_at: datetime
    updated_at: datetime
