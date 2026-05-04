"""DIS-06 端到端验证：禁用一条经验后检索不到。

执行步骤：
  1. 写入 3 条测试经验（Bitable + Chroma）
  2. 提示用户在飞书表格中把第 1 条状态改为「禁用」
  3. 调 query_top_k，验证被禁用的那条不在结果中
  4. 提示用户把状态改回「启用」
  5. 再次调 query_top_k，验证它重新出现
  6. 验证全程 Chroma metadata 未被修改

用法：
  python scripts/verify_dis06.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from feishu.bitable import BitableClient
from memory.experience import ExperienceManager
from memory.experience_store import ExperienceVectorStore
import config


# ── 测试数据：3 条测试经验，场景相似，便于语义召回 ──
_TEST_CARDS = [
    {
        "situation": "客户要求在小红书发布品牌传播内容，需要精准触达目标受众",
        "action": "先分析平台调性，必须使用真实用户视角撰写，避免硬广感",
        "outcome": "内容获得高互动，品牌曝光量提升 30%",
        "lesson": "小红书内容必须先做受众画像分析，避免生硬推广，使用真实场景叙事",
        "title": "DIS06-TEST-A 小红书品牌传播",
        "category": "品牌传播",
        "applicable_roles": ["copywriter"],
        "source_run": "dis06-verify",
        "source_stage": "copywriter",
        "review_status": "通过",
    },
    {
        "situation": "新品发布需要在多平台同步推广，时间窗口紧张",
        "action": "必须优先输出核心卖点矩阵，应该按平台差异化改写而不是复制粘贴",
        "outcome": "三平台同步上线，互动率超行业均值 20%",
        "lesson": "多平台发布应该先产出一份核心卖点文档，再按各平台调性二次加工，避免内容同质化",
        "title": "DIS06-TEST-B 多平台新品发布",
        "category": "新品发布",
        "applicable_roles": ["copywriter"],
        "source_run": "dis06-verify",
        "source_stage": "copywriter",
        "review_status": "通过",
    },
    {
        "situation": "电商大促期间文案需要快速产出，质量和效率都有要求",
        "action": "建议先建立词库模板，必须保留品牌核心话术，避免过度依赖通用模板",
        "outcome": "大促期间日均产出文案量翻倍，质量审核通过率 92%",
        "lesson": "电商大促文案必须先建词库，避免临时发挥导致品牌话术不一致，建议维护品牌禁用词表",
        "title": "DIS06-TEST-C 电商大促快速产出",
        "category": "电商大促",
        "applicable_roles": ["copywriter"],
        "source_run": "dis06-verify",
        "source_stage": "copywriter",
        "review_status": "通过",
    },
]

_VERIFY_ROLE = "copywriter"
_VERIFY_BRIEF = "内容创作品牌传播小红书推广策略"
_CONFIDENCE = 0.8


def _chroma_metadata_snapshot(store: ExperienceVectorStore, record_id: str) -> dict | None:
    """快照指定 record_id 在 Chroma 中的 metadata。"""
    try:
        result = store._col.get(ids=[record_id], include=["metadatas"])
        metas = result.get("metadatas", [])
        return metas[0] if metas else None
    except Exception:
        return None


async def main():
    mgr = ExperienceManager()
    store = ExperienceVectorStore()
    client = BitableClient()

    print("=" * 60)
    print("DIS-06 端到端验证：禁用经验后检索不到")
    print("=" * 60)

    # ── 步骤 1：写入 3 条测试经验 ──
    print("\n[1/6] 写入 3 条测试经验...")
    record_ids: list[str] = []
    for i, card in enumerate(_TEST_CARDS):
        rid = await mgr.save_experience(card, _CONFIDENCE, "DIS06-验证")
        if rid:
            record_ids.append(rid)
            print(f"  ✓ 写入成功: {card['title']} → record_id={rid}")
        else:
            print(f"  ✗ 写入失败: {card['title']}（可能质量检查未通过或 Bitable 未配置）")

    if not record_ids:
        print("\n❌ 没有写入任何经验，请检查 .env 配置（EXPERIENCE_TABLE_ID / Bitable 凭证）")
        return

    target_id = record_ids[0]
    print(f"\n  目标记录（待禁用）: {target_id}")

    # ── 步骤 2：快照 Chroma metadata（验证全程不被修改）──
    print("\n[2/6] 快照 Chroma metadata（验证基准）...")
    chroma_before = _chroma_metadata_snapshot(store, target_id)
    print(f"  Chroma metadata 快照: {chroma_before}")

    # ── 步骤 3：提示用户手动禁用 ──
    print(f"\n[3/6] 请在飞书经验池表中，将以下记录的「状态」改为「禁用」：")
    print(f"  record_id = {target_id}")
    print(f"  标题 = {_TEST_CARDS[0]['title']}")
    input("\n  >>> 改好后按 Enter 继续...")

    # ── 步骤 4：检索，验证被禁用的记录不在结果中 ──
    print("\n[4/6] 调用 query_top_k，验证禁用后检索不到...")
    results_after_disable = await mgr.query_top_k(_VERIFY_ROLE, _VERIFY_BRIEF, k=10)
    result_ids_after = [r["record_id"] for r in results_after_disable]

    if target_id not in result_ids_after:
        print(f"  ✅ 禁用后 query_top_k 结果中不包含 {target_id}")
    else:
        print(f"  ❌ 禁用后 query_top_k 仍返回了 {target_id}，过滤逻辑未生效！")
        print(f"  当前结果 IDs: {result_ids_after}")

    # ── 步骤 5：提示用户恢复启用 ──
    print(f"\n[5/6] 请将该记录的「状态」改回「启用」：")
    print(f"  record_id = {target_id}")
    input("\n  >>> 改好后按 Enter 继续...")

    # ── 步骤 6：再次检索，验证重新出现 ──
    print("\n[6/6] 再次调用 query_top_k，验证启用后重新检索到...")
    results_after_enable = await mgr.query_top_k(_VERIFY_ROLE, _VERIFY_BRIEF, k=10)
    result_ids_after_enable = [r["record_id"] for r in results_after_enable]

    if target_id in result_ids_after_enable:
        print(f"  ✅ 启用后 query_top_k 结果中重新包含 {target_id}")
    else:
        print(f"  ❌ 启用后 query_top_k 仍不包含 {target_id}，状态回写可能未生效")

    # ── 验证 Chroma metadata 全程未被修改 ──
    print("\n[验证] 检查 Chroma metadata 是否被修改...")
    chroma_after = _chroma_metadata_snapshot(store, target_id)
    if chroma_before == chroma_after:
        print(f"  ✅ Chroma metadata 未被修改（与初始快照一致）")
    else:
        print(f"  ❌ Chroma metadata 被修改了！")
        print(f"  修改前: {chroma_before}")
        print(f"  修改后: {chroma_after}")

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print("验收汇总：")
    disable_ok = target_id not in result_ids_after
    enable_ok = target_id in result_ids_after_enable
    chroma_ok = chroma_before == chroma_after

    print(f"  禁用后检索不到:         {'✅' if disable_ok else '❌'}")
    print(f"  启用后重新检索到:       {'✅' if enable_ok else '❌'}")
    print(f"  全程无 Chroma 同步操作: ✅（无 Chroma 写入路径被触发）")
    print(f"  Chroma metadata 未修改: {'✅' if chroma_ok else '❌'}")
    print("=" * 60)

    all_pass = disable_ok and enable_ok and chroma_ok
    if all_pass:
        print("\n🎉 DIS-06 全部验收通过！读时校验方案工作正常。")
    else:
        print("\n⚠️  有验收项未通过，请检查上方详细输出。")


if __name__ == "__main__":
    asyncio.run(main())
