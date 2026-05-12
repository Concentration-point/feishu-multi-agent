"""单阶段执行：超时、必调工具校验、工具错误识别、checkpoint 清理、StageResult。"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agents.base import AgentResult, BaseAgent as _DefaultBaseAgent
from config import STAGE_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from agents.base import BaseAgent
    from orchestrator import Orchestrator


logger = logging.getLogger(__name__)


def _resolve_BaseAgent():
    """通过 orchestrator 模块属性访问 BaseAgent，让测试 monkey-patch orchestrator.BaseAgent 生效。"""
    import sys
    orch_mod = sys.modules.get("orchestrator")
    if orch_mod is not None:
        return getattr(orch_mod, "BaseAgent", _DefaultBaseAgent)
    return _DefaultBaseAgent


@dataclass
class StageResult:
    role_id: str
    ok: bool
    duration_sec: float
    output: str = ""
    error: str = ""
    used_ask_human: bool = False  # Agent 内部调用了 ask_human 工具（有效人机交互，不算死循环）


def detect_required_tool_failure(output, agent) -> tuple[bool, str, str]:
    """识别 Agent 必调工具契约失败，返回 (是否失败, 错误信息, 可展示输出)。"""
    output_text = ""
    missing: list[str] = []
    meta_check = None

    if isinstance(output, AgentResult):
        output_text = output.output or ""
        missing = list(output.missing_required_tools or [])
        meta = output.meta if isinstance(output.meta, dict) else {}
        meta_check = meta.get("required_tool_check")
        if isinstance(meta_check, dict):
            meta_missing = meta_check.get("missing") or []
            if isinstance(meta_missing, list):
                missing.extend(str(item) for item in meta_missing if item)
    else:
        output_text = output or ""

    agent_missing = getattr(agent, "missing_required_tools", None)
    if isinstance(agent_missing, list):
        missing.extend(str(item) for item in agent_missing if item)

    missing = sorted(set(missing))
    meta_failed = isinstance(meta_check, dict) and meta_check.get("ok") is False
    raw_output = str(output_text)
    lower_output = raw_output.lower()
    warning_only_failed = (
        "required_tool_missing" in lower_output
        or "required tool" in lower_output
        or ("必需工具" in raw_output and ("未调用" in raw_output or "缺失" in raw_output))
        or ("必调工具" in raw_output and ("未调用" in raw_output or "缺失" in raw_output))
    )

    if missing or meta_failed or warning_only_failed:
        if missing:
            error = f"required tool violation: missing {', '.join(missing)}"
        else:
            error = "required tool violation: warning-only output was treated as failure"
        return True, error, raw_output

    return False, "", raw_output


def detect_tool_error(agent) -> tuple[bool, str]:
    """识别被自然语言吞掉的工具错误。"""
    messages = getattr(agent, "_messages", None) or []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        lowered = content.lower()
        if (
            "feishuapierror" in lowered
            or "tool error" in lowered
            or "工具执行错误" in content
            or "宸ュ叿鎵ц閿欒" in content
            or content.startswith("错误:")
            or content.startswith("閿欒:")
        ):
            return True, content[:300]
    return False, ""


def clear_stage_checkpoint(record_id: str, role_id: str) -> None:
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


async def run_stage_with_agent(
    orch: "Orchestrator",
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
        BaseAgent = _resolve_BaseAgent()
        agent = BaseAgent(role_id=role_id, record_id=orch.record_id, event_bus=orch._event_bus)
        output = await asyncio.wait_for(agent.run(), timeout=STAGE_TIMEOUT_SECONDS)
        duration = time.perf_counter() - start
        failed, error, output_text = detect_required_tool_failure(output, agent)
        if failed:
            print(f"[Orchestrator] 阶段 {role_id} 必调工具校验失败，耗时 {duration:.2f} 秒: {error}")
            logger.error("阶段 %s 必调工具校验失败: %s", role_id, error)
            return StageResult(
                role_id=role_id, ok=False, duration_sec=duration,
                output=output_text,
                error=error,
                used_ask_human=getattr(agent, '_used_ask_human', False),
            ), agent
        tool_failed, tool_error = detect_tool_error(agent)
        if tool_failed:
            error = f"tool error detected: {tool_error}"
            logger.error("阶段 %s 工具错误: %s", role_id, tool_error)
            return StageResult(
                role_id=role_id, ok=False, duration_sec=duration,
                output=output_text,
                error=error,
                used_ask_human=getattr(agent, '_used_ask_human', False),
            ), agent
        print(f"[Orchestrator] 阶段 {role_id} 完成，耗时 {duration:.2f} 秒")
        return StageResult(
            role_id=role_id, ok=True, duration_sec=duration,
            output=output_text,
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


async def safe_write_agent_error_log(orch: "Orchestrator", message: str) -> None:
    """Best-effort error-log write; failures must not crash the pipeline."""
    try:
        writer = getattr(orch._pm, "write_agent_error_log", None)
        if writer is None:
            logger.warning("ProjectMemory missing write_agent_error_log; skipping error log write")
            return
        await writer(message)
    except Exception as exc:
        logger.warning("Agent error log write failed; continuing pipeline: %s", exc)
