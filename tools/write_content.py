from __future__ import annotations

from config import CONTENT_TABLE_ID, FIELD_MAP_CONTENT as FC
from feishu.bitable import BitableClient, FeishuAPIError
from memory.project import ContentMemory
from tools import AgentContext

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


async def _get_existing_fields(record_id: str) -> dict:
    client = BitableClient()
    return await client.get_record(CONTENT_TABLE_ID, record_id)


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
            return f"已写入成稿内容（{len(value)} 字）"

        if field == "word_count":
            existing = await _get_existing_fields(rid)
            existing_draft = existing.get(FC["draft"], "")
            await cm.write_draft(rid, existing_draft, int(value))
            return f"已更新字数: {value}"

        if field == "review_status":
            existing = await _get_existing_fields(rid)
            existing_feedback = existing.get(FC["review_feedback"], "")
            await cm.write_review(rid, value, existing_feedback)
            return f"已更新审核状态: {value}"

        if field == "review_feedback":
            existing = await _get_existing_fields(rid)
            existing_status = existing.get(FC["review_status"], "")
            await cm.write_review(rid, existing_status, value)
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
