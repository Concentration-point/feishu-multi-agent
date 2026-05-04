from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from agents.base import BaseAgent
from config import (
    DELIVERY_DOC_ENABLED,
    EXPERIENCE_CONFIDENCE_THRESHOLD,
    EXPERIENCE_POOL_ROLE_ALLOWLIST,
    FEISHU_CHAT_ID,
    HUMAN_REVIEW_TIMEOUT,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    MAX_ROUTE_STEPS,
    REVIEW_MAX_RETRIES,
    STAGE_TIMEOUT_SECONDS,
    REVIEW_PASS_THRESHOLD_DEFAULT,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_NEED_REVISE,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_TIMEOUT,
    REVIEW_THRESHOLDS_BY_PROJECT_TYPE,
    ROUTE_TABLE,
    ROUTE_TERMINAL_STATUSES,
    STATUS_DONE,
    STATUS_PENDING,
    STATUS_PENDING_REVIEW,
    STATUS_REJECTED,
    ROLE_NAMES,
    WIKI_SPACE_ID,
)
from dashboard.event_bus import EventBus
from memory.experience import ExperienceManager
from memory.project import BriefProject, ContentMemory, ProjectMemory


logger = logging.getLogger(__name__)


def _clear_stage_checkpoint(record_id: str, role_id: str) -> None:
    """清除指定角色的所有 checkpoint 文件（含 fan-out 平台后缀变体）。

    策略：globbing checkpoints/{record_id}/{role_id}*.json。
    copywriter fan-out 子 Agent 的 checkpoint 文件名是 copywriter_小红书.json 这种，
    状态推进后必须一并清除，否则下次返工会错误恢复到旧平台对话。
    """
    from pathlib import Path
    try:
        checkpoint_dir = Path("checkpoints") / record_id
        if not checkpoint_dir.is_dir():
            return
        count = 0
        for path in checkpoint_dir.glob(f"{role_id}*.json"):
            path.unlink()
            count += 1
        if count > 0:
            logger.info("checkpoint 已清除 %d 文件: %s/%s*.json", count, record_id, role_id)
    except Exception as exc:
        logger.warning("checkpoint 清除失败: %s", exc)


@dataclass
class StageResult:
    role_id: str
    ok: bool
    duration_sec: float
    output: str = ""
    error: str = ""
    used_ask_human: bool = False  # Agent 内部调用了 ask_human 工具（有效人机交互，不算死循环）


class Orchestrator:
    # 默认流水线序列（仅用于 Dashboard 展示和 stage_total 计算）
    DEFAULT_PIPELINE = [
        "account_manager",
        "strategist",
        "copywriter",
        "reviewer",
        "project_manager",
    ]

    # 进程级缓存：「项目交付文档」父节点 token，避免每次重复查找/创建
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
        # 死循环防护：同状态连续 N 次后强制 halt，可在测试中覆写
        # AM 需要多轮人类交互，给更多机会（默认 3）
        self._no_progress_limit = 3
        self._pm = ProjectMemory(record_id)
        self._started = False  # 标记 pipeline.started 是否已发布

    def _publish(self, event_type: str, payload: dict | None = None, *, agent_role: str = "", agent_name: str = "") -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(
                self.record_id, event_type, payload,
                agent_role=agent_role,
                agent_name=agent_name,
            )
        except Exception:
            pass

    async def _read_current_status(self) -> str:
        """从 Bitable 读取项目当前状态，空状态自动初始化为「待处理」。

        区分两种"无状态"：
          - API 异常导致读不到 → 返回 ""，调用方按未知状态处理
          - 读到了但字段为空 → 兜底回写「待处理」并返回，避免动态路由空转直接退出
        """
        try:
            proj = await self._pm.load()
            status = (proj.status or "").strip()
            if not status:
                return await self._initialize_pending_status()
            return status
        except Exception as exc:
            logger.warning("动态路由：读取项目状态失败: %s", exc)
            return ""

    async def _initialize_pending_status(self) -> str:
        """空状态兜底：回写「待处理」到 Bitable 并返回。

        回写失败仅记录警告，仍返回 STATUS_PENDING——动态路由能正常推进比 Bitable 同步更优先。
        下次 _read_current_status 还会再次尝试初始化，最终一致。
        """
        print(f"[Orchestrator] 项目状态为空，自动初始化为「{STATUS_PENDING}」")
        try:
            await self._pm.update_status(STATUS_PENDING)
        except Exception as exc:
            logger.warning("初始化空状态为「%s」失败: %s", STATUS_PENDING, exc)
            print(
                f"[Orchestrator] 警告: 空状态回写失败（不阻断主流程）: "
                f"{type(exc).__name__}: {exc}"
            )
        return STATUS_PENDING

    def _resolve_next_role(self, status: str) -> str | None:
        """根据当前项目状态查路由表，返回下一个角色 ID 或 None（终止）。

        未匹配的状态返回 None，由调用方决定是否 fallback。
        """
        return ROUTE_TABLE.get(status)

    async def run(self) -> list[StageResult]:
        self._start_time = time.perf_counter()
        pending_experiences: list[dict] = []
        self._review_threshold = await self._get_review_threshold()

        try:
            proj = await self._pm.load()
        except Exception as exc:
            logger.exception("加载项目失败")
            print(f"[Orchestrator] 警告: 加载项目失败: {type(exc).__name__}: {exc}")
            return self.stage_results

        project_name = proj.client_name or "未知客户"
        project_type = (proj.project_type or "").strip()
        brief_summary = (proj.brief or "")[:200]
        current_status = (proj.status or "").strip()

        # 入口兜底：空状态视为新项目，初始化为「待处理」让动态路由能正常进入 AM
        if not current_status:
            current_status = await self._initialize_pending_status()

        self._publish("pipeline.started", {
            "project_name": project_name,
            "brief": brief_summary,
            "stages": list(self.pipeline),
            "stage_names": {k: v for k, v in ROLE_NAMES.items()},
            "routing": "dynamic",
            "initial_status": current_status,
        })
        self._started = True

        # ── 动态路由主循环 ──
        step = 0
        prev_role: str = ""
        # 死循环防护：同状态连续 N 次执行同角色后仍未推进 → 强制 halt
        # 触发场景：PM 拒绝排期但不更新状态、reviewer 漏写字段、任何 Agent 安全退出但状态机未推进
        no_progress_count = 0
        NO_PROGRESS_LIMIT = self._no_progress_limit

        # 入口：状态为「待人审」 → 恢复人审门禁
        if current_status == STATUS_PENDING_REVIEW:
            print(f"[Orchestrator] 检测到 status='待人审'，跳过 AM 直接进入恢复门禁")
            await self._broadcast(
                title="项目恢复",
                content=(
                    f"客户 **{project_name}** 状态为「待人审」，\n"
                    f"基于已保留的 Brief 解读继续等待审核"
                ),
                color="blue",
            )
            gate_outcome = await self._enter_human_review_gate(resumed=True)
            if gate_outcome != "approved":
                await self._finalize_pipeline_halted(project_name, gate_outcome)
                return self.stage_results
            # 待人审恢复且审核通过 → AM 阶段已完结，清除其 checkpoint 防止恢复过期上下文
            _clear_stage_checkpoint(self.record_id, "account_manager")
            current_status = await self._read_current_status()
        else:
            await self._broadcast(
                title="新项目启动",
                content=(
                    f"客户 **{project_name}** 的 Brief 已接收，虚拟团队自动组建中\n\n"
                    "动态路由模式: 根据项目状态自动调度下一角色"
                ),
                color="purple",
            )

        while step < self._max_route_steps:
            next_role = self._resolve_next_role(current_status)

            # 路由终止：状态已完成或已驳回
            if next_role is None:
                if current_status in ROUTE_TERMINAL_STATUSES:
                    print(f"[Orchestrator] 动态路由终止: status='{current_status}'")
                else:
                    print(f"[Orchestrator] 动态路由: 未知状态 '{current_status}'，终止")
                break

            # 特殊路由：人审门禁
            if next_role == "__human_review_gate__":
                print(f"[Orchestrator] 动态路由 → 人审门禁 (status='{current_status}')")
                gate_outcome = await self._enter_human_review_gate(resumed=False)
                if gate_outcome != "approved":
                    await self._finalize_pipeline_halted(project_name, gate_outcome)
                    return self.stage_results
                current_status = await self._read_current_status()
                continue

            status_at_entry = current_status  # 记录本次执行前的状态，用于死循环检测
            step += 1
            role_id = next_role
            role_name = ROLE_NAMES.get(role_id, role_id)

            prev_duration = self.stage_results[-1].duration_sec if self.stage_results else 0
            self._publish("pipeline.stage_changed", {
                "stage_index": step,
                "stage_total": len(self.pipeline),
                "current_role": role_id,
                "current_name": role_name,
                "prev_role": prev_role,
                "prev_duration": prev_duration,
                "routed_from_status": current_status,
            }, agent_role=role_id, agent_name=role_name)
            prev_role = role_id

            print(f"[Orchestrator] 动态路由: status='{current_status}' → {role_id} (step {step})")

            # ── 交接校验：上游必填字段检查 ──
            if role_id in ("strategist", "copywriter", "reviewer", "project_manager"):
                handoff_ok, handoff_reason = await self._validate_handoff(role_id, project_name)
                if not handoff_ok:
                    logger.error(
                        "交接校验失败: %s → %s: %s", current_status, role_id, handoff_reason,
                    )
                    await self._broadcast(
                        title="流水线异常 · 交接校验失败",
                        content=(
                            f"角色 **{role_name}** 无法启动\n"
                            f"原因：{handoff_reason}\n\n"
                            "请检查上游 Agent 产出是否完整，或人工介入修复数据后重新触发。"
                        ),
                        color="red",
                    )
                    await self._finalize_pipeline_halted(
                        project_name, f"handoff_failed:{role_id}",
                    )
                    return self.stage_results

            # ── 执行阶段（保留 copywriter fan-out 特殊路径）──
            if role_id == "copywriter":
                result, fanout_experiences = await self._run_copywriter_fanout(
                    index=step,
                    total=len(self.pipeline),
                )
                self.stage_results.append(result)
                pending_experiences.extend(fanout_experiences)
            else:
                result, agent = await self._run_stage_with_agent(
                    role_id,
                    index=step,
                    total=len(self.pipeline),
                )
                self.stage_results.append(result)

                if agent and agent._pending_experience:
                    pending_experiences.append(
                        {
                            "role_id": role_id,
                            "card": agent._pending_experience,
                            "agent": agent,
                        }
                    )

            # ── 广播阶段结果 ──
            if result.ok:
                summary = result.output[:200] if result.output else "已完成"
                is_truncated = result.output.startswith("[TRUNCATED:")
                await self._broadcast(
                    title=f"{role_name} 完成{'（输出截断）' if is_truncated else ''}",
                    content=f"耗时 {result.duration_sec:.1f}s\n\n{summary}",
                    color="orange" if is_truncated else "blue",
                )
                if is_truncated:
                    logger.warning(
                        "阶段 %s 输出被截断（达到 max_iterations），结果可能不完整", role_id
                    )
            else:
                await self._broadcast(
                    title="流水线异常",
                    content=f"阶段 **{role_name}** 执行失败\n\n`{result.error[:300]}`",
                    color="red",
                )
                # 回写 Bitable 让运营侧可从表格感知失败（_safe_update 写失败仅 warn，不影响主流程）
                ts = time.strftime("%m-%d %H:%M")
                await self._pm.write_agent_error_log(
                    f"[{ts}][{role_id}] {result.error[:200]}"
                )

            # ── 文案完成后二次兜底：fan-out 已做完成度检查 + 重试，此处为安全网 ──
            # 无论 fan-out 返回 ok=True/False 都执行安全网（部分完成带缺口时 ok=False 但仍需兜底）
            if role_id == "copywriter":
                filled = await self._ensure_copywriter_drafts(project_name)

                # 安全网：兜底后再次确认，仍有空行则阻断
                try:
                    cm = ContentMemory()
                    rows = await cm.list_by_project(project_name)
                    still_empty = [r for r in rows if not (r.draft or "").strip()]
                except Exception as exc:
                    logger.warning("文案安全网读行失败: %s", exc)
                    still_empty = []

                if rows and not still_empty:
                    # 重新读取 Bitable 最新状态（fan-out 可能已推进），避免用捕获的陈旧状态
                    fresh_status = await self._read_current_status()
                    if fresh_status == "撰写中":
                        print(
                            f"[Orchestrator] 文案安全网：{len(rows)} 条全部成稿，"
                            f"补充推进状态「撰写中」→「审核中」"
                        )
                        await self._pm.update_status("审核中")
                elif still_empty:
                    logger.error(
                        "文案安全网失败：fan-out 后仍有 %d/%d 条 draft 为空"
                        "（兜底补写成功 %d 条），阻断推进到审核",
                        len(still_empty), len(rows or []), filled,
                    )
                    empty_details = ", ".join(
                        f"{r.platform or '?'}/{(r.title or '?')[:15]}"
                        for r in still_empty
                    )
                    print(
                        f"[Orchestrator] 文案安全网 FAIL："
                        f"{len(still_empty)}/{len(rows)} 条仍为空 ({empty_details})"
                    )
                    # 子 Agent 不再推状态，但如果外部原因导致状态已是审核中则回退
                    fresh_status = await self._read_current_status()
                    if fresh_status == "审核中":
                        print(
                            f"[Orchestrator] 文案安全网：回退状态「审核中」→「撰写中」以待重试"
                        )
                        await self._pm.update_status("撰写中")

            # ── 审核完成后处理返工逻辑 ──
            if role_id == "reviewer":
                await self._handle_reviewer_retries()

            # ── AM 完成后兜底：LLM 可能漏调 update_status，Orchestrator 兜底推进 ──
            if role_id == "account_manager" and result.ok and current_status == "解读中":
                try:
                    proj_check = await self._pm.load()
                    has_brief = bool((proj_check.brief_analysis or "").strip())
                except Exception:
                    has_brief = bool(result.output.strip())
                if has_brief:
                    print(
                        f"[Orchestrator] AM 兜底: 阶段成功但 status 仍为「解读中」，"
                        f"自动推进到「待人审」"
                    )
                    try:
                        await self._pm.update_status(STATUS_PENDING_REVIEW)
                        current_status = STATUS_PENDING_REVIEW
                        _clear_stage_checkpoint(self.record_id, role_id)
                    except Exception as exc:
                        print(f"[Orchestrator] 警告: AM 兜底状态推进失败: {exc}")

            # ── 路由决策：读取最新状态，进入下一轮 ──
            current_status = await self._read_current_status()

            # ── 死循环防护：状态未推进则计数，连续超阈值即 halt ──
            # Agent 调用了 ask_human 工具 = 发生了有效人机交互，不算无效循环
            if current_status == status_at_entry:
                if result.used_ask_human:
                    print(
                        f"[Orchestrator] 死循环防护: status='{current_status}' 经 {role_id} 后未推进，"
                        f"但 Agent 调用了 ask_human（人机交互），重置计数"
                    )
                    no_progress_count = 0
                else:
                    no_progress_count += 1
                    print(
                        f"[Orchestrator] 死循环防护: status='{current_status}' 经 {role_id} 后未推进 "
                        f"({no_progress_count}/{NO_PROGRESS_LIMIT})"
                    )
                if no_progress_count >= NO_PROGRESS_LIMIT:
                    print(
                        f"[Orchestrator] 死循环防护触发: status='{current_status}' 连续 "
                        f"{NO_PROGRESS_LIMIT} 次执行 {role_id} 后状态未推进，强制 halt"
                    )
                    await self._broadcast(
                        title="流水线异常 · 强制中止",
                        content=(
                            f"项目 **{project_name}** 卡在状态 `{current_status}`\n"
                            f"连续 {NO_PROGRESS_LIMIT} 次执行 **{role_name}** 后状态未推进\n\n"
                            f"已强制中止以避免死循环，请人工介入排查上游产出"
                        ),
                        color="red",
                    )
                    await self._finalize_pipeline_halted(
                        project_name, f"no_progress:{current_status}"
                    )
                    return self.stage_results
            else:
                no_progress_count = 0
                # 状态已推进，清除该角色的 checkpoint（下次应全新执行）
                _clear_stage_checkpoint(self.record_id, role_id)

        else:
            print(f"[Orchestrator] 警告: 动态路由超出最大步数 {self._max_route_steps}，强制终止")

        # ── 流水线收尾 ──
        total_time = time.perf_counter() - self._start_time
        pass_rate = await self._get_review_pass_rate()
        pass_rate = await self._reconcile_review_pass_rate(pass_rate)
        pass_rate_display = f"{pass_rate:.0%}" if pass_rate is not None else "未知"
        review_status = await self._get_project_review_status()
        ok_count = sum(1 for item in self.stage_results if item.ok)
        await self._broadcast(
            title="项目交付就绪",
            content=(
                f"客户 **{project_name}** 全链路完成\n"
                f"- 动态路由步数: {step}\n"
                f"- 阶段完成: {ok_count}/{len(self.stage_results)}\n"
                f"- 审核通过率: {pass_rate_display}\n"
                f"- 审核阈值: {self._review_threshold:.0%}\n"
                f"- 红线风险: {self._review_red_flag or '无'}\n"
                f"- 人审状态: {review_status or '未知'}\n"
                f"- 总耗时: {total_time:.1f}s"
            ),
            color="green",
        )

        # ── 5 判据校验：决定发 pipeline.completed 还是 pipeline.aborted ──
        # 判据 1: 流水线已 finalize（执行到此处即满足）
        # 判据 2: route_steps ≥ 1
        # 判据 3: ok_count ≥ 1
        # 判据 4: 最终 status == "已完成"
        # 判据 5: pass_rate is not None and ≥ 阈值（覆盖"reviewer pass=true"）
        final_status = current_status or STATUS_DONE
        is_truly_completed = (
            step >= 1
            and ok_count >= 1
            and final_status == STATUS_DONE
            and pass_rate is not None
            and pass_rate >= self._review_threshold
        )

        abort_reason: str | None = None
        if not is_truly_completed:
            if step == 0:
                abort_reason = "route_zero_steps"
            elif ok_count == 0:
                abort_reason = "no_ok_stage"
            elif final_status != STATUS_DONE:
                abort_reason = f"status_not_done:{final_status}"
            elif pass_rate is None:
                abort_reason = "no_pass_rate"
            elif pass_rate < self._review_threshold:
                abort_reason = f"below_threshold:{pass_rate:.2f}<{self._review_threshold:.2f}"

        verdict_event = "pipeline.completed" if is_truly_completed else "pipeline.aborted"
        self._publish(verdict_event, {
            "total_time": total_time,
            "ok_count": ok_count,
            "total_stages": len(self.stage_results),
            "pass_rate": pass_rate,
            "status": final_status,
            "route_steps": step,
            "verdict": "completed" if is_truly_completed else "aborted",
            "abort_reason": abort_reason,
            "review_threshold": self._review_threshold,
        })

        # ── 生成飞书交付云文档 ──
        if DELIVERY_DOC_ENABLED and WIKI_SPACE_ID and current_status in (STATUS_DONE, None):
            try:
                doc_url = await self._generate_delivery_document(project_name)
                if doc_url:
                    self._publish("delivery_doc.created", {"url": doc_url, "project_name": project_name})
            except Exception as exc:
                logger.warning("交付文档生成失败（不影响主流程）: %s", exc)
                print(f"[Orchestrator] 警告: 交付文档生成失败: {type(exc).__name__}: {exc}")

        await self._settle_experiences(pending_experiences, project_name, pass_rate)
        await self._append_evolution_log(project_name, project_type, pass_rate, pending_experiences)
        return self.stage_results

    async def _run_stage_with_agent(
        self,
        role_id: str,
        *,
        index: int,
        total: int,
    ) -> tuple[StageResult, BaseAgent | None]:
        print("=" * 60)
        print(f"[Orchestrator] 启动第 {index}/{total} 阶段: {role_id}")
        print("=" * 60)

        start = time.perf_counter()
        try:
            agent = BaseAgent(role_id=role_id, record_id=self.record_id, event_bus=self._event_bus)
            output = await asyncio.wait_for(agent.run(), timeout=STAGE_TIMEOUT_SECONDS)
            duration = time.perf_counter() - start
            print(f"[Orchestrator] 阶段 {role_id} 完成，耗时 {duration:.2f} 秒")
            return StageResult(
                role_id=role_id, ok=True, duration_sec=duration,
                output=output or "",
                used_ask_human=getattr(agent, '_used_ask_human', False),
            ), agent
        except asyncio.TimeoutError:
            duration = time.perf_counter() - start
            message = f"阶段超时（>{STAGE_TIMEOUT_SECONDS:.0f}s），强制中止"
            print(f"[Orchestrator] 阶段 {role_id} 超时，耗时 {duration:.2f} 秒")
            logger.error("阶段 %s 超时 (>%ss)", role_id, STAGE_TIMEOUT_SECONDS)
            return StageResult(role_id=role_id, ok=False, duration_sec=duration, error=message), None
        except Exception as exc:
            duration = time.perf_counter() - start
            message = f"{type(exc).__name__}: {exc}"
            print(f"[Orchestrator] 阶段 {role_id} 异常，耗时 {duration:.2f} 秒: {message}")
            logger.exception("阶段 %s 执行异常", role_id)
            return StageResult(role_id=role_id, ok=False, duration_sec=duration, error=message), None

    async def _run_copywriter_fanout(
        self,
        *,
        index: int,
        total: int,
    ) -> tuple[StageResult, list[dict]]:
        """Copywriter 阶段 fan-out: 分发前计数 → 分组 → 推状态 → 并行执行 → 完成度检查 → 重试 → 推审核。

        状态流转权在编排层：子 Agent 只能写内容，不能推状态。
        完成度检查确保所有内容行都有成稿后才推进到审核。
        """
        print("=" * 60)
        print(f"[Orchestrator] 启动第 {index}/{total} 阶段: copywriter (fan-out)")
        print("=" * 60)

        start = time.perf_counter()

        # ── 1. 分发前：拉全部 rows，按 platform 分组 ──
        try:
            proj = await self._pm.load()
            rows = await ContentMemory().list_by_project(proj.client_name)
        except Exception as exc:
            duration = time.perf_counter() - start
            message = f"fan-out 拉取 rows 失败: {type(exc).__name__}: {exc}"
            logger.exception("fan-out 拉 rows 异常")
            return StageResult(
                role_id="copywriter", ok=False,
                duration_sec=duration, error=message,
            ), []

        if not rows:
            print("[Orchestrator] fan-out: 项目下无 content rows, 退化为单 agent")
            result, agent = await self._run_stage_with_agent(
                "copywriter", index=index, total=total,
            )
            pending = []
            if agent and agent._pending_experience:
                pending.append({
                    "role_id": "copywriter",
                    "card": agent._pending_experience,
                    "agent": agent,
                })
            return result, pending

        groups: dict[str, list] = {}
        for row in rows:
            key = ((row.platform or "").strip()) or "通用"
            groups.setdefault(key, []).append(row)

        group_names = sorted(groups.keys())
        total_rows = len(rows)
        print(f"[Orchestrator] fan-out 分组: {group_names} (共 {total_rows} 行)")

        # dashboard 预建 sub lane
        self._publish("pipeline.copywriter_fanout_started", {
            "groups": group_names,
            "rows_per_group": {k: len(v) for k, v in groups.items()},
            "concurrency_limit": 5,
        }, agent_role="copywriter", agent_name="文案")

        # ── 2. 分发前：Orchestrator 推状态到「撰写中」──
        try:
            current_status = await self._read_current_status()
        except Exception:
            current_status = "撰写中"
        if current_status != "撰写中":
            try:
                await self._pm.update_status("撰写中")
                print("[Orchestrator] fan-out: 推状态到「撰写中」")
            except Exception as exc:
                print(f"[Orchestrator] 警告: 推状态失败: {exc}")

        # ── 3. 创建子 Agent — 每个 platform 一个，注入 content_rows ──
        def _make_row_summary(r) -> dict:
            return {
                "record_id": r.record_id,
                "title": r.title or "",
                "platform": r.platform or "",
                "content_type": r.content_type or "",
                "key_point": r.key_point or "",
                "target_audience": r.target_audience or "",
            }

        def _make_agent(platform: str, row_list: list) -> BaseAgent:
            return BaseAgent(
                role_id="copywriter",
                record_id=self.record_id,
                event_bus=self._event_bus,
                task_filter={
                    "platform": platform,
                    "content_rows": [_make_row_summary(r) for r in row_list],
                },
            )

        sub_agents: dict[str, BaseAgent] = {
            k: _make_agent(k, groups[k]) for k in group_names
        }

        # ── 4. 并行执行 + 失败组串行重试 1 次 ──
        _sem = asyncio.Semaphore(5)

        async def _run_with_sem(platform: str) -> tuple[str, str | None, BaseAgent | None, str]:
            """返回 (platform, output, agent, error)"""
            agent = sub_agents[platform]
            async with _sem:
                try:
                    output = await agent.run()
                    return (platform, output, agent, "")
                except Exception as exc:
                    return (platform, None, agent, f"{type(exc).__name__}: {exc}")

        parallel_start = time.perf_counter()
        tasks = [_run_with_sem(k) for k in group_names]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        parallel_duration = time.perf_counter() - parallel_start
        print(f"[Orchestrator] fan-out 并行执行完成, 耗时 {parallel_duration:.2f}s")

        # 失败组串行重试
        final_status: dict[str, dict] = {}
        for result in raw_results:
            if isinstance(result, BaseException):
                logger.error("fan-out 子任务抛非 Exception 异常（如 CancelledError），结果丢失: %s", result)
                print(f"[Orchestrator] 错误: fan-out 子任务异常退出: {type(result).__name__}: {result}")
                continue
            platform, output, agent, error = result
            if error:
                logger.warning(
                    "[fan-out] platform=%s 首次失败: %s, 准备串行重试",
                    platform, error,
                )
                print(f"[Orchestrator] 警告: platform={platform} 首次失败 {error}, 串行重试")
                retry_agent = _make_agent(platform, groups[platform])
                try:
                    retry_output = await retry_agent.run()
                    final_status[platform] = {
                        "ok": True,
                        "output": retry_output or "",
                        "agent": retry_agent,
                        "retried": True,
                    }
                    print(f"[Orchestrator] platform={platform} 重试成功")
                except Exception as retry_exc:
                    err_msg = f"{type(retry_exc).__name__}: {retry_exc}"
                    logger.warning("[fan-out] platform=%s 重试失败: %s", platform, err_msg)
                    print(f"[Orchestrator] platform={platform} 重试仍失败: {err_msg}")
                    final_status[platform] = {
                        "ok": False,
                        "error": err_msg,
                        "agent": retry_agent,
                        "retried": True,
                    }
            else:
                final_status[platform] = {
                    "ok": True,
                    "output": output or "",
                    "agent": agent,
                    "retried": False,
                }

        # ── 5. 收集 pending experiences ──
        pending_experiences: list[dict] = []
        for platform in group_names:
            ag = final_status[platform].get("agent")
            if ag and ag._pending_experience:
                pending_experiences.append({
                    "role_id": "copywriter",
                    "card": ag._pending_experience,
                    "agent": ag,
                    "task_filter": {"platform": platform},
                })

        # ── 6. 完成度检查：重新读取全部内容行，逐条检查 draft ──
        retry_filled = 0
        try:
            check_rows = await ContentMemory().list_by_project(proj.client_name)
        except Exception as exc:
            logger.warning("fan-out 完成度检查读行失败: %s", exc)
            check_rows = []

        empty_rows = [r for r in check_rows if not (r.draft or "").strip()] if check_rows else []

        if empty_rows and len(empty_rows) <= 2:
            # 少量缺失 → 对缺失条目单独重试一次（完整 ReAct Agent）
            print(
                f"[Orchestrator] fan-out 完成度检查：{len(empty_rows)}/{len(check_rows)} 条缺失，"
                f"启动定向重试"
            )
            empty_details = ", ".join(
                f"{r.platform or '?'}/{r.record_id[:12]}..."
                f"{r.title[:20] if r.title else '?'}"
                for r in empty_rows
            )
            logger.warning("fan-out 定向重试: %s", empty_details)

            # 按 platform 分组缺失行，为每个平台创建一个重试 agent
            retry_groups: dict[str, list] = {}
            for r in empty_rows:
                key = ((r.platform or "").strip()) or "通用"
                retry_groups.setdefault(key, []).append(r)

            for retry_platform, retry_rows in retry_groups.items():
                retry_agent = BaseAgent(
                    role_id="copywriter",
                    record_id=self.record_id,
                    event_bus=self._event_bus,
                    task_filter={
                        "platform": retry_platform,
                        "content_rows": [_make_row_summary(r) for r in retry_rows],
                        # 告诉 Agent 这是重试
                        "is_retry": True,
                        "retry_reason": (
                            f"上一轮 {retry_platform} 子 Agent 完成后，"
                            f"以下 {len(retry_rows)} 条内容行 draft 仍为空，"
                            f"请重新撰写。"
                        ),
                    },
                )
                try:
                    retry_output = await retry_agent.run()
                    # 重试后再次读取验证
                    try:
                        verify_rows = await ContentMemory().list_by_project(proj.client_name)
                        still_empty = [
                            r for r in verify_rows
                            if not (r.draft or "").strip()
                            and r.record_id in {rr.record_id for rr in retry_rows}
                        ]
                        retry_filled += len(retry_rows) - len(still_empty)
                        print(
                            f"[Orchestrator] 定向重试 platform={retry_platform}: "
                            f"尝试 {len(retry_rows)} 条，成功 {len(retry_rows) - len(still_empty)} 条"
                        )
                    except Exception:
                        pass
                    # 收集重试 agent 的经验
                    if retry_agent._pending_experience:
                        pending_experiences.append({
                            "role_id": "copywriter",
                            "card": retry_agent._pending_experience,
                            "agent": retry_agent,
                            "task_filter": {"platform": retry_platform, "is_retry": True},
                        })
                except Exception as retry_exc:
                    logger.warning(
                        "fan-out 定向重试失败 platform=%s: %s",
                        retry_platform, retry_exc,
                    )
                    print(
                        f"[Orchestrator] 定向重试 platform={retry_platform} 异常: "
                        f"{type(retry_exc).__name__}: {retry_exc}"
                    )

            # 重试后再次检查
            try:
                check_rows = await ContentMemory().list_by_project(proj.client_name)
                empty_rows = [r for r in check_rows if not (r.draft or "").strip()]
            except Exception:
                pass

        # ── 7. 完成度判定 + 状态推进 ──
        all_filled = check_rows and not empty_rows
        large_missing = empty_rows and len(empty_rows) > 2

        if all_filled:
            print(
                f"[Orchestrator] fan-out 完成度检查通过：{len(check_rows)} 条全部成稿，"
                f"推进状态「撰写中」→「审核中」"
            )
            try:
                await self._pm.update_status("审核中")
            except Exception as exc:
                print(f"[Orchestrator] 警告: 状态推进失败: {exc}")
        elif large_missing:
            logger.error(
                "fan-out 大面积缺失：%d/%d 条 draft 为空，保持「撰写中」等待人工介入",
                len(empty_rows), len(check_rows or []),
            )
            empty_details = ", ".join(
                f"{r.platform or '?'}/{r.record_id[:12]}..."
                for r in empty_rows[:5]
            )
            print(
                f"[Orchestrator] fan-out 大面积缺失: "
                f"{len(empty_rows)}/{len(check_rows)} 条为空 ({empty_details}{'...' if len(empty_rows) > 5 else ''})，"
                f"保持「撰写中」"
            )
        elif empty_rows:
            # 少量缺失（重试后仍存在）— 告警但继续
            logger.warning(
                "fan-out 少量缺失（已重试）: %d/%d 条 draft 仍为空",
                len(empty_rows), len(check_rows or []),
            )

        # ── 8. 聚合 StageResult ──
        all_ok = all_filled  # 严格：仅当全部成稿才算完成；部分完成=未完成
        partial_gap = not all_filled and not large_missing and empty_rows
        duration = time.perf_counter() - start

        summary_lines = []
        for platform in group_names:
            st = final_status[platform]
            tag = "OK" if st["ok"] else "FAIL"
            if st.get("retried"):
                tag += "(retry)"
            detail = (st.get("output") or "")[:80] if st["ok"] else st.get("error", "")
            summary_lines.append(f"[{platform}] {tag}: {detail}")
        if retry_filled > 0:
            summary_lines.append(f"[retry] 定向重试补写 {retry_filled} 条")
        if empty_rows:
            summary_lines.append(
                f"[gap] {len(empty_rows)}/{len(check_rows or [])} 条仍为空"
            )
        if partial_gap:
            summary_lines.append("[partial] 部分完成带缺口 — 少量缺失但非大面积阻塞")
        stage_output = "fan-out 汇总:\n" + "\n".join(summary_lines)

        failed = [p for p in group_names if not final_status[p]["ok"]]
        stage_error = "" if not failed else "; ".join(
            f"{p}: {final_status[p].get('error', '')}" for p in failed
        )
        if empty_rows:
            gap_detail = ", ".join(
                f"{r.platform or '?'}/{r.record_id[:12]}..." for r in empty_rows
            )
            stage_error = (stage_error + "; " if stage_error else "") + f"缺失行: {gap_detail}"

        ok_cnt = sum(1 for v in final_status.values() if v["ok"])
        completion_label = (
            "全部完成" if all_filled
            else ("部分完成带缺口" if partial_gap else "未完成（大面积缺失）")
        )
        print(
            f"[Orchestrator] fan-out {completion_label}: {ok_cnt}/{len(group_names)} 平台成功, "
            f"收集 {len(pending_experiences)} 条经验, 总耗时 {duration:.2f}s, "
            f"成稿 {len([r for r in (check_rows or []) if (r.draft or '').strip()])}/{len(check_rows or [])}"
        )

        return StageResult(
            role_id="copywriter",
            ok=all_ok,
            duration_sec=duration,
            output=stage_output,
            error=stage_error,
        ), pending_experiences

    async def _handle_reviewer_retries(self) -> None:
        """审核后评估：检查通过率和红线，不达标则回退状态为"撰写中"让主循环路由接管。

        不再内部执行 agent，重试流程由主循环动态路由自然驱动：
        撰写中 → copywriter → 审核中 → reviewer → _handle_reviewer_retries → ...
        """
        pass_rate = await self._get_review_pass_rate()
        pass_rate = await self._reconcile_review_pass_rate(pass_rate)
        if pass_rate is None:
            print("[Orchestrator] 警告: 无法读取审核通过率，跳过返工重试逻辑")
            return

        review_red_flag = await self._get_review_red_flag()
        has_red_flag = bool(review_red_flag and review_red_flag.strip() and review_red_flag.strip() != "无")
        self._review_red_flag = review_red_flag.strip() if review_red_flag and review_red_flag.strip() else "无"

        if has_red_flag:
            print(f"[Orchestrator] 警告: 审核结构化红线字段命中风险：{self._review_red_flag}，触发一票否决")

        if pass_rate >= self._review_threshold and not has_red_flag:
            print(f"[Orchestrator] 审核通过率 {pass_rate:.0%}，达到阈值 {self._review_threshold:.0%}，且无红线风险，推进状态「审核中」→「排期中」")
            await self._write_auto_review_summary(pass_rate)
            try:
                await self._pm.update_status("排期中")
            except Exception as exc:
                print(f"[Orchestrator] 警告: 推进状态到排期中失败: {type(exc).__name__}: {exc}")
            return

        # 已达最大重试次数，强制推进到排期阶段，避免死循环
        if self.reviewer_retries >= REVIEW_MAX_RETRIES:
            print(
                f"[Orchestrator] 警告: 审核通过率 {pass_rate:.0%}，阈值 {self._review_threshold:.0%}，"
                f"重试已达上限 {REVIEW_MAX_RETRIES}，强制推进到排期阶段"
            )
            await self._write_auto_review_summary(pass_rate)
            try:
                await self._pm.update_status("排期中")
            except Exception as exc:
                print(f"[Orchestrator] 警告: 强制推进状态失败: {type(exc).__name__}: {exc}")
            return

        # 触发返工：回退状态为"撰写中"，由主循环路由自然驱动 copywriter → reviewer
        self.reviewer_retries += 1
        self._publish("pipeline.rejection", {
            "pass_rate": pass_rate,
            "attempt": self.reviewer_retries,
            "max_attempts": REVIEW_MAX_RETRIES,
        }, agent_role="reviewer", agent_name="审核")

        print(
            f"[Orchestrator] 警告: 审核通过率 {pass_rate:.0%} < {self._review_threshold:.0%} 或存在红线风险，"
            f"触发返工重试 {self.reviewer_retries}/{REVIEW_MAX_RETRIES}，状态改回 '撰写中'"
        )

        review_status = await self._get_project_review_status()
        await self._broadcast(
            title="审核驳回，触发返工",
            content=(
                f"通过率 **{pass_rate:.0%}**，阈值 **{self._review_threshold:.0%}**\n"
                f"红线风险：**{self._review_red_flag or '无'}**\n"
                f"人审状态：**{review_status or '未知'}**\n"
                f"文案将根据审核反馈修改，第 {self.reviewer_retries}/{REVIEW_MAX_RETRIES} 次重试"
            ),
            color="orange",
        )

        try:
            await self._pm.update_status("撰写中")
        except Exception as exc:
            print(f"[Orchestrator] 警告: 状态回退失败: {type(exc).__name__}: {exc}")

    async def _write_auto_review_summary(self, pass_rate: float) -> None:
        """审核完成后，由 Orchestrator 自动聚合行级审核结果写入 review_summary。

        不依赖 LLM 主动调工具，确保 _validate_handoff 的前置字段非空。
        若 review_summary 已有值（reviewer 手写过）则跳过，不覆盖。
        """
        try:
            proj = await self._pm.load()
            if (proj.review_summary or "").strip():
                return  # reviewer 已写，不覆盖

            project_name = proj.client_name or "未知客户"
            rows = await ContentMemory().list_by_project(project_name)

            passed = [r for r in rows if (r.review_status or "").strip() == REVIEW_STATUS_APPROVED]
            failed = [r for r in rows if (r.review_status or "").strip() not in (REVIEW_STATUS_APPROVED, "")]
            total = len(rows)

            lines = [
                f"审核通过率：{pass_rate:.0%}（{len(passed)}/{total} 条通过）",
                f"阈值：{self._review_threshold:.0%}",
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
            await self._pm.write_review_summary(
                summary,
                pass_rate,
                threshold=float(getattr(proj, "review_threshold", 0.0) or 0.0),
                red_flag=getattr(proj, "review_red_flag", "") or "",
            )
            print(f"[Orchestrator] 已自动写入 review_summary（{len(summary)} 字）")
        except Exception as exc:
            logger.warning("自动写入 review_summary 失败，跳过: %s", exc)
            print(f"[Orchestrator] 警告: 自动写入 review_summary 失败: {type(exc).__name__}: {exc}")

    async def _enter_human_review_gate(self, *, resumed: bool) -> str:
        """AM 之后的人审门禁，或从"待人审"恢复。

        返回:
            "approved"     → 放行，继续 pipeline 后续阶段
            "need_revise"  → 人类要求修改，已落盘 human_feedback + status 回"解读中"
            "timeout"      → 本轮超时，status 落"待人审"，下次触发可恢复
            "skipped"      → 降级跳过（AUTO_APPROVE / 无群聊 / brief_analysis 空），等价 approved
        """
        from tools.request_human_review import poll_for_human_reply

        try:
            proj = await self._pm.load()
        except Exception as exc:
            logger.exception("门禁加载项目失败")
            print(f"[Orchestrator] 警告: 门禁加载项目失败: {exc}")
            return "approved"

        brief_analysis = (proj.brief_analysis or "").strip()
        if not brief_analysis:
            print("[Orchestrator] 警告: brief_analysis 为空，跳过人审门禁")
            return "skipped"

        await self._pm.write_review_status(REVIEW_STATUS_PENDING)
        self._publish("human_review.started", {"resumed": resumed})

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
        await self._pm.write_pending_meta(meta_to_save)

        if status in ("approved", "skipped_auto_approve", "skipped_no_chat", "send_failed"):
            await self._pm.write_review_status(REVIEW_STATUS_APPROVED)
            await self._pm.clear_pending_state()
            try:
                await self._pm.update_status("策略中")
            except Exception as exc:
                print(f"[Orchestrator] 警告: 放行后更新状态失败: {exc}")
            self._publish("human_review.resolved", {
                "outcome": "approved", "feedback": feedback, "resumed": resumed,
            })
            await self._broadcast(
                title="人审通过",
                content=(
                    f"审核人已确认 Brief 解读，项目进入策略阶段\n\n"
                    f"{feedback[:200] or '（无额外意见）'}"
                ),
                color="green",
            )
            return "approved"

        if status == "need_revise":
            await self._pm.write_review_status(REVIEW_STATUS_NEED_REVISE)
            await self._pm.write_human_feedback(feedback)
            try:
                await self._pm.update_status("解读中")
            except Exception as exc:
                print(f"[Orchestrator] 警告: 回退状态失败: {exc}")
            self._publish("human_review.resolved", {
                "outcome": "need_revise", "feedback": feedback, "resumed": resumed,
            })
            await self._broadcast(
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
        await self._pm.write_review_status(REVIEW_STATUS_TIMEOUT)

        # 第二次超时 → 终止项目
        if prev_send_count >= 1:
            try:
                await self._pm.update_status(STATUS_REJECTED)
            except Exception as exc:
                print(f"[Orchestrator] 警告: 切换到已驳回状态失败: {exc}")
            await self._pm.clear_pending_state()
            self._publish("human_review.resolved", {
                "outcome": "timeout_final", "feedback": feedback, "resumed": resumed,
            })
            await self._broadcast(
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
            await self._pm.update_status(STATUS_PENDING_REVIEW)
        except Exception as exc:
            print(f"[Orchestrator] 警告: 切换到待人审状态失败: {exc}")
        self._publish("human_review.resolved", {
            "outcome": "timeout", "feedback": feedback, "resumed": resumed,
        })
        await self._broadcast(
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

    # 兜底补写最多重试次数
    _FALLBACK_MAX_RETRIES = 3

    async def _ensure_copywriter_drafts(self, project_name: str) -> int:
        """文案阶段后兜底：扫 content_rows，对 draft 为空的行用 LLM 补写（最多 3 次重试）。

        底层逻辑：
          - 不走完整 ReAct，单次调 LLM 生成成稿（成本/延时最小化）
          - 兜底补写只调 ContentMemory.write_draft，不进经验池、不经过审核工具
          - 单条最多重试 _FALLBACK_MAX_RETRIES 次，每次用更直接的 system prompt
          - 任何一条补写失败不影响其余，也不阻断主流程

        返回实际补写成功的行数。
        """
        try:
            cm = ContentMemory()
            rows = await cm.list_by_project(project_name)
        except Exception as exc:
            logger.exception("文案兜底读取内容行失败")
            print(f"[Orchestrator] 警告: 文案兜底读行失败: {exc}")
            return 0

        empty_rows = [r for r in rows if not (r.draft or "").strip()]
        if not empty_rows:
            print(f"[Orchestrator] 文案兜底：{len(rows)} 条内容行全部有成稿，跳过")
            return 0

        print(
            f"[Orchestrator] 文案兜底：{len(empty_rows)}/{len(rows)} 条内容行 draft 为空，启动 LLM 补写"
        )
        self._publish("copywriter.fallback.started", {
            "empty_count": len(empty_rows),
            "total_count": len(rows),
        }, agent_role="copywriter", agent_name="文案")

        try:
            from openai import AsyncOpenAI
            proj = await self._pm.load()
            client = AsyncOpenAI(
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.exception("文案兜底初始化 LLM 失败")
            print(f"[Orchestrator] 警告: 文案兜底初始化失败: {exc}")
            return 0

        # 兜底 LLM system prompts：从宽松到严格，逐次加压
        _FALLBACK_SYSTEM_PROMPTS = [
            (
                "你是资深内容营销文案。按目标平台调性生成完整成稿，"
                "不要解释、不要使用 ``` 代码块包裹，直接输出正文。"
                "严禁医疗化、绝对化、虚假宣传用语。"
            ),
            (
                "你必须生成完整的营销成稿正文。直接输出内容，"
                "一个字都不要解释，不要用代码块。"
                "即使对平台不熟悉，也要根据内容标题和核心卖点写出可发布的正文。"
            ),
            (
                "I NEED you to write a complete marketing content draft RIGHT NOW. "
                "Output the draft content DIRECTLY, NO explanations, NO code blocks. "
                "Write in Chinese. Even if you're uncertain about the platform, "
                "produce a publishable draft based on the title and key points. "
                "DO NOT refuse. DO NOT explain. JUST WRITE."
            ),
        ]

        filled = 0
        for row in empty_rows:
            prompt = self._build_copy_fallback_prompt(proj, row)
            draft = ""
            last_error = ""

            for attempt in range(1, self._FALLBACK_MAX_RETRIES + 1):
                try:
                    sys_idx = min(attempt - 1, len(_FALLBACK_SYSTEM_PROMPTS) - 1)
                    sys_prompt = _FALLBACK_SYSTEM_PROMPTS[sys_idx]
                    resp = await client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": prompt},
                        ],
                    )
                    draft = (resp.choices[0].message.content or "").strip()
                    if draft:
                        break
                    last_error = "LLM 返回空内容"
                    logger.warning(
                        "文案兜底补写 attempt=%d/%d rid=%s 返回空内容，%s",
                        attempt, self._FALLBACK_MAX_RETRIES, row.record_id[:12],
                        "将重试" if attempt < self._FALLBACK_MAX_RETRIES else "已达上限",
                    )
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning(
                        "文案兜底补写 attempt=%d/%d rid=%s 异常: %s",
                        attempt, self._FALLBACK_MAX_RETRIES, row.record_id[:12], last_error,
                    )

            if draft:
                try:
                    await cm.write_draft(row.record_id, draft, len(draft))
                    filled += 1
                    print(
                        f"[Orchestrator] 补写成功 rid={row.record_id[:12]}... "
                        f"title={row.title[:20]}... 字数={len(draft)}"
                    )
                    # 补发 Dashboard 事件，保证前端与兜底路径同步
                    self._publish("content.updated", {
                        "record_id": row.record_id,
                        "platform": getattr(row, "platform", ""),
                        "title": getattr(row, "title", ""),
                        "content_length": len(draft),
                        "via": "fallback",
                    }, agent_role="copywriter", agent_name="文案")
                except Exception as exc:
                    logger.exception("补写 write_draft 失败 rid=%s: %s", row.record_id[:12], exc)
            else:
                logger.error(
                    "文案兜底补写彻底失败 rid=%s 平台=%s title=%s: %s",
                    row.record_id[:12], row.platform, (row.title or "")[:30], last_error,
                )

        self._publish("copywriter.fallback.completed", {
            "filled": filled,
            "attempted": len(empty_rows),
        }, agent_role="copywriter", agent_name="文案")

        await self._broadcast(
            title="文案补写兜底",
            content=(
                f"检测到 {len(empty_rows)}/{len(rows)} 条内容缺成稿，"
                f"已自动补写 {filled} 条" +
                (f"，仍有 {len(empty_rows) - filled} 条为空" if filled < len(empty_rows) else "")
            ),
            color="blue" if filled == len(empty_rows) else "red",
        )

        return filled

    @staticmethod
    def _build_copy_fallback_prompt(proj: BriefProject, row) -> str:
        # 平台字数参考表
        _WORD_COUNT_HINT = {
            "小红书": "400-800",
            "抖音": "200-400（分镜脚本格式）",
            "视频号": "150-300",
            "公众号": "800-1500",
            "微博": "140-300",
        }
        wc_hint = _WORD_COUNT_HINT.get(row.platform or "", "300-500")

        parts = [
            "# 项目上下文",
            f"- 客户: {proj.client_name or '未填'}",
        ]
        if proj.project_type:
            parts.append(f"- 项目类型: {proj.project_type}")
        if proj.brand_tone:
            parts.append(f"- 品牌调性: {proj.brand_tone}")
        if (proj.dept_style or "").strip():
            parts.append(f"- 部门风格: {proj.dept_style}")

        parts += [
            "",
            "# 本条任务",
            f"- 内容标题: {row.title or '未填'}",
            f"- 目标平台: {row.platform or '未填'}",
            f"- 内容类型: {row.content_type or '未填'}",
            f"- 核心卖点: {row.key_point or '未填'}",
            f"- 目标人群: {row.target_audience or '未填'}",
            "",
            "# 输出要求",
            f"- 目标平台 {row.platform}，参考字数 {wc_hint}",
            "- 直接输出完整成稿正文，不要任何解释",
            "- 正文顶部用 <!-- 未命中精准对标，已用平台通用结构撰写 --> HTML 注释占位（一行即可）",
        ]
        return "\n".join(parts)

    async def _finalize_pipeline_halted(self, project_name: str, outcome: str) -> None:
        """流程在门禁被中断时的收尾：事件、耗时、不做经验沉淀。"""
        total_time = time.perf_counter() - self._start_time
        ok_count = sum(1 for item in self.stage_results if item.ok)
        self._publish("pipeline.halted", {
            "total_time": total_time,
            "ok_count": ok_count,
            "total_stages": len(self.stage_results),
            "outcome": outcome,
            "project_name": project_name,
        })
        print(
            f"[Orchestrator] 流程在人审门禁中断: outcome={outcome}, "
            f"阶段完成 {ok_count}/{len(self.stage_results)}, 总耗时 {total_time:.1f}s"
        )

    async def _get_review_threshold(self) -> float:
        try:
            proj = await self._pm.load()
            project_type = (proj.project_type or "").strip()
            return REVIEW_THRESHOLDS_BY_PROJECT_TYPE.get(project_type, REVIEW_PASS_THRESHOLD_DEFAULT)
        except Exception as exc:
            logger.exception("获取审核阈值失败")
            print(f"[Orchestrator] 警告: 获取审核阈值失败: {type(exc).__name__}: {exc}")
            return REVIEW_PASS_THRESHOLD_DEFAULT

    async def _get_review_summary(self) -> str:
        try:
            proj = await self._pm.load()
            return proj.review_summary or ""
        except Exception as exc:
            logger.exception("获取审核总评失败")
            print(f"[Orchestrator] 警告: 获取审核总评失败: {type(exc).__name__}: {exc}")
            return ""

    async def _get_review_red_flag(self) -> str:
        try:
            proj = await self._pm.load()
            return (proj.review_red_flag or "").strip()
        except Exception as exc:
            logger.exception("获取审核红线风险失败")
            print(f"[Orchestrator] 警告: 获取审核红线风险失败: {type(exc).__name__}: {exc}")
            return ""

    async def _get_project_review_status(self) -> str:
        try:
            proj = await self._pm.load()
            return getattr(proj, "review_status", "") or ""
        except Exception as exc:
            logger.exception("获取人审状态失败")
            print(f"[Orchestrator] 警告: 获取人审状态失败: {type(exc).__name__}: {exc}")
            return ""

    async def _get_review_pass_rate(self) -> float | None:
        try:
            proj = await self._pm.load()
            raw_value = proj.review_pass_rate
            if raw_value in (None, "", []):
                return 0.5
            return float(raw_value)
        except Exception as exc:
            logger.exception("读取审核通过率失败")
            print(f"[Orchestrator] 警告: 读取审核通过率失败: {type(exc).__name__}: {exc}")
            return None

    async def _compute_row_level_pass_rate(self) -> tuple[float | None, int, int]:
        """按内容行级 review_status 实际统计通过率。

        返回 (pass_rate, passed_count, total_count)。
        total==0 时 pass_rate 返回 None，表示没有可用于汇总的行。
        只承认 REVIEW_STATUS_APPROVED ("通过") 作为通过；空值、需修改、驳回、超时均不计入通过。
        """
        try:
            project_name = await self._get_project_name()
            if not project_name or project_name == "未知客户":
                return None, 0, 0
            cm = ContentMemory()
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

    async def _reconcile_review_pass_rate(
        self,
        project_level_rate: float | None,
    ) -> float | None:
        """对齐项目级字段和行级统计，不一致时以行级为准并回写项目主表。"""
        row_rate, passed, total = await self._compute_row_level_pass_rate()
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
            proj = await self._pm.load()
            await self._pm.write_review_summary(
                proj.review_summary or "",
                row_rate,
                threshold=float(getattr(proj, "review_threshold", 0.0) or 0.0),
                red_flag=getattr(proj, "review_red_flag", "") or "",
            )
        except Exception as exc:
            logger.exception("回写审核通过率失败")
            print(f"[Orchestrator] 警告: 回写审核通过率失败: {type(exc).__name__}: {exc}")

        return row_rate

    async def _get_project_name(self) -> str:
        try:
            proj = await self._pm.load()
            return proj.client_name or "未知客户"
        except Exception:
            return "未知客户"

    @staticmethod
    def _md_to_blocks(text: str) -> list[dict]:
        """把 LLM 产出的 Markdown 文本转换成飞书文档 block 列表。

        支持：## 标题、### 标题、- 列表、* 列表、--- 分隔线，以及行内 **bold** / *em* / `code` 剥离。
        """
        import re
        blocks: list[dict] = []
        for line in text.split("\n"):
            s = line.strip()
            if not s:
                continue
            if s.startswith("### "):
                blocks.append({"type": "heading3", "text": s[4:].strip()})
            elif s.startswith("## "):
                blocks.append({"type": "heading2", "text": s[3:].strip()})
            elif s.startswith("# "):
                blocks.append({"type": "heading2", "text": s[2:].strip()})
            elif s.startswith(("- ", "* ", "+ ")):
                clean = re.sub(r"\*\*(.+?)\*\*", r"\1", s[2:])
                blocks.append({"type": "bullet", "text": clean.strip()})
            elif s in ("---", "===", "***"):
                blocks.append({"type": "divider"})
            else:
                clean = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
                clean = re.sub(r"\*(.+?)\*", r"\1", clean)
                clean = re.sub(r"`(.+?)`", r"\1", clean)
                blocks.append({"type": "text", "text": clean})
        return blocks

    async def _get_delivery_parent_token(self, wiki) -> str:
        """查找或创建「项目交付文档」父节点，返回 node_token。进程级缓存，单次创建。"""
        if Orchestrator._delivery_parent_token:
            return Orchestrator._delivery_parent_token

        parent_title = "项目交付文档"
        existing = await wiki.find_node_by_title(WIKI_SPACE_ID, parent_title)
        if existing:
            Orchestrator._delivery_parent_token = existing["node_token"]
            return Orchestrator._delivery_parent_token

        # 取空间根 token：顶级节点的 parent_node_token 即空间根
        root_nodes = await wiki.list_nodes(WIKI_SPACE_ID)
        space_root_token = root_nodes[0].get("parent_node_token", "") if root_nodes else ""
        node = await wiki.create_node(WIKI_SPACE_ID, space_root_token, parent_title)
        Orchestrator._delivery_parent_token = node["node_token"]
        return Orchestrator._delivery_parent_token

    async def _generate_delivery_document(self, project_name: str) -> str | None:
        """流水线完成后，在飞书知识空间自动生成面向客户的交付云文档。

        返回文档 URL（成功时）或 None。
        文档内容面向客户，不包含内部审核数据。
        """
        from datetime import datetime
        from feishu.wiki import FeishuWikiClient

        wiki = FeishuWikiClient()
        proj = await self._pm.load()
        cm = ContentMemory()
        rows = await cm.list_by_project(project_name)

        # 统计数据
        from feishu.delivery_charts import compute_delivery_stats
        stats = compute_delivery_stats(rows)
        today = datetime.now().strftime("%Y-%m-%d")
        doc_title = f"{project_name}-交付报告-{today}"

        # 查找或创建「项目交付文档」父节点（进程级缓存，不重复创建）
        parent_token = await self._get_delivery_parent_token(wiki)

        existing = await wiki.find_node_by_title(WIKI_SPACE_ID, doc_title, parent_token)
        if existing:
            obj_token = existing.get("obj_token", "")
        else:
            node = await wiki.create_node(WIKI_SPACE_ID, parent_token, doc_title)
            obj_token = node.get("obj_token", "")

        if not obj_token:
            logger.warning("交付文档：无法获取 document_id")
            return None

        # 构建文档结构化块（面向客户）
        blocks: list[dict] = []

        # ── 交付概览（Callout 蓝色高亮块）──
        platforms_str = "、".join(stats["platform_counts"].keys()) if stats["platform_counts"] else "未指定"
        date_range = ""
        if stats["first_date"] and stats["last_date"]:
            date_range = f"{stats['first_date']} — {stats['last_date']}"
        elif stats["first_date"]:
            date_range = stats["first_date"]

        overview_lines = [
            f"📝 交付内容: {stats['total']} 篇",
            f"📡 覆盖平台: {platforms_str}",
        ]
        if date_range:
            overview_lines.append(f"📅 排期周期: {date_range}")
        if stats["pending"] > 0:
            overview_lines.append(f"⏳ 待确认: {stats['pending']} 篇")
        overview_lines.append(f"📆 交付日期: {today}")
        if proj.project_type:
            overview_lines.insert(0, f"📋 项目类型: {proj.project_type}")

        blocks.append({"type": "callout", "text": "\n".join(overview_lines), "emoji": "chart_with_upwards_trend", "bg_color": 5})
        blocks.append({"type": "divider"})

        # ── 需求理解 ──
        if proj.brief_analysis:
            blocks.append({"type": "heading2", "text": "需求理解"})
            blocks.extend(self._md_to_blocks(proj.brief_analysis))
            blocks.append({"type": "divider"})

        # ── 策略思路 ──
        if proj.strategy:
            blocks.append({"type": "heading2", "text": "策略思路"})
            blocks.extend(self._md_to_blocks(proj.strategy))
            blocks.append({"type": "divider"})

        # ── 内容清单表格 ──
        if rows:
            blocks.append({"type": "heading2", "text": "📋 内容清单"})
            table_header = ["#", "标题", "平台", "类型", "计划发布", "字数"]
            table_rows = [table_header]
            for idx, row in enumerate(rows, 1):
                table_rows.append([
                    str(idx),
                    (row.title or "未命名")[:20],
                    row.platform or "—",
                    row.content_type or "—",
                    row.publish_date or "待确认",
                    str(row.word_count) if row.word_count else "—",
                ])
            blocks.append({"type": "table", "rows": table_rows})

        # ── 各内容正文 ──
        for idx, row in enumerate(rows, 1):
            if row.draft:
                blocks.append({"type": "heading3", "text": f"{idx}. {row.title or '未命名'}"})
                blocks.extend(self._md_to_blocks(row.draft))

        if rows:
            blocks.append({"type": "divider"})

        # ── 投放概览（表格 + 图表）──
        if stats["platform_counts"]:
            blocks.append({"type": "heading2", "text": "📈 投放概览"})

            # 平台分布表
            pt_header = ["平台", "内容数", "内容类型", "字数区间"]
            pt_rows = [pt_header]
            for plat, cnt in stats["platform_counts"].items():
                plat_rows_data = [r for r in rows if (r.platform or "未指定") == plat]
                wc_list = [r.word_count for r in plat_rows_data if r.word_count > 0]
                wc_range = f"{min(wc_list)}~{max(wc_list)}" if wc_list else "—"
                pt_rows.append([
                    plat,
                    str(cnt),
                    stats["platform_types"].get(plat, "—"),
                    wc_range,
                ])
            blocks.append({"type": "table", "rows": pt_rows})

            # 图表（matplotlib，失败不影响主流程）
            try:
                from feishu.delivery_charts import generate_platform_bar_chart, generate_status_pie_chart

                bar_png = generate_platform_bar_chart(stats["platform_counts"])
                if bar_png:
                    blocks.append({"type": "image", "data": bar_png, "name": "platform_bar.png"})

                if stats["total"] > 0:
                    pie_png = generate_status_pie_chart(stats["scheduled"], stats["pending"])
                    if pie_png:
                        blocks.append({"type": "image", "data": pie_png, "name": "status_pie.png"})
            except ImportError:
                logger.info("matplotlib 未安装，跳过图表生成")
            except Exception as chart_exc:
                logger.warning("图表生成失败（不影响文档）: %s", chart_exc)

            blocks.append({"type": "divider"})

        # ── 待确认项（黄色 Callout）──
        pending_rows = [r for r in rows if not r.publish_date]
        if pending_rows:
            pending_text = "以下内容待贵方确认后安排发布：\n" + "\n".join(
                f"· 《{r.title or '未命名'}》— {r.platform or '未指定'}" for r in pending_rows
            )
            blocks.append({"type": "callout", "text": pending_text, "emoji": "warning", "bg_color": 3})
            blocks.append({"type": "divider"})

        # ── 交付摘要 ──
        if proj.delivery:
            blocks.append({"type": "heading2", "text": "交付总结"})
            blocks.extend(self._md_to_blocks(proj.delivery))
            blocks.append({"type": "divider"})

        # ── 署名 ──
        blocks.append({"type": "text", "text": f"智策传媒 · {today} 自动生成"})

        # 写入文档
        await wiki.write_delivery_doc(obj_token, blocks)
        doc_url = f"https://feishu.cn/docx/{obj_token}"

        print(f"[Orchestrator] 交付文档已生成: {doc_title} → {doc_url}")
        await self._broadcast(
            title="📄 交付文档已生成",
            content=f"客户 **{project_name}** 的交付报告已自动生成\n📎 {doc_url}",
            color="green",
        )
        return doc_url

    async def _append_evolution_log(
        self,
        project_name: str,
        project_type: str,
        pass_rate: float | None,
        pending_experiences: list[dict] | None = None,
    ) -> None:
        """将本次运行关键指标追加写入 evolution_log.json。写入失败只打日志不阻塞。"""
        import json as _json
        from datetime import datetime, timezone
        from pathlib import Path

        log_path = Path("evolution_log.json")

        # 从所有 Agent 实例汇总本次注入的经验条数
        experiences_injected = sum(
            getattr(item.get("agent"), "_injected_experience_count", 0)
            for item in (pending_experiences or [])
            if item.get("agent") is not None
        )

        # 统计内容行数
        content_count = 0
        try:
            rows = await ContentMemory().list_by_project(project_name)
            content_count = len(rows)
        except Exception:
            pass

        entry = {
            "run_id": self.record_id,
            "project_type": project_type or "未知",
            "experiences_injected": int(experiences_injected),
            "review_pass_rate": round(float(pass_rate), 4) if pass_rate is not None else 0.0,
            "rework_count": int(self.reviewer_retries),
            "content_count": int(content_count),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            if log_path.exists():
                existing = _json.loads(log_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            else:
                existing = []
            existing.append(entry)
            log_path.write_text(
                _json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("evolution_log.json 已追加: run_id=%s entries=%d", self.record_id, len(existing))
        except Exception as exc:
            logger.warning("evolution_log.json 写入失败（不阻塞主流程）: %s", exc)

    async def _settle_experiences(
        self,
        pending: list[dict],
        project_name: str,
        pass_rate: float | None,
    ) -> None:
        if not pending:
            print("[Orchestrator] 无经验卡片需要沉淀")
            return

        self._publish("experience.settle_started", {
            "total": len(pending),
            "project_name": project_name,
        })

        deduped: dict[tuple[str, str], dict] = {}
        for item in pending:
            platform = (item.get("task_filter") or {}).get("platform", "")
            deduped[(item["role_id"], platform)] = item
        unique_pending = list(deduped.values())

        em = ExperienceManager()
        total = len(unique_pending)
        passed = 0
        merged_count = 0
        settled = 0

        for item in unique_pending:
            role_id = item["role_id"]
            card = item["card"]
            agent_ref: BaseAgent | None = item.get("agent")

            # 角色白名单过滤：只有外部验证来源的角色经验才进入 L2 经验池。
            # copywriter 自评无外部验证；project_manager 为 LLM 通识；均只留 wiki 本地记录。
            if role_id not in EXPERIENCE_POOL_ROLE_ALLOWLIST:
                logger.info(
                    "[经验沉淀] 跳过 %s，该角色不在 L2 经验池白名单 %s",
                    role_id, sorted(EXPERIENCE_POOL_ROLE_ALLOWLIST),
                )
                continue

            stage_ok = any(result.ok and result.role_id == role_id for result in self.stage_results)

            knowledge_cited = False
            if agent_ref and hasattr(agent_ref, "_messages"):
                for message in agent_ref._messages:
                    if not isinstance(message, dict) or message.get("role") != "assistant":
                        continue
                    for tool_call in message.get("tool_calls") or []:
                        if not isinstance(tool_call, dict):
                            continue
                        fn_name = tool_call.get("function", {}).get("name", "")
                        if fn_name in {"search_knowledge", "get_experience"}:
                            knowledge_cited = True
                            break
                    if knowledge_cited:
                        break

            no_rework = True  # 白名单内角色均不存在返工惩罚场景

            confidence = self._calc_confidence(
                pass_rate=pass_rate,
                task_completed=stage_ok,
                no_rework=no_rework,
                knowledge_cited=knowledge_cited,
            )

            self._publish("experience.scored", {
                "role_id": role_id,
                "confidence": confidence,
                "threshold": EXPERIENCE_CONFIDENCE_THRESHOLD,
                "passed": confidence >= EXPERIENCE_CONFIDENCE_THRESHOLD,
                "factors": {
                    "pass_rate": pass_rate,
                    "task_completed": stage_ok,
                    "no_rework": no_rework,
                    "knowledge_cited": knowledge_cited,
                },
                "lesson": str(card.get("lesson", "") or "")[:80],
                "category": card.get("category", "未分类"),
            }, agent_role=role_id)

            if confidence < EXPERIENCE_CONFIDENCE_THRESHOLD:
                logger.info(
                    "[经验沉淀] 跳过 %s，置信度 %.2f < %.2f",
                    role_id,
                    confidence,
                    EXPERIENCE_CONFIDENCE_THRESHOLD,
                )
                continue

            passed += 1
            try:
                category = card.get("category", "未分类")
                lesson = str(card.get("lesson", "") or "")
                card.setdefault("title", f"{category} - {role_id} - {lesson[:18]}")
                card["source_project"] = project_name
                card["source_run"] = self.record_id
                card["source_stage"] = role_id
                card["review_status"] = await self._get_project_review_status()
                saved = await em.save_experience(card, confidence, project_name)
                # Agent 未自主写入 wiki 时，Orchestrator 兜底写入
                wiki_saved = None
                if not getattr(agent_ref, "_wiki_written", False):
                    wiki_saved = await em.save_to_wiki(card, confidence)
                if saved or wiki_saved:
                    settled += 1
                    self._publish("experience.saved", {
                        "role_id": role_id,
                        "category": category,
                        "confidence": confidence,
                        "lesson": lesson[:80],
                        "bitable_saved": bool(saved),
                        "wiki_saved": bool(wiki_saved),
                    }, agent_role=role_id)

                    optimize_roles = card.get("applicable_roles") or [role_id]
                    seen_roles: set[str] = set()
                    for optimize_role in optimize_roles:
                        optimize_role = str(optimize_role or role_id)
                        if optimize_role in seen_roles:
                            continue
                        seen_roles.add(optimize_role)
                        optimize_call = em.optimize_bucket(
                            optimize_role, category, project_name=project_name
                        )
                        optimize_summary = {}
                        if hasattr(optimize_call, "__await__"):
                            optimize_summary = await optimize_call
                        if optimize_summary:
                            if optimize_summary.get("merged_created", 0) > 0:
                                merged_count += 1
                                self._publish("experience.merging", {
                                    "role_id": optimize_role,
                                    "category": category,
                                    "existing_count": optimize_summary.get("after_dedup", 0),
                                }, agent_role=optimize_role)
                                self._publish("experience.merged", {
                                    "role_id": optimize_role,
                                    "category": category,
                                    "merged_from": optimize_summary.get("merged_deleted", 0),
                                    "new_count": optimize_summary.get("merged_created", 0),
                                }, agent_role=optimize_role)
                            if (
                                optimize_summary.get("dedup_deleted", 0) > 0
                                or optimize_summary.get("merged_created", 0) > 0
                            ):
                                self._publish("experience.optimized", {
                                    **optimize_summary,
                                }, agent_role=optimize_role)
                else:
                    logger.info("[经验沉淀] %s 被质量门槛或去重策略拦截，未落盘", role_id)
            except Exception as exc:
                logger.warning("[经验沉淀] %s 沉淀失败: %s", role_id, exc)

        # ── 经验进化统计输出 ──
        print("\n" + "-" * 60)
        print("  经验进化统计（自进化闭环）")
        print("-" * 60)
        print(f"  Hook 蒸馏产出:   {total} 条")
        print(f"  置信度阈值:     ≥ {EXPERIENCE_CONFIDENCE_THRESHOLD:.2f}")
        print(f"  打分通过:       {passed} 条")
        print(f"  去重合并:       {merged_count} 组")
        print(f"  最终沉淀:       {settled} 条（Bitable + Wiki 双写）")

        # 按角色统计沉淀来源
        role_stats: dict[str, int] = {}
        for item in unique_pending:
            rid = item["role_id"]
            role_stats[rid] = role_stats.get(rid, 0) + 1
        if role_stats:
            roles_line = " | ".join(f"{r}: {c}" for r, c in role_stats.items())
            print(f"  来源角色分布:   {roles_line}")

        # 展示沉淀样例（最多 2 条）
        sample_count = 0
        for item in unique_pending:
            card = item.get("card") or {}
            lesson = str(card.get("lesson", "") or "")[:60]
            if lesson and sample_count < 2:
                cat = card.get("category", "未分类")
                print(f"  样例 [{item['role_id']}][{cat}]: {lesson}...")
                sample_count += 1

        print("-" * 60)

        self._publish("experience.settle_completed", {
            "total_distilled": total,
            "passed_scoring": passed,
            "merged_groups": merged_count,
            "final_settled": settled,
            "project_name": project_name,
        })

    @staticmethod
    def _calc_confidence(
        pass_rate: float | None,
        task_completed: bool,
        no_rework: bool,
        knowledge_cited: bool,
    ) -> float:
        score = 0.0
        score += 0.4 * (pass_rate if pass_rate is not None else 0.5)
        score += 0.3 * (1.0 if task_completed else 0.0)
        score += 0.2 * (1.0 if no_rework else 0.0)
        score += 0.1 * (1.0 if knowledge_cited else 0.0)
        return round(score, 2)

    async def _validate_handoff(self, role_id: str, project_name: str) -> tuple[bool, str]:
        """交接校验：启动下游 Agent 前检查上游必填字段非空。

        返回 (True, "") 表示可以启动；(False, reason) 表示上游产出缺失，不应启动。
        读取失败时不阻塞（返回 True），让 Agent 自己报错。
        """
        try:
            proj = await self._pm.load()
        except Exception as exc:
            logger.warning("交接校验：读取项目失败，跳过校验: %s", exc)
            return True, ""

        if role_id == "strategist":
            if not (proj.brief_analysis or "").strip():
                return False, "策略师启动前必须有 brief_analysis（客户经理产出为空）"

        elif role_id == "copywriter":
            if not (proj.strategy or "").strip():
                return False, "文案启动前必须有 strategy（策略师产出为空）"
            try:
                rows = await ContentMemory().list_by_project(proj.client_name or project_name)
                if not rows:
                    return False, "文案启动前内容排期表必须有行（策略师未创建内容行）"
            except Exception as exc:
                logger.warning("交接校验：读取内容行失败，跳过行数检查: %s", exc)

        elif role_id == "reviewer":
            try:
                rows = await ContentMemory().list_by_project(proj.client_name or project_name)
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

    async def _broadcast(self, title: str, content: str, color: str) -> None:
        try:
            print(f"[广播] {title}: {content[:100]}")
        except UnicodeEncodeError:
            fallback = f"[broadcast] {title.encode('ascii', 'ignore').decode('ascii')}: {content[:100].encode('ascii', 'ignore').decode('ascii')}"
            print(fallback)
        if not FEISHU_CHAT_ID:
            return

        try:
            from feishu.im import FeishuIMClient

            im = FeishuIMClient()
            await im.send_card(FEISHU_CHAT_ID, title, content, color)
        except Exception as exc:
            logger.warning("广播发送失败: %s", exc)
