from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("WEBHOOK_VERIFICATION_TOKEN", "test-token")

import main as app_main  # noqa: E402


class DummyOrchestrator:
    started: list[str] = []

    def __init__(self, record_id: str, event_bus=None):
        self.record_id = record_id
        self.event_bus = event_bus

    async def run(self):
        DummyOrchestrator.started.append(self.record_id)
        return []


def _build_challenge_payload() -> dict:
    return {
        "challenge": "abc123",
        "token": "test-token",
        "type": "url_verification",
    }


def _build_event_payload(record_id: str) -> dict:
    return {
        "header": {
            "event_type": "bitable.record.created_v1",
            "token": "test-token",
        },
        "event": {
            "record_id": record_id,
        },
    }


def test_challenge_verification():
    client = TestClient(app_main.app)
    response = client.post("/webhook/event", json=_build_challenge_payload())
    assert response.status_code == 200
    assert response.json() == {"challenge": "abc123"}


def test_record_created_event_triggers_pipeline(monkeypatch):
    DummyOrchestrator.started.clear()

    async def fake_trigger_sync_once():
        return None

    monkeypatch.setattr(app_main, "Orchestrator", DummyOrchestrator)
    monkeypatch.setattr(app_main, "_trigger_sync_once", fake_trigger_sync_once)

    client = TestClient(app_main.app)
    response = client.post("/webhook/event", json=_build_event_payload("rec_test_1"))

    assert response.status_code == 200
    assert response.json()["ok"] is True

    asyncio.run(asyncio.sleep(0.05))
    assert "rec_test_1" in DummyOrchestrator.started


def test_duplicate_event_is_filtered(monkeypatch):
    DummyOrchestrator.started.clear()
    app_main._processed_record_ids.clear()

    async def fake_trigger_sync_once():
        return None

    monkeypatch.setattr(app_main, "Orchestrator", DummyOrchestrator)
    monkeypatch.setattr(app_main, "_trigger_sync_once", fake_trigger_sync_once)

    client = TestClient(app_main.app)
    first = client.post("/webhook/event", json=_build_event_payload("rec_dup"))
    second = client.post("/webhook/event", json=_build_event_payload("rec_dup"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


def test_invalid_payload_returns_400():
    client = TestClient(app_main.app)
    response = client.post("/webhook/event", json={"hello": "world"})
    assert response.status_code == 400
