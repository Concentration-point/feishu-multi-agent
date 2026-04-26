"""工具注册表 — 自动发现 + 统一调用接口。"""

from __future__ import annotations

import importlib
import json
import logging
import pkgutil
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


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

    async def call_tool(
        self, tool_name: str, params: dict, context: AgentContext
    ) -> str:
        """调用指定工具，返回工具结果；结构化对象会序列化为 JSON 字符串给 LLM。"""
        if tool_name not in self._tools:
            return f"错误: 工具 '{tool_name}' 不存在。可用工具: {self.tool_names}"
        try:
            result = await self._tools[tool_name]["execute"](params, context)
            return result if isinstance(result, str) else json.dumps(
                result, ensure_ascii=False
            )
        except Exception as e:
            logger.error("工具 %s 执行异常: %s", tool_name, e, exc_info=True)
            return f"工具执行错误: {type(e).__name__}: {e}"
