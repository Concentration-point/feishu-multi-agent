"""FIX-05 验证：save_experience 后自动触发桶合并。

运行方式:
    python tests/test_bucket_automerge.py

验证步骤:
1. 向同一桶 (reviewer, _test_bucket_merge) 连续写入 4 条相似但不完全相同的经验
2. 第 4 条写入后应自动触发 optimize_bucket（日志可见）
3. 验证桶内经验数量 ≤ EXPERIENCE_MAX_PER_CATEGORY (默认 3)
4. 清理所有测试记录
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("test_bucket_automerge")

TEST_ROLE = "reviewer"
TEST_CATEGORY = "_test_bucket_merge"
TEST_PROJECT = "FIX-05-验证项目"
CONFIDENCE = 0.80

# 4 条主题差异大的 reviewer 经验，确保相互间语义相似度 < 0.85，全部入库触发合并
TEST_CARDS = [
    {
        "situation": "审核电商大促小红书笔记，发现绝对化用词",
        "action": "先用 search_knowledge 查禁用词库，逐条比对，标注违规位置",
        "outcome": "拦截 3 处违规表述，避免平台处罚",
        "lesson": "审核前必须先查禁用词库，避免绝对化用词（第一、最好、最强）导致平台限流",
        "category": TEST_CATEGORY,
        "applicable_roles": [TEST_ROLE],
    },
    {
        "situation": "图片素材审核发现版权水印未清除，存在侵权风险",
        "action": "建立图片来源检查步骤：确认素材授权文件，检查水印、品牌logo是否合规",
        "outcome": "图片侵权投诉率下降至零，账号信用分提升",
        "lesson": "图片版权审核必须先确认授权文件，禁止使用未授权的品牌logo或明星肖像",
        "category": TEST_CATEGORY,
        "applicable_roles": [TEST_ROLE],
    },
    {
        "situation": "母婴产品广告含有未经验证的医疗功效声称",
        "action": "查阅广告法合规指南，识别功效声称类型，区分特证和普证产品的允许表述",
        "outcome": "全部医疗功效声称被替换为合法表述，通过平台审核",
        "lesson": "医疗健康类声称应该对照广告法第十七条逐条核查，普通食品禁止声称疾病预防",
        "category": TEST_CATEGORY,
        "applicable_roles": [TEST_ROLE],
    },
    {
        "situation": "抖音内容中出现未成年人演示购买行为，触发平台未成年人保护审查",
        "action": "制定儿童内容专项检查表：确认无引导购买场景、无暗示早熟内容、无危险动作",
        "outcome": "儿童相关内容违规率降为零，账号通过平台专项审查",
        "lesson": "涉及未成年人的内容必须先用儿童保护检查表逐项审核，避免引导购买和危险行为",
        "category": TEST_CATEGORY,
        "applicable_roles": [TEST_ROLE],
    },
]


async def cleanup_test_records(em, client) -> int:
    """清理所有测试分类的 Bitable 记录。"""
    from config import EXPERIENCE_TABLE_ID, FIELD_MAP_EXPERIENCE as FE
    filter_expr = (
        f'AND(CurrentValue.[{FE["role"]}]="{TEST_ROLE}",'
        f'CurrentValue.[{FE["scene"]}]="{TEST_CATEGORY}")'
    )
    records = await client.list_records(EXPERIENCE_TABLE_ID, filter_expr)
    deleted = 0
    for record in records:
        try:
            await client.delete_record(EXPERIENCE_TABLE_ID, record["record_id"])
            deleted += 1
        except Exception as e:
            logger.warning("清理测试记录失败: %s", e)

    # 清理 Chroma
    try:
        from memory.experience_store import ExperienceVectorStore
        store = ExperienceVectorStore()
        existing = store.query(TEST_CATEGORY, role_id=TEST_ROLE, k=20)
        for item in existing:
            store.delete(item["id"])
    except Exception as e:
        logger.warning("清理 Chroma 测试记录失败: %s", e)

    return deleted


async def get_bucket_count(em) -> int:
    records = await em._list_bucket_records(TEST_ROLE, TEST_CATEGORY)
    return len(records)


async def main() -> None:
    from config import EXPERIENCE_MAX_PER_CATEGORY
    from feishu.bitable import BitableClient
    from memory.experience import ExperienceManager

    client = BitableClient()
    em = ExperienceManager(client=client)

    print("=" * 60)
    print("FIX-05: 桶自动合并验证")
    print(f"  桶: role={TEST_ROLE} / category={TEST_CATEGORY}")
    print(f"  EXPERIENCE_MAX_PER_CATEGORY = {EXPERIENCE_MAX_PER_CATEGORY}")
    print("=" * 60)

    # 先清理历史遗留
    deleted = await cleanup_test_records(em, client)
    if deleted:
        print(f"\n[前置清理] 清除 {deleted} 条历史测试记录")

    passed: list[str] = []
    failed: list[str] = []

    # ── 逐条写入，观察触发 ──
    print(f"\n[写入] 准备写入 {len(TEST_CARDS)} 条经验到同一桶...\n")
    record_ids: list[str] = []

    for i, card in enumerate(TEST_CARDS, 1):
        count_before = await get_bucket_count(em)
        print(f"  写入第 {i} 条 (桶当前: {count_before} 条)...")
        record_id = await em.save_experience(card, CONFIDENCE, TEST_PROJECT)
        count_after = await get_bucket_count(em)
        print(f"  写入第 {i} 条完成 → record_id={record_id} | 桶变化: {count_before} → {count_after}")

        if record_id:
            record_ids.append(record_id)

        # 第 4 条写入后检查合并是否触发（桶应 ≤ EXPERIENCE_MAX_PER_CATEGORY-1 或 = EXPERIENCE_MAX_PER_CATEGORY）
        if i == len(TEST_CARDS):
            print(f"\n[合并检查] 第 {i} 条写入后，桶内 {count_after} 条")
            # 合并触发要求：写入第4条后桶大小 ≤ EXPERIENCE_MAX_PER_CATEGORY
            # 若4条全入库则会超限并触发合并压缩至 ≤ max；若去重拦截则可能仍 ≤ max
            if count_after <= EXPERIENCE_MAX_PER_CATEGORY:
                passed.append(f"写入第{i}条后桶大小={count_after} ≤ 阈值{EXPERIENCE_MAX_PER_CATEGORY}（合并触发或去重生效）")
                print(f"  ✅ 桶大小 {count_after} ≤ EXPERIENCE_MAX_PER_CATEGORY ({EXPERIENCE_MAX_PER_CATEGORY})")
            else:
                failed.append(f"写入第{i}条后桶大小={count_after} > 阈值{EXPERIENCE_MAX_PER_CATEGORY}，合并未触发或失败")
                print(f"  ❌ 桶大小 {count_after} > EXPERIENCE_MAX_PER_CATEGORY ({EXPERIENCE_MAX_PER_CATEGORY})")

    # ── 验证合并后 lesson 覆盖要点 ──
    print("\n[内容检查] 读取合并后的经验...")
    final_records = await em._list_bucket_records(TEST_ROLE, TEST_CATEGORY)
    print(f"  合并后桶内共 {len(final_records)} 条\n")
    keywords_to_cover = ["禁用词", "绝对化", "清单", "必须"]
    merged_text = ""
    for r in final_records:
        payload = r.get("_payload", {})
        lesson = payload.get("lesson", "")
        print(f"  lesson: {lesson[:120]}")
        merged_text += lesson

    covered = [kw for kw in keywords_to_cover if kw in merged_text]
    print(f"\n  关键词覆盖: {covered}/{keywords_to_cover}")
    if len(covered) >= 2:
        passed.append(f"合并后 lesson 覆盖 {len(covered)}/{len(keywords_to_cover)} 个关键词")
        print(f"  ✅ 关键词覆盖 {len(covered)}/{len(keywords_to_cover)}")
    else:
        failed.append(f"合并后 lesson 仅覆盖 {len(covered)}/{len(keywords_to_cover)} 个关键词")
        print(f"  ❌ 关键词覆盖不足 {len(covered)}/{len(keywords_to_cover)}")

    # ── 清理 ──
    print("\n[清理] 删除所有测试记录...")
    cleaned = await cleanup_test_records(em, client)
    print(f"  已清理 {cleaned} 条 Bitable 记录 + Chroma 向量")

    # ── 报告 ──
    print("\n" + "=" * 60)
    print(f"FIX-05 验证结果: {len(passed)} 通过 / {len(failed)} 失败")
    print("=" * 60)
    for p in passed:
        print(f"  ✅ {p}")
    for f in failed:
        print(f"  ❌ {f}")
    print("=" * 60)

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    asyncio.run(main())
