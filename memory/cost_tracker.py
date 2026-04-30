"""单项目 LLM 调用成本追踪器。

每次 LLM 调用 / 工具调用后追加写入 logs/tool_calls.jsonl（JSONL 格式），
同时维护内存聚合供 API 查询：
  - 项目级：总 token、总调用次数
  - 角色级：token 明细 + 逐次 LLM 调用记录 + 工具调用计数
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_LOGS_DIR = Path(__file__).parent.parent / "logs"
_JSONL_PATH = _LOGS_DIR / "tool_calls.jsonl"


def _append_jsonl(entry: dict) -> None:
    """追加写入 JSONL，失败不影响主流程。"""
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with _JSONL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


class CostTracker:
    """LLM 调用 + 工具调用成本追踪器。GIL 保证 dict 操作原子。"""

    def __init__(self) -> None:
        self._stats: dict[str, dict] = {}

    # ── 内部辅助 ────────────────────────────────────────────────────

    def _project(self, record_id: str) -> dict:
        if record_id not in self._stats:
            self._stats[record_id] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
                "by_role": {},
            }
        return self._stats[record_id]

    def _role(self, record_id: str, role_id: str) -> dict:
        p = self._project(record_id)
        if role_id not in p["by_role"]:
            p["by_role"][role_id] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
                "llm_calls": [],   # 逐次 LLM 调用明细（供 Drawer 展示）
                "tool_calls": {},  # tool_name → 调用次数
            }
        return p["by_role"][role_id]

    # ── 公开 API ────────────────────────────────────────────────────

    def record(
        self,
        record_id: str,
        role_id: str,
        stage: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        iteration: int | None = None,
    ) -> None:
        """记录一次 LLM 调用的 token 消耗。"""
        total = prompt_tokens + completion_tokens
        ts = time.time()

        entry: dict = {
            "type": "llm",
            "ts": ts,
            "record_id": record_id,
            "role_id": role_id,
            "stage": stage,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total,
        }
        if iteration is not None:
            entry["iteration"] = iteration
        _append_jsonl(entry)

        # 项目级聚合
        p = self._project(record_id)
        p["prompt_tokens"] += prompt_tokens
        p["completion_tokens"] += completion_tokens
        p["total_tokens"] += total
        p["calls"] += 1

        # 角色级聚合
        r = self._role(record_id, role_id)
        r["prompt_tokens"] += prompt_tokens
        r["completion_tokens"] += completion_tokens
        r["total_tokens"] += total
        r["calls"] += 1
        r["llm_calls"].append({
            "ts": ts,
            "stage": stage,
            "iteration": iteration,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total,
        })

    def record_tool_call(
        self,
        record_id: str,
        role_id: str,
        tool_name: str,
        iteration: int | None = None,
    ) -> None:
        """记录一次工具调用（无 token 消耗，只计次数）。"""
        _append_jsonl({
            "type": "tool",
            "ts": time.time(),
            "record_id": record_id,
            "role_id": role_id,
            "tool_name": tool_name,
            "iteration": iteration,
        })

        r = self._role(record_id, role_id)
        r["tool_calls"][tool_name] = r["tool_calls"].get(tool_name, 0) + 1

    def get_project_summary(self, record_id: str) -> dict:
        """返回项目聚合摘要，by_role 含 LLM 调用明细和工具调用计数。"""
        p = self._stats.get(record_id)
        if not p:
            return {
                "record_id": record_id,
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "by_role": {},
            }
        by_role = {}
        for role_id, r in p["by_role"].items():
            by_role[role_id] = {
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "total_tokens": r["total_tokens"],
                "calls": r["calls"],
                "llm_calls": list(r["llm_calls"]),
                "tool_calls": dict(r["tool_calls"]),
            }
        return {
            "record_id": record_id,
            "calls": p["calls"],
            "prompt_tokens": p["prompt_tokens"],
            "completion_tokens": p["completion_tokens"],
            "total_tokens": p["total_tokens"],
            "by_role": by_role,
        }

    def get_all_summaries(self) -> list[dict]:
        """返回所有项目摘要（不含 llm_calls 明细，减少响应体积）。"""
        result = []
        for rid, p in self._stats.items():
            by_role = {}
            for role_id, r in p["by_role"].items():
                by_role[role_id] = {
                    "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"],
                    "total_tokens": r["total_tokens"],
                    "calls": r["calls"],
                }
            result.append({
                "record_id": rid,
                "calls": p["calls"],
                "prompt_tokens": p["prompt_tokens"],
                "completion_tokens": p["completion_tokens"],
                "total_tokens": p["total_tokens"],
                "by_role": by_role,
            })
        result.sort(key=lambda x: x["total_tokens"], reverse=True)
        return result


# 全局单例
cost_tracker = CostTracker()
