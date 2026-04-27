"""报告文档生成工具 + 分析图表 单元测试。

测试覆盖:
  - report_charts 图表函数不报错 + 返回有效 PNG
  - generate_report_doc schema 校验
  - ToolRegistry 发现新工具
  - _build_blocks 文档结构正确性
  - _compute_platform_pass_rates 通过率计算
  - soul.md 包含 generate_report_doc

使用方式:
    pytest tests/test_report_doc.py -v
"""

import json
import pytest
from pathlib import Path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  图表测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_project_status_chart_returns_png():
    """项目状态分布图表返回有效 PNG bytes。"""
    from feishu.report_charts import generate_project_status_chart

    data = {"待处理": 2, "策略中": 3, "已完成": 5, "审核中": 1}
    result = generate_project_status_chart(data)
    assert isinstance(result, bytes)
    assert len(result) > 100
    assert result[:4] == b"\x89PNG"


def test_project_status_chart_empty():
    """空数据返回空 bytes。"""
    from feishu.report_charts import generate_project_status_chart

    assert generate_project_status_chart({}) == b""


def test_platform_pass_rate_chart_returns_png():
    """平台通过率图表返回有效 PNG bytes。"""
    from feishu.report_charts import generate_platform_pass_rate_chart

    data = {"小红书": 0.75, "公众号": 0.90, "抖音": 0.60}
    result = generate_platform_pass_rate_chart(data)
    assert isinstance(result, bytes)
    assert len(result) > 100
    assert result[:4] == b"\x89PNG"


def test_platform_pass_rate_chart_empty():
    """空数据返回空 bytes。"""
    from feishu.report_charts import generate_platform_pass_rate_chart

    assert generate_platform_pass_rate_chart({}) == b""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  generate_report_doc 工具测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_generate_report_doc_schema():
    """generate_report_doc schema 符合 OpenAI function calling 格式。"""
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
    """ToolRegistry 能扫描到 generate_report_doc。"""
    from tools import ToolRegistry

    registry = ToolRegistry()
    assert "generate_report_doc" in registry.tool_names


def test_compute_platform_pass_rates():
    """_compute_platform_pass_rates 从 review detail 正确计算通过率。"""
    from tools.generate_report_doc import _compute_platform_pass_rates

    content_data = {
        "platform_review_detail": {
            "小红书": {"通过": 3, "需修改": 1, "未审核": 2},
            "公众号": {"通过": 5, "未审核": 1},
        }
    }
    rates = _compute_platform_pass_rates(content_data)
    assert abs(rates["小红书"] - 0.75) < 0.01  # 3 / (3+1) = 0.75
    assert abs(rates["公众号"] - 1.0) < 0.01   # 5 / 5 = 1.0


def test_compute_platform_pass_rates_empty():
    """空数据返回空 dict。"""
    from tools.generate_report_doc import _compute_platform_pass_rates

    assert _compute_platform_pass_rates({}) == {}


def test_build_blocks_structure():
    """_build_blocks 返回的块列表包含关键结构。"""
    from tools.generate_report_doc import _build_blocks

    stats = {
        "projects": {
            "total": 10, "completion_rate": 0.6,
            "by_status": {"待处理": 2, "已完成": 6, "审核中": 2},
            "by_type": {"电商大促": 5, "品牌传播": 5},
            "avg_review_pass_rate": 0.75,
            "avg_review_pass_rate_by_type": {"电商大促": 0.8, "品牌传播": 0.7},
        },
        "content": {
            "total": 20, "draft_rate": 0.8,
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
    blocks = _build_blocks("weekly", "测试周报", "这是测试摘要", ["建议1", "建议2"], stats)

    # 基本结构校验
    types = [b["type"] for b in blocks]
    assert "heading1" in types
    assert "callout" in types
    assert "heading2" in types
    assert "table" in types
    assert "bullet" in types
    assert "divider" in types

    # 标题正确
    assert blocks[0]["type"] == "heading1"
    assert blocks[0]["text"] == "测试周报"

    # 建议被包含
    bullet_texts = [b["text"] for b in blocks if b["type"] == "bullet"]
    assert "建议1" in bullet_texts
    assert "建议2" in bullet_texts


def test_soul_md_includes_generate_report_doc():
    """soul.md 工具列表包含 generate_report_doc。"""
    soul_path = Path(__file__).parent.parent / "agents" / "data_analyst" / "soul.md"
    text = soul_path.read_text(encoding="utf-8")
    assert "generate_report_doc" in text
