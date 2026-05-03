"""EXP-10 端到端验证：Chroma 语义检索 + 去重 + 质量检查 + 完整流水线。"""

import pytest

# ── 全局 fixture：每个测试用独立 Chroma 目录 ──

@pytest.fixture(autouse=True)
def chroma_env(monkeypatch, tmp_path):
    import config
    chroma_path = str(tmp_path / "chroma")
    # 同时 patch env 和 config 模块级变量，保证动态实例化也走 tmp 目录
    monkeypatch.setenv("CHROMA_DB_PATH", chroma_path)
    monkeypatch.setattr(config, "CHROMA_DB_PATH", chroma_path)
    monkeypatch.setenv("FEISHU_APP_ID", "test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "test")
    monkeypatch.setenv("BITABLE_APP_TOKEN", "test")
    monkeypatch.setenv("EXPERIENCE_TABLE_ID", "")
    yield chroma_path


def _get_store(chroma_path: str | None = None):
    from memory.experience_store import ExperienceVectorStore
    import config
    return ExperienceVectorStore(path=chroma_path or config.CHROMA_DB_PATH)


def _seed_five_categories(store):
    """写入五品类基准经验，全部用同一 role_id 方便对比。"""
    entries = [
        ("beauty",    "beauty serum xiaohongshu post must highlight ingredient efficacy and skin texture"),
        ("food",      "bbq restaurant tiktok video must show live grilling scene and smoky atmosphere"),
        ("maternal",  "infant formula wechat article must emphasize formula safety and baby growth"),
        ("education", "education institution xiaohongshu must highlight admission rate and star teachers"),
        ("home",      "home renovation tiktok must show dramatic before-after space transformation"),
    ]
    for cat, doc in entries:
        store.add(
            f"seed-{cat}",
            doc,
            {"role_id": "copywriter", "category": cat, "confidence": 0.85,
             "use_count": 0, "source_project": "seed"},
        )


# ── 用例 1：烧烤店抖音种草 → 餐饮经验排在美妆前面 ──

@pytest.mark.asyncio
async def test_food_query_ranks_food_before_beauty():
    store = _get_store()
    _seed_five_categories(store)

    results = store.query(
        "bbq restaurant tiktok short video strategy",
        role_id="copywriter",
        k=5,
    )
    categories = [r["metadata"]["category"] for r in results]
    assert "food" in categories, "food 经验应在结果中"
    food_idx = categories.index("food")
    beauty_idx = categories.index("beauty") if "beauty" in categories else len(categories)
    assert food_idx < beauty_idx, (
        f"food ({food_idx}) 应排在 beauty ({beauty_idx}) 前面，实际顺序: {categories}"
    )


# ── 用例 2：美妆精华液小红书 → 美妆经验排在餐饮前面 ──

@pytest.mark.asyncio
async def test_beauty_query_ranks_beauty_before_food():
    store = _get_store()
    _seed_five_categories(store)

    results = store.query(
        "beauty serum xiaohongshu content strategy",
        role_id="copywriter",
        k=5,
    )
    categories = [r["metadata"]["category"] for r in results]
    assert "beauty" in categories, "beauty 经验应在结果中"
    beauty_idx = categories.index("beauty")
    food_idx = categories.index("food") if "food" in categories else len(categories)
    assert beauty_idx < food_idx, (
        f"beauty ({beauty_idx}) 应排在 food ({food_idx}) 前面，实际顺序: {categories}"
    )


# ── 用例 3：高相似低 confidence 经验被跳过入库 ──

@pytest.mark.asyncio
async def test_dedup_skips_low_confidence_similar():
    from memory.experience import ExperienceManager

    store = _get_store()
    mgr = ExperienceManager()

    base_card = {
        "applicable_roles": ["copywriter"],
        "category": "beauty",
        "situation": "为美妆品牌在小红书撰写种草文案",
        "action": "以第一人称场景描述作为开头",
        "outcome": "互动率明显提升",
        "lesson": "小红书帖子开头必须用第一人称场景描述，这样能迅速建立情感连接并提升用户互动率",
        "title": "小红书开头技巧",
    }
    # 先写高置信度经验
    await mgr.save_experience(base_card, confidence=0.90, project_name="proj-A")

    # 写高度相似但置信度更低的经验 → 应被跳过（sim=0.994 > 0.85）
    similar_low = dict(base_card,
        lesson="小红书帖子开头必须采用第一人称场景描述，这样可以迅速建立情感连接")
    await mgr.save_experience(similar_low, confidence=0.70, project_name="proj-B")

    results = store.query(
        "小红书开头第一人称场景",
        role_id="copywriter",
        k=5,
    )
    assert len(results) == 1, (
        f"高相似低 conf 经验应被跳过，期望 1 条，实际 {len(results)} 条"
    )
    assert abs(results[0]["metadata"]["confidence"] - 0.90) < 0.01, (
        f"留存经验置信度应为 0.90，实际 {results[0]['metadata']['confidence']}"
    )


# ── 用例 4：废话 lesson 被质量检查拦截 ──

@pytest.mark.asyncio
async def test_quality_check_rejects_vague_lesson():
    from memory.experience import ExperienceManager, _is_lesson_quality_ok

    # 直接测函数：无可操作词且字数不足
    c1 = {"lesson": "注意品牌调性", "situation": "品牌内容创作"}
    ok, reason = _is_lesson_quality_ok(c1)
    assert not ok, f"应被拒绝，实际 ok={ok}"

    # 通过 save_experience 路径：废话 lesson 不写入 Chroma
    mgr = ExperienceManager()
    store = _get_store()

    bad_card = {
        "applicable_roles": ["copywriter"],
        "category": "beauty",
        "situation": "writing copy",
        "action": "pay attention",
        "outcome": "ok",
        "lesson": "注意品牌调性",  # 字数不足且无可操作词
        "title": "bad lesson",
    }
    result = await mgr.save_experience(bad_card, confidence=0.85, project_name="proj-bad")
    assert result is None, "废话经验 save_experience 应返回 None"

    items = store.query("brand tone", role_id="copywriter", k=5)
    assert len(items) == 0, f"废话经验不应写入 Chroma，实际有 {len(items)} 条"


# ── 用例 5：完整流水线 — 经验沉淀到 Chroma，下次运行能检索到 ──

@pytest.mark.asyncio
async def test_full_pipeline_save_and_retrieve(tmp_path):
    from memory.experience import ExperienceManager

    # 第一轮：写入经验
    mgr1 = ExperienceManager()
    card = {
        "applicable_roles": ["copywriter"],
        "category": "food",
        "situation": "为餐饮品牌制作抖音种草短视频文案",
        "action": "开头3秒展示现场烤制画面",
        "outcome": "完播率提升25%",
        "lesson": "抖音餐饮视频必须在前3秒用现场烤制特写镜头勾起食欲，避免直接展示价格信息",
        "title": "抖音餐饮开场钩子",
    }
    await mgr1.save_experience(card, confidence=0.88, project_name="restaurant-campaign")

    # 第二轮：新实例查询（模拟下次运行，path 与第一轮相同）
    from memory.experience_store import ExperienceVectorStore
    import config
    store2 = ExperienceVectorStore(path=config.CHROMA_DB_PATH)

    results = store2.query("抖音餐饮视频开场策略", role_id="copywriter", k=5)
    assert len(results) >= 1, "经验应持久化，下次运行能检索到"

    meta = results[0]["metadata"]
    assert meta["role_id"] == "copywriter"
    assert meta["category"] == "food"
    assert abs(meta["confidence"] - 0.88) < 0.01
    assert meta["source_project"] == "restaurant-campaign"

    # 通过 query_top_k 路径也能检索到
    mgr2 = ExperienceManager()
    top_k = await mgr2.query_top_k("copywriter", task_brief="抖音餐饮视频开场钩子")
    assert len(top_k) >= 1, "query_top_k 也应能检索到沉淀的经验"
    assert top_k[0].get("category") == "food"
