"""工具: 查询经验池中的历史经验卡片"""

import json
from tools import AgentContext
from memory.experience import ExperienceManager

SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_experience",
        "description": "从经验池查询历史项目沉淀的经验卡片，用于提升产出质量。返回按置信度排序的 top-K 经验。",
        "parameters": {
            "type": "object",
            "properties": {
                "role_id": {
                    "type": "string",
                    "description": "查询哪个角色的经验，如 account_manager/strategist/copywriter/reviewer/project_manager",
                },
                "category": {
                    "type": "string",
                    "description": "场景分类，如: 电商大促/新品发布/品牌传播/日常运营。可选。",
                },
            },
            "required": ["role_id"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    role_id = params.get("role_id", "")
    category = params.get("category")

    if not role_id:
        return "错误: role_id 不能为空"

    em = ExperienceManager()
    experiences = await em.query_top_k(role_id, category=category)

    if not experiences:
        return "暂无相关历史经验。"

    lines = [f"找到 {len(experiences)} 条相关经验：\n"]
    for i, exp in enumerate(experiences, 1):
        cat = exp.get("category", "")
        conf = exp.get("confidence", 0)
        lesson = exp.get("lesson", "")
        situation = exp.get("situation", "")
        lines.append(
            f"{i}. [置信度 {conf:.2f}] {cat} - {situation[:30]}\n"
            f"   经验：{lesson}\n"
        )

    return "\n".join(lines)
