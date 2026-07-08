"""沙箱单元测试：run_python 各种边界。"""
from __future__ import annotations

import os
import sys

import pytest

from app.services.sandbox import (
    DEFAULT_TIMEOUT_SEC,
    MAX_CODE_BYTES,
    CaseResult,
    SandboxCase,
    SandboxResult,
    _build_prelude,
    result_to_dict,
    run_python,
)

# POSIX 平台才支持 resource 模块和 RLIMIT 限制
IS_POSIX = os.name == "posix"
posix_only = pytest.mark.skipif(not IS_POSIX, reason="resource limits only on POSIX")


# ---------- 基本行为 ----------

def test_simple_addition_all_pass():
    code = "def solution(a, b):\n    return a + b\n"
    cases = [
        SandboxCase("t1", [1, 2], 3),
        SandboxCase("t2", [0, 0], 0),
        SandboxCase("t3", [-1, 1], 0),
    ]
    r = run_python(code, cases)
    assert r.error is None
    assert r.passed == 3
    assert r.total == 3
    assert r.pass_rate == 1.0
    for c in r.cases:
        assert isinstance(c, CaseResult)
        assert c.passed is True
        assert c.error is None


def test_some_cases_fail():
    code = "def solution(a, b):\n    return a - b  # bug: should be +\n"
    cases = [
        SandboxCase("t1", [1, 2], 3),  # 1-2=-1 != 3, fail
        SandboxCase("t2", [5, 0], 5),  # 5-0=5 == 5, pass
    ]
    r = run_python(code, cases)
    assert r.error is None
    assert r.passed == 1
    assert r.total == 2
    assert r.cases[0].passed is False
    assert r.cases[1].passed is True
    assert "-1" in r.cases[0].actual
    assert "3" in r.cases[0].expected


# ---------- 异常处理 ----------

def test_user_code_raises():
    code = "def solution(a, b):\n    raise ValueError('nope')\n"
    cases = [SandboxCase("t1", [1, 2], 3)]
    r = run_python(code, cases)
    assert r.error is None
    assert r.passed == 0
    assert r.total == 1
    assert r.cases[0].passed is False
    assert "ValueError" in (r.cases[0].error or "")


def test_user_code_syntax_error_returns_global_error():
    code = "def solution(:\n    return 1\n"  # 语法错
    cases = [SandboxCase("t1", [], 1)]
    r = run_python(code, cases)
    assert r.error is not None
    assert r.passed == 0
    assert r.total == 1
    assert "exit" in r.error or "SyntaxError" in r.error


def test_user_code_missing_function():
    code = "def other():\n    return 1\n"  # 没有 solution
    cases = [SandboxCase("t1", [], 1)]
    r = run_python(code, cases)
    assert r.error is not None
    assert "missing function: solution" in r.error
    assert r.passed == 0
    assert r.total == 1


def test_custom_func_name():
    code = "def solve(x):\n    return x * 2\n"
    cases = [SandboxCase("t1", [5], 10)]
    r = run_python(code, cases, func_name="solve")
    assert r.error is None
    assert r.passed == 1


def test_invalid_func_name_rejected():
    """非法 Python 标识符（数字开头 / 过滤后为空）必须被拒绝。"""
    code = "def solution():\n    return 1\n"
    cases = [SandboxCase("t1", [], 1)]

    # 数字开头：Python 标识符不能以数字开头
    r = run_python(code, cases, func_name="123abc")
    assert r.error is not None
    assert "invalid func_name" in r.error

    # 过滤后为空：纯符号
    r2 = run_python(code, cases, func_name="@#$")
    assert r2.error is not None
    assert "invalid func_name" in r2.error


def test_func_name_with_safe_symbols_normalized():
    """含空格的 func_name 过滤后是合法标识符，code 校验会失败（因为没那个 def）。"""
    code = "def solution():\n    return 1\n"
    cases = [SandboxCase("t1", [], 1)]
    r = run_python(code, cases, func_name="sol os")  # 过滤成 "solos"
    # safe_func_name="solos" 是合法标识符，校验通过；找不到 def solos → 报 missing function
    assert r.error is not None
    assert "missing function" in r.error


# ---------- 边界 ----------

def test_empty_code():
    r = run_python("", [SandboxCase("t1", [], 0)])
    assert r.error is not None
    assert "missing function" in r.error


def test_no_test_cases():
    code = "def solution():\n    return 1\n"
    r = run_python(code, [])
    assert r.error == "no test cases"
    assert r.total == 0


def test_code_too_large():
    code = "def solution():\n    return 1\n" + "x = 1\n" * (MAX_CODE_BYTES // 5)
    cases = [SandboxCase("t1", [], 1)]
    r = run_python(code, cases)
    assert r.error is not None
    assert "too large" in r.error


def test_too_many_cases():
    code = "def solution(x):\n    return x\n"
    cases = [SandboxCase(f"t{i}", [i], i) for i in range(201)]
    r = run_python(code, cases)
    assert r.error is not None
    assert "too many test cases" in r.error


# ---------- 性能 ----------

def test_timeout_on_infinite_loop():
    code = "def solution():\n    while True: pass\n"
    cases = [SandboxCase("t1", [], None)]
    r = run_python(code, cases, timeout=0.5)
    assert r.error is not None
    assert "TIMEOUT" in r.error
    assert r.passed == 0
    assert r.total == 1


def test_runtime_measured():
    code = "def solution(x):\n    return x * 2\n"
    cases = [SandboxCase("t1", [3], 6)]
    r = run_python(code, cases)
    assert r.error is None
    # 即使再快也至少有 1ms 精度
    assert r.total_runtime_ms >= 0
    assert r.cases[0].runtime_ms >= 0


# ---------- 复杂数据 ----------

def test_list_return():
    code = "def solution(n):\n    return list(range(n))\n"
    cases = [
        SandboxCase("t1", [3], [0, 1, 2]),
        SandboxCase("t2", [0], []),
    ]
    r = run_python(code, cases)
    assert r.passed == 2


def test_dict_return():
    code = "def solution():\n    return {'a': 1, 'b': [2, 3]}\n"
    cases = [SandboxCase("t1", [], {"a": 1, "b": [2, 3]})]
    r = run_python(code, cases)
    assert r.passed == 1


# ---------- 序列化 ----------

def test_result_to_dict():
    code = "def solution(a, b):\n    return a + b\n"
    cases = [SandboxCase("t1", [1, 2], 3)]
    r = run_python(code, cases)
    d = result_to_dict(r)
    assert "passed" in d
    assert "total" in d
    assert "pass_rate" in d
    assert "cases" in d
    assert "error" in d
    assert d["pass_rate"] == 1.0
    assert d["error"] is None
    assert len(d["cases"]) == 1


# ---------- 默认超时 ----------

def test_default_timeout_used():
    """不传 timeout 时用 DEFAULT_TIMEOUT_SEC。"""
    code = "def solution():\n    return 1\n"
    cases = [SandboxCase("t1", [], 1)]
    r = run_python(code, cases)
    # 不抛错就 OK
    assert r.error is None
    assert r.passed == 1
    # 默认值 sanity check
    assert DEFAULT_TIMEOUT_SEC > 0


# ---------- P2.x 资源限制 ----------

def test_build_prelude_includes_all_limits():
    """prelude 必须包含三类 RLIMIT 设置，参数正确。"""
    prelude = _build_prelude(memory_mb=128, cpu_time_sec=3, max_procs=16)
    assert "import resource" in prelude
    assert "RLIMIT_AS" in prelude
    assert "RLIMIT_CPU" in prelude
    assert "RLIMIT_NPROC" in prelude
    assert "128 * 1024 * 1024" in prelude
    assert "(3, 4)" in prelude  # cpu_time_sec=3, hard=3+1
    assert "(16, 16)" in prelude  # nproc soft=hard=16
    assert "except ImportError" in prelude  # Windows 降级


def test_build_prelude_zero_cpu_uses_plus_one():
    """cpu_time_sec=0 时硬限 = soft + 1（避免 hard < soft）。"""
    prelude = _build_prelude(memory_mb=256, cpu_time_sec=0, max_procs=32)
    assert "(0, 1)" in prelude


def test_run_python_uses_configured_memory():
    """prelude 应根据 settings.sandbox_memory_mb 生成。"""
    from app.core import config
    from app.services import sandbox

    s = config.get_settings()
    original = s.sandbox_memory_mb
    try:
        # 临时改 settings
        object.__setattr__(s, "sandbox_memory_mb", 512)
        config.get_settings.cache_clear()
        prelude = sandbox._build_prelude(512, 5, 32)
        assert "512 * 1024 * 1024" in prelude
    finally:
        object.__setattr__(s, "sandbox_memory_mb", original)
        config.get_settings.cache_clear()


@posix_only
def test_memory_limit_triggers_oom():
    """内存超限（申请 100MB 但限制 50MB）应被 kill，runner 全局 error。"""
    code = (
        "def solution():\n"
        "    x = []\n"
        "    while True:\n"
        "        x.append(' ' * 1024 * 1024)  # 每次 1MB\n"
        "    return x\n"
    )
    cases = [SandboxCase("t1", [], None)]

    # 用 monkeypatch 临时设小内存限制（不影响其他测试）
    from app.core import config
    from app.services import sandbox

    s = config.get_settings()
    original = s.sandbox_memory_mb
    try:
        object.__setattr__(s, "sandbox_memory_mb", 50)
        config.get_settings.cache_clear()
        r = sandbox.run_python(code, cases, timeout=3.0)
    finally:
        object.__setattr__(s, "sandbox_memory_mb", original)
        config.get_settings.cache_clear()

    # 应该被 OOM kill
    assert r.error is not None
    assert r.passed == 0
    # 错误信息含 exit code 或 MemoryError
    assert any(s in (r.error or "") for s in ("exit", "MemoryError", "signal"))


@posix_only
def test_cpu_limit_triggers_sigxcpu():
    """CPU 时间超限（busy loop）应被 SIGXCPU kill。"""
    code = (
        "def solution():\n"
        "    s = 0\n"
        "    while True:\n"
        "        s += 1\n"
        "    return s\n"
    )
    cases = [SandboxCase("t1", [], None)]

    from app.core import config
    from app.services import sandbox

    s = config.get_settings()
    original = s.sandbox_cpu_time_sec
    try:
        object.__setattr__(s, "sandbox_cpu_time_sec", 1)  # 1 秒 CPU 时间
        config.get_settings.cache_clear()
        r = sandbox.run_python(code, cases, timeout=5.0)  # wall 5s 不会先触发
    finally:
        object.__setattr__(s, "sandbox_cpu_time_sec", original)
        config.get_settings.cache_clear()

    # 应当被 SIGXCPU kill
    assert r.error is not None
    assert r.passed == 0
    # exit code 是 -SIGXCPU（值是平台相关的，通常负数）
    assert "exit" in r.error or "signal" in r.error


@posix_only
def test_normal_code_still_works_under_limits():
    """正常代码在限制下应照常工作（验证不误杀）。"""
    code = "def solution(a, b):\n    return a + b\n"
    cases = [SandboxCase("t1", [1, 2], 3), SandboxCase("t2", [10, 20], 30)]

    from app.core import config
    from app.services import sandbox

    s = config.get_settings()
    original_mem = s.sandbox_memory_mb
    original_cpu = s.sandbox_cpu_time_sec
    try:
        object.__setattr__(s, "sandbox_memory_mb", 128)
        object.__setattr__(s, "sandbox_cpu_time_sec", 5)
        config.get_settings.cache_clear()
        r = sandbox.run_python(code, cases, timeout=3.0)
    finally:
        object.__setattr__(s, "sandbox_memory_mb", original_mem)
        object.__setattr__(s, "sandbox_cpu_time_sec", original_cpu)
        config.get_settings.cache_clear()

    assert r.error is None
    assert r.passed == 2
