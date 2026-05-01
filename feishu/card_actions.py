"""飞书卡片问题注册表 — 桥接 WebSocket 事件与主 asyncio 循环。

双通道接收人类回复：
  1. card.action.trigger（按钮回调）—— 用户点击卡片按钮，通过 WebSocket 长连接接收
  2. im.message.receive_v1（消息接收）—— 用户在群里打字回复，正则匹配选项（兜底）

注册表 key = chat_id，value = deque 队列（支持批量多卡片场景）：
  - 单卡片：register() 创建只有 1 个 entry 的 deque
  - 多卡片：register_batch() 创建 N 个 entry 的 deque
  - 每次 resolve 消费队首 entry，队列清空后自动删除 chat_id 键

使用流程：
  1. lifespan 启动时调用 set_main_loop(asyncio.get_running_loop())
  2. ask_human 工具调用 register(chat_id, choices) 获取 Future 并 await
  3. WebSocket 线程收到 card.action.trigger → resolve_by_card_action(chat_id, action_value)
  4. 或收到 im.message.receive_v1 → resolve_by_message(chat_id, text) 兜底
"""
import asyncio
import logging
import re
from collections import deque

logger = logging.getLogger(__name__)

_main_loop: asyncio.AbstractEventLoop | None = None

_STRUCTURED_REPLY_TOKEN_RE = re.compile(r"\d+\s*[:：.\-]?\s*[A-Za-z0-9一-鿿]+")
_LETTER_SERIES_REPLY_RE = re.compile(
    r"^[A-Za-z](?:\s*[/,，、|｜\-]\s*[A-Za-z0-9一-鿿]+){2,}$"
)

# chat_id → deque([{"future": Future[str], "choices": list[str], "accept_any": bool}, ...])
_pending: dict[str, deque[dict]] = {}


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop
    logger.info("card_actions: 主 asyncio 循环已绑定")


def register(chat_id: str, choices: list[str], accept_any: bool = False) -> "asyncio.Future[str]":
    """注册一个等待用户回复的 Future（单卡片，向后兼容）。

    同一 chat_id 的新注册会取消旧队列中所有未完成的 Future。
    """
    if _main_loop is None:
        raise RuntimeError(
            "card_actions 未初始化，请在 lifespan 中调用 set_main_loop()"
        )
    # 取消旧队列中所有未完成的 Future
    _cancel_all_pending(chat_id)

    fut: asyncio.Future[str] = _main_loop.create_future()
    _pending[chat_id] = deque([{"future": fut, "choices": choices, "accept_any": accept_any}])
    logger.info(
        "card_actions: 注册 chat_id=%s choices=%s accept_any=%s 当前 pending keys=%s",
        chat_id, choices, accept_any, list(_pending.keys()),
    )
    return fut


def register_batch(chat_id: str, questions: list[dict]) -> list["asyncio.Future[str]"]:
    """批量注册多个等待用户回复的 Future（多卡片）。

    同一 chat_id 的新注册会取消旧队列中所有未完成的 Future。

    Args:
        chat_id: 群聊 ID
        questions: [{"choices": [...], "accept_any": bool}, ...]

    Returns:
        与 questions 等长的 Future 列表，按序对应每张卡片。
    """
    if _main_loop is None:
        raise RuntimeError(
            "card_actions 未初始化，请在 lifespan 中调用 set_main_loop()"
        )
    _cancel_all_pending(chat_id)

    futures: list[asyncio.Future[str]] = []
    entries: list[dict] = []
    for q in questions:
        fut: asyncio.Future[str] = _main_loop.create_future()
        entries.append({
            "future": fut,
            "choices": q.get("choices", []),
            "accept_any": q.get("accept_any", False),
        })
        futures.append(fut)

    _pending[chat_id] = deque(entries)
    logger.info(
        "card_actions: 批量注册 chat_id=%s 共 %d 个问题 当前 pending keys=%s",
        chat_id, len(questions), list(_pending.keys()),
    )
    return futures


def _cancel_all_pending(chat_id: str) -> None:
    """取消指定 chat_id 下所有未完成的 Future 并清理。

    注意：此函数在工具执行的主线程中调用（非 WebSocket 线程），直接 cancel 即可。
    """
    dq = _pending.get(chat_id)
    if not dq:
        return
    for entry in dq:
        fut = entry.get("future")
        if fut and not fut.done():
            fut.cancel()
    _pending.pop(chat_id, None)


def cancel_wait(chat_id: str) -> None:
    """取消指定 chat_id 下所有待处理 Future（整个队列）。"""
    _cancel_all_pending(chat_id)


def skip_current(chat_id: str) -> bool:
    """跳过队首未完成的 Future（批量场景中超时跳过当前题）。

    Returns True 如果成功跳过（队列还有剩余），False 如果队列已空。
    """
    dq = _pending.get(chat_id)
    if not dq:
        return False
    # 取消队首 Future（工具执行在主线程，直接 cancel）
    entry = dq[0]
    fut = entry.get("future")
    if fut and not fut.done():
        fut.cancel()
    dq.popleft()
    if not dq:
        _pending.pop(chat_id, None)
        return False
    return True


def _peek_front(chat_id: str) -> dict | None:
    """查看队首 entry，忽略已完成的 Future。"""
    dq = _pending.get(chat_id)
    while dq:
        entry = dq[0]
        fut: asyncio.Future = entry["future"]
        if fut.done():
            dq.popleft()
            if not dq:
                _pending.pop(chat_id, None)
                return None
            continue
        return entry
    return None


def resolve_by_card_action(chat_id: str, action_value) -> bool:
    """WebSocket 线程调用 — 处理 card.action.trigger 按钮回调，设置队首 Future。

    从按钮的 value 字段中提取 choice_index，映射到对应的选项文字。

    Returns True 如果匹配成功并设置了 Future。
    """
    entry = _peek_front(chat_id)
    if not entry:
        logger.warning(
            "card_actions: resolve_by_card_action chat_id=%r 未在 _pending 中找到活跃 entry，当前 keys=%r",
            chat_id, list(_pending.keys()),
        )
        return False
    fut: asyncio.Future = entry["future"]
    choices: list[str] = entry["choices"]

    # 兼容 dict 和 str 两种 value 格式
    idx: int | None = None
    if isinstance(action_value, dict):
        raw = action_value.get("choice_index")
        if isinstance(raw, int):
            idx = raw
        elif isinstance(raw, str) and raw.isdigit():
            idx = int(raw)
    elif isinstance(action_value, str):
        if action_value.isdigit():
            idx = int(action_value)

    if idx is None or idx < 0 or idx >= len(choices):
        logger.warning(
            "card_actions: card.action.trigger value=%r 无法映射到选项 choices=%s",
            action_value, choices,
        )
        return False

    choice = choices[idx]
    # 消费队首
    _pending[chat_id].popleft()
    if not _pending[chat_id]:
        _pending.pop(chat_id, None)
    if _main_loop:
        _main_loop.call_soon_threadsafe(fut.set_result, choice)
    logger.info(
        "card_actions: 按钮回调 chat_id=%s value=%r → choice=%r",
        chat_id, action_value, choice,
    )
    return True


def resolve_by_message(chat_id: str, text: str) -> bool:
    """WebSocket 线程调用 — 尝试用用户消息文本匹配选项并设置队首 Future。

    匹配优先级：
      1. 纯数字 "1"/"2"/"3" → 对应第 n 个选项（1-based）
      2. 文本与某选项完全匹配（大小写不敏感）
      3. 文本包含某选项文字

    Returns True 如果匹配成功并设置了 Future。
    """
    entry = _peek_front(chat_id)
    if not entry:
        return False
    fut: asyncio.Future = entry["future"]
    choices: list[str] = entry["choices"]

    stripped = text.strip()

    # accept_any 模式：直接接受用户任意文本（自由文本追问场景）
    if entry.get("accept_any"):
        _pending[chat_id].popleft()
        if not _pending[chat_id]:
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

    _pending[chat_id].popleft()
    if not _pending[chat_id]:
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
    for dq in list(_pending.values()):
        for entry in dq:
            fut = entry.get("future")
            if fut and not fut.done():
                fut.cancel()
    _pending.clear()
    logger.info("card_actions: 已取消所有待处理 Future")
