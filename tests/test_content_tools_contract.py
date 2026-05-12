from __future__ import annotations

import json

import pytest

from tools import AgentContext
from tools.batch_create_content import execute as batch_create_content_execute


class ExistingContent:
    def __init__(self, title: str):
        self.title = title


class FakeContentMemory:
    created_items = []

    async def list_by_project(self, project_name: str):
        return [ExistingContent("已有标题")]

    async def batch_create_content_items(self, project_name: str, content_items):
        self.__class__.created_items = list(content_items)
        return [f"rec_{i}" for i, _ in enumerate(content_items, 1)]


@pytest.mark.asyncio
async def test_batch_create_content_dedupes_and_accepts_legacy_aliases(monkeypatch):
    import tools.batch_create_content as mod

    FakeContentMemory.created_items = []
    monkeypatch.setattr(mod, "ContentMemory", FakeContentMemory)

    ctx = AgentContext(record_id="rec", project_name="项目A", role_id="strategist")
    result = await batch_create_content_execute(
        {
            "contents": [
                {
                    "seq": 1,
                    "title": "已有标题",
                    "platform": "小红书",
                    "content_type": "种草笔记",
                    "key_point": "门店烟火气",
                    "target_audience": "周边年轻人",
                },
                {
                    "seq": 2,
                    "title": "夜宵开场",
                    "platform": "小红书笔记",
                    "content_type": "种草笔记",
                    "key_point": "深夜聚餐场景",
                    "target_audience": "下班聚餐人群",
                },
                {
                    "seq": 3,
                    "title": "夜宵开场",
                    "platform": "抖音",
                    "content_type": "口播脚本",
                    "key_point": "重复标题",
                    "target_audience": "同城用户",
                },
                {
                    "seq": 4,
                    "title": "公众号铺垫",
                    "platform": "公众号",
                    "content_type": "深度长文",
                    "key_point": "不应落表",
                    "target_audience": "老客",
                },
            ]
        },
        ctx,
    )

    payload = json.loads(result)
    assert payload["record_ids"] == ["rec_1"]
    assert payload["skipped_count"] == 3
    assert len(FakeContentMemory.created_items) == 1
    created = FakeContentMemory.created_items[0]
    assert created.seq == 2
    assert created.title == "夜宵开场"
    assert created.platform == "小红书"
    assert created.key_point == "深夜聚餐场景"


@pytest.mark.asyncio
async def test_batch_create_content_all_invalid_returns_structured_skip(monkeypatch):
    import tools.batch_create_content as mod

    FakeContentMemory.created_items = []
    monkeypatch.setattr(mod, "ContentMemory", FakeContentMemory)

    ctx = AgentContext(record_id="rec", project_name="项目A", role_id="strategist")
    result = await batch_create_content_execute(
        {
            "items": [
                {
                    "sequence": 1,
                    "title": "微博预热",
                    "platform": "微博",
                    "content_type": "话题文案",
                    "key_message": "不落表",
                    "target_audience": "泛人群",
                }
            ]
        },
        ctx,
    )

    payload = json.loads(result)
    assert payload["record_ids"] == []
    assert payload["skipped_count"] == 1
    assert "platform" in payload["skipped"][0]["reason"]
    assert FakeContentMemory.created_items == []
