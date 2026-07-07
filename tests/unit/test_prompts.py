"""system_prompt / few_shot 单元测试。"""
from app.prompts.few_shot import FEW_SHOT_EXAMPLES, few_shot_block
from app.prompts.system_prompt import build_system_prompt
from app.prompts.rubric import DIMENSIONS


def test_system_prompt_contains_all_layers():
    sp = build_system_prompt()
    assert "Layer 1" in sp
    assert "Layer 2" in sp
    assert "Layer 3" in sp
    assert "Layer 4" in sp
    for d in DIMENSIONS:
        assert d in sp


def test_few_shot_examples_have_required_fields():
    assert len(FEW_SHOT_EXAMPLES) >= 3
    for ex in FEW_SHOT_EXAMPLES:
        out = ex["output"]
        assert "thought_summary" in out
        for d in DIMENSIONS:
            assert d in out
            assert "score" in out[d]
            assert "analysis" in out[d]
            assert 0 <= out[d]["score"] <= {"correctness": 50, "standardization": 30, "readability": 20}[d]
        assert "overall_comment" in out


def test_few_shot_block_renders():
    blk = few_shot_block()
    assert "示例 1" in blk
    assert "示例 2" in blk
    assert "示例 3" in blk
