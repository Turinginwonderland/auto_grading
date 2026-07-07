"""ingestion 子配置（独立 .env 段，不污染 app 运行时）。"""
from __future__ import annotations

import os
from pathlib import Path

# 项目根 = ingestion 的上一级
ROOT = Path(__file__).resolve().parent.parent

# 缓存/中间产物目录
INGESTION_CACHE = ROOT / "ingestion" / "cache"
INGESTION_CACHE.mkdir(parents=True, exist_ok=True)

# OCR 原始输出
OCR_OUTPUT = ROOT / "ingestion" / "ocr_output"
OCR_OUTPUT.mkdir(parents=True, exist_ok=True)

# 人工抽检 CSV
HUMAN_REVIEW_CSV = ROOT / "ingestion" / "human_review.csv"

# 抽检比例
HUMAN_REVIEW_RATIO = float(os.getenv("INGESTION_REVIEW_RATIO", "0.1"))


# ===== OCR 后端选择 =====
# 可选： paddleocr | tesseract | vision_api | mock
OCR_BACKEND = os.getenv("INGESTION_OCR_BACKEND", "mock")

# 云视觉 API 配置（与 app/core/config 解耦）
VISION_API_KEY = os.getenv("VISION_API_KEY", "")
VISION_API_BASE = os.getenv("VISION_API_BASE", "https://api.openai.com/v1")
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o")

# 章节候选词（用于识别 "例 X.Y" / "习题 X-Y"）
SECTION_HINTS = [
    r"^[【\[]\s*\d+[\.\-]\d+[\.\-]?\d*\s*[】\]]",  # 【1.2.3】 / [1-2-3]
    r"^例\s*\d+[\.\-]\d+",
    r"^习题\s*\d+",
    r"^算法\s*\d+",
]
