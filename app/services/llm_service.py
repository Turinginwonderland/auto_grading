"""LLM 调用层。

- 配置了 LLM_API_KEY 时走 OpenAI 兼容协议
- 未配置时走内置 mock grader（保证 P1.0 端到端可跑）
- 统一返回 ``(parsed_dict, raw_text, latency_ms, retry_count)``
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.logging import logger
from app.prompts.rubric import DIMENSIONS, RUBRIC, calc_overall, validate_score
from app.services.prompt_builder import get_system_prompt, build_user_prompt

settings = get_settings()


@dataclass
class LLMResult:
    parsed: dict[str, Any]
    raw: str
    latency_ms: int
    retry_count: int
    model: str


# ---------- Mock 评分器（无 API key 时使用）----------

def _count_lines(code: str) -> int:
    return sum(1 for _ in code.splitlines() if _.strip())


def _has_docstring(code: str) -> bool:
    return ('"""' in code) or ("'''" in code)


def _has_type_hints(code: str) -> bool:
    # 简单启发式：包含 "->" 或 ": List["、": int" 等
    return bool(re.search(r"->\s*\w+|:\s*(List|Dict|Optional|int|str|float|bool)\b", code))


def _has_dead_code_markers(code: str) -> bool:
    return any(tok in code for tok in ("TODO", "FIXME", "pass  # ", "raise NotImplementedError"))


def _mock_grade(
    problem_title: str,
    problem_description: str,
    language: str,
    code: str,
    reference_solution: str | None,
) -> dict[str, Any]:
    """基于规则的可复现 mock 评分。"""
    n = _count_lines(code)
    has_doc = _has_docstring(code)
    has_hint = _has_type_hints(code)
    has_dead = _has_dead_code_markers(code)

    # 正确性启发式
    if n == 0:
        correctness = 0
    elif "def " not in code and "class " not in code:
        correctness = 12
    elif has_dead:
        correctness = 18
    elif n < 5:
        correctness = 25
    elif n < 20:
        correctness = 40
    else:
        correctness = 46

    # 规范性
    standardization = 12
    if has_hint:
        standardization += 8
    if has_doc:
        standardization += 6
    if n > 0 and n < 200:
        standardization += 2
    standardization = min(30, standardization)

    # 可读性
    readability = 8
    if n > 0 and n < 80:
        readability += 6
    if has_doc:
        readability += 3
    if has_hint:
        readability += 2
    readability = min(20, readability)

    scores = {
        "correctness": correctness,
        "standardization": standardization,
        "readability": readability,
    }

    return {
        "thought_summary": f"基于规则的 mock 评分：代码 {n} 行，含类型注解={has_hint}, docstring={has_doc}。",
        "correctness": {
            "score": scores["correctness"],
            "analysis": f"代码共 {n} 行（mock 评估）。" + ("检测到 TODO/NotImplementedError 等未完成标记。" if has_dead else "未发现明显未完成标记。"),
        },
        "standardization": {
            "score": scores["standardization"],
            "analysis": f"类型注解={has_hint}, docstring={has_doc}。",
        },
        "readability": {
            "score": scores["readability"],
            "analysis": f"代码 {n} 行，" + ("较短易读" if n < 80 else "建议拆分函数"),
        },
        "overall_comment": "此为 P1.0 mock 输出；配置 LLM_API_KEY 后将切换为真实模型评分。",
        "_overall_score": calc_overall(scores),
    }


# ---------- 真实 LLM 调用（OpenAI 兼容协议）----------

def _call_openai(
    system: str, user: str, *, max_retries: int = 2
) -> tuple[dict[str, Any], str, int]:
    """同步调用 OpenAI 兼容协议。返回 (parsed, raw, latency_ms)。"""
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout,
    )

    last_err: Exception | None = None
    raw_text = ""
    start = time.time()

    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            raw_text = (resp.choices[0].message.content or "").strip()
            parsed = _parse_and_validate(raw_text)
            latency_ms = int((time.time() - start) * 1000)
            return parsed, raw_text, latency_ms
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
            continue

    latency_ms = int((time.time() - start) * 1000)
    raise RuntimeError(f"LLM call failed after {max_retries + 1} attempts: {last_err}")


# ---------- 解析与校验 ----------

def _extract_json(text: str) -> str:
    """LLM 偶尔会包 ```json ... ```，尝试剥离。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉首尾三反引号
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # 找最外层 {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


def _parse_and_validate(text: str) -> dict[str, Any]:
    """JSON 解析 + 维度/分数校验。"""
    raw = _extract_json(text)
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("LLM output is not a JSON object")

    for dim in DIMENSIONS:
        if dim not in obj or not isinstance(obj[dim], dict):
            raise ValueError(f"missing dimension: {dim}")
        s = obj[dim].get("score")
        if not isinstance(s, int):
            raise ValueError(f"{dim}.score is not int: {s!r}")
        if not validate_score(dim, s):
            raise ValueError(f"{dim}.score out of range: {s}")
        if "analysis" not in obj[dim]:
            raise ValueError(f"{dim}.analysis missing")

    if "overall_comment" not in obj:
        raise ValueError("overall_comment missing")

    # 计算 overall（不信任 LLM 算的）
    scores = {d: obj[d]["score"] for d in DIMENSIONS}
    obj["_overall_score"] = calc_overall(scores)
    return obj


# ---------- 公开入口 ----------

def grade_code(
    *,
    problem_title: str,
    problem_description: str,
    language: str,
    code: str,
    reference_solution: str | None = None,
) -> LLMResult:
    """统一入口：返回 LLMResult。"""
    system = get_system_prompt()
    user = build_user_prompt(
        problem_title=problem_title,
        problem_description=problem_description,
        language=language,
        code=code,
        reference_solution=reference_solution,
    )

    if settings.use_real_llm:
        parsed, raw, latency = _call_openai(system, user)
        model = settings.llm_model
        retries = 0
    else:
        start = time.time()
        parsed = _mock_grade(problem_title, problem_description, language, code, reference_solution)
        raw = json.dumps(parsed, ensure_ascii=False)
        latency = int((time.time() - start) * 1000)
        model = "mock-grader-v1"
        retries = 0

    return LLMResult(
        parsed=parsed,
        raw=raw,
        latency_ms=latency,
        retry_count=retries,
        model=model,
    )
