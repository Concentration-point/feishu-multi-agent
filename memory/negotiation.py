"""Agent 协商记忆层。

管理 Agent 之间的协商消息，支持提问/建议/接受/让步四种消息类型。
协商记录按项目维度存储，可在 prompt 中注入历史协商上下文。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Literal

NegotiationType = Literal["question", "proposal", "accept", "concede"]

# 消息类型中文标签（用于飞书/Dashboard 展示）
NEGOTIATION_TYPE_LABELS: dict[str, str] = {
    "question": "提问",
    "proposal": "建议",
    "accept": "接受",
    "concede": "让步",
}


@dataclass
class NegotiationMessage:
    """一条协商消息。"""
    sender_role: str        # 发送方角色 ID
    receiver_role: str      # 接收方角色 ID
    msg_type: str           # question / proposal / accept / concede
    content: str            # 消息正文
    round_num: int = 0      # 当前协商轮次
    timestamp: float = 0.0  # 时间戳

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return asdict(self)

    def format_display(self, role_names: dict[str, str] | None = None) -> str:
        """格式化为可读的展示文本。"""
        names = role_names or {}
        sender = names.get(self.sender_role, self.sender_role)
        receiver = names.get(self.receiver_role, self.receiver_role)
        label = NEGOTIATION_TYPE_LABELS.get(self.msg_type, self.msg_type)
        return f"[{sender} → {receiver}]（{label}）{self.content}"


@dataclass
class NegotiationRound:
    """一轮协商（包含发起方消息 + 回应方消息）。"""
    initiator_msg: NegotiationMessage
    responder_msg: NegotiationMessage | None = None
    resolved: bool = False

    def to_dict(self) -> dict:
        return {
            "initiator": self.initiator_msg.to_dict(),
            "responder": self.responder_msg.to_dict() if self.responder_msg else None,
            "resolved": self.resolved,
        }


class NegotiationManager:
    """管理单个项目的协商历史。

    用法：
        nm = NegotiationManager()
        nm.add_message(msg)
        context = nm.format_for_prompt()  # 注入到 Agent system prompt
    """

    def __init__(self):
        self._messages: list[NegotiationMessage] = []
        self._rounds: list[NegotiationRound] = []

    @property
    def messages(self) -> list[NegotiationMessage]:
        return list(self._messages)

    @property
    def rounds(self) -> list[NegotiationRound]:
        return list(self._rounds)

    def add_message(self, msg: NegotiationMessage) -> None:
        """添加一条协商消息。"""
        self._messages.append(msg)

    def start_round(self, initiator_msg: NegotiationMessage) -> NegotiationRound:
        """开启一轮协商。"""
        self.add_message(initiator_msg)
        rnd = NegotiationRound(initiator_msg=initiator_msg)
        self._rounds.append(rnd)
        return rnd

    def close_round(self, rnd: NegotiationRound, responder_msg: NegotiationMessage) -> None:
        """关闭一轮协商（写入回应消息并标记解决）。"""
        self.add_message(responder_msg)
        rnd.responder_msg = responder_msg
        rnd.resolved = responder_msg.msg_type in ("accept", "concede")

    def get_history_between(self, role_a: str, role_b: str) -> list[NegotiationMessage]:
        """获取两个角色之间的协商历史。"""
        return [
            m for m in self._messages
            if {m.sender_role, m.receiver_role} == {role_a, role_b}
        ]

    def format_for_prompt(self, role_names: dict[str, str] | None = None) -> str:
        """将全部协商历史格式化为可注入 prompt 的文本。"""
        if not self._messages:
            return ""
        lines = ["## 团队协商记录\n"]
        for msg in self._messages:
            lines.append(f"- {msg.format_display(role_names)}")
        return "\n".join(lines)

    def format_round_for_broadcast(self, rnd: NegotiationRound, role_names: dict[str, str] | None = None) -> str:
        """将一轮协商格式化为飞书广播文本。"""
        names = role_names or {}
        init = rnd.initiator_msg
        sender = names.get(init.sender_role, init.sender_role)
        receiver = names.get(init.receiver_role, init.receiver_role)
        label = NEGOTIATION_TYPE_LABELS.get(init.msg_type, init.msg_type)

        parts = [f"**{sender}** 向 **{receiver}** 发起{label}：\n> {init.content}"]

        if rnd.responder_msg:
            resp = rnd.responder_msg
            resp_name = names.get(resp.sender_role, resp.sender_role)
            resp_label = NEGOTIATION_TYPE_LABELS.get(resp.msg_type, resp.msg_type)
            parts.append(f"\n**{resp_name}** 回应（{resp_label}）：\n> {resp.content}")
            if rnd.resolved:
                parts.append("\n✅ 已达成共识")
            else:
                parts.append("\n⏳ 待进一步协商")

        return "\n".join(parts)

    def to_dict_list(self) -> list[dict]:
        """序列化全部消息。"""
        return [m.to_dict() for m in self._messages]
