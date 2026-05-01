"""飞书 WebSocket 长连接客户端 — 接收群消息 + 卡片按钮点击，驱动 ask_human。

订阅事件：
  - im.message.receive_v1（消息接收）→ 文字回复兜底
  - card.action.trigger（卡片按钮点击）→ 按钮回调（主要通道）

使用 lark-oapi 长连接，无需公网 URL。

前置条件：
  1. pip install lark-oapi>=1.0.0
  2. 飞书开放平台 → 机器人 → 开启机器人功能
  3. 飞书开放平台 → 事件与回调 → 事件订阅：
       ① 接收事件方式选「使用长连接接收事件」
       ② 添加事件 → 订阅 im.message.receive_v1（接收消息）
       ③ 添加事件 → 订阅 card.action.trigger（卡片交互）
  4. 飞书开放平台 → 权限管理 → 开通 im:message:readonly
"""
import json
import logging
import threading
import time

from config import FEISHU_APP_ID, FEISHU_APP_SECRET

logger = logging.getLogger(__name__)

_ws_thread: threading.Thread | None = None


def _extract_text(content_str: str) -> str:
    """从飞书消息 content 字段提取纯文本（兼容 text/post 等消息类型）。"""
    try:
        content = json.loads(content_str)
        # 文本消息
        if "text" in content:
            return content["text"].strip()
        # 富文本 (post)
        if "content" in content:
            parts = []
            for line in content["content"]:
                for seg in line:
                    if seg.get("tag") == "text":
                        parts.append(seg.get("text", ""))
            return "".join(parts).strip()
    except Exception:
        pass
    return content_str.strip()


def _handle_card_action(data) -> None:
    """处理 card.action.trigger 事件，将按钮点击转发给 card_actions。

    返回 P2CardActionTriggerResponse 以给用户弹窗反馈。
    """
    from lark_oapi.event.callback.model.p2_card_action_trigger import (
        P2CardActionTriggerResponse,
        CallBackToast,
    )
    from feishu.card_actions import resolve_by_card_action

    result = P2CardActionTriggerResponse()
    result.toast = CallBackToast()
    result.toast.type = "info"
    result.toast.content = "已收到选择"

    try:
        if hasattr(data, "event"):
            ev = data.event
            action = getattr(ev, "action", None)
            ctx = getattr(ev, "context", None)
            chat_id: str = getattr(ctx, "open_chat_id", "") or "" if ctx else ""
            action_value = getattr(action, "value", None) if action else None
        else:
            ev = data.get("event", {})
            action = ev.get("action", {})
            ctx = ev.get("context", {})
            chat_id = (ctx or {}).get("open_chat_id", "")
            action_value = action.get("value") if isinstance(action, dict) else None

        logger.info(
            "ws_client: card.action.trigger 收到 chat_id=%r action_value=%r type=%s",
            chat_id, action_value, type(action_value).__name__,
        )

        if not chat_id:
            logger.warning("ws_client: card.action.trigger 缺少 open_chat_id，event=%s", ev)
            return result

        resolved = resolve_by_card_action(chat_id, action_value)
        if resolved:
            logger.info("ws_client: card.action.trigger chat_id=%s 按钮回调已匹配 ✓", chat_id)
            result.toast.content = "已收到选择 ✓"
        else:
            from feishu.card_actions import _pending
            logger.warning(
                "ws_client: resolve_by_card_action 返回 False，chat_id=%r 不在 _pending keys=%r 中",
                chat_id, list(_pending.keys()),
            )

    except Exception:
        logger.exception("ws_client: card.action.trigger 处理异常")

    return result


def _handle_message(data) -> None:
    """处理 im.message.receive_v1 事件，将用户回复文字转发给 card_actions。"""
    from feishu.card_actions import resolve_by_message

    try:
        # lark-oapi 可能传入对象或 dict，兼容处理
        if hasattr(data, "event"):
            ev = data.event
            msg = getattr(ev, "message", None)
            sender = getattr(ev, "sender", None)
            chat_id: str = getattr(msg, "chat_id", "") or ""
            content_str: str = getattr(msg, "content", "") or ""
            # 过滤机器人自己的消息
            sender_type: str = getattr(getattr(sender, "sender_id", None), "id_type", "") or ""
            if sender_type == "app":
                return
        else:
            ev = data.get("event", {})
            msg = ev.get("message", {})
            chat_id = msg.get("chat_id", "")
            content_str = msg.get("content", "")
            sender = ev.get("sender", {})
            if sender.get("sender_type") == "app":
                return

        if not chat_id or not content_str:
            return

        text = _extract_text(content_str)
        if not text:
            return

        resolved = resolve_by_message(chat_id, text)
        if resolved:
            logger.info("ws_client: chat_id=%s 用户回复已匹配选项", chat_id)

    except Exception:
        logger.exception("ws_client: 消息处理异常")


def _patch_lark_oapi_card_support() -> None:
    """Monkey-patch lark-oapi SDK：修复 WebSocket 长连接不处理 CARD 消息的问题。

    lark-oapi v1.5.3 的 _handle_data_frame 对 MessageType.CARD 直接 return，
    导致 card.action.trigger 事件不被分发给注册的 handler。此 patch 让 CARD
    消息也走 EventDispatcherHandler.do_without_validation，使 card.action.trigger
    handler 能被正常调用并返回响应。

    注意：必须在子线程中调用（不能在主线程导入 lark_oapi，因为 SDK 在模块加载时
    调用 asyncio.get_event_loop() 捕获主线程 loop，导致子线程 start() 报
    RuntimeError: This event loop is already running）。
    """
    import base64
    from http import HTTPStatus
    import lark_oapi as lark
    from lark_oapi.ws.client import (
        HEADER_BIZ_RT, HEADER_MESSAGE_ID, HEADER_SEQ, HEADER_SUM,
        HEADER_TRACE_ID, HEADER_TYPE, UTF_8,
        Frame, MessageType, Response,
        _get_by_key,
    )
    from lark_oapi.core.json import JSON as LarkJSON

    _original = lark.ws.Client._handle_data_frame  # noqa: F841

    async def _patched_handle_data_frame(self, frame: Frame):
        hs = frame.headers
        msg_id = _get_by_key(hs, HEADER_MESSAGE_ID)
        trace_id = _get_by_key(hs, HEADER_TRACE_ID)
        sum_ = _get_by_key(hs, HEADER_SUM)
        seq = _get_by_key(hs, HEADER_SEQ)
        type_ = _get_by_key(hs, HEADER_TYPE)

        pl = frame.payload
        if int(sum_) > 1:
            pl = self._combine(msg_id, int(sum_), int(seq), pl)
            if pl is None:
                return

        message_type = MessageType(type_)
        logger.debug(
            "ws_client: receive message_type=%s msg_id=%s trace_id=%s",
            message_type.value, msg_id, trace_id,
        )

        resp = Response(code=HTTPStatus.OK)
        try:
            start = int(round(time.time() * 1000))
            if message_type == MessageType.EVENT:
                result = self._event_handler.do_without_validation(pl)
            elif message_type == MessageType.CARD:
                # ── PATCH: 原 SDK 此处直接 return，导致 card.action.trigger 丢失 ──
                result = self._event_handler.do_without_validation(pl)
            else:
                return
            end = int(round(time.time() * 1000))
            header = hs.add()
            header.key = HEADER_BIZ_RT
            header.value = str(end - start)
            if result is not None:
                resp.data = base64.b64encode(
                    LarkJSON.marshal(result).encode(UTF_8)
                )
        except Exception as e:
            logger.error(
                "ws_client: handle message failed, message_type=%s msg_id=%s err=%s",
                message_type.value, msg_id, e,
            )
            resp = Response(code=HTTPStatus.INTERNAL_SERVER_ERROR)

        frame.payload = LarkJSON.marshal(resp).encode(UTF_8)
        await self._write_message(frame.SerializeToString())

    lark.ws.Client._handle_data_frame = _patched_handle_data_frame
    logger.info("ws_client: 已打 lark-oapi CARD 消息处理补丁")


def start() -> None:
    """在 daemon 线程中启动 WebSocket 长连接，立即返回（非阻塞）。"""
    global _ws_thread

    if _ws_thread and _ws_thread.is_alive():
        logger.debug("WebSocket 客户端已在运行")
        return

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logger.warning("FEISHU_APP_ID/SECRET 未配置，WebSocket 客户端不启动")
        return

    def _run() -> None:
        import lark_oapi as lark

        try:
            _patch_lark_oapi_card_support()
        except Exception:
            logger.exception("ws_client: patch 失败")
            return

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(_handle_message)
            .register_p2_card_action_trigger(_handle_card_action)
            .build()
        )
        cli = lark.ws.Client(
            FEISHU_APP_ID,
            FEISHU_APP_SECRET,
            event_handler=handler,
            log_level=lark.LogLevel.WARNING,
        )
        logger.info("飞书 WebSocket 长连接已建立，监听群消息 + 卡片按钮回调...")
        try:
            cli.start()  # 内部自动重连，永久阻塞
        except Exception:
            logger.exception("ws_client: cli.start() 异常退出")

    _ws_thread = threading.Thread(target=_run, daemon=True, name="feishu-ws-client")
    _ws_thread.start()
    logger.info("飞书 WebSocket daemon 线程已启动 (ident=%s)", _ws_thread.ident)


def is_alive() -> bool:
    return _ws_thread is not None and _ws_thread.is_alive()
