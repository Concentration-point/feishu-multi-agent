"""人审门禁 — 状态机、门禁四分支、反馈注入、容错写入。

覆盖改造后的关键路径，不依赖真实飞书连接：
  1. 状态机新边 合法性（解读中↔待人审、待人审→策略中/解读中）
  2. poll_for_human_reply 三种降级分支 + 返回结构
  3. Orchestrator._enter_human_review_gate 四分支行为
  4. BaseAgent._build_system_prompt AM 人类反馈注入（按角色分化）
  5. ProjectMemory._safe_update 字段未映射时 skip 不抛

使用:
    python tests/test_human_review_gate.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("test_human_review_gate")


class TestReport:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.passed.append(name)
        print(f"PASS: {name} {detail}")

    def fail(self, name: str, detail: str = "") -> None:
        self.failed.append(name)
        print(f"FAIL: {name} {detail}")

    def summary(self) -> int:
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*60}")
        print(f"人审门禁测试: {len(self.passed)}/{total} 通过")
        if self.failed:
            print(f"失败清单: {self.failed}")
        print(f"{'='*60}")
        return 0 if not self.failed else 1


report = TestReport()


# ============================================================
# 1. 状态机新边合法性
# ============================================================
def test_state_machine_transitions() -> None:
    from tools.update_status import _TRANSITIONS

    cases_legal = [
        ("解读中", "待人审"),
        ("解读中", "策略中"),
        ("待人审", "策略中"),
        ("待人审", "解读中"),
    ]
    cases_illegal = [
        ("待人审", "撰写中"),
        ("待人审", "已完成"),
        ("解读中", "审核中"),
        ("策略中", "待人审"),
        ("撰写中", "待人审"),
    ]

    for cur, tgt in cases_legal:
        if tgt in _TRANSITIONS.get(cur, []):
            report.ok(f"transition legal: {cur} -> {tgt}")
        else:
            report.fail(f"transition legal: {cur} -> {tgt}", "should be allowed")

    for cur, tgt in cases_illegal:
        if tgt not in _TRANSITIONS.get(cur, []):
            report.ok(f"transition illegal: {cur} -> {tgt} blocked")
        else:
            report.fail(f"transition illegal: {cur} -> {tgt}", "should be blocked")


# ============================================================
# 2. poll_for_human_reply 三种降级分支
# ============================================================
def test_poll_downgrade() -> None:
    import tools.request_human_review as mod
    import config

    # (1) AUTO_APPROVE
    orig_auto = config.AUTO_APPROVE_HUMAN_REVIEW
    orig_chat = config.FEISHU_CHAT_ID
    try:
        config.AUTO_APPROVE_HUMAN_REVIEW = True
        mod.AUTO_APPROVE_HUMAN_REVIEW = True
        result_auto = asyncio.run(mod.poll_for_human_reply("brief"))
        if result_auto["status"] == "skipped_auto_approve":
            report.ok("poll: AUTO_APPROVE -> skipped_auto_approve")
        else:
            report.fail("poll: AUTO_APPROVE", str(result_auto))
    finally:
        config.AUTO_APPROVE_HUMAN_REVIEW = orig_auto
        mod.AUTO_APPROVE_HUMAN_REVIEW = orig_auto

    # (2) 空 brief -> need_revise
    result_empty = asyncio.run(mod.poll_for_human_reply(""))
    if result_empty["status"] == "need_revise" and "为空" in result_empty.get("feedback", ""):
        report.ok("poll: empty brief -> need_revise")
    else:
        report.fail("poll: empty brief", str(result_empty))

    # (3) 无 FEISHU_CHAT_ID -> skipped_no_chat
    try:
        config.AUTO_APPROVE_HUMAN_REVIEW = False
        mod.AUTO_APPROVE_HUMAN_REVIEW = False
        config.FEISHU_CHAT_ID = ""
        mod.FEISHU_CHAT_ID = ""
        result_no_chat = asyncio.run(mod.poll_for_human_reply("brief"))
        if result_no_chat["status"] == "skipped_no_chat":
            report.ok("poll: no chat_id -> skipped_no_chat")
        else:
            report.fail("poll: no chat_id", str(result_no_chat))
    finally:
        config.FEISHU_CHAT_ID = orig_chat
        mod.FEISHU_CHAT_ID = orig_chat

    # (4) 返回 dict 结构字段齐全
    expected = {"status", "feedback", "msg_id", "deadline", "sent_at"}
    if set(result_no_chat.keys()) >= expected:
        report.ok(f"poll: dict keys complete ({sorted(expected)})")
    else:
        report.fail("poll: dict keys missing", str(set(result_no_chat.keys())))


# ============================================================
# 3. _enter_human_review_gate 四分支 (mock poll + mock PM)
# ============================================================
class _StubPM:
    """ProjectMemory 替身，捕获所有写入动作。"""

    def __init__(self, proj):
        self.record_id = proj.record_id
        self._proj = proj
        self.writes: list[tuple[str, object]] = []

    async def load(self):
        return self._proj

    async def write_review_status(self, status):
        self.writes.append(("review_status", status))
        self._proj.review_status = status

    async def write_pending_meta(self, meta):
        self.writes.append(("pending_meta", meta))
        self._proj.pending_meta = json.dumps(meta, ensure_ascii=False)

    async def write_human_feedback(self, fb):
        self.writes.append(("human_feedback", fb))
        self._proj.human_feedback = fb

    async def clear_pending_state(self):
        self.writes.append(("clear_pending_state", None))

    async def update_status(self, status):
        self.writes.append(("status", status))
        self._proj.status = status


def _run_gate(poll_result: dict, *, brief: str = "已就绪 Brief 解读", status_init: str = "解读中"):
    """封装一次门禁运行：patch ProjectMemory + poll_for_human_reply，返回 (outcome, stub_pm)。"""
    import orchestrator as omod
    import tools.request_human_review as rhrm
    from memory.project import BriefProject

    proj = BriefProject(
        record_id="rec_x",
        client_name="stub",
        brief_analysis=brief,
        status=status_init,
    )
    stub_pm = _StubPM(proj)

    def _pm_factory(record_id, *args, **kwargs):  # ProjectMemory(record_id, ...)
        return stub_pm

    async def _fake_poll(*args, **kwargs):
        return poll_result

    orig_pm = omod.ProjectMemory
    orig_chat = omod.FEISHU_CHAT_ID
    orig_poll = rhrm.poll_for_human_reply
    try:
        omod.ProjectMemory = _pm_factory
        omod.FEISHU_CHAT_ID = ""  # 禁用 _broadcast 真发 IM
        rhrm.poll_for_human_reply = _fake_poll
        orch = omod.Orchestrator(record_id="rec_x")
        outcome = asyncio.run(orch._enter_human_review_gate(resumed=False))
    finally:
        omod.ProjectMemory = orig_pm
        omod.FEISHU_CHAT_ID = orig_chat
        rhrm.poll_for_human_reply = orig_poll

    return outcome, stub_pm


def test_gate_approved() -> None:
    outcome, pm = _run_gate({
        "status": "approved",
        "feedback": "可以",
        "msg_id": "om_x",
        "deadline": 0,
        "sent_at": "t",
    })
    if outcome == "approved":
        report.ok("gate.approved: outcome = approved")
    else:
        report.fail("gate.approved: outcome", outcome)

    kinds = dict(pm.writes)
    rs_writes = [v for k, v in pm.writes if k == "review_status"]
    status_writes = [v for k, v in pm.writes if k == "status"]
    if "通过" in rs_writes and "策略中" in status_writes:
        report.ok("gate.approved: 人审状态=通过 + status=策略中")
    else:
        report.fail("gate.approved: writes", str(pm.writes))

    if any(k == "clear_pending_state" for k, _ in pm.writes):
        report.ok("gate.approved: 触发 clear_pending_state")
    else:
        report.fail("gate.approved: missing clear", str(pm.writes))


def test_gate_need_revise() -> None:
    outcome, pm = _run_gate({
        "status": "need_revise",
        "feedback": "目标人群颗粒度不够",
        "msg_id": "om_x",
        "deadline": 0,
        "sent_at": "t",
    })
    if outcome == "need_revise":
        report.ok("gate.need_revise: outcome = need_revise")
    else:
        report.fail("gate.need_revise: outcome", outcome)

    fb_writes = [v for k, v in pm.writes if k == "human_feedback"]
    if fb_writes and "目标人群" in fb_writes[0]:
        report.ok("gate.need_revise: 反馈原话落盘 human_feedback")
    else:
        report.fail("gate.need_revise: human_feedback", str(pm.writes))

    status_writes = [v for k, v in pm.writes if k == "status"]
    if "解读中" in status_writes:
        report.ok("gate.need_revise: status 回退到 解读中")
    else:
        report.fail("gate.need_revise: status", str(status_writes))


def test_gate_timeout() -> None:
    outcome, pm = _run_gate({
        "status": "timeout",
        "feedback": "[超时] 等待超过 60 秒",
        "msg_id": "om_x",
        "deadline": 0,
        "sent_at": "t",
    })
    if outcome == "timeout":
        report.ok("gate.timeout: outcome = timeout")
    else:
        report.fail("gate.timeout: outcome", outcome)

    rs_writes = [v for k, v in pm.writes if k == "review_status"]
    status_writes = [v for k, v in pm.writes if k == "status"]
    if "超时" in rs_writes:
        report.ok("gate.timeout: 人审状态 = 超时")
    else:
        report.fail("gate.timeout: 人审状态 missing", str(rs_writes))
    if "待人审" in status_writes:
        report.ok("gate.timeout: status = 待人审 (可恢复)")
    else:
        report.fail("gate.timeout: status missing 待人审", str(status_writes))


def test_gate_skipped_empty_brief() -> None:
    outcome, pm = _run_gate(
        {"status": "timeout", "feedback": "", "msg_id": "", "deadline": 0, "sent_at": ""},
        brief="",
    )
    if outcome == "skipped":
        report.ok("gate.skipped: brief_analysis 为空 -> skipped")
    else:
        report.fail("gate.skipped: outcome", outcome)


# ============================================================
# 4. _build_system_prompt AM 反馈注入（按角色分化）
# ============================================================
class _MinimalAgent:
    """BaseAgent 的裸壳，只用于测 _build_system_prompt 静态逻辑。"""

    def __init__(self, role_id: str):
        self.role_id = role_id
        self.shared_knowledge = ""
        self.soul = type("Soul", (), {"name": role_id, "description": "", "body": ""})()

    # 借 BaseAgent 的方法
    from agents.base import BaseAgent as _BA

    _build_system_prompt = _BA._build_system_prompt


def test_prompt_feedback_injection() -> None:
    from memory.project import BriefProject

    # (1) AM + 有 feedback -> 注入
    am = _MinimalAgent("account_manager")
    proj_fb = BriefProject(record_id="x", human_feedback="人群颗粒度不够")
    prompt = am._build_system_prompt(proj_fb)
    if "上一轮人类审核反馈" in prompt and "颗粒度不够" in prompt:
        report.ok("prompt.AM+fb: 注入反馈段")
    else:
        report.fail("prompt.AM+fb: should inject", prompt[-400:])

    # (2) AM + 空 feedback -> 不注入
    proj_empty = BriefProject(record_id="x", human_feedback="")
    prompt2 = am._build_system_prompt(proj_empty)
    if "上一轮人类审核反馈" not in prompt2:
        report.ok("prompt.AM+empty: 不注入")
    else:
        report.fail("prompt.AM+empty: should not inject")

    # (3) 非 AM 角色 + 有 feedback -> 不注入（防止策略师也被错注入）
    strat = _MinimalAgent("strategist")
    proj_strat = BriefProject(record_id="x", human_feedback="上轮意见")
    prompt3 = strat._build_system_prompt(proj_strat)
    if "上一轮人类审核反馈" not in prompt3:
        report.ok("prompt.non-AM: 非 AM 不注入反馈 (隔离正确)")
    else:
        report.fail("prompt.non-AM: should not inject for non-AM")


# ============================================================
# 5. ProjectMemory._safe_update 容错
# ============================================================
def test_safe_update_skip_unmapped() -> None:
    from memory.project import ProjectMemory

    captured: list[tuple[str, dict]] = []

    class _FakeClient:
        async def update_record(self, tid, rid, fields):
            captured.append((rid, fields))

    pm = ProjectMemory("rec_x", client=_FakeClient())

    # (1) mapped key -> 正常写
    asyncio.run(pm._safe_update("review_status", "超时"))
    if captured and any("人审状态" in f for _, f in captured):
        report.ok("safe_update.mapped: review_status 写入 字段=人审状态")
    else:
        report.fail("safe_update.mapped: should write", str(captured))

    # (2) 未映射键 -> skip
    captured.clear()
    asyncio.run(pm._safe_update("not_a_real_key", "x"))
    if not captured:
        report.ok("safe_update.unmapped: skip without crash")
    else:
        report.fail("safe_update.unmapped: should skip", str(captured))

    # (3) 客户端抛异常 -> warn 不重抛
    class _BrokenClient:
        async def update_record(self, tid, rid, fields):
            raise RuntimeError("飞书返回 FieldNameNotFound")

    pm_broken = ProjectMemory("rec_y", client=_BrokenClient())
    try:
        asyncio.run(pm_broken._safe_update("review_status", "通过"))
        report.ok("safe_update.exception: 异常吞掉不重抛")
    except Exception as exc:
        report.fail("safe_update.exception: 不应重抛", str(exc))


# ============================================================
# main
# ============================================================
def main() -> int:
    test_state_machine_transitions()
    test_poll_downgrade()
    test_gate_approved()
    test_gate_need_revise()
    test_gate_timeout()
    test_gate_skipped_empty_brief()
    test_prompt_feedback_injection()
    test_safe_update_skip_unmapped()
    return report.summary()


if __name__ == "__main__":
    raise SystemExit(main())
