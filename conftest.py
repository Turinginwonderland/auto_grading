"""pytest 配置：确保根目录在 sys.path；为每个测试隔离 DB。"""
import os
import sys

# 把项目根加入 import path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """每个测试用临时 sqlite 隔离 DB。

    解决：app.db.database 的 engine 是 module-level，import 时锁了 DATABASE_URL；
    不重置会导致所有测试共享默认 DB（可能含脏数据），产生跨测试污染。
    """
    db_file = tmp_path / f"test_{os.getpid()}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("LLM_API_KEY", "")
    from app.core import config
    config.get_settings.cache_clear()

    # 重建 engine + SessionLocal（关键）
    import app.db.database as db
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    db.engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        echo=False,
        future=True,
    )
    db.SessionLocal = sessionmaker(
        bind=db.engine, autoflush=False, autocommit=False, future=True
    )
    db.init_db()

    # 清进程内 LRU 缓存，避免 mock 评分结果跨测试污染
    from app.services import cache
    cache._cache.clear()

    yield
