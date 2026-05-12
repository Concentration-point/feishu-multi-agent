"""文案 fan-out 阶段：按平台分组并行执行 + 失败重试 + 定向重试 + LLM 兜底补写。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from agents.base import BaseAgent as _DefaultBaseAgent
from config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from memory.project import BriefProject, ContentMemory as _DefaultContentMemory

from .stage_runner import StageResult, detect_required_tool_failure

if TYPE_CHECKING:
    from agents.base import BaseAgent
    from memory.project import ContentMemory
    from orchestrator import Orchestrator


logger = logging.getLogger(__name__)


def _resolve_BaseAgent():
    """通过 orchestrator 模块属性获取 BaseAgent，让测试 monkey-patch 生效。"""
    import sys
    orch_mod = sys.modules.get("orchestrator")
    if orch_mod is not None:
        return getattr(orch_mod, "BaseAgent", _DefaultBaseAgent)
    return _DefaultBaseAgent


def _resolve_ContentMemory():
    """通过 orchestrator 模块属性获取 ContentMemory，让测试 monkey-patch 生效。"""
    import sys
    orch_mod = sys.modules.get("orchestrator")
    if orch_mod is not None:
        return getattr(orch_mod, "ContentMemory", _DefaultContentMemory)
    return _DefaultContentMemory


# 兜底补写最多重试次数
FALLBACK_MAX_RETRIES = 3


async def run_copywriter_fanout(
    orch: "Orchestrator",
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
    BaseAgent = _resolve_BaseAgent()
    ContentMemory = _resolve_ContentMemory()

    # ── 1. 分发前：拉全部 rows，按 platform 分组 ──
    try:
        proj = await orch._pm.load()
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
        result, agent = await orch._run_stage_with_agent(
            "copywriter", index=index, total=total,
        )
        return result, []

    groups: dict[str, list] = {}
    for row in rows:
        key = ((row.platform or "").strip()) or "通用"
        groups.setdefault(key, []).append(row)

    group_names = sorted(groups.keys())
    total_rows = len(rows)
    print(f"[Orchestrator] fan-out 分组: {group_names} (共 {total_rows} 行)")

    # dashboard 预建 sub lane
    orch._publish("pipeline.copywriter_fanout_started", {
        "groups": group_names,
        "rows_per_group": {k: len(v) for k, v in groups.items()},
        "concurrency_limit": 5,
    }, agent_role="copywriter", agent_name="文案")

    # ── 2. 分发前：Orchestrator 推状态到「撰写中」──
    try:
        current_status = await orch._read_current_status()
    except Exception:
        current_status = "撰写中"
    if current_status != "撰写中":
        try:
            await orch._pm.update_status("撰写中")
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
            record_id=orch.record_id,
            event_bus=orch._event_bus,
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
                failed, error, output_text = detect_required_tool_failure(output, agent)
                if failed:
                    return (platform, output_text, agent, error)
                return (platform, output_text, agent, "")
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
                failed, error, retry_output_text = detect_required_tool_failure(retry_output, retry_agent)
                if failed:
                    final_status[platform] = {
                        "ok": False,
                        "error": error,
                        "output": retry_output_text,
                        "agent": retry_agent,
                        "retried": True,
                    }
                    print(f"[Orchestrator] platform={platform} 重试必调工具校验失败: {error}")
                    continue
                final_status[platform] = {
                    "ok": True,
                    "output": retry_output_text,
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

    # ── 5. 完成度检查：重新读取全部内容行，逐条检查 draft ──
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
                record_id=orch.record_id,
                event_bus=orch._event_bus,
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
            await orch._pm.update_status("审核中")
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
        f"总耗时 {duration:.2f}s, "
        f"成稿 {len([r for r in (check_rows or []) if (r.draft or '').strip()])}/{len(check_rows or [])}"
    )

    return StageResult(
        role_id="copywriter",
        ok=all_ok,
        duration_sec=duration,
        output=stage_output,
        error=stage_error,
    ), []


def build_copy_fallback_prompt(proj: BriefProject, row) -> str:
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


async def ensure_copywriter_drafts(orch: "Orchestrator", project_name: str) -> int:
    """文案阶段后兜底：扫 content_rows，对 draft 为空的行用 LLM 补写（最多 3 次重试）。

    底层逻辑：
      - 不走完整 ReAct，单次调 LLM 生成成稿（成本/延时最小化）
      - 兜底补写只调 ContentMemory.write_draft，不进经验池、不经过审核工具
      - 单条最多重试 FALLBACK_MAX_RETRIES 次，每次用更直接的 system prompt
      - 任何一条补写失败不影响其余，也不阻断主流程

    返回实际补写成功的行数。
    """
    ContentMemory = _resolve_ContentMemory()
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
    orch._publish("copywriter.fallback.started", {
        "empty_count": len(empty_rows),
        "total_count": len(rows),
    }, agent_role="copywriter", agent_name="文案")

    try:
        from openai import AsyncOpenAI
        proj = await orch._pm.load()
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
        prompt = orch._build_copy_fallback_prompt(proj, row)
        draft = ""
        last_error = ""

        for attempt in range(1, FALLBACK_MAX_RETRIES + 1):
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
                    attempt, FALLBACK_MAX_RETRIES, row.record_id[:12],
                    "将重试" if attempt < FALLBACK_MAX_RETRIES else "已达上限",
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "文案兜底补写 attempt=%d/%d rid=%s 异常: %s",
                    attempt, FALLBACK_MAX_RETRIES, row.record_id[:12], last_error,
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
                orch._publish("content.updated", {
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

    orch._publish("copywriter.fallback.completed", {
        "filled": filled,
        "attempted": len(empty_rows),
    }, agent_role="copywriter", agent_name="文案")

    await orch._broadcast(
        title="文案补写兜底",
        content=(
            f"检测到 {len(empty_rows)}/{len(rows)} 条内容缺成稿，"
            f"已自动补写 {filled} 条" +
            (f"，仍有 {len(empty_rows) - filled} 条为空" if filled < len(empty_rows) else "")
        ),
        color="blue" if filled == len(empty_rows) else "red",
    )

    return filled
