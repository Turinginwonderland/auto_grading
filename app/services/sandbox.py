"""代码沙箱（Phase 2 性能维度前置）。

MVP 实现：用 subprocess + timeout 跑 Python 代码，逐个用例验证。
- **不**做 syscall 拦截（生产应上 Docker / gVisor）
- **不**限制网络/文件访问（仅靠 timeout + 代码长度限制兜底）
- 通过 JSON 序列化用例入参，避免字符串解析歧义

后续 P2.x 可替换为 Docker 版本（接口不变）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------- 数据结构 ----------

@dataclass
class SandboxCase:
    name: str
    args: list[Any]
    expected: Any


@dataclass
class CaseResult:
    name: str
    passed: bool
    actual: Any
    expected: Any
    error: str | None
    runtime_ms: int


@dataclass
class SandboxResult:
    passed: int
    total: int
    cases: list[CaseResult] = field(default_factory=list)
    total_runtime_ms: int = 0
    error: str | None = None  # 全局错误：timeout / 编译错 / 进程退出码非 0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


# ---------- 配置 ----------

DEFAULT_TIMEOUT_SEC = 2.0
MAX_CODE_BYTES = 50_000  # 50KB，与 grade endpoint 上限对齐
MAX_CASES = 200
RESULT_TAG = "===SANDBOX_RESULT==="

# 拼装到用户代码后的 runner 模板。CASES_JSON 会被安全转义后填入。
# FUNC_NAME 占位符在运行时替换为入口函数名。
_RUNNER_TEMPLATE = '''
import json as __json
import time as __time
import sys as __sys

__CASES__ = __json.loads(__CASES_JSON_PLACEHOLDER__)
__FUNC__ = "__FUNC_NAME_PLACEHOLDER__"

def __sandbox_runner__():
    __out = []
    for __tc in __CASES__:
        __t0 = __time.perf_counter()
        try:
            __actual = eval(__FUNC__)(*__tc["args"])
            __actual_s = repr(__actual)
            __expected_s = repr(__tc["expected"])
            __passed = (__actual_s == __expected_s)
            __err = None
        except Exception as __e:
            __actual_s = ""
            __expected_s = repr(__tc["expected"])
            __passed = False
            __err = f"{type(__e).__name__}: {__e}"
        __elapsed_ms = int((__time.perf_counter() - __t0) * 1000)
        __out.append({
            "name": __tc["name"],
            "passed": __passed,
            "actual": __actual_s,
            "expected": __expected_s,
            "error": __err,
            "runtime_ms": __elapsed_ms,
        })
    __sys.stdout.write("===SANDBOX_RESULT===\\n")
    __sys.stdout.write(__json.dumps(__out, ensure_ascii=False))
    __sys.stdout.write("\\n")

__sandbox_runner__()
'''


# ---------- 公开 API ----------

def run_python(
    code: str,
    test_cases: list[SandboxCase],
    *,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    func_name: str = "solution",
) -> SandboxResult:
    """同步跑 Python 代码并逐个用例验证。

    Args:
        code: 用户代码，必须定义 ``def solution(*args)`` 或自定义 ``func_name``
        test_cases: 用例列表
        timeout: 总超时（秒，含所有用例）；超时返回 SandboxResult(error="TIMEOUT")
        func_name: 待调用的入口函数名

    Returns:
        SandboxResult。``error`` 非空表示全局失败（未跑用例）；否则按 cases 看。
    """
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        return SandboxResult(
            passed=0, total=0, error=f"code too large (> {MAX_CODE_BYTES} bytes)"
        )
    if not test_cases:
        return SandboxResult(passed=0, total=0, error="no test cases")
    if len(test_cases) > MAX_CASES:
        return SandboxResult(
            passed=0, total=0, error=f"too many test cases (> {MAX_CASES})"
        )

    # func_name 必须是合法 Python 标识符（防御性检查，防止注入到 runner 模板）
    safe_func_name = "".join(c for c in func_name if c.isalnum() or c == "_")
    if not safe_func_name or not safe_func_name.isidentifier():
        return SandboxResult(
            passed=0,
            total=len(test_cases),
            error=f"invalid func_name: {func_name!r}",
        )

    # 校验用户代码定义了目标函数（简单字符串检查）
    if f"def {func_name}(" not in code:
        return SandboxResult(
            passed=0,
            total=len(test_cases),
            error=f"user code missing function: {func_name}",
        )

    cases_json = json.dumps(
        [{"name": tc.name, "args": tc.args, "expected": tc.expected} for tc in test_cases],
        ensure_ascii=False,
    )
    # JSON 字符串内双引号需做转义避免破坏 wrapper 字符串
    cases_json_escaped = cases_json.replace("\\", "\\\\").replace('"', '\\"')
    runner = _RUNNER_TEMPLATE.replace("__CASES_JSON_PLACEHOLDER__", f'"{cases_json_escaped}"')
    runner = runner.replace("__FUNC_NAME_PLACEHOLDER__", safe_func_name)

    wrapper = code + "\n\n" + runner

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            timeout=timeout,
            capture_output=True,
            text=True,
            # 限制子进程环境变量，移除可能影响沙箱的（如 PYTHONPATH）
            env={
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # Windows 需要
                "HOME": os.environ.get("HOME", ""),
            },
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return SandboxResult(
            passed=0,
            total=len(test_cases),
            total_runtime_ms=elapsed_ms,
            error=f"TIMEOUT after {timeout}s",
        )

    total_runtime_ms = int((time.perf_counter() - start) * 1000)

    if proc.returncode != 0:
        return SandboxResult(
            passed=0,
            total=len(test_cases),
            total_runtime_ms=total_runtime_ms,
            error=f"exit {proc.returncode}: {(proc.stderr or '').strip()[:500]}",
        )

    # 解析 stdout 找结果
    stdout = proc.stdout or ""
    if RESULT_TAG not in stdout:
        return SandboxResult(
            passed=0,
            total=len(test_cases),
            total_runtime_ms=total_runtime_ms,
            error=f"runner produced no result: stdout={stdout.strip()[:200]!r}",
        )

    try:
        json_part = stdout.split(RESULT_TAG, 1)[1].strip()
        raw = json.loads(json_part)
    except (json.JSONDecodeError, IndexError) as e:
        return SandboxResult(
            passed=0,
            total=len(test_cases),
            total_runtime_ms=total_runtime_ms,
            error=f"failed to parse runner output: {e}",
        )

    cases: list[CaseResult] = []
    passed = 0
    for item in raw:
        cr = CaseResult(
            name=item.get("name", "?"),
            passed=bool(item.get("passed")),
            actual=item.get("actual"),
            expected=item.get("expected"),
            error=item.get("error"),
            runtime_ms=int(item.get("runtime_ms", 0)),
        )
        cases.append(cr)
        if cr.passed:
            passed += 1

    return SandboxResult(
        passed=passed,
        total=len(cases),
        cases=cases,
        total_runtime_ms=total_runtime_ms,
    )


def result_to_dict(r: SandboxResult) -> dict[str, Any]:
    """转 dict（API 序列化用）。"""
    d = asdict(r)
    d["pass_rate"] = r.pass_rate
    return d
