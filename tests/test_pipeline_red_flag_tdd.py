from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    REVIEW_MAX_RETRIES,
    REVIEW_STATUS_APPROVED,
    STATUS_DONE,
    STATUS_REJECTED,
    STATUS_SCHEDULING,
)
from orchestrator import Orchestrator  # noqa: E402


class _RecordingProjectMemory:
    """记录编排器对项目主表的写入，避免触碰真实飞书环境。"""

    def __init__(self, *, review_red_flag: str = "无", review_pass_rate: float = 1.0):
        self.status_updates: list[str] = []
        self.review_summary_writes: list[dict] = []
        self.project = SimpleNamespace(
            client_name="红线测试客户",
            review_red_flag=review_red_flag,
            review_pass_rate=review_pass_rate,
            review_threshold=0.6,
            review_summary="",
            review_status=REVIEW_STATUS_APPROVED,
        )

    async def load(self):
        return self.project

    async def update_status(self, status: str) -> None:
        self.status_updates.append(status)
        self.project.status = status

    async def write_review_summary(
        self,
        content: str,
        pass_rate: float,
        threshold: float | None = None,
        red_flag: str = "",
    ) -> None:
        self.review_summary_writes.append(
            {
                "content": content,
                "pass_rate": pass_rate,
                "threshold": threshold,
                "red_flag": red_flag,
            }
        )
        self.project.review_summary = content
        self.project.review_pass_rate = pass_rate
        self.project.review_threshold = threshold or 0.0
        self.project.review_red_flag = red_flag


class _RowsWithRedFlagFeedback:
    """模拟内容行存在红线反馈，但项目主表 review_red_flag 未同步。"""

    async def list_by_project(self, project_name: str):
        return [
            SimpleNamespace(
                record_id="content_red_flag_001",
                project_name=project_name,
                review_status=REVIEW_STATUS_APPROVED,
                review_feedback="命中广告法禁用词：绝对化用语，存在虚假宣传风险",
            )
        ]


async def _noop_broadcast(*_args, **_kwargs):
    return None


async def _approved_review_status():
    return REVIEW_STATUS_APPROVED


async def _pass_through_reconcile(rate):
    return rate


def _assert_hard_stopped_for_red_flag(pm: _RecordingProjectMemory) -> None:
    assert STATUS_SCHEDULING not in pm.status_updates
    assert STATUS_DONE not in pm.status_updates
    assert STATUS_REJECTED in pm.status_updates


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "red_flag_signal",
    [
        "true",
        "是",
        "存在：绝对化用语",
        "严重合规风险：虚假宣传",
    ],
)
async def test_reviewer_red_flag_signals_hard_stop_even_when_pass_rate_is_high(red_flag_signal):
    """任意等价红线信号都应一票否决，不能因通过率达标进入排期。"""
    pm = _RecordingProjectMemory(review_red_flag=red_flag_signal, review_pass_rate=1.0)
    orch = Orchestrator("rec_red_flag_signal")
    orch._pm = pm
    orch._review_threshold = 0.6
    orch.reviewer_retries = 0
    orch._broadcast = _noop_broadcast
    orch._get_project_review_status = _approved_review_status
    orch._reconcile_review_pass_rate = _pass_through_reconcile

    async def fake_write_summary(_pass_rate):
        return None

    orch._write_auto_review_summary = fake_write_summary

    await orch._handle_reviewer_retries()

    _assert_hard_stopped_for_red_flag(pm)
    assert orch._review_red_flag == red_flag_signal


@pytest.mark.asyncio
async def test_red_flag_is_not_overridden_by_review_max_retries():
    """红线命中时，返工上限不能把项目强制推进到排期或完成。"""
    red_flag_signal = "存在：医疗化表述"
    pm = _RecordingProjectMemory(review_red_flag=red_flag_signal, review_pass_rate=0.2)
    orch = Orchestrator("rec_red_flag_max_retry")
    orch._pm = pm
    orch._review_threshold = 0.9
    orch.reviewer_retries = REVIEW_MAX_RETRIES
    orch._broadcast = _noop_broadcast
    orch._get_project_review_status = _approved_review_status
    orch._reconcile_review_pass_rate = _pass_through_reconcile

    async def fake_write_summary(_pass_rate):
        return None

    orch._write_auto_review_summary = fake_write_summary

    await orch._handle_reviewer_retries()

    _assert_hard_stopped_for_red_flag(pm)
    assert orch._review_red_flag == red_flag_signal


@pytest.mark.asyncio
async def test_red_flag_hard_stop_preserves_risk_state_or_marker():
    """红线命中后需要留下风险状态，不能只消耗返工次数后静默回退。"""
    red_flag_signal = "严重合规风险：编造数据"
    pm = _RecordingProjectMemory(review_red_flag=red_flag_signal, review_pass_rate=0.5)
    orch = Orchestrator("rec_red_flag_marker")
    orch._pm = pm
    orch._review_threshold = 0.9
    orch.reviewer_retries = REVIEW_MAX_RETRIES
    orch._broadcast = _noop_broadcast
    orch._get_project_review_status = _approved_review_status
    orch._reconcile_review_pass_rate = _pass_through_reconcile

    async def fake_write_summary(pass_rate):
        await pm.write_review_summary(
            "红线命中，已记录风险",
            pass_rate,
            threshold=orch._review_threshold,
            red_flag=orch._review_red_flag,
        )

    orch._write_auto_review_summary = fake_write_summary

    await orch._handle_reviewer_retries()

    has_terminal_risk_status = STATUS_REJECTED in pm.status_updates
    has_persisted_risk_marker = any(
        write["red_flag"] == red_flag_signal for write in pm.review_summary_writes
    )
    assert has_terminal_risk_status or has_persisted_risk_marker
    assert STATUS_SCHEDULING not in pm.status_updates
    assert STATUS_DONE not in pm.status_updates


@pytest.mark.asyncio
async def test_row_level_red_flag_blocks_scheduling_when_project_field_is_not_synced(monkeypatch):
    """内容行已暴露红线时，即使项目主表 review_red_flag 仍为无，也不能放行。"""
    import orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "ContentMemory", _RowsWithRedFlagFeedback)
    pm = _RecordingProjectMemory(review_red_flag="无", review_pass_rate=1.0)
    orch = Orchestrator("rec_row_level_red_flag")
    orch._pm = pm
    orch._review_threshold = 0.6
    orch.reviewer_retries = 0
    orch._broadcast = _noop_broadcast
    orch._get_project_review_status = _approved_review_status

    async def fake_write_summary(_pass_rate):
        return None

    orch._write_auto_review_summary = fake_write_summary

    await orch._handle_reviewer_retries()

    _assert_hard_stopped_for_red_flag(pm)
    assert "虚假宣传" in orch._review_red_flag or "绝对化用语" in orch._review_red_flag
