"""提交记录表 ORM。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _new_submission_id() -> str:
    return str(uuid.uuid4())


class Submission(Base):
    __tablename__ = "submissions"

    submission_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_submission_id
    )
    problem_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    student_id: Mapped[str | None] = mapped_column(String(64), index=True)

    code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="python")
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    overall_score: Mapped[float | None] = mapped_column(Float)
    dimension_scores_json: Mapped[str | None] = mapped_column(Text)
    llm_comment: Mapped[str | None] = mapped_column(Text)

    llm_raw_output: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(String(64))
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
