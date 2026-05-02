"""Agent 工具: 批量向飞书群发送多张交互式选择卡片，逐题阻塞等待人类回复。

适用场景：客户经理有 2 个及以上 🔴 强阻塞项需要追问时，一次性发完所有问题，
每张卡片标注「追问 1/N」，逐题等待人类点击后再发下一题。

限制：单次最多 5 题。超出部分由 Agent 在调用前裁剪。
"""
import logging

from config import ASK_HUMAN_TIMEOUT
from tools import AgentContext

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_human_batch",
        "description": (
            "批量向飞书群聊发送多张带按钮的交互式卡片，逐题阻塞等待人类回复。"
            "每张卡片标注「追问 1/N」，适用于需要一次性追问多个问题的场景。"
            "单次最多 5 题，每题 2-4 个选项。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "问题列表，每项包含 question/choices/title",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "向人类提出的问题，支持 Markdown",
                            },
                            "choices": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "选项列表，2-4 个",
                                "minItems": 2,
                                "maxItems": 4,
                            },
                            "title": {
                                "type": "string",
                                "description": "卡片标题，可选",
                            },
                        },
                        "required": ["question", "choices"],
                    },
                    "minItems": 1,
                    "maxItems": 5,
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": f"每题等待超时秒数，默认 {ASK_HUMAN_TIMEOUT} 秒",
                },
            },
            "required": ["questions"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    from tools.ask_human import execute as ask_human_execute

    questions: list[dict] = params.get("questions") or []
    timeout_sec: int = params.get("timeout_seconds") or ASK_HUMAN_TIMEOUT

    if not questions:
        return "错误: questions 不能为空"
    if len(questions) > 5:
        questions = questions[:5]

    total = len(questions)
    results: list[str] = []

    for idx, q in enumerate(questions, 1):
        title = q.get("title") or "需要你的判断"
        tagged_title = f"追问 {idx}/{total} — {title}"

        single_params = {
            "question": q.get("question", ""),
            "choices": q.get("choices", []),
            "title": tagged_title,
            "timeout_seconds": timeout_sec,
        }

        logger.info("ask_human_batch: 发送第 %d/%d 题", idx, total)
        result = await ask_human_execute(single_params, context)
        results.append(f"【{idx}/{total}】{result}")
        logger.info("ask_human_batch: 第 %d/%d 题结果: %s", idx, total, result)

    return "\n".join(results)
