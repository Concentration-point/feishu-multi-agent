"""ToolStats SQLite sink 测试。

验证点：
1. 默认 SQLite 关闭时，仅 JSONL 写入
2. 设置 TOOL_STATS_SQLITE_PATH 后，JSONL 与 SQLite 双写
3. SQLite 写入失败不阻断主流程
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools as tools_pkg
from tools import AgentContext, ToolRegistry
from tools import tool_stats_store


# --- helpers --------------------------------------------------------------

def _make_context() -> AgentContext:
    return AgentContext(
        record_id="rec_test",
        project_name="测试项目",
        role_id="account_manager",
        sub_id="sub_x",
    )


def _patch_paths(monkeypatch, tmp_path: Path):
    """把 JSONL / SQLite 全部隔离到临时目录，并重置 store 单例。"""
    jsonl_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(tools_pkg, "_STATS_FILE", jsonl_path, raising=True)
    # 重置 store 单例，避免测试间互相污染
    monkeypatch.setattr(tool_stats_store, "_STORE_SINGLETON", None, raising=False)
    monkeypatch.setattr(tool_stats_store, "_INIT_FAILED", False, raising=False)
    return jsonl_path


def _register_fake_tool(reg: ToolRegistry, name: str, fn):
    """绕过文件扫描，直接注册一个假工具。"""
    reg._tools[name] = {
        "schema": {
            "type": "function",
            "function": {"name": name, "description": "fake", "parameters": {}},
        },
        "execute": fn,
    }


# --- tests ----------------------------------------------------------------

def test_sqlite_disabled_only_jsonl(monkeypatch, tmp_path):
    """默认未设置 TOOL_STATS_SQLITE_PATH 时，只写 JSONL，不创建 SQLite 文件。"""
    jsonl_path = _patch_paths(monkeypatch, tmp_path)
    monkeypatch.delenv("TOOL_STATS_SQLITE_PATH", raising=False)

    reg = ToolRegistry.__new__(ToolRegistry)
    reg._tools = {}
    reg._cb = {}

    async def ok_tool(params, ctx):
        return "ok"

    _register_fake_tool(reg, "fake_ok", ok_tool)

    asyncio.run(reg.call_tool("fake_ok", {}, _make_context()))

    assert jsonl_path.exists(), "JSONL 应写入"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["tool"] == "fake_ok"
    assert rec["success"] is True

    # 不应该有任何 .db 文件
    db_files = list(tmp_path.glob("*.db"))
    assert db_files == [], f"未启用 SQLite，不应生成 db 文件，实际: {db_files}"

    # store 单例仍为 None
    assert tool_stats_store._STORE_SINGLETON is None


def test_sqlite_enabled_dual_write(monkeypatch, tmp_path):
    """设置 TOOL_STATS_SQLITE_PATH 后，JSONL 与 SQLite 双写。"""
    jsonl_path = _patch_paths(monkeypatch, tmp_path)
    db_path = tmp_path / "tool_stats.db"
    monkeypatch.setenv("TOOL_STATS_SQLITE_PATH", str(db_path))

    reg = ToolRegistry.__new__(ToolRegistry)
    reg._tools = {}
    reg._cb = {}

    async def ok_tool(params, ctx):
        return "ok"

    async def biz_err_tool(params, ctx):
        return "错误: 业务校验失败"

    _register_fake_tool(reg, "fake_ok", ok_tool)
    _register_fake_tool(reg, "fake_biz_err", biz_err_tool)

    ctx = _make_context()
    asyncio.run(reg.call_tool("fake_ok", {}, ctx))
    asyncio.run(reg.call_tool("fake_biz_err", {}, ctx))

    # JSONL 双写
    assert jsonl_path.exists()
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    # SQLite 已生成且包含两行
    assert db_path.exists(), "启用后应生成 SQLite 文件"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT tool, role_id, record_id, sub_id, success, error, duration_ms, raw "
            "FROM tool_calls ORDER BY ts ASC"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    tools_seen = [r[0] for r in rows]
    assert "fake_ok" in tools_seen and "fake_biz_err" in tools_seen

    ok_row = next(r for r in rows if r[0] == "fake_ok")
    err_row = next(r for r in rows if r[0] == "fake_biz_err")

    assert ok_row[1] == "account_manager"
    assert ok_row[2] == "rec_test"
    assert ok_row[3] == "sub_x"
    assert ok_row[4] == 1  # success=True → 1
    assert ok_row[5] is None or ok_row[5] == "" or ok_row[5] == "None"
    assert ok_row[6] is not None  # duration_ms
    # raw 应是合法 JSON
    raw_obj = json.loads(ok_row[7])
    assert raw_obj["tool"] == "fake_ok"

    assert err_row[4] == 0  # 业务错误 success=False
    assert err_row[5] == "biz_error"


def test_sqlite_failure_does_not_break_main(monkeypatch, tmp_path):
    """SQLite store.record 抛异常时，JSONL 仍然写入，工具调用正常返回。"""
    jsonl_path = _patch_paths(monkeypatch, tmp_path)
    db_path = tmp_path / "tool_stats_fail.db"
    monkeypatch.setenv("TOOL_STATS_SQLITE_PATH", str(db_path))

    # 先触发一次 store 初始化（通过一个空 call），然后再 monkeypatch record 抛错
    reg = ToolRegistry.__new__(ToolRegistry)
    reg._tools = {}
    reg._cb = {}

    async def ok_tool(params, ctx):
        return "ok"

    _register_fake_tool(reg, "fake_ok", ok_tool)

    # 第一次调用以初始化 store 单例
    asyncio.run(reg.call_tool("fake_ok", {}, _make_context()))
    store = tool_stats_store._STORE_SINGLETON
    assert store is not None

    # monkeypatch store.record 抛异常
    def boom(stat):
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "record", boom)

    # 再次调用：必须不抛异常，且返回正常结果
    result = asyncio.run(reg.call_tool("fake_ok", {}, _make_context()))
    assert result == "ok"

    # JSONL 应该有 2 行
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_sqlite_store_unwritable_path_falls_back(monkeypatch, tmp_path):
    """构造一个不可写的 SQLite 路径（指向已存在的目录），初始化失败不阻断主流程。"""
    jsonl_path = _patch_paths(monkeypatch, tmp_path)
    # 指向一个已存在的目录，sqlite3.connect 会失败
    bad_dir = tmp_path / "is_a_dir"
    bad_dir.mkdir()
    monkeypatch.setenv("TOOL_STATS_SQLITE_PATH", str(bad_dir))

    reg = ToolRegistry.__new__(ToolRegistry)
    reg._tools = {}
    reg._cb = {}

    async def ok_tool(params, ctx):
        return "ok"

    _register_fake_tool(reg, "fake_ok", ok_tool)

    # 调用不应抛异常
    result = asyncio.run(reg.call_tool("fake_ok", {}, _make_context()))
    assert result == "ok"

    # JSONL 正常
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
