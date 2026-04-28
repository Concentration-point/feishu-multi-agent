"""工具: 更新项目状态（带状态机校验）"""

from feishu.bitable import FeishuAPIError
from tools import AgentContext
from memory.project import ProjectMemory
from config import VALID_STATUSES

SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_status",
        "description": "更新项目状态。会进行状态机校验，只允许合法的顺序流转。",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": VALID_STATUSES,
                    "description": "目标状态",
                },
            },
            "required": ["status"],
        },
    },
}

# 合法的状态流转: {当前状态: [可流转到的状态]}
_TRANSITIONS = {
    "待处理":   ["解读中"],
    "解读中":   ["策略中", "待人审"],   # Brief 解读后进入人审门禁
    "待人审":   ["策略中", "解读中"],   # 放行→策略；需修改→回退解读
    "策略中":   ["撰写中"],
    "撰写中":   ["审核中"],
    "审核中":   ["排期中", "撰写中"],   # 审核不过可回退到撰写中
    "排期中":   ["已完成"],
    "已完成":   [],
    "已驳回":   ["撰写中"],             # 驳回后可回到撰写中
}


async def execute(params: dict, context: AgentContext) -> str:
    target = params.get("status", "")
    if target not in VALID_STATUSES:
        return f"错误: 无效状态 '{target}'。合法状态: {VALID_STATUSES}"

    try:
        pm = ProjectMemory(context.record_id)
        proj = await pm.load()
        current = proj.status or "待处理"

        allowed = _TRANSITIONS.get(current, [])
        if target not in allowed:
            return (
                f"错误: 状态流转不合法。当前状态={current}，"
                f"目标状态={target}，允许的流转: {allowed}"
            )

        await pm.update_status(target)
        return f"状态已更新: {current} → {target}"

    except FeishuAPIError as exc:
        return f"飞书API错误（code={exc.code}）: {exc.msg}"
