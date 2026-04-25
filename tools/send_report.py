"""工具: 发送数据分析报告到飞书群聊。

以富文本卡片形式推送，支持 Markdown 格式的长文本报告，
适用于运营周报、数据洞察、决策建议等场景。
"""

import logging

from tools import AgentContext
from config import FEISHU_CHAT_ID

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "send_report",
        "description": (
            "将数据分析报告以富文本卡片形式发送到飞书群聊。"
            "适用于周报、数据洞察、决策建议等长文本报告。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "报告标题，如「智策传媒·运营周报」「内容质量洞察」",
                },
                "content": {
                    "type": "string",
                    "description": "报告正文（支持 Markdown 格式）",
                },
                "report_type": {
                    "type": "string",
                    "enum": ["weekly", "insight", "decision"],
                    "description": "报告类型：weekly=周报，insight=数据洞察，decision=决策建议",
                },
            },
            "required": ["title", "content"],
        },
    },
}

_COLOR_MAP = {
    "weekly": "blue",
    "insight": "purple",
    "decision": "orange",
}


async def execute(params: dict, context: AgentContext) -> str:
    title = params.get("title", "数据分析报告")
    content = params.get("content", "")
    report_type = params.get("report_type", "weekly")

    if not content:
        return "错误: content 参数不能为空"

    color = _COLOR_MAP.get(report_type, "blue")
    prefixed = f"[数据分析师] {content}"

    if not FEISHU_CHAT_ID:
        logger.info("[报告 fallback] %s:\n%s", title, content[:300])
        return (
            f"报告已生成（未配置 FEISHU_CHAT_ID，未实际发送）:\n"
            f"标题: {title}\n"
            f"类型: {report_type}\n"
            f"正文长度: {len(content)} 字"
        )

    try:
        from feishu.im import FeishuIMClient

        im = FeishuIMClient()
        await im.send_card(FEISHU_CHAT_ID, title, prefixed, color)
        return f"报告已发送到飞书群聊: {title}（{len(content)} 字）"
    except Exception as e:
        logger.warning("报告发送失败: %s", e)
        return f"报告发送失败: {e}"
