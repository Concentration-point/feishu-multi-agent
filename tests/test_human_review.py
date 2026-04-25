"""模块三单元测试 — request_human_review 工具 + 必调工具校验。

覆盖路径:
  1. AUTO_APPROVE 模式
  2. 无 FEISHU_CHAT_ID 降级
  3. brief_analysis 为空拒绝
  4. 回复解析 (_parse_review_reply)
  5. 噪音过滤 (_looks_like_review / _is_reply_to)
  6. 超时兜底
  7. BaseAgent 必调工具校验

使用方法:
    python tests/test_human_review.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("test_human_review")


class TestReport:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []

    def ok(self, name: str, detail: str = ""):
        self.passed.append(name)
        logger.info("PASS: %s %s", name, detail)

    def fail(self, name: str, detail: str = ""):
        self.failed.append(name)
        logger.error("FAIL: %s %s", name, detail)

    def summary(self) -> int:
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*60}")
        print(f"模块三测试: {len(self.passed)}/{total} 通过")
        if self.failed:
            print(f"失败: {self.failed}")
        print(f"{'='*60}")
        return 0 if not self.failed else 1


report = TestReport()


# ========== 回复解析测试 ==========

def test_parse_reply():
    """测试 _parse_review_reply 对各种输入的解析。"""
    from tools.request_human_review import _parse_review_reply

    # 通过
    cases_approve = ["通过", "approved", "ok", "LGTM", "没问题", "可以"]
    for text in cases_approve:
        status, _ = _parse_review_reply(text)
        if status == "通过":
            report.ok(f"parse_approve: '{text}'")
        else:
            report.fail(f"parse_approve: '{text}'", f"got status={status}")

    # 带前缀的修改
    cases_modify_prefix = [
        ("修改：目标人群需要调整", "目标人群需要调整"),
        ("修改:预算是10万", "预算是10万"),
        ("修改 品牌调性不对", "品牌调性不对"),
    ]
    for text, expected_feedback in cases_modify_prefix:
        status, feedback = _parse_review_reply(text)
        if status == "需要修改" and feedback == expected_feedback:
            report.ok(f"parse_modify_prefix: '{text}'")
        else:
            report.fail(f"parse_modify_prefix: '{text}'", f"got status={status}, feedback={feedback}")

    # 含审核关键词但无前缀 → 修改
    cases_modify_keyword = ["建议把目标人群改一下", "调整一下品牌调性", "不行，重做"]
    for text in cases_modify_keyword:
        status, feedback = _parse_review_reply(text)
        if status == "需要修改":
            report.ok(f"parse_modify_keyword: '{text}'")
        else:
            report.fail(f"parse_modify_keyword: '{text}'", f"got status={status}")

    # 无关文本 → None (不识别)
    cases_noise = ["午饭吃啥", "今天天气不错", "哈哈哈"]
    for text in cases_noise:
        status, _ = _parse_review_reply(text)
        if status is None:
            report.ok(f"parse_noise_reject: '{text}'")
        else:
            report.fail(f"parse_noise_reject: '{text}'", f"should be None, got status={status}")


# ========== 消息过滤测试 ==========

def test_message_filtering():
    """测试 _is_reply_to 和 _looks_like_review。"""
    from tools.request_human_review import _is_reply_to, _looks_like_review

    # _is_reply_to
    msg_thread = {"root_id": "om_abc", "parent_id": "om_abc"}
    msg_direct = {"root_id": "", "parent_id": ""}
    msg_other_thread = {"root_id": "om_xyz", "parent_id": "om_xyz"}

    if _is_reply_to(msg_thread, "om_abc"):
        report.ok("is_reply_to: thread reply matches")
    else:
        report.fail("is_reply_to: thread reply should match")

    if not _is_reply_to(msg_direct, "om_abc"):
        report.ok("is_reply_to: direct msg not a reply")
    else:
        report.fail("is_reply_to: direct msg should not match")

    if not _is_reply_to(msg_other_thread, "om_abc"):
        report.ok("is_reply_to: different thread not a reply")
    else:
        report.fail("is_reply_to: different thread should not match")

    # _looks_like_review
    if _looks_like_review("通过"):
        report.ok("looks_like_review: '通过'")
    else:
        report.fail("looks_like_review: '通过' should match")

    if _looks_like_review("修改一下目标人群"):
        report.ok("looks_like_review: '修改一下目标人群'")
    else:
        report.fail("looks_like_review: should match")

    if not _looks_like_review("午饭吃啥"):
        report.ok("looks_like_review: noise rejected")
    else:
        report.fail("looks_like_review: noise should not match")


# ========== AUTO_APPROVE 模式测试 ==========

def test_auto_approve():
    """AUTO_APPROVE_HUMAN_REVIEW=true 时跳过真人审核。"""
    import tools.request_human_review as mod
    import config

    original = config.AUTO_APPROVE_HUMAN_REVIEW
    try:
        config.AUTO_APPROVE_HUMAN_REVIEW = True
        # 需要重新 import 或直接 patch 模块级变量
        mod.AUTO_APPROVE_HUMAN_REVIEW = True

        from tools import AgentContext
        ctx = AgentContext(record_id="rec_test", project_name="test", role_id="account_manager")
        result = asyncio.run(mod.execute({"brief_analysis": "测试 Brief 解读"}, ctx))

        if "[AUTO_APPROVE]" in result and "通过" in result:
            report.ok("auto_approve: returns approved with tag")
        else:
            report.fail("auto_approve: missing [AUTO_APPROVE] tag", result[:100])
    finally:
        config.AUTO_APPROVE_HUMAN_REVIEW = original
        mod.AUTO_APPROVE_HUMAN_REVIEW = original


# ========== 无 CHAT_ID 降级测试 ==========

def test_no_chat_id():
    """FEISHU_CHAT_ID 为空时降级通过。"""
    import tools.request_human_review as mod
    import config

    original_approve = config.AUTO_APPROVE_HUMAN_REVIEW
    original_chat = config.FEISHU_CHAT_ID
    try:
        config.AUTO_APPROVE_HUMAN_REVIEW = False
        mod.AUTO_APPROVE_HUMAN_REVIEW = False
        config.FEISHU_CHAT_ID = ""
        mod.FEISHU_CHAT_ID = ""

        from tools import AgentContext
        ctx = AgentContext(record_id="rec_test", project_name="test", role_id="account_manager")
        result = asyncio.run(mod.execute({"brief_analysis": "测试 Brief 解读"}, ctx))

        if "[未配置群聊]" in result:
            report.ok("no_chat_id: fallback with tag")
        else:
            report.fail("no_chat_id: missing [未配置群聊] tag", result[:100])
    finally:
        config.AUTO_APPROVE_HUMAN_REVIEW = original_approve
        mod.AUTO_APPROVE_HUMAN_REVIEW = original_approve
        config.FEISHU_CHAT_ID = original_chat
        mod.FEISHU_CHAT_ID = original_chat


# ========== 空 brief_analysis 拒绝测试 ==========

def test_empty_brief():
    """brief_analysis 为空时拒绝执行。"""
    import tools.request_human_review as mod
    import config

    original = config.AUTO_APPROVE_HUMAN_REVIEW
    try:
        # 关掉 AUTO_APPROVE，确保走到空检查
        config.AUTO_APPROVE_HUMAN_REVIEW = False
        mod.AUTO_APPROVE_HUMAN_REVIEW = False

        from tools import AgentContext
        ctx = AgentContext(record_id="rec_test", project_name="test", role_id="account_manager")
        result = asyncio.run(mod.execute({"brief_analysis": ""}, ctx))

        if "不能为空" in result:
            report.ok("empty_brief: rejected with error")
        else:
            report.fail("empty_brief: should reject empty input", result[:100])
    finally:
        config.AUTO_APPROVE_HUMAN_REVIEW = original
        mod.AUTO_APPROVE_HUMAN_REVIEW = original


# ========== BaseAgent 必调工具校验测试 ==========

def test_required_tool_check():
    """_check_required_tools: AM 已解绑人审，copywriter/reviewer 仍必调校验。"""
    from agents.base import _REQUIRED_TOOL_CALLS as req_map

    # account_manager 人审已收归 Orchestrator 门禁驱动，不再列入硬约束
    if "account_manager" not in req_map:
        report.ok("required_config: account_manager 已从必调配置解绑（人审由门禁驱动）")
    else:
        report.fail(
            "required_config: account_manager 不应再挂必调工具",
            str(req_map.get("account_manager")),
        )

    # copywriter 保留对标+规则双轨
    cw_req = req_map.get("copywriter", [])
    if "search_reference" in cw_req and "search_knowledge" in cw_req:
        report.ok("required_config: copywriter 保留双轨必调")
    else:
        report.fail("required_config: copywriter 双轨必调缺失", str(cw_req))

    # reviewer 保留 search_knowledge 必调
    rv_req = req_map.get("reviewer", [])
    if "search_knowledge" in rv_req:
        report.ok("required_config: reviewer 保留规则必调")
    else:
        report.fail("required_config: reviewer 必调缺失", str(rv_req))

    # 策略师 / 项目经理 不应有必调约束
    for role in ("strategist", "project_manager"):
        if req_map.get(role, []) == []:
            report.ok(f"required_config: {role} 无必调约束 (correct)")
        else:
            report.fail(f"required_config: {role} 不应有必调约束", str(req_map.get(role)))

    # 必调检测逻辑对 copywriter 生效：未调 search_reference 时应被识别
    messages_missing = [
        {"role": "assistant", "content": None, "tool_calls": [
            {"function": {"name": "search_knowledge", "arguments": "{}"}, "id": "tc1"}
        ]},
        {"role": "tool", "tool_call_id": "tc1", "content": "..."},
        {"role": "assistant", "content": "最终输出"},
    ]
    called = set()
    for msg in messages_missing:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    called.add(tc.get("function", {}).get("name", ""))
    missing = [t for t in cw_req if t not in called]
    if missing == ["search_reference"]:
        report.ok("required_check: detects missing search_reference for copywriter")
    else:
        report.fail("required_check: copywriter missing detection broken", str(missing))


# ========== 执行所有测试 ==========

def main() -> int:
    test_parse_reply()
    test_message_filtering()
    test_auto_approve()
    test_no_chat_id()
    test_empty_brief()
    test_required_tool_check()
    return report.summary()


if __name__ == "__main__":
    raise SystemExit(main())
