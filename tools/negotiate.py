"""工具: Agent 协商 — 向其他角色发起结构化协商消息。

Agent 可通过此工具向上游/下游角色提问、提建议，系统会模拟目标角色的回应。
协商过程实时广播到飞书群聊和 Dashboard，营造虚拟团队讨论的互动画面。
"""

import logging
from tools import AgentContext
from agents.base import load_soul_snippet
from config import FEISHU_CHAT_ID, ROLE_NAMES

logger = logging.getLogger(__name__)

# 可协商的目标角色列表
_VALID_TARGETS = list(ROLE_NAMES.keys())

SCHEMA = {
    "type": "function",
    "function": {
        "name": "negotiate",
        "description": (
            "向团队中的其他角色发起协商。可以提问、提建议或表达接受/让步。"
            "协商消息会广播给全团队，目标角色会基于自身专业立场回应。"
            "适用场景：对上游产出有疑问、想提修改建议、需要跨角色确认信息。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_role": {
                    "type": "string",
                    "enum": _VALID_TARGETS,
                    "description": "目标角色 ID（你想和谁协商）",
                },
                "message_type": {
                    "type": "string",
                    "enum": ["question", "proposal", "accept", "concede"],
                    "description": (
                        "协商类型：question=提问, proposal=建议, "
                        "accept=接受对方观点, concede=让步妥协"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "协商内容，需具体明确，说明原因和期望",
                },
            },
            "required": ["target_role", "message_type", "content"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    target_role = params.get("target_role", "")
    msg_type = params.get("message_type", "question")
    content = params.get("content", "")

    if not content.strip():
        return "错误: 协商内容不能为空"

    if target_role not in ROLE_NAMES:
        return f"错误: 无效的目标角色 '{target_role}'，可选: {list(ROLE_NAMES.keys())}"

    if target_role == context.role_id:
        return "错误: 不能和自己协商"

    sender_name = ROLE_NAMES.get(context.role_id, context.role_id)
    target_name = ROLE_NAMES.get(target_role, target_role)

    type_labels = {
        "question": "提问",
        "proposal": "建议",
        "accept": "接受",
        "concede": "让步",
    }
    label = type_labels.get(msg_type, msg_type)

    # 广播到飞书群聊
    broadcast_text = (
        f"**{sender_name}** 向 **{target_name}** 发起{label}：\n\n"
        f"> {content}"
    )
    await _broadcast_negotiation(
        title=f"💬 团队协商 — {sender_name} → {target_name}",
        content=broadcast_text,
        color="purple",
    )

    # 生成目标角色的回应（基于其 soul 人格）
    response = await _generate_response(
        sender_role=context.role_id,
        target_role=target_role,
        msg_type=msg_type,
        content=content,
        project_name=context.project_name,
    )

    # 广播回应
    await _broadcast_negotiation(
        title=f"💬 {target_name} 回应",
        content=f"**{target_name}** 回应 **{sender_name}**：\n\n> {response}",
        color="blue",
    )

    return (
        f"[协商结果] {target_name} 回应：\n{response}\n\n"
        f"（如需继续协商，可再次调用 negotiate 工具）"
    )


async def _generate_response(
    *,
    sender_role: str,
    target_role: str,
    msg_type: str,
    content: str,
    project_name: str,
) -> str:
    """调用 LLM 模拟目标角色回应协商消息。"""
    from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT_SECONDS
    from openai import AsyncOpenAI

    sender_name = ROLE_NAMES.get(sender_role, sender_role)
    target_name = ROLE_NAMES.get(target_role, target_role)

    # 加载目标角色的 soul.md 作为人格
    soul_context = load_soul_snippet(target_role)

    type_labels = {"question": "提问", "proposal": "建议", "accept": "接受", "concede": "让步"}
    label = type_labels.get(msg_type, msg_type)

    system_prompt = (
        f"你是内容营销团队的{target_name}。{soul_context}\n\n"
        f"现在 {sender_name} 向你发起了一个{label}，你需要基于自己的专业立场回应。\n\n"
        "回应原则：\n"
        "- 用第一人称回应，保持你的角色人格\n"
        "- 如果对方说得有道理，直接接受并说明如何调整\n"
        "- 如果你有不同看法，给出专业理由\n"
        "- 保持简洁，不超过 150 字\n"
        "- 用协作口吻，避免对抗性语言"
    )

    user_prompt = (
        f"项目: {project_name}\n\n"
        f"{sender_name}（{label}）：{content}\n\n"
        f"请以{target_name}的身份回应："
    )

    try:
        client = AsyncOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        resp = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip() or "（回应生成失败）"
    except Exception as e:
        logger.warning("协商回应生成失败: %s", e)
        return f"（{target_name}暂时无法回应: {type(e).__name__}）"




async def _broadcast_negotiation(title: str, content: str, color: str) -> None:
    """广播协商消息到飞书群聊。"""
    try:
        print(f"[协商广播] {title}: {content[:100]}")
    except UnicodeEncodeError:
        print(f"[negotiate] broadcast: {title[:30]}")

    if not FEISHU_CHAT_ID:
        return

    try:
        from feishu.im import FeishuIMClient
        im = FeishuIMClient()
        await im.send_card(FEISHU_CHAT_ID, title, content, color)
    except Exception as exc:
        logger.warning("协商广播失败: %s", exc)
