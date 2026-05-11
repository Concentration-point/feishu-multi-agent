from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as app_main


class _ClosedPipeline:
    def close(self) -> None:
        return None


def _event_payload(
    *,
    record_id: str = "rec_dedup",
    event_id: str | None = "evt_1",
    create_time: str | None = "1710000000000",
    retry_count: int | None = None,
) -> dict:
    header = {
        "event_type": "bitable.record.created_v1",
        "token": "expected-token",
    }
    if event_id is not None:
        header["event_id"] = event_id
    if create_time is not None:
        header["create_time"] = create_time
    if retry_count is not None:
        header["retry_count"] = retry_count

    return {
        "schema": "2.0",
        "header": header,
        "event": {"record_id": record_id},
    }


@pytest.fixture
def webhook_client(monkeypatch):
    launched_record_ids: list[str] = []

    def fake_launch_pipeline(record_id: str) -> _ClosedPipeline:
        launched_record_ids.append(record_id)
        return _ClosedPipeline()

    def fake_track_task(pipeline: _ClosedPipeline) -> None:
        pipeline.close()
        return None

    monkeypatch.setattr(app_main, "WEBHOOK_VERIFICATION_TOKEN", "expected-token")
    monkeypatch.setattr(app_main, "_launch_pipeline", fake_launch_pipeline)
    monkeypatch.setattr(app_main, "_track_task", fake_track_task)
    app_main._processed_record_ids.clear()
    app_main._running_record_ids.clear()
    app_main._record_task_map.clear()

    yield TestClient(app_main.app), launched_record_ids

    app_main._processed_record_ids.clear()
    app_main._running_record_ids.clear()
    app_main._record_task_map.clear()


def test_same_record_same_event_id_retry_is_filtered(webhook_client):
    """同一 event_id 的重试应被幂等过滤，只触发一次流水线。"""
    client, launched_record_ids = webhook_client
    first_payload = _event_payload(record_id="rec_retry", event_id="evt_retry", retry_count=0)
    retry_payload = _event_payload(record_id="rec_retry", event_id="evt_retry", retry_count=1)

    first = client.post("/webhook/event", json=first_payload)
    retry = client.post("/webhook/event", json=retry_payload)

    assert first.status_code == 200
    assert first.json().get("duplicate") is not True
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True
    assert launched_record_ids == ["rec_retry"]


def test_same_record_different_event_id_is_not_filtered(webhook_client):
    """同一 record_id 的不同 event_id 代表新事件，不能被 record_id 永久吞掉。"""
    client, launched_record_ids = webhook_client

    first = client.post(
        "/webhook/event",
        json=_event_payload(record_id="rec_second_edit", event_id="evt_first"),
    )
    second = client.post(
        "/webhook/event",
        json=_event_payload(record_id="rec_second_edit", event_id="evt_second"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json().get("duplicate") is not True
    assert launched_record_ids == ["rec_second_edit", "rec_second_edit"]


def test_same_record_without_event_id_uses_timestamp_to_separate_events(webhook_client):
    """缺少 event_id 时，应至少用 timestamp 区分二次编辑事件。"""
    client, launched_record_ids = webhook_client

    first = client.post(
        "/webhook/event",
        json=_event_payload(record_id="rec_timestamp", event_id=None, create_time="1710000000000"),
    )
    second = client.post(
        "/webhook/event",
        json=_event_payload(record_id="rec_timestamp", event_id=None, create_time="1710000005000"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json().get("duplicate") is not True
    assert launched_record_ids == ["rec_timestamp", "rec_timestamp"]


def test_same_record_same_timestamp_without_event_id_retry_is_filtered(webhook_client):
    """缺少 event_id 的真实重试，record_id + timestamp 相同时应被过滤。"""
    client, launched_record_ids = webhook_client
    first_payload = _event_payload(record_id="rec_timestamp_retry", event_id=None, retry_count=0)
    retry_payload = _event_payload(record_id="rec_timestamp_retry", event_id=None, retry_count=1)

    first = client.post("/webhook/event", json=first_payload)
    retry = client.post("/webhook/event", json=retry_payload)

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True
    assert launched_record_ids == ["rec_timestamp_retry"]
