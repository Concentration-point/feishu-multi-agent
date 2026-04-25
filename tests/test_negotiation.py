"""Agent 协商机制单元测试。

验证点：
1. NegotiationManager 消息管理与轮次管理
2. negotiate 工具的 SCHEMA 和基础验证
3. Orchestrator 协商检查点触发逻辑
4. 协商配置常量完备性
5. soul.md negotiate 工具白名单
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory.negotiation import (
    NegotiationManager,
    NegotiationMessage,
    NegotiationRound,
    NEGOTIATION_TYPE_LABELS,
)
from config import NEGOTIATION_CHECKPOINTS, NEGOTIATION_MAX_ROUNDS


# ── 1. NegotiationMessage 测试 ──

def test_negotiation_message_creation():
    """创建协商消息并验证字段。"""
    msg = NegotiationMessage(
        sender_role="strategist",
        receiver_role="account_manager",
        msg_type="question",
        content="Brief 中目标人群描述是否可以更细化？",
    )
    assert msg.sender_role == "strategist"
    assert msg.receiver_role == "account_manager"
    assert msg.msg_type == "question"
    assert msg.timestamp > 0


def test_negotiation_message_display():
    """format_display 生成可读文本。"""
    msg = NegotiationMessage(
        sender_role="reviewer",
        receiver_role="copywriter",
        msg_type="proposal",
        content="建议修改第二段的绝对化用语",
    )
    names = {"reviewer": "审核", "copywriter": "文案"}
    display = msg.format_display(names)
    assert "审核" in display
    assert "文案" in display
    assert "建议" in display


def test_negotiation_message_to_dict():
    """to_dict 返回可序列化字典。"""
    msg = NegotiationMessage(
        sender_role="a", receiver_role="b",
        msg_type="accept", content="ok",
    )
    d = msg.to_dict()
    assert d["sender_role"] == "a"
    assert d["msg_type"] == "accept"
    assert "timestamp" in d


# ── 2. NegotiationManager 测试 ──

def test_manager_add_message():
    """添加消息并查看历史。"""
    nm = NegotiationManager()
    msg = NegotiationMessage("a", "b", "question", "测试")
    nm.add_message(msg)
    assert len(nm.messages) == 1
    assert nm.messages[0].content == "测试"


def test_manager_start_and_close_round():
    """开启和关闭一轮协商。"""
    nm = NegotiationManager()
    init = NegotiationMessage("strategist", "account_manager", "proposal", "建议细化人群")
    rnd = nm.start_round(init)
    assert isinstance(rnd, NegotiationRound)
    assert not rnd.resolved

    resp = NegotiationMessage("account_manager", "strategist", "accept", "同意，已补充")
    nm.close_round(rnd, resp)
    assert rnd.resolved
    assert rnd.responder_msg is not None
    assert len(nm.messages) == 2


def test_manager_round_not_resolved_on_concede():
    """concede 类型也标记为 resolved。"""
    nm = NegotiationManager()
    init = NegotiationMessage("a", "b", "question", "q")
    rnd = nm.start_round(init)
    resp = NegotiationMessage("b", "a", "concede", "让步")
    nm.close_round(rnd, resp)
    assert rnd.resolved is True


def test_manager_get_history_between():
    """获取两个角色之间的历史。"""
    nm = NegotiationManager()
    nm.add_message(NegotiationMessage("a", "b", "question", "q1"))
    nm.add_message(NegotiationMessage("b", "a", "accept", "ok"))
    nm.add_message(NegotiationMessage("c", "a", "proposal", "unrelated"))

    history = nm.get_history_between("a", "b")
    assert len(history) == 2

    history_ca = nm.get_history_between("c", "a")
    assert len(history_ca) == 1


def test_manager_format_for_prompt_empty():
    """无消息时 format_for_prompt 返回空字符串。"""
    nm = NegotiationManager()
    assert nm.format_for_prompt() == ""


def test_manager_format_for_prompt_with_messages():
    """有消息时 format_for_prompt 包含协商记录标题。"""
    nm = NegotiationManager()
    nm.add_message(NegotiationMessage("a", "b", "question", "测试问题"))
    result = nm.format_for_prompt()
    assert "团队协商记录" in result
    assert "测试问题" in result


def test_manager_format_round_for_broadcast():
    """格式化一轮协商为广播文本。"""
    nm = NegotiationManager()
    init = NegotiationMessage("strategist", "account_manager", "proposal", "建议细化")
    rnd = nm.start_round(init)
    resp = NegotiationMessage("account_manager", "strategist", "accept", "同意")
    nm.close_round(rnd, resp)

    names = {"strategist": "策略师", "account_manager": "客户经理"}
    text = nm.format_round_for_broadcast(rnd, names)
    assert "策略师" in text
    assert "客户经理" in text
    assert "已达成共识" in text


# ── 3. negotiate 工具 SCHEMA 测试 ──

def test_negotiate_tool_schema():
    """negotiate 工具 SCHEMA 结构正确。"""
    from tools.negotiate import SCHEMA
    func = SCHEMA["function"]
    assert func["name"] == "negotiate"
    params = func["parameters"]["properties"]
    assert "target_role" in params
    assert "message_type" in params
    assert "content" in params
    assert set(params["message_type"]["enum"]) == {"question", "proposal", "accept", "concede"}


def test_negotiate_tool_registered():
    """negotiate 工具被 ToolRegistry 发现。"""
    from tools import ToolRegistry
    registry = ToolRegistry()
    assert "negotiate" in registry.tool_names


# ── 4. 配置常量测试 ──

def test_negotiation_checkpoints_structure():
    """NEGOTIATION_CHECKPOINTS 为 (str, str) 元组列表。"""
    assert isinstance(NEGOTIATION_CHECKPOINTS, list)
    for item in NEGOTIATION_CHECKPOINTS:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], str)
        assert isinstance(item[1], str)


def test_negotiation_max_rounds_positive():
    """NEGOTIATION_MAX_ROUNDS 为正整数。"""
    assert isinstance(NEGOTIATION_MAX_ROUNDS, int)
    assert NEGOTIATION_MAX_ROUNDS > 0


def test_negotiation_type_labels_complete():
    """所有协商类型都有中文标签。"""
    expected_types = {"question", "proposal", "accept", "concede"}
    assert set(NEGOTIATION_TYPE_LABELS.keys()) == expected_types


# ── 5. soul.md negotiate 工具白名单测试 ──

_PIPELINE_ROLES = ["account_manager", "strategist", "copywriter", "reviewer", "project_manager"]

@pytest.mark.parametrize("role_id", _PIPELINE_ROLES)
def test_soul_has_negotiate_tool(role_id: str):
    """流水线中的 5 个角色 soul.md 都声明了 negotiate 工具。"""
    soul_path = ROOT / "agents" / role_id / "soul.md"
    assert soul_path.exists(), f"{role_id}/soul.md 不存在"
    text = soul_path.read_text(encoding="utf-8")
    # 检查 frontmatter 中的 tools 列表
    assert "negotiate" in text, f"{role_id}/soul.md 未声明 negotiate 工具"


@pytest.mark.parametrize("role_id", _PIPELINE_ROLES)
def test_soul_has_negotiation_style(role_id: str):
    """流水线中的 5 个角色 soul.md 都包含协商风格段落。"""
    soul_path = ROOT / "agents" / role_id / "soul.md"
    text = soul_path.read_text(encoding="utf-8")
    assert "协商风格" in text, f"{role_id}/soul.md 缺少协商风格段落"


# ── 6. Orchestrator 协商检查点集成测试 ──

@pytest.mark.asyncio
async def test_negotiation_checkpoint_triggers_for_account_manager():
    """AM 完成后应触发与 strategist 的协商检查点。"""
    from orchestrator import Orchestrator

    orch = Orchestrator("rec_test")

    # mock LLM 调用 → 返回 __SKIP__（无异议）
    async def _skip_gen(**kw):
        return "__SKIP__"

    orch._generate_negotiation_message = _skip_gen
    orch.stage_results = [MagicMock(role_id="account_manager", ok=True, output="test output")]

    # 应不报错地完成协商检查点（跳过模式）
    with patch("orchestrator.NEGOTIATION_ENABLED", True):
        await orch._run_negotiation_checkpoint(
            upstream_role="account_manager",
            project_name="测试客户",
        )


@pytest.mark.asyncio
async def test_negotiation_checkpoint_skipped_when_disabled():
    """NEGOTIATION_ENABLED=False 时协商被跳过。"""
    from orchestrator import Orchestrator

    orch = Orchestrator("rec_test")
    call_count = 0

    async def _should_not_be_called(**kw):
        nonlocal call_count
        call_count += 1
        return "__SKIP__"

    orch._generate_negotiation_message = _should_not_be_called

    with patch("orchestrator.NEGOTIATION_ENABLED", False):
        await orch._run_negotiation_checkpoint(
            upstream_role="account_manager",
            project_name="测试客户",
        )

    assert call_count == 0, "协商关闭时不应调用 LLM"


@pytest.mark.asyncio
async def test_negotiation_checkpoint_no_match():
    """data_analyst 不在协商检查点中，应直接跳过。"""
    from orchestrator import Orchestrator

    orch = Orchestrator("rec_test")
    call_count = 0

    async def _should_not_be_called(**kw):
        nonlocal call_count
        call_count += 1
        return "__SKIP__"

    orch._generate_negotiation_message = _should_not_be_called

    with patch("orchestrator.NEGOTIATION_ENABLED", True):
        await orch._run_negotiation_checkpoint(
            upstream_role="data_analyst",
            project_name="测试客户",
        )

    assert call_count == 0, "无匹配检查点时不应调用 LLM"
