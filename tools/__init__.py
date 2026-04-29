"""工具注册表 — 自动发现 + 统一调用接口。"""

from __future__ import annotations

import importlib
import json
import logging
import os
import pkgutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

from config import TOOL_CB_THRESHOLD, TOOL_CB_RESET_SECONDS

logger = logging.getLogger(__name__)

# 绝对路径：固定在项目根 logs/，不受 cwd 影响；append-only，永不清空
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STATS_FILE = _PROJECT_ROOT / "logs" / "tool_calls.jsonl"


def _write_stat(record: dict) -> None:
    """追加一条工具调用记录到全局持久日志（跨运行累积，不清空）。"""
    try:
        _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        with _STATS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


@dataclass
class AgentContext:
    """工具执行时的上下文信息。"""
    record_id: str
    project_name: str
    role_id: str


class ToolRegistry:
    """自动扫描 tools/ 目录，注册所有工具的 SCHEMA + execute 函数。

    每个工具文件必须导出:
      - SCHEMA: dict — OpenAI function calling 格式的工具描述
      - execute: async (params: dict, context: AgentContext) -> str | dict
    """

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}
        # 熔断状态：{tool_name: {"failures": int, "open_since": float | None}}
        self._cb: dict[str, dict] = {}
        self._scan()

    def _scan(self) -> None:
        """扫描 tools/ 目录下所有 .py 文件（排除 __init__.py）。"""
        import tools as pkg
        for finder, name, ispkg in pkgutil.iter_modules(pkg.__path__):
            if name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"tools.{name}")
                schema = getattr(mod, "SCHEMA", None)
                execute = getattr(mod, "execute", None)
                if schema and execute:
                    tool_name = schema["function"]["name"]
                    self._tools[tool_name] = {
                        "schema": schema,
                        "execute": execute,
                    }
                    logger.debug("注册工具: %s", tool_name)
            except Exception as e:
                logger.warning("加载工具 %s 失败: %s", name, e)

        logger.info("工具注册完成，共 %d 个: %s",
                     len(self._tools), list(self._tools.keys()))

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tools(self, tool_names: list[str] | None = None) -> list[dict]:
        """返回 OpenAI function calling 格式的工具列表。

        Args:
            tool_names: 过滤列表，None 则返回全部
        """
        if tool_names is None:
            return [t["schema"] for t in self._tools.values()]
        return [
            self._tools[n]["schema"]
            for n in tool_names
            if n in self._tools
        ]

    def _cb_state(self, tool_name: str) -> dict:
        """获取或初始化工具的熔断状态。"""
        if tool_name not in self._cb:
            self._cb[tool_name] = {"failures": 0, "open_since": None}
        return self._cb[tool_name]

    def _cb_is_open(self, tool_name: str) -> bool:
        """检查熔断是否触发。超过恢复间隔则自动半开（允许一次试探）。"""
        state = self._cb_state(tool_name)
        if state["open_since"] is None:
            return False
        if time.monotonic() - state["open_since"] >= TOOL_CB_RESET_SECONDS:
            # 恢复到半开状态：重置计数，允许下次调用
            state["failures"] = 0
            state["open_since"] = None
            logger.info("工具 %s 熔断已恢复（超过 %.0fs 重置）", tool_name, TOOL_CB_RESET_SECONDS)
            return False
        return True

    async def call_tool(
        self, tool_name: str, params: dict, context: AgentContext
    ) -> str:
        """调用指定工具，返回工具结果；结构化对象会序列化为 JSON 字符串给 LLM。

        内置简单熔断：连续失败 TOOL_CB_THRESHOLD 次后开路，TOOL_CB_RESET_SECONDS 后自动恢复。
        """
        if tool_name not in self._tools:
            return f"错误: 工具 '{tool_name}' 不存在。可用工具: {self.tool_names}"

        if self._cb_is_open(tool_name):
            state = self._cb_state(tool_name)
            remaining = TOOL_CB_RESET_SECONDS - (time.monotonic() - state["open_since"])
            return (
                f"工具熔断中（连续失败 {TOOL_CB_THRESHOLD} 次），"
                f"约 {remaining:.0f}s 后自动恢复，请稍后再试或换用其他工具"
            )

        t0 = time.monotonic()
        try:
            result = await self._tools[tool_name]["execute"](params, context)
            duration_ms = round((time.monotonic() - t0) * 1000)
            self._cb_state(tool_name)["failures"] = 0
            _write_stat({
                "event": "tool_call",
                "tool": tool_name,
                "success": True,
                "error": None,
                "duration_ms": duration_ms,
                "record_id": context.record_id,
                "role_id": context.role_id,
            })
            return result if isinstance(result, str) else json.dumps(
                result, ensure_ascii=False
            )
        except Exception as e:
            duration_ms = round((time.monotonic() - t0) * 1000)
            logger.error("工具 %s 执行异常: %s", tool_name, e, exc_info=True)
            _write_stat({
                "event": "tool_call",
                "tool": tool_name,
                "success": False,
                "error": type(e).__name__,
                "duration_ms": duration_ms,
                "record_id": context.record_id,
                "role_id": context.role_id,
            })
            state = self._cb_state(tool_name)
            state["failures"] += 1
            if state["failures"] >= TOOL_CB_THRESHOLD:
                state["open_since"] = time.monotonic()
                logger.warning(
                    "工具 %s 熔断触发（连续失败 %d 次），%.0fs 后恢复",
                    tool_name, TOOL_CB_THRESHOLD, TOOL_CB_RESET_SECONDS,
                )
            return f"工具执行错误: {type(e).__name__}: {e}"
