"""end-to-end runner：split → ocr → structure → review → write to DB。

用法：
    python -m ingestion.runner --pdf data/xxx.pdf --backend mock
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 把项目根加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingestion import config as cfg  # noqa: E402
from ingestion.human_review import apply_reviewed, export_review_csv  # noqa: E402
from ingestion.ocr_pipeline import ocr_pdf  # noqa: E402
from ingestion.pdf_splitter import chapter_summary  # noqa: E402
from scripts.seed_problems import seed_from_list  # noqa: E402


def run(
    pdf_path: str,
    *,
    backend: str = "mock",
    limit: int | None = None,
    review_ratio: float = 0.1,
    write_to_db: bool = True,
    ocr_cache: Path | None = None,
) -> dict:
    """一站式入库。返回各阶段统计。"""
    pdf_path = Path(pdf_path)
    ocr_cache = ocr_cache or (cfg.INGESTION_CACHE / f"{pdf_path.stem}_ocr.json")

    # 1) OCR
    pages = ocr_pdf(pdf_path, output_json=ocr_cache, backend=backend, limit=limit)
    chapters = chapter_summary([
        type("P", (), {
            "page_no": p["page_no"], "chapter": p["chapter"],
            "chapter_level": p["chapter_level"], "text": p["text"],
            "image_path": None, "is_blank": p.get("is_blank", False),
        })()
        for p in pages
    ])

    # 2) 结构化
    from ingestion.llm_structurer import structure

    structured = structure(pages)

    # 3) 抽检
    new_review_rows = export_review_csv(structured, ratio=review_ratio, append=True)

    # 4) 应用抽检结果（首次跑时全部为 pending，等于全保留）
    kept, edited, rejected = apply_reviewed(structured)
    final_problems = kept + edited

    # 5) 入库
    stats = {
        "pages_total": len(pages),
        "chapters": len(chapters),
        "structured_count": len(structured),
        "review_pending": len(new_review_rows),
        "kept": len(kept),
        "edited": len(edited),
        "rejected": len(rejected),
        "final_problem_count": len(final_problems),
        "ocr_cache": str(ocr_cache),
        "review_csv": str(cfg.HUMAN_REVIEW_CSV),
    }
    if write_to_db and final_problems:
        seed_from_list(final_problems, upsert=True)
        stats["seeded"] = len(final_problems)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF → 题库 一站式入库")
    parser.add_argument("--pdf", required=True, help="PDF 路径")
    parser.add_argument("--backend", default=None, help="OCR 后端: paddleocr/tesseract/vision_api/mock")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 页（调试用）")
    parser.add_argument("--review-ratio", type=float, default=0.1, help="抽检比例")
    parser.add_argument("--no-db", action="store_true", help="不入库，只生成中间产物")
    args = parser.parse_args()

    stats = run(
        args.pdf,
        backend=args.backend or cfg.OCR_BACKEND,
        limit=args.limit,
        review_ratio=args.review_ratio,
        write_to_db=not args.no_db,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
