from __future__ import annotations

import pytest

from .conftest import FakeMessage, FakeToolRegistry, fake_response, make_agent, tool_call


@pytest.mark.asyncio
async def test_account_manager_soul_runs_with_explicit_input_context_strategy(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "account_manager soul: explicit unit run",
        [
            "加载 agents/account_manager/soul.md 作为具体客户经理 agent",
            "显式传入 input_data/strategy/context，不读取项目主表或流水线状态",
            "mock LLM 第 1 轮要求调用 search_knowledge，第 2 轮返回 Brief analysis",
            "验证工具上下文 record_id/project_name/role_id 和最终 AgentResult",
        ],
    )
    registry = FakeToolRegistry({"search_knowledge": "matched prior brief rule"})
    agent = make_agent("account_manager", registry=registry)
    llm = scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="checking internal rules",
                    tool_calls=[
                        tool_call(
                            "search_knowledge",
                            {"keywords": ["brief", "launch"]},
                        )
                    ],
                )
            ),
            fake_response(FakeMessage(content="Brief analysis ready")),
        ],
    )

    result = await agent.run(
        input_data="Client wants a product launch campaign.",
        strategy={"deliverable": "brief_analysis", "must_extract": ["goal", "risk"]},
        context={"record_id": "rec_am", "project_name": "Launch Client"},
    )

    assert result.role_id == "account_manager"
    assert result.output == "Brief analysis ready"
    assert result.meta["mode"] == "unit"
    assert result.meta["project_name"] == "Launch Client"
    assert result.missing_required_tools == []
    assert registry.calls == [
        {
            "tool_name": "search_knowledge",
            "params": {"keywords": ["brief", "launch"]},
            "record_id": "rec_am",
            "project_name": "Launch Client",
            "role_id": "account_manager",
        }
    ]
    first_messages = llm["calls"][0]["messages"]
    assert "deliverable" in first_messages[0]["content"]
    assert "Client wants a product launch campaign." in first_messages[1]["content"]
