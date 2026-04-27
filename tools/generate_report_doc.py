"""工具: 将数据分析结果生成为飞书知识空间云文档（含表格和图表）。

数据分析师先调 query_project_stats 获取原始数据并自行分析，
再调本工具传入洞察结论，工具负责：
  1. 拉取最新统计数据
  2. 生成 matplotlib 图表
  3. 在飞书知识空间创建/更新结构化文档
"""

import json
import logging
from datetime import datetime

from tools import AgentContext
from config import WIKI_SPACE_ID

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_report_doc",
        "description": (
            "将数据分析结果生成为飞书知识空间云文档（含表格和图表）。"
            "传入分析师的洞察结论和建议，工具自动拉取数据、生成图表、写入文档。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "report_type": {
                    "type": "string",
                    "enum": ["weekly", "insight", "decision"],
                    "description": "报告类型：weekly=运营周报，insight=数据洞察，decision=决策建议",
                },
                "title": {
                    "type": "string",
                    "description": "报告标题，如「智策传媒·运营周报（2026-04-25）」",
                },
                "summary": {
                    "type": "string",
                    "description": "核心发现摘要（3句话以内）",
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可操作的建议列表（2-5条，每条附数据支撑）",
                },
            },
            "required": ["title", "summary", "recommendations"],
        },
    },
}

_REPORT_TYPE_LABELS = {
    "weekly": "运营周报",
    "insight": "数据洞察",
    "decision": "决策建议",
}

_REPORT_EMOJI = {
    "weekly": "bar_chart",
    "insight": "mag",
    "decision": "bulb",
}


async def _fetch_stats() -> dict:
    """调用 query_project_stats 获取全量统计数据。"""
    from tools.query_project_stats import execute as qs_execute

    dummy_ctx = AgentContext(record_id="__report__", project_name="", role_id="data_analyst")
    raw = await qs_execute({"scope": "all"}, dummy_ctx)
    return json.loads(raw)


def _compute_platform_pass_rates(content_data: dict) -> dict[str, float]:
    """从 platform_review_detail 计算各平台审核通过率。"""
    detail = content_data.get("platform_review_detail", {})
    rates: dict[str, float] = {}
    for platform, status_counts in detail.items():
        passed = status_counts.get("通过", 0)
        total_reviewed = sum(v for k, v in status_counts.items() if k != "未审核")
        if total_reviewed > 0:
            rates[platform] = round(passed / total_reviewed, 3)
    return rates


def _build_blocks(
    report_type: str,
    title: str,
    summary: str,
    recommendations: list[str],
    stats: dict,
) -> list[dict]:
    """构建飞书文档结构化块列表。"""
    today = datetime.now().strftime("%Y-%m-%d")
    label = _REPORT_TYPE_LABELS.get(report_type, "数据分析报告")
    emoji = _REPORT_EMOJI.get(report_type, "bar_chart")

    blocks: list[dict] = []

    # ── 标题 ──
    blocks.append({"type": "heading1", "text": title})

    # ── 概览 Callout ──
    proj = stats.get("projects", {})
    content = stats.get("content", {})
    exp = stats.get("experience", {})

    overview_lines = [
        f"报告类型: {label}",
        f"项目总数: {proj.get('total', 0)} | 完成率: {_pct(proj.get('completion_rate', 0))}",
        f"内容总条数: {content.get('total', 0)} | 成稿率: {_pct(content.get('draft_rate', 0))}",
        f"经验池条目: {exp.get('total', 0)}",
        f"数据日期: {today}",
    ]
    blocks.append({"type": "callout", "text": "\n".join(overview_lines), "emoji": emoji, "bg_color": 5})
    blocks.append({"type": "divider"})

    # ── 核心发现 ──
    blocks.append({"type": "heading2", "text": "核心发现"})
    blocks.append({"type": "text", "text": summary, "bold": True})
    blocks.append({"type": "divider"})

    # ── 项目运营概览 ──
    if proj and not proj.get("error"):
        blocks.append({"type": "heading2", "text": "项目运营概览"})

        status_data = proj.get("by_status", {})
        if status_data:
            table_rows = [["状态", "数量", "占比"]]
            total = proj.get("total", 1)
            for status, count in status_data.items():
                table_rows.append([status, str(count), _pct(count / total if total else 0)])
            blocks.append({"type": "table", "rows": table_rows})

            # 项目状态图表
            try:
                from feishu.report_charts import generate_project_status_chart
                chart_png = generate_project_status_chart(status_data)
                if chart_png:
                    blocks.append({"type": "image", "data": chart_png, "name": "project_status.png"})
            except Exception as e:
                logger.warning("项目状态图表生成失败: %s", e)

        # 按类型分布
        type_data = proj.get("by_type", {})
        if type_data:
            type_rows = [["项目类型", "数量", "平均审核通过率"]]
            rate_by_type = proj.get("avg_review_pass_rate_by_type", {})
            for ptype, count in type_data.items():
                avg_rate = rate_by_type.get(ptype)
                type_rows.append([ptype, str(count), _pct(avg_rate) if avg_rate else "—"])
            blocks.append({"type": "table", "rows": type_rows})

        blocks.append({"type": "divider"})

    # ── 内容质量分析 ──
    if content and not content.get("error"):
        blocks.append({"type": "heading2", "text": "内容质量分析"})

        # 平台审核通过率
        platform_rates = _compute_platform_pass_rates(content)
        if platform_rates:
            rate_rows = [["平台", "审核通过率", "内容数量"]]
            by_platform = content.get("by_platform", {})
            for plat, rate in platform_rates.items():
                rate_rows.append([plat, _pct(rate), str(by_platform.get(plat, 0))])
            blocks.append({"type": "table", "rows": rate_rows})

            # 通过率图表
            try:
                from feishu.report_charts import generate_platform_pass_rate_chart
                chart_png = generate_platform_pass_rate_chart(platform_rates)
                if chart_png:
                    blocks.append({"type": "image", "data": chart_png, "name": "pass_rate.png"})
            except Exception as e:
                logger.warning("通过率图表生成失败: %s", e)

        # 返工率
        review_status = content.get("by_review_status", {})
        rework_count = review_status.get("需修改", 0)
        total_reviewed = sum(v for k, v in review_status.items() if k != "未审核")
        if total_reviewed > 0:
            rework_rate = rework_count / total_reviewed
            blocks.append({"type": "text", "text": f"返工率: {_pct(rework_rate)}（{rework_count}/{total_reviewed}）"})

        # 字数统计
        wc = content.get("word_count_stats", {})
        if wc.get("avg_words"):
            blocks.append({
                "type": "text",
                "text": f"平均字数: {wc['avg_words']} | 范围: {wc.get('min_words', 0)}~{wc.get('max_words', 0)}",
            })

        blocks.append({"type": "divider"})

    # ── 经验沉淀健康度 ──
    if exp and not exp.get("error"):
        blocks.append({"type": "heading2", "text": "经验沉淀健康度"})

        role_data = exp.get("by_role", {})
        if role_data:
            exp_rows = [["角色", "经验条数", "占比"]]
            exp_total = exp.get("total", 1)
            for role, count in role_data.items():
                exp_rows.append([role, str(count), _pct(count / exp_total if exp_total else 0)])
            blocks.append({"type": "table", "rows": exp_rows})

        conf = exp.get("confidence_stats", {})
        if conf.get("avg"):
            blocks.append({
                "type": "text",
                "text": f"平均置信度: {conf['avg']:.2f} | 范围: {conf.get('min', 0):.2f}~{conf.get('max', 0):.2f}",
            })
        blocks.append({"type": "divider"})

    # ── 建议 ──
    blocks.append({"type": "heading2", "text": "决策建议"})
    for rec in recommendations:
        blocks.append({"type": "bullet", "text": rec})
    blocks.append({"type": "divider"})

    # ── 署名 ──
    blocks.append({"type": "text", "text": f"智策传媒·数据分析师 · {today} 自动生成"})

    return blocks


def _pct(val: float | None) -> str:
    """浮点数转百分比字符串。"""
    if val is None:
        return "—"
    return f"{val * 100:.1f}%"


async def execute(params: dict, context: AgentContext) -> str:
    report_type = params.get("report_type", "weekly")
    title = params.get("title", "数据分析报告")
    summary = params.get("summary", "")
    recommendations = params.get("recommendations", [])

    if not WIKI_SPACE_ID:
        return (
            f"报告文档未生成（未配置 WIKI_SPACE_ID）。\n"
            f"标题: {title}\n"
            f"摘要: {summary}\n"
            f"建议数: {len(recommendations)} 条"
        )

    # 1. 拉取最新统计数据
    try:
        stats = await _fetch_stats()
    except Exception as e:
        logger.warning("拉取统计数据失败: %s", e)
        return f"报告文档生成失败: 无法拉取统计数据 — {e}"

    # 2. 构建文档块
    blocks = _build_blocks(report_type, title, summary, recommendations, stats)

    # 3. 创建飞书知识空间节点并写入
    try:
        from feishu.wiki import FeishuWikiClient
        from sync.wiki_sync import WikiSyncService

        wiki = FeishuWikiClient()
        sync_svc = WikiSyncService(WIKI_SPACE_ID)

        parent_title = "数据分析报告"
        parent_node = await sync_svc._ensure_parent_node(parent_title)
        parent_token = parent_node["node_token"]

        existing = await wiki.find_node_by_title(WIKI_SPACE_ID, title, parent_token)
        if existing:
            obj_token = existing.get("obj_token", "")
        else:
            node = await wiki.create_node(WIKI_SPACE_ID, parent_token, title)
            obj_token = node.get("obj_token", "")

        if not obj_token:
            return "报告文档生成失败: 无法获取 document_id"

        await wiki.write_delivery_doc(obj_token, blocks)
        doc_url = f"https://feishu.cn/docx/{obj_token}"
        logger.info("报告文档已生成: %s → %s", title, doc_url)

        return (
            f"报告文档已生成并写入飞书知识空间:\n"
            f"标题: {title}\n"
            f"链接: {doc_url}\n"
            f"核心发现: {summary}\n"
            f"建议数: {len(recommendations)} 条"
        )
    except Exception as e:
        logger.warning("报告文档写入失败: %s", e)
        return f"报告文档生成失败: {e}"
