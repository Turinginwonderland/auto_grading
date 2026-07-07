# Code Grader (Phase 1)

> LLM-as-a-Judge 代码评分器 — 当前阶段：P1.0 基础架子
> 规划文件：[planning_mini.md](./planning_mini.md)

## 当前进度

| 里程碑 | 状态 |
|---|---|
| P1.0 基础架子（FastAPI + DB + grade 接口 + mock rubric） | ✅ |
| P1.1 OCR 题目入库（PDF → 题库 ≥ 30 道） | TODO |
| P1.2 System Prompt v2 + Few-shot + 重试/校验 | ✅（已写） |
| P1.3 评分缓存 + 异步化 | ✅（缓存已写；异步待 P1.3） |
| P1.4 评测集 + 一致性报告 | TODO |

## 快速开始

```bash
# 1. 准备虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. 装依赖
pip install -r requirements.txt

# 3. 复制环境变量模板
cp .env.example .env
# 默认就是 mock 模式，可直接跑

# 4. 启动
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000/docs> 看 Swagger UI。

## 切换到真实 LLM

编辑 `.env`：

```env
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

重启后 `/api/v1/health` 会返回真实模型名；未配置时返回 `mock-grader-v1`。

## API 概览

| Method | Path | 说明 |
|---|---|---|
| GET  | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/problems` | 新增题目 |
| GET  | `/api/v1/problems/{id}` | 题目详情 |
| POST | `/api/v1/grade` | 提交评分（同步，P1.3 会改异步） |
| GET  | `/api/v1/submissions/{id}` | 提交详情 |
| GET  | `/api/v1/submissions?problem_id=&student_id=` | 列表（分页） |

### grade 请求示例

```bash
curl -X POST http://127.0.0.1:8000/api/v1/grade \
  -H "Content-Type: application/json" \
  -d '{
    "problem_id": "ds-ch02-ex01",
    "code": "def add(a, b):\n    return a + b\n",
    "language": "python"
  }'
```

返回：

```json
{
  "submission_id": "uuid",
  "problem_id": "ds-ch02-ex01",
  "overall_score": 78.5,
  "dimensions": {
    "correctness":     {"score": 40, "weight": 0.5, "max_score": 50, "analysis": "..."},
    "standardization": {"score": 22, "weight": 0.3, "max_score": 30, "analysis": "..."},
    "readability":     {"score": 16, "weight": 0.2, "max_score": 20, "analysis": "..."}
  },
  "llm_comment": "...",
  "llm_model": "mock-grader-v1",
  "status": "success",
  "cached": false
}
```

## 评分维度（rubric）

| 维度 | 满分 | 权重 | 关键锚点 |
|---|---|---|---|
| 正确性 correctness     | 50 | 50% | 边界覆盖 / 关键路径 / 框架 |
| 规范性 standardization | 30 | 30% | 类型注解 / docstring / 错误处理 |
| 可读性 readability     | 20 | 20% | 命名 / 层级 / 注释 |

详见 `app/prompts/rubric.py`。

## 目录结构

```
auto_grading/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── core/                   # config / logging
│   ├── api/v1/                 # grade / problems / health
│   ├── models/                 # SQLAlchemy ORM
│   ├── schemas/                # Pydantic
│   ├── services/               # grading / llm / cache / prompt_builder
│   ├── prompts/                # system / rubric / few_shot
│   ├── db/                     # database
│   └── utils/                  # code_hash
├── tests/                      # unit / eval
├── scripts/                    # seed / run_eval
├── data/                       # 题源 PDF + sqlite db
├── requirements.txt
└── .env.example
```

## 跑测试

```bash
pytest -q
```

## 下一步

- **P1.1**：基于 `27王道《数据结构》高清带书签.pdf` 跑 OCR 流水线，入库 ≥ 30 道题
- **P1.3**：把 `grade_submission` 改异步，前端拿 submission_id 轮询
- **P1.4**：建 20-30 条带标注的评测集，统计吻合率（< 80% 不许过 P1）
