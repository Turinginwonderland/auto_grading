# 代码评分器 — 第一阶段规划（v2 / 完整版）

> 项目：Code Grader
> 阶段：Phase 1 — 大模型 API 评测版（LLM-as-a-Judge）
> 技术栈：Python 3.11+ · FastAPI · SQLAlchemy · SQLite/PostgreSQL
> 题目数据源：《27王道 数据结构》PDF（需 OCR 入库）
> 目标：稳定、可复现、防止幻觉的代码多维度评分

---

## 0. 三个用户原文里"自相矛盾"的处理决定

| 矛盾点 | 决定 | 理由 |
|---|---|---|
| 维度名称 1：可读性 20% / 逻辑正确性 50% / 规范性 30% | ✅ **采用这一组** | 你在主问题里点名了权重，给出了总和 100%，最具体 |
| 维度名称 2：规范、逻辑、**性能** | ❌ 性能维度放 Phase 2 | 性能需要跑测试用例 + benchmark，依赖沙箱；第一阶段纯 LLM 评分无法客观给"性能分" |
| LLM 选型 | 提供**多模型可切换**配置（gpt-4o / deepseek-chat / claude-sonnet-4-6 等 OpenAI 兼容协议） | 第一阶段不锁死单一供应商，方便后期对比 |

---

## 1. 题目入库链路：PDF → OCR → 结构化 JSON → DB  ⚠️ 原 plan 缺失

> 你的题目源是《27王道 数据结构》PDF，里面有题目描述、示例、图示。要让 LLM 评分，必须先有结构化题目数据。**OCR 是这一阶段的前置基建**。

### 1.1 处理流水线

```
27王道数据结构.pdf
    ↓
[Step 1] PDF 拆页（按章节书签）           ← PyMuPDF / pdfplumber
    ↓
[Step 2] 文本层提取 + 扫描页 OCR           ← Tesseract（中文） / PaddleOCR / 阿里云 OCR
    ↓
[Step 3] LLM 题目结构化                     ← Claude / GPT 把非结构化文本 → JSON
    ↓
[Step 4] 人工抽检（10% 抽样）              ← 兜底，避免 OCR+LLM 双重幻觉
    ↓
[Step 5] 入库 problems 表
```

### 1.2 OCR 选型建议

| 方案 | 优点 | 缺点 | 推荐度 |
|---|---|---|---|
| PaddleOCR（本地） | 免费、中文准、可离线 | 需要 GPU/CPU 资源、自己处理版式 | ⭐⭐⭐⭐⭐ |
| Tesseract + chi_sim | 轻量、跨平台 | 中文效果一般、对复杂版式差 | ⭐⭐ |
| 阿里云 / 腾讯云 OCR API | 准、有版面还原 | 收费、需联网 | ⭐⭐⭐⭐ |
| GPT-4V / Claude 3.5 Vision 直接看 PDF | 一步到位，**含图示也能识别** | 贵、慢 | ⭐⭐⭐（小批量可用） |

**推荐：PaddleOCR 为主 + GPT-4V 兜底含图的题目**。第一阶段不要求全自动化，先做半自动流水线（OCR → LLM 结构化 → 人工抽样确认）。

### 1.3 入库题目数据契约（problems 表 / problem.json）

```json
{
  "problem_id": "ds-2024-ch02-ex07",
  "source": {"book": "27王道数据结构", "chapter": "线性表", "page": 42},
  "title": "删除链表中重复的节点",
  "difficulty": "medium",
  "description": "在一个排序的链表中，删除重复的节点...",
  "input_format": "链表头节点指针",
  "output_format": "去重后的链表头节点",
  "examples": [
    {"input": "1->2->3->3->4->4->5", "output": "1->2->5"}
  ],
  "constraints": "链表长度 0 <= n <= 10^4",
  "reference_solution": "def deleteDuplicates(head): ...",
  "test_cases": [
    {"input": "...", "expected": "..."}
  ],
  "scoring_rules": {
    "correctness_weight": 0.5,
    "standardization_weight": 0.3,
    "readability_weight": 0.2
  },
  "created_at": "..."
}
```

---

## 2. 数据库 Schema（SQLAlchemy ORM）

```python
# problems 题目表
class Problem(Base):
    __tablename__ = "problems"
    problem_id: str           # PK, 例 "ds-ch02-ex07"
    title: str
    description: str          # 题目描述（Markdown）
    difficulty: str           # easy/medium/hard
    input_format: str | None
    output_format: str | None
    examples_json: str        # JSON 字符串
    constraints: str | None
    reference_solution: str   # 参考答案代码
    test_cases_json: str      # JSON 字符串
    scoring_rules_json: str   # JSON 字符串
    source_book: str | None   # 来源教材
    source_chapter: str | None
    source_page: int | None
    ocr_raw: str | None       # OCR 原始文本（用于审计）
    created_at: datetime
    updated_at: datetime

# submissions 提交记录表
class Submission(Base):
    __tablename__ = "submissions"
    submission_id: str        # PK, UUID
    problem_id: str           # FK -> problems
    student_id: str | None    # 可选，鉴权后填写
    code: str                 # 提交的源码
    language: str             # python / java / cpp / go
    status: str               # pending / success / failed
    overall_score: float | None
    dimension_scores_json: str | None  # {"correctness": 42, "standardization": 25, "readability": 18}
    llm_comment: str | None
    llm_raw_output: str | None         # 原始 LLM 输出（调试用）
    llm_model: str | None              # 用的哪个模型
    llm_latency_ms: int | None
    retry_count: int = 0
    error_message: str | None
    created_at: datetime
```

**为什么存 `llm_raw_output` 和 `ocr_raw`？**——为了**可复现、可审计**。评分这种事出问题一定要能查原始输入输出，不能只看最终分数。

---

## 3. API 接口契约

### 3.1 提交评分 `POST /api/v1/grade`

**Request**:
```json
{
  "problem_id": "ds-ch02-ex07",
  "code": "def deleteDuplicates(head): ...",
  "language": "python",
  "student_id": "optional-user-id"
}
```

**Response — 200**:
```json
{
  "submission_id": "uuid",
  "problem_id": "ds-ch02-ex07",
  "overall_score": 85.5,
  "dimensions": {
    "correctness":     {"score": 42, "weight": 0.5, "max_score": 50, "analysis": "..."},
    "standardization": {"score": 25, "weight": 0.3, "max_score": 30, "analysis": "..."},
    "readability":     {"score": 18, "weight": 0.2, "max_score": 20, "analysis": "..."}
  },
  "llm_comment": "整体质量较好...",
  "llm_model": "gpt-4o",
  "created_at": "2026-07-06T10:30:00Z"
}
```

**Response — 422**（输入校验失败）/ 500（LLM 多次重试仍失败）。

### 3.2 其他端点

| Method | Path | 说明 |
|---|---|---|
| `POST` | `/api/v1/grade` | 提交评分 |
| `GET`  | `/api/v1/submissions/{id}` | 查询提交详情 |
| `GET`  | `/api/v1/submissions?problem_id=&student_id=` | 列表查询（分页） |
| `POST` | `/api/v1/problems` | 新增题目（含 OCR 原始文本） |
| `GET`  | `/api/v1/problems/{id}` | 题目详情 |
| `GET`  | `/api/v1/health` | 健康检查 |

---

## 4. 数据流（含 OCR 链路与缓存）

```
┌──────────────────────────────────────────────────────────┐
│  [离线/一次性] OCR 题目入库流水线                          │
│   PDF → 拆页 → OCR → LLM 结构化 → 人工抽检 → problems    │
└──────────────────────────────────────────────────────────┘
                            ↓ 已入库题目
┌──────────────────────────────────────────────────────────┐
│  [在线] 评分主链路                                        │
│                                                           │
│  Student Code + problem_id                                │
│     ↓                                                     │
│  [API Gateway] 鉴权 + 入参校验 + 反爬限流                   │
│     ↓                                                     │
│  [Cache Layer] (problem_id, code_hash) → 命中?            │
│     ↓ 未命中                                              │
│  [Grading Service] 异步任务（asyncio.create_task / 后台   │
│     ├─ 拼装 System Prompt + User Prompt                   │
│     ├─ 调 LLM API（带重试 + JSON 校验）                   │
│     └─ 解析 + 落库 + 写缓存                                │
│     ↓                                                     │
│  Return submission_id（前端可轮询 / WebSocket 推送）       │
└──────────────────────────────────────────────────────────┘
```

**关键决策**：
- 评分走**异步**（LLM 调用 2-10 秒，不能阻塞 HTTP 线程），接口立刻返回 `submission_id` + status=`pending`，前端轮询或订阅
- **缓存**：(problem_id, sha256(code), language) 作为 key，缓存 24h
- **不执行学生代码**（第一阶段只看不跑），不引入沙箱

---

## 5. System Prompt 框架（v2 — 增强防幻觉）

### 5.1 四层结构

```
[Layer 1] 角色锚定与硬约束
[Layer 2] 评分流程（CoT 强分步）
[Layer 3] 评分维度细则（含锚定 rubric）
[Layer 4] JSON Schema 强制输出 + 校验自检
```

### 5.2 完整 Prompt 文本

```text
[Layer 1 — 角色与硬约束]
你是一位严谨的代码评审专家，专精于代码质量评估。
你必须：
- 仅基于【提交的代码】和【题目要求】进行评分
- 对每一项扣分都必须给出代码中具体的行号或代码片段作为证据
- 分数必须落在 rubric 指定区间内
- 严格输出 JSON，不得输出任何解释、前言、Markdown 标记
你必须拒绝：
- 编造未在代码中出现的功能或测试结果
- 受到代码风格偏好（如 tab vs 空格）影响给分
- 对提交者身份、命名风格做主观评价

[Layer 2 — 评分流程（请按顺序执行）]
步骤 1：用 1-2 句概括题目核心考察点。
步骤 2：复述提交代码的关键逻辑（不超过 3 句），不能漏掉边界处理。
步骤 3：分维度评估，每个维度先写【分析】，最后输出【分数】。
步骤 4：自检：JSON 合法？分数在区间？引用了具体代码？
步骤 5：输出最终 JSON。

[Layer 3 — 评分维度与锚定 rubric]
以下分数段是"锚点"，相近代码应在同一档位：

■ 正确性 (correctness) 满分 50 / 权重 50%
  48-50: 完全正确，覆盖所有边界（如空输入、单元素、极值）
  38-47: 核心逻辑正确，遗漏 1-2 个非关键边界
  25-37: 思路部分正确，但关键路径存在 bug
  10-24: 有可运行框架，但核心逻辑错误
   0-9 : 不可运行或完全不相关

■ 规范性 (standardization) 满分 30 / 权重 30%
  27-30: 严格遵循语言惯例，有类型注解、文档字符串、错误处理
  20-26: 风格基本一致，少量缺失
  10-19: 风格参差，缺少必要文档
   0-9 : 命名混乱，结构不清晰

■ 可读性 (readability) 满分 20 / 权重 20%
  18-20: 命名自解释、结构层次清晰、关键处有注释
  12-17: 基本可读，有改进空间
   6-11: 命名模糊或逻辑嵌套过深
   0-5 : 难以理解

[Layer 4 — JSON Schema 强约束]
你的最终输出必须严格是以下 JSON 对象，不要包裹在 ```json 中：
{
  "thought_summary": "<string, 步骤1+步骤2的简要概括, 不超过 80 字>",
  "correctness":     {"score": <int 0-50>, "analysis": "<string, 引用具体代码行/片段>"},
  "standardization": {"score": <int 0-30>, "analysis": "<string, 引用具体行/片段>"},
  "readability":     {"score": <int 0-20>, "analysis": "<string, 引用具体行/片段>"},
  "overall_comment": "<string, 总结性建议, 100 字以内>"
}

自检 checklist（输出前默默核对）：
- [ ] 四个维度字段都齐全
- [ ] score 是整数且在区间
- [ ] 每个 analysis 至少包含 1 处具体代码引用（行号或代码片段）
- [ ] 没有 ```json 包裹，没有多余文字
```

### 5.3 防幻觉的关键手段（不只是 prompt）

| 手段 | 说明 |
|---|---|
| **Rubric 锚点** | 给出"参照档"而非开放式评分，减少 LLM 自创标准 |
| **强制代码引用** | 每个 analysis 必须引用具体行/片段，引用不到 = 该点不能给分 |
| **JSON Schema 校验** | 后端用 Pydantic 二次解析，失败则重试 |
| **低温度** | `temperature=0.0` 起步 |
| **Few-shot** | 准备 3 个标注好的示例（含正例/反例/边界） |
| **重试策略** | JSON 解析失败 / 分数越界 → 重试 2 次，仍失败则标 `status=failed` |

### 5.4 Few-shot 示例（节选）

```text
=== 示例 1：优秀 ===
[题] 两数之和
[代码] def two_sum(nums, target): seen={}; ... (哈希 O(n) 解法)
[输出] {"correctness":{"score":50,"analysis":"第 3 行使用哈希表...正确处理了无解返回 [] (第 6 行)"},
        "standardization":{"score":28,"analysis":"函数名 snake_case，但缺少类型注解 (第 1 行)"},
        "readability":{"score":19,"analysis":"enumerate 同时获取 idx 和 val (第 3 行)，意图清晰"},
        "overall_comment":"...","thought_summary":"..."}

=== 示例 2：有 bug ===
[代码] def twoSum(nums, target): for i in range(len(nums)): for j... (O(n²))
[输出] {"correctness":{"score":35,"analysis":"第 2-3 行暴力枚举思路正确，但缺空数组保护 (nums 为空时 i=0 不会进入内层循环，返回 [] 反而偶然正确)"},
        ...}
```

---

## 6. LLM 调用配置

| 参数 | 值 | 备注 |
|---|---|---|
| `model` | `gpt-4o` / `deepseek-chat` / `claude-sonnet-4-6` | 通过环境变量切换 |
| `temperature` | `0.0` | 极致稳定 |
| `response_format` | `{type: "json_object"}` | OpenAI 兼容接口 |
| `max_tokens` | `1500` | 够用即可 |
| `timeout` | `30s` | 防止卡死 |
| `retry` | `2` 次（指数退避） | 仅在 JSON 解析失败时重试 |
| **缓存** | `(problem_id, sha256(code))` 为 key，TTL 24h | 避免重复烧钱 |

---

## 7. 项目目录结构

```
code-grader/
├── app/
│   ├── main.py                       # FastAPI 入口，挂载路由
│   ├── core/
│   │   ├── config.py                 # pydantic-settings 读取 .env
│   │   ├── security.py               # API key / 简单鉴权
│   │   └── logging.py                # 结构化日志
│   ├── api/v1/
│   │   ├── grade.py                  # POST /grade, GET /submissions
│   │   ├── problems.py               # CRUD /problems
│   │   └── health.py
│   ├── models/                       # SQLAlchemy ORM
│   │   ├── problem.py
│   │   └── submission.py
│   ├── schemas/                      # Pydantic 请求/响应
│   │   ├── grade.py
│   │   ├── problem.py
│   │   └── submission.py
│   ├── services/
│   │   ├── grading_service.py        # 评分编排（异步）
│   │   ├── llm_service.py            # LLM 调用 + 重试 + JSON 校验
│   │   ├── prompt_builder.py         # System + User Prompt 拼装
│   │   └── cache.py                  # 评分缓存
│   ├── prompts/
│   │   ├── system_prompt.py          # System Prompt 文本
│   │   ├── rubric.py                 # 评分锚点（Python dict）
│   │   └── few_shot.py               # 标注好的示例
│   ├── db/
│   │   ├── database.py
│   │   └── migrations/               # alembic
│   └── utils/
│       ├── code_hash.py
│       └── retry.py
├── ingestion/                        # ⚠️ 离线 OCR 流水线
│   ├── pdf_splitter.py               # PyMuPDF 按章节拆
│   ├── ocr_runner.py                 # PaddleOCR 封装
│   ├── llm_structurer.py             # OCR 文本 → JSON
│   └── human_review.csv              # 人工抽检结果
├── tests/
│   ├── unit/                         # 单测：services / schemas
│   ├── integration/                  # 集成测：API 端到端
│   └── eval/                         # ⚠️ 评分一致性评测集
│       └── labeled_samples.json      # 人工标好的 20-30 个代码 + 期望分数段
├── scripts/
│   ├── seed_problems.py              # 批量导入题目
│   └── run_eval.py                   # 跑评分一致性评测
├── data/
│   └── 27王道数据结构.pdf            # 题源
├── requirements.txt
├── .env.example
├── alembic.ini
└── README.md
```

### 7.1 核心依赖（requirements.txt）

```text
# Web
fastapi>=0.110
uvicorn[standard]>=0.27

# 数据
sqlalchemy>=2.0
alembic>=1.13
pydantic>=2.5
pydantic-settings>=2.1

# LLM
openai>=1.30                # 兼容 OpenAI 协议（也支持 deepseek/通义/Claude via gateway）
tenacity>=8.2               # 重试

# 缓存（轻量起步，后续可换 redis）
cachetools>=5.3             # 进程内 LRU；后续可换 redis

# 异步任务（轻量起步，后续可换 celery/rq）
apscheduler>=3.10           # 或直接用 asyncio.create_task

# 日志 / 工具
loguru>=0.7
python-dotenv>=1.0
httpx>=0.27

# 测试
pytest>=8.0
pytest-asyncio>=0.23

# OCR 流水线（可选，按需安装）
pymupdf>=1.24
paddleocr>=2.7
```

> **暂不引入 langchain**。第一阶段 LLM 调用只是拼字符串+调 API，langchain 抽象带来的复杂度 > 收益。等真正需要 prompt template 复用、agent 链路再考虑。

---

## 8. 评分一致性评测（第一阶段必做）

LLM-as-a-Judge 的最大风险是**评分不稳定**。必须在第一阶段建立评测集：

```python
# tests/eval/run_eval.py 伪代码
1. 准备 labeled_samples.json: 20-30 个 (problem, code, expected_score_range)
2. 跑 N 次（不同 temperature 或不同模型）→ 统计：
   - 同一代码多次评分的方差
   - 与人工标注分段的吻合率
3. 吻合率 < 80% → 调整 rubric / 调 Few-shot / 换模型
```

这是**进入 Phase 2 之前必须通过的 gate**。

---

## 9. 错误处理与边界

| 场景 | 处理 |
|---|---|
| 输入缺 problem_id / code 为空 | 422 Pydantic 校验 |
| problem_id 不存在 | 404 |
| LLM 返回非 JSON | 重试 2 次 → 仍失败则 `status=failed` + 记录 `llm_raw_output` |
| LLM 返回 score 越界 | 同上重试 |
| LLM 超时（>30s） | 取消 + 记录 + 返回 504 |
| 同一 submission 重复提交 | 走缓存，返回旧结果 |
| 代码超长（>50KB） | 截断 + 在 prompt 中提示"已截断" |

---

## 10. 阶段规划与里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| **P1.0** | 基础架子（FastAPI + DB + 单条 grade 接口 + 写死 rubric） | ✅ 2026-07-07 |
| **P1.1** | OCR 流水线（PDF → 题目库），至少入库 30 道题 | ✅ 2026-07-07 |
| **P1.2** | System Prompt v2 + Few-shot + 重试/校验 | ✅ 2026-07-07 |
| **P1.3** | 评分缓存 + 异步化 | ✅ 2026-07-08 |
| **P1.4** | 评测集 + 一致性报告 | ✅ 2026-07-08（mock 100% 吻合，gate PASS） |
| **P2.0** | 沙箱原型（subprocess + timeout + Python） | ✅ 2026-07-08（65 测试全过，feature/p2-sandbox） |
| **P2.x** | 沙箱硬化（RLIMIT + Windows 降级） | ✅ 2026-07-08（68 测试，3 POSIX-only skip） |
| **P2.1 (后续)** | 性能维度（拆 correctness → correctness+performance） | 待开 |
| **P2.y (后续)** | Docker 化 sandbox（接口不变） | 待开 |

---

## 11. 一句话总结

**Phase 1 = OCR 入题库 + 异步 LLM-as-a-Judge + 缓存/重试/JSON 校验兜底 + 一致性评测集**，确保第一阶段交付的是一个**稳定、可复现、可审计**的代码评分 API。
