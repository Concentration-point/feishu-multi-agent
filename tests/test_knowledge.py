"""阶段四集成测试 — 本地知识库 + 知识工具 + Wiki 同步。

使用方法:
    python tests/test_knowledge.py

第一层测试不需要飞书凭证。
第二层测试需要 WIKI_SPACE_ID 配置。
"""

import asyncio
import json
import sys
import os
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("test_knowledge")


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
#  第一层: 本地知识库测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def test_seed_docs():
    """测试 1: 种子文档验证"""
    from pathlib import Path
    from config import KNOWLEDGE_BASE_PATH

    raw_dir = Path(KNOWLEDGE_BASE_PATH) / "raw"
    assert raw_dir.exists(), f"raw 目录不存在: {raw_dir}"

    md_files = list(raw_dir.glob("*.md"))
    assert len(md_files) >= 2, f"raw/ 下只有 {len(md_files)} 个文件，期望 >= 2"

    for f in md_files:
        content = f.read_text(encoding="utf-8")
        char_count = len(content)
        assert char_count > 500, f"{f.name} 只有 {char_count} 字，期望 > 500"
        print(f"  {f.name}: {char_count} 字")

    report.ok("种子文档验证", f"{len(md_files)} 个文件")


async def test_search_knowledge():
    """测试 2: search_knowledge 搜索"""
    from tools import ToolRegistry, AgentContext

    registry = ToolRegistry()
    ctx = AgentContext(record_id="test", project_name="test", role_id="test")

    # 搜 "小红书 种草"
    result1 = await registry.call_tool(
        "search_knowledge", {"query": "小红书 种草"}, ctx
    )
    assert "找到" in result1, f"搜索'小红书 种草'未返回结果: {result1[:100]}"
    print(f"\n--- 搜索 '小红书 种草' ---")
    print(result1[:300])
    report.ok("搜索 '小红书 种草'", "有结果")

    # 搜不存在的
    result2 = await registry.call_tool(
        "search_knowledge", {"query": "完全不存在的关键词xyz"}, ctx
    )
    assert "未找到" in result2, f"应返回未找到: {result2[:100]}"
    report.ok("搜索不存在关键词", "返回未找到")

    # 搜 "电商 营销 策略"
    result3 = await registry.call_tool(
        "search_knowledge", {"query": "电商 营销 策略"}, ctx
    )
    assert "找到" in result3, f"搜索'电商 营销 策略'未返回: {result3[:100]}"
    # 验证按命中数排序（第一个的命中数应 >= 后面的）
    print(f"\n--- 搜索 '电商 营销 策略' ---")
    print(result3[:300])
    report.ok("搜索 '电商 营销 策略'", "有结果且排序")


async def test_read_knowledge():
    """测试 3: read_knowledge 读取"""
    from tools import ToolRegistry, AgentContext

    registry = ToolRegistry()
    ctx = AgentContext(record_id="test", project_name="test", role_id="test")

    # 读取第一篇
    result1 = await registry.call_tool(
        "read_knowledge",
        {"filepath": "raw/某美妆品牌618电商营销全案.md"},
        ctx,
    )
    assert len(result1) > 100, f"读取内容太短: {len(result1)}"
    assert "花漾美肌" in result1 or "618" in result1, "内容不匹配"
    report.ok("读取 raw 文档", f"{len(result1)} 字")

    # 读取不存在的
    result2 = await registry.call_tool(
        "read_knowledge", {"filepath": "不存在的文件.md"}, ctx
    )
    assert "错误" in result2 or "不存在" in result2, f"应返回错误: {result2[:100]}"
    report.ok("读取不存在文件", "返回错误信息")


async def test_write_wiki():
    """测试 4: write_wiki 写入 + 索引更新 + dirty 标记"""
    from tools import ToolRegistry, AgentContext
    from pathlib import Path
    from config import KNOWLEDGE_BASE_PATH

    registry = ToolRegistry()
    ctx = AgentContext(record_id="test", project_name="test", role_id="test")

    # 写入测试经验
    result = await registry.call_tool(
        "write_wiki",
        {
            "category": "电商大促",
            "title": "测试经验",
            "content": "这是一条测试经验内容，用于验证 write_wiki 工具的功能。",
        },
        ctx,
    )
    assert "已写入" in result, f"写入失败: {result}"
    report.ok("write_wiki 写入")

    base = Path(KNOWLEDGE_BASE_PATH)

    # 验证文件存在
    target = base / "wiki" / "电商大促" / "测试经验.md"
    assert target.exists(), f"文件不存在: {target}"
    content = target.read_text(encoding="utf-8")
    assert "---" in content, "缺少 frontmatter"
    assert "测试经验内容" in content, "正文缺失"
    report.ok("文件创建验证")

    # 验证索引更新
    index = base / "wiki" / "_index.md"
    index_content = index.read_text(encoding="utf-8")
    assert "测试经验" in index_content, f"索引未包含新条目"
    report.ok("_index.md 索引更新")

    # 验证 dirty 标记
    state_file = base / ".sync_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert "wiki/电商大促/测试经验.md" in state, "sync_state 中无该文件"
    assert state["wiki/电商大促/测试经验.md"]["dirty"] is True, "未标记为 dirty"
    report.ok(".sync_state.json dirty 标记")

    # 验证搜索能搜到
    result2 = await registry.call_tool(
        "search_knowledge", {"query": "测试经验"}, ctx
    )
    assert "找到" in result2, f"搜索写入的 wiki 文件失败: {result2[:100]}"
    report.ok("搜索新写入的 wiki")

    # 清理
    shutil.rmtree(base / "wiki" / "电商大促", ignore_errors=True)
    # 重建索引
    from tools.write_wiki import _update_index
    _update_index(base / "wiki")
    # 清理 state
    state.pop("wiki/电商大促/测试经验.md", None)
    state.pop("wiki/_index.md", None)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    report.ok("测试清理完成")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  第二层: 同步测试（需要飞书凭证）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def test_wiki_sync():
    """测试 5: WikiSyncService 同步（需要 WIKI_SPACE_ID）"""
    from config import WIKI_SPACE_ID
    from pathlib import Path
    from config import KNOWLEDGE_BASE_PATH

    if not WIKI_SPACE_ID:
        report.ok("Wiki 同步测试-跳过", "未配置 WIKI_SPACE_ID")
        return

    base = Path(KNOWLEDGE_BASE_PATH)

    # 写入测试文件
    from tools import ToolRegistry, AgentContext
    registry = ToolRegistry()
    ctx = AgentContext(record_id="test", project_name="test", role_id="test")

    await registry.call_tool(
        "write_wiki",
        {
            "category": "同步测试",
            "title": "同步验证文档",
            "content": "此文档用于验证 WikiSyncService 同步功能。",
        },
        ctx,
    )

    # 手动 trigger sync
    from sync.wiki_sync import WikiSyncService
    sync = WikiSyncService(WIKI_SPACE_ID)

    try:
        await sync.sync_once()
        report.ok("WikiSync 同步执行")
    except Exception as e:
        report.fail("WikiSync 同步执行", str(e))

    # 验证飞书知识空间
    try:
        from feishu.wiki import FeishuWikiClient
        wiki_client = FeishuWikiClient()
        nodes = await wiki_client.list_nodes(WIKI_SPACE_ID)
        titles = [n.get("title", "") for n in nodes]
        print(f"  飞书知识空间节点: {titles}")
        report.ok("飞书节点列表读取", f"{len(nodes)} 个节点")
    except Exception as e:
        report.fail("飞书节点列表读取", str(e))

    # 清理本地
    shutil.rmtree(base / "wiki" / "同步测试", ignore_errors=True)
    from tools.write_wiki import _update_index
    _update_index(base / "wiki")


async def main():
    print("=" * 60)
    print("知识库 — 阶段四集成测试")
    print("=" * 60)

    print("\n--- 第一层: 本地知识库测试 ---\n")

    try:
        await test_seed_docs()
    except Exception as e:
        report.fail("种子文档验证", str(e))

    try:
        await test_search_knowledge()
    except Exception as e:
        report.fail("search_knowledge", str(e))

    try:
        await test_read_knowledge()
    except Exception as e:
        report.fail("read_knowledge", str(e))

    try:
        await test_write_wiki()
    except Exception as e:
        report.fail("write_wiki", str(e))

    print("\n--- 第二层: 同步测试 ---\n")

    try:
        await test_wiki_sync()
    except Exception as e:
        report.fail("Wiki 同步", str(e))

    all_passed = report.summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
