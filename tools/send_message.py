"""工具: 发送飞书群聊消息（文本 / 卡片）"""

import logging
from tools import AgentContext
from config import FEISHU_CHAT_ID

logger = logging.getLogger(__name__)

# 角色 ID → 中文名映射
_ROLE_NAMES = {
    "account_manager": "客户经理",
    "strategist": "策略师",
    "copywriter": "文案",
    "reviewer": "审核",
    "project_manager": "项目经理",
    "data_analyst": "数据分析师",
}

SCHEMA = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": "向飞书群聊发送进度消息，让团队了解当前工作状态。支持纯文本和富文本卡片。",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要发送的消息内容（支持 Markdown）",
                },
                "message_type": {
                    "type": "string",
                    "enum": ["text", "card"],
                    "description": "消息类型，默认 card",
                },
                "title": {
                    "type": "string",
                    "description": "卡片标题（仅 card 模式），默认用角色名 + 进度更新",
                },
                "color": {
                    "type": "string",
                    "enum": ["blue", "green", "orange", "red", "purple"],
                    "description": "卡片颜色，默认 blue",
                },
            },
            "required": ["message"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    message = params.get("message", "")
    msg_type = params.get("message_type", "card")
    color = params.get("color", "blue")

    role_name = _ROLE_NAMES.get(context.role_id, context.role_id)
    title = params.get("title") or f"[{role_name}] 进度更新"

    if not FEISHU_CHAT_ID:
        logger.info("[IM fallback] %s: %s", role_name, message)
        return f"消息已记录（未配置 FEISHU_CHAT_ID）: {message[:80]}..."

    try:
        from feishu.im import FeishuIMClient
        im = FeishuIMClient()

        prefixed = f"[{role_name}] {message}"

        if msg_type == "text":
            await im.send_text(FEISHU_CHAT_ID, prefixed)
        else:
            await im.send_card(FEISHU_CHAT_ID, title, prefixed, color)

        return f"消息已发送: {message[:80]}..."
    except Exception as e:
        logger.warning("消息发送失败: %s", e)
        return f"消息发送失败: {e}"
