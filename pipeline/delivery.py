"""交付文档生成：流水线收尾后在飞书知识空间生成面向客户的交付云文档。"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from config import WIKI_SPACE_ID
from memory.project import ContentMemory as _DefaultContentMemory

if TYPE_CHECKING:
    from memory.project import ContentMemory
    from orchestrator import Orchestrator


logger = logging.getLogger(__name__)


def _resolve_ContentMemory():
    """通过 orchestrator 模块属性获取 ContentMemory，让测试 monkey-patch 生效。"""
    import sys
    orch_mod = sys.modules.get("orchestrator")
    if orch_mod is not None:
        return getattr(orch_mod, "ContentMemory", _DefaultContentMemory)
    return _DefaultContentMemory


def md_to_blocks(text: str) -> list[dict]:
    """把 LLM 产出的 Markdown 文本转换成飞书文档 block 列表。

    支持：## 标题、### 标题、- 列表、* 列表、--- 分隔线，以及行内 **bold** / *em* / `code` 剥离。
    """
    blocks: list[dict] = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("### "):
            blocks.append({"type": "heading3", "text": s[4:].strip()})
        elif s.startswith("## "):
            blocks.append({"type": "heading2", "text": s[3:].strip()})
        elif s.startswith("# "):
            blocks.append({"type": "heading2", "text": s[2:].strip()})
        elif s.startswith(("- ", "* ", "+ ")):
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", s[2:])
            blocks.append({"type": "bullet", "text": clean.strip()})
        elif s in ("---", "===", "***"):
            blocks.append({"type": "divider"})
        else:
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
            clean = re.sub(r"\*(.+?)\*", r"\1", clean)
            clean = re.sub(r"`(.+?)`", r"\1", clean)
            blocks.append({"type": "text", "text": clean})
    return blocks


async def get_delivery_parent_token(orch: "Orchestrator", wiki) -> str:
    """查找或创建「项目交付文档」父节点，返回 node_token。进程级缓存，单次创建。"""
    # 进程级缓存挂在 Orchestrator 类上，避免重复创建
    from orchestrator import Orchestrator as _OrchCls

    if _OrchCls._delivery_parent_token:
        return _OrchCls._delivery_parent_token

    parent_title = "项目交付文档"
    existing = await wiki.find_node_by_title(WIKI_SPACE_ID, parent_title)
    if existing:
        _OrchCls._delivery_parent_token = existing["node_token"]
        return _OrchCls._delivery_parent_token

    # 取空间根 token：顶级节点的 parent_node_token 即空间根
    root_nodes = await wiki.list_nodes(WIKI_SPACE_ID)
    space_root_token = root_nodes[0].get("parent_node_token", "") if root_nodes else ""
    node = await wiki.create_node(WIKI_SPACE_ID, space_root_token, parent_title)
    _OrchCls._delivery_parent_token = node["node_token"]
    return _OrchCls._delivery_parent_token


async def generate_delivery_document(orch: "Orchestrator", project_name: str) -> str | None:
    """流水线完成后，在飞书知识空间自动生成面向客户的交付云文档。

    返回文档 URL（成功时）或 None。
    文档内容面向客户，不包含内部审核数据。
    """
    from datetime import datetime
    from feishu.wiki import FeishuWikiClient

    wiki = FeishuWikiClient()
    proj = await orch._pm.load()
    cm = _resolve_ContentMemory()()
    rows = await cm.list_by_project(project_name)

    # 统计数据
    from feishu.delivery_charts import compute_delivery_stats
    stats = compute_delivery_stats(rows)
    today = datetime.now().strftime("%Y-%m-%d")
    doc_title = f"{project_name}-交付报告-{today}"

    # 查找或创建「项目交付文档」父节点（进程级缓存，不重复创建）
    parent_token = await get_delivery_parent_token(orch, wiki)

    existing = await wiki.find_node_by_title(WIKI_SPACE_ID, doc_title, parent_token)
    if existing:
        obj_token = existing.get("obj_token", "")
    else:
        node = await wiki.create_node(WIKI_SPACE_ID, parent_token, doc_title)
        obj_token = node.get("obj_token", "")

    if not obj_token:
        logger.warning("交付文档：无法获取 document_id")
        return None

    # 飞书 wiki 新建节点后，底层 docx 文档需要约 1-2s 才能通过 docx API 访问，
    # 立即请求会导致 httpx 60s 超时 × 3次重试（~4分钟挂起）。
    await wiki.wait_for_new_doc_ready(obj_token)
    logger.info("[交付文档] 开始写入文档内容，obj_token=%s", obj_token)

    # 构建文档结构化块（面向客户）
    blocks: list[dict] = []

    # ── 交付概览（Callout 蓝色高亮块）──
    platforms_str = "、".join(stats["platform_counts"].keys()) if stats["platform_counts"] else "未指定"
    date_range = ""
    if stats["first_date"] and stats["last_date"]:
        date_range = f"{stats['first_date']} — {stats['last_date']}"
    elif stats["first_date"]:
        date_range = stats["first_date"]

    overview_lines = [
        f"📝 交付内容: {stats['total']} 篇",
        f"📡 覆盖平台: {platforms_str}",
    ]
    if date_range:
        overview_lines.append(f"📅 排期周期: {date_range}")
    if stats["pending"] > 0:
        overview_lines.append(f"⏳ 待确认: {stats['pending']} 篇")
    overview_lines.append(f"📆 交付日期: {today}")
    if proj.project_type:
        overview_lines.insert(0, f"📋 项目类型: {proj.project_type}")

    blocks.append({"type": "callout", "text": "\n".join(overview_lines), "emoji": "chart_with_upwards_trend", "bg_color": 5})
    blocks.append({"type": "divider"})

    # ── 需求理解 ──
    if proj.brief_analysis:
        blocks.append({"type": "heading2", "text": "需求理解"})
        blocks.extend(md_to_blocks(proj.brief_analysis))
        blocks.append({"type": "divider"})

    # ── 策略思路 ──
    if proj.strategy:
        blocks.append({"type": "heading2", "text": "策略思路"})
        blocks.extend(md_to_blocks(proj.strategy))
        blocks.append({"type": "divider"})

    # ── 内容清单表格 ──
    if rows:
        blocks.append({"type": "heading2", "text": "📋 内容清单"})
        table_header = ["#", "标题", "平台", "类型", "计划发布", "字数"]
        table_rows = [table_header]
        for idx, row in enumerate(rows, 1):
            table_rows.append([
                str(idx),
                (row.title or "未命名")[:20],
                row.platform or "—",
                row.content_type or "—",
                row.publish_date or "待确认",
                str(row.word_count) if row.word_count else "—",
            ])
        blocks.append({"type": "table", "rows": table_rows})

    # ── 各内容正文 ──
    for idx, row in enumerate(rows, 1):
        if row.draft:
            blocks.append({"type": "heading3", "text": f"{idx}. {row.title or '未命名'}"})
            blocks.extend(md_to_blocks(row.draft))

    if rows:
        blocks.append({"type": "divider"})

    # ── 投放概览（表格 + 图表）──
    if stats["platform_counts"]:
        blocks.append({"type": "heading2", "text": "📈 投放概览"})

        # 平台分布表
        pt_header = ["平台", "内容数", "内容类型", "字数区间"]
        pt_rows = [pt_header]
        for plat, cnt in stats["platform_counts"].items():
            plat_rows_data = [r for r in rows if (r.platform or "未指定") == plat]
            wc_list = [r.word_count for r in plat_rows_data if r.word_count > 0]
            wc_range = f"{min(wc_list)}~{max(wc_list)}" if wc_list else "—"
            pt_rows.append([
                plat,
                str(cnt),
                stats["platform_types"].get(plat, "—"),
                wc_range,
            ])
        blocks.append({"type": "table", "rows": pt_rows})

        # 图表（matplotlib，失败不影响主流程）
        # 用 run_in_executor 防止同步 matplotlib 代码阻塞 asyncio 事件循环
        # Windows 首次初始化 MKL/字体缓存时可能长时间卡住，加 15s timeout 兜底
        try:
            from feishu.delivery_charts import generate_platform_bar_chart, generate_status_pie_chart
            import functools
            _loop = asyncio.get_event_loop()

            bar_png = await asyncio.wait_for(
                _loop.run_in_executor(None, generate_platform_bar_chart, stats["platform_counts"]),
                timeout=15.0,
            )
            if bar_png:
                blocks.append({"type": "image", "data": bar_png, "name": "platform_bar.png"})

            if stats["total"] > 0:
                pie_png = await asyncio.wait_for(
                    _loop.run_in_executor(
                        None,
                        functools.partial(generate_status_pie_chart, stats["scheduled"], stats["pending"]),
                    ),
                    timeout=15.0,
                )
                if pie_png:
                    blocks.append({"type": "image", "data": pie_png, "name": "status_pie.png"})
        except ImportError:
            logger.info("matplotlib 未安装，跳过图表生成")
        except asyncio.TimeoutError:
            logger.warning("图表生成超时（15s），跳过图表嵌入")
        except Exception as chart_exc:
            logger.warning("图表生成失败（不影响文档）: %s", chart_exc)

        blocks.append({"type": "divider"})

    # ── 待确认项（黄色 Callout）──
    pending_rows = [r for r in rows if not r.publish_date]
    if pending_rows:
        pending_text = "以下内容待贵方确认后安排发布：\n" + "\n".join(
            f"· 《{r.title or '未命名'}》— {r.platform or '未指定'}" for r in pending_rows
        )
        blocks.append({"type": "callout", "text": pending_text, "emoji": "warning", "bg_color": 3})
        blocks.append({"type": "divider"})

    # ── 交付摘要 ──
    if proj.delivery:
        blocks.append({"type": "heading2", "text": "交付总结"})
        blocks.extend(md_to_blocks(proj.delivery))
        blocks.append({"type": "divider"})

    # ── 署名 ──
    blocks.append({"type": "text", "text": f"智策传媒 · {today} 自动生成"})

    # 写入文档
    await wiki.write_delivery_doc(obj_token, blocks)
    doc_url = f"https://feishu.cn/docx/{obj_token}"

    print(f"[Orchestrator] 交付文档已生成: {doc_title} → {doc_url}")
    await orch._broadcast(
        title="📄 交付文档已生成",
        content=f"客户 **{project_name}** 的交付报告已自动生成\n📎 {doc_url}",
        color="green",
    )
    return doc_url
