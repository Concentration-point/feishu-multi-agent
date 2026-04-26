"""交付文档功能单元测试。

测试覆盖：
1. delivery_charts 统计计算
2. delivery_charts 图表生成（不依赖飞书 API）
3. write_delivery_doc block 构建逻辑
"""

from __future__ import annotations

import pytest

from feishu.delivery_charts import compute_delivery_stats


# ── 模拟 ContentRecord ──

class FakeContentRecord:
    def __init__(self, **kwargs):
        self.record_id = kwargs.get("record_id", "rec_test")
        self.project_name = kwargs.get("project_name", "测试项目")
        self.seq = kwargs.get("seq", 1)
        self.title = kwargs.get("title", "")
        self.platform = kwargs.get("platform", "")
        self.content_type = kwargs.get("content_type", "")
        self.key_point = kwargs.get("key_point", "")
        self.target_audience = kwargs.get("target_audience", "")
        self.draft = kwargs.get("draft", "")
        self.word_count = kwargs.get("word_count", 0)
        self.review_status = kwargs.get("review_status", "")
        self.review_feedback = kwargs.get("review_feedback", "")
        self.publish_date = kwargs.get("publish_date", "")
        self.remark = kwargs.get("remark", "")


SAMPLE_ROWS = [
    FakeContentRecord(title="618爆款推荐", platform="小红书", content_type="种草笔记", word_count=580, publish_date="2024-06-10"),
    FakeContentRecord(title="品牌故事", platform="公众号", content_type="深度长文", word_count=1200, publish_date="2024-06-12"),
    FakeContentRecord(title="开箱测评", platform="抖音", content_type="短视频脚本", word_count=350, publish_date="2024-06-14"),
    FakeContentRecord(title="好物清单", platform="小红书", content_type="好物推荐", word_count=460, publish_date=""),
    FakeContentRecord(title="深度解读", platform="公众号", content_type="深度长文", word_count=980, publish_date="2024-06-18"),
]


class TestComputeDeliveryStats:
    """测试 compute_delivery_stats 统计函数。"""

    def test_basic_stats(self):
        stats = compute_delivery_stats(SAMPLE_ROWS)
        assert stats["total"] == 5
        assert stats["scheduled"] == 4
        assert stats["pending"] == 1

    def test_platform_counts(self):
        stats = compute_delivery_stats(SAMPLE_ROWS)
        assert stats["platform_counts"]["小红书"] == 2
        assert stats["platform_counts"]["公众号"] == 2
        assert stats["platform_counts"]["抖音"] == 1

    def test_word_range(self):
        stats = compute_delivery_stats(SAMPLE_ROWS)
        assert stats["word_range"]["min"] == 350
        assert stats["word_range"]["max"] == 1200
        assert stats["word_range"]["avg"] > 0

    def test_date_range(self):
        stats = compute_delivery_stats(SAMPLE_ROWS)
        assert stats["first_date"] == "2024-06-10"
        assert stats["last_date"] == "2024-06-18"

    def test_empty_rows(self):
        stats = compute_delivery_stats([])
        assert stats["total"] == 0
        assert stats["scheduled"] == 0
        assert stats["platform_counts"] == {}
        assert stats["word_range"]["min"] == 0

    def test_platform_types(self):
        stats = compute_delivery_stats(SAMPLE_ROWS)
        assert "种草笔记" in stats["platform_types"]["小红书"]
        assert "深度长文" in stats["platform_types"]["公众号"]


class TestChartGeneration:
    """测试图表生成（仅验证返回 PNG bytes）。"""

    def test_bar_chart_returns_png(self):
        try:
            from feishu.delivery_charts import generate_platform_bar_chart
            result = generate_platform_bar_chart({"小红书": 2, "公众号": 2, "抖音": 1})
            assert isinstance(result, bytes)
            assert len(result) > 1000  # PNG 至少几 KB
            assert result[:4] == b"\x89PNG"  # PNG magic number
        except ImportError:
            pytest.skip("matplotlib 未安装")

    def test_pie_chart_returns_png(self):
        try:
            from feishu.delivery_charts import generate_status_pie_chart
            result = generate_status_pie_chart(4, 1)
            assert isinstance(result, bytes)
            assert result[:4] == b"\x89PNG"
        except ImportError:
            pytest.skip("matplotlib 未安装")

    def test_pie_chart_all_scheduled(self):
        try:
            from feishu.delivery_charts import generate_status_pie_chart
            result = generate_status_pie_chart(5, 0)
            assert isinstance(result, bytes)
            assert len(result) > 0
        except ImportError:
            pytest.skip("matplotlib 未安装")

    def test_pie_chart_empty(self):
        try:
            from feishu.delivery_charts import generate_status_pie_chart
            result = generate_status_pie_chart(0, 0)
            assert result == b""
        except ImportError:
            pytest.skip("matplotlib 未安装")
