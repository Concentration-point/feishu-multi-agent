from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents.base import BaseAgent


class FakeToolRegistry:
    def __init__(self, outputs: dict[str, str] | None = None):
        self.outputs = outputs or {}
        self.calls: list[dict] = []

    def get_tools(self, tool_names=None):
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"fake {name}",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            for name in (tool_names or [])
        ]

    async def call_tool(self, tool_name, params, context):
        self.calls.append(
            {
                "tool_name": tool_name,
                "params": params,
                "record_id": context.record_id,
                "project_name": context.project_name,
                "role_id": context.role_id,
            }
        )
        return self.outputs.get(tool_name, f"{tool_name} ok")


class FakeMessage:
    def __init__(self, *, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self):
        payload = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        return payload


def tool_call(name: str, arguments: dict, call_id: str = "call_1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        ),
    )


def fake_response(message: FakeMessage):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_agent(
    role_id: str,
    *,
    registry: FakeToolRegistry | None = None,
    task_filter: dict | None = None,
) -> BaseAgent:
    return BaseAgent(
        role_id=role_id,
        record_id="rec_unit",
        task_filter=task_filter,
        tool_registry=registry or FakeToolRegistry(),
        llm_client=object(),
        shared_knowledge="unit shared knowledge",
    )


@pytest.fixture
def scripted_llm():
    def _install(agent: BaseAgent, responses):
        state = {"calls": []}
        queued = list(responses)

        async def fake_llm_call(messages, **kwargs):
            state["calls"].append(
                {
                    "messages": [dict(message) for message in messages],
                    "kwargs": dict(kwargs),
                }
            )
            return queued.pop(0)

        agent._llm_call = fake_llm_call
        state["remaining"] = queued
        return state

    return _install


@pytest.fixture
def agent_test_log(request):
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")

    def _write(title: str, lines: list[str]):
        if reporter is None:
            return
        reporter.write_line("")
        reporter.write_line(f"[agent-unit] {title}")
        for line in lines:
            reporter.write_line(f"  - {line}")

    return _write
