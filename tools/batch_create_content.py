"""工具: 批量创建内容排期行"""

import json
from feishu.bitable import FeishuAPIError
from tools import AgentContext
from memory.project import ContentMemory, ContentItem

SCHEMA = {
    "type": "function",
    "function": {
        "name": "batch_create_content",
        "description": "批量创建多条内容排期行。适用于策略师一次性规划整个内容矩阵。",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "内容标题"},
                            "platform": {
                                "type": "string",
                                "enum": ["公众号", "小红书", "抖音", "微博", "视频号", "B站", "知乎"],
                                "description": "目标投放平台（只能填平台名本身，不要带内容形式后缀如'抖音脚本'）",
                            },
                            "content_type": {
                                "type": "string",
                                "enum": ["深度长文", "种草笔记", "口播脚本", "话题文案", "图文卡片", "开箱脚本", "对比种草"],
                                "description": "内容形式（平台无关的文稿体裁，如口播脚本 / 种草笔记）",
                            },
                            "key_message": {"type": "string", "description": "核心卖点"},
                            "target_audience": {"type": "string", "description": "目标人群"},
                            "sequence": {"type": "integer", "description": "内容序号"},
                        },
                        "required": ["title", "platform", "content_type",
                                     "key_message", "target_audience", "sequence"],
                    },
                    "description": "内容行列表",
                },
            },
            "required": ["items"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    raw_items = params.get("items", [])
    if not raw_items:
        return "错误: items 不能为空"

    try:
        cm = ContentMemory()

        # ── 入口去重：拉当前项目已有内容行，按 title 精确比对（strip 后）──
        # 防止 strategist 因 Orchestrator 重启而重复建仓导致内容表膨胀
        existing = await cm.list_by_project(context.project_name)
        existing_titles = {
            (r.title or "").strip()
            for r in existing
            if (r.title or "").strip()
        }

        kept: list[dict] = []
        skipped: list[dict] = []
        for it in raw_items:
            title_norm = (it.get("title") or "").strip()
            if title_norm and title_norm in existing_titles:
                skipped.append({"title": title_norm, "reason": "已存在同名内容行"})
                continue
            # 同批次内部也要去重，防止单次 items 内自带重复
            if title_norm in {(k.get("title") or "").strip() for k in kept}:
                skipped.append({"title": title_norm, "reason": "同批次内重复"})
                continue
            kept.append(it)

        # 全部重复 → 直接返回不发起 Bitable 写入
        if not kept:
            return json.dumps({
                "message": (
                    f"全部 {len(raw_items)} 条已存在，未创建新内容行。"
                    f"已有内容行 {len(existing)} 条，无需重复建仓。"
                ),
                "skipped_count": len(skipped),
                "skipped": skipped[:10],
                "existing_count": len(existing),
                "record_ids": [],
            }, ensure_ascii=False)

        content_items = [
            ContentItem(
                seq=it["sequence"],
                title=it["title"],
                platform=it["platform"],
                content_type=it["content_type"],
                key_point=it["key_message"],
                target_audience=it["target_audience"],
            )
            for it in kept
        ]

        record_ids = await cm.batch_create_content_items(
            context.project_name, content_items
        )
        msg = f"已批量创建 {len(record_ids)} 条内容行"
        if skipped:
            msg += f"，跳过 {len(skipped)} 条已存在/重复"
        return json.dumps({
            "message": msg,
            "record_ids": record_ids,
            "skipped_count": len(skipped),
            "skipped": skipped[:10],
        }, ensure_ascii=False)

    except FeishuAPIError as exc:
        return f"飞书API错误（code={exc.code}）: {exc.msg}"
