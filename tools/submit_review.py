"""审核 Agent 专用提交工具 — 单次原子调用完成单条内容的审核写回。

替代 write_content 分两次写 review_status + review_feedback 的模式，
同时提供结构化五维校验：任何维度"不通过"不得标记整体"通过"。
"""

from __future__ import annotations

import logging

from feishu.bitable import FeishuAPIError
from memory.project import ContentMemory
from tools import AgentContext

logger = logging.getLogger(__name__)

_VALID_STATUSES = ["通过", "需修改", "驳回"]
_VALID_DIM_VALUES = ["通过", "不通过"]
_DIMENSIONS = ["banned_words", "brand_tone", "platform_spec", "dept_style", "fact_check"]

SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_review",
        "description": (
            "提交单条内容的审核结论（原子写回 review_status + review_feedback）。"
            "内置结构化五维校验：若任一维度为'不通过'则不允许整体状态为'通过'。"
            "替代旧的两次 write_content 模式，确保状态与反馈原子性一致。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content_record_id": {
                    "type": "string",
                    "description": "内容行的 record_id",
                },
                "status": {
                    "type": "string",
                    "enum": _VALID_STATUSES,
                    "description": "审核总结论：通过 / 需修改 / 驳回",
                },
                "feedback": {
                    "type": "string",
                    "description": "审核反馈（需修改/驳回时必须非空，具体说明问题和修改建议）",
                },
                "violated_rules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "命中的规则条目列表，如 ['广告法禁用词：最有效', '品牌调性偏移']",
                },
                "dimensions": {
                    "type": "object",
                    "description": "五个审核维度各自的通过/不通过",
                    "properties": {
                        "banned_words": {
                            "type": "string",
                            "enum": _VALID_DIM_VALUES,
                            "description": "禁用词 & 合规检查",
                        },
                        "brand_tone": {
                            "type": "string",
                            "enum": _VALID_DIM_VALUES,
                            "description": "品牌调性一致性",
                        },
                        "platform_spec": {
                            "type": "string",
                            "enum": _VALID_DIM_VALUES,
                            "description": "平台适配",
                        },
                        "dept_style": {
                            "type": "string",
                            "enum": _VALID_DIM_VALUES,
                            "description": "部门风格注入一致性",
                        },
                        "fact_check": {
                            "type": "string",
                            "enum": _VALID_DIM_VALUES,
                            "description": "事实准确性与数据来源",
                        },
                    },
                    "required": _DIMENSIONS,
                },
            },
            "required": ["content_record_id", "status", "feedback", "violated_rules", "dimensions"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    rid = params.get("content_record_id", "")
    status = params.get("status", "")
    feedback = (params.get("feedback") or "").strip()
    dimensions: dict = params.get("dimensions") or {}

    # ── 基础参数校验 ──
    if not rid:
        return "错误: content_record_id 不能为空"
    if status not in _VALID_STATUSES:
        return f"错误: status 必须是 {_VALID_STATUSES}，收到 '{status}'"

    # ── violated_rules 硬校验（schema required，execute 同步强制）──
    if "violated_rules" not in params:
        return "错误: violated_rules 为必填参数，不能缺失（无违规时传空数组 []）"
    violated_rules = params["violated_rules"]
    if not isinstance(violated_rules, list):
        return f"错误: violated_rules 必须是字符串数组，收到 {type(violated_rules).__name__}"
    non_str = [i for i in violated_rules if not isinstance(i, str)]
    if non_str:
        return f"错误: violated_rules 元素必须全部为字符串，发现非字符串元素: {non_str[:3]}"

    # ── dimensions 结构校验 ──
    missing_dims = [d for d in _DIMENSIONS if d not in dimensions]
    if missing_dims:
        return f"错误: dimensions 缺少必填字段 {missing_dims}，请补全五个审核维度"

    invalid_dims = {k: v for k, v in dimensions.items() if k in _DIMENSIONS and v not in _VALID_DIM_VALUES}
    if invalid_dims:
        return f"错误: dimensions 字段值非法（必须是'通过'或'不通过'）: {invalid_dims}"

    # ── 维度一致性校验：维度不通过但结论为通过 ──
    failed_dims = [d for d in _DIMENSIONS if dimensions.get(d) == "不通过"]
    if failed_dims and status == "通过":
        return (
            f"错误: 存在不通过维度 {failed_dims}，审核结论不能为「通过」。"
            "请将 status 改为「需修改」或「驳回」，并在 feedback 中说明具体原因。"
        )

    # ── 反馈非空校验 ──
    if status in ("需修改", "驳回") and not feedback:
        return f"错误: status 为「{status}」时 feedback 不能为空，请填写具体的问题描述和修改建议。"

    # ── 写入 Bitable ──
    try:
        cm = ContentMemory()
        await cm.write_review(rid, status, feedback)

        dim_summary = "、".join(
            f"{d}:{'✓' if dimensions.get(d) == '通过' else '✗'}"
            for d in _DIMENSIONS
        )
        rules_note = f"，命中规则：{violated_rules}" if violated_rules else ""
        logger.info(
            "[submit_review] rid=%s status=%s dims=[%s]%s",
            rid[:12], status, dim_summary, rules_note,
        )
        return (
            f"审核结论已写回: status={status}，维度=[{dim_summary}]"
            + (f"，命中规则={violated_rules}" if violated_rules else "")
        )
    except FeishuAPIError as exc:
        return f"飞书API错误（code={exc.code}）: {exc.msg}"
