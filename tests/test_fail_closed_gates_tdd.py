from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.base import BaseAgent
from config import (
    REVIEW_STATUS_APPROVED,
    STATUS_PENDING_REVIEW,
    STATUS_REJECTED,
    STATUS_STRATEGY,
)
from memory.project import BriefProject
from orchestrator import Orchestrator


class GateProjectMemory:
    def __init__(self, project: BriefProject | None = None):
        self.project = project or BriefProject(
            record_id="rec_gate",
            client_name="FailClosed",
            brief_analysis="analysis ready",
            status=STATUS_PENDING_REVIEW,
        )
        self.review_statuses: list[str] = []
        self.status_updates: list[str] = []
        self.pending_meta: list[dict] = []
        self.cleared = False

    async def load(self):
        return self.project

    async def write_review_status(self, status: str):
        self.review_statuses.append(status)
        self.project.review_status = status

    async def write_pending_meta(self, meta: dict):
        self.pending_meta.append(meta)

    async def write_human_feedback(self, feedback: str):
        self.project.human_feedback = feedback

    async def clear_pending_state(self):
        self.cleared = True

    async def update_status(self, status: str):
        self.status_updates.append(status)
        self.project.status = status


class BrokenLoadProjectMemory(GateProjectMemory):
    async def load(self):
        raise RuntimeError("bitable read failed")


@pytest.mark.asyncio
async def test_human_review_gate_project_read_exception_is_not_approved():
    orchestrator = Orchestrator(record_id="rec_gate")
    orchestrator._pm = BrokenLoadProjectMemory()

    outcome = await orchestrator._enter_human_review_gate(resumed=False)

    assert outcome != "approved"


@pytest.mark.asyncio
@pytest.mark.parametrize("poll_status", ["skipped_no_chat", "send_failed"])
async def test_human_review_gate_transport_failures_do_not_default_to_approved(poll_status):
    import tools.request_human_review as review_tool

    pm = GateProjectMemory()
    orchestrator = Orchestrator(record_id="rec_gate")
    orchestrator._pm = pm

    async def fake_poll(*args, **kwargs):
        return {
            "status": poll_status,
            "feedback": "transport failure",
            "msg_id": "",
            "deadline": 0,
            "sent_at": "",
        }

    with patch.object(review_tool, "poll_for_human_reply", fake_poll):
        outcome = await orchestrator._enter_human_review_gate(resumed=False)

    assert outcome != "approved"
    assert REVIEW_STATUS_APPROVED not in pm.review_statuses
    assert STATUS_STRATEGY not in pm.status_updates


@pytest.mark.asyncio
async def test_request_human_review_tool_send_failure_is_not_formatted_as_pass():
    import tools.request_human_review as review_tool
    from tools import AgentContext

    async def fake_poll(*args, **kwargs):
        return {
            "status": "send_failed",
            "feedback": "send_card failed",
            "msg_id": "",
            "deadline": 0,
            "sent_at": "",
        }

    context = AgentContext(
        record_id="rec_gate",
        project_name="FailClosed",
        role_id="account_manager",
    )
    with patch.object(review_tool, "poll_for_human_reply", fake_poll):
        result = await review_tool.execute({"brief_analysis": "analysis ready"}, context)

    assert "send_card failed" in result
    assert "通过" not in result and "approved" not in result.lower()


@pytest.mark.asyncio
async def test_request_human_review_poll_message_read_exception_times_out_not_approved(monkeypatch):
    import tools.request_human_review as review_tool

    class BrokenIM:
        async def send_card_return_id(self, *args, **kwargs):
            return {}, "msg_1"

        async def list_messages(self, *args, **kwargs):
            raise RuntimeError("list_messages failed")

        def is_user_message(self, message):
            return True

        def extract_text_from_message(self, message):
            return "通过"

    monkeypatch.setattr(review_tool, "FEISHU_CHAT_ID", "chat_1")
    monkeypatch.setattr(review_tool, "AUTO_APPROVE_HUMAN_REVIEW", False)
    monkeypatch.setattr(review_tool, "HUMAN_REVIEW_POLL_INTERVAL", 1)
    monkeypatch.setattr(review_tool.asyncio, "sleep", AsyncMock())

    with patch("feishu.im.FeishuIMClient", return_value=BrokenIM()):
        result = await review_tool.poll_for_human_reply("analysis ready", timeout=1)

    assert result["status"] == "timeout"


class AlwaysTextMessage:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = None

    def model_dump(self):
        return {"role": "assistant", "content": self.content}


def llm_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=AlwaysTextMessage(content))])


@pytest.mark.asyncio
async def test_plan_verify_exhausted_gaps_do_not_return_natural_language_success():
    project = BriefProject(
        record_id="rec_plan",
        client_name="PlanVerify",
        status=STATUS_STRATEGY,
    )

    class ProjectMemoryFactory:
        def __call__(self, record_id):
            pm = AsyncMock()
            pm.load = AsyncMock(return_value=project)
            return pm

    agent = BaseAgent(
        "strategist",
        "rec_plan",
        llm_client=object(),
        shared_knowledge="",
        project_memory_factory=ProjectMemoryFactory(),
    )
    agent.soul.max_iterations = 3
    agent._verify_config = {"table": "project", "check_fields": ["strategy"]}
    agent._load_experiences = AsyncMock(return_value="")
    agent._generate_plan = AsyncMock(return_value=[{"scope": "project", "field": "strategy"}])
    agent._verify_plan = AsyncMock(
        return_value=[{"scope": "project", "field": "strategy", "reason": "missing"}]
    )
    agent._llm_call = AsyncMock(
        side_effect=[
            llm_response("I am done"),
            llm_response("Still done"),
            llm_response("Final natural-language success"),
        ]
    )

    output = await agent.run()

    assert "Final natural-language success" not in output
    assert "Plan-Verify" in output or "verify" in output.lower() or "failed" in output.lower()


@pytest.mark.asyncio
async def test_handoff_read_exception_fails_closed():
    orchestrator = Orchestrator(record_id="rec_handoff")
    orchestrator._pm = BrokenLoadProjectMemory()

    ok, reason = await orchestrator._validate_handoff("strategist", "FailClosed")

    assert ok is False
    assert reason


class ToolErrorAgent:
    def __init__(self, role_id, record_id, event_bus=None, task_filter=None):
        self.role_id = role_id
        self.record_id = record_id
        self._used_ask_human = False
        self._messages = [
            {"role": "tool", "content": "错误: FeishuAPIError write_project failed"}
        ]

    async def run(self):
        return "natural language says everything is ok"


@pytest.mark.asyncio
async def test_stage_with_swallowed_tool_error_is_not_marked_ok():
    with patch("orchestrator.BaseAgent", ToolErrorAgent):
        orchestrator = Orchestrator(record_id="rec_tool_error")
        result, agent = await orchestrator._run_stage_with_agent(
            "strategist",
            index=2,
            total=5,
        )

    assert agent is not None
    assert result.ok is False
    assert "tool" in result.error.lower() or "FeishuAPIError" in result.error

