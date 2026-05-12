"""Orchestrator: 飞书多 Agent 流水线的薄外观类与主循环。

具体职责拆到 pipeline/ 子模块；本文件保留外部 API、主 while 循环和事件广播。
"""
from __future__ import annotations

import asyncio
import logging
import time

from agents.base import BaseAgent
from config import (
    DELIVERY_DOC_ENABLED,
    FEISHU_CHAT_ID,
    MAX_ROUTE_STEPS,
    REVIEW_PASS_THRESHOLD_DEFAULT,
    ROLE_NAMES,
    ROUTE_TERMINAL_STATUSES,
    STATUS_DONE,
    STATUS_PENDING_REVIEW,
    WIKI_SPACE_ID,
)
from dashboard.event_bus import EventBus
from memory.experience import ExperienceManager  # re-exported for tests monkeypatching
from memory.project import BriefProject, ContentMemory, ProjectMemory
from pipeline import (
    copywriter_fanout as _cw,
    delivery as _delivery,
    experience_settlement as _exp,
    review_flow as _review,
    routing as _routing,
    stage_runner as _stage,
)


logger = logging.getLogger(__name__)

StageResult = _stage.StageResult
_detect_required_tool_failure = _stage.detect_required_tool_failure
_detect_tool_error = _stage.detect_tool_error
_clear_stage_checkpoint = _stage.clear_stage_checkpoint


class Orchestrator:
    """状态驱动的多 Agent 编排器。"""

    DEFAULT_PIPELINE = [
        "account_manager",
        "strategist",
        "copywriter",
        "reviewer",
        "project_manager",
    ]

    _delivery_parent_token: str = ""

    def __init__(self, record_id: str, event_bus: EventBus | None = None):
        self.record_id = record_id
        self._event_bus = event_bus
        self.pipeline = list(self.DEFAULT_PIPELINE)
        self.stage_results: list[StageResult] = []
        self.reviewer_retries = 0
        self._start_time = 0.0
        self._review_threshold = REVIEW_PASS_THRESHOLD_DEFAULT
        self._review_red_flag = ""
        self._max_route_steps = MAX_ROUTE_STEPS
        self._no_progress_limit = 3
        self._pm = ProjectMemory(record_id)
        self._started = False

    def _publish(
        self,
        event_type: str,
        payload: dict | None = None,
        *,
        agent_role: str = "",
        agent_name: str = "",
    ) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(
                self.record_id,
                event_type,
                payload,
                agent_role=agent_role,
                agent_name=agent_name,
            )
        except Exception:
            pass

    async def _read_current_status(self) -> str:
        return await _routing.read_current_status(self)

    async def _initialize_pending_status(self) -> str:
        return await _routing.initialize_pending_status(self)

    def _resolve_next_role(self, status: str) -> str | None:
        return _routing.resolve_next_role(self, status)

    async def _enter_human_review_gate(self, *, resumed: bool) -> str:
        return await _routing.enter_human_review_gate(self, resumed=resumed)

    async def _finalize_pipeline_halted(self, project_name: str, outcome: str) -> None:
        await _routing.finalize_pipeline_halted(self, project_name, outcome)

    async def _get_project_name(self) -> str:
        return await _routing.get_project_name(self)

    async def _validate_handoff(self, role_id: str, project_name: str) -> tuple[bool, str]:
        return await _routing.validate_handoff(self, role_id, project_name)

    async def _run_stage_with_agent(
        self, role_id: str, *, index: int, total: int
    ) -> tuple[StageResult, BaseAgent | None]:
        return await _stage.run_stage_with_agent(self, role_id, index=index, total=total)

    async def _safe_write_agent_error_log(self, message: str) -> None:
        await _stage.safe_write_agent_error_log(self, message)

    async def _run_copywriter_fanout(
        self, *, index: int, total: int
    ) -> tuple[StageResult, list[dict]]:
        return await _cw.run_copywriter_fanout(self, index=index, total=total)

    async def _ensure_copywriter_drafts(self, project_name: str) -> int:
        return await _cw.ensure_copywriter_drafts(self, project_name)

    @staticmethod
    def _build_copy_fallback_prompt(proj: BriefProject, row) -> str:
        return _cw.build_copy_fallback_prompt(proj, row)

    async def _handle_reviewer_retries(self) -> None:
        await _review.handle_reviewer_retries(self)

    async def _hard_stop_reviewer_red_flag(self, pass_rate: float | None) -> None:
        await _review.hard_stop_reviewer_red_flag(self, pass_rate)

    async def _write_auto_review_summary(self, pass_rate: float) -> None:
        await _review.write_auto_review_summary(self, pass_rate)

    async def _get_review_threshold(self) -> float:
        return await _review.get_review_threshold(self)

    async def _get_review_summary(self) -> str:
        return await _review.get_review_summary(self)

    async def _get_review_red_flag(self) -> str:
        return await _review.get_review_red_flag(self)

    @staticmethod
    def _is_review_red_flag(value: str | None) -> bool:
        return _review.is_review_red_flag(value)

    async def _collect_review_red_flag(self) -> str:
        return await _review.collect_review_red_flag(self)

    async def _get_row_level_review_red_flag(self) -> str:
        return await _review.get_row_level_review_red_flag(self)

    async def _get_project_review_status(self) -> str:
        return await _review.get_project_review_status(self)

    async def _get_review_pass_rate(self) -> float | None:
        return await _review.get_review_pass_rate(self)

    async def _compute_row_level_pass_rate(self) -> tuple[float | None, int, int]:
        return await _review.compute_row_level_pass_rate(self)

    async def _reconcile_review_pass_rate(self, pass_rate: float | None) -> float | None:
        return await _review.reconcile_review_pass_rate(self, pass_rate)

    @staticmethod
    def _md_to_blocks(text: str) -> list[dict]:
        return _delivery.md_to_blocks(text)

    async def _get_delivery_parent_token(self, wiki) -> str:
        return await _delivery.get_delivery_parent_token(self, wiki)

    async def _generate_delivery_document(self, project_name: str) -> str | None:
        return await _delivery.generate_delivery_document(self, project_name)

    @staticmethod
    def _calc_confidence(
        pass_rate: float | None,
        task_completed: bool,
        no_rework: bool,
        knowledge_cited: bool,
    ) -> float:
        return _exp.calc_confidence(pass_rate, task_completed, no_rework, knowledge_cited)

    async def _distill_experience(
        self,
        *,
        chain_id: str,
        task_summary: str,
        feedback_text: str,
    ) -> dict | None:
        return await _exp.distill_experience(
            self,
            chain_id=chain_id,
            task_summary=task_summary,
            feedback_text=feedback_text,
        )

    async def _distill_from_feedback(self, project_name: str) -> list[dict]:
        return await _exp.distill_from_feedback(self, project_name)

    async def _settle_experiences(self, project_name: str, project_type: str) -> None:
        await _exp.settle_experiences(self, project_name, project_type)

    async def _append_evolution_log(
        self, project_name: str, project_type: str, pass_rate: float | None
    ) -> None:
        await _exp.append_evolution_log(self, project_name, project_type, pass_rate)

    async def run(self) -> list[StageResult]:
        self._start_time = time.perf_counter()
        self._review_threshold = await self._get_review_threshold()

        try:
            proj = await self._pm.load()
        except Exception as exc:
            logger.exception("pipeline startup failed")
            self._publish("pipeline.failed", {"error": f"{type(exc).__name__}: {exc}"})
            return self.stage_results

        project_name = proj.client_name or "未知客户"
        project_type = (proj.project_type or "").strip()
        brief_summary = (proj.brief or "")[:200]
        current_status = (proj.status or "").strip()
        if not current_status:
            current_status = await self._initialize_pending_status()

        self._publish(
            "pipeline.started",
            {
                "project_name": project_name,
                "brief": brief_summary,
                "stages": list(self.pipeline),
                "stage_names": {k: v for k, v in ROLE_NAMES.items()},
                "routing": "dynamic",
                "initial_status": current_status,
            },
        )
        self._started = True

        step = 0
        no_progress_count = 0
        no_progress_limit = self._no_progress_limit

        if current_status == STATUS_PENDING_REVIEW:
            print("[Orchestrator] 检测到 status='待人审'，跳过 AM 直接进入恢复门禁")
            await self._broadcast(
                title="项目恢复",
                content=f"客户 **{project_name}** 状态为「待人审」，\n基于已保留的 Brief 解读继续等待审核",
                color="blue",
            )
            gate_outcome = await self._enter_human_review_gate(resumed=True)
            if gate_outcome != "approved":
                await self._finalize_pipeline_halted(project_name, gate_outcome)
                return self.stage_results
            _clear_stage_checkpoint(self.record_id, "account_manager")
            current_status = await self._read_current_status()
        else:
            await self._broadcast(
                title="新项目启动",
                content=f"客户 **{project_name}** 的 Brief 已接收，虚拟团队自动组建中\n\n动态路由模式: 根据项目状态自动调度下一角色",
                color="purple",
            )

        while step < self._max_route_steps:
            if current_status in ROUTE_TERMINAL_STATUSES:
                break

            role_id = self._resolve_next_role(current_status)
            if role_id is None:
                break

            if role_id == "__human_review_gate__":
                gate_outcome = await self._enter_human_review_gate(resumed=False)
                if gate_outcome != "approved":
                    await self._finalize_pipeline_halted(project_name, gate_outcome)
                    return self.stage_results
                _clear_stage_checkpoint(self.record_id, "account_manager")
                current_status = await self._read_current_status()
                continue

            step += 1
            role_name = ROLE_NAMES.get(role_id, role_id)
            self._publish(
                "pipeline.stage_changed",
                {
                    "current_role": role_id,
                    "stage_index": step,
                    "stage_total": len(self.pipeline),
                    "current_status": current_status,
                },
                agent_role=role_id,
                agent_name=role_name,
            )

            ok, reason = await self._validate_handoff(role_id, project_name)
            if not ok:
                result = StageResult(role_id=role_id, ok=False, duration_sec=0.0, error=reason)
                self.stage_results.append(result)
                await self._safe_write_agent_error_log(f"{role_id}: {reason}")
                self._publish("pipeline.stage_failed", {"role_id": role_id, "error": reason})
                break

            if role_id == "copywriter":
                result, _fanout = await self._run_copywriter_fanout(index=step, total=len(self.pipeline))
            else:
                result, _agent = await self._run_stage_with_agent(
                    role_id, index=step, total=len(self.pipeline)
                )
            self.stage_results.append(result)

            if not result.ok:
                error = result.error or "stage failed"
                await self._safe_write_agent_error_log(f"{role_id}: {error}")
                self._publish(
                    "pipeline.stage_failed",
                    {"role_id": role_id, "error": error, "duration_sec": result.duration_sec},
                    agent_role=role_id,
                    agent_name=role_name,
                )
                await self._broadcast(
                    title="流水线阶段失败",
                    content=f"角色 **{role_name}** 执行失败：\n\n{error}",
                    color="red",
                )
                break

            self._publish(
                "pipeline.stage_completed",
                {"role_id": role_id, "duration_sec": result.duration_sec},
                agent_role=role_id,
                agent_name=role_name,
            )

            if role_id == "reviewer":
                await self._handle_reviewer_retries()

            previous_status = current_status
            current_status = await self._read_current_status()

            if role_id == "account_manager" and current_status == STATUS_PENDING_REVIEW:
                gate_outcome = await self._enter_human_review_gate(resumed=False)
                if gate_outcome != "approved":
                    await self._finalize_pipeline_halted(project_name, gate_outcome)
                    return self.stage_results
                current_status = await self._read_current_status()

            if current_status == previous_status:
                if result.used_ask_human:
                    no_progress_count = 0
                else:
                    no_progress_count += 1
                    print(
                        f"[Orchestrator] 状态未推进: {current_status} "
                        f"({no_progress_count}/{no_progress_limit})"
                    )
                if no_progress_count >= no_progress_limit:
                    reason = f"no_progress:{current_status}"
                    await self._finalize_pipeline_halted(project_name, reason)
                    return self.stage_results
            else:
                no_progress_count = 0
                _clear_stage_checkpoint(self.record_id, role_id)

        if step >= self._max_route_steps and current_status not in ROUTE_TERMINAL_STATUSES:
            if self.stage_results and self.stage_results[-1].used_ask_human:
                self._publish(
                    "pipeline.aborted",
                    {
                        "project_name": project_name,
                        "status": current_status,
                        "stage_count": len(self.stage_results),
                        "abort_reason": f"max_route_steps_after_ask_human:{self._max_route_steps}",
                    },
                )
                return self.stage_results
            await self._finalize_pipeline_halted(project_name, f"max_route_steps:{self._max_route_steps}")
            return self.stage_results

        pass_rate = await self._get_review_pass_rate()
        if current_status == STATUS_DONE:
            try:
                await self._append_evolution_log(project_name, project_type, pass_rate)
            except Exception as exc:
                logger.warning("evolution log append failed: %s", exc)

            self._publish(
                "pipeline.completed",
                {
                    "project_name": project_name,
                    "status": current_status,
                    "review_pass_rate": pass_rate,
                    "review_threshold": self._review_threshold,
                    "stage_count": len(self.stage_results),
                },
            )
            await self._settle_experiences(project_name, project_type)

            if DELIVERY_DOC_ENABLED and WIKI_SPACE_ID:
                async def _bg_delivery_doc():
                    try:
                        doc_url = await asyncio.wait_for(
                            self._generate_delivery_document(project_name),
                            timeout=90.0,
                        )
                        if doc_url:
                            self._publish(
                                "delivery_doc.created",
                                {"url": doc_url, "project_name": project_name},
                            )
                    except asyncio.TimeoutError:
                        logger.warning("[交付文档] 生成超时（90s），已跳过本次交付文档")
                    except Exception as exc:
                        logger.warning("交付文档后台生成失败: %s", exc)

                asyncio.create_task(_bg_delivery_doc())
        else:
            self._publish(
                "pipeline.aborted",
                {
                    "project_name": project_name,
                    "status": current_status,
                    "stage_count": len(self.stage_results),
                    "review_pass_rate": pass_rate,
                },
            )

        return self.stage_results

    async def _broadcast(self, title: str, content: str, color: str) -> None:
        try:
            print(f"[广播] {title}: {content[:100]}")
        except UnicodeEncodeError:
            fallback = (
                f"[broadcast] {title.encode('ascii', 'ignore').decode('ascii')}: "
                f"{content[:100].encode('ascii', 'ignore').decode('ascii')}"
            )
            print(fallback)
        if not FEISHU_CHAT_ID:
            return

        try:
            from feishu.im import FeishuIMClient

            im = FeishuIMClient()
            await im.send_card(FEISHU_CHAT_ID, title, content, color)
        except Exception as exc:
            logger.warning("广播发送失败: %s", exc)
