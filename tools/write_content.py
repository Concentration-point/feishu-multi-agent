from __future__ import annotations

import logging
import re

from config import CONTENT_TABLE_ID, FIELD_MAP_CONTENT as FC
from feishu.bitable import BitableClient, FeishuAPIError
from memory.project import ContentMemory
from tools import AgentContext
from tools.preflight_lint import scan_forbidden_words, format_preflight_result

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_content",
        "description": "更新内容排期表中一条记录的指定字段。",
        "parameters": {
            "type": "object",
            "properties": {
                "content_record_id": {
                    "type": "string",
                    "description": "内容行的 record_id",
                },
                "field_name": {
                    "type": "string",
                    "enum": [
                        "draft_content",
                        "word_count",
                        "review_status",
                        "review_feedback",
                        "publish_date",
                        "notes",
                    ],
                    "description": "要更新的字段名",
                },
                "value": {
                    "type": "string",
                    "description": "要写入的值",
                },
            },
            "required": ["content_record_id", "field_name", "value"],
        },
    },
}


# ── 预检备注合并工具 ──
# 识别一行（含尾部换行/空白）开头是 [预检] 的整段，吃到下一个空行或字符串末尾。
# 设计幂等：多次写 draft 不会让备注里的 [预检] 段堆积。
_PREFLIGHT_BLOCK_RE = re.compile(
    r"(?:\r?\n)*\[预检\][^\n]*(?:\r?\n(?!\s*\r?\n)[^\n]*)*",
)


def _merge_preflight_into_remark(existing_remark: str, preflight_line: str) -> str:
    """把新预检行合并进现有备注，剔除旧的 [预检] 段后 append。

    幂等保证：连续多次合并同样的 preflight_line 结果不变。
    """
    base = existing_remark or ""
    # 移除全部既有 [预检] 段
    cleaned = _PREFLIGHT_BLOCK_RE.sub("", base).rstrip()
    if cleaned:
        return f"{cleaned}\n\n{preflight_line}"
    return preflight_line


async def _get_existing_fields(record_id: str) -> dict:
    client = BitableClient()
    return await client.get_record(CONTENT_TABLE_ID, record_id)


async def _run_preflight_and_merge_remark(
    rid: str, draft_text: str
) -> tuple[str, str]:
    """对成稿做禁用词预检并把结果幂等合并到备注字段。

    返回 (preflight_summary, status_tag):
      preflight_summary: 给 LLM 看的简短摘要（如 "命中禁用词 2 个（最有效、顶级）"）
      status_tag: "ok" / "fail"，便于上层拼接最终返回串
    """
    try:
        hits = scan_forbidden_words(draft_text)
        preflight_line = format_preflight_result(hits)
    except Exception as exc:  # noqa: BLE001
        # 扫描失败：备注写"扫描失败"，不影响成稿主流程
        logger.warning("预检扫描失败: %s", exc, exc_info=True)
        preflight_line = f"[预检] 扫描失败：{type(exc).__name__}: {exc}"
        hits = None

    # 写备注：先读现有，剔除旧 [预检] 段，再 append
    try:
        existing = await _get_existing_fields(rid)
        existing_remark = existing.get(FC["remark"], "") or ""
        merged = _merge_preflight_into_remark(existing_remark, preflight_line)
        client = BitableClient()
        await client.update_record(CONTENT_TABLE_ID, rid, {FC["remark"]: merged})
    except Exception as exc:  # noqa: BLE001
        # 备注写入失败也不能让成稿失败：仅日志告警
        logger.warning("预检备注写入失败: %s", exc, exc_info=True)

    # 给 LLM 看的摘要
    if hits is None:
        return "扫描失败", "fail"
    if not hits:
        return "通过", "ok"
    sample = "、".join(h["word"] for h in hits[:5])
    more = "" if len(hits) <= 5 else "等"
    return f"命中禁用词 {len(hits)} 个（{sample}{more}）", "ok"


async def execute(params: dict, context: AgentContext) -> str:
    rid = params.get("content_record_id", "")
    field = params.get("field_name", "")
    value = params.get("value", "")

    if not rid or not field:
        return "错误: content_record_id 和 field_name 不能为空"

    try:
        cm = ContentMemory()

        if field == "draft_content":
            await cm.write_draft(rid, value, len(value))
            base = f"已写入成稿内容（{len(value)} 字）"
            # 预检与备注合并：失败也要兜底，绝不影响成稿写入主路径
            try:
                summary, _tag = await _run_preflight_and_merge_remark(rid, value)
                return f"{base}，预检：{summary}"
            except Exception as exc:  # noqa: BLE001
                logger.warning("预检整段失败兜底: %s", exc, exc_info=True)
                return f"{base}，预检：扫描失败"

        if field == "word_count":
            existing = await _get_existing_fields(rid)
            existing_draft = existing.get(FC["draft"], "")
            await cm.write_draft(rid, existing_draft, int(value))
            return f"已更新字数: {value}"

        if field == "review_status":
            await cm.write_review_status(rid, value)
            return f"已更新审核状态: {value}"

        if field == "review_feedback":
            await cm.write_review_feedback(rid, value)
            return f"已写入审核反馈（{len(value)} 字）"

        if field == "publish_date":
            await cm.write_publish_date(rid, value)
            return f"已设置发布日期: {value}"

        if field == "notes":
            client = BitableClient()
            await client.update_record(CONTENT_TABLE_ID, rid, {FC["remark"]: value})
            return f"已写入备注（{len(value)} 字）"

        return f"错误: 不支持的字段 '{field}'"

    except FeishuAPIError as exc:
        return f"飞书API错误（code={exc.code}）: {exc.msg}"
