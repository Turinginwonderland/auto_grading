"""OCR 后端实现：PaddleOCR / Tesseract / 云视觉 / Mock。

每个后端实现 ingestion.backends.OCRBackend 接口。
未安装依赖的后端构造时会给出明确报错；按需安装。
"""
from __future__ import annotations

import base64
from pathlib import Path

from ingestion import config as cfg
from ingestion.backends import OCRBackend


# ---------- Mock（默认，无外部依赖）----------

class MockOCRBackend(OCRBackend):
    """用于无 OCR 环境的占位实现。

    假装识别出"第N章 / 第N题"等模板文本，便于在没装 PaddleOCR 的机器上
    跑通整条管线（结构化器会从这种模板里读到题号，但内容为占位）。
    """
    name = "mock"

    def __init__(self) -> None:
        # 强制延迟初始化，避免无谓开销
        pass

    def recognize(self, image_path: str) -> str:
        p = Path(image_path)
        # 用文件名里的页号生成伪内容
        try:
            page_no = int(p.stem.split("_")[1])
        except (IndexError, ValueError):
            page_no = 0
        return (
            f"【第 {page_no // 20 + 1} 章】\n"
            f"例 {page_no}.1  题目描述（mock 占位）\n"
            f"输入：无\n"
            f"输出：无\n"
            f"参考代码：def solution():\n    pass\n"
        )


# ---------- PaddleOCR（中文准；需 paddleocr + paddlepaddle）----------

class PaddleOCRBackend(OCRBackend):
    name = "paddleocr"

    def __init__(self, lang: str = "ch") -> None:
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "PaddleOCR 未安装。请先 `pip install paddlepaddle paddleocr`"
            ) from e
        self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)

    def recognize(self, image_path: str) -> str:
        result = self._ocr.ocr(image_path, cls=True)
        lines: list[str] = []
        for page in result or []:
            for line in page or []:
                if line and len(line) >= 2 and line[1]:
                    lines.append(line[1][0])
        return "\n".join(lines)


# ---------- Tesseract（轻量；需本机装 tesseract 二进制 + pytesseract）----------

class TesseractBackend(OCRBackend):
    name = "tesseract"

    def __init__(self, lang: str = "chi_sim") -> None:
        try:
            import pytesseract  # type: ignore  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "pytesseract 未安装。请 `pip install pytesseract` 并安装 Tesseract 二进制"
            ) from e
        self._lang = lang

    def recognize(self, image_path: str) -> str:
        import pytesseract  # type: ignore

        return pytesseract.image_to_string(image_path, lang=self._lang)


# ---------- 云视觉 API（OpenAI 兼容，支持 gpt-4o vision）----------

class VisionAPIBackend(OCRBackend):
    name = "vision_api"

    def __init__(self) -> None:
        if not cfg.VISION_API_KEY:
            raise RuntimeError("VISION_API_KEY 未配置")
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError("openai 未安装，请 `pip install openai`") from e
        self._client = OpenAI(
            api_key=cfg.VISION_API_KEY,
            base_url=cfg.VISION_API_BASE,
        )
        self._model = cfg.VISION_MODEL

    def recognize(self, image_path: str) -> str:
        img = Path(image_path)
        b64 = base64.b64encode(img.read_bytes()).decode("ascii")
        ext = img.suffix.lstrip(".").lower() or "png"
        data_url = f"data:image/{ext};base64,{b64}"
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0.0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "请识别图中的所有文字内容（中文教材扫描页），"
                                "保持原始换行与段落结构。不要做任何总结或翻译，"
                                "只输出 OCR 后的纯文本。"
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        )
        return (resp.choices[0].message.content or "").strip()
