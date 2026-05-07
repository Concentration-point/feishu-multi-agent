"""Report doc generation tests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


def test_project_status_chart_returns_png():
    from feishu.report_charts import generate_project_status_chart

    data = {"待处理": 2, "策略中": 3, "已完成": 5, "审核中": 1}
    result = generate_project_status_chart(data)
    assert isinstance(result, bytes)
    assert len(result) > 100
    assert result[:4] == b"\x89PNG"


def test_project_status_chart_empty():
    from feishu.report_charts import generate_project_status_chart

    assert generate_project_status_chart({}) == b""


def test_platform_pass_rate_chart_returns_png():
    from feishu.report_charts import generate_platform_pass_rate_chart

    data = {"小红书": 0.75, "公众号": 0.90, "抖音": 0.60}
    result = generate_platform_pass_rate_chart(data)
    assert isinstance(result, bytes)
    assert len(result) > 100
    assert result[:4] == b"\x89PNG"


def test_platform_pass_rate_chart_empty():
    from feishu.report_charts import generate_platform_pass_rate_chart

    assert generate_platform_pass_rate_chart({}) == b""


def test_generate_report_doc_schema():
    from tools.generate_report_doc import SCHEMA

    assert SCHEMA["type"] == "function"
    fn = SCHEMA["function"]
    assert fn["name"] == "generate_report_doc"
    assert "parameters" in fn
    required = fn["parameters"]["required"]
    assert "title" in required
    assert "summary" in required
    assert "recommendations" in required


def test_tool_registry_discovers_generate_report_doc():
    from tools import ToolRegistry

    registry = ToolRegistry()
    assert "generate_report_doc" in registry.tool_names


def test_compute_platform_pass_rates():
    from tools.generate_report_doc import _compute_platform_pass_rates

    content_data = {
        "platform_review_detail": {
            "小红书": {"通过": 3, "需修改": 1, "未审核": 2},
            "公众号": {"通过": 5, "未审核": 1},
        }
    }
    rates = _compute_platform_pass_rates(content_data)
    assert abs(rates["小红书"] - 0.75) < 0.01
    assert abs(rates["公众号"] - 1.0) < 0.01


def test_compute_platform_pass_rates_empty():
    from tools.generate_report_doc import _compute_platform_pass_rates

    assert _compute_platform_pass_rates({}) == {}


@pytest.mark.asyncio
async def test_build_blocks_structure():
    from tools.generate_report_doc import _build_blocks

    stats = {
        "projects": {
            "total": 10,
            "completion_rate": 0.6,
            "by_status": {"待处理": 2, "已完成": 6, "审核中": 2},
            "by_type": {"电商大促": 5, "品牌传播": 5},
            "avg_review_pass_rate": 0.75,
            "avg_review_pass_rate_by_type": {"电商大促": 0.8, "品牌传播": 0.7},
        },
        "content": {
            "total": 20,
            "draft_rate": 0.8,
            "by_platform": {"小红书": 10, "公众号": 10},
            "by_review_status": {"通过": 15, "需修改": 3, "未审核": 2},
            "platform_review_detail": {
                "小红书": {"通过": 7, "需修改": 2},
                "公众号": {"通过": 8, "需修改": 1},
            },
            "word_count_stats": {"avg_words": 500, "min_words": 200, "max_words": 1000},
        },
        "experience": {
            "total": 15,
            "by_role": {"策略师": 5, "文案": 10},
            "confidence_stats": {"avg": 0.8, "min": 0.6, "max": 0.95},
        },
    }

    blocks = await _build_blocks("weekly", "测试周报", "这是测试摘要", ["建议1", "建议2"], stats)
    types = [b["type"] for b in blocks]
    assert "heading1" in types
    assert "callout" in types
    assert "heading2" in types
    assert "table" in types
    assert "bullet" in types
    assert "divider" in types
    assert blocks[0]["type"] == "heading1"
    assert blocks[0]["text"] == "测试周报"
    bullet_texts = [b["text"] for b in blocks if b["type"] == "bullet"]
    assert "建议1" in bullet_texts
    assert "建议2" in bullet_texts


def test_soul_md_includes_generate_report_doc():
    soul_path = Path(__file__).parent.parent / "agents" / "data_analyst" / "soul.md"
    text = soul_path.read_text(encoding="utf-8")
    assert "generate_report_doc" in text


def _make_wiki_mock(parent_node_found: bool, report_node_found: bool) -> AsyncMock:
    mock = AsyncMock()
    mock.list_nodes.return_value = [
        {"node_token": "child_tok", "parent_node_token": "space_root_tok", "title": "01_企业底座"}
    ]

    parent_node = {
        "node_token": "parent_node_tok",
        "obj_token": "parent_obj_tok",
        "title": "数据分析报告",
    }
    report_node = {
        "node_token": "report_node_tok",
        "obj_token": "report_obj_tok",
        "title": "测试周报",
    }

    async def _find_node_by_title(_space_id, title, _parent_token=None):
        if title == "数据分析报告":
            return parent_node if parent_node_found else None
        if title == "测试周报":
            return report_node if report_node_found else None
        return None

    mock.find_node_by_title.side_effect = _find_node_by_title
    mock.create_node.return_value = {"node_token": "new_tok", "obj_token": "new_obj_tok"}
    mock.wait_for_new_doc_ready = AsyncMock()
    mock.write_delivery_doc = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_execute_reuses_existing_parent_node():
    from tools.generate_report_doc import execute
    from tools import AgentContext

    mock_wiki = _make_wiki_mock(parent_node_found=True, report_node_found=False)
    ctx = AgentContext(record_id="__test__", project_name="", role_id="data_analyst")

    with patch("tools.generate_report_doc.WIKI_SPACE_ID", "space_001"), \
         patch("tools.generate_report_doc._fetch_stats", AsyncMock(return_value={})), \
         patch("tools.generate_report_doc._build_blocks", AsyncMock(return_value=[])), \
         patch("feishu.wiki.FeishuWikiClient", return_value=mock_wiki):
        result = await execute(
            {"title": "测试周报", "summary": "摘要", "recommendations": ["建议1"]},
            ctx,
        )

    assert mock_wiki.create_node.call_count == 1
    call_args = mock_wiki.create_node.call_args
    assert call_args.args[1] == "parent_node_tok"
    assert call_args.args[2] == "测试周报"
    mock_wiki.wait_for_new_doc_ready.assert_awaited_once_with("new_obj_tok")
    assert "报告文档已生成" in result


@pytest.mark.asyncio
async def test_execute_creates_parent_node_when_missing():
    from tools.generate_report_doc import execute
    from tools import AgentContext

    mock_wiki = _make_wiki_mock(parent_node_found=False, report_node_found=False)
    ctx = AgentContext(record_id="__test__", project_name="", role_id="data_analyst")

    with patch("tools.generate_report_doc.WIKI_SPACE_ID", "space_001"), \
         patch("tools.generate_report_doc._fetch_stats", AsyncMock(return_value={})), \
         patch("tools.generate_report_doc._build_blocks", AsyncMock(return_value=[])), \
         patch("feishu.wiki.FeishuWikiClient", return_value=mock_wiki):
        result = await execute(
            {"title": "测试周报", "summary": "摘要", "recommendations": ["建议1"]},
            ctx,
        )

    assert mock_wiki.create_node.call_count == 2
    first_call = mock_wiki.create_node.call_args_list[0]
    assert first_call.args[1] == "space_root_tok"
    assert first_call.args[2] == "数据分析报告"
    mock_wiki.wait_for_new_doc_ready.assert_awaited_once_with("new_obj_tok")
    assert "报告文档已生成" in result


@pytest.mark.asyncio
async def test_execute_uses_space_root_token_for_parent_search():
    from tools.generate_report_doc import execute
    from tools import AgentContext

    mock_wiki = _make_wiki_mock(parent_node_found=True, report_node_found=True)
    ctx = AgentContext(record_id="__test__", project_name="", role_id="data_analyst")

    with patch("tools.generate_report_doc.WIKI_SPACE_ID", "space_001"), \
         patch("tools.generate_report_doc._fetch_stats", AsyncMock(return_value={})), \
         patch("tools.generate_report_doc._build_blocks", AsyncMock(return_value=[])), \
         patch("feishu.wiki.FeishuWikiClient", return_value=mock_wiki):
        await execute(
            {"title": "测试周报", "summary": "摘要", "recommendations": []},
            ctx,
        )

    first_find_call = mock_wiki.find_node_by_title.call_args_list[0]
    assert first_find_call.args[2] == "space_root_tok"
    mock_wiki.wait_for_new_doc_ready.assert_not_awaited()
