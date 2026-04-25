"""阶段二集成测试 — Agent 框架 + 工具系统 + ReAct 循环。

使用方法:
    python tests/test_agent.py

前置条件:
    1. 阶段一测试通过（.env 配置正确、Bitable 可读写）
    2. 如需运行 LLM 测试: .env 中配置好 LLM_API_KEY
"""

import asyncio
import json
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
logger = logging.getLogger("test_agent")


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


async def test_tool_registry():
    """测试 1: ToolRegistry 自动发现"""
    from tools import ToolRegistry

    registry = ToolRegistry()
    names = registry.tool_names
    assert len(names) >= 10, f"只发现 {len(names)} 个工具，期望 >= 10"
    report.ok("ToolRegistry 自动发现", f"共 {len(names)} 个: {names}")

    # 验证 get_tools 过滤
    subset = registry.get_tools(["read_project", "write_project"])
    assert len(subset) == 2, f"过滤后 {len(subset)} 个，期望 2"
    report.ok("ToolRegistry.get_tools 过滤")

    # 验证 schema 格式
    for tool in subset:
        assert tool["type"] == "function", f"schema type 不是 function: {tool}"
        assert "function" in tool, "schema 缺少 function 字段"
        assert "name" in tool["function"], "schema function 缺少 name"
        assert "parameters" in tool["function"], "schema function 缺少 parameters"
    report.ok("工具 schema 格式校验")

    return registry


async def test_soul_parse():
    """测试 2: soul.md 解析"""
    from agents.base import parse_soul
    from pathlib import Path

    soul_path = Path(__file__).parent.parent / "agents" / "account_manager" / "soul.md"
    text = soul_path.read_text(encoding="utf-8")
    soul = parse_soul(text)

    assert soul.name == "客户经理", f"name 不匹配: {soul.name}"
    assert soul.role_id == "account_manager", f"role_id 不匹配: {soul.role_id}"
    assert len(soul.tools) >= 4, f"工具数量 {len(soul.tools)}，期望 >= 4"
    assert soul.max_iterations > 0, f"max_iterations={soul.max_iterations}"
    assert len(soul.body) > 100, f"body 太短: {len(soul.body)} 字"

    report.ok(
        "soul.md 解析",
        f"name={soul.name}, tools={soul.tools}, "
        f"max_iter={soul.max_iterations}, body={len(soul.body)}字",
    )

    # 打印 body 前 200 字
    print(f"\n--- soul.md body 前 200 字 ---")
    print(soul.body[:200])
    print("---\n")


async def test_shared_knowledge():
    """测试 3: 共享知识加载"""
    from agents.base import load_shared_knowledge

    shared = load_shared_knowledge()
    assert len(shared) > 200, f"共享知识太短: {len(shared)} 字"
    assert "智策传媒" in shared, "未包含公司名称"
    assert "SOP" in shared or "标准操作流程" in shared, "未包含 SOP"
    assert "质量红线" in shared or "绝对禁止" in shared, "未包含质量标准"

    report.ok("共享知识加载", f"总 {len(shared)} 字")


async def test_system_prompt():
    """测试 4: system prompt 装配"""
    from agents.base import BaseAgent

    # 使用占位 record_id（不会真正调 API）
    agent = BaseAgent(role_id="account_manager", record_id="rec_test_placeholder")
    preview = agent.system_prompt_preview

    assert preview["total_chars"] > 500, f"prompt 太短: {preview['total_chars']}"
    assert len(preview["sections"]) >= 3, f"段落不足: {len(preview['sections'])}"

    print("\n--- system prompt 结构预览 ---")
    print(f"总字数: {preview['total_chars']}")
    for i, sec in enumerate(preview["sections"]):
        print(f"  [{i+1}] {sec['title']} ({sec['chars']} 字)")
    print("---\n")

    report.ok(
        "system prompt 装配",
        f"总 {preview['total_chars']} 字, {len(preview['sections'])} 段",
    )


async def test_tool_call():
    """测试 5: 工具实际调用（需要 Bitable 连接）"""
    from tools import ToolRegistry, AgentContext
    from config import PROJECT_TABLE_ID
    from feishu.bitable import BitableClient

    # 先找一条已有记录（用较大 page_size 减少请求次数）
    client = BitableClient()
    records = await client.list_records(PROJECT_TABLE_ID, page_size=20)
    if not records:
        report.ok("工具调用测试-跳过", "Bitable 中无记录")
        return

    rid = records[0]["record_id"]
    ctx = AgentContext(
        record_id=rid,
        project_name=records[0]["fields"].get("客户名称", "test"),
        role_id="account_manager",
    )

    registry = ToolRegistry()

    # 调用 read_project
    result = await registry.call_tool(
        "read_project", {"fields": ["brief_content", "brand_tone", "status"]}, ctx
    )
    assert "错误" not in result or "未知字段" not in result, f"read_project 出错: {result}"
    report.ok("工具调用 read_project", result[:80])

    # 调用 send_message (stub)
    result2 = await registry.call_tool(
        "send_message", {"message": "测试消息"}, ctx
    )
    assert "消息已发送" in result2 or "stub" in result2, f"send_message 异常: {result2}"
    report.ok("工具调用 send_message")

    # 调用不存在的工具
    result3 = await registry.call_tool("nonexistent_tool", {}, ctx)
    assert "不存在" in result3 or "错误" in result3
    report.ok("不存在工具的错误处理")


async def test_react_loop():
    """测试 6: 完整 ReAct 循环（需要 LLM API key + Bitable 记录）"""
    from config import LLM_API_KEY, PROJECT_TABLE_ID
    from feishu.bitable import BitableClient

    if not LLM_API_KEY or LLM_API_KEY.startswith("sk-xxxx"):
        report.ok("ReAct 循环-跳过", "未配置 LLM_API_KEY")
        return

    # 找一条测试记录
    client = BitableClient()
    records = await client.list_records(PROJECT_TABLE_ID, page_size=5)
    # 找一条状态为"待处理"的记录
    target = None
    for r in records:
        if r["fields"].get("状态") == "待处理":
            target = r
            break

    if not target:
        report.ok("ReAct 循环-跳过", "Bitable 中无'待处理'状态记录")
        return

    rid = target["record_id"]
    print(f"\n--- ReAct 循环测试 ---")
    print(f"使用记录: {rid}")
    print(f"客户名称: {target['fields'].get('客户名称', 'N/A')}")
    print(f"Brief: {str(target['fields'].get('Brief 内容', 'N/A'))[:100]}...")

    from agents.base import BaseAgent
    agent = BaseAgent(role_id="account_manager", record_id=rid)
    result = await agent.run()

    print(f"\n--- 最终输出 ---")
    print(result[:500] if result else "(空)")
    print("---\n")

    assert result and len(result) > 50, f"输出太短或为空: {result}"
    report.ok("ReAct 循环完整运行", f"输出 {len(result)} 字")


async def main():
    print("=" * 60)
    print("Agent 框架 — 阶段二集成测试")
    print("=" * 60)

    try:
        await test_tool_registry()
    except Exception as e:
        report.fail("ToolRegistry", str(e))

    try:
        await test_soul_parse()
    except Exception as e:
        report.fail("soul.md 解析", str(e))

    try:
        await test_shared_knowledge()
    except Exception as e:
        report.fail("共享知识加载", str(e))

    try:
        await test_system_prompt()
    except Exception as e:
        report.fail("system prompt 装配", str(e))

    try:
        await test_tool_call()
    except Exception as e:
        report.fail("工具调用", str(e))

    try:
        await test_react_loop()
    except Exception as e:
        report.fail("ReAct 循环", str(e))

    all_passed = report.summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
