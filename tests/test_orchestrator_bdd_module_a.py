from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from config import STATUS_DONE, STATUS_STRATEGY
from memory.project import BriefProject
from orchestrator import Orchestrator


class _RecordingEventBus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish(
        self,
        record_id: str,
        event_type: str,
        payload: dict | None = None,
        *,
        agent_role: str = "",
        agent_name: str = "",
    ) -> None:
        self.events.append(
            {
                "record_id": record_id,
                "event_type": event_type,
                "payload": payload or {},
                "agent_role": agent_role,
                "agent_name": agent_name,
            }
        )


class _ProjectMemory:
    def __init__(self, project: BriefProject) -> None:
        self.project = project
        self.status_updates: list[str] = []
        self.error_logs: list[str] = []

    async def load(self) -> BriefProject:
        return self.project

    async def update_status(self, status: str) -> None:
        self.status_updates.append(status)
        self.project = replace(self.project, status=status)

    async def write_agent_error_log(self, message: str) -> None:
        self.error_logs.append(message)


class _FailingErrorLogProjectMemory(_ProjectMemory):
    async def write_agent_error_log(self, message: str) -> None:
        self.error_logs.append(message)
        self.project = replace(self.project, status=STATUS_DONE)
        raise RuntimeError("bitable error-log column unavailable")


class _TimeoutAgent:
    def __init__(self, role_id, record_id, event_bus=None, task_filter=None):
        self.role_id = role_id
        self.record_id = record_id
        self._event_bus = event_bus
        self._task_filter = task_filter or {}
        self._used_ask_human = False
        self._messages = []

    async def run(self):
        raise asyncio.TimeoutError()


class _AskHumanAgent:
    def __init__(self, role_id, record_id, event_bus=None, task_filter=None):
        self.role_id = role_id
        self.record_id = record_id
        self._event_bus = event_bus
        self._task_filter = task_filter or {}
        self._used_ask_human = True
        self._messages = []

    async def run(self):
        return "asked human for blocking context"


async def _noop(*_args, **_kwargs):
    return None


async def _pass_rate():
    return 0.8


async def _review_status():
    return "通过"


@pytest.mark.asyncio
async def test_a05_timeout_stage_error_log_failure_does_not_crash(monkeypatch):
    import orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "BaseAgent", _TimeoutAgent)
    project = BriefProject(
        record_id="rec_a05",
        client_name="A05",
        status=STATUS_STRATEGY,
        brief_analysis="brief analysis ready",
        project_type="电商大促",
    )
    pm = _FailingErrorLogProjectMemory(project)
    bus = _RecordingEventBus()
    orch = Orchestrator("rec_a05", event_bus=bus)
    orch._pm = pm
    orch._validate_handoff = lambda *_args, **_kwargs: _handoff_ok()
    orch._get_review_pass_rate = _pass_rate
    orch._reconcile_review_pass_rate = lambda rate: _return(rate)
    orch._get_project_review_status = _review_status
    orch._settle_experiences = _noop
    orch._append_evolution_log = _noop

    results = await orch.run()

    assert len(results) == 1
    assert results[0].ok is False
    assert "超时" in results[0].error or "timeout" in results[0].error.lower()
    assert pm.error_logs
    assert any(e["event_type"] == "pipeline.aborted" for e in bus.events)


@pytest.mark.asyncio
async def test_a15_publish_without_event_bus_is_noop():
    orch = Orchestrator("rec_a15", event_bus=None)

    orch._publish("pipeline.stage_changed", {"current_role": "account_manager"})


@pytest.mark.asyncio
async def test_a16_ask_human_no_progress_does_not_trigger_no_progress_halt(monkeypatch):
    import orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "BaseAgent", _AskHumanAgent)
    project = BriefProject(
        record_id="rec_a16",
        client_name="A16",
        status=STATUS_STRATEGY,
        brief_analysis="brief analysis ready",
        project_type="电商大促",
    )
    bus = _RecordingEventBus()
    orch = Orchestrator("rec_a16", event_bus=bus)
    orch._pm = _ProjectMemory(project)
    orch._max_route_steps = 2
    orch._no_progress_limit = 1
    orch._validate_handoff = lambda *_args, **_kwargs: _handoff_ok()
    orch._get_review_pass_rate = _pass_rate
    orch._reconcile_review_pass_rate = lambda rate: _return(rate)
    orch._get_project_review_status = _review_status
    orch._settle_experiences = _noop
    orch._append_evolution_log = _noop

    results = await orch.run()

    assert len(results) == 2
    assert all(result.used_ask_human for result in results)
    halted = [e for e in bus.events if e["event_type"] == "pipeline.halted"]
    assert not halted


async def _handoff_ok():
    return True, ""


async def _return(value):
    return value
