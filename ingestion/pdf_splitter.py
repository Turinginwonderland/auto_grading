"""PDF 拆页：按章节书签切分，输出 page 文本（若有）+ 图片。

输出 Page dataclass 列表，可直接喂给 OCR 后端。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ingestion import config as cfg


@dataclass
class Page:
    """一页 PDF 的内容。"""
    page_no: int                   # 1-based
    chapter: str                   # 所属章节名（来自 toc）
    chapter_level: int             # toc 层级（1=章，2=节，3=小节）
    text: str = ""                 # 文本层（扫描页通常为空）
    image_path: str | None = None  # 渲染出的图片路径（OCR 用）
    is_blank: bool = False         # 是否空白页

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


@dataclass
class Chapter:
    """一个章节的范围。"""
    title: str
    level: int
    start_page: int                # 1-based inclusive
    end_page: int                  # 1-based inclusive


def _toc_to_chapters(doc: pymupdf.Document) -> list[Chapter]:
    """把 toc 转成 Chapter 区间列表。"""
    toc = doc.get_toc()
    if not toc:
        return []

    chapters: list[Chapter] = []
    for i, entry in enumerate(toc):
        level, title, page = entry[0], entry[1], entry[2]
        # end_page = 下一条同/更高级的 page - 1
        end = doc.page_count
        for j in range(i + 1, len(toc)):
            if toc[j][0] <= level:
                end = toc[j][2] - 1
                break
        chapters.append(Chapter(title=title, level=level, start_page=page, end_page=end))
    return chapters


def _page_chapter(chapters: list[Chapter], page_no: int) -> tuple[str, int]:
    """找 page_no 属于哪个 chapter。返回 (title, level)，无则返回 ('', 0)。"""
    for c in chapters:
        if c.start_page <= page_no <= c.end_page:
            return c.title, c.level
    return "", 0


def render_page_to_image(
    doc: pymupdf.Document,
    page_no_1based: int,
    out_dir: Path,
    dpi: int = 200,
) -> Path:
    """把指定页渲染为 PNG。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    page = doc[page_no_1based - 1]
    pix = page.get_pixmap(dpi=dpi)
    out = out_dir / f"page_{page_no_1based:04d}.png"
    pix.save(str(out))
    return out


def split_pdf(
    pdf_path: str | Path,
    *,
    render_dir: Path | None = None,
    dpi: int = 200,
    only_text_pages: bool = False,
) -> list[Page]:
    """拆 PDF 返回 Page 列表。

    - 总是抽取文本层（即使很短）
    - 若 only_text_pages=False 且文本为空，自动渲染图片到 render_dir
    - 章节归属来自 toc
    """
    pdf_path = Path(pdf_path)
    doc = pymupdf.open(str(pdf_path))
    chapters = _toc_to_chapters(doc)

    render_dir = render_dir or (cfg.INGESTION_CACHE / "pages")
    render_dir.mkdir(parents=True, exist_ok=True)

    pages: list[Page] = []
    for i in range(doc.page_count):
        page_no = i + 1
        page_obj = doc[i]
        text = page_obj.get_text().strip()

        # 检测空白页（只有页码/分页符）
        cleaned = text.replace("\n", "").strip()
        is_blank = len(cleaned) < 3

        chapter_title, chapter_level = _page_chapter(chapters, page_no)

        image_path = None
        if (not only_text_pages) and (not text):
            image_path = str(render_page_to_image(doc, page_no, render_dir, dpi=dpi))

        pages.append(
            Page(
                page_no=page_no,
                chapter=chapter_title,
                chapter_level=chapter_level,
                text=text,
                image_path=image_path,
                is_blank=is_blank,
            )
        )

    doc.close()
    return pages


def chapter_summary(pages: list[Page]) -> list[dict]:
    """把 Page 列表按章节聚合，给出每章覆盖页范围。"""
    agg: dict[tuple[str, int], dict] = {}
    for p in pages:
        key = (p.chapter, p.chapter_level)
        if key not in agg:
            agg[key] = {
                "title": p.chapter,
                "level": p.chapter_level,
                "pages": [],
                "text_pages": 0,
                "ocr_pages": 0,
            }
        e = agg[key]
        e["pages"].append(p.page_no)
        if p.has_text:
            e["text_pages"] += 1
        elif p.image_path:
            e["ocr_pages"] += 1

    return sorted(
        [{"title": v["title"], "level": v["level"],
          "page_range": (min(v["pages"]), max(v["pages"])) if v["pages"] else (0, 0),
          "page_count": len(v["pages"]),
          "text_pages": v["text_pages"],
          "ocr_pages": v["ocr_pages"]}
         for v in agg.values()],
        key=lambda x: x["page_range"][0],
    )
