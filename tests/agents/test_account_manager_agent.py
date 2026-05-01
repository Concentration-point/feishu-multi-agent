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


@pytest.mark.asyncio
async def test_account_manager_can_call_ask_human_for_blocking_info(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "account_manager ask_human: blocking info path",
        [
            "构造一个缺少关键信息的 BBQ brief 场景",
            "mock LLM 第 1 轮调用 ask_human，第 2 轮输出最终 Brief analysis",
            "验证 ask_human 工具被真实调度，且 question / choices 参数完整透传",
        ],
    )
    registry = FakeToolRegistry({"ask_human": "人类已选择：预算 3000-8000 / 先做小红书和大众点评"})
    agent = make_agent("account_manager", registry=registry)
    scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="需要先确认阻塞信息",
                    tool_calls=[
                        tool_call(
                            "ask_human",
                            {
                                "question": "烧烤店 brief 缺少预算和重点平台，先确认后再继续解读。",
                                "choices": [
                                    "预算 3000 以内 / 只做到店引流",
                                    "预算 3000-8000 / 先做小红书和大众点评",
                                    "预算 8000 以上 / 增加短视频拍摄",
                                ],
                                "title": "需要确认缺失信息",
                            },
                            "call_ask_human",
                        )
                    ],
                )
            ),
            fake_response(FakeMessage(content="Brief analysis ready with confirmed budget and platform.")),
        ],
    )

    result = await agent.run(
        input_data="一家新开的烧烤店，想做夜宵引流，但没有给预算和重点平台。",
        strategy={"deliverable": "brief_analysis", "must_extract": ["budget", "platform"]},
        context={"record_id": "rec_am_ask", "project_name": "BBQ AskHuman"},
    )

    assert result.role_id == "account_manager"
    assert result.output == "Brief analysis ready with confirmed budget and platform."
    assert result.meta["mode"] == "unit"
    assert result.meta["project_name"] == "BBQ AskHuman"
    assert result.missing_required_tools == []
    assert [call["tool_name"] for call in registry.calls] == ["ask_human"]
    assert registry.calls[0]["params"]["title"] == "需要确认缺失信息"
    assert "缺少预算和重点平台" in registry.calls[0]["params"]["question"]
    assert len(registry.calls[0]["params"]["choices"]) == 3
    assert registry.calls[0]["record_id"] == "rec_am_ask"
    assert registry.calls[0]["project_name"] == "BBQ AskHuman"
    assert registry.calls[0]["role_id"] == "account_manager"
