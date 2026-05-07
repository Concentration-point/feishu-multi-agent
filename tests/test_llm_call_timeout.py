from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import agents.base as base_module
from agents.base import BaseAgent


class _DummyRegistry:
    def get_tools(self, _tool_names=None):
        return []

    async def call_tool(self, _tool_name, _params, _context):
        return ""


def _make_agent() -> BaseAgent:
    return BaseAgent(
        role_id="account_manager",
        record_id="rec_timeout_test",
        tool_registry=_DummyRegistry(),
        llm_client=object(),
        shared_knowledge="",
    )


@pytest.mark.asyncio
async def test_llm_call_emits_started_and_completed(monkeypatch):
    agent = _make_agent()
    events: list[tuple[str, dict | None, int]] = []

    def _capture(event_type: str, payload: dict | None = None, *, round_num: int = 0):
        events.append((event_type, payload, round_num))

    async def _fast_create(**_kwargs):
        return SimpleNamespace(usage=None)

    agent._publish = _capture
    agent._llm = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=_fast_create)
        )
    )

    monkeypatch.setattr(base_module, "LLM_APP_MAX_RETRIES", 1)
    monkeypatch.setattr(base_module, "LLM_TOTAL_TIMEOUT_SECONDS", 1.0)

    response = await agent._llm_call(
        [{"role": "user", "content": "hi"}],
        stage="react_loop",
        iteration=3,
    )

    assert response.usage is None
    assert events[0][0] == "llm.started"
    assert events[0][1]["stage"] == "react_loop"
    assert events[-1][0] == "llm.completed"


@pytest.mark.asyncio
async def test_llm_call_total_timeout_emits_failure(monkeypatch):
    agent = _make_agent()
    events: list[tuple[str, dict | None, int]] = []

    def _capture(event_type: str, payload: dict | None = None, *, round_num: int = 0):
        events.append((event_type, payload, round_num))

    async def _slow_create(**_kwargs):
        await asyncio.sleep(0.05)
        return SimpleNamespace(usage=None)

    agent._publish = _capture
    agent._llm = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=_slow_create)
        )
    )

    monkeypatch.setattr(base_module, "LLM_APP_MAX_RETRIES", 1)
    monkeypatch.setattr(base_module, "LLM_TOTAL_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(asyncio.TimeoutError):
        await agent._llm_call(
            [{"role": "user", "content": "hi"}],
            stage="react_loop",
            iteration=4,
        )

    assert events[0][0] == "llm.started"
    assert events[-1][0] == "llm.failed"
    assert events[-1][1]["error_type"] == "TimeoutError"
