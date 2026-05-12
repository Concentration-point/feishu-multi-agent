from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import AgentContext
from tools import submit_review


def _dims(value: str) -> dict[str, str]:
    return {name: value for name in submit_review._DIMENSIONS}


class _FakeContentMemory:
    writes: list[tuple[str, str, str]] = []

    async def write_review(self, record_id: str, status: str, feedback: str) -> None:
        self.writes.append((record_id, status, feedback))


@pytest.mark.asyncio
async def test_submit_review_schema_exposes_structured_red_flag(monkeypatch):
    assert "review_red_flag" in submit_review.SCHEMA["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_submit_review_rejects_pass_with_red_flag(monkeypatch):
    monkeypatch.setattr(submit_review, "ContentMemory", _FakeContentMemory)
    ctx = AgentContext(record_id="project_1", project_name="demo", role_id="reviewer")

    result = await submit_review.execute(
        {
            "content_record_id": "content_1",
            "status": submit_review._VALID_STATUSES[0],
            "feedback": "looks fine",
            "violated_rules": [],
            "dimensions": _dims(submit_review._VALID_DIM_VALUES[0]),
            "review_red_flag": "severe compliance risk",
        },
        ctx,
    )

    assert "review_red_flag" in result
    assert not _FakeContentMemory.writes


@pytest.mark.asyncio
async def test_submit_review_merges_real_red_flag_but_ignores_none_signal(monkeypatch):
    _FakeContentMemory.writes = []
    monkeypatch.setattr(submit_review, "ContentMemory", _FakeContentMemory)
    ctx = AgentContext(record_id="project_1", project_name="demo", role_id="reviewer")

    await submit_review.execute(
        {
            "content_record_id": "content_1",
            "status": submit_review._VALID_STATUSES[1],
            "feedback": "needs rewrite",
            "violated_rules": ["rule-a"],
            "dimensions": _dims(submit_review._VALID_DIM_VALUES[1]),
            "review_red_flag": "medicalized claim",
        },
        ctx,
    )
    await submit_review.execute(
        {
            "content_record_id": "content_2",
            "status": submit_review._VALID_STATUSES[0],
            "feedback": "approved",
            "violated_rules": [],
            "dimensions": _dims(submit_review._VALID_DIM_VALUES[0]),
            "review_red_flag": "无",
        },
        ctx,
    )

    assert _FakeContentMemory.writes[0][2].endswith("review_red_flag: medicalized claim")
    assert _FakeContentMemory.writes[1][2] == "approved"
