"""工具: 将 Brief 解读提交给人类专家审核，阻塞等待回复。

流程：发送审核卡片到群聊 → 轮询新消息 → 解析人类回复 → 返回审核结果。
支持 AUTO_APPROVE 模式跳过真人审核（Demo 快速跑通）。
"""

import asyncio
import json
import logging
import time

from tools import AgentContext
from config import (
    AUTO_APPROVE_HUMAN_REVIEW,
    FEISHU_CHAT_ID,
    HUMAN_REVIEW_POLL_INTERVAL,
    HUMAN_REVIEW_TIMEOUT,
)

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "request_human_review",
        "description": (
            "将 Brief 解读提交给人类专家审核，获取修改建议。"
            "工具会发送审核请求到群聊并等待人类回复，"
            "回复「通过」表示认可，回复「修改：xxx」提出修改意见。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "brief_analysis": {
                    "type": "string",
                    "description": "你生成的 Brief 解读全文",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "等待人类回复的超时时间（秒），默认使用系统配置",
                },
            },
            "required": ["brief_analysis"],
        },
    },
}

# ── 审核回复解析关键词 ──
_APPROVE_KEYWORDS = {"通过", "approved", "ok", "lgtm", "没问题", "可以"}
_MODIFY_PREFIXES = ["修改：", "修改:", "修改 ", "revise:", "revise："]
# 用于判断非引用消息是否是审核回复（而非闲聊）
_REVIEW_SIGNAL_KEYWORDS = _APPROVE_KEYWORDS | {"修改", "revise", "不行", "重做", "调整", "建议"}


def _is_reply_to(msg: dict, target_msg_id: str) -> bool:
    """判断消息是否是对 target_msg_id 的引用回复（thread reply）。"""
    if not target_msg_id:
        return False
    return (
        msg.get("root_id") == target_msg_id
        or msg.get("parent_id") == target_msg_id
    )


def _looks_like_review(text: str) -> bool:
    """判断文本是否像审核回复（含审核关键词），用于过滤群聊闲聊噪音。"""
    lower = text.strip().lower()
    return any(kw in lower for kw in _REVIEW_SIGNAL_KEYWORDS)


def _parse_review_reply(text: str) -> tuple[str, str]:
    """解析人类回复，返回 (状态, 意见)。

    状态: "通过" | "需要修改" | None(无法识别)
    调用方保证 text 已经通过了 _is_reply_to 或 _looks_like_review 校验。
    """
    stripped = text.strip()
    lower = stripped.lower()

    # 检查是否为通过
    if lower in _APPROVE_KEYWORDS or any(kw in lower for kw in _APPROVE_KEYWORDS):
        return "通过", stripped

    # 检查是否为修改意见（带前缀）
    for prefix in _MODIFY_PREFIXES:
        if stripped.startswith(prefix):
            feedback = stripped[len(prefix):].strip()
            return "需要修改", feedback

    # 含修改信号关键词但无前缀 → 整段文本作为修改意见
    if _looks_like_review(stripped):
        return "需要修改", stripped

    # 无法识别为审核回复
    return None, ""


def _format_result(status: str, feedback: str) -> str:
    """格式化审核结果为工具返回字符串。"""
    if status == "通过":
        return (
            "人类审核结果：\n"
            f"状态：通过\n"
            f"意见：{feedback or '解读准确，可以进入下一阶段。'}\n\n"
            "请根据以上结果继续后续流程。"
        )
    return (
        "人类审核结果：\n"
        f"状态：需要修改\n"
        f"修改意见：{feedback}\n\n"
        "请根据以上意见重新生成 Brief 解读。"
    )


def _build_review_card_content(brief_analysis: str, role_name: str) -> str:
    """构造审核请求卡片正文。"""
    # 截断过长的分析内容，卡片正文有长度限制
    truncated = brief_analysis[:3000]
    if len(brief_analysis) > 3000:
        truncated += "\n\n... (内容过长已截断)"

    return (
        f"**{role_name}** 已完成 Brief 解读，请审核以下内容：\n\n"
        f"---\n\n"
        f"{truncated}\n\n"
        f"---\n\n"
        f"**请在群聊中回复：**\n"
        f"- 回复 **通过** → 确认解读准确\n"
        f"- 回复 **修改：你的修改意见** → 提出具体修改建议"
    )


async def poll_for_human_reply(
    brief_analysis: str,
    *,
    previous_msg_id: str | None = None,
    timeout: int | None = None,
) -> dict:
    """Orchestrator 使用的人审轮询 helper。

    超时语义翻转：不再默认通过，而是返回 status="timeout" 由编排器决定挂起。
    返回结构：
        {
          "status": "approved" | "need_revise" | "timeout"
                    | "skipped_auto_approve" | "skipped_no_chat"
                    | "send_failed",
          "feedback": str,          # 人类反馈原话 / 降级说明
          "msg_id": str,            # 本次发送的卡片 msg_id（失败或跳过时为空）
          "deadline": int,          # Unix 秒，本轮轮询截止时间
          "sent_at": str,           # ISO 时间字符串
        }
    """
    import datetime as _dt

    wait_sec = int(timeout if timeout is not None else HUMAN_REVIEW_TIMEOUT)
    now = int(time.time())
    deadline = now + wait_sec
    sent_at_iso = _dt.datetime.fromtimestamp(now).isoformat(timespec="seconds")

    if not (brief_analysis or "").strip():
        return {
            "status": "need_revise",
            "feedback": "Brief 解读为空，请先生成完整解读再提交人审。",
            "msg_id": "",
            "deadline": deadline,
            "sent_at": sent_at_iso,
        }

    if AUTO_APPROVE_HUMAN_REVIEW:
        logger.info("[human_review] AUTO_APPROVE 模式，模拟人类批准")
        return {
            "status": "skipped_auto_approve",
            "feedback": "[AUTO_APPROVE] 模拟人类批准。",
            "msg_id": "",
            "deadline": deadline,
            "sent_at": sent_at_iso,
        }

    if not FEISHU_CHAT_ID:
        logger.warning("[human_review] 未配置 FEISHU_CHAT_ID，跳过人审")
        return {
            "status": "skipped_no_chat",
            "feedback": "[未配置群聊] 无法发起人审，视为跳过。",
            "msg_id": "",
            "deadline": deadline,
            "sent_at": sent_at_iso,
        }

    try:
        from feishu.im import FeishuIMClient

        im = FeishuIMClient()
        card_content = _build_review_card_content(brief_analysis, "客户经理")
        _, msg_id = await im.send_card_return_id(
            FEISHU_CHAT_ID,
            "🔍 Brief 解读等待审核",
            card_content,
            "orange",
        )
        send_time = str(now)
        logger.info(
            "[human_review] 审核卡片已发送 msg_id=%s, 等待回复 (timeout=%ds)",
            msg_id, wait_sec,
        )
    except Exception as exc:
        logger.warning("[human_review] 发送审核卡片失败: %s", exc)
        return {
            "status": "send_failed",
            "feedback": f"[发送失败] {exc}",
            "msg_id": "",
            "deadline": deadline,
            "sent_at": sent_at_iso,
        }

    elapsed = 0
    poll_interval = HUMAN_REVIEW_POLL_INTERVAL
    while elapsed < wait_sec:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        try:
            messages = await im.list_messages(
                chat_id=FEISHU_CHAT_ID,
                start_time=send_time,
            )
            for msg in messages:
                if not im.is_user_message(msg):
                    continue
                text = im.extract_text_from_message(msg)
                if not text.strip():
                    continue

                is_thread_reply = (
                    _is_reply_to(msg, msg_id)
                    or _is_reply_to(msg, previous_msg_id or "")
                )
                looks_like_review = _looks_like_review(text)
                if not is_thread_reply and not looks_like_review:
                    continue

                status_cn, feedback = _parse_review_reply(text)
                if status_cn is None:
                    continue

                norm = "approved" if status_cn == "通过" else "need_revise"
                logger.info(
                    "[human_review] 收到人类回复 status=%s feedback=%s",
                    norm, feedback[:100],
                )
                return {
                    "status": norm,
                    "feedback": feedback or "",
                    "msg_id": msg_id,
                    "deadline": deadline,
                    "sent_at": sent_at_iso,
                }
        except Exception as exc:
            logger.warning("[human_review] 轮询消息失败: %s，继续等待", exc)

        if elapsed % 30 == 0:
            logger.info("[human_review] 已等待 %d/%d 秒...", elapsed, wait_sec)

    logger.warning("[human_review] 等待超时 (%ds)", wait_sec)
    return {
        "status": "timeout",
        "feedback": f"[超时] 等待人类回复超过 {wait_sec} 秒。",
        "msg_id": msg_id,
        "deadline": deadline,
        "sent_at": sent_at_iso,
    }


async def execute(params: dict, context: AgentContext) -> str:
    """保留 Agent 调用入口（向下兼容，当前已不在 soul.md 授权）。

    超时语义保持与 poll_for_human_reply 一致：不再默认通过。
    """
    brief_analysis = params.get("brief_analysis", "")
    timeout = params.get("timeout_seconds")

    if not brief_analysis.strip():
        return "错误: brief_analysis 不能为空，请先生成 Brief 解读再提交审核。"

    result = await poll_for_human_reply(brief_analysis, timeout=timeout)
    status = result["status"]
    feedback = result.get("feedback", "")

    if status in ("approved", "skipped_auto_approve", "skipped_no_chat"):
        return _format_result("通过", feedback or "默认通过。")
    if status == "need_revise":
        return _format_result("需要修改", feedback)
    if status == "timeout":
        return (
            "人类审核超时：\n"
            f"状态：超时\n"
            f"说明：{feedback}\n\n"
            "请等待下一次人工触发该项目，数据已保留。"
        )
    return _format_result("通过", feedback or "降级通过。")
