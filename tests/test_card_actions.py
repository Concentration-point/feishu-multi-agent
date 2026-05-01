from __future__ import annotations

import asyncio

import pytest

from feishu import card_actions


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
