from __future__ import annotations

import pytest

from .conftest import FakeMessage, FakeToolRegistry, fake_response, make_agent, tool_call


@pytest.mark.asyncio
async def test_copywriter_soul_requires_reference_and_knowledge_checks(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "copywriter soul: required reference + rule checks",
        [
            "加载 agents/copywriter/soul.md，并启用 task_filter platform=抖音",
            "显式传入文案任务 input_data、平台策略和项目 context",
            "mock LLM 要求依次调用 search_reference 与 search_knowledge",
            "验证抖音平台 soul patch 进入 prompt，且必调工具不缺失",
        ],
    )
    registry = FakeToolRegistry(
        {
            "search_reference": "reference pattern",
            "search_knowledge": "platform rule",
        }
    )
    agent = make_agent(
        "copywriter",
        registry=registry,
        task_filter={"platform": "抖音"},
    )
    llm = scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="gathering examples and rules",
                    tool_calls=[
                        tool_call("search_reference", {"keywords": ["launch hook"]}, "call_ref"),
                        tool_call("search_knowledge", {"keywords": ["compliance"]}, "call_rule"),
                    ],
                )
            ),
            fake_response(FakeMessage(content="Short video script draft")),
        ],
    )

    result = await agent.run(
        input_data="Write one Douyin launch script.",
        strategy={"platform": "抖音", "tone": "sharp"},
        context={"record_id": "rec_copy", "project_name": "Launch Client"},
    )

    assert agent._platform_patch_used is True
    assert result.output == "Short video script draft"
    assert result.missing_required_tools == []
    assert [call["tool_name"] for call in registry.calls] == [
        "search_reference",
        "search_knowledge",
    ]
    system_prompt = llm["calls"][0]["messages"][0]["content"]
    assert "抖音" in system_prompt
    assert "sharp" in system_prompt


@pytest.mark.asyncio
async def test_copywriter_reports_missing_required_tools_in_unit_result(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "copywriter soul: missing required tools is surfaced",
        [
            "加载 copywriter soul 后直接 mock 最终文案输出",
            "故意不调用 search_reference/search_knowledge",
            "验证 AgentResult.missing_required_tools 明确暴露缺失项",
        ],
    )
    agent = make_agent("copywriter", registry=FakeToolRegistry())
    scripted_llm(
        agent,
        [fake_response(FakeMessage(content="draft without checks"))],
    )

    result = await agent.run(
        input_data="Write one post.",
        strategy={},
        context={"record_id": "rec_copy"},
    )

    assert result.output == "draft without checks"
    assert result.missing_required_tools == ["search_reference", "search_knowledge"]
