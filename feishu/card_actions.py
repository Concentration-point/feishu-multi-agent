"""飞书卡片问题注册表 — 桥接 WebSocket 消息事件与主 asyncio 循环。

架构说明：
  - card.action.trigger（按钮回调）需要公网 URL，本模块不使用。
  - 改用 im.message.receive_v1（消息接收事件），通过 WebSocket 长连接收取，
    解析用户的数字回复（"1"/"2"/"3"或完整选项文字）作为选择结果。
  - 注册表 key = chat_id（同一群同一时刻只允许一个待处理问题）。

使用流程：
  1. lifespan 启动时调用 set_main_loop(asyncio.get_running_loop())
  2. ask_human 工具调用 register(chat_id, choices) 获取 Future 并 await
  3. WebSocket 线程收到用户消息后调用 resolve_by_message(chat_id, text)
  4. 若 text 匹配某个选项，Future 被设置，await 侧收到选择文字
"""
import asyncio
import logging
import re

logger = logging.getLogger(__name__)

_main_loop: asyncio.AbstractEventLoop | None = None

_STRUCTURED_REPLY_TOKEN_RE = re.compile(r"\d+\s*[:：.\-]?\s*[A-Za-z0-9\u4e00-\u9fff]+")
_LETTER_SERIES_REPLY_RE = re.compile(
    r"^[A-Za-z](?:\s*[/,，、|｜\-]\s*[A-Za-z0-9\u4e00-\u9fff]+){2,}$"
)

# chat_id → {"future": Future[str], "choices": list[str], "accept_any": bool}
_pending: dict[str, dict] = {}


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop
    logger.info("card_actions: 主 asyncio 循环已绑定")


def register(chat_id: str, choices: list[str], accept_any: bool = False) -> "asyncio.Future[str]":
    """注册一个等待用户回复的 Future。

    同一 chat_id 只允许一个未完成的问题；新注册会取消旧的。

    Args:
        accept_any: True 时跳过选项匹配，直接接受用户任意文本回复（用于自由文本追问）。
    """
    if _main_loop is None:
        raise RuntimeError(
            "card_actions 未初始化，请在 lifespan 中调用 set_main_loop()"
        )
    # 取消旧的（如果有）
    old = _pending.get(chat_id)
    if old and not old["future"].done():
        _main_loop.call_soon_threadsafe(old["future"].cancel)

    fut: asyncio.Future[str] = _main_loop.create_future()
    _pending[chat_id] = {"future": fut, "choices": choices, "accept_any": accept_any}
    logger.debug("card_actions: 注册 chat_id=%s choices=%s accept_any=%s", chat_id, choices, accept_any)
    return fut


def cancel_wait(chat_id: str) -> None:
    """超时或取消时清理注册表。"""
    _pending.pop(chat_id, None)


def resolve_by_message(chat_id: str, text: str) -> bool:
    """WebSocket 线程调用 — 尝试用用户消息文本匹配选项并设置 Future。

    匹配优先级：
      1. 纯数字 "1"/"2"/"3" → 对应第 n 个选项（1-based）
      2. 文本与某选项完全匹配（大小写不敏感）
      3. 文本包含某选项文字

    Returns True 如果匹配成功并设置了 Future。
    """
    entry = _pending.get(chat_id)
    if not entry:
        return False
    fut: asyncio.Future = entry["future"]
    choices: list[str] = entry["choices"]
    if fut.done():
        _pending.pop(chat_id, None)
        return False

    stripped = text.strip()

    # accept_any 模式：直接接受用户任意文本（自由文本追问场景）
    if entry.get("accept_any"):
        _pending.pop(chat_id, None)
        if _main_loop:
            _main_loop.call_soon_threadsafe(fut.set_result, stripped)
        logger.info("card_actions: accept_any 匹配 chat_id=%s text=%r", chat_id, stripped)
        return True

    choice: str | None = None

    # 数字匹配
    if stripped.isdigit():
        idx = int(stripped) - 1
        if 0 <= idx < len(choices):
            choice = choices[idx]

    # 文本匹配
    if choice is None:
        lower = stripped.lower()
        for c in choices:
            if c.lower() == lower:
                choice = c
                break

    # 结构化多题回复兜底，例如 "1B, 2D, 3C, 4A"
    # 这类回复不属于单选选项，但仍然是 ask_human 需要的人类答案。
    if choice is None:
        tokens = _STRUCTURED_REPLY_TOKEN_RE.findall(stripped)
        if len(tokens) >= 2:
            choice = stripped

    # 兼容按 A/B/C 逐项回复，例如 "A/B/C/B/C"
    if choice is None and _looks_like_stepwise_reply(choices, stripped):
        choice = stripped

    # 包含匹配（最后兜底）
    if choice is None:
        lower = stripped.lower()
        for c in choices:
            if c.lower() in lower:
                choice = c
                break

    if choice is None:
        return False

    _pending.pop(chat_id, None)
    if _main_loop:
        _main_loop.call_soon_threadsafe(fut.set_result, choice)
    logger.info("card_actions: 匹配成功 chat_id=%s text=%r → choice=%r", chat_id, stripped, choice)
    return True


def _looks_like_stepwise_reply(choices: list[str], text: str) -> bool:
    """Allow structured free-form replies when the card explicitly asked for stepwise A/B/C answers."""
    normalized_choices = [c.strip().lower() for c in choices]
    asked_for_stepwise_reply = any(
        ("逐项回复" in c) or ("按 a/b/c" in c) or ("按a/b/c" in c)
        for c in normalized_choices
    )
    if not asked_for_stepwise_reply:
        return False
    return bool(_LETTER_SERIES_REPLY_RE.fullmatch(text.strip()))


def shutdown() -> None:
    for entry in list(_pending.values()):
        fut = entry.get("future")
        if fut and not fut.done() and _main_loop:
            _main_loop.call_soon_threadsafe(fut.cancel)
    _pending.clear()
    logger.info("card_actions: 已取消所有待处理 Future")
