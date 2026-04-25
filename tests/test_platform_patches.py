"""Copywriter platform-specific soul patch tests (P7).

9 offline checks, no LLM.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.base import BaseAgent, SoulConfig, load_soul_with_platform_patch


XHS = '小红书'
DY = '抖音'
GZH = '公众号'
ZHIHU = '知乎'
SEP_PREFIX = '平台专属补充：'
ANCHOR = '严格服从策略'
WARN_KW = '无专属补丁'
CAT_EC = '电商大促'


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []
    def emit(self, record):
        self.records.append(record)


def _attach_capture():
    cap = _LogCapture()
    lg = logging.getLogger("agents.base")
    lg.addHandler(cap)
    lg.setLevel(logging.DEBUG)
    return cap


def _detach_capture(cap):
    logging.getLogger("agents.base").removeHandler(cap)


def test_patch_files_exist():
    fails = []
    base = ROOT / "agents" / "copywriter" / "platforms"
    if not base.is_dir():
        fails.append("platforms dir missing: " + str(base))
        return fails
    for name in (XHS + ".md", DY + ".md", GZH + ".md"):
        p = base / name
        if not p.exists():
            fails.append("missing file " + name)
            continue
        text = p.read_text(encoding="utf-8").strip()
        if not text:
            fails.append(name + " is empty")
        if text.startswith("---"):
            fails.append(name + " should not contain frontmatter")
    if not fails:
        print("[PASS] test_patch_files_exist")
    return fails


def test_copywriter_xhs_patch_applied():
    fails = []
    soul, used = load_soul_with_platform_patch("copywriter", XHS)
    if not used:
        fails.append("xhs should return used=True")
    if not isinstance(soul, SoulConfig):
        fails.append("return type not SoulConfig")
    kws = ["种草", "闺蜜", "个人反差"]
    if not any(k in soul.body for k in kws):
        fails.append("xhs body missing patch keywords")
    if (SEP_PREFIX + XHS) not in soul.body:
        fails.append("xhs body missing separator title")
    if ANCHOR not in soul.body:
        fails.append("xhs body lost base soul key section")
    if "search_reference" not in soul.tools:
        fails.append("xhs tools missing search_reference")
    if not fails:
        print("[PASS] test_copywriter_xhs_patch_applied")
    return fails


def test_copywriter_douyin_patch_applied():
    fails = []
    soul, used = load_soul_with_platform_patch("copywriter", DY)
    if not used:
        fails.append("douyin should return used=True")
    kws = ["镜头", "脚本", "时长"]
    if not any(k in soul.body for k in kws):
        fails.append("douyin body missing patch keywords")
    if (SEP_PREFIX + DY) not in soul.body:
        fails.append("douyin body missing separator title")
    if not fails:
        print("[PASS] test_copywriter_douyin_patch_applied")
    return fails


def test_copywriter_gongzhonghao_patch_applied():
    fails = []
    soul, used = load_soul_with_platform_patch("copywriter", GZH)
    if not used:
        fails.append("gzh should return used=True")
    kws = ["长文", "金句", "深度"]
    if not any(k in soul.body for k in kws):
        fails.append("gzh body missing patch keywords")
    if (SEP_PREFIX + GZH) not in soul.body:
        fails.append("gzh body missing separator title")
    if not fails:
        print("[PASS] test_copywriter_gongzhonghao_patch_applied")
    return fails


def test_unknown_platform_falls_back_with_warning():
    fails = []
    cap = _attach_capture()
    try:
        soul, used = load_soul_with_platform_patch("copywriter", ZHIHU)
        if used:
            fails.append("zhihu should return used=False")
        if SEP_PREFIX in soul.body:
            fails.append("zhihu body should not contain separator")
        warnings = [r for r in cap.records if r.levelno == logging.WARNING]
        hit = any(ZHIHU in r.getMessage() and WARN_KW in r.getMessage() for r in warnings)
        if not hit:
            fails.append("expected WARNING log not produced")
    finally:
        _detach_capture(cap)
    if not fails:
        print("[PASS] test_unknown_platform_falls_back_with_warning")
    return fails


def test_empty_or_none_platform_no_patch():
    fails = []
    for p in ("", None):
        soul, used = load_soul_with_platform_patch("copywriter", p)
        if used:
            fails.append("platform=" + repr(p) + " should not patch")
        if SEP_PREFIX in soul.body:
            fails.append("platform=" + repr(p) + " body should not contain separator")
    if not fails:
        print("[PASS] test_empty_or_none_platform_no_patch")
    return fails


def test_non_copywriter_role_skips_patch():
    fails = []
    for role in ("strategist", "reviewer", "account_manager", "project_manager"):
        soul, used = load_soul_with_platform_patch(role, XHS)
        if used:
            fails.append("role=" + role + " should not patch")
        if SEP_PREFIX in soul.body:
            fails.append("role=" + role + " body should not contain separator")
    if not fails:
        print("[PASS] test_non_copywriter_role_skips_patch")
    return fails


def test_base_agent_init_sets_platform_patch_used():
    fails = []
    import os
    for k, v in {
        "FEISHU_APP_ID": "test_app_id",
        "FEISHU_APP_SECRET": "test_app_secret",
        "BITABLE_APP_TOKEN": "test_app_token",
        "BITABLE_TABLE_ID_PROJECT": "test_proj",
        "BITABLE_TABLE_ID_CONTENT": "test_cnt",
        "BITABLE_TABLE_ID_EXPERIENCE": "test_exp",
        "BITABLE_TABLE_ID_PROMOTION": "test_prom",
        "LLM_API_KEY": "sk-test",
    }.items():
        os.environ.setdefault(k, v)
    a1 = BaseAgent(role_id="copywriter", record_id="rec_x", task_filter={"platform": XHS})
    if a1._platform_patch_used is not True:
        fails.append("xhs agent _platform_patch_used should be True, got " + repr(a1._platform_patch_used))
    if (SEP_PREFIX + XHS) not in a1.soul.body:
        fails.append("xhs agent soul body missing separator")
    a2 = BaseAgent(role_id="copywriter", record_id="rec_x", task_filter={"platform": ZHIHU})
    if a2._platform_patch_used is not False:
        fails.append("zhihu agent _platform_patch_used should be False")
    a3 = BaseAgent(role_id="copywriter", record_id="rec_x", task_filter={})
    if a3._platform_patch_used is not False:
        fails.append("no-platform agent _platform_patch_used should be False")
    a4 = BaseAgent(role_id="strategist", record_id="rec_x", task_filter={"platform": XHS})
    if a4._platform_patch_used is not False:
        fails.append("strategist agent _platform_patch_used should be False")
    if not fails:
        print("[PASS] test_base_agent_init_sets_platform_patch_used")
    return fails


def test_publish_injects_platform_patch_and_fallback():
    fails = []
    class FakeBus:
        def __init__(self):
            self.events = []
        def publish(self, record_id, event_type, payload, *, agent_role="", agent_name="", round_num=0):
            self.events.append({"event_type": event_type, "payload": payload, "agent_role": agent_role})
    bus = FakeBus()
    # Case 1: patch used True
    a1 = object.__new__(BaseAgent)
    a1.role_id = "copywriter"
    a1.record_id = "rec_a"
    a1._event_bus = bus
    a1._task_filter = {"platform": XHS}
    a1._platform_patch_used = True
    a1._publish("agent.started", {"foo": 1})
    evt1 = bus.events[-1]
    if evt1["payload"].get("platform_patch") != XHS:
        fails.append("patch_used=True should inject platform_patch=xhs, got: " + str(evt1["payload"]))
    if evt1["payload"].get("fallback_used") is not None:
        fails.append("patch_used=True should not inject fallback_used")
    if evt1["payload"].get("task_filter") != {"platform": XHS}:
        fails.append("task_filter should be preserved")
    if evt1["payload"].get("foo") != 1:
        fails.append("original payload foo lost")
    # Case 2: patch used False with platform
    a2 = object.__new__(BaseAgent)
    a2.role_id = "copywriter"
    a2.record_id = "rec_b"
    a2._event_bus = bus
    a2._task_filter = {"platform": ZHIHU}
    a2._platform_patch_used = False
    bus.events.clear()
    a2._publish("tool.called", {"tool_name": "search_knowledge"})
    evt2 = bus.events[-1]
    if evt2["payload"].get("fallback_used") is not True:
        fails.append("fallback should inject fallback_used=True, got: " + str(evt2["payload"]))
    if evt2["payload"].get("platform_patch") is not None:
        fails.append("fallback should not inject platform_patch")
    # Case 3: task_filter without platform
    a3 = object.__new__(BaseAgent)
    a3.role_id = "copywriter"
    a3.record_id = "rec_c"
    a3._event_bus = bus
    a3._task_filter = {"category": CAT_EC}
    a3._platform_patch_used = False
    bus.events.clear()
    a3._publish("agent.completed", {"output_length": 100})
    evt3 = bus.events[-1]
    if "platform_patch" in evt3["payload"]:
        fails.append("no platform should not inject platform_patch")
    if "fallback_used" in evt3["payload"]:
        fails.append("no platform should not inject fallback_used")
    if evt3["payload"].get("task_filter") != {"category": CAT_EC}:
        fails.append("task_filter dict should be preserved")
    # Case 4: missing _platform_patch_used attr
    a4 = object.__new__(BaseAgent)
    a4.role_id = "copywriter"
    a4.record_id = "rec_d"
    a4._event_bus = bus
    a4._task_filter = {"platform": DY}
    bus.events.clear()
    try:
        a4._publish("agent.started", {})
    except AttributeError as e:
        fails.append("missing _platform_patch_used should not AttributeError: " + str(e))
    evt4 = bus.events[-1] if bus.events else None
    if evt4 and evt4["payload"].get("fallback_used") is not True:
        fails.append("missing attr should be treated as fallback, got: " + str(evt4["payload"]))
    if not fails:
        print("[PASS] test_publish_injects_platform_patch_and_fallback")
    return fails


def main():
    print("=" * 70)
    print("Platform patches tests")
    print("=" * 70)
    all_fails = []
    for fn in (
        test_patch_files_exist,
        test_copywriter_xhs_patch_applied,
        test_copywriter_douyin_patch_applied,
        test_copywriter_gongzhonghao_patch_applied,
        test_unknown_platform_falls_back_with_warning,
        test_empty_or_none_platform_no_patch,
        test_non_copywriter_role_skips_patch,
        test_base_agent_init_sets_platform_patch_used,
        test_publish_injects_platform_patch_and_fallback,
    ):
        try:
            fails = fn()
        except Exception as e:
            fails = ["test " + fn.__name__ + " threw: " + type(e).__name__ + ": " + str(e)]
        all_fails.extend([fn.__name__ + ": " + f for f in fails])
    print("=" * 70)
    if all_fails:
        print("FAIL (" + str(len(all_fails)) + " assertions)")
        for f in all_fails:
            print("  - " + f)
        return 1
    print("PASS - all platform patch tests green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
