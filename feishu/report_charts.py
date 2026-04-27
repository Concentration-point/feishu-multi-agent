"""数据分析报告图表生成 — matplotlib 内存渲染，返回 PNG bytes。

供 generate_report_doc 工具嵌入飞书云文档。
复用 delivery_charts 的 _configure_matplotlib 配置。
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


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


# 调色板（与 delivery_charts 一致）
_COLORS = ["#4ECDC4", "#FF6B6B", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#87CEEB"]


def generate_project_status_chart(status_counts: dict[str, int]) -> bytes:
    """项目状态分布横向柱状图。

    Args:
        status_counts: {"待处理": 2, "策略中": 3, "已完成": 5, ...}

    Returns:
        PNG 图片 bytes，空数据返回 b""
    """
    if not status_counts:
        return b""

    plt = _configure_matplotlib()

    labels = list(status_counts.keys())
    counts = list(status_counts.values())
    colors = _COLORS[: len(labels)] if len(labels) <= len(_COLORS) else (
        _COLORS * ((len(labels) // len(_COLORS)) + 1)
    )[: len(labels)]

    fig, ax = plt.subplots(figsize=(6, max(2.5, len(labels) * 0.5)), dpi=150)
    bars = ax.barh(labels, counts, color=colors, height=0.6, edgecolor="white", linewidth=0.8)
    ax.set_xlabel("项目数量", fontsize=11)
    ax.set_title("项目状态分布", fontsize=13, fontweight="bold", pad=12)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, v in zip(bars, counts):
        ax.text(
            bar.get_width() + 0.15, bar.get_y() + bar.get_height() / 2,
            str(v), ha="left", va="center", fontweight="bold", fontsize=11,
        )

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def generate_platform_pass_rate_chart(platform_pass_rates: dict[str, float]) -> bytes:
    """各平台审核通过率对比柱状图。

    Args:
        platform_pass_rates: {"小红书": 0.75, "公众号": 0.90, "抖音": 0.60}
                             值为 0~1 的浮点数

    Returns:
        PNG 图片 bytes，空数据返回 b""
    """
    if not platform_pass_rates:
        return b""

    plt = _configure_matplotlib()

    platforms = list(platform_pass_rates.keys())
    rates = [v * 100 for v in platform_pass_rates.values()]
    colors = _COLORS[: len(platforms)]

    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=150)
    bars = ax.bar(platforms, rates, color=colors, width=0.6, edgecolor="white", linewidth=0.8)
    ax.set_ylabel("通过率 (%)", fontsize=11)
    ax.set_title("各平台审核通过率", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylim(0, 110)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, v in zip(bars, rates):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
            f"{v:.0f}%", ha="center", va="bottom", fontweight="bold", fontsize=11,
        )

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
