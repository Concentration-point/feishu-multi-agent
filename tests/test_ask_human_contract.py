from __future__ import annotations

import pytest

from tools import AgentContext
from tools.ask_human_batch import execute as ask_human_batch_execute


@pytest.mark.asyncio
async def test_ask_human_batch_trims_to_five_and_tags_titles(monkeypatch):
    import tools.ask_human_batch as mod

    calls = []

    async def fake_ask_human(params, context):
        calls.append(params)
        return f"selected:{params['title']}"

    monkeypatch.setattr("tools.ask_human.execute", fake_ask_human)

    questions = [
        {"question": f"问题{i}", "choices": ["A", "B"], "title": f"标题{i}"}
        for i in range(1, 7)
    ]
    result = await ask_human_batch_execute(
        {"questions": questions, "timeout_seconds": 3},
        AgentContext(record_id="rec", project_name="proj", role_id="account_manager"),
    )

    assert len(calls) == 5
    assert calls[0]["title"].startswith("追问 1/5")
    assert calls[-1]["title"].startswith("追问 5/5")
    assert calls[-1]["question"] == "问题5"
    assert "5/5" in result
