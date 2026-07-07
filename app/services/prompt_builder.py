"""Prompt 拼装：System + User 组合。"""
from __future__ import annotations

from app.prompts.few_shot import few_shot_block
from app.prompts.system_prompt import build_system_prompt


def build_user_prompt(
    problem_title: str,
    problem_description: str,
    language: str,
    code: str,
    reference_solution: str | None = None,
) -> str:
    parts = [
        f"## 题目：{problem_title}",
        "",
        "### 题目描述",
        problem_description.strip(),
        "",
        f"### 提交语言：{language}",
        "",
        "### 提交代码",
        "```" + language,
        code.strip(),
        "```",
    ]
    if reference_solution:
        parts += [
            "",
            "### 参考答案（仅作对照，不要直接据此给分）",
            "```" + language,
            reference_solution.strip(),
            "```",
        ]
    parts += [
        "",
        "---",
        "下面是若干带标注的示例，请参考其评分粒度与表达方式：",
        "",
        few_shot_block(),
        "",
        "请开始按 Layer 2 的流程评估，并按 Layer 4 输出严格 JSON。",
    ]
    return "\n".join(parts)


def get_system_prompt() -> str:
    return build_system_prompt()
