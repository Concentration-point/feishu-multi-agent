from __future__ import annotations

import pytest

from .conftest import FakeMessage, FakeToolRegistry, fake_response, make_agent, tool_call


@pytest.mark.asyncio
async def test_strategist_soul_runs_full_research_to_matrix_chain(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "strategist soul: 内部经验 + 外部情报 + 矩阵落表",
        [
            "加载 agents/strategist/soul.md，无 task_filter（角色级直跑）",
            "显式传入 Brief 解读 input_data、项目类型 strategy 与 record_id context",
            "mock LLM：第 1 轮调 search_knowledge + search_web，第 2 轮调 web_fetch，",
            "  第 3 轮 batch_create_content + write_project + update_status + send_message",
            "验证内外双轨调研 + 内容行批创 + 状态推进至撰写中 全链路工具序列",
        ],
    )
    registry = FakeToolRegistry(
        {
            "search_knowledge": "历史方案：双十一爆款矩阵参考",
            "search_web": "https://example.com/competitor 摘要 + 链接列表",
            "web_fetch": "竞品在小红书集中投放种草笔记",
            "batch_create_content": "已批量创建 4 条内容",
            "write_project": "策略方案已写入项目主表",
            "update_status": "状态已更新为 撰写中",
            "send_message": "群消息已发送",
        }
    )
    agent = make_agent("strategist", registry=registry)
    llm = scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="先查内部历史 + 外部情报",
                    tool_calls=[
                        tool_call(
                            "search_knowledge",
                            {"keywords": ["电商大促", "内容矩阵"]},
                            "call_kn",
                        ),
                        tool_call(
                            "search_web",
                            {
                                "query": "2025 国货美妆 双十一 营销策略",
                                "topic": "news",
                                "max_results": 5,
                            },
                            "call_sw",
                        ),
                    ],
                )
            ),
            fake_response(
                FakeMessage(
                    content="对权威竞品页深抓",
                    tool_calls=[
                        tool_call(
                            "web_fetch",
                            {
                                "url": "https://example.com/competitor",
                                "prompt": "提取竞品投放节奏与主打平台",
                            },
                            "call_wf",
                        )
                    ],
                )
            ),
            fake_response(
                FakeMessage(
                    content="矩阵落表 + 状态推进",
                    tool_calls=[
                        tool_call(
                            "batch_create_content",
                            {"contents": [{"标题": "种草笔记 1", "平台": "小红书"}]},
                            "call_bc",
                        ),
                        tool_call(
                            "write_project",
                            {"策略方案": "内容矩阵已生成"},
                            "call_wp",
                        ),
                        tool_call(
                            "update_status",
                            {"status": "撰写中"},
                            "call_us",
                        ),
                        tool_call(
                            "send_message",
                            {"text": "策略已完成"},
                            "call_sm",
                        ),
                    ],
                )
            ),
            fake_response(FakeMessage(content="策略制定完成，已通知文案接力")),
        ],
    )

    result = await agent.run(
        input_data="客户 Brief：双十一国货美妆大促，主打 Z 世代",
        strategy={"项目类型": "电商大促", "目标平台": ["小红书", "抖音"]},
        context={"record_id": "rec_strategist", "project_name": "国货美妆双十一"},
    )

    assert result.role_id == "strategist"
    assert result.output == "策略制定完成，已通知文案接力"
    assert result.meta["mode"] == "unit"
    assert result.meta["project_name"] == "国货美妆双十一"
    # 策略师无硬性必调工具白名单（_REQUIRED_TOOL_CALLS 未定义），缺失列表恒为空
    assert result.missing_required_tools == []
    # 验证全链路工具调用序列：内外调研 → 矩阵 → 状态 → 广播
    called_tools = [call["tool_name"] for call in registry.calls]
    assert called_tools == [
        "search_knowledge",
        "search_web",
        "web_fetch",
        "batch_create_content",
        "write_project",
        "update_status",
        "send_message",
    ]
    # 状态推进确实推到「撰写中」
    update_status_call = next(c for c in registry.calls if c["tool_name"] == "update_status")
    assert update_status_call["params"]["status"] == "撰写中"
    # System prompt 应注入 strategy 字段
    system_prompt = llm["calls"][0]["messages"][0]["content"]
    assert "电商大促" in system_prompt
    assert "小红书" in system_prompt


@pytest.mark.asyncio
async def test_strategist_soul_loads_with_only_internal_research(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "strategist soul: 仅内部调研也能直出策略（边界）",
        [
            "mock LLM 跳过外网调研，直接基于内部经验出方案",
            "验证 BaseAgent 不会因为缺少 search_web 调用而报错",
            "验证 missing_required_tools 仍为空（strategist 无硬约束）",
        ],
    )
    registry = FakeToolRegistry({"search_knowledge": "历史经验命中"})
    agent = make_agent("strategist", registry=registry)
    scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="只查内部",
                    tool_calls=[
                        tool_call("search_knowledge", {"keywords": ["策略"]}, "call_only_kn")
                    ],
                )
            ),
            fake_response(FakeMessage(content="策略草案：基于内部经验")),
        ],
    )

    result = await agent.run(
        input_data="紧急 Brief，时间紧",
        strategy={"项目类型": "日常运营"},
        context={"record_id": "rec_strategist_min"},
    )

    assert result.output == "策略草案：基于内部经验"
    assert result.missing_required_tools == []
    assert [c["tool_name"] for c in registry.calls] == ["search_knowledge"]
