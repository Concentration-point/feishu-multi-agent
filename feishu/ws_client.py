"""飞书 WebSocket 长连接客户端 — 接收群消息并驱动 ask_human 选择解析。

使用 im.message.receive_v1（消息接收事件），通过 lark-oapi WebSocket 长连接。
无需公网 URL，无需配置「卡片行为触发」。

前置条件：
  1. pip install lark-oapi>=1.0.0
  2. 飞书开放平台 → 机器人 → 开启机器人功能
  3. 飞书开放平台 → 事件与回调 → 事件订阅：
       ① 接收事件方式选「使用长连接接收事件」
       ② 添加事件 → 搜索「接收消息」→ 订阅 im.message.receive_v1
  4. 飞书开放平台 → 权限管理 → 开通 im:message:readonly（读取消息）

运行模式：daemon 线程，lark-oapi 内部自动重连。
"""
import json
import logging
import threading

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
        try:
            import lark_oapi as lark

            handler = (
                lark.EventDispatcherHandler.builder("", "")
                .register_p2_im_message_receive_v1(_handle_message)
                .build()
            )
            cli = lark.ws.Client(
                FEISHU_APP_ID,
                FEISHU_APP_SECRET,
                event_handler=handler,
                log_level=lark.LogLevel.WARNING,
            )
            logger.info("飞书 WebSocket 长连接已建立，监听群消息...")
            cli.start()  # 内部自动重连，永久阻塞
        except ImportError:
            logger.error(
                "缺少依赖 lark-oapi，WebSocket 无法启动。"
                "请执行: pip install lark-oapi>=1.0.0"
            )
        except Exception:
            logger.exception("WebSocket 客户端异常退出")

    _ws_thread = threading.Thread(target=_run, daemon=True, name="feishu-ws-client")
    _ws_thread.start()
    logger.info("飞书 WebSocket daemon 线程已启动 (ident=%s)", _ws_thread.ident)


def is_alive() -> bool:
    return _ws_thread is not None and _ws_thread.is_alive()
