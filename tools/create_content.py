"""工具: 创建一条内容排期行"""

from tools import AgentContext
from memory.project import ContentMemory, ContentItem

SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_content",
        "description": "创建一条内容排期行。自动关联到当前项目。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "内容标题",
                },
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
                "key_message": {
                    "type": "string",
                    "description": "核心卖点",
                },
                "target_audience": {
                    "type": "string",
                    "description": "目标人群",
                },
                "sequence": {
                    "type": "integer",
                    "description": "内容序号",
                },
            },
            "required": ["title", "platform", "content_type", "key_message",
                         "target_audience", "sequence"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    item = ContentItem(
        seq=params["sequence"],
        title=params["title"],
        platform=params["platform"],
        content_type=params["content_type"],
        key_point=params["key_message"],
        target_audience=params["target_audience"],
    )
    cm = ContentMemory()
    record_id = await cm.create_content_item(context.project_name, item)
    return f"内容行已创建，record_id={record_id}"
