"""评分锚点 rubric（Python dict），可被 Prompt 引用也可被 Python 校验。"""
from __future__ import annotations

# 三个维度的满分与权重（合计 100）
RUBRIC = {
    "correctness": {
        "max_score": 50,
        "weight": 0.50,
        "anchors": [
            (48, 50, "完全正确，覆盖所有边界（空输入、单元素、极值）"),
            (38, 47, "核心逻辑正确，遗漏 1-2 个非关键边界"),
            (25, 37, "思路部分正确，但关键路径存在 bug"),
            (10, 24, "有可运行框架，但核心逻辑错误"),
            (0, 9, "不可运行或完全不相关"),
        ],
    },
    "standardization": {
        "max_score": 30,
        "weight": 0.30,
        "anchors": [
            (27, 30, "严格遵循语言惯例，有类型注解、文档字符串、错误处理"),
            (20, 26, "风格基本一致，少量缺失"),
            (10, 19, "风格参差，缺少必要文档"),
            (0, 9, "命名混乱，结构不清晰"),
        ],
    },
    "readability": {
        "max_score": 20,
        "weight": 0.20,
        "anchors": [
            (18, 20, "命名自解释、结构层次清晰、关键处有注释"),
            (12, 17, "基本可读，有改进空间"),
            (6, 11, "命名模糊或逻辑嵌套过深"),
            (0, 5, "难以理解"),
        ],
    },
}

DIMENSIONS = ("correctness", "standardization", "readability")


def validate_score(dim: str, score: int) -> bool:
    """判断某维度分数是否在合法区间内。"""
    if dim not in RUBRIC:
        return False
    return 0 <= score <= RUBRIC[dim]["max_score"]


def calc_overall(scores: dict[str, int]) -> float:
    """总分 = 各维度分数直接相加（满分 100）。

    与规划文档一致：correctness 50 + standardization 30 + readability 20 = 100。
    """
    total = 0.0
    for dim, s in scores.items():
        if dim not in RUBRIC:
            raise KeyError(f"unknown dimension: {dim}")
        if not (0 <= s <= RUBRIC[dim]["max_score"]):
            raise ValueError(f"{dim}.score out of range: {s}")
        total += s
    return round(total, 2)
