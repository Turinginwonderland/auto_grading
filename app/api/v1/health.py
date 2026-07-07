"""健康检查。"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "env": s.app_env,
        "llm_model": "mock-grader-v1" if not s.use_real_llm else s.llm_model,
    }
