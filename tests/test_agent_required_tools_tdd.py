from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import orchestrator as orchestrator_module
from orchestrator import Orchestrator


class _AgentMissingRequiredTools:
    """模拟 Agent 正常返回文本，但仍缺少必调工具。"""

    def __init__(self, role_id: str, record_id: str, event_bus=None):
        self.role_id = role_id
        self.record_id = record_id
        self._used_ask_human = False
        self.missing_required_tools = ["submit_review"]

    async def run(self):
        return "已完成，但缺少 submit_review"


@pytest.mark.asyncio
async def test_orchestrator_marks_stage_failed_when_required_tools_missing(monkeypatch):
    """必调工具缺失时，阶段不能因为 agent.run 正常返回就被标记成功。"""
    monkeypatch.setattr(orchestrator_module, "BaseAgent", _AgentMissingRequiredTools)

    orch = Orchestrator("rec_missing_tools")
    result, agent = await orch._run_stage_with_agent(
        "reviewer",
        index=1,
        total=1,
    )

    assert agent is not None
    assert result.ok is False
    assert "submit_review" in result.error


class _AgentWithWarningOnlyOutput:
    """模拟当前 BaseAgent 的 warning-only 输出形态。"""

    def __init__(self, role_id: str, record_id: str, event_bus=None):
        self.role_id = role_id
        self.record_id = record_id
        self._used_ask_human = False

    async def run(self):
        return "\n\n⚠️ 合规警告：本次执行未调用必需工具 ['write_project']，输出可能未经必要审核流程。"


@pytest.mark.asyncio
async def test_orchestrator_treats_warning_only_required_tool_output_as_failure(monkeypatch):
    """warning-only 不是成功产出，Orchestrator 应识别并失败。"""
    monkeypatch.setattr(orchestrator_module, "BaseAgent", _AgentWithWarningOnlyOutput)

    orch = Orchestrator("rec_warning_only")
    result, _agent = await orch._run_stage_with_agent(
        "account_manager",
        index=1,
        total=1,
    )

    assert result.ok is False
    assert "必需工具" in result.error or "required" in result.error.lower()

