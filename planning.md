# 代码评分器 — 第一阶段规划

> 项目：代码评分器 (Code Grader)
> 阶段：Phase 1 — 大模型 API 评测版
> 技术栈：Python + FastAPI
> 参考架构：LLM-as-a-Judge

---

## 一、API 接口 JSON 契约

### 1.1 提交评分 `POST /api/v1/grade`

**Request**:
```json
{
  "problem_id": "uuid-string",
  "code": "def two_sum(nums, target):\n    for i in range(len(nums)):\n        for j in range(i+1, len(nums)):\n            if nums[i] + nums[j] == target:\n                return [i, j]",
  "language": "python"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `problem_id` | string (uuid) | 题目唯一标识 |
| `code` | string | 学生提交的源代码 |
| `language` | string | 编程语言（python / java / cpp / go 等） |

**Response — 成功 (200)**:
```json
{
  "submission_id": "uuid-string",
  "problem_id": "uuid-string",
  "language": "python",
  "overall_score": 85.5,
  "dimensions": {
    "correctness": {
      "score": 42,
      "weight": 0.5,
      "max_score": 50,
      "analysis": "核心逻辑正确，能通过基本的测试用例。但在空数组输入时处理不够健壮，缺少边界条件检查。"
    },
    "standardization": {
      "score": 25,
      "weight": 0.3,
      "max_score": 30,
      "analysis": "代码遵循了 PEP8 规范，命名风格一致。但函数缺少类型注解，docstring 缺失。"
    },
    "readability": {
      "score": 18,
      "weight": 0.2,
      "max_score": 20,
      "analysis": "变量命名清晰，逻辑结构直观。嵌套循环的可读性一般，建议提取为辅助函数。"
    }
  },
  "llm_comment": "整体质量较好，核心功能正确。建议补充边界测试、添加类型注解和注释以提升规范性。",
  "test_results": {
    "passed": 4,
    "failed": 1,
    "error": null
  },
  "created_at": "2026-07-06T10:30:00Z"
}
```

### 1.2 查询提交记录 `GET /api/v1/submissions/{submission_id}`

**Response**:
```json
{
  "submission_id": "uuid-string",
  "problem_id": "uuid-string",
  "code": "...",
  "language": "python",
  "overall_score": 85.5,
  "dimensions": { /* 同上结构 */ },
  "llm_comment": "...",
  "test_results": { "passed": 4, "failed": 1, "error": null },
  "created_at": "2026-07-06T10:30:00Z"
}
```

### 1.3 创建题目 `POST /api/v1/problems`

**Request**:
```json
{
  "title": "两数之和",
  "description": "给定一个整数数组 nums 和一个整数目标值 target...",
  "difficulty": "easy",
  "test_cases": [
    {
      "input": "nums = [2,7,11,15], target = 9",
      "expected_output": "[0,1]"
    }
  ],
  "reference_solution": "def two_sum(nums, target):\n    ...",
  "scoring_rules": {
    "correctness_weight": 0.5,
    "standardization_weight": 0.3,
    "readability_weight": 0.2
  }
}
```

**Response**:
```json
{
  "problem_id": "uuid-string",
  "title": "两数之和",
  "difficulty": "easy",
  "created_at": "2026-07-06T10:30:00Z"
}
```

---

## 二、System Prompt 核心文本

### Layer 1 — 角色锚定（边界设定）

```
你是一位专业的代码评分专家。你的职责是对用户提交的代码进行多维度评分。
你需要保持客观、一致、公正，不受提交者身份或代码风格偏好的影响。
你只对代码本身评分，不评价提交者的能力或意图。
```

### Layer 2 — 评分流程与维度细则（CoT 强制分步推理）

```
评分流程——请务必严格按以下步骤执行：

【步骤1】阅读题目要求，列出该题目的关键考察点（如算法正确性、边界处理、时间/空间复杂度）。
【步骤2】分析提交代码的逻辑结构，对比题目要求的正确性。
【步骤3】依照以下三个维度分别评分，每个维度先写出分析文字，再给出具体分数。
【步骤4】按权重汇总得出总分。

========== 评分维度 ==========

维度一：逻辑正确性（满分 50 分，权重 50%）
  - 45-50 分：逻辑完全正确，通过了所有可见和隐含的测试用例，边界条件处理完善
  - 35-44 分：核心逻辑正确，通过了主要测试用例，但存在少量边缘情况或边界条件遗漏
  - 20-34 分：部分逻辑正确，有可运行的代码框架但在关键路径上存在明显错误
  - 0-19 分：逻辑基本不可用，或代码无法通过任何基础测试

维度二：规范性（满分 30 分，权重 30%）
  - 25-30 分：严格遵守语言最佳实践（命名规范、模块化设计、有类型注解/docstring）
  - 15-24 分：基本遵循规范，存在一些风格不一致或遗漏（如缺少部分注释）
  - 0-14 分：缺乏规范的代码结构，命名随意，缺少必要的文档说明

维度三：可读性（满分 20 分，权重 20%）
  - 15-20 分：代码清晰易懂，结构层次分明，变量/函数命名自解释，注释恰到好处
  - 8-14 分：代码基本可读但存在改进空间（如命名含义模糊、缺少关键注释、函数过长）
  - 0-7 分：代码难以理解，缺乏注释，命名混乱或逻辑过于复杂

========== 评分约束 ==========
- 每个维度的分析文字必须在前，分数在后
- 分析文字必须引用代码中的具体行或具体结构作为证据
- 禁止在分析文字中编造代码没有的特性（如幻觉出测试结果）
- 分析文字中不要直接给出分数提示——分数只出现在最后的 JSON 中
```

### Layer 3 — 输出格式强制（JSON Schema 约束）

```
========== 输出格式 ==========
你的输出必须是一个符合 JSON 格式的对象，严格遵循以下 schema：

{
  "correctness": {
    "score": <整数, 0-50>,
    "analysis": "<字符串，引用具体代码行说明逻辑正确或错误的原因>"
  },
  "standardization": {
    "score": <整数, 0-30>,
    "analysis": "<字符串，说明规范性的评分理由>"
  },
  "readability": {
    "score": <整数, 0-20>,
    "analysis": "<字符串，说明可读性的评分理由>"
  },
  "overall_comment": "<字符串，对代码的总体评价和改进建议>"
}

约束：
1. 每个维度的 score 必须在指定范围内，超出范围视为无效
2. analysis 必须至少包含一个具体代码引用
3. 不要输出除 JSON 外的任何内容（包括 markdown 代码块包围）
4. JSON 必须合法，不可缺失字段
```

### Few-shot 示例

```
=== 示例1：优秀代码 ===
题目：两数之和
提交代码：
def two_sum(nums, target):
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []

正确输出：
{
  "correctness": { "score": 50, "analysis": "使用哈希表一次性遍历，时间复杂度O(n)...正确处理了无解情况返回空列表..." },
  "standardization": { "score": 28, "analysis": "变量命名语义明确(seen/complement)，函数名符合snake_case...缺少类型注解..." },
  "readability": { "score": 19, "analysis": "逻辑清晰，enumerate同时获取索引和值...哈希表查找意图一目了然..." },
  "overall_comment": "高效的O(n)解法，代码优雅。建议补充类型注解和docstring。"
}

=== 示例2：需改进代码 ===
题目：两数之和
提交代码：
def twoSum(nums, target):
    for i in range(len(nums)):
        for j in range(i+1, len(nums)):
            if nums[j] == target - nums[i]:
                return [i, j]
    return []

正确输出：
{
  "correctness": { "score": 42, "analysis": "暴力枚举逻辑正确，能通过基本测试...但O(n²)时间复杂度在大数据量下性能不足..." },
  "standardization": { "score": 25, "analysis": "命名风格大体一致但函数名使用了camelCase而非snake_case..." },
  "readability": { "score": 16, "analysis": "逻辑直观容易理解...嵌套循环代码块建议提取为辅助函数..." },
  "overall_comment": "功能正确，但可以优化时间复杂度和代码风格。建议改为哈希表解法。"
}
```

---

## 三、API 调用配置

| 参数 | 值 | 说明 |
|------|-----|------|
| model | `gpt-4o` / `deepseek-chat` / `claude-sonnet-4-6` | 选一个支持 json 模式的模型 |
| temperature | `0.0` ~ `0.1` | 极低温度保证一致性 |
| response_format | `{ "type": "json_object" }` | 仅 OpenAI 兼容接口支持 |
| max_tokens | `2048` | 充足但不过量 |
| system prompt | 上述三层文本拼接 | 作为 system message 发送 |
| user prompt | 题目描述 + 提交代码 | 作为 user message 发送 |

---

## 四、数据流设计

```
Student Code → POST /api/v1/grade
    ↓
[API Layer] 校验输入，从 DB 取出题目
    ↓
[Grading Service] 编排评分流程：
    ├─ [路径A] Docker 沙箱运行代码 → 客观测试结果（可选，Phase 2 强化）
    └─ [路径B] LLM Service
         ├─ 拼接 System Prompt + User Prompt
         ├─ 调用 LLM API (temperature=0.1)
         └─ 解析并校验 JSON 输出
    ↓
[结果聚合] LLM 维度分 + 客观测试通过率 → 加权总分
    ↓
[持久化] 写入 submissions / scores 表
    ↓
Return GradeResponse JSON
```

---

## 五、项目目录结构（建议骨架）

```
code-grader/
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── api/v1/
│   │   ├── grade.py                # POST /api/v1/grade
│   │   ├── problems.py             # CRUD /api/v1/problems
│   │   └── submissions.py          # GET /api/v1/submissions
│   ├── core/
│   │   ├── config.py               # 环境变量配置
│   │   └── dependencies.py         # 依赖注入
│   ├── models/                     # SQLAlchemy ORM 模型
│   ├── schemas/                    # Pydantic 请求/响应模型
│   ├── services/
│   │   ├── grading_service.py      # 评分主逻辑编排
│   │   └── llm_service.py          # LLM API 调用封装
│   ├── prompts/
│   │   ├── system_prompt.py        # System Prompt 模板
│   │   └── few_shot.py             # Few-shot 示例
│   └── db/
│       ├── database.py             # 数据库连接
│       └── seed.py                 # 初始数据
├── tests/
├── sandbox/                        # [Phase 2] 代码执行沙箱
├── requirements.txt
├── .env.example
└── README.md
```

**核心依赖**：
- `fastapi` + `uvicorn` — Web 框架
- `sqlalchemy` + `alembic` — 数据库 ORM 和迁移
- `openai` (≥1.0) — LLM API SDK
- `pydantic` (≥2.0) — 数据校验
- `python-dotenv` — 环境变量管理
- `pytest` + `httpx` — 测试

---

## 六、关于评分维度的取舍说明

文件中有两处评分标准不完全一致：
- **第3点**：可读性 20% + 逻辑正确性 50% + 规范性 30%
- **第4点**：多维度（规范、逻辑、**性能**）

**建议**：第一阶段以三围度为准（可读性 20% + 逻辑正确性 50% + 规范性 30%）。性能维度依赖客观测试环境的 benchmark 数据（需 Docker 沙箱），更适合放在 Phase 2 引入。
