"""工具方法：源码哈希、文本截断等。"""
from __future__ import annotations

import hashlib


def sha256_code(code: str) -> str:
    """计算代码的 SHA-256（用于评分缓存 key）。"""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def truncate_code(code: str, max_bytes: int = 50 * 1024) -> str:
    """代码超长截断（按字符截，避免半字符）。"""
    if len(code.encode("utf-8")) <= max_bytes:
        return code
    # 留 1KB 余量给提示
    return code[: max(0, max_bytes - 1024)] + "\n# ... [已截断]"
