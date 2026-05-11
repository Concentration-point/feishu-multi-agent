from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as app_main


def _event_payload(record_id: str = "rec_auth") -> dict:
    return {
        "header": {"event_type": "bitable.record.created_v1"},
        "event": {"record_id": record_id},
    }


def _challenge_payload() -> dict:
    return {
        "challenge": "challenge-token",
        "type": "url_verification",
    }


def test_webhook_event_missing_token_rejected_when_token_configured(monkeypatch):
    """配置 webhook token 后，事件请求缺 token 必须拒绝。"""
    monkeypatch.setattr(app_main, "WEBHOOK_VERIFICATION_TOKEN", "expected-token")

    def fake_track_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(app_main, "_track_task", fake_track_task)
    app_main._processed_record_ids.clear()

    client = TestClient(app_main.app)
    response = client.post("/webhook/event", json=_event_payload())

    assert response.status_code == 401


def test_webhook_challenge_missing_token_rejected_when_token_configured(monkeypatch):
    """配置 webhook token 后，challenge 缺 token 也必须拒绝。"""
    monkeypatch.setattr(app_main, "WEBHOOK_VERIFICATION_TOKEN", "expected-token")

    client = TestClient(app_main.app)
    response = client.post("/webhook/event", json=_challenge_payload())

    assert response.status_code == 401


def test_webhook_challenge_invalid_token_rejected_when_token_configured(monkeypatch):
    """配置 webhook token 后，challenge token 错误也必须拒绝。"""
    monkeypatch.setattr(app_main, "WEBHOOK_VERIFICATION_TOKEN", "expected-token")

    payload = _challenge_payload()
    payload["token"] = "wrong-token"

    client = TestClient(app_main.app)
    response = client.post("/webhook/event", json=payload)

    assert response.status_code == 401


def test_webhook_event_invalid_token_rejected(monkeypatch):
    """token 不匹配必须拒绝。"""
    monkeypatch.setattr(app_main, "WEBHOOK_VERIFICATION_TOKEN", "expected-token")
    app_main._processed_record_ids.clear()

    payload = _event_payload()
    payload["header"]["token"] = "wrong-token"

    client = TestClient(app_main.app)
    response = client.post("/webhook/event", json=payload)

    assert response.status_code == 401


def test_webhook_event_valid_token_accepted(monkeypatch):
    """合法 token 才能进入事件处理。"""
    monkeypatch.setattr(app_main, "WEBHOOK_VERIFICATION_TOKEN", "expected-token")

    def fake_track_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(app_main, "_track_task", fake_track_task)
    app_main._processed_record_ids.clear()

    payload = _event_payload("rec_auth_ok")
    payload["header"]["token"] = "expected-token"

    client = TestClient(app_main.app)
    response = client.post("/webhook/event", json=payload)

    assert response.status_code == 200
    assert response.json()["ok"] is True
