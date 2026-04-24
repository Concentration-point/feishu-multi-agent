"""L0 工作记忆工具。

给 BaseAgent / Orchestrator 提供轻量上下文拼接、消息裁剪和粗略 token 统计。
不依赖外部库，够用就行。

关键设计（MessageWindow）：
- 保留所有 system messages（不能丢，里面有角色 prompt + 经验注入）
- 其他消息按 "assistant + 紧跟的 tool messages" 为一组整体保留或丢弃
  避免 OpenAI function calling 的 assistant(tool_calls)/tool 成对约束被切碎
- 超预算时从最早的对话组开始丢弃
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


def estimate_tokens(text: str) -> int:
    """Token 估算（中英分治，接近真实 cl100k_base tokenizer）。

    经验值：
      - ASCII 字符: 约 0.25 tokens/char (4 字符 ≈ 1 token)
      - 非 ASCII（中文/日文等）: 约 1.2 tokens/char
        * 常见汉字 1 token, 少见字 2 tokens, 平均偏保守取 1.2
    估算用于窗口保护，**略偏保守**（宁可早裁也别炸 LLM 上下文）。
    """
    if not text:
        return 0
    ascii_count = 0
    cjk_count = 0
    for ch in text:
        if ord(ch) < 128:
            ascii_count += 1
        else:
            cjk_count += 1
    return max(1, ascii_count // 4 + int(cjk_count * 1.2))


def join_prompt_sections(sections: Iterable[str], separator: str = "\n\n---\n\n") -> str:
    """拼接 prompt 段落，自动跳过空白段。"""
    cleaned = [section.strip() for section in sections if section and section.strip()]
    return separator.join(cleaned)


def _message_tokens(message: dict) -> int:
    """估算单条 message 的 token 占用（含 content + tool_calls 结构）。"""
    if not isinstance(message, dict):
        return 0
    total = 0
    content = message.get("content")
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif isinstance(content, list):
        # function calling 的 content 偶尔是 list of dict
        total += estimate_tokens(str(content))
    elif content is not None:
        total += estimate_tokens(str(content))

    # tool_calls 结构本身也占 token（arguments 可能很长）
    tool_calls = message.get("tool_calls") or []
    for tc in tool_calls:
        if isinstance(tc, dict):
            fn = tc.get("function") or {}
            total += estimate_tokens(str(fn.get("name", "")))
            total += estimate_tokens(str(fn.get("arguments", "")))
    return total


def _group_by_turn(messages: list[dict]) -> list[list[dict]]:
    """把非 system messages 按"对话回合"分组。

    一个回合 = 一条 assistant + 紧跟的 tool messages
             或 一条 user message（单独一组）
             或 一条孤立 assistant（没有 tool_calls，也单独一组）

    这样裁剪时可以整组丢弃，保证 assistant.tool_calls 和 tool.tool_call_id 永远成对。
    """
    groups: list[list[dict]] = []
    current: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            continue  # system 不进组
        if role in ("user",):
            # user 是新回合起点，先把上一组收尾
            if current:
                groups.append(current)
                current = []
            groups.append([msg])
        elif role == "assistant":
            # assistant 是新回合起点
            if current:
                groups.append(current)
            current = [msg]
        elif role == "tool":
            # tool 追随当前 assistant
            if not current or current[0].get("role") != "assistant":
                # 孤儿 tool（理论不该出现），单独成组避免丢失
                groups.append([msg])
            else:
                current.append(msg)
        else:
            # 其他 role（function/developer 等），单独成组
            if current:
                groups.append(current)
                current = []
            groups.append([msg])
    if current:
        groups.append(current)
    return groups


@dataclass
class MessageWindow:
    """维护一段对话窗口，避免 messages 无限变胖。

    用法：
        window = MessageWindow(max_tokens=40000, reserve_tokens=4000)
        window.append({"role": "system", "content": ...})
        window.append({"role": "user", "content": ...})
        ...
        window.trim()   # 每轮 LLM 调用前 trim 一次
        response = await llm.chat.completions.create(messages=window.messages, ...)
    """

    max_tokens: int = 40000
    reserve_tokens: int = 4000
    messages: list[dict] = field(default_factory=list)

    def append(self, message: dict) -> None:
        self.messages.append(message)

    def extend(self, items: Iterable[dict]) -> None:
        for item in items:
            self.messages.append(item)

    def total_tokens(self) -> int:
        return sum(_message_tokens(m) for m in self.messages)

    def trim(self) -> list[dict]:
        """超预算时按回合组整体丢弃最早的对话，保证 assistant/tool 成对。

        - system messages 全部保留
        - 非 system 按 _group_by_turn 分组
        - 从最早的组开始丢弃，直到 total <= budget
        - 永远至少保留最新的一组（避免把 LLM 要响应的消息也丢了）
        """
        budget = max(0, self.max_tokens - self.reserve_tokens)

        system_messages = [m for m in self.messages if m.get("role") == "system"]
        non_system = [m for m in self.messages if m.get("role") != "system"]

        def _total(msgs: list[dict]) -> int:
            return sum(_message_tokens(m) for m in msgs)

        if _total(self.messages) <= budget:
            return self.messages

        groups = _group_by_turn(non_system)
        if not groups:
            return self.messages

        # 从最早的 group 开始丢，留下至少 1 组
        system_cost = _total(system_messages)
        while len(groups) > 1:
            current_total = system_cost + sum(_total(g) for g in groups)
            if current_total <= budget:
                break
            groups.pop(0)

        self.messages = system_messages + [msg for group in groups for msg in group]
        return self.messages
