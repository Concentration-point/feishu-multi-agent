from __future__ import annotations

import asyncio

import pytest

from feishu import card_actions


# ── 文字回复匹配（兜底通道） ────────────────────────────────

@pytest.mark.asyncio
async def test_card_actions_resolve_by_digit_reply():
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_digit", ["方案A", "方案B", "方案C"])

    matched = card_actions.resolve_by_message("chat_digit", "2")

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "方案B"
    card_actions.shutdown()


@pytest.mark.asyncio
async def test_card_actions_resolve_structured_multi_answer_reply():
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_structured", ["A", "B", "C"])

    matched = card_actions.resolve_by_message("chat_structured", "1B, 2D, 3C, 4A")

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "1B, 2D, 3C, 4A"
    card_actions.shutdown()


@pytest.mark.asyncio
async def test_card_actions_resolve_stepwise_letter_series_reply():
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register(
        "chat_stepwise",
        ["已按 A/B/C/D/E/F 逐项回复", "信息暂不方便提供，请先按保守默认推进"],
    )

    matched = card_actions.resolve_by_message("chat_stepwise", "A/B/C/B/C")

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "A/B/C/B/C"
    card_actions.shutdown()


# ── 按钮回调匹配（主通道） ──────────────────────────────────

@pytest.mark.asyncio
async def test_card_actions_resolve_by_card_action_dict():
    """按钮 value 为 {"choice_index": 1} 的 dict 格式。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_btn_dict", ["通过", "需要修改", "驳回"])

    matched = card_actions.resolve_by_card_action("chat_btn_dict", {"choice_index": 1})

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "需要修改"
    card_actions.shutdown()


@pytest.mark.asyncio
async def test_card_actions_resolve_by_card_action_first_choice():
    """按钮 value 为 {"choice_index": 0} 选择第一项。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_btn_first", ["方案A", "方案B"])

    matched = card_actions.resolve_by_card_action("chat_btn_first", {"choice_index": 0})

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "方案A"
    card_actions.shutdown()


@pytest.mark.asyncio
async def test_card_actions_resolve_by_card_action_last_choice():
    """选择最后一项（6 选项）。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    choices = ["红", "橙", "黄", "绿", "蓝", "紫"]
    fut = card_actions.register("chat_btn_last", choices)

    matched = card_actions.resolve_by_card_action("chat_btn_last", {"choice_index": 5})

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "紫"
    card_actions.shutdown()


@pytest.mark.asyncio
async def test_card_actions_resolve_by_card_action_out_of_range():
    """无效索引应返回 False 且 Future 不被设置。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_btn_oob", ["A", "B"])

    matched = card_actions.resolve_by_card_action("chat_btn_oob", {"choice_index": 99})

    assert matched is False
    assert not fut.done()
    card_actions.shutdown()


@pytest.mark.asyncio
async def test_card_actions_resolve_by_card_action_wrong_chat_id():
    """chat_id 不匹配时应返回 False。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_x", ["A", "B"])

    matched = card_actions.resolve_by_card_action("chat_y", {"choice_index": 0})

    assert matched is False
    assert not fut.done()
    card_actions.shutdown()


@pytest.mark.asyncio
async def test_card_actions_resolve_by_card_action_str_value():
    """兼容 value 为纯数字字符串的格式。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_btn_str", ["选项一", "选项二", "选项三"])

    matched = card_actions.resolve_by_card_action("chat_btn_str", "2")

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "选项三"
    card_actions.shutdown()


# ── 双通道互不干扰 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_card_actions_both_channels_resolve_same_future():
    """同一 chat_id 注册一次，两个通道都能 resolve（先到先得）。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_both", ["通过", "驳回"])

    # 按钮回调先到
    matched = card_actions.resolve_by_card_action("chat_both", {"choice_index": 0})

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "通过"

    # 文字回复后到，应该失败（Future 已 done）
    matched = card_actions.resolve_by_message("chat_both", "2")
    assert matched is False
    card_actions.shutdown()


@pytest.mark.asyncio
async def test_card_actions_message_fallback_when_card_action_not_used():
    """按钮回调未触发时，文字回复兜底仍正常工作。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    fut = card_actions.register("chat_fallback", ["✅ 确认", "✏️ 修改", "❌ 驳回"])

    matched = card_actions.resolve_by_message("chat_fallback", "1")

    assert matched is True
    assert await asyncio.wait_for(fut, timeout=0.1) == "✅ 确认"
    card_actions.shutdown()


# ── 批量注册（多卡片） ──────────────────────────────────────

@pytest.mark.asyncio
async def test_register_batch_resolve_in_order():
    """批量注册 3 个问题，按序 resolve，验证队首消费逻辑。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    futures = card_actions.register_batch("chat_batch", [
        {"choices": ["A1", "A2"], "accept_any": False},
        {"choices": ["B1", "B2"], "accept_any": False},
        {"choices": ["C1", "C2"], "accept_any": False},
    ])
    assert len(futures) == 3

    # 第 1 题：按钮回调
    matched = card_actions.resolve_by_card_action("chat_batch", {"choice_index": 0})
    assert matched is True
    assert await asyncio.wait_for(futures[0], timeout=0.1) == "A1"

    # 第 2 题：文字回复
    matched = card_actions.resolve_by_message("chat_batch", "1")
    assert matched is True
    assert await asyncio.wait_for(futures[1], timeout=0.1) == "B1"

    # 第 3 题：按钮回调
    matched = card_actions.resolve_by_card_action("chat_batch", {"choice_index": 1})
    assert matched is True
    assert await asyncio.wait_for(futures[2], timeout=0.1) == "C2"

    card_actions.shutdown()


@pytest.mark.asyncio
async def test_register_batch_skip_current():
    """skip_current 取消队首并让后续题可被 resolve。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    futures = card_actions.register_batch("chat_skip", [
        {"choices": ["X1", "X2"], "accept_any": False},
        {"choices": ["Y1", "Y2"], "accept_any": False},
    ])
    assert len(futures) == 2

    # 跳过第 1 题（模拟超时）
    has_more = card_actions.skip_current("chat_skip")
    assert has_more is True
    assert futures[0].done()  # 被取消
    assert futures[0].cancelled()

    # 第 2 题应立即可匹配
    matched = card_actions.resolve_by_message("chat_skip", "2")
    assert matched is True
    assert await asyncio.wait_for(futures[1], timeout=0.1) == "Y2"

    card_actions.shutdown()


@pytest.mark.asyncio
async def test_register_batch_skip_last_cleans_up():
    """skip_current 跳过最后一个 entry 后 chat_id 被清理。"""
    card_actions.set_main_loop(asyncio.get_running_loop())
    futures = card_actions.register_batch("chat_skip_last", [
        {"choices": ["Z1"], "accept_any": False},
    ])
    has_more = card_actions.skip_current("chat_skip_last")
    assert has_more is False
    assert "chat_skip_last" not in card_actions._pending

    card_actions.shutdown()


@pytest.mark.asyncio
async def test_batch_and_single_coexist():
    """不同 chat_id 的批量队列和单卡片队列互不干扰。"""
    card_actions.set_main_loop(asyncio.get_running_loop())

    # 单卡片注册 chat_a
    fut_a = card_actions.register("chat_a", ["P1", "P2"])
    # 批量注册 chat_b
    futures_b = card_actions.register_batch("chat_b", [
        {"choices": ["Q1", "Q2"], "accept_any": False},
        {"choices": ["R1", "R2"], "accept_any": False},
    ])

    # 各自 resolve 互不影响
    card_actions.resolve_by_card_action("chat_a", {"choice_index": 1})
    card_actions.resolve_by_card_action("chat_b", {"choice_index": 0})
    card_actions.resolve_by_message("chat_b", "2")

    assert await asyncio.wait_for(fut_a, timeout=0.1) == "P2"
    assert await asyncio.wait_for(futures_b[0], timeout=0.1) == "Q1"
    assert await asyncio.wait_for(futures_b[1], timeout=0.1) == "R2"

    card_actions.shutdown()
