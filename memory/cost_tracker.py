"""单项目 LLM 调用成本追踪器。

每次 LLM 调用后记录 token 消耗到 logs/tool_calls.jsonl（JSONL 格式），
同时维护内存聚合供 API 查询和 Dashboard 展示。
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

_LOGS_DIR = Path(__file__).parent.parent / "logs"
_JSONL_PATH = _LOGS_DIR / "tool_calls.jsonl"


class CostTracker:
    """LLM 调用成本追踪器。GIL 保证 dict 操作原子，文件追加写入同理。"""

    def __init__(self) -> None:
        # {record_id: {"prompt_tokens": int, ...}}
        self._stats: dict[str, dict] = {}

    def _get_or_create(self, record_id: str) -> dict:
        if record_id not in self._stats:
            self._stats[record_id] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
                "by_role": {},
            }
        return self._stats[record_id]

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
        """记录一次 LLM 调用的 token 消耗，写入 JSONL 并更新内存聚合。"""
        total = prompt_tokens + completion_tokens
        entry: dict = {
            "ts": time.time(),
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

        # 追加写入 JSONL（失败不影响主流程）
        try:
            _LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with _JSONL_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

        # 内存聚合 —— 项目级
        s = self._get_or_create(record_id)
        s["prompt_tokens"] += prompt_tokens
        s["completion_tokens"] += completion_tokens
        s["total_tokens"] += total
        s["calls"] += 1

        # 内存聚合 —— 角色级
        if role_id not in s["by_role"]:
            s["by_role"][role_id] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
            }
        rs = s["by_role"][role_id]
        rs["prompt_tokens"] += prompt_tokens
        rs["completion_tokens"] += completion_tokens
        rs["total_tokens"] += total
        rs["calls"] += 1

    def get_project_summary(self, record_id: str) -> dict:
        """返回某项目的聚合成本摘要。"""
        s = self._stats.get(record_id)
        if not s:
            return {
                "record_id": record_id,
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "by_role": {},
            }
        return {
            "record_id": record_id,
            "calls": s["calls"],
            "prompt_tokens": s["prompt_tokens"],
            "completion_tokens": s["completion_tokens"],
            "total_tokens": s["total_tokens"],
            "by_role": {k: dict(v) for k, v in s["by_role"].items()},
        }

    def get_all_summaries(self) -> list[dict]:
        """返回所有项目的摘要列表，按总 token 降序。"""
        result = [self.get_project_summary(rid) for rid in self._stats]
        result.sort(key=lambda x: x["total_tokens"], reverse=True)
        return result


# 全局单例
cost_tracker = CostTracker()
