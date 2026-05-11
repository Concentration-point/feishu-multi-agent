from __future__ import annotations

from unittest.mock import patch

import pytest

from agents.base import load_soul_with_platform_patch
from config import STATUS_REVIEWING, STATUS_WRITING
from memory.project import BriefProject, ContentRecord
from orchestrator import Orchestrator
from tools import AgentContext


class RecordingProjectMemory:
    def __init__(self, status: str = STATUS_WRITING):
        self.project = BriefProject(
            record_id="rec_status_auth",
            client_name="StatusAuthority",
            status=status,
        )
        self.status_updates: list[str] = []

    async def load(self):
        return self.project

    async def update_status(self, status: str):
        self.status_updates.append(status)
        self.project.status = status

    async def write_agent_error_log(self, message: str):
        self.agent_error = message


class FilledContentMemory:
    rows = [
        ContentRecord(
            record_id="content_1",
            project_name="StatusAuthority",
            title="one",
            platform="xhs",
            draft="finished draft",
            word_count=120,
        )
    ]

    def __init__(self, client=None):
        pass

    async def list_by_project(self, project_name: str):
        return list(self.rows)


class PassiveCopywriterAgent:
    instances: list["PassiveCopywriterAgent"] = []

    def __init__(self, role_id, record_id, event_bus=None, task_filter=None):
        self.role_id = role_id
        self.record_id = record_id
        self._event_bus = event_bus
        self._task_filter = task_filter or {}
        self._messages = []
        self._used_ask_human = False
        PassiveCopywriterAgent.instances.append(self)

    async def run(self):
        return "drafts already written"


def test_copywriter_soul_does_not_whitelist_global_status_tool():
    soul, _ = load_soul_with_platform_patch("copywriter", None)

    assert "update_status" not in soul.tools


@pytest.mark.asyncio
async def test_copywriter_update_status_tool_is_rejected_before_bitable_write():
    import tools.update_status as update_status_tool

    pm = RecordingProjectMemory(status=STATUS_WRITING)
    context = AgentContext(
        record_id="rec_status_auth",
        project_name="StatusAuthority",
        role_id="copywriter",
        sub_id="xhs",
    )

    with patch.object(update_status_tool, "ProjectMemory", return_value=pm):
        result = await update_status_tool.execute({"status": STATUS_REVIEWING}, context)

    assert pm.status_updates == []
    assert "copywriter" in result or "Orchestrator" in result or "unauthorized" in result.lower()


@pytest.mark.asyncio
async def test_orchestrator_advances_copywriter_status_after_all_content_is_complete():
    pm = RecordingProjectMemory(status=STATUS_WRITING)
    PassiveCopywriterAgent.instances = []

    with patch("orchestrator.BaseAgent", PassiveCopywriterAgent), patch(
        "orchestrator.ContentMemory", FilledContentMemory
    ):
        orchestrator = Orchestrator(record_id="rec_status_auth")
        orchestrator._pm = pm
        result, _ = await orchestrator._run_copywriter_fanout(index=3, total=5)

    assert result.ok is True
    assert pm.status_updates == [STATUS_REVIEWING]
    assert PassiveCopywriterAgent.instances
    assert all(agent.role_id == "copywriter" for agent in PassiveCopywriterAgent.instances)
