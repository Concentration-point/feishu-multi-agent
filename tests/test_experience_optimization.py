from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from config import FIELD_MAP_EXPERIENCE as FE
from memory import experience as exp_mod
from memory.experience import ExperienceManager
from tools.write_wiki import WIKI_WRITE_SUBDIR, sanitize_name


@pytest.fixture
def local_tmp_dir():
    base = Path.cwd() / "pytest-tmp" / f"experience_optimization_{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


class FakeBitableClient:
    def __init__(self, records: list[dict] | None = None):
        self.records = records or []
        self.deleted: list[str] = []
        self.created: list[dict] = []

    async def list_records(self, table_id: str, filter_expr: str | None = None):
        return list(self.records)

    async def delete_record(self, table_id: str, record_id: str) -> None:
        self.deleted.append(record_id)
        self.records = [r for r in self.records if r["record_id"] != record_id]

    async def create_record(self, table_id: str, fields: dict) -> str:
        record_id = f"rec_new_{len(self.created) + 1}"
        record = {"record_id": record_id, "fields": dict(fields)}
        self.created.append(record)
        self.records.append(record)
        return record_id


def make_record(record_id: str, lesson: str, confidence: float, title: str | None = None) -> dict:
    payload = {
        "situation": "测试场景足够长",
        "action": "测试行动足够长",
        "outcome": "测试结果",
        "lesson": lesson,
        "title": title or f"电商大促 - copywriter - {lesson[:18]}",
    }
    return {
        "record_id": record_id,
        "fields": {
            FE["role"]: "copywriter",
            FE["scene"]: "电商大促",
            FE["content"]: json.dumps(payload, ensure_ascii=False),
            FE["confidence"]: confidence,
            FE["use_count"]: 0,
        },
    }


@pytest.mark.asyncio
async def test_optimize_bucket_deduplicates_and_deletes_local_wiki(local_tmp_dir, monkeypatch):
    monkeypatch.setattr(exp_mod, "KNOWLEDGE_BASE_PATH", str(local_tmp_dir))
    low = make_record(
        "rec_low",
        "小红书探店文案先写门店场景再写产品卖点，避免只堆形容词",
        0.72,
    )
    high = make_record(
        "rec_high",
        "小红书探店文案先写门店场景再写产品卖点，避免只堆形容词",
        0.91,
    )
    client = FakeBitableClient([low, high])
    em = ExperienceManager(client=client)
    em._table_id = "tbl_test"

    payload = json.loads(low["fields"][FE["content"]])
    category_dir = local_tmp_dir / WIKI_WRITE_SUBDIR / sanitize_name("电商大促")
    category_dir.mkdir(parents=True)
    wiki_file = category_dir / f"{sanitize_name(payload['title'][:48], 48)}.md"
    wiki_file.write_text(
        "角色：copywriter\n"
        "小红书探店文案先写门店场景再写产品卖点，避免只堆形容词\n",
        encoding="utf-8",
    )

    summary = await em.optimize_bucket("copywriter", "电商大促", "测试项目")

    assert summary["dedup_deleted"] == 1
    assert client.deleted == ["rec_low"]
    assert [r["record_id"] for r in client.records] == ["rec_high"]
    assert not wiki_file.exists()


@pytest.mark.asyncio
async def test_optimize_bucket_merges_bucket_and_resets_use_count(local_tmp_dir, monkeypatch):
    monkeypatch.setattr(exp_mod, "KNOWLEDGE_BASE_PATH", str(local_tmp_dir))
    lessons = [
        "需求澄清阶段先列目标人群、卖点和禁用词，避免后续反复返工",
        "脚本产出前先拆开开头钩子、证明材料和行动指令，保证结构可检查",
        "审核反馈要按严重程度排序，先处理事实错误再处理语气优化",
        "交付前统一核对平台、标题、发布时间和字数，避免漏填关键字段",
    ]
    records = [
        make_record(f"rec{i}", lesson, 0.7 + i * 0.03)
        for i, lesson in enumerate(lessons)
    ]
    client = FakeBitableClient(records)
    em = ExperienceManager(client=client)
    em._table_id = "tbl_test"
    em._merge_bucket_records = AsyncMock(return_value=[{
        "situation": "合并场景足够长可复用",
        "action": "合并行动足够长可以执行",
        "outcome": "合并结果",
        "lesson": "先确认需求，再输出可执行清单，并补齐关键检查项",
        "category": "电商大促",
        "applicable_roles": ["copywriter"],
        "_merged_confidence": 0.93,
    }])

    summary = await em.optimize_bucket("copywriter", "电商大促", "测试项目")

    assert summary["merged_deleted"] == 4
    assert summary["merged_created"] == 1
    assert len(client.records) == 1
    fields = client.records[0]["fields"]
    assert fields[FE["confidence"]] == 0.93
    assert fields[FE["use_count"]] == 0
    assert (local_tmp_dir / WIKI_WRITE_SUBDIR / sanitize_name("电商大促")).exists()
