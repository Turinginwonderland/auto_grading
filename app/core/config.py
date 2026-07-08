"""Pydantic-settings 配置入口。"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    llm_api_key: Optional[str] = Field(default=None, alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.openai.com/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=1500, alias="LLM_MAX_TOKENS")
    llm_timeout: int = Field(default=30, alias="LLM_TIMEOUT")

    # App
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    # Database
    database_url: str = Field(default="sqlite:///./data/code_grader.db", alias="DATABASE_URL")

    # Cache
    grade_cache_ttl: int = Field(default=86400, alias="GRADE_CACHE_TTL")
    grade_cache_maxsize: int = Field(default=1024, alias="GRADE_CACHE_MAXSIZE")

    # Sandbox（P2.x 硬化）
    sandbox_backend: str = Field(default="subprocess", alias="SANDBOX_BACKEND")
    sandbox_memory_mb: int = Field(default=256, alias="SANDBOX_MEMORY_MB")
    sandbox_max_processes: int = Field(default=32, alias="SANDBOX_MAX_PROCESSES")
    # 0 = 自动 = wall_timeout + 1 秒
    sandbox_cpu_time_sec: int = Field(default=0, alias="SANDBOX_CPU_TIME_SEC")

    @property
    def use_real_llm(self) -> bool:
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
