"""动态路由单元测试。

验证点：
1. _resolve_next_role 路由表覆盖全部状态
2. 路由终止状态正确终止
3. 人审门禁特殊标记正确识别
4. 未知状态返回 None
5. ROUTE_TABLE 与 VALID_STATUSES 完备性
6. 动态路由全流程 mock（状态递进 → 正确角色序列）
7. 路由死循环保护（max_route_steps）
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (
    ROUTE_TABLE,
    ROUTE_TERMINAL_STATUSES,
    STATUS_PENDING,
    STATUS_ANALYZING,
    STATUS_STRATEGY,
    STATUS_WRITING,
    STATUS_REVIEWING,
    STATUS_SCHEDULING,
    STATUS_DONE,
    STATUS_REJECTED,
    STATUS_PENDING_REVIEW,
    VALID_STATUSES,
)
from orchestrator import Orchestrator


class _FakeContentMemory:
    """ContentMemory mock，list_by_project 返回空列表。"""
    def __init__(self, client=None):
        pass

    async def list_by_project(self, name):
        return []


# ── 1. 路由表基础测试 ──

def test_route_table_covers_all_valid_statuses():
    """ROUTE_TABLE 必须覆盖 VALID_STATUSES 中的全部状态。"""
    for status in VALID_STATUSES:
        assert status in ROUTE_TABLE, f"ROUTE_TABLE 缺少状态 '{status}'"


def test_resolve_next_role_normal_sequence():
    """正常序列中的状态映射到正确角色。"""
    orch = Orchestrator("rec_test")
    assert orch._resolve_next_role(STATUS_PENDING) == "account_manager"
    assert orch._resolve_next_role(STATUS_ANALYZING) == "account_manager"
    assert orch._resolve_next_role(STATUS_STRATEGY) == "strategist"
    assert orch._resolve_next_role(STATUS_WRITING) == "copywriter"
    assert orch._resolve_next_role(STATUS_REVIEWING) == "reviewer"
    assert orch._resolve_next_role(STATUS_SCHEDULING) == "project_manager"


def test_resolve_next_role_terminal():
    """终止状态返回 None。"""
    orch = Orchestrator("rec_test")
    assert orch._resolve_next_role(STATUS_DONE) is None
    assert orch._resolve_next_role(STATUS_REJECTED) is None


def test_resolve_next_role_human_review():
    """待人审状态路由到人审门禁特殊标记。"""
    orch = Orchestrator("rec_test")
    result = orch._resolve_next_role(STATUS_PENDING_REVIEW)
    assert result == "__human_review_gate__"


def test_resolve_next_role_unknown():
    """未知状态返回 None。"""
    orch = Orchestrator("rec_test")
    assert orch._resolve_next_role("不存在的状态") is None
    assert orch._resolve_next_role("") is None


def test_terminal_statuses_subset_of_valid():
    """终止状态集合必须是 VALID_STATUSES 的子集。"""
    for s in ROUTE_TERMINAL_STATUSES:
        assert s in VALID_STATUSES, f"终止状态 '{s}' 不在 VALID_STATUSES 中"


# ── 2. 动态路由集成测试（mock Agent + ProjectMemory）──

class _StatusProgression:
    """模拟项目状态递进：每次 load() 返回下一个预设状态。"""

    def __init__(self, statuses: list[str], project_name: str = "TestClient"):
        self._statuses = list(statuses)
        self._index = 0
        self._project_name = project_name

    def __call__(self, record_id, *args, **kwargs):
        return self

    async def load(self):
        from memory.project import BriefProject
        status = self._statuses[min(self._index, len(self._statuses) - 1)]
        self._index += 1
        return BriefProject(
            record_id="rec_test",
            client_name=self._project_name,
            status=status,
            brief="测试 Brief",
            project_type="电商大促",
        )

    async def update_status(self, s): pass
    async def write_review_summary(self, *a, **kw): pass
    async def write_review_status(self, s): pass
    async def write_pending_meta(self, m): pass
    async def write_human_feedback(self, f): pass
    async def clear_pending_state(self): pass


class _MockAgent:
    """极简 Agent mock，记录被调用的角色序列。"""
    call_log: list[str] = []

    def __init__(self, role_id, record_id, event_bus=None, task_filter=None):
        self.role_id = role_id
        self.record_id = record_id
        self._event_bus = event_bus
        self._task_filter = task_filter or {}
        self._pending_experience = None
        self._wiki_written = False
        self._messages = []

    async def run(self):
        _MockAgent.call_log.append(self.role_id)
        return f"[{self.role_id}] done"


@pytest.mark.asyncio
async def test_dynamic_routing_full_sequence():
    """模拟完整状态递进，验证动态路由按正确顺序调度角色。

    状态序列：待处理 → 解读中(AM完成后) → 待人审(门禁) → 策略中 → 撰写中 → 审核中 → 排期中 → 已完成
    但由于 AM 完成后 _read_current_status 返回的是下一个状态，
    我们直接模拟路由看到的状态序列。
    """
    _MockAgent.call_log = []

    # 状态递进（注意 fan-out 内部额外调用一次 ProjectMemory.load()）：
    # load #0: run() 初始 load → 待处理 → route → AM
    # load #1: _read_current_status (AM后) → 策略中 → route → strategist
    # load #2: _read_current_status (strategist后) → 撰写中 → route → copywriter
    # load #3: fan-out 内部 ProjectMemory.load()（被消耗，不参与路由）
    # load #4: _read_current_status (copywriter后) → 审核中 → route → reviewer
    # load #5: _read_current_status (reviewer后) → 排期中 → route → PM
    # load #6: _read_current_status (PM后) → 已完成 → route → None → break
    status_prog = _StatusProgression([
        STATUS_PENDING,     # #0 初始 load
        STATUS_STRATEGY,    # #1 AM 后
        STATUS_WRITING,     # #2 strategist 后
        STATUS_WRITING,     # #3 fan-out 内部消耗
        STATUS_REVIEWING,   # #4 copywriter 后
        STATUS_SCHEDULING,  # #5 reviewer 后
        STATUS_DONE,        # #6 PM 后
        STATUS_DONE,        # 安全余量
    ])

    # mock review helpers 返回安全值
    async def _fake_threshold():
        return 0.6

    async def _fake_pass_rate():
        return 0.8

    async def _fake_reconcile(rate):
        return rate

    async def _fake_review_status():
        return "通过"

    async def _fake_red_flag():
        return "无"

    async def _noop_retries(**kw):
        pass

    async def _noop_drafts(name):
        pass

    with patch("orchestrator.BaseAgent", _MockAgent), \
         patch("orchestrator.ProjectMemory", status_prog), \
         patch("orchestrator.ContentMemory", _FakeContentMemory):
        orch = Orchestrator(record_id="rec_route_test")
        orch._get_review_threshold = _fake_threshold
        orch._get_review_pass_rate = _fake_pass_rate
        orch._reconcile_review_pass_rate = _fake_reconcile
        orch._get_project_review_status = _fake_review_status
        orch._get_review_red_flag = _fake_red_flag
        orch._handle_reviewer_retries = lambda **kw: _noop_retries(**kw)
        orch._ensure_copywriter_drafts = lambda name: _noop_drafts(name)

        results = await orch.run()

    # 验证角色调用顺序
    assert _MockAgent.call_log == [
        "account_manager",
        "strategist",
        "copywriter",
        "reviewer",
        "project_manager",
    ], f"角色调用顺序不正确: {_MockAgent.call_log}"

    # 验证所有阶段成功
    assert all(r.ok for r in results), "所有阶段应成功"
    assert len(results) == 5


@pytest.mark.asyncio
async def test_dynamic_routing_max_steps_guard():
    """模拟状态不变导致的死循环，验证 max_route_steps 保护生效。"""
    _MockAgent.call_log = []

    # 状态始终返回 "待处理"，Agent 永远不改状态
    stuck_prog = _StatusProgression([STATUS_PENDING] * 20)

    async def _fake_threshold():
        return 0.6

    async def _fake_pass_rate():
        return 0.8

    async def _fake_reconcile(rate):
        return rate

    async def _fake_review_status():
        return ""

    with patch("orchestrator.BaseAgent", _MockAgent), \
         patch("orchestrator.ProjectMemory", stuck_prog), \
         patch("orchestrator.ContentMemory", _FakeContentMemory):
        orch = Orchestrator(record_id="rec_stuck")
        orch._max_route_steps = 3  # 降低上限加速测试
        orch._get_review_threshold = _fake_threshold
        orch._get_review_pass_rate = _fake_pass_rate
        orch._reconcile_review_pass_rate = _fake_reconcile
        orch._get_project_review_status = _fake_review_status

        results = await orch.run()

    # 最多执行 3 步
    assert len(_MockAgent.call_log) == 3
    assert all(r == "account_manager" for r in _MockAgent.call_log)


@pytest.mark.asyncio
async def test_dynamic_routing_starts_from_midway_status():
    """项目状态已在中途（撰写中），路由应直接从 copywriter 开始。"""
    _MockAgent.call_log = []

    # fan-out 内部额外消耗一次 ProjectMemory.load()
    status_prog = _StatusProgression([
        STATUS_WRITING,     # #0 初始 load
        STATUS_WRITING,     # #1 fan-out 内部消耗
        STATUS_REVIEWING,   # #2 copywriter 后
        STATUS_SCHEDULING,  # #3 reviewer 后
        STATUS_DONE,        # #4 PM 后
        STATUS_DONE,        # 安全余量
    ])

    async def _fake_threshold():
        return 0.6

    async def _fake_pass_rate():
        return 0.8

    async def _fake_reconcile(rate):
        return rate

    async def _fake_review_status():
        return "通过"

    async def _noop_retries(**kw):
        pass

    async def _noop_drafts(name):
        pass

    with patch("orchestrator.BaseAgent", _MockAgent), \
         patch("orchestrator.ProjectMemory", status_prog), \
         patch("orchestrator.ContentMemory", _FakeContentMemory):
        orch = Orchestrator(record_id="rec_midway")
        orch._get_review_threshold = _fake_threshold
        orch._get_review_pass_rate = _fake_pass_rate
        orch._reconcile_review_pass_rate = _fake_reconcile
        orch._get_project_review_status = _fake_review_status
        orch._handle_reviewer_retries = lambda **kw: _noop_retries(**kw)
        orch._ensure_copywriter_drafts = lambda name: _noop_drafts(name)

        results = await orch.run()

    # 应从 copywriter 开始，跳过 AM 和 strategist
    assert _MockAgent.call_log == [
        "copywriter",
        "reviewer",
        "project_manager",
    ], f"中途启动的角色序列不正确: {_MockAgent.call_log}"


@pytest.mark.asyncio
async def test_dynamic_routing_terminal_status_immediate_exit():
    """项目状态已为终止状态（已完成），应立即结束不执行任何 Agent。"""
    _MockAgent.call_log = []

    status_prog = _StatusProgression([STATUS_DONE, STATUS_DONE])

    async def _fake_threshold():
        return 0.6

    async def _fake_pass_rate():
        return 0.8

    async def _fake_reconcile(rate):
        return rate

    async def _fake_review_status():
        return "通过"

    with patch("orchestrator.BaseAgent", _MockAgent), \
         patch("orchestrator.ProjectMemory", status_prog), \
         patch("orchestrator.ContentMemory", _FakeContentMemory):
        orch = Orchestrator(record_id="rec_done")
        orch._get_review_threshold = _fake_threshold
        orch._get_review_pass_rate = _fake_pass_rate
        orch._reconcile_review_pass_rate = _fake_reconcile
        orch._get_project_review_status = _fake_review_status

        results = await orch.run()

    assert _MockAgent.call_log == [], "已完成状态不应执行任何 Agent"
    assert len(results) == 0
