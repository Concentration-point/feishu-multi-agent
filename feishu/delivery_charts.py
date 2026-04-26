"""交付文档图表生成 — matplotlib 内存渲染，返回 PNG bytes。

仅在 Orchestrator 生成交付文档时调用。
图表面向客户，措辞使用客户友好语言（不暴露内部审核指标）。
"""

from __future__ import annotations

import io
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# 调色板
_COLORS = ["#4ECDC4", "#FF6B6B", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#87CEEB"]
_GREEN = "#34D399"
_YELLOW = "#FCD34D"
_GRAY = "#D1D5DB"


def _configure_matplotlib():
    """配置 matplotlib 中文字体（Windows: Microsoft YaHei）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def generate_platform_bar_chart(platform_counts: dict[str, int]) -> bytes:
    """各平台内容数量柱状图。

    Args:
        platform_counts: {"小红书": 2, "公众号": 2, "抖音": 1}

    Returns:
        PNG 图片 bytes
    """
    plt = _configure_matplotlib()

    platforms = list(platform_counts.keys())
    counts = list(platform_counts.values())
    colors = _COLORS[: len(platforms)]

    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=150)
    bars = ax.bar(platforms, counts, color=colors, width=0.6, edgecolor="white", linewidth=0.8)
    ax.set_ylabel("内容数量", fontsize=11)
    ax.set_title("各平台内容分布", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylim(0, max(counts) * 1.3 if counts else 1)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, v in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
            str(v), ha="center", va="bottom", fontweight="bold", fontsize=11,
        )

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def generate_status_pie_chart(scheduled: int, pending: int) -> bytes:
    """内容状态分布饼图（面向客户：已排期 / 待确认）。

    Args:
        scheduled: 已排期数量
        pending: 待确认数量

    Returns:
        PNG 图片 bytes
    """
    plt = _configure_matplotlib()

    labels, sizes, colors = [], [], []
    if scheduled > 0:
        labels.append("已排期")
        sizes.append(scheduled)
        colors.append(_GREEN)
    if pending > 0:
        labels.append("待确认")
        sizes.append(pending)
        colors.append(_YELLOW)
    if not sizes:
        return b""

    fig, ax = plt.subplots(figsize=(4.5, 4), dpi=150)
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct="%1.0f%%",
        startangle=90, textprops={"fontsize": 12},
        wedgeprops={"edgecolor": "white", "linewidth": 2},
    )
    for t in autotexts:
        t.set_fontweight("bold")
    ax.set_title("内容状态分布", fontsize=13, fontweight="bold", pad=12)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def compute_delivery_stats(content_rows: list) -> dict:
    """从 ContentRecord 列表计算交付统计数据（面向客户）。

    Returns:
        {
            "total": int,
            "scheduled": int,
            "pending": int,
            "platform_counts": {"小红书": 2, ...},
            "platform_types": {"小红书": "种草笔记", ...},
            "word_range": {"min": 350, "max": 1200, "avg": 680},
            "first_date": "2024-06-10",
            "last_date": "2024-06-20",
        }
    """
    total = len(content_rows)
    platform_counter: Counter = Counter()
    platform_types: dict[str, set] = {}
    word_counts: list[int] = []
    dates: list[str] = []
    scheduled = 0

    for row in content_rows:
        platform = row.platform or "未指定"
        platform_counter[platform] += 1
        platform_types.setdefault(platform, set()).add(row.content_type or "未知")
        if row.word_count and row.word_count > 0:
            word_counts.append(row.word_count)
        if row.publish_date:
            dates.append(row.publish_date)
            scheduled += 1

    sorted_dates = sorted(d for d in dates if d)

    return {
        "total": total,
        "scheduled": scheduled,
        "pending": total - scheduled,
        "platform_counts": dict(platform_counter.most_common()),
        "platform_types": {k: "、".join(sorted(v)) for k, v in platform_types.items()},
        "word_range": {
            "min": min(word_counts) if word_counts else 0,
            "max": max(word_counts) if word_counts else 0,
            "avg": round(sum(word_counts) / len(word_counts)) if word_counts else 0,
        },
        "first_date": sorted_dates[0] if sorted_dates else "",
        "last_date": sorted_dates[-1] if sorted_dates else "",
    }
