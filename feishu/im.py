"""飞书 IM 消息收发 — 文本 + 卡片 + 消息列表查询。"""

import json
import logging
from typing import Any

import httpx

from config import FEISHU_BASE_URL, IM_TIMEOUT_SECONDS
from feishu.auth import TokenManager
from feishu.bitable import FeishuAPIError

logger = logging.getLogger(__name__)

MESSAGES_URL = f"{FEISHU_BASE_URL}/im/v1/messages"


class FeishuIMClient:
    """飞书即时通讯消息发送客户端。"""

    def __init__(self, token_manager: TokenManager | None = None):
        self._tm = token_manager or TokenManager()

    async def _headers(self) -> dict[str, str]:
        token = await self._tm.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _check(resp: httpx.Response) -> dict:
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()
            raise FeishuAPIError(-1, f"HTTP {resp.status_code}, 响应非 JSON")
        code = data.get("code", -1)
        if resp.status_code != 200 or code != 0:
            msg = data.get("msg", "unknown")
            raise FeishuAPIError(
                code,
                f"HTTP {resp.status_code} | code={code} | {msg}",
            )
        return data

    async def send_text(self, chat_id: str, text: str) -> dict:
        """发送纯文本消息到群聊。"""
        headers = await self._headers()
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(IM_TIMEOUT_SECONDS)) as client:
            resp = await client.post(
                MESSAGES_URL, headers=headers, json=payload,
                params={"receive_id_type": "chat_id"},
            )
        data = self._check(resp)
        logger.info("send_text OK chat=%s len=%d", chat_id, len(text))
        return data

    async def send_text_return_id(self, chat_id: str, text: str) -> tuple[dict, str]:
        """发送纯文本消息并返回 (完整响应, message_id)。"""
        data = await self.send_text(chat_id, text)
        msg_id = data.get("data", {}).get("message_id", "")
        return data, msg_id

    async def list_messages(
        self,
        chat_id: str,
        start_time: str,
        end_time: str | None = None,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """获取群聊中指定时间范围内的消息列表。

        Args:
            chat_id: 群聊 ID
            start_time: 起始时间，Unix 时间戳（秒），字符串格式
            end_time: 结束时间，Unix 时间戳（秒），不传则用当前时间
            page_size: 每页条数，最大 50

        Returns:
            消息列表，每条含 message_id, sender, body, create_time 等
        """
        import time as _time

        if end_time is None:
            end_time = str(int(_time.time()))

        headers = await self._headers()
        params = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "start_time": start_time,
            "end_time": end_time,
            "page_size": str(page_size),
            "sort_type": "ByCreateTimeAsc",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(IM_TIMEOUT_SECONDS)) as client:
            resp = await client.get(MESSAGES_URL, headers=headers, params=params)
        data = self._check(resp)
        items = data.get("data", {}).get("items", [])
        logger.info("list_messages chat=%s start=%s count=%d", chat_id, start_time, len(items))
        return items

    @staticmethod
    def extract_text_from_message(msg: dict[str, Any]) -> str:
        """从飞书消息对象中提取纯文本内容。"""
        body = msg.get("body", {})
        content_str = body.get("content", "")
        if not content_str:
            return ""
        try:
            content = json.loads(content_str)
            return content.get("text", "")
        except (json.JSONDecodeError, TypeError):
            return content_str

    @staticmethod
    def is_user_message(msg: dict[str, Any]) -> bool:
        """判断消息是否由真人用户发送（非机器人）。"""
        sender = msg.get("sender", {})
        return sender.get("sender_type", "") == "user"

    async def send_card(
        self,
        chat_id: str,
        title: str,
        content: str,
        color: str = "blue",
    ) -> dict:
        """发送富文本卡片消息到群聊。

        Args:
            chat_id: 群聊 ID
            title: 卡片标题
            content: Markdown 格式正文
            color: 卡片颜色 blue/green/orange/red/purple
        """
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        }
        headers = await self._headers()
        payload = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(IM_TIMEOUT_SECONDS)) as client:
            resp = await client.post(
                MESSAGES_URL, headers=headers, json=payload,
                params={"receive_id_type": "chat_id"},
            )
        data = self._check(resp)
        logger.info("send_card OK chat=%s title=%s color=%s", chat_id, title, color)
        return data

    async def send_prompt_card(
        self,
        chat_id: str,
        question: str,
        title: str = "需要你的输入",
        color: str = "blue",
    ) -> tuple[dict, str]:
        """发送自由文本提示卡片（不带选项），返回 (完整响应, message_id)。

        用户在群聊中直接回复文字即可，ws_client 通过 card_actions 的
        accept_any 模式接收任意文本回复。

        Args:
            chat_id: 群聊 ID
            question: 问题正文，支持 Markdown
            title: 卡片标题
            color: 卡片主题色 blue/green/orange/red/purple
        """
        body = (
            f"{question}\n\n"
            f"---\n\n"
            f"**请在群聊中直接回复文字即可。**"
        )
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": [
                {"tag": "markdown", "content": body},
            ],
        }
        headers = await self._headers()
        payload = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(IM_TIMEOUT_SECONDS)) as client:
            resp = await client.post(
                MESSAGES_URL, headers=headers, json=payload,
                params={"receive_id_type": "chat_id"},
            )
        data = self._check(resp)
        msg_id = data.get("data", {}).get("message_id", "")
        logger.info(
            "send_prompt_card OK chat=%s title=%s msg_id=%s",
            chat_id, title, msg_id,
        )
        return data, msg_id

    async def send_card_return_id(
        self,
        chat_id: str,
        title: str,
        content: str,
        color: str = "blue",
    ) -> tuple[dict, str]:
        """发送卡片消息并返回 (完整响应, message_id)。"""
        data = await self.send_card(chat_id, title, content, color)
        msg_id = data.get("data", {}).get("message_id", "")
        return data, msg_id

    async def send_choice_card(
        self,
        chat_id: str,
        question: str,
        choices: list[str],
        title: str = "需要你的判断",
        color: str = "blue",
    ) -> tuple[dict, str]:
        """发送带按钮的交互式选择卡片，返回 (完整响应, message_id)。

        卡片包含真正的飞书按钮（action 组件），用户点击按钮后，
        ws_client 通过 card.action.trigger 事件接收回调并通知 ask_human 工具。
        同时保留文字回复兜底：用户在群里回复数字或选项文字依然生效。
        无需公网 URL，通过 WebSocket 长连接接收回调。

        Args:
            chat_id: 群聊 ID
            question: 问题正文，支持 Markdown
            choices: 选项列表（2-6 项）
            title: 卡片标题
            color: 卡片主题色 blue/green/orange/red/purple
        """
        # 构建按钮列表，value 用 JSON 对象编码选项索引
        button_styles = ["primary", "default", "danger", "default", "default", "default"]
        buttons = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": choice},
                "type": button_styles[i] if i < len(button_styles) else "default",
                "value": {"choice_index": i},
            }
            for i, choice in enumerate(choices)
        ]
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": [
                {"tag": "markdown", "content": question},
                {"tag": "hr"},
                {"tag": "note", "elements": [
                    {"tag": "plain_text",
                     "content": "💡 点击下方按钮选择，也可在群里回复数字或选项文字"}
                ]},
                {"tag": "action", "actions": buttons},
            ],
        }
        headers = await self._headers()
        payload = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(IM_TIMEOUT_SECONDS)) as client:
            resp = await client.post(
                MESSAGES_URL, headers=headers, json=payload,
                params={"receive_id_type": "chat_id"},
            )
        data = self._check(resp)
        msg_id = data.get("data", {}).get("message_id", "")
        logger.info(
            "send_choice_card OK chat=%s title=%s choices=%s msg_id=%s",
            chat_id, title, choices, msg_id,
        )
        return data, msg_id
