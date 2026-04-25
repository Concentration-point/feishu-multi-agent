"""阶段一集成测试 — 跑通飞书多维表格读写链路。

使用方法:
    python tests/test_bitable.py

前置条件:
    1. .env 中配置好 FEISHU_APP_ID / FEISHU_APP_SECRET
    2. .env 中配置好 BITABLE_APP_TOKEN / PROJECT_TABLE_ID / CONTENT_TABLE_ID
    3. 飞书多维表格已按 CLAUDE.md 建好项目主表和内容排期表
"""

import asyncio
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows GBK 终端兼容 UTF-8 输出
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("test_bitable")


# ── 测试结果统计 ──

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

    def summary(self):
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


async def test_auth():
    """测试 1: 获取 tenant_access_token"""
    from feishu.auth import TokenManager

    tm = TokenManager()
    token = await tm.get_token()
    assert token and len(token) > 10, "token 为空或太短"
    report.ok("鉴权获取 token", f"token={token[:20]}...")

    # 第二次调用应该命中缓存
    token2 = await tm.get_token()
    assert token2 == token, "第二次获取 token 不一致，缓存未生效"
    report.ok("鉴权 token 缓存复用")


async def test_project_table_crud():
    """测试 2: 项目主表 CRUD"""
    from feishu.bitable import BitableClient
    from config import PROJECT_TABLE_ID, FIELD_MAP_PROJECT as FP

    client = BitableClient()

    # 2a. 列出记录
    records = await client.list_records(PROJECT_TABLE_ID)
    report.ok("项目主表-列出记录", f"现有 {len(records)} 条")

    # 2b. 创建测试 Brief
    test_fields = {
        FP["client_name"]: "测试客户-Agent",
        FP["brief"]: "双十一电商大促测试Brief，主推新品精华液",
        FP["project_type"]: "电商大促",
        FP["brand_tone"]: "科技感、专业、年轻",
        FP["dept_style"]: "所有文案必须包含CTA",
        FP["status"]: "待处理",
    }
    record_id = await client.create_record(PROJECT_TABLE_ID, test_fields)
    assert record_id, "创建记录未返回 record_id"
    report.ok("项目主表-创建记录", f"record_id={record_id}")

    # 2c. 读取验证
    fields = await client.get_record(PROJECT_TABLE_ID, record_id)
    assert fields.get(FP["client_name"]) == "测试客户-Agent", (
        f"客户名称不匹配: {fields.get(FP['client_name'])}"
    )
    report.ok("项目主表-读取验证", f"客户名称={fields.get(FP['client_name'])}")

    # 2d. 更新 Brief 解读字段
    analysis = "【Brief 解读】目标受众: 25-35岁女性; 核心诉求: 双十一精华液种草"
    await client.update_record(
        PROJECT_TABLE_ID, record_id, {FP["brief_analysis"]: analysis}
    )
    fields2 = await client.get_record(PROJECT_TABLE_ID, record_id)
    assert analysis in fields2.get(FP["brief_analysis"], ""), "更新后读取不匹配"
    report.ok("项目主表-更新并验证 Brief 解读")

    return record_id


async def test_content_table_crud(project_name: str = "测试客户-Agent"):
    """测试 3: 内容排期表 CRUD"""
    from feishu.bitable import BitableClient
    from config import CONTENT_TABLE_ID, FIELD_MAP_CONTENT as FC

    client = BitableClient()

    # 3a. 批量创建 3 条内容行
    items = [
        {
            FC["project_name"]: project_name,
            FC["seq"]: 1,
            FC["title"]: "双十一囤货清单｜精华液横评",
            FC["platform"]: "公众号",
            FC["content_type"]: "深度长文",
            FC["key_point"]: "成分对比+性价比分析",
            FC["target_audience"]: "25-30岁成分党女性",
        },
        {
            FC["project_name"]: project_name,
            FC["seq"]: 2,
            FC["title"]: "3步get发光肌｜精华液种草",
            FC["platform"]: "小红书",
            FC["content_type"]: "种草笔记",
            FC["key_point"]: "使用前后对比+护肤步骤",
            FC["target_audience"]: "20-28岁护肤新手",
        },
        {
            FC["project_name"]: project_name,
            FC["seq"]: 3,
            FC["title"]: "精华液开箱实测60秒",
            FC["platform"]: "抖音脚本",
            FC["content_type"]: "口播脚本",
            FC["key_point"]: "质地展示+即时效果",
            FC["target_audience"]: "18-35岁短视频用户",
        },
    ]
    record_ids = await client.batch_create_records(CONTENT_TABLE_ID, items)
    assert len(record_ids) == 3, f"批量创建返回 {len(record_ids)} 条，期望 3 条"
    report.ok("内容排期表-批量创建 3 条", f"ids={record_ids}")

    # 3b. 列出该项目的所有内容行
    filter_expr = f'CurrentValue.[{FC["project_name"]}]="{project_name}"'
    rows = await client.list_records(CONTENT_TABLE_ID, filter_expr)
    assert len(rows) >= 3, f"筛选后仅 {len(rows)} 条，期望 >= 3"
    report.ok("内容排期表-按项目筛选列出", f"count={len(rows)}")

    # 3c. 更新第一条的成稿内容
    draft_text = "【公众号长文】双十一囤货清单来了！今年最值得入手的精华液..."
    await client.update_record(
        CONTENT_TABLE_ID,
        record_ids[0],
        {FC["draft"]: draft_text, FC["word_count"]: len(draft_text)},
    )
    fields = await client.get_record(CONTENT_TABLE_ID, record_ids[0])
    assert draft_text in fields.get(FC["draft"], ""), "成稿内容更新后不匹配"
    report.ok("内容排期表-更新成稿并验证")

    return record_ids


async def test_project_memory(record_id: str):
    """测试 4: ProjectMemory 语义化读写"""
    from memory.project import ProjectMemory

    pm = ProjectMemory(record_id)

    # 4a. load 全量
    proj = await pm.load()
    assert proj.client_name == "测试客户-Agent", f"load 客户名不匹配: {proj.client_name}"
    report.ok("ProjectMemory.load()", f"客户={proj.client_name}, 状态={proj.status}")

    # 4b. 单字段读
    brief = await pm.get_brief()
    assert "双十一" in brief, f"get_brief 不含关键词: {brief}"
    report.ok("ProjectMemory.get_brief()")

    tone = await pm.get_brand_tone()
    assert "科技" in tone, f"get_brand_tone 不含关键词: {tone}"
    report.ok("ProjectMemory.get_brand_tone()")

    # 4c. 语义化写
    await pm.update_status("解读中")
    proj2 = await pm.load()
    assert proj2.status == "解读中", f"状态更新失败: {proj2.status}"
    report.ok("ProjectMemory.update_status()")

    await pm.write_strategy("策略方案：3篇公众号+5条小红书+2个抖音脚本")
    proj3 = await pm.load()
    assert "策略方案" in proj3.strategy, f"策略写入失败: {proj3.strategy}"
    report.ok("ProjectMemory.write_strategy()")

    await pm.write_knowledge_ref(["618电商营销全案", "新品发布传播方案"])
    proj4 = await pm.load()
    assert "618" in proj4.knowledge_ref, f"知识引用写入失败: {proj4.knowledge_ref}"
    report.ok("ProjectMemory.write_knowledge_ref()")


async def test_content_memory():
    """测试 5: ContentMemory 语义化读写"""
    from memory.project import ContentMemory, ContentItem

    cm = ContentMemory()
    project_name = "测试客户-Agent-Memory"

    # 5a. 创建单条
    item = ContentItem(
        seq=1,
        title="语义化测试-单条创建",
        platform="微博",
        content_type="话题文案",
        key_point="测试核心卖点",
        target_audience="测试人群",
    )
    rid = await cm.create_content_item(project_name, item)
    assert rid, "单条创建未返回 record_id"
    report.ok("ContentMemory.create_content_item()", f"record_id={rid}")

    # 5b. 批量创建
    items = [
        ContentItem(seq=2, title="语义化测试-批量1", platform="公众号",
                    content_type="深度长文", key_point="卖点A", target_audience="人群A"),
        ContentItem(seq=3, title="语义化测试-批量2", platform="小红书",
                    content_type="种草笔记", key_point="卖点B", target_audience="人群B"),
    ]
    rids = await cm.batch_create_content_items(project_name, items)
    assert len(rids) == 2, f"批量创建返回 {len(rids)}，期望 2"
    report.ok("ContentMemory.batch_create_content_items()", f"ids={rids}")

    # 5c. 按项目列出
    rows = await cm.list_by_project(project_name)
    assert len(rows) >= 3, f"列出 {len(rows)} 条，期望 >= 3"
    report.ok("ContentMemory.list_by_project()", f"count={len(rows)}")

    # 5d. 写成稿
    await cm.write_draft(rid, "微博话题文案正文测试内容", 12)
    rows2 = await cm.list_by_project(project_name)
    first = [r for r in rows2 if r.record_id == rid][0]
    assert "微博" in first.draft, f"write_draft 失败: {first.draft}"
    report.ok("ContentMemory.write_draft()")

    # 5e. 写审核
    await cm.write_review(rid, "通过", "内容质量合格，无违规")
    rows3 = await cm.list_by_project(project_name)
    first2 = [r for r in rows3 if r.record_id == rid][0]
    assert first2.review_status == "通过", f"write_review 失败: {first2.review_status}"
    report.ok("ContentMemory.write_review()")

    # 5f. 写发布日期
    await cm.write_publish_date(rid, "2026-11-11")
    report.ok("ContentMemory.write_publish_date()")


async def main():
    print("=" * 60)
    print("飞书 Bitable 共享记忆层 — 阶段一集成测试")
    print("=" * 60)

    try:
        await test_auth()
    except Exception as e:
        report.fail("鉴权", str(e))
        report.summary()
        return

    record_id = None
    try:
        record_id = await test_project_table_crud()
    except Exception as e:
        report.fail("项目主表 CRUD", str(e))

    try:
        await test_content_table_crud()
    except Exception as e:
        report.fail("内容排期表 CRUD", str(e))

    if record_id:
        try:
            await test_project_memory(record_id)
        except Exception as e:
            report.fail("ProjectMemory 语义化读写", str(e))

    try:
        await test_content_memory()
    except Exception as e:
        report.fail("ContentMemory 语义化读写", str(e))

    all_passed = report.summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
