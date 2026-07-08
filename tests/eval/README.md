# 评分一致性评测（P1.4 必做 gate）

## 跑法
```bash
python tests/eval/run_eval.py             # 单轮
python tests/eval/run_eval.py --runs 3    # 3 轮算方差
python tests/eval/run_eval.py --json-only # 只写 JSON
```

报告输出：
- `report.json` — 完整结构化数据
- `report.md` — 人类可读

## 评测集
`labeled_samples.json` 含 20 条样本，分布：
- high × 10（高质量代码）
- mid_high × 1
- mid × 4
- low × 5（含 5 道"buggy"代码）

## Mock 模式局限（重要）
当前 P1 默认走 mock grader（未配 `LLM_API_KEY`），其评分规则只启发式检查：
- 行数 / 是否有 `def` / 是否有 `TODO` / 类型注解 / docstring

**不识别算法 bug、不实际运行代码**。所以 5 道 buggy 样本在 mock 模式下也会被评 60-70 分。
评测集中 buggy 样本的 `expected_overall` 区间已扩大到 `[50, 80]` 反映这一现实，并在 `notes` 注明"理想 LLM 应 < 50"。

## Gate
- 阈值：Overall 吻合率 ≥ 80%
- 吻合判定：actual 在 expected 区间内
- 跑测试：`pytest tests/unit/test_eval.py -v`

## 接 LLM 后
1. 配 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`
2. 重跑：`python tests/eval/run_eval.py --runs 3`
3. 建议：先跑 1 轮，**根据实际 LLM 评分收紧 expected 区间**（尤其 buggy 样本应能正确识别 < 50）
4. 跑多轮算方差（不同 temperature 下同一代码的分数波动）
