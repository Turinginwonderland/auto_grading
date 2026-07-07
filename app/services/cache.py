"""进程内 LRU 缓存。"""
from __future__ import annotations

from cachetools import LRUCache
from threading import Lock

from app.core.config import get_settings

settings = get_settings()

_cache: LRUCache = LRUCache(maxsize=settings.grade_cache_maxsize)
_lock = Lock()


def cache_get(key: str):
    with _lock:
        return _cache.get(key)


def cache_set(key: str, value) -> None:
    with _lock:
        _cache[key] = value


def cache_key(problem_id: str, code_hash: str, language: str) -> str:
    return f"{problem_id}|{language}|{code_hash}"
