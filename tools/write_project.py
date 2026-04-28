from __future__ import annotations

import re

from feishu.bitable import FeishuAPIError
from memory.project import ProjectMemory
from tools import AgentContext

SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_project",
        "description": "写入项目主表的指定字段。用于保存 Brief 解读、策略方案、审核总评、审核通过率、审核阈值、红线风险、交付摘要等产出。",
        "parameters": {
            "type": "object",
            "properties": {
                "field_name": {
                    "type": "string",
                    "enum": [
                        "brief_analysis",
                        "strategy",
                        "review_summary",
                        "review_pass_rate",
                        "review_threshold",
                        "review_red_flag",
                        "delivery_summary",
                        "knowledge_ref",
                    ],
                    "description": "要写入的字段名",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容",
                },
            },
            "required": ["field_name", "content"],
        },
    },
}

_WRITERS = {
    "brief_analysis": "write_brief_analysis",
    "strategy": "write_strategy",
    "delivery_summary": "write_delivery",
    "knowledge_ref": "write_knowledge_ref",
}


def _parse_pass_rate(content: str) -> float | None:
    text = (content or "").strip()
    if not text:
        return None

    percent_match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
    if percent_match:
        return float(percent_match.group(1)) / 100.0

    number_match = re.fullmatch(r"-?\d+(?:\.\d+)?", text)
    if number_match:
        value = float(number_match.group(0))
        return value / 100.0 if value > 1 else value

    return None


async def execute(params: dict, context: AgentContext) -> str:
    field_name = params.get("field_name", "")
    content = params.get("content", "")

    if not field_name or not content:
        return "错误: field_name 和 content 不能为空"

    try:
        pm = ProjectMemory(context.record_id)

        if field_name == "review_summary":
            proj = await pm.load()
            parsed_pass_rate = _parse_pass_rate(content)
            pass_rate = (
                parsed_pass_rate
                if parsed_pass_rate is not None
                else float(proj.review_pass_rate or 0.0)
            )
            await pm.write_review_summary(
                content,
                pass_rate,
                threshold=float(getattr(proj, "review_threshold", 0.0) or 0.0),
                red_flag=getattr(proj, "review_red_flag", "") or "",
            )
            return (
                f"已写入 review_summary（{len(content)} 字），"
                f"review_pass_rate={pass_rate:.0%}"
            )

        if field_name == "review_pass_rate":
            parsed_pass_rate = _parse_pass_rate(content)
            if parsed_pass_rate is None:
                return "错误: review_pass_rate 无法解析，请使用 0.75 或 75% 这类格式"

            proj = await pm.load()
            await pm.write_review_summary(
                proj.review_summary,
                parsed_pass_rate,
                threshold=float(getattr(proj, "review_threshold", 0.0) or 0.0),
                red_flag=getattr(proj, "review_red_flag", "") or "",
            )
            return f"已写入 review_pass_rate（{parsed_pass_rate:.0%}）"

        if field_name == "review_threshold":
            parsed = _parse_pass_rate(content)
            if parsed is None:
                return "错误: review_threshold 无法解析，请使用 0.6 或 60% 这类格式"
            proj = await pm.load()
            await pm.write_review_summary(
                proj.review_summary,
                float(proj.review_pass_rate or 0.0),
                threshold=parsed,
                red_flag=getattr(proj, "review_red_flag", "") or "",
            )
            return f"已写入 review_threshold（{parsed:.0%}）"

        if field_name == "review_red_flag":
            proj = await pm.load()
            await pm.write_review_summary(
                proj.review_summary,
                float(proj.review_pass_rate or 0.0),
                threshold=float(getattr(proj, "review_threshold", 0.0) or 0.0),
                red_flag=content.strip(),
            )
            return f"已写入 review_red_flag（{content.strip() or '无'}）"

        if field_name == "knowledge_ref":
            refs = [r.strip() for r in content.split("\n") if r.strip()]
            await pm.write_knowledge_ref(refs)
            return f"已写入 knowledge_ref（{len(refs)} 条引用）"

        writer_method = _WRITERS.get(field_name)
        if not writer_method:
            return f"错误: 不支持写入字段 '{field_name}'"

        await getattr(pm, writer_method)(content)
        return f"已写入 {field_name}（{len(content)} 字）"

    except FeishuAPIError as exc:
        return f"飞书API错误（code={exc.code}）: {exc.msg}"
