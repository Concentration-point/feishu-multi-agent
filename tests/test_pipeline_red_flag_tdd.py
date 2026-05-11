from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import REVIEW_MAX_RETRIES, STATUS_SCHEDULING
from orchestrator import Orchestrator


class _RecordingProjectMemory:
    """记录编排器尝试写入的状态，用于验证红线是否真正阻断。"""

    def __init__(self):
        self.status_updates: list[str] = []

    async def load(self):
        raise AssertionError("本测试不应依赖真实 ProjectMemory.load")

    async def update_status(self, status: str) -> None:
        self.status_updates.append(status)


@pytest.mark.asyncio
async def test_red_flag_blocks_force_advance_after_max_retries():
    """红线存在时，即使返工次数达到上限，也不能强制推进到排期。"""
    pm = _RecordingProjectMemory()
    orch = Orchestrator("rec_red_flag")
    orch._pm = pm
    orch._review_threshold = 0.9
    orch.reviewer_retries = REVIEW_MAX_RETRIES

    async def fake_pass_rate():
        return 0.8

    async def fake_reconcile(rate):
        return rate

    async def fake_red_flag():
        return "存在：绝对化用语"

    async def fake_review_status():
        return "通过"

    async def fake_write_summary(_pass_rate):
        return None

    async def fake_broadcast(*_args, **_kwargs):
        return None

    orch._get_review_pass_rate = fake_pass_rate
    orch._reconcile_review_pass_rate = fake_reconcile
    orch._get_review_red_flag = fake_red_flag
    orch._get_project_review_status = fake_review_status
    orch._write_auto_review_summary = fake_write_summary
    orch._broadcast = fake_broadcast

    await orch._handle_reviewer_retries()

    assert STATUS_SCHEDULING not in pm.status_updates
    assert pm.status_updates, "红线命中后应写入中止/驳回类状态，而不是静默返回"


@pytest.mark.asyncio
async def test_red_flag_blocks_scheduling_even_when_pass_rate_is_high():
    """红线优先级高于通过率，通过率达标也不能进入排期。"""
    pm = _RecordingProjectMemory()
    orch = Orchestrator("rec_red_flag_high_rate")
    orch._pm = pm
    orch._review_threshold = 0.6
    orch.reviewer_retries = 0

    async def fake_pass_rate():
        return 1.0

    async def fake_reconcile(rate):
        return rate

    async def fake_red_flag():
        return "存在：虚假宣传"

    async def fake_review_status():
        return "通过"

    async def fake_broadcast(*_args, **_kwargs):
        return None

    orch._get_review_pass_rate = fake_pass_rate
    orch._reconcile_review_pass_rate = fake_reconcile
    orch._get_review_red_flag = fake_red_flag
    orch._get_project_review_status = fake_review_status
    orch._broadcast = fake_broadcast

    await orch._handle_reviewer_retries()

    assert STATUS_SCHEDULING not in pm.status_updates

