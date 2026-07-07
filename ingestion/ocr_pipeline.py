"""批量 OCR 入口。"""
from __future__ import annotations

import json
from pathlib import Path

from ingestion import config as cfg
from ingestion.backends import get_backend
from ingestion.pdf_splitter import Page, split_pdf


def ocr_pdf(
    pdf_path: str | Path,
    *,
    output_json: Path | None = None,
    backend: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """PDF → 逐页 OCR → 写出 JSON 缓存。

    返回 list[{page_no, chapter, text, source}].
    """
    pdf_path = Path(pdf_path)
    backend = backend or cfg.OCR_BACKEND
    ocr = get_backend(backend)

    pages = split_pdf(pdf_path, only_text_pages=False)
    if limit:
        pages = pages[:limit]

    results: list[dict] = []
    for p in pages:
        if p.has_text:
            text, source = p.text, f"text_layer@{p.page_no}"
        elif p.image_path:
            text, source = ocr.recognize(p.image_path), f"{ocr.name}@{p.image_path}"
        else:
            text, source = "", "blank"

        results.append(
            {
                "page_no": p.page_no,
                "chapter": p.chapter,
                "chapter_level": p.chapter_level,
                "text": text,
                "source": source,
                "is_blank": p.is_blank,
            }
        )

    if output_json:
        output_json = Path(output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    return results
