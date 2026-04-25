"""Fan-out tests for Copywriter parallelization (P7 交付物).

Covers 8 verifications fully offline (mock BaseAgent + FakeBitableClient):

1. list_content platform filter: with platform param returns filtered rows; no param returns all
2. 3 platforms parallel spawn: start time diff < 0.2s proves true concurrency
3. Retry once: one platform throws first, orchestrator retries serially once, stage ok
4. Both attempts fail: stage ok=False but other platforms continue
5. Bitable Semaphore <= 5: counter+lock verifies peak active count
6. Empty rows: degenerate to single agent, no fan-out sub-agents
7. Pending experiences: every sub-agent card collected into returned list
8. BaseAgent._publish injects task_filter into payload

Invoke:
    python tests/test_copywriter_fanout.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def test_list_content_platform_filter():
    fails = []
    from tools.list_content import execute, SCHEMA
    from tools import AgentContext
    from memory.project import ContentRecord

    props = SCHEMA["function"]["parameters"]["properties"]
    if "platform" not in props:
        fails.append("SCHEMA.parameters.properties missing platform")

    rows = [
        ContentRecord(record_id="r1", project_name="X", seq=1, title="A", platform="小红书"),
        ContentRecord(record_id="r2", project_name="X", seq=2, title="B", platform="抖音"),
        ContentRecord(record_id="r3", project_name="X", seq=3, title="C", platform="小红书"),
    ]

    class FakeCM:
        async def list_by_project(self, name):
            return rows

    ctx = AgentContext(record_id="rec1", project_name="X", role_id="copywriter")

    with patch("tools.list_content.ContentMemory", return_value=FakeCM()):
        out_all = json.loads(await execute({}, ctx))
        if len(out_all) != 3:
            fails.append("no platform should return all 3, got " + str(len(out_all)))

        out_xhs = json.loads(await execute({"platform": "小红书"}, ctx))
        if len(out_xhs) != 2:
            fails.append("platform=xhs should return 2, got " + str(len(out_xhs)))
        if not all(r["platform"] == "小红书" for r in out_xhs):
            fails.append("filter result leaked other platforms")

        out_empty = json.loads(await execute({"platform": ""}, ctx))
        if len(out_empty) != 3:
            fails.append("empty platform should equal unset, got " + str(len(out_empty)))

    if not fails:
        print("[PASS] test_list_content_platform_filter")
    return fails


class MockAgentRegistry:
    instances = []
    behaviors = {}

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.behaviors = {}


class MockAgent:
    def __init__(self, role_id, record_id, event_bus=None, task_filter=None):
        self.role_id = role_id
        self.record_id = record_id
        self._event_bus = event_bus
        self._task_filter = task_filter or {}
        self._pending_experience = None
        self._wiki_written = False
        self._messages = []
        self.started_at = 0.0
        self.completed_at = 0.0
        MockAgentRegistry.instances.append(self)

    async def run(self):
        self.started_at = time.perf_counter()
        platform = (self._task_filter or {}).get("platform", "")
        behavior = MockAgentRegistry.behaviors.get(platform, {})
        delay = behavior.get("delay", 0.1)
        raise_first = behavior.get("raise_first")
        raise_always = behavior.get("raise_always")

        await asyncio.sleep(delay)

        # prior_runs counts EARLIER instances of the same platform (regardless of
        # whether they completed) — on retry the registry has 2+ instances for
        # the same platform, so the retry agent sees prior_runs >= 1 and skips the raise.
        prior_runs = sum(
            1 for a in MockAgentRegistry.instances
            if a is not self
            and (a._task_filter or {}).get("platform") == platform
            and a.started_at > 0 and a.started_at < self.started_at
        )
        if raise_first and prior_runs == 0:
            raise raise_first

        if raise_always:
            raise raise_always

        self.completed_at = time.perf_counter()
        self._pending_experience = behavior.get("experience") or {
            "situation": "platform=" + platform,
            "action": "mock",
            "outcome": "done",
            "lesson": "lesson for " + platform,
            "category": "电商大促",
            "applicable_roles": ["copywriter"],
        }
        return "[MockAgent output] platform=" + platform + " completed"


def _build_fake_rows(platform_counts):
    from memory.project import ContentRecord
    rows = []
    seq = 0
    for platform, n in platform_counts.items():
        for _ in range(n):
            seq += 1
            rows.append(ContentRecord(
                record_id="r" + str(seq),
                project_name="TestClient",
                seq=seq,
                title="t" + str(seq),
                platform=platform,
            ))
    return rows


class FakeProjectMemory:
    def __init__(self, record_id):
        self.record_id = record_id

    async def load(self):
        from memory.project import BriefProject
        return BriefProject(record_id=self.record_id, client_name="TestClient", project_type="电商大促")


class FakeContentMemory:
    rows = []

    def __init__(self, client=None):
        pass

    async def list_by_project(self, name):
        return list(FakeContentMemory.rows)



async def test_parallel_spawn_3_platforms():
    fails = []
    from orchestrator import Orchestrator

    MockAgentRegistry.reset()
    MockAgentRegistry.behaviors = {
        "小红书": {"delay": 0.3},
        "抖音":   {"delay": 0.3},
        "公众号": {"delay": 0.3},
    }
    FakeContentMemory.rows = _build_fake_rows({"小红书": 2, "抖音": 2, "公众号": 2})

    with patch("orchestrator.BaseAgent", MockAgent), \
         patch("orchestrator.ProjectMemory", FakeProjectMemory), \
         patch("orchestrator.ContentMemory", FakeContentMemory):
        orch = Orchestrator(record_id="rec_test")
        result, pending = await orch._run_copywriter_fanout(index=3, total=5)

    if not result.ok:
        fails.append("stage ok should be True, err=" + result.error)

    if len(MockAgentRegistry.instances) != 3:
        fails.append("expected 3 agents spawned, got " + str(len(MockAgentRegistry.instances)))

    starts = sorted(a.started_at for a in MockAgentRegistry.instances)
    span = starts[-1] - starts[0] if starts else 0
    if span > 0.2:
        fails.append("spawn not parallel — start span = " + format(span, ".3f") + "s > 0.2s")
    else:
        print("[PASS] test_parallel_spawn_3_platforms (start span = " + format(span, ".4f") + "s)")

    if len(pending) != 3:
        fails.append("expected 3 pending experiences, got " + str(len(pending)))

    return fails


async def test_retry_succeeds_after_first_failure():
    fails = []
    from orchestrator import Orchestrator

    MockAgentRegistry.reset()
    MockAgentRegistry.behaviors = {
        "小红书": {"delay": 0.05, "raise_first": RuntimeError("first-try-exc")},
        "抖音":   {"delay": 0.05},
        "公众号": {"delay": 0.05},
    }
    FakeContentMemory.rows = _build_fake_rows({"小红书": 1, "抖音": 1, "公众号": 1})

    with patch("orchestrator.BaseAgent", MockAgent), \
         patch("orchestrator.ProjectMemory", FakeProjectMemory), \
         patch("orchestrator.ContentMemory", FakeContentMemory):
        orch = Orchestrator(record_id="rec_test_retry")
        result, pending = await orch._run_copywriter_fanout(index=3, total=5)

    if not result.ok:
        fails.append("retry should recover, ok=" + str(result.ok) + " err=" + result.error)

    xhs = [a for a in MockAgentRegistry.instances if (a._task_filter or {}).get("platform") == "小红书"]
    if len(xhs) != 2:
        fails.append("xhs should spawn 2 agents (1 fail + 1 retry), got " + str(len(xhs)))

    dy = [a for a in MockAgentRegistry.instances if (a._task_filter or {}).get("platform") == "抖音"]
    if len(dy) != 1:
        fails.append("dy should spawn 1 agent, got " + str(len(dy)))

    if "(retry)" not in result.output:
        fails.append("stage output should mark retry, got: " + result.output[:200])

    if len(pending) != 3:
        fails.append("expected 3 experiences after retry, got " + str(len(pending)))

    if not fails:
        print("[PASS] test_retry_succeeds_after_first_failure")
    return fails


async def test_double_failure_isolated():
    fails = []
    from orchestrator import Orchestrator

    MockAgentRegistry.reset()
    MockAgentRegistry.behaviors = {
        "小红书": {"delay": 0.05, "raise_always": ValueError("always-fail")},
        "抖音":   {"delay": 0.05},
    }
    FakeContentMemory.rows = _build_fake_rows({"小红书": 1, "抖音": 1})

    with patch("orchestrator.BaseAgent", MockAgent), \
         patch("orchestrator.ProjectMemory", FakeProjectMemory), \
         patch("orchestrator.ContentMemory", FakeContentMemory):
        orch = Orchestrator(record_id="rec_test_double_fail")
        result, pending = await orch._run_copywriter_fanout(index=3, total=5)

    if result.ok:
        fails.append("expected stage ok=False, got True (err=" + result.error + ")")

    if "小红书" not in result.error:
        fails.append("stage error should mention 小红书, got: " + result.error)

    if "抖音] OK" not in result.output and "抖音] OK(retry)" not in result.output:
        fails.append("抖音 should be OK, output: " + result.output[:300])

    xhs = [a for a in MockAgentRegistry.instances if (a._task_filter or {}).get("platform") == "小红书"]
    if len(xhs) != 2:
        fails.append("小红书 should spawn 2 agents, got " + str(len(xhs)))

    if len(pending) != 1:
        fails.append("expected 1 pending exp (抖音 only), got " + str(len(pending)))

    if not fails:
        print("[PASS] test_double_failure_isolated")
    return fails



async def test_bitable_semaphore_limit():
    fails = []
    from feishu.bitable import _get_bitable_sem, _reset_bitable_sem_for_test, BITABLE_CONCURRENCY_LIMIT

    _reset_bitable_sem_for_test(BITABLE_CONCURRENCY_LIMIT)
    sem = _get_bitable_sem()

    state = {"active": 0, "max_active": 0}
    lock = asyncio.Lock()

    async def fake_http_call(i):
        async with sem:
            async with lock:
                state["active"] += 1
                if state["active"] > state["max_active"]:
                    state["max_active"] = state["active"]
            await asyncio.sleep(0.03)
            async with lock:
                state["active"] -= 1
        return i

    results = await asyncio.gather(*(fake_http_call(i) for i in range(20)))

    if state["max_active"] > BITABLE_CONCURRENCY_LIMIT:
        fails.append("Bitable semaphore breached: max_active=" + str(state["max_active"]) + " > limit=" + str(BITABLE_CONCURRENCY_LIMIT))
    if state["max_active"] == 0:
        fails.append("max_active never incremented — test broken")
    if sorted(results) != list(range(20)):
        fails.append("result integrity broken")

    if not fails:
        print("[PASS] test_bitable_semaphore_limit (max concurrent=" + str(state["max_active"]) + " <= " + str(BITABLE_CONCURRENCY_LIMIT) + ")")
    return fails


async def test_empty_rows_no_agents_spawned():
    fails = []
    from orchestrator import Orchestrator

    MockAgentRegistry.reset()
    FakeContentMemory.rows = []

    with patch("orchestrator.BaseAgent", MockAgent), \
         patch("orchestrator.ProjectMemory", FakeProjectMemory), \
         patch("orchestrator.ContentMemory", FakeContentMemory):
        orch = Orchestrator(record_id="rec_empty")
        result, pending = await orch._run_copywriter_fanout(index=3, total=5)

    if len(MockAgentRegistry.instances) != 1:
        fails.append("empty rows should spawn 1 fallback agent, got " + str(len(MockAgentRegistry.instances)))
    elif MockAgentRegistry.instances[0]._task_filter != {}:
        fails.append("fallback agent should have no task_filter, got " + str(MockAgentRegistry.instances[0]._task_filter))

    if not fails:
        print("[PASS] test_empty_rows_no_agents_spawned")
    return fails


async def test_all_pending_experiences_collected():
    fails = []
    from orchestrator import Orchestrator

    MockAgentRegistry.reset()
    MockAgentRegistry.behaviors = {
        "小红书": {"delay": 0.02, "experience": {"lesson": "xhs lesson", "category": "电商大促"}},
        "抖音":   {"delay": 0.02, "experience": {"lesson": "dy lesson", "category": "电商大促"}},
        "公众号": {"delay": 0.02, "experience": {"lesson": "gzh lesson", "category": "电商大促"}},
        "通用":   {"delay": 0.02, "experience": {"lesson": "default lesson", "category": "电商大促"}},
    }
    FakeContentMemory.rows = _build_fake_rows({"小红书": 1, "抖音": 1, "公众号": 1, "": 1})

    with patch("orchestrator.BaseAgent", MockAgent), \
         patch("orchestrator.ProjectMemory", FakeProjectMemory), \
         patch("orchestrator.ContentMemory", FakeContentMemory):
        orch = Orchestrator(record_id="rec_exp")
        result, pending = await orch._run_copywriter_fanout(index=3, total=5)

    if len(pending) != 4:
        fails.append("expected 4 experiences (3 platforms + 通用), got " + str(len(pending)))

    lessons = sorted(p["card"]["lesson"] for p in pending)
    expected = sorted(["xhs lesson", "dy lesson", "gzh lesson", "default lesson"])
    if lessons != expected:
        fails.append("lessons mismatch: " + str(lessons) + " != " + str(expected))

    if not all("task_filter" in p and "platform" in p["task_filter"] for p in pending):
        fails.append("pending entries missing task_filter.platform")

    if not fails:
        print("[PASS] test_all_pending_experiences_collected")
    return fails


async def test_base_agent_publish_injects_task_filter():
    fails = []
    from agents.base import BaseAgent

    class FakeEventBus:
        def __init__(self):
            self.events = []

        def publish(self, record_id, event_type, payload, *, agent_role="", agent_name="", round_num=0):
            self.events.append({
                "event_type": event_type,
                "payload": payload,
                "agent_role": agent_role,
                "round_num": round_num,
            })

    bus = FakeEventBus()
    agent = object.__new__(BaseAgent)
    agent.role_id = "copywriter"
    agent.record_id = "rec_xx"
    agent._event_bus = bus
    agent._task_filter = {"platform": "小红书"}

    agent._publish("agent.started", {"foo": 1})

    if len(bus.events) != 1:
        fails.append("expected 1 event, got " + str(len(bus.events)))
    else:
        evt = bus.events[0]
        if evt["payload"].get("task_filter") != {"platform": "小红书"}:
            fails.append("task_filter not injected: " + str(evt["payload"]))
        if evt["payload"].get("foo") != 1:
            fails.append("original payload lost")

    agent2 = object.__new__(BaseAgent)
    agent2.role_id = "strategist"
    agent2.record_id = "rec_yy"
    agent2._event_bus = bus
    agent2._task_filter = {}
    bus.events.clear()
    agent2._publish("agent.started", {"foo": 2})
    if "task_filter" in bus.events[0]["payload"]:
        fails.append("no task_filter should NOT add key")

    if not fails:
        print("[PASS] test_base_agent_publish_injects_task_filter")
    return fails


async def main():
    print("=" * 70)
    print("Copywriter Fan-out tests")
    print("=" * 70)

    all_fails = []
    coros = [
        test_list_content_platform_filter(),
        test_bitable_semaphore_limit(),
        test_base_agent_publish_injects_task_filter(),
        test_parallel_spawn_3_platforms(),
        test_retry_succeeds_after_first_failure(),
        test_double_failure_isolated(),
        test_empty_rows_no_agents_spawned(),
        test_all_pending_experiences_collected(),
    ]
    for coro in coros:
        try:
            fails = await coro
        except Exception as e:
            fails = ["test threw uncaught exception: " + type(e).__name__ + ": " + str(e)]
        all_fails.extend(fails)

    print("=" * 70)
    if all_fails:
        print("FAIL (" + str(len(all_fails)) + " assertions)")
        for f in all_fails:
            print("  - " + f)
        return 1
    print("PASS — all fan-out tests green")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
