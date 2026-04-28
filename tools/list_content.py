"""工具: 列出当前项目的所有内容行。

支持可选 platform 过滤：用于 copywriter fan-out 场景，
每个 platform 子 agent 传入 platform=X 只拉取自己负责的 rows。
未传 platform 时维持原有「按项目名拉全部」行为。
"""

import json
from dataclasses import asdict
from feishu.bitable import FeishuAPIError
from tools import AgentContext
from memory.project import ContentMemory

SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_content",
        "description": (
            "列出当前项目的所有内容排期行。自动按项目名称过滤。"
            "可选参数 platform：若传入则仅返回目标平台匹配的行（大小写不敏感），"
            "用于并行子 Agent 只处理自己负责的平台子集。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": (
                        "可选。目标平台名称（如「小红书」「抖音」）。"
                        "传入后按 row.platform 字段大小写不敏感过滤。不传则返回全部。"
                    ),
                },
            },
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    try:
        cm = ContentMemory()
        records = await cm.list_by_project(context.project_name)

        platform = (params.get("platform") or "").strip()
        if platform:
            needle = platform.lower()
            records = [r for r in records if (r.platform or "").strip().lower() == needle]

        items = [asdict(r) for r in records]
        return json.dumps(items, ensure_ascii=False, indent=2)

    except FeishuAPIError as exc:
        return f"飞书API错误（code={exc.code}）: {exc.msg}"
