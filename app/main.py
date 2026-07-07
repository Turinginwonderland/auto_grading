"""FastAPI 入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import grade as grade_routes
from app.api.v1 import health as health_routes
from app.api.v1 import problems as problem_routes
from app.core.config import get_settings
from app.core.logging import logger
from app.db.database import init_db


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(f"Starting app env={settings.app_env} llm={'real' if settings.use_real_llm else 'mock'}")
    init_db()
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Code Grader API",
    version="0.1.0",
    description="LLM-as-a-Judge 代码评分器（Phase 1）",
    lifespan=lifespan,
)


app.include_router(health_routes.router, prefix="/api/v1", tags=["health"])
app.include_router(grade_routes.router, prefix="/api/v1", tags=["grade"])
app.include_router(problem_routes.router, prefix="/api/v1", tags=["problems"])


@app.get("/")
def root() -> dict:
    return {
        "name": "code-grader",
        "version": "0.1.0",
        "phase": "P1.0",
        "docs": "/docs",
    }
