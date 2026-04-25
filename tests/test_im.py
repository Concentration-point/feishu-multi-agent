"""阶段五集成测试 — 飞书 IM 群聊通道。

使用方法:
    python tests/test_im.py            # 第一层+第二层
    python tests/test_im.py --full     # 全链路（创建 Brief → 跑流水线 → 验证 IM）

第一层: 不需要飞书凭证（类实例化 + SCHEMA 验证）
第二层: 需要 FEISHU_CHAT_ID（真实发送消息）
第三层: 全链路 IM 验证（需要全部飞书凭证 + LLM_API_KEY）
"""

import asyncio
import re
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("test_im")


class TestReport:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []

    def ok(self, name: str, detail: str = ""):
        self.passed.append(name)
        logger.info("✅ PASS: %s %s", name, detail)

    def fail(self, name: str, detail: str = ""):
        self.failed.append(name)
        logger.error("❌ FAIL: %s %s", name, detail)

    def summary(self) -> bool:
        total = len(self.passed) + len(self.failed)
        print("\n" + "=" * 60)
        print(f"测试报告: {len(self.passed)}/{total} 通过")
        print("=" * 60)
        if self.passed:
            print("\n通过:")
            for t in self.passed:
                print(f"  ✅ {t}")
        if self.failed:
            print("\n失败:")
            for t in self.failed:
                print(f"  ❌ {t}")
        print("=" * 60)
        return len(self.failed) == 0


report = TestReport()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  第一层: 不需要飞书凭证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def test_im_client_init():
    """测试 1: FeishuIMClient 实例化"""
    from feishu.im import FeishuIMClient
    client = FeishuIMClient()
    assert client is not None
    assert hasattr(client, "send_text")
    assert hasattr(client, "send_card")
    report.ok("FeishuIMClient 实例化")


async def test_send_message_schema():
    """测试 2: send_message SCHEMA 格式验证"""
    from tools import ToolRegistry

    registry = ToolRegistry()
    tools = registry.get_tools(["send_message"])
    assert len(tools) == 1, f"未找到 send_message 工具"

    schema = tools[0]
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "send_message"

    params = fn["parameters"]["properties"]
    assert "message" in params, "缺少 message 参数"
    assert "message_type" in params, "缺少 message_type 参数"
    assert "title" in params, "缺少 title 参数"
    assert "color" in params, "缺少 color 参数"

    # 向后兼容: 只有 message 是 required
    required = fn["parameters"]["required"]
    assert required == ["message"], f"required 应只有 message: {required}"

    report.ok("send_message SCHEMA 格式")


async def test_schema_backward_compat():
    """测试 3: SCHEMA 向后兼容"""
    from tools import ToolRegistry, AgentContext

    registry = ToolRegistry()
    ctx = AgentContext(record_id="test", project_name="test", role_id="account_manager")

    # 只传 message（旧格式），不传 message_type/title/color
    result = await registry.call_tool("send_message", {"message": "兼容性测试"}, ctx)
    # 无 FEISHU_CHAT_ID 时应该走 fallback
    assert "记录" in result or "发送" in result, f"向后兼容失败: {result}"
    report.ok("SCHEMA 向后兼容", "只传 message 不报错")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  第二层: 需要飞书凭证 + FEISHU_CHAT_ID
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def test_send_real_messages():
    """测试 4: 真实发送消息"""
    from config import FEISHU_CHAT_ID

    if not FEISHU_CHAT_ID:
        report.ok("真实发送-跳过", "未配置 FEISHU_CHAT_ID")
        return

    from feishu.im import FeishuIMClient
    im = FeishuIMClient()

    # 4a. 纯文本
    try:
        await im.send_text(FEISHU_CHAT_ID, "[测试] IM 通道连通性测试")
        report.ok("发送纯文本消息")
    except Exception as e:
        report.fail("发送纯文本消息", str(e))

    # 4b. 蓝色卡片
    try:
        await im.send_card(
            FEISHU_CHAT_ID,
            "测试卡片",
            "**阶段五测试**\n消息发送功能正常",
            "blue",
        )
        report.ok("发送蓝色卡片")
    except Exception as e:
        report.fail("发送蓝色卡片", str(e))

    # 4c. 通过工具调用
    from tools import ToolRegistry, AgentContext

    registry = ToolRegistry()
    ctx = AgentContext(record_id="test", project_name="测试项目", role_id="account_manager")

    result = await registry.call_tool(
        "send_message",
        {
            "message": "阶段五工具调用测试 — 来自 test_im.py",
            "message_type": "card",
            "title": "工具调用测试",
            "color": "green",
        },
        ctx,
    )
    if "失败" not in result:
        report.ok("通过工具发送卡片消息")
    else:
        report.fail("通过工具发送卡片消息", result)

    print("\n✅ 3 条消息已发送，请检查飞书群聊")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  第三层: 全链路 IM 验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class IMCounter(logging.Handler):
    """拦截 feishu.im 日志来统计消息发送。"""

    def __init__(self):
        super().__init__()
        self.cards: list[dict] = []
        self.texts: list[dict] = []

    def emit(self, record: logging.LogRecord):
        msg = record.getMessage()
        if "send_card OK" in msg:
            m = re.search(r"title=(.+?) color=(\w+)", msg)
            self.cards.append({
                "title": m.group(1) if m else "?",
                "color": m.group(2) if m else "?",
                "time": record.created,
            })
        elif "send_text OK" in msg:
            m = re.search(r"len=(\d+)", msg)
            self.texts.append({
                "len": int(m.group(1)) if m else 0,
                "time": record.created,
            })


async def test_full_pipeline():
    """第三层: 创建 Brief → Orchestrator 全链路 → 验证 IM + 多维表格"""
    from config import (
        FEISHU_CHAT_ID, LLM_API_KEY,
        PROJECT_TABLE_ID, FIELD_MAP_PROJECT as FP,
    )

    if not FEISHU_CHAT_ID or not LLM_API_KEY:
        report.ok("全链路-跳过", "未配置 FEISHU_CHAT_ID 或 LLM_API_KEY")
        return

    from feishu.bitable import BitableClient
    from memory.project import ProjectMemory, ContentMemory
    from orchestrator import Orchestrator

    # ── 挂载 IM 计数器 ──
    counter = IMCounter()
    logging.getLogger("feishu.im").addHandler(counter)

    # ── 创建 Brief ──
    client = BitableClient()
    fields = {
        FP["client_name"]: "IM全链路验证",
        FP["brief"]: (
            "双十一电商大促，主推新款玻尿酸精华液，预算5万，"
            "目标25-35岁女性，需要公众号深度测评+小红书种草笔记+抖音短视频脚本，"
            "重点突出成分科技感和性价比"
        ),
        FP["project_type"]: "电商大促",
        FP["brand_tone"]: "科技专业、成分党友好、避免过度促销感",
        FP["dept_style"]: "所有文案必须包含核心成分名称和功效数据，结尾必须有明确CTA",
        FP["status"]: "待处理",
    }
    record_id = await client.create_record(PROJECT_TABLE_ID, fields)
    logger.info("创建 Brief: %s", record_id)

    # ── 跑流水线 ──
    started = time.perf_counter()
    orch = Orchestrator(record_id=record_id)
    results = await orch.run()
    elapsed = time.perf_counter() - started

    # ── 多维表格验证 ──
    pm = ProjectMemory(record_id)
    proj = await pm.load()
    cm = ContentMemory()
    content_rows = await cm.list_by_project(proj.client_name)

    ok_stages = sum(1 for r in results if r.ok)
    drafted = [r for r in content_rows if r.draft and r.draft.strip()]
    approved = [r for r in content_rows if r.review_status == "通过"]
    scheduled = [r for r in content_rows if r.publish_date]

    # ── IM 消息统计 ──
    # Orchestrator 广播 = 启动(purple) + 阶段完成(blue) + 交付(green) + 异常(red) + 驳回(orange)
    orch_colors = {"purple", "green", "red", "orange", "blue"}
    orch_cards = [c for c in counter.cards if c["color"] in orch_colors]
    agent_cards = [c for c in counter.cards if c not in orch_cards]

    # 按时间段推断 Agent 文本消息归属
    stage_boundaries = []
    for r in results:
        stage_boundaries.append(r.role_id)

    total_msgs = len(counter.cards) + len(counter.texts)

    # ── 打印报告 ──
    minutes = int(elapsed // 60)
    seconds = elapsed - minutes * 60

    print("\n" + "=" * 50)
    print("  全链路 IM 验证报告")
    print("=" * 50)
    print(f"  记录 ID: {record_id}")
    print(f"  总耗时: {minutes} 分 {seconds:.1f} 秒")
    print()
    print("  [多维表格]")
    status_ok = proj.status == "已完成"
    print(f"    项目状态: {proj.status} {'✅' if status_ok else '⚠️'}")
    print(f"    Brief解读: {len(proj.brief_analysis)} 字 {'✅' if proj.brief_analysis.strip() else '❌'}")
    print(f"    策略方案: {len(proj.strategy)} 字 {'✅' if proj.strategy.strip() else '❌'}")
    print(f"    审核总评: {len(proj.review_summary)} 字 {'✅' if proj.review_summary.strip() else '❌'}")
    print(f"    审核通过率: {proj.review_pass_rate:.0%}")
    print(f"    交付摘要: {len(proj.delivery)} 字 {'✅' if proj.delivery.strip() else '❌'}")
    print(f"    内容行数: {len(content_rows)} 条")
    print(f"    成稿完成: {len(drafted)}/{len(content_rows)} {'✅' if len(drafted) == len(content_rows) and content_rows else '❌'}")
    print(f"    审核通过: {len(approved)}/{len(content_rows)}")
    print(f"    已排期:   {len(scheduled)} 条 {'✅' if scheduled else '❌'}")
    print()
    print("  [IM 群聊消息]")
    print(f"    Orchestrator 广播: {len(orch_cards)} 条卡片")
    print(f"    Agent 卡片消息:    {len(agent_cards)} 条")
    print(f"    Agent 文本消息:    {len(counter.texts)} 条")
    print(f"    合计: {total_msgs} 条消息")
    print()
    print("  [阶段耗时]")
    role_names = {
        "account_manager": "客户经理",
        "strategist": "策略师",
        "copywriter": "文案",
        "reviewer": "审核",
        "project_manager": "项目经理",
    }
    for r in results:
        name = role_names.get(r.role_id, r.role_id)
        flag = "✅" if r.ok else "❌"
        print(f"    {name}: {r.duration_sec:.1f}s {flag}")
    print()
    print("  请打开飞书群聊查看完整消息流")
    print("=" * 50)

    # ── 断言 ──
    if ok_stages == len(results):
        report.ok("全链路阶段完成", f"{ok_stages}/{len(results)}")
    else:
        report.fail("全链路阶段完成", f"{ok_stages}/{len(results)}")

    if proj.brief_analysis.strip() and proj.strategy.strip() and proj.review_summary.strip() and proj.delivery.strip():
        report.ok("主表关键字段非空")
    else:
        report.fail("主表关键字段非空", "Brief解读/策略/审核/交付 有空值")

    if content_rows:
        report.ok("内容行创建", f"{len(content_rows)} 条")
    else:
        report.fail("内容行创建", "0 条")

    if total_msgs >= 5:
        report.ok("IM 消息发送", f"{total_msgs} 条")
    else:
        report.fail("IM 消息发送", f"仅 {total_msgs} 条，期望 >= 5")

    if len(orch_cards) >= 2:
        report.ok("Orchestrator 广播", f"{len(orch_cards)} 条卡片")
    else:
        report.fail("Orchestrator 广播", f"仅 {len(orch_cards)} 条")

    if counter.texts:
        report.ok("Agent 主动通讯", f"{len(counter.texts)} 条文本消息")
    else:
        report.fail("Agent 主动通讯", "0 条文本消息")

    # 清理计数器
    logging.getLogger("feishu.im").removeHandler(counter)


async def main():
    print("=" * 60)
    print("飞书 IM 群聊 — 阶段五集成测试")
    print("=" * 60)

    full_mode = "--full" in sys.argv

    print("\n--- 第一层: 基础验证 ---\n")

    try:
        await test_im_client_init()
    except Exception as e:
        report.fail("FeishuIMClient 实例化", str(e))

    try:
        await test_send_message_schema()
    except Exception as e:
        report.fail("send_message SCHEMA", str(e))

    try:
        await test_schema_backward_compat()
    except Exception as e:
        report.fail("SCHEMA 向后兼容", str(e))

    print("\n--- 第二层: 真实发送 ---\n")

    try:
        await test_send_real_messages()
    except Exception as e:
        report.fail("真实发送", str(e))

    if full_mode:
        print("\n--- 第三层: 全链路 IM 验证 ---\n")
        try:
            await test_full_pipeline()
        except Exception as e:
            report.fail("全链路", str(e))
    else:
        print("\n提示: 使用 --full 参数运行全链路 IM 验证")

    all_passed = report.summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
