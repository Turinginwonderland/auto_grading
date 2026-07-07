"""OCR 文本 → Problem JSON 结构化器。

- split_into_problem_blocks: 规则式切分（无 LLM 依赖，启发式）
- structure_with_llm: 调 OpenAI 兼容 LLM，把页文本 → Problem 列表
- structure_mock: 无 LLM 时的占位实现（保证端到端可跑）
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import httpx

from ingestion import config as cfg

# 题目编号正则（覆盖常见中文教材题号形式）
_PROBLEM_PATTERNS = [
    re.compile(r"^\s*【?\s*例?\s*(\d+)[\.\-](\d+)[\.\-]?\d*】?"),       # 1.2 / 1-2 / 1.2.3
    re.compile(r"^\s*习题\s*(\d+)[\.\-](\d+)[\.\-]?\d*"),               # 习题 2-3
    re.compile(r"^\s*算法\s*(\d+)[\.\-](\d+)[\.\-]?\d*"),               # 算法 2-3
    re.compile(r"^\s*(\d+)\s*[\.、]\s*(\d+)[\.\-]?\d*"),                # 1. 2 / 1、 2
]

# 章节标题正则
_CHAPTER_RE = re.compile(r"^第\s*[一二三四五六七八九十0-9]+\s*章")


def _is_chapter_title(line: str) -> bool:
    return bool(_CHAPTER_RE.match(line.strip()))


def _match_problem_start(line: str) -> str | None:
    """返回识别到的题号字符串；非题号起始行返回 None。"""
    s = line.strip()
    if not s:
        return None
    for pat in _PROBLEM_PATTERNS:
        m = pat.match(s)
        if m:
            return f"{m.group(1)}.{m.group(2)}"
    # 单独的 "1. xxx" 也算
    m2 = re.match(r"^(\d+)\s*[\.、]\s*([^\d].{4,})", s)
    if m2:
        return m2.group(1)
    return None


def split_into_problem_blocks(pages: Iterable[dict]) -> list[dict]:
    """把页文本按"题号"规则切块。每块结构：

    {problem_no, chapter, page_range, raw_text}
    """
    blocks: list[dict] = []
    current: dict | None = None
    current_chapter = ""

    for page in pages:
        chapter = page.get("chapter") or current_chapter
        if chapter and chapter != current_chapter:
            current_chapter = chapter
        lines = (page.get("text") or "").splitlines()
        for line in lines:
            pno = _match_problem_start(line)
            if pno is not None:
                if current is not None:
                    blocks.append(current)
                current = {
                    "problem_no": pno,
                    "chapter": current_chapter,
                    "start_page": page["page_no"],
                    "end_page": page["page_no"],
                    "raw_text": line + "\n",
                }
            else:
                if current is not None:
                    current["raw_text"] += line + "\n"
                    current["end_page"] = page["page_no"]
    if current is not None:
        blocks.append(current)
    return blocks


# ---------- Mock 结构化器 ----------

def structure_mock(blocks: list[dict], source_book: str = "27王道数据结构") -> list[dict]:
    """无 LLM 时的占位实现：把每块转成 Problem dict。"""
    out: list[dict] = []
    for i, b in enumerate(blocks, 1):
        pid = f"ds-{b.get('chapter', 'unk').replace(' ', '')[:8] or 'p'}-{b['problem_no']}"
        # 截前 240 字做描述
        desc = b["raw_text"].strip()[:240] or "（待人工补全）"
        out.append(
            {
                "problem_id": pid,
                "title": f"题目 {b['problem_no']}",
                "description": desc,
                "difficulty": "medium",
                "input_format": None,
                "output_format": None,
                "examples": [],
                "constraints": None,
                "reference_solution": "def solution():\n    pass\n",
                "test_cases": [],
                "scoring_rules": {
                    "correctness_weight": 0.5,
                    "standardization_weight": 0.3,
                    "readability_weight": 0.2,
                },
                "source_book": source_book,
                "source_chapter": b.get("chapter"),
                "source_page": b.get("start_page"),
                "ocr_raw": b["raw_text"][:4000],
            }
        )
    return out


# ---------- LLM 结构化器 ----------

_SYSTEM_PROMPT = """你是一位数据结构教材的题目结构化专家。
你的任务是从教材页面的 OCR 文本中，识别出【每一道独立的题目】，并输出标准 JSON。

要求：
- 只输出 JSON 数组，不要任何解释或 Markdown 包裹
- 每道题字段：problem_no, title, description, difficulty(easy/medium/hard),
  input_format, output_format, examples, constraints, reference_solution
- 找不到的字段填 null 或空数组
- reference_solution 必须是可运行的代码（与题目语言一致，通常是 C / C++ / Python）
- 如果一页内没有完整题目（比如只有讲解），跳过该页
"""


def _call_llm_for_structuring(pages_text: list[dict], model: str, base_url: str, api_key: str) -> list[dict]:
    """调 LLM 把多页文本 → Problem 列表。"""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
    user_content = json.dumps(pages_text, ensure_ascii=False, indent=2)
    resp = client.chat.completions.create(
        model=model,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "请从以下 OCR 文本中提取所有题目，输出 JSON 对象：\n"
                    "{ \"problems\": [ <Problem>, ... ] }\n\n"
                    + user_content[:50_000]  # 截断，避免超 token
                ),
            },
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    obj = json.loads(raw)
    return obj.get("problems", [])


def structure_with_llm(
    pages: list[dict],
    *,
    source_book: str = "27王道数据结构",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """真实 LLM 结构化入口。需 LLM_API_KEY（或显式传入）。"""
    from app.core.config import get_settings

    s = get_settings()
    api_key = api_key or s.llm_api_key
    base_url = base_url or s.llm_base_url
    model = model or s.llm_model
    if not api_key:
        raise RuntimeError("未配置 LLM_API_KEY，无法走 LLM 结构化")

    problems = _call_llm_for_structuring(pages, model=model, base_url=base_url, api_key=api_key)
    # 补上 source 字段
    for p in problems:
        p.setdefault("source_book", source_book)
        p.setdefault("scoring_rules", {
            "correctness_weight": 0.5,
            "standardization_weight": 0.3,
            "readability_weight": 0.2,
        })
    return problems


def structure(
    pages: list[dict],
    *,
    mode: str = "auto",
    source_book: str = "27王道数据结构",
) -> list[dict]:
    """统一入口。

    - mode='llm'  强制走 LLM
    - mode='mock' 强制走 mock
    - mode='auto' 有 key 走 LLM，否则 mock
    """
    from app.core.config import get_settings

    s = get_settings()
    if mode == "llm" or (mode == "auto" and s.use_real_llm):
        return structure_with_llm(pages, source_book=source_book)
    # mock 模式：先按规则切块，再喂给结构化器
    blocks = split_into_problem_blocks(pages)
    return structure_mock(blocks, source_book=source_book)
