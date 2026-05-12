"""审核流程：通过率读取、行级统计、红线汇总、返工与强制推进、自动 review_summary 写入。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import (
    REVIEW_MAX_RETRIES,
    REVIEW_PASS_THRESHOLD_DEFAULT,
    REVIEW_RED_FLAG_KEYWORDS,
    REVIEW_STATUS_APPROVED,
    REVIEW_THRESHOLDS_BY_PROJECT_TYPE,
    STATUS_REJECTED,
)
from memory.project import ContentMemory as _DefaultContentMemory

if TYPE_CHECKING:
    from memory.project import ContentMemory
    from orchestrator import Orchestrator


logger = logging.getLogger(__name__)


def _resolve_ContentMemory():
    """通过 orchestrator 模块属性获取 ContentMemory，让测试 monkey-patch 生效。"""
    import sys
    orch_mod = sys.modules.get("orchestrator")
    if orch_mod is not None:
        return getattr(orch_mod, "ContentMemory", _DefaultContentMemory)
    return _DefaultContentMemory


async def handle_reviewer_retries(orch: "Orchestrator") -> None:
    """审核后评估：检查通过率和红线，不达标则回退状态为"撰写中"让主循环路由接管。

    不再内部执行 agent，重试流程由主循环动态路由自然驱动：
    撰写中 → copywriter → 审核中 → reviewer → _handle_reviewer_retries → ...
    """
    pass_rate = await orch._get_review_pass_rate()
    pass_rate = await orch._reconcile_review_pass_rate(pass_rate)

    review_red_flag = await orch._collect_review_red_flag()
    has_red_flag = orch._is_review_red_flag(review_red_flag)
    orch._review_red_flag = review_red_flag.strip() if has_red_flag else "无"

    if has_red_flag:
        print(f"[Orchestrator] 警告: 审核结构化红线字段命中风险：{orch._review_red_flag}，触发一票否决")
        await orch._hard_stop_reviewer_red_flag(pass_rate)
        return

    if pass_rate is None:
        print("[Orchestrator] 警告: 无法读取审核通过率，跳过返工重试逻辑")
        return

    if pass_rate >= orch._review_threshold:
        print(f"[Orchestrator] 审核通过率 {pass_rate:.0%}，达到阈值 {orch._review_threshold:.0%}，且无红线风险，推进状态「审核中」→「排期中」")
        await orch._write_auto_review_summary(pass_rate)
        try:
            await orch._pm.update_status("排期中")
        except Exception as exc:
            print(f"[Orchestrator] 警告: 推进状态到排期中失败: {type(exc).__name__}: {exc}")
        return

    # 已达最大重试次数，强制推进到排期阶段，避免死循环
    if orch.reviewer_retries >= REVIEW_MAX_RETRIES:
        print(
            f"[Orchestrator] 警告: 审核通过率 {pass_rate:.0%}，阈值 {orch._review_threshold:.0%}，"
            f"重试已达上限 {REVIEW_MAX_RETRIES}，强制推进到排期阶段"
        )
        await orch._write_auto_review_summary(pass_rate)
        try:
            await orch._pm.update_status("排期中")
        except Exception as exc:
            print(f"[Orchestrator] 警告: 强制推进状态失败: {type(exc).__name__}: {exc}")
        return

    # 触发返工：回退状态为"撰写中"，由主循环路由自然驱动 copywriter → reviewer
    orch.reviewer_retries += 1
    orch._publish("pipeline.rejection", {
        "pass_rate": pass_rate,
        "attempt": orch.reviewer_retries,
        "max_attempts": REVIEW_MAX_RETRIES,
    }, agent_role="reviewer", agent_name="审核")

    print(
        f"[Orchestrator] 警告: 审核通过率 {pass_rate:.0%} < {orch._review_threshold:.0%} 或存在红线风险，"
        f"触发返工重试 {orch.reviewer_retries}/{REVIEW_MAX_RETRIES}，状态改回 '撰写中'"
    )

    review_status = await orch._get_project_review_status()
    await orch._broadcast(
        title="审核驳回，触发返工",
        content=(
            f"通过率 **{pass_rate:.0%}**，阈值 **{orch._review_threshold:.0%}**\n"
            f"红线风险：**{orch._review_red_flag or '无'}**\n"
            f"人审状态：**{review_status or '未知'}**\n"
            f"文案将根据审核反馈修改，第 {orch.reviewer_retries}/{REVIEW_MAX_RETRIES} 次重试"
        ),
        color="orange",
    )

    try:
        await orch._pm.update_status("撰写中")
    except Exception as exc:
        print(f"[Orchestrator] 警告: 状态回退失败: {type(exc).__name__}: {exc}")


async def hard_stop_reviewer_red_flag(orch: "Orchestrator", pass_rate: float | None) -> None:
    """红线命中后一票否决，并把风险写回项目主表供后续追踪。"""
    safe_pass_rate = pass_rate if pass_rate is not None else 0.0
    try:
        proj = await orch._pm.load()
        existing_summary = (getattr(proj, "review_summary", "") or "").strip()
        risk_line = f"红线命中，已硬中止：{orch._review_red_flag}"
        summary = existing_summary
        if not summary:
            summary = risk_line
        elif orch._review_red_flag not in summary:
            summary = f"{summary}\n\n{risk_line}"

        await orch._pm.write_review_summary(
            summary,
            safe_pass_rate,
            threshold=float(getattr(proj, "review_threshold", 0.0) or orch._review_threshold),
            red_flag=orch._review_red_flag,
        )
    except Exception as exc:
        logger.exception("写入红线硬中止风险标记失败")
        print(f"[Orchestrator] 警告: 写入红线硬中止风险标记失败: {type(exc).__name__}: {exc}")

    orch._publish("pipeline.red_flag_halted", {
        "pass_rate": safe_pass_rate,
        "threshold": orch._review_threshold,
        "red_flag": orch._review_red_flag,
    }, agent_role="reviewer", agent_name="审核")

    await orch._broadcast(
        title="审核命中红线，流程已中止",
        content=(
            f"通过率 **{safe_pass_rate:.0%}**，阈值 **{orch._review_threshold:.0%}**\n"
            f"红线风险：**{orch._review_red_flag}**\n"
            "项目已标记为已驳回，不再进入返工或排期。"
        ),
        color="red",
    )

    try:
        await orch._pm.update_status(STATUS_REJECTED)
    except Exception as exc:
        print(f"[Orchestrator] 警告: 红线硬中止状态写入失败: {type(exc).__name__}: {exc}")


async def write_auto_review_summary(orch: "Orchestrator", pass_rate: float) -> None:
    """审核完成后，由 Orchestrator 自动聚合行级审核结果写入 review_summary。

    不依赖 LLM 主动调工具，确保 _validate_handoff 的前置字段非空。
    若 review_summary 已有值（reviewer 手写过）则跳过，不覆盖。
    """
    try:
        proj = await orch._pm.load()
        if (proj.review_summary or "").strip():
            return  # reviewer 已写，不覆盖

        project_name = proj.client_name or "未知客户"
        rows = await _resolve_ContentMemory()().list_by_project(project_name)

        passed = [r for r in rows if (r.review_status or "").strip() == REVIEW_STATUS_APPROVED]
        failed = [r for r in rows if (r.review_status or "").strip() not in (REVIEW_STATUS_APPROVED, "")]
        total = len(rows)

        lines = [
            f"审核通过率：{pass_rate:.0%}（{len(passed)}/{total} 条通过）",
            f"阈值：{orch._review_threshold:.0%}",
        ]
        if failed:
            lines.append("未通过条目：")
            for r in failed[:5]:  # 最多列 5 条，避免摘要过长
                fb = (r.review_feedback or "").strip()[:60]
                lines.append(f"  · [{r.review_status}] {r.title or r.record_id[:8]}：{fb}")
            if len(failed) > 5:
                lines.append(f"  · … 另 {len(failed) - 5} 条，详见内容排期表")
        else:
            lines.append("全部内容行已通过审核。")

        summary = "\n".join(lines)
        await orch._pm.write_review_summary(
            summary,
            pass_rate,
            threshold=float(getattr(proj, "review_threshold", 0.0) or 0.0),
            red_flag=getattr(proj, "review_red_flag", "") or "",
        )
        print(f"[Orchestrator] 已自动写入 review_summary（{len(summary)} 字）")
    except Exception as exc:
        logger.warning("自动写入 review_summary 失败，跳过: %s", exc)
        print(f"[Orchestrator] 警告: 自动写入 review_summary 失败: {type(exc).__name__}: {exc}")


async def get_review_threshold(orch: "Orchestrator") -> float:
    try:
        proj = await orch._pm.load()
        project_type = (proj.project_type or "").strip()
        return REVIEW_THRESHOLDS_BY_PROJECT_TYPE.get(project_type, REVIEW_PASS_THRESHOLD_DEFAULT)
    except Exception as exc:
        logger.exception("获取审核阈值失败")
        print(f"[Orchestrator] 警告: 获取审核阈值失败: {type(exc).__name__}: {exc}")
        return REVIEW_PASS_THRESHOLD_DEFAULT


async def get_review_summary(orch: "Orchestrator") -> str:
    try:
        proj = await orch._pm.load()
        return proj.review_summary or ""
    except Exception as exc:
        logger.exception("获取审核总评失败")
        print(f"[Orchestrator] 警告: 获取审核总评失败: {type(exc).__name__}: {exc}")
        return ""


async def get_review_red_flag(orch: "Orchestrator") -> str:
    try:
        proj = await orch._pm.load()
        return (proj.review_red_flag or "").strip()
    except Exception as exc:
        logger.exception("获取审核红线风险失败")
        print(f"[Orchestrator] 警告: 获取审核红线风险失败: {type(exc).__name__}: {exc}")
        return ""


def is_review_red_flag(value: str | None) -> bool:
    """判断 review_red_flag 是否表达真实红线，而不是空值或否定信号。"""
    normalized = (value or "").strip().lower()
    if not normalized:
        return False
    return normalized not in {"无", "否", "false", "none", "null", "0", "未命中", "无红线", "无风险"}


async def collect_review_red_flag(orch: "Orchestrator") -> str:
    """汇总项目级与内容行级红线，避免 submit_review 只写内容行时漏拦截。"""
    project_flag = await orch._get_review_red_flag()
    if orch._is_review_red_flag(project_flag):
        return project_flag
    return await orch._get_row_level_review_red_flag()


async def get_row_level_review_red_flag(orch: "Orchestrator") -> str:
    """从内容行审核反馈中提取红线关键词，作为项目级字段未同步时的兜底。"""
    try:
        project_name = await orch._get_project_name()
        if not project_name or project_name == "未知客户":
            return ""

        rows = await _resolve_ContentMemory()().list_by_project(project_name)
        hits: list[str] = []
        keywords = [*REVIEW_RED_FLAG_KEYWORDS, "红线", "广告法禁用词", "禁用词"]
        for row in rows:
            feedback = (getattr(row, "review_feedback", "") or "").strip()
            if not feedback:
                continue
            matched_keywords = [keyword for keyword in keywords if keyword and keyword in feedback]
            if matched_keywords:
                title = (getattr(row, "title", "") or getattr(row, "record_id", "") or "未知内容").strip()
                hits.append(f"{title}：{', '.join(dict.fromkeys(matched_keywords))}")

        return "；".join(hits)
    except Exception as exc:
        logger.exception("行级审核红线汇总失败")
        print(f"[Orchestrator] 警告: 行级审核红线汇总失败: {type(exc).__name__}: {exc}")
        return ""


async def get_project_review_status(orch: "Orchestrator") -> str:
    try:
        proj = await orch._pm.load()
        return getattr(proj, "review_status", "") or ""
    except Exception as exc:
        logger.exception("获取人审状态失败")
        print(f"[Orchestrator] 警告: 获取人审状态失败: {type(exc).__name__}: {exc}")
        return ""


async def get_review_pass_rate(orch: "Orchestrator") -> float | None:
    try:
        proj = await orch._pm.load()
        raw_value = proj.review_pass_rate
        if raw_value in (None, "", []):
            return 0.5
        return float(raw_value)
    except Exception as exc:
        logger.exception("读取审核通过率失败")
        print(f"[Orchestrator] 警告: 读取审核通过率失败: {type(exc).__name__}: {exc}")
        return None


async def compute_row_level_pass_rate(orch: "Orchestrator") -> tuple[float | None, int, int]:
    """按内容行级 review_status 实际统计通过率。

    返回 (pass_rate, passed_count, total_count)。
    total==0 时 pass_rate 返回 None，表示没有可用于汇总的行。
    只承认 REVIEW_STATUS_APPROVED ("通过") 作为通过；空值、需修改、驳回、超时均不计入通过。
    """
    try:
        project_name = await orch._get_project_name()
        if not project_name or project_name == "未知客户":
            return None, 0, 0
        cm = _resolve_ContentMemory()()
        rows = await cm.list_by_project(project_name)
        total = len(rows)
        if total == 0:
            return None, 0, 0
        passed = sum(
            1 for r in rows
            if (r.review_status or "").strip() == REVIEW_STATUS_APPROVED
        )
        return passed / total, passed, total
    except Exception as exc:
        logger.exception("行级审核通过率统计失败")
        print(f"[Orchestrator] 警告: 行级审核通过率统计失败: {type(exc).__name__}: {exc}")
        return None, 0, 0


async def reconcile_review_pass_rate(
    orch: "Orchestrator",
    project_level_rate: float | None,
) -> float | None:
    """对齐项目级字段和行级统计，不一致时以行级为准并回写项目主表。"""
    row_rate, passed, total = await orch._compute_row_level_pass_rate()
    if row_rate is None:
        return project_level_rate

    if project_level_rate is None:
        print(
            f"[Orchestrator] 项目级审核通过率为空，采用行级统计 {row_rate:.0%}"
            f"（{passed}/{total}），回写项目主表"
        )
    elif abs(row_rate - project_level_rate) > 1e-3:
        print(
            f"[Orchestrator] 警告: 审核通过率口径不一致——项目级 {project_level_rate:.0%}"
            f" vs 行级 {row_rate:.0%}（{passed}/{total}），以行级为准并回写项目主表"
        )
    else:
        return project_level_rate

    try:
        proj = await orch._pm.load()
        await orch._pm.write_review_summary(
            proj.review_summary or "",
            row_rate,
            threshold=float(getattr(proj, "review_threshold", 0.0) or 0.0),
            red_flag=getattr(proj, "review_red_flag", "") or "",
        )
    except Exception as exc:
        logger.exception("回写审核通过率失败")
        print(f"[Orchestrator] 警告: 回写审核通过率失败: {type(exc).__name__}: {exc}")

    return row_rate
