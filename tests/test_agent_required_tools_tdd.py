from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import orchestrator as orchestrator_module
from agents.base import AgentResult, BaseAgent
from orchestrator import Orchestrator


class _AgentMissingRequiredTools:
    """模拟 Agent 正常返回文本，但仍缺少必调工具。"""

    def __init__(self, role_id: str, record_id: str, event_bus=None):
        self.role_id = role_id
        self.record_id = record_id
        self._used_ask_human = False
        self.missing_required_tools = ["submit_review"]

    async def run(self):
        return "我已经审核完成"


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


class _AgentReturningStructuredMissingTools:
    """模拟 BaseAgent 以结构化 AgentResult 暴露必调工具缺失。"""

    def __init__(self, role_id: str, record_id: str, event_bus=None):
        self.role_id = role_id
        self.record_id = record_id
        self._used_ask_human = False

    async def run(self):
        return AgentResult(
            role_id=self.role_id,
            output="我已经审核完成",
            messages=[],
            tool_calls=[],
            missing_required_tools=["submit_review"],
            meta={"required_tool_check": {"ok": False, "missing": ["submit_review"]}},
        )


@pytest.mark.asyncio
async def test_orchestrator_fails_on_structured_required_tool_violation(monkeypatch):
    """必调工具校验应通过结构化失败信号传递，而不是依赖 warning 文案。"""
    monkeypatch.setattr(orchestrator_module, "BaseAgent", _AgentReturningStructuredMissingTools)

    orch = Orchestrator("rec_structured_missing_tools")
    result, agent = await orch._run_stage_with_agent(
        "reviewer",
        index=1,
        total=1,
    )

    assert agent is not None
    assert result.ok is False
    assert "submit_review" in result.error
    assert "required" in result.error.lower() or "必调" in result.error


def test_reviewer_partial_submit_review_is_incomplete_required_tool_call():
    """reviewer 只审核部分内容行时，submit_review 应被标记为未完整满足。"""
    agent = object.__new__(BaseAgent)
    agent.role_id = "reviewer"
    messages = [
        {
            "role": "assistant",
            "content": "先读取规则和待审内容",
            "tool_calls": [
                {
                    "id": "call_rule",
                    "type": "function",
                    "function": {
                        "name": "search_knowledge",
                        "arguments": json.dumps({"keywords": ["合规规则"]}, ensure_ascii=False),
                    },
                },
                {
                    "id": "call_list",
                    "type": "function",
                    "function": {
                        "name": "list_content",
                        "arguments": "{}",
                    },
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_rule",
            "content": "规则已读取",
        },
        {
            "role": "tool",
            "tool_call_id": "call_list",
            "content": json.dumps(
                [
                    {"record_id": "content_1", "title": "小红书首发"},
                    {"record_id": "content_2", "title": "抖音短视频"},
                ],
                ensure_ascii=False,
            ),
        },
        {
            "role": "assistant",
            "content": "只提交第一条审核",
            "tool_calls": [
                {
                    "id": "call_review_1",
                    "type": "function",
                    "function": {
                        "name": "submit_review",
                        "arguments": json.dumps(
                            {
                                "content_record_id": "content_1",
                                "status": "通过",
                                "feedback": "第一条通过",
                                "violated_rules": [],
                                "dimensions": {
                                    "banned_words": "通过",
                                    "brand_tone": "通过",
                                    "platform_spec": "通过",
                                    "dept_style": "通过",
                                    "fact_check": "通过",
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_review_1",
            "content": "审核结论已写回",
        },
    ]

    missing = agent._check_required_tools(messages)

    assert missing == ["submit_review"]
    assert agent._get_unreviewed_rows(messages) == [
        {"record_id": "content_2", "title": "抖音短视频"},
    ]


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
