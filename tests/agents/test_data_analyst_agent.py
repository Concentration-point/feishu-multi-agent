from __future__ import annotations

import pytest

from .conftest import FakeMessage, FakeToolRegistry, fake_response, make_agent, tool_call


@pytest.mark.asyncio
async def test_data_analyst_soul_runs_weekly_report_full_chain(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "data_analyst soul: 周报全链路（query → generate doc → send）",
        [
            "加载 agents/data_analyst/soul.md，task_filter={report_type: weekly}",
            "显式传入分析窗口与目标 strategy，独立 agent 不依赖项目主表",
            "mock LLM：第 1 轮 query_project_stats，第 2 轮 generate_report_doc + send_report",
            "验证跨项目分析链路完整，且 soul 声明的工具白名单全部命中",
        ],
    )
    registry = FakeToolRegistry(
        {
            "query_project_stats": (
                "{\"项目总数\":12,\"已完成\":8,\"审核通过率均值\":0.85,"
                "\"红线命中\":0,\"经验池条目\":42}"
            ),
            "generate_report_doc": (
                "https://feishu.example.com/docx/abc 飞书文档已生成"
            ),
            "send_report": "群消息推送成功",
        }
    )
    agent = make_agent(
        "data_analyst",
        registry=registry,
        task_filter={"report_type": "weekly"},
    )
    llm = scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="先拉全量统计",
                    tool_calls=[
                        tool_call(
                            "query_project_stats",
                            {"window": "last_7_days"},
                            "call_q",
                        )
                    ],
                )
            ),
            fake_response(
                FakeMessage(
                    content="生成飞书文档并推送",
                    tool_calls=[
                        tool_call(
                            "generate_report_doc",
                            {
                                "title": "智策传媒·运营周报（2026-04-30）",
                                "report_type": "weekly",
                                "key_findings": [
                                    "完成率 67%",
                                    "审核通过率 0.85，红线命中 0",
                                ],
                            },
                            "call_g",
                        ),
                        tool_call(
                            "send_report",
                            {
                                "summary": "本周完成 8/12 项目",
                                "doc_url": "https://feishu.example.com/docx/abc",
                            },
                            "call_s",
                        ),
                    ],
                )
            ),
            fake_response(
                FakeMessage(
                    content=(
                        "# 智策传媒·运营周报\n"
                        "- 项目总数：12，已完成 8\n"
                        "- 审核通过率：0.85，红线命中 0\n"
                        "- 已推送至飞书群聊"
                    )
                )
            ),
        ],
    )

    result = await agent.run(
        input_data="生成本周运营周报",
        strategy={"report_type": "weekly", "audience": "团队全员"},
        context={"record_id": "rec_data_weekly", "project_name": "运营中台"},
    )

    assert result.role_id == "data_analyst"
    assert "运营周报" in result.output
    assert result.meta["mode"] == "unit"
    # 数据分析师无强制必调工具
    assert result.missing_required_tools == []
    called = [c["tool_name"] for c in registry.calls]
    assert called == ["query_project_stats", "generate_report_doc", "send_report"]
    # 工具上下文角色对齐
    assert all(c["role_id"] == "data_analyst" for c in registry.calls)
    # System prompt 注入了 report_type
    system_prompt = llm["calls"][0]["messages"][0]["content"]
    assert "weekly" in system_prompt


@pytest.mark.asyncio
async def test_data_analyst_soul_supports_insight_report_type(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "data_analyst soul: insight 报告类型（异常下钻）",
        [
            "task_filter={report_type: insight}，聚焦单一异常现象",
            "mock LLM 调 query_project_stats → generate_report_doc + send_report",
            "验证不同 report_type 下 soul 仍能自驱完成分析输出",
        ],
    )
    registry = FakeToolRegistry(
        {
            "query_project_stats": "{\"电商大促\":{\"通过率\":0.62}}",
            "generate_report_doc": "https://feishu.example.com/docx/insight",
            "send_report": "推送成功",
        }
    )
    agent = make_agent(
        "data_analyst",
        registry=registry,
        task_filter={"report_type": "insight"},
    )
    scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="拉数据并分析",
                    tool_calls=[
                        tool_call("query_project_stats", {"focus": "电商大促"}, "call_q"),
                    ],
                )
            ),
            fake_response(
                FakeMessage(
                    content="生成洞察报告",
                    tool_calls=[
                        tool_call(
                            "generate_report_doc",
                            {"title": "数据洞察·电商大促通过率下降", "report_type": "insight"},
                            "call_g",
                        ),
                        tool_call(
                            "send_report",
                            {"summary": "电商大促通过率 0.62，建议加强合规自检"},
                            "call_s",
                        ),
                    ],
                )
            ),
            fake_response(
                FakeMessage(
                    content="数据洞察·电商大促通过率下降已推送"
                )
            ),
        ],
    )

    result = await agent.run(
        input_data="深挖电商大促异常",
        strategy={"report_type": "insight"},
        context={"record_id": "rec_data_insight"},
    )

    assert "洞察" in result.output
    called = [c["tool_name"] for c in registry.calls]
    assert called == [
        "query_project_stats",
        "generate_report_doc",
        "send_report",
    ]
