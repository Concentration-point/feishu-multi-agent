from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- lightweight stubs to avoid optional runtime deps during self-check ----
if "agents.base" not in sys.modules:
    agents_pkg = types.ModuleType("agents")
    base_mod = types.ModuleType("agents.base")

    class BaseAgent:  # minimal placeholder
        def __init__(self, *args, **kwargs):
            self._pending_experience = None
            self._wiki_written = False
            self._messages = []

        async def run(self):
            return ""

    base_mod.BaseAgent = BaseAgent
    agents_pkg.base = base_mod
    sys.modules["agents"] = agents_pkg
    sys.modules["agents.base"] = base_mod

if "memory.experience" not in sys.modules:
    mem_pkg = types.ModuleType("memory")
    exp_mod = types.ModuleType("memory.experience")

    class ExperienceManager:
        async def check_dedup(self, *args, **kwargs):
            return []

        async def merge_experiences(self, *args, **kwargs):
            return None

        async def save_experience(self, *args, **kwargs):
            return None

        async def save_to_wiki(self, *args, **kwargs):
            return None

    exp_mod.ExperienceManager = ExperienceManager
    sys.modules["memory"] = mem_pkg
    sys.modules["memory.experience"] = exp_mod

if "memory.project" not in sys.modules:
    proj_mod = types.ModuleType("memory.project")

    class PlaceholderProjectMemory:
        def __init__(self, *_args, **_kwargs):
            pass

        async def load(self):
            return SimpleNamespace(review_red_flag="", review_summary="")

    proj_mod.ProjectMemory = PlaceholderProjectMemory
    sys.modules["memory.project"] = proj_mod

import orchestrator as orchestrator_module
from orchestrator import Orchestrator


class DummyPMHasFlag:
    def __init__(self, *_args, **_kwargs):
        pass

    async def load(self):
        return SimpleNamespace(
            review_red_flag="存在：绝对化用语",
            review_summary="整体可发布，仅建议优化"
        )


class DummyPMNoFlagButSummaryKeyword:
    def __init__(self, *_args, **_kwargs):
        pass

    async def load(self):
        return SimpleNamespace(
            review_red_flag="无",
            review_summary="存在严重合规风险（旧文案残留，不应作为结构化判定依据）"
        )


async def main() -> int:
    original_pm = orchestrator_module.ProjectMemory
    try:
        orchestrator_module.ProjectMemory = DummyPMHasFlag
        orch = Orchestrator("rec_demo")
        red_flag = await orch._get_review_red_flag()
        print(f"CASE1 structured field => {red_flag}")
        if red_flag != "存在：绝对化用语":
            print("FAIL: CASE1 expected structured red flag")
            return 1

        orchestrator_module.ProjectMemory = DummyPMNoFlagButSummaryKeyword
        orch2 = Orchestrator("rec_demo")
        red_flag2 = await orch2._get_review_red_flag()
        print(f"CASE2 structured field => {red_flag2}")
        if red_flag2 != "无":
            print("FAIL: CASE2 expected '无'")
            return 1

        has_red_flag = bool(red_flag2 and red_flag2.strip() and red_flag2.strip() != "无")
        print(f"CASE2 decision has_red_flag => {has_red_flag}")
        if has_red_flag:
            print("FAIL: CASE2 should not be blocked by summary keyword residue")
            return 1

        print("PASS: orchestrator now uses structured review_red_flag as gate source")
        return 0
    finally:
        orchestrator_module.ProjectMemory = original_pm


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
