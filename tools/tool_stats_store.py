"""工具调用统计 SQLite sink — 与 JSONL 并行的可选持久化通道。

设计目标：
- 仅当环境变量 TOOL_STATS_SQLITE_PATH 非空时启用。
- 写入失败不阻断主流程，仅记录一次 warning。
- 使用标准库 sqlite3，无新依赖。
- 多线程安全（threading.Lock）。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 进程级单例（lazy init）
_STORE_SINGLETON: "ToolStatsSqliteStore | None" = None
# 初始化失败标记：失败一次后不再重试（避免每次调用都试连接）
_INIT_FAILED: bool = False
_INIT_LOCK = threading.Lock()

_DDL = """
CREATE TABLE IF NOT EXISTS tool_calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    record_id    TEXT,
    role_id      TEXT,
    sub_id       TEXT,
    tool         TEXT NOT NULL,
    success      INTEGER,
    error        TEXT,
    duration_ms  REAL,
    raw          TEXT
)
"""

_INSERT_SQL = (
    "INSERT INTO tool_calls "
    "(ts, record_id, role_id, sub_id, tool, success, error, duration_ms, raw) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


class ToolStatsSqliteStore:
    """SQLite sink，构造时 ensure schema；record(stat) 写入一条工具调用。"""

    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._warned_failure = False
        # 确保父目录存在（若路径含目录段）
        parent = Path(self._db_path).parent
        if str(parent) and parent != Path("."):
            parent.mkdir(parents=True, exist_ok=True)
        # 建表（失败会抛，由调用方捕获）
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(_DDL)
            conn.commit()
        finally:
            conn.close()

    def record(self, stat: dict[str, Any]) -> None:
        """写入一条工具调用记录；缺字段用 None。"""
        try:
            success_val = stat.get("success")
            if isinstance(success_val, bool):
                success_int: int | None = 1 if success_val else 0
            elif success_val is None:
                success_int = None
            else:
                success_int = 1 if success_val else 0

            duration = stat.get("duration_ms")
            try:
                duration_val: float | None = float(duration) if duration is not None else None
            except (TypeError, ValueError):
                duration_val = None

            row = (
                stat.get("ts"),
                stat.get("record_id"),
                stat.get("role_id"),
                stat.get("sub_id"),
                stat.get("tool"),
                success_int,
                stat.get("error"),
                duration_val,
                json.dumps(stat, ensure_ascii=False, default=str),
            )
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(_INSERT_SQL, row)
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:  # noqa: BLE001 — 故意吞掉，单次 warning
            if not self._warned_failure:
                logger.warning("ToolStats SQLite 写入失败（后续静默）: %s", e)
                self._warned_failure = True


def get_store() -> "ToolStatsSqliteStore | None":
    """读取 TOOL_STATS_SQLITE_PATH 环境变量；非空则 lazy 初始化单例。

    初始化失败后用 _INIT_FAILED 标记，不再重试。
    """
    global _STORE_SINGLETON, _INIT_FAILED

    if _INIT_FAILED:
        return None
    if _STORE_SINGLETON is not None:
        return _STORE_SINGLETON

    path = os.environ.get("TOOL_STATS_SQLITE_PATH", "").strip()
    if not path:
        return None

    with _INIT_LOCK:
        # double-check
        if _STORE_SINGLETON is not None:
            return _STORE_SINGLETON
        if _INIT_FAILED:
            return None
        try:
            _STORE_SINGLETON = ToolStatsSqliteStore(path)
            logger.info("ToolStats SQLite sink 启用: %s", path)
        except Exception as e:  # noqa: BLE001
            logger.warning("ToolStats SQLite 初始化失败，回退仅 JSONL: %s", e)
            _INIT_FAILED = True
            _STORE_SINGLETON = None
    return _STORE_SINGLETON
