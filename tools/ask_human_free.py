"""Agent 工具: 向飞书群发送自由文本提示卡片，阻塞等待人类回复任意文字。

与 ask_human 的区别：
  - ask_human: 选择题（2-6 个按钮选项），用于需要人类做决策的场景
  - ask_human_free: 自由文本（无选项），用于需要人类补充信息的追问场景

典型用途：
  - 客户经理追问缺失的 Brief 信息（"请补充平台信息"）
  - 需要人类提供自由格式回答的场景（非选择题）

依赖：
  - feishu/ws_client.py 启动的 WebSocket 长连接（在 server 模式下自动启动）
  - feishu/card_actions.py 的 accept_any 模式
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
        "name": "ask_human_free",
        "description": (
            "向飞书群聊发送自由文本提示卡片，等待人类回复任意文字后返回。"
            "用于需要人类补充信息的追问场景（如缺失 Brief 信息）。"
            "与 ask_human 的区别：ask_human 是选择题（需提供选项），"
            "ask_human_free 是开放题（人类直接打字回复）。"
            "工具会阻塞等待人类响应，超时则返回提示。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "向人类提出的问题，支持 Markdown 格式，要清晰说明需要补充什么信息",
                },
                "title": {
                    "type": "string",
                    "description": "卡片标题，简短说明这是什么追问，默认「需要你的输入」",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": f"等待超时秒数，默认 {ASK_HUMAN_TIMEOUT} 秒",
                },
            },
            "required": ["question"],
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
            logger.warning("ask_human_free: polling list_messages failed: %s", exc)
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

            logger.info("ask_human_free: polling saw user reply text=%r", text)
            if resolve_by_message(chat_id, text):
                logger.info("ask_human_free: polling matched user reply")
                return


async def execute(params: dict, context: AgentContext) -> str:
    from feishu.im import FeishuIMClient
    from feishu.card_actions import register, cancel_wait

    question: str = (params.get("question") or "").strip()
    title: str = (params.get("title") or "需要你的输入").strip()
    timeout_sec: int = int(params.get("timeout_seconds") or ASK_HUMAN_TIMEOUT)

    if not question:
        return "错误: question 不能为空"
    if not FEISHU_CHAT_ID:
        return "错误: 未配置 FEISHU_CHAT_ID，无法发送卡片"

    im = FeishuIMClient()
    start_time_unix = str(max(0, int(time.time()) - 2))
    try:
        await im.send_prompt_card(
            chat_id=FEISHU_CHAT_ID,
            question=question,
            title=title,
        )
    except Exception as exc:
        logger.error("ask_human_free: 发送提示卡片失败: %s", exc)
        return f"发送提示卡片失败: {exc}"

    # accept_any=True：接受用户任意文本回复（非选项匹配）
    try:
        fut = register(FEISHU_CHAT_ID, [], accept_any=True)
    except RuntimeError as exc:
        return f"ask_human_free 不可用（未在 server 模式下运行）: {exc}"

    logger.info(
        "ask_human_free: 卡片已发出 chat_id=%s，等待用户回复（超时 %ds）...",
        FEISHU_CHAT_ID, timeout_sec,
    )
    poll_task = asyncio.create_task(_poll_for_reply(FEISHU_CHAT_ID, start_time_unix, timeout_sec))

    try:
        reply = await asyncio.wait_for(fut, timeout=timeout_sec)
        logger.info("ask_human_free: 收到回复 chat_id=%s reply=%r", FEISHU_CHAT_ID, reply)
        return f"人类回复：{reply}"
    except asyncio.TimeoutError:
        cancel_wait(FEISHU_CHAT_ID)
        return (
            f"等待超时（{timeout_sec} 秒），未收到用户回复。\n"
            "请使用调研数据或行业经验做默认推断，继续完成工作。"
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
