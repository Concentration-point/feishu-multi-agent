"""EventBus — 按项目隔离的异步事件总线 + 磁盘持久化。

事件实时推送到 SSE 订阅者，同时旁路写入 runs/{record_id}/events.jsonl。
服务重启后可从磁盘加载历史执行记录。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

_RUNS_DIR = Path(__file__).parent.parent / "runs"

# 进行中判据：最近 N 秒内有事件且没有终止事件 → "running"
_RUNNING_FRESH_SECONDS = 300

# 真正完成 5 判据中的最低通过率（追溯重分类老 jsonl 时的兜底，与 config.REVIEW_PASS_THRESHOLD_DEFAULT 对齐）
_RETRO_PASS_RATE_THRESHOLD = 0.6


class EventBus:
    """按 record_id 隔离的事件总线，支持全局订阅 + 磁盘持久化。"""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._global_queues: list[asyncio.Queue] = []
        self._history: dict[str, list[dict]] = {}

    def publish(
        self,
        record_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        agent_role: str = "",
        agent_name: str = "",
        round_num: int = 0,
    ) -> None:
        """发布事件到订阅者 + 写入磁盘。"""
        event = {
            "event_type": event_type,
            "timestamp": time.time(),
            "record_id": record_id,
            "agent_role": agent_role,
            "agent_name": agent_name,
            "round": round_num,
            "payload": payload or {},
        }

        # 存入内存历史
        if record_id not in self._history:
            self._history[record_id] = []
        self._history[record_id].append(event)

        # 旁路写入磁盘（失败只打日志）
        try:
            self._persist_event(record_id, event)
        except Exception as e:
            logger.warning("持久化事件失败 %s: %s", record_id, e)

        # 推送到项目订阅者
        for queue in self._queues.get(record_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        # 推送到全局订阅者
        for queue in self._global_queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, record_id: str) -> AsyncIterator[dict]:
        """订阅指定项目的事件流。"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        if record_id not in self._queues:
            self._queues[record_id] = []
        self._queues[record_id].append(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if queue in self._queues.get(record_id, []):
                self._queues[record_id].remove(queue)

    async def subscribe_all(self) -> AsyncIterator[dict]:
        """全局订阅：接收所有项目的事件。"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._global_queues.append(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if queue in self._global_queues:
                self._global_queues.remove(queue)

    def get_history(self, record_id: str) -> list[dict]:
        """返回内存中的事件历史。"""
        return list(self._history.get(record_id, []))

    def get_all_history(self) -> list[dict]:
        """返回所有项目的内存事件，按时间排序。"""
        all_events = []
        for events in self._history.values():
            all_events.extend(events)
        all_events.sort(key=lambda e: e.get("timestamp", 0))
        return all_events

    def list_pipelines(self) -> list[dict]:
        """返回内存中已知的 pipeline 列表（与磁盘版 list_runs 同分类规则）。"""
        now = time.time()
        result = []
        for rid, events in self._history.items():
            started = next((e for e in events if e["event_type"] == "pipeline.started"), None)
            classification = _classify_run(events, now)
            result.append({
                "record_id": rid,
                "project_name": (started or {}).get("payload", {}).get("project_name", ""),
                "event_count": len(events),
                "status": classification["status"],
                "abort_reason": classification.get("abort_reason"),
                "verdict": classification.get("verdict"),
                "started_at": events[0]["timestamp"] if events else 0,
            })
        result.sort(key=lambda x: x["started_at"], reverse=True)
        return result

    def close(self, record_id: str) -> None:
        """流水线结束后向所有订阅者发送结束信号。"""
        for queue in self._queues.get(record_id, []):
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # ── 磁盘持久化 ──

    @staticmethod
    def _persist_event(record_id: str, event: dict) -> None:
        """追加写入 runs/{record_id}/events.jsonl"""
        run_dir = _RUNS_DIR / record_id
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def has_run(record_id: str) -> bool:
        """检查某 record_id 是否有磁盘上的执行记录。"""
        return (_RUNS_DIR / record_id / "events.jsonl").exists()

    @staticmethod
    def load_run(record_id: str) -> list[dict]:
        """从磁盘加载执行记录。"""
        path = _RUNS_DIR / record_id / "events.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    @staticmethod
    def list_runs() -> list[dict]:
        """列出磁盘上所有执行记录，按 4 分类输出。

        status ∈ {completed, aborted, running, incomplete}：
            completed   — 5 判据全过的真正完成（新事件信任 verdict 字段；老事件追溯重分类）
            aborted     — 已终止但未达完成判据（pipeline.aborted / pipeline.halted / 老脏数据）
            running     — 末事件距今 < 5 分钟，且无终止事件
            incomplete  — 无终止事件且很久没动静（疑似进程死亡）
        """
        if not _RUNS_DIR.exists():
            return []
        result = []
        now = time.time()
        for run_dir in _RUNS_DIR.iterdir():
            if not run_dir.is_dir():
                continue
            events_file = run_dir / "events.jsonl"
            if not events_file.exists():
                continue
            lines = [l for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            if not lines:
                continue

            events: list[dict] = []
            for line in lines:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if not events:
                continue

            # 项目名从 pipeline.started 事件提取
            project_name = ""
            for e in events[:5]:
                if e.get("event_type") == "pipeline.started":
                    project_name = e.get("payload", {}).get("project_name", "")
                    break

            classification = _classify_run(events, now)
            result.append({
                "record_id": run_dir.name,
                "project_name": project_name,
                "event_count": len(events),
                "status": classification["status"],
                "abort_reason": classification.get("abort_reason"),
                "verdict": classification.get("verdict"),
                "started_at": events[0].get("timestamp", 0),
                "completed_at": events[-1].get("timestamp", 0),
            })
        result.sort(key=lambda x: x["started_at"], reverse=True)
        return result


def _classify_run(events: list[dict], now: float) -> dict:
    """根据事件序列判定 run 的 4 状态分类。

    优先级：
      1. 末事件 == pipeline.completed → 信任 verdict（新事件）；无 verdict 则按 5 判据追溯重分类（老事件）
      2. 末事件 == pipeline.aborted → aborted
      3. 末事件 == pipeline.halted    → aborted（人审驳回 / 超时）
      4. 末事件距今 < 5 分钟          → running
      5. 其它                         → incomplete
    """
    if not events:
        return {"status": "incomplete"}

    last = events[-1]
    last_type = last.get("event_type", "")
    last_payload = last.get("payload", {}) or {}
    last_ts = last.get("timestamp", 0)

    if last_type == "pipeline.completed":
        # 新事件已带 verdict 字段（orchestrator.py 写入），直接信任
        verdict = last_payload.get("verdict")
        if verdict == "completed":
            return {"status": "completed", "verdict": "completed"}
        if verdict == "aborted":
            return {
                "status": "aborted",
                "verdict": "aborted",
                "abort_reason": last_payload.get("abort_reason"),
            }
        # 老事件无 verdict，用 5 判据反推（追溯重分类）
        route_steps = last_payload.get("route_steps", 0) or 0
        ok_count = last_payload.get("ok_count", 0) or 0
        status_field = last_payload.get("status", "")
        pass_rate = last_payload.get("pass_rate")
        threshold = last_payload.get("review_threshold", _RETRO_PASS_RATE_THRESHOLD)

        passed_all = (
            route_steps >= 1
            and ok_count >= 1
            and status_field == "已完成"
            and pass_rate is not None
            and pass_rate >= threshold
        )
        if passed_all:
            return {"status": "completed", "verdict": "completed"}
        # 推断老脏数据的 abort_reason
        if route_steps == 0:
            reason = "route_zero_steps"
        elif ok_count == 0:
            reason = "no_ok_stage"
        elif status_field != "已完成":
            reason = f"status_not_done:{status_field or 'empty'}"
        elif pass_rate is None:
            reason = "no_pass_rate"
        else:
            reason = f"below_threshold:{pass_rate:.2f}<{threshold:.2f}"
        return {
            "status": "aborted",
            "verdict": "aborted_retro",
            "abort_reason": reason,
        }

    if last_type == "pipeline.aborted":
        return {
            "status": "aborted",
            "verdict": "aborted",
            "abort_reason": last_payload.get("abort_reason"),
        }

    if last_type == "pipeline.halted":
        return {
            "status": "aborted",
            "verdict": "halted",
            "abort_reason": f"halted:{last_payload.get('outcome', 'unknown')}",
        }

    # 没有任何终止事件
    if last_ts and now - last_ts < _RUNNING_FRESH_SECONDS:
        return {"status": "running"}

    return {"status": "incomplete"}


# 全局单例
event_bus = EventBus()
