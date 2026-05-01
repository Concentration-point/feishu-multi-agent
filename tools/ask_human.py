"""Agent 工具: 向飞书群发送带按钮的交互式卡片，阻塞等待人类点击后返回所选项文字。

双通道接收人类响应：
  1. card.action.trigger（主通道）—— 用户直接点击卡片按钮，WebSocket 实时接收
  2. im.message.receive_v1（兜底）—— 用户在群里打字回复数字或选项文字
  3. polling list_messages（降级）—— WebSocket 不可用时的最终兜底

典型用途：
  - Agent 遇到需要人类判断的节点（审核通过/驳回/修改）
  - 多方案选择（策略A/策略B/需要重新讨论）
  - 风险确认（继续/暂停/上报）

依赖：
  - feishu/ws_client.py 启动的 WebSocket 长连接（在 server 模式下自动启动）
  - 飞书开放平台已订阅 card.action.trigger 事件（长连接模式）
  - 飞书开放平台已订阅 im.message.receive_v1 事件（兜底）
"""
import asyncio
import logging
import time

from config import FEISHU_CHAT_ID, ASK_HUMAN_TIMEOUT
from tools import AgentContext

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_human",
        "description": (
            "向飞书群聊发送带按钮的交互式卡片，等待人类点击按钮或回复文字后返回所选项。"
            "用于需要人类判断的场景：如审核结果确认、多方案决策、风险等级评估等。"
            "卡片包含真正的飞书按钮，人类可直接点击选择，无需打字。"
            "工具会阻塞等待人类响应，超时则返回提示。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "向人类提出的问题，支持 Markdown 格式，要清晰说明背景",
                },
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "选项列表，每项对应一个按钮，建议 2-4 个，文字简短清晰",
                    "minItems": 2,
                    "maxItems": 6,
                },
                "title": {
                    "type": "string",
                    "description": "卡片标题，简短说明这是什么决策，默认「需要你的判断」",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": f"等待超时秒数，默认 {ASK_HUMAN_TIMEOUT} 秒",
                },
            },
            "required": ["question", "choices"],
        },
    },
}


async def _poll_for_reply(chat_id: str, start_time_unix: str, timeout_sec: int) -> None:
    """Production fallback: poll chat messages and feed them back into card_actions."""
    from feishu.card_actions import resolve_by_message
    from feishu.im import FeishuIMClient

    im = FeishuIMClient()
    seen_message_ids: set[str] = set()
    deadline = time.monotonic() + timeout_sec

    while time.monotonic() < deadline:
        await asyncio.sleep(4)
        try:
            messages = await im.list_messages(
                chat_id=chat_id,
                start_time=start_time_unix,
                page_size=20,
            )
        except Exception as exc:
            logger.warning("ask_human: polling list_messages failed: %s", exc)
            continue

        for msg in messages:
            message_id = msg.get("message_id", "")
            if message_id:
                if message_id in seen_message_ids:
                    continue
                seen_message_ids.add(message_id)

            if not im.is_user_message(msg):
                continue

            text = im.extract_text_from_message(msg).strip()
            if not text:
                continue

            logger.info("ask_human: polling saw user reply text=%r", text)
            if resolve_by_message(chat_id, text):
                logger.info("ask_human: polling matched user reply")
                return


async def execute(params: dict, context: AgentContext) -> str:
    from feishu.im import FeishuIMClient
    from feishu.card_actions import register, cancel_wait

    question: str = (params.get("question") or "").strip()
    choices: list[str] = params.get("choices") or []
    title: str = (params.get("title") or "需要你的判断").strip()
    timeout_sec: int = int(params.get("timeout_seconds") or ASK_HUMAN_TIMEOUT)

    if not question:
        return "错误: question 不能为空"
    if len(choices) < 2:
        return "错误: choices 至少需要 2 个选项"
    if len(choices) > 6:
        choices = choices[:6]
    if not FEISHU_CHAT_ID:
        return "错误: 未配置 FEISHU_CHAT_ID，无法发送卡片"

    im = FeishuIMClient()
    start_time_unix = str(max(0, int(time.time()) - 2))
    try:
        await im.send_choice_card(
            chat_id=FEISHU_CHAT_ID,
            question=question,
            choices=choices,
            title=title,
        )
    except Exception as exc:
        logger.error("ask_human: 发送选择卡片失败: %s", exc)
        return f"发送选择卡片失败: {exc}"

    # 以 chat_id 为 key 注册等待（同一群同时只允许一个待处理问题）
    try:
        fut = register(FEISHU_CHAT_ID, choices)
    except RuntimeError as exc:
        return f"ask_human 不可用（未在 server 模式下运行）: {exc}"

    logger.info(
        "ask_human: 卡片已发出 chat_id=%s，等待用户回复（超时 %ds）...",
        FEISHU_CHAT_ID, timeout_sec,
    )
    poll_task = asyncio.create_task(_poll_for_reply(FEISHU_CHAT_ID, start_time_unix, timeout_sec))

    try:
        choice = await asyncio.wait_for(fut, timeout=timeout_sec)
        logger.info("ask_human: 收到选择 chat_id=%s choice=%r", FEISHU_CHAT_ID, choice)
        return f"人类已选择：{choice}"
    except asyncio.TimeoutError:
        cancel_wait(FEISHU_CHAT_ID)
        return (
            f"等待超时（{timeout_sec} 秒），未收到用户回复。\n"
            "请告知用户重新触发，或直接在群里告知决定。"
        )
    except asyncio.CancelledError:
        cancel_wait(FEISHU_CHAT_ID)
        return "等待被取消（服务关闭？），请重新触发"
    finally:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
