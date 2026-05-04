"""Plan-Verify 机制单元测试 — `_generate_plan` + `_verify_plan`。

覆盖路径:
  1. verify_config 为 None → plan 为空，verify 返回空 gaps
  2. content 模式 + 3 条全部有 draft → gaps 为空
  3. content 模式 + 3 条其中 1 条 draft 为空 → gaps 包含该条
  4. project 模式 + strategy 非空 → gaps 为空
  5. project 模式 + strategy 为空 → gaps 包含该字段
  6. project 模式 + min_content_rows=3 但只有 1 行 → gaps 包含行数不足

字段名注：实际落地用 `ContentRecord.draft` / `BriefProject.strategy` 这些 dataclass
属性名（任务文本里的 `draft_content` 在代码层并不存在；详见 PV-08 偏离记录）。

可独立跑：
    pytest tests/test_plan_verify.py
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent  # noqa: E402
from memory.project import BriefProject, ContentRecord  # noqa: E402


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  辅助：构造一个绕过 __init__ 的 BaseAgent 实例
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _make_agent(verify_config, *, project_factory=None, record_id="rec_test"):
    """跳过 __init__，只挂上 _verify_plan / _generate_plan 需要的字段。

    单测不走真实 LLM / 飞书凭证。
    """
    a = BaseAgent.__new__(BaseAgent)
    a.role_id = "test_role"
    a.record_id = record_id
    a._verify_config = verify_config
    a._project_memory_factory = project_factory
    return a


def _content_records_all_filled():
    """3 条内容行，全部填齐 draft + word_count。"""
    return [
        ContentRecord(
            record_id=f"rec_c00{i}", project_name="proj_x",
            title=f"标题{i}", platform="小红书",
            draft=f"成稿正文 {i}" * 20, word_count=400 + i,
        )
        for i in range(1, 4)
    ]


def _content_records_one_missing():
    """3 条内容行，第 2 条 draft 为空白（strip 后空）。"""
    return [
        ContentRecord(record_id="rec_c001", project_name="proj_x", title="标题1",
                      platform="小红书", draft="成稿1", word_count=500),
        ContentRecord(record_id="rec_c002", project_name="proj_x", title="标题2",
                      platform="小红书", draft="   ", word_count=0),
        ContentRecord(record_id="rec_c003", project_name="proj_x", title="标题3",
                      platform="小红书", draft="成稿3", word_count=600),
    ]


def _project_factory(proj: BriefProject):
    """返回一个能让 await pm.load() 拿到指定 BriefProject 的 factory。"""

    def _factory(rid):
        pm = MagicMock()
        pm.load = AsyncMock(return_value=proj)
        return pm

    return _factory


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Test 1: verify_config 为 None
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_verify_config_none_returns_empty():
    """verify_config 为 None → plan 与 verify 都返回空。"""
    agent = _make_agent(None)
    plan = await agent._generate_plan("proj_x")
    assert plan == [], "verify_config=None 时 plan 必须为空"
    gaps = await agent._verify_plan(plan, "proj_x")
    assert gaps == [], "verify_config=None 时 verify 必须返回空 gaps"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Test 2: content 模式 全部填齐
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_content_all_filled_no_gaps():
    """content 模式 + 3 条全部有 draft + word_count → gaps 为空。"""
    agent = _make_agent({
        "table": "content",
        "check_fields": ["draft", "word_count"],
    })
    records = _content_records_all_filled()

    with patch("agents.base.ContentMemory") as MockCM:
        MockCM.return_value.list_by_project = AsyncMock(return_value=records)
        plan = await agent._generate_plan("proj_x")
        assert len(plan) == 3, "plan 条目数应等于内容行数"
        gaps = await agent._verify_plan(plan, "proj_x")

    assert gaps == [], f"全部填齐时不应有 gap，实际 {gaps}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Test 3: content 模式 一条 draft 为空
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_content_one_missing_appears_in_gaps():
    """content 模式 + 1 条 draft 为空 → gaps 含该条 record_id。"""
    agent = _make_agent({
        "table": "content",
        "check_fields": ["draft", "word_count"],
    })
    records = _content_records_one_missing()

    with patch("agents.base.ContentMemory") as MockCM:
        MockCM.return_value.list_by_project = AsyncMock(return_value=records)
        plan = await agent._generate_plan("proj_x")
        gaps = await agent._verify_plan(plan, "proj_x")

    # rec_c002 的 draft 与 word_count 各产出 1 条 gap
    target_gaps = [g for g in gaps if g["record_id"] == "rec_c002"]
    assert len(target_gaps) == 2, f"rec_c002 应有 draft + word_count 2 条 gap，实际 {target_gaps}"
    fields = {g["field"] for g in target_gaps}
    assert fields == {"draft", "word_count"}
    # 其它两条不应该出现在 gap 中
    other_ids = {g["record_id"] for g in gaps} - {"rec_c002"}
    assert other_ids == set(), f"已填齐的内容行不应进 gap，实际 {other_ids}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Test 4: project 模式 strategy 非空
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_project_strategy_filled_no_gaps():
    """project 模式 + strategy 非空 → gaps 为空。"""
    proj = BriefProject(
        record_id="rec_proj_x", client_name="客户A",
        strategy="本季度策略：聚焦小红书种草 + 抖音引流",
    )
    agent = _make_agent(
        {"table": "project", "check_fields": ["strategy"]},
        project_factory=_project_factory(proj),
        record_id="rec_proj_x",
    )
    plan = await agent._generate_plan("proj_x")
    gaps = await agent._verify_plan(plan, "proj_x")
    assert gaps == [], f"strategy 非空时不应有 gap，实际 {gaps}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Test 5: project 模式 strategy 为空
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_project_strategy_empty_appears_in_gaps():
    """project 模式 + strategy 为空 → gaps 包含 strategy 字段。"""
    proj = BriefProject(record_id="rec_proj_x", client_name="客户A", strategy="")
    agent = _make_agent(
        {"table": "project", "check_fields": ["strategy"]},
        project_factory=_project_factory(proj),
        record_id="rec_proj_x",
    )
    plan = await agent._generate_plan("proj_x")
    gaps = await agent._verify_plan(plan, "proj_x")

    assert len(gaps) == 1
    assert gaps[0]["scope"] == "project"
    assert gaps[0]["field"] == "strategy"
    assert gaps[0]["reason"] == "字段为空"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Test 6: project 模式 + min_content_rows 不足
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_project_min_content_rows_insufficient():
    """project 模式 + min_content_rows=3 但只有 1 行 → gaps 含行数不足条目。"""
    proj = BriefProject(
        record_id="rec_proj_x", client_name="客户A", strategy="已写策略",
    )
    agent = _make_agent(
        {
            "table": "project",
            "check_fields": ["strategy"],
            "min_content_rows": 3,
        },
        project_factory=_project_factory(proj),
        record_id="rec_proj_x",
    )

    only_one_row = [
        ContentRecord(record_id="rec_c001", project_name="proj_x",
                      title="标题1", platform="小红书", draft="成稿1", word_count=500),
    ]
    with patch("agents.base.ContentMemory") as MockCM:
        MockCM.return_value.list_by_project = AsyncMock(return_value=only_one_row)
        plan = await agent._generate_plan("proj_x")
        gaps = await agent._verify_plan(plan, "proj_x")

    assert len(gaps) == 1, f"strategy 已写 → 仅行数不足触发 1 条 gap，实际 {gaps}"
    g = gaps[0]
    assert g["scope"] == "content_rows_count"
    assert "实际 1 行" in g["reason"]
    assert "至少 3 行" in g["reason"]
