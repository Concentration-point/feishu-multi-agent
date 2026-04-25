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
        """返回内存中已知的 pipeline 列表。"""
        result = []
        for rid, events in self._history.items():
            started = next((e for e in events if e["event_type"] == "pipeline.started"), None)
            completed = next((e for e in events if e["event_type"] == "pipeline.completed"), None)
            result.append({
                "record_id": rid,
                "project_name": (started or {}).get("payload", {}).get("project_name", ""),
                "event_count": len(events),
                "status": "completed" if completed else "running",
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
        """列出磁盘上所有执行记录。"""
        if not _RUNS_DIR.exists():
            return []
        result = []
        for run_dir in _RUNS_DIR.iterdir():
            if not run_dir.is_dir():
                continue
            events_file = run_dir / "events.jsonl"
            if not events_file.exists():
                continue
            # 读取首行和末行获取摘要
            lines = events_file.read_text(encoding="utf-8").splitlines()
            lines = [l for l in lines if l.strip()]
            if not lines:
                continue
            try:
                first = json.loads(lines[0])
                last = json.loads(lines[-1])
            except json.JSONDecodeError:
                continue
            # 从 pipeline.started 事件提取项目名
            project_name = ""
            for l in lines[:3]:
                try:
                    e = json.loads(l)
                    if e.get("event_type") == "pipeline.started":
                        project_name = e.get("payload", {}).get("project_name", "")
                        break
                except json.JSONDecodeError:
                    continue
            result.append({
                "record_id": run_dir.name,
                "project_name": project_name,
                "event_count": len(lines),
                "status": "completed" if last.get("event_type") == "pipeline.completed" else "incomplete",
                "started_at": first.get("timestamp", 0),
                "completed_at": last.get("timestamp", 0),
            })
        result.sort(key=lambda x: x["started_at"], reverse=True)
        return result


# 全局单例
event_bus = EventBus()
