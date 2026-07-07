"""工具函数测试。"""
from app.utils.code_hash import sha256_code, truncate_code


def test_sha256_stable():
    a = sha256_code("def f(): return 1\n")
    b = sha256_code("def f(): return 1\n")
    c = sha256_code("def f(): return 2\n")
    assert a == b
    assert a != c
    assert len(a) == 64


def test_truncate_under_limit_unchanged():
    code = "x = 1\n" * 100
    assert truncate_code(code) == code


def test_truncate_over_limit_marks_truncation():
    code = "x = 1\n" * 10_000
    out = truncate_code(code, max_bytes=2048)
    assert "已截断" in out
    assert len(out.encode("utf-8")) <= 2048 + 64
