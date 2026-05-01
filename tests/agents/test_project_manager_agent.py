from __future__ import annotations

import pytest

from .conftest import FakeMessage, FakeToolRegistry, fake_response, make_agent, tool_call


@pytest.mark.asyncio
async def test_project_manager_soul_schedules_only_passed_contents(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "project_manager soul: 仅对审核通过内容排期 + 写交付摘要 + 推进至已完成",
        [
            "加载 agents/project_manager/soul.md 作为项目经理 agent",
            "显式传入审核结果摘要 input_data 与项目 context",
            "mock LLM：第 1 轮 read_project + list_content，第 2 轮 write_content + write_project + update_status + send_message",
            "验证只对「通过」内容写 write_content（不强制断言 LLM 决策，但断言调用链对齐 soul 设计）",
        ],
    )
    registry = FakeToolRegistry(
        {
            "read_project": "项目主表：审核通过率 0.9，状态=审核中",
            "list_content": "[{序号:1,审核状态:通过},{序号:2,审核状态:驳回}]",
            "write_content": "已写回计划发布日期",
            "write_project": "交付摘要已写入",
            "update_status": "状态已更新为 已完成",
            "send_message": "群消息已发送",
        }
    )
    agent = make_agent("project_manager", registry=registry)
    llm = scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="先读项目主表与内容行",
                    tool_calls=[
                        tool_call("read_project", {}, "call_rp"),
                        tool_call("list_content", {}, "call_lc"),
                    ],
                )
            ),
            fake_response(
                FakeMessage(
                    content="只对审核通过内容写排期",
                    tool_calls=[
                        tool_call(
                            "write_content",
                            {"序号": 1, "计划发布日期": "2026-05-08"},
                            "call_wc1",
                        ),
                        tool_call(
                            "write_project",
                            {"交付摘要": "## 1. 项目完成情况\n通过 1 条 / 驳回 1 条"},
                            "call_wp",
                        ),
                        tool_call(
                            "update_status",
                            {"status": "已完成"},
                            "call_us",
                        ),
                        tool_call(
                            "send_message",
                            {"text": "排期完成"},
                            "call_sm",
                        ),
                    ],
                )
            ),
            fake_response(FakeMessage(content="项目本轮交付完成")),
        ],
    )

    result = await agent.run(
        input_data="审核通过率 0.9，1 条通过 / 1 条驳回",
        strategy={"deliverable": "交付摘要"},
        context={"record_id": "rec_pm", "project_name": "国货美妆双十一"},
    )

    assert result.role_id == "project_manager"
    assert result.output == "项目本轮交付完成"
    assert result.meta["mode"] == "unit"
    # 项目经理无强制必调工具
    assert result.missing_required_tools == []
    called = [c["tool_name"] for c in registry.calls]
    assert called == [
        "read_project",
        "list_content",
        "write_content",
        "write_project",
        "update_status",
        "send_message",
    ]
    # 写排期日期的目标是序号 1（通过），不是序号 2（驳回）
    wc_call = next(c for c in registry.calls if c["tool_name"] == "write_content")
    assert wc_call["params"]["序号"] == 1
    assert "计划发布日期" in wc_call["params"]
    # 状态推进到「已完成」
    us_call = next(c for c in registry.calls if c["tool_name"] == "update_status")
    assert us_call["params"]["status"] == "已完成"
    # 工具上下文携带正确角色
    assert all(c["role_id"] == "project_manager" for c in registry.calls)
    # System prompt 注入了 deliverable 字段
    system_prompt = llm["calls"][0]["messages"][0]["content"]
    assert "交付摘要" in system_prompt


@pytest.mark.asyncio
async def test_project_manager_soul_handles_no_schedulable_content(
    scripted_llm,
    agent_test_log,
):
    agent_test_log(
        "project_manager soul: 全部内容驳回时不强行推进已完成（边界）",
        [
            "mock LLM 在读到全驳回后只发广播说明无法完成",
            "验证 BaseAgent 不会自动追加任何工具调用",
            "验证 unit 模式下 tool_calls 数量 = LLM 实际声明数量",
        ],
    )
    registry = FakeToolRegistry(
        {
            "read_project": "审核通过率 0.0",
            "list_content": "[{序号:1,审核状态:驳回}]",
            "send_message": "已广播：无可排期内容",
        }
    )
    agent = make_agent("project_manager", registry=registry)
    scripted_llm(
        agent,
        [
            fake_response(
                FakeMessage(
                    content="读取后发现无可排期",
                    tool_calls=[
                        tool_call("read_project", {}, "call_rp"),
                        tool_call("list_content", {}, "call_lc"),
                        tool_call(
                            "send_message",
                            {"text": "无可排期内容，项目暂未完成"},
                            "call_sm",
                        ),
                    ],
                )
            ),
            fake_response(FakeMessage(content="本轮无法交付，请客户经理跟进驳回原因")),
        ],
    )

    result = await agent.run(
        input_data="全部内容被驳回",
        strategy={},
        context={"record_id": "rec_pm_empty"},
    )

    assert result.output == "本轮无法交付，请客户经理跟进驳回原因"
    called = [c["tool_name"] for c in registry.calls]
    assert "update_status" not in called
    assert "write_content" not in called
    assert "write_project" not in called
