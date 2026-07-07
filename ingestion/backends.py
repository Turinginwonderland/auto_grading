"""OCR 后端抽象。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class OCRBackend(ABC):
    """把一张图片识别成纯文本（带页内 bbox 可选）。"""

    name: str = "abstract"

    @abstractmethod
    def recognize(self, image_path: str) -> str:
        """识别一张图片，返回纯文本（多行）。"""


def get_backend(name: str | None = None) -> OCRBackend:
    """按名称获取后端实例；name=None 时走 ingestion.config.OCR_BACKEND。"""
    from ingestion import config as cfg

    name = name or cfg.OCR_BACKEND
    name = name.lower()

    if name == "paddleocr":
        from ingestion.ocr_runner import PaddleOCRBackend

        return PaddleOCRBackend()
    if name == "tesseract":
        from ingestion.ocr_runner import TesseractBackend

        return TesseractBackend()
    if name == "vision_api":
        from ingestion.ocr_runner import VisionAPIBackend

        return VisionAPIBackend()
    if name == "mock":
        from ingestion.ocr_runner import MockOCRBackend

        return MockOCRBackend()

    raise ValueError(f"unknown OCR backend: {name}")
