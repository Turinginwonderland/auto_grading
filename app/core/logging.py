"""结构化日志（loguru）。"""
from __future__ import annotations

import sys

from loguru import logger

from app.core.config import get_settings

settings = get_settings()

# 移除默认 handler，配置统一格式
logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
    ),
    level="DEBUG" if settings.app_env == "dev" else "INFO",
    enqueue=False,
)


__all__ = ["logger"]
