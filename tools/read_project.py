"""工具: 读取项目主表字段"""

import json
from tools import AgentContext
from memory.project import ProjectMemory
from config import FIELD_MAP_PROJECT as FP

SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_project",
        "description": "读取项目主表的指定字段。可一次读取多个字段。",
        "parameters": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "要读取的字段名列表。可选值: "
                        "brief_content, project_type, brand_tone, dept_style, "
                        "status, brief_analysis, strategy, review_summary, "
                        "review_pass_rate, delivery_summary, knowledge_ref, client_name"
                    ),
                }
            },
            "required": ["fields"],
        },
    },
}

# 代码字段名 → ProjectMemory 的 FIELD_MAP 键
_FIELD_ALIAS = {
    "brief_content": "brief",
    "delivery_summary": "delivery",
    "client_name": "client_name",
    "project_type": "project_type",
    "brand_tone": "brand_tone",
    "dept_style": "dept_style",
    "status": "status",
    "brief_analysis": "brief_analysis",
    "strategy": "strategy",
    "review_summary": "review_summary",
    "review_pass_rate": "review_pass_rate",
    "knowledge_ref": "knowledge_ref",
}


async def execute(params: dict, context: AgentContext) -> str:
    fields = params.get("fields", [])
    if not fields:
        return "错误: fields 参数不能为空"

    pm = ProjectMemory(context.record_id)
    proj = await pm.load()

    result = {}
    for f in fields:
        key = _FIELD_ALIAS.get(f, f)
        if hasattr(proj, key):
            result[f] = getattr(proj, key)
        else:
            result[f] = f"未知字段: {f}"

    return json.dumps(result, ensure_ascii=False, indent=2)
