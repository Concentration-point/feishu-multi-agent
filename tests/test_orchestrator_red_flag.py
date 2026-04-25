from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator import Orchestrator


class _DummyPM:
    def __init__(self, *_args, **_kwargs):
        pass

    async def load(self):
        return SimpleNamespace(review_red_flag="存在：绝对化用语", review_summary="整体可发布")


class _DummyPMNoFlag:
    def __init__(self, *_args, **_kwargs):
        pass

    async def load(self):
        return SimpleNamespace(review_red_flag="无", review_summary="存在严重合规风险，但这里只是旧文案残留")


async def _run(coro):
    return await coro


def test_get_review_red_flag_reads_structured_field(monkeypatch):
    import orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "ProjectMemory", _DummyPM)
    orch = Orchestrator("rec_test")
    result = __import__("asyncio").run(orch._get_review_red_flag())
    assert result == "存在：绝对化用语"


def test_structured_red_flag_takes_priority_over_summary_keywords(monkeypatch):
    import orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "ProjectMemory", _DummyPMNoFlag)
    orch = Orchestrator("rec_test")
    result = __import__("asyncio").run(orch._get_review_red_flag())
    assert result == "无"
    assert orch._review_red_flag == ""
