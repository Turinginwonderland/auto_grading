"""Few-shot 示例（3 条：优秀 / 有 bug / 边界漏处理）。"""
from __future__ import annotations

# 简短示例，作为 user-turn 追加在主 prompt 之后
FEW_SHOT_EXAMPLES = [
    {
        "title": "示例 1：优秀解法（两数之和 — 哈希 O(n)）",
        "problem": "给定整数数组 nums 和目标值 target，返回两个下标使 nums[i]+nums[j]=target。",
        "code": (
            "from typing import List\n"
            "def two_sum(nums: List[int], target: int) -> List[int]:\n"
            "    seen = {}\n"
            "    for i, v in enumerate(nums):\n"
            "        if target - v in seen:\n"
            "            return [seen[target - v], i]\n"
            "        seen[v] = i\n"
            "    return []\n"
        ),
        "output": {
            "thought_summary": "哈希表一次遍历，时间 O(n)，处理了无解返回 [] 的边界。",
            "correctness": {
                "score": 49,
                "analysis": (
                    "第 4-5 行先查后写避免自匹配；第 7 行对无解返回 [] 兜底。"
                    "边界 nums 为空时直接 return []，正确。"
                ),
            },
            "standardization": {
                "score": 28,
                "analysis": (
                    "第 1 行有类型注解，函数命名 snake_case 一致；"
                    "但缺少 docstring（第 2 行）。"
                ),
            },
            "readability": {
                "score": 19,
                "analysis": (
                    "enumerate 同时获取 idx 和 val（第 4 行）意图清晰；"
                    "变量名 seen/num 自解释。"
                ),
            },
            "overall_comment": "实现简洁高效，建议补 docstring。",
        },
    },
    {
        "title": "示例 2：有 bug 的解法（O(n²) 暴力 + 缺少空数组保护）",
        "problem": "给定整数数组 nums 和目标值 target，返回两个下标使 nums[i]+nums[j]=target。",
        "code": (
            "def twoSum(nums, target):\n"
            "    for i in range(len(nums)):\n"
            "        for j in range(i+1, len(nums)):\n"
            "            if nums[i] + nums[j] == target:\n"
            "                return [i, j]\n"
        ),
        "output": {
            "thought_summary": "暴力枚举思路正确，但无解时无返回值，时间复杂度偏高。",
            "correctness": {
                "score": 32,
                "analysis": (
                    "第 2-5 行双重循环思路成立；"
                    "但当 nums 为空时外层不进入循环，函数无 return（第 6 行缺失），"
                    "隐式返回 None，是潜在 bug。"
                ),
            },
            "standardization": {
                "score": 18,
                "analysis": (
                    "函数名 twoSum 是 camelCase，违反 PEP8；"
                    "无类型注解（第 1 行），无 docstring。"
                ),
            },
            "readability": {
                "score": 14,
                "analysis": (
                    "循环嵌套层级合理；"
                    "但命名两套风格混用（twoSum 与常见 snake_case 不一致）。"
                ),
            },
            "overall_comment": "思路对，O(n²) 可接受但建议改哈希；务必补 None 兜底。",
        },
    },
    {
        "title": "示例 3：边界处理不佳（链表去重漏空指针）",
        "problem": "在排序链表中删除重复节点，使每个元素只出现一次。",
        "code": (
            "def deleteDup(head):\n"
            "    cur = head\n"
            "    while cur and cur.next:\n"
            "        if cur.val == cur.next.val:\n"
            "            cur.next = cur.next.next\n"
            "    return head\n"
        ),
        "output": {
            "thought_summary": "遍历思路正确，但漏掉 cur 推进，head 为 None 时 OK 但会死循环。",
            "correctness": {
                "score": 28,
                "analysis": (
                    "第 3-5 行去重逻辑成立；"
                    "但删除重复节点后未推进 cur（第 6 行缺失），"
                    "若出现连续 3 个相同值会陷入死循环，是关键 bug。"
                ),
            },
            "standardization": {
                "score": 15,
                "analysis": (
                    "无类型注解；"
                    "命名 cur/head 偏简，缺 docstring。"
                ),
            },
            "readability": {
                "score": 12,
                "analysis": (
                    "代码较短、结构清晰；"
                    "但变量命名偏单字符，可读性一般。"
                ),
            },
            "overall_comment": "补 else: cur = cur.next 即可解决死循环。",
        },
    },
]


def few_shot_block() -> str:
    """把 few-shot 渲染成可追加到 user prompt 的文本。"""
    parts = []
    for i, ex in enumerate(FEW_SHOT_EXAMPLES, 1):
        parts.append(f"=== 示例 {i}：{ex['title']} ===")
        parts.append(f"[题] {ex['problem']}")
        parts.append(f"[代码]\n{ex['code']}")
        parts.append(f"[期望输出] {_pretty_json(ex['output'])}")
        parts.append("")
    return "\n".join(parts)


def _pretty_json(obj: dict) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
