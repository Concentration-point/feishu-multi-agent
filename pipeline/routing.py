"""动态路由：状态读取、初始化、ROUTE_TABLE 查询、人审门禁、交接校验、halt 收尾。"""
from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from config import (
    HUMAN_REVIEW_TIMEOUT,
    ROUTE_TABLE,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_NEED_REVISE,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_TIMEOUT,
    STATUS_PENDING,
    STATUS_PENDING_REVIEW,
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


async def read_current_status(orch: "Orchestrator") -> str:
    """从 Bitable 读取项目当前状态，空状态自动初始化为「待处理」。

    区分两种"无状态"：
      - API 异常导致读不到 → 返回 ""，调用方按未知状态处理
      - 读到了但字段为空 → 兜底回写「待处理」并返回，避免动态路由空转直接退出
    """
    try:
        proj = await orch._pm.load()
        status = (proj.status or "").strip()
        if not status:
            return await orch._initialize_pending_status()
        return status
    except Exception as exc:
        logger.warning("动态路由：读取项目状态失败: %s", exc)
        return ""


async def initialize_pending_status(orch: "Orchestrator") -> str:
    """空状态兜底：回写「待处理」到 Bitable 并返回。

    回写失败仅记录警告，仍返回 STATUS_PENDING——动态路由能正常推进比 Bitable 同步更优先。
    下次 _read_current_status 还会再次尝试初始化，最终一致。
    """
    print(f"[Orchestrator] 项目状态为空，自动初始化为「{STATUS_PENDING}」")
    try:
        await orch._pm.update_status(STATUS_PENDING)
    except Exception as exc:
        logger.warning("初始化空状态为「%s」失败: %s", STATUS_PENDING, exc)
        print(
            f"[Orchestrator] 警告: 空状态回写失败（不阻断主流程）: "
            f"{type(exc).__name__}: {exc}"
        )
    return STATUS_PENDING


def resolve_next_role(orch: "Orchestrator", status: str) -> str | None:
    """根据当前项目状态查路由表，返回下一个角色 ID 或 None（终止）。

    未匹配的状态返回 None，由调用方决定是否 fallback。
    """
    return ROUTE_TABLE.get(status)


async def enter_human_review_gate(orch: "Orchestrator", *, resumed: bool) -> str:
    """AM 之后的人审门禁，或从"待人审"恢复。

    返回:
        "approved"     → 放行，继续 pipeline 后续阶段
        "need_revise"  → 人类要求修改，已落盘 human_feedback + status 回"解读中"
        "timeout"      → 本轮超时，status 落"待人审"，下次触发可恢复
        "skipped"      → 降级跳过（AUTO_APPROVE / 无群聊 / brief_analysis 空），等价 approved
    """
    from tools.request_human_review import poll_for_human_reply

    try:
        proj = await orch._pm.load()
    except Exception as exc:
        logger.exception("门禁加载项目失败")
        print(f"[Orchestrator] 警告: 门禁加载项目失败: {exc}")
        return "error"

    brief_analysis = (proj.brief_analysis or "").strip()
    if not brief_analysis:
        print("[Orchestrator] 警告: brief_analysis 为空，跳过人审门禁")
        return "skipped"

    await orch._pm.write_review_status(REVIEW_STATUS_PENDING)
    orch._publish("human_review.started", {"resumed": resumed})

    previous_msg_id: str | None = None
    prev_send_count = 0
    try:
        meta_prev = json.loads(proj.pending_meta or "{}")
        previous_msg_id = meta_prev.get("msg_id") or None
        prev_send_count = int(meta_prev.get("send_count", 0))
    except Exception:
        pass

    result = await poll_for_human_reply(
        brief_analysis,
        previous_msg_id=previous_msg_id,
    )
    status = result.get("status", "")
    feedback = (result.get("feedback") or "").strip()
    new_msg_id = result.get("msg_id", "")
    deadline = result.get("deadline", 0)
    sent_at = result.get("sent_at", "")

    meta_to_save = {
        "msg_id": new_msg_id,
        "deadline": deadline,
        "send_count": prev_send_count + 1,
        "sent_at": sent_at,
    }
    await orch._pm.write_pending_meta(meta_to_save)

    if status in ("approved", "skipped_auto_approve"):
        await orch._pm.write_review_status(REVIEW_STATUS_APPROVED)
        await orch._pm.clear_pending_state()
        try:
            await orch._pm.update_status("策略中")
        except Exception as exc:
            print(f"[Orchestrator] 警告: 放行后更新状态失败: {exc}")
        orch._publish("human_review.resolved", {
            "outcome": "approved", "feedback": feedback, "resumed": resumed,
        })
        await orch._broadcast(
            title="人审通过",
            content=(
                f"审核人已确认 Brief 解读，项目进入策略阶段\n\n"
                f"{feedback[:200] or '（无额外意见）'}"
            ),
            color="green",
        )
        return "approved"

    if status == "need_revise":
        await orch._pm.write_review_status(REVIEW_STATUS_NEED_REVISE)
        await orch._pm.write_human_feedback(feedback)
        try:
            await orch._pm.update_status("解读中")
        except Exception as exc:
            print(f"[Orchestrator] 警告: 回退状态失败: {exc}")
        orch._publish("human_review.resolved", {
            "outcome": "need_revise", "feedback": feedback, "resumed": resumed,
        })
        await orch._broadcast(
            title="审核要求修改",
            content=(
                f"审核意见已落盘，本次流程结束。\n"
                f"下次触发本项目，客户经理会读取反馈重写解读。\n\n"
                f"反馈：{feedback[:300]}"
            ),
            color="orange",
        )
        return "need_revise"

    # timeout
    await orch._pm.write_review_status(REVIEW_STATUS_TIMEOUT)

    # 第二次超时 → 终止项目
    if prev_send_count >= 1:
        try:
            await orch._pm.update_status(STATUS_REJECTED)
        except Exception as exc:
            print(f"[Orchestrator] 警告: 切换到已驳回状态失败: {exc}")
        await orch._pm.clear_pending_state()
        orch._publish("human_review.resolved", {
            "outcome": "timeout_final", "feedback": feedback, "resumed": resumed,
        })
        await orch._broadcast(
            title="人审连续超时，项目已终止",
            content=(
                f"本项目已连续两次等待人审超过 {HUMAN_REVIEW_TIMEOUT} 秒上限，\n"
                f"系统自动将项目标记为「已驳回」并终止流程。\n"
                f"如需重新启动，请在多维表格将状态手动改为「待处理」后重新触发。"
            ),
            color="red",
        )
        return "timeout_final"

    # 第一次超时 → 挂起，等待下次触发恢复
    try:
        await orch._pm.update_status(STATUS_PENDING_REVIEW)
    except Exception as exc:
        print(f"[Orchestrator] 警告: 切换到待人审状态失败: {exc}")
    orch._publish("human_review.resolved", {
        "outcome": "timeout", "feedback": feedback, "resumed": resumed,
    })
    await orch._broadcast(
        title="等待审核超时，项目已挂起",
        content=(
            f"本轮等待审核超过 {HUMAN_REVIEW_TIMEOUT} 秒上限。\n"
            f"项目数据已完整保留，status=「待人审」。\n"
            f"下次触发同一 record_id，将直接恢复到人审环节，无需重跑客户经理。\n"
            f"⚠️ 如下次仍超时，项目将被自动终止。"
        ),
        color="yellow",
    )
    return "timeout"


async def finalize_pipeline_halted(orch: "Orchestrator", project_name: str, outcome: str) -> None:
    """流程在门禁被中断时的收尾：事件、耗时、不做经验沉淀。"""
    total_time = time.perf_counter() - orch._start_time
    ok_count = sum(1 for item in orch.stage_results if item.ok)
    orch._publish("pipeline.halted", {
        "total_time": total_time,
        "ok_count": ok_count,
        "total_stages": len(orch.stage_results),
        "outcome": outcome,
        "project_name": project_name,
    })
    print(
        f"[Orchestrator] 流程在人审门禁中断: outcome={outcome}, "
        f"阶段完成 {ok_count}/{len(orch.stage_results)}, 总耗时 {total_time:.1f}s"
    )


async def get_project_name(orch: "Orchestrator") -> str:
    try:
        proj = await orch._pm.load()
        return proj.client_name or "未知客户"
    except Exception:
        return "未知客户"


async def validate_handoff(orch: "Orchestrator", role_id: str, project_name: str) -> tuple[bool, str]:
    """交接校验：启动下游 Agent 前检查上游必填字段非空。

    返回 (True, "") 表示可以启动；(False, reason) 表示上游产出缺失，不应启动。
    读取失败时不阻塞（返回 True），让 Agent 自己报错。
    """
    try:
        proj = await orch._pm.load()
    except Exception as exc:
        logger.warning("交接校验：读取项目失败，跳过校验: %s", exc)
        return False, f"读取项目失败: {exc}"

    if role_id == "strategist":
        if not (proj.brief_analysis or "").strip():
            return False, "策略师启动前必须有 brief_analysis（客户经理产出为空）"

    elif role_id == "copywriter":
        if not (proj.strategy or "").strip():
            return False, "文案启动前必须有 strategy（策略师产出为空）"
        try:
            rows = await _resolve_ContentMemory()().list_by_project(proj.client_name or project_name)
            if not rows:
                return False, "文案启动前内容排期表必须有行（策略师未创建内容行）"
        except Exception as exc:
            logger.warning("交接校验：读取内容行失败，跳过行数检查: %s", exc)

    elif role_id == "reviewer":
        try:
            rows = await _resolve_ContentMemory()().list_by_project(proj.client_name or project_name)
            if not rows:
                return False, "审核启动前内容排期表必须有行（策略师未创建或文案未完成任何行）"
            empty = [r for r in rows if not (r.draft or "").strip()]
            if empty:
                return False, (
                    f"审核启动前所有内容行必须有成稿"
                    f"（{len(empty)}/{len(rows)} 条 draft 为空）"
                )
        except Exception as exc:
            logger.warning("交接校验：读取内容行失败，跳过成稿检查: %s", exc)

    elif role_id == "project_manager":
        if not (proj.review_summary or "").strip():
            return False, "项目经理启动前必须有 review_summary（审核产出为空）"

    return True, ""
