"""工具: 批量创建内容排期行"""

import json
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

    content_items = [
        ContentItem(
            seq=it["sequence"],
            title=it["title"],
            platform=it["platform"],
            content_type=it["content_type"],
            key_point=it["key_message"],
            target_audience=it["target_audience"],
        )
        for it in raw_items
    ]

    cm = ContentMemory()
    record_ids = await cm.batch_create_content_items(
        context.project_name, content_items
    )
    return json.dumps({
        "message": f"已批量创建 {len(record_ids)} 条内容行",
        "record_ids": record_ids,
    }, ensure_ascii=False)
