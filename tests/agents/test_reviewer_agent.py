from __future__ import annotations

import pytest

from .conftest import FakeMessage, FakeToolRegistry, fake_response, make_agent, tool_call


@pytest.mark.asyncio
async def test_reviewer_soul_runs_review_with_mocked_rule_lookup(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "reviewer soul: mocked compliance rule lookup",
        [
            "加载 agents/reviewer/soul.md 作为审核 agent",
            "显式传入待审文案、审核策略和项目 context",
            "mock LLM 第 1 轮调用 search_knowledge 查询规则，第 2 轮返回审核结论",
            "验证审核 agent 不依赖飞书/内容表/流水线状态",
        ],
    )
    registry = FakeToolRegistry({
        "search_knowledge": "absolute wording is forbidden",
        "submit_review": "审核结论已写回: status=需修改，维度=[banned_words:✗、brand_tone:✓、platform_spec:✓、dept_style:✓、fact_check:✓]",
    })
    agent = make_agent("reviewer", registry=registry)
    scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="checking compliance rules",
                    tool_calls=[
                        tool_call(
                            "search_knowledge",
                            {"keywords": ["forbidden words", "platform rules"]},
                            call_id="call_1",
                        )
                    ],
                )
            ),
            fake_response(
                FakeMessage(
                    content="submitting review result",
                    tool_calls=[
                        tool_call(
                            "submit_review",
                            {
                                "content_record_id": "rec_content_1",
                                "status": "需修改",
                                "feedback": "Contains absolute wording 'best product' — remove or replace.",
                                "violated_rules": ["absolute wording: best"],
                                "dimensions": {
                                    "banned_words": "不通过",
                                    "brand_tone": "通过",
                                    "platform_spec": "通过",
                                    "dept_style": "通过",
                                    "fact_check": "通过",
                                },
                            },
                            call_id="call_2",
                        )
                    ],
                )
            ),
            fake_response(FakeMessage(content="Review failed: remove absolute wording")),
        ],
    )

    result = await agent.run(
        input_data="Draft says this is the best product in the market.",
        strategy={"checks": ["forbidden_words", "factual_claims"]},
        context={"record_id": "rec_review", "project_name": "Launch Client"},
    )

    assert result.role_id == "reviewer"
    assert result.output == "Review failed: remove absolute wording"
    assert result.missing_required_tools == []
    assert registry.calls[0]["tool_name"] == "search_knowledge"
    assert registry.calls[0]["role_id"] == "reviewer"
    assert registry.calls[1]["tool_name"] == "submit_review"


@pytest.mark.asyncio
async def test_reviewer_unit_result_exposes_missing_rule_lookup(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "reviewer soul: missing rule lookup is surfaced",
        [
            "加载 reviewer soul 后直接 mock 审核通过",
            "故意不调用 search_knowledge",
            "验证 AgentResult.missing_required_tools 返回 search_knowledge",
        ],
    )
    agent = make_agent("reviewer", registry=FakeToolRegistry())
    scripted_llm(agent, [fake_response(FakeMessage(content="Review passed"))])

    result = await agent.run(
        input_data="Draft text.",
        strategy={},
        context={"record_id": "rec_review"},
    )

    assert result.output == "Review passed"
    # reviewer 现在要求同时调用 search_knowledge 和 submit_review
    assert set(result.missing_required_tools) == {"search_knowledge", "submit_review"}
