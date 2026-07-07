"""题目表 ORM。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Problem(Base):
    __tablename__ = "problems"

    problem_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")

    input_format: Mapped[str | None] = mapped_column(Text)
    output_format: Mapped[str | None] = mapped_column(Text)
    examples_json: Mapped[str] = mapped_column(Text, default="[]")
    constraints: Mapped[str | None] = mapped_column(Text)
    reference_solution: Mapped[str] = mapped_column(Text, default="")
    test_cases_json: Mapped[str] = mapped_column(Text, default="[]")
    scoring_rules_json: Mapped[str] = mapped_column(Text, default="{}")

    source_book: Mapped[str | None] = mapped_column(String(128))
    source_chapter: Mapped[str | None] = mapped_column(String(64))
    source_page: Mapped[int | None] = mapped_column(Integer)

    ocr_raw: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
