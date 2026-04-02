from __future__ import annotations

import random
import re
import secrets
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Optional, List

from curl_cffi import requests

MAILTM_BASE = "https://api.mail.tm"


@dataclass
class MailboxResult:
    ok: bool
    stage: str
    error_code: str = ""
    email: str = ""
    token: str = ""
    detail: str = ""
    checked_at: str = ""


@dataclass
class OtpResult:
    ok: bool
    stage: str
    error_code: str = ""
    otp_code: str = ""
    detail: str = ""
    checked_at: str = ""


def _now() -> str:
    return datetime.now().isoformat()


def _headers(*, token: str = "", use_json: bool = False) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    if use_json:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _domains(proxies: Any = None) -> List[str]:
    resp = requests.get(
        f"{MAILTM_BASE}/domains",
        headers=_headers(),
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"domains_http_{resp.status_code}")

    data = resp.json()
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("hydra:member") or data.get("items") or []
    else:
        items = []

    domains = []
    for item in items:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").strip()
        if domain and item.get("isActive", True) and not item.get("isPrivate", False):
            domains.append(domain)
    return domains


def create_mailbox(proxies: Any = None) -> MailboxResult:
    try:
        domains = _domains(proxies)
        if not domains:
            return MailboxResult(False, "create_mailbox", "no_available_domain", checked_at=_now())

        domain = random.choice(domains)
        for _ in range(5):
            local = f"oc{secrets.token_hex(5)}"
            email = f"{local}@{domain}"
            password = secrets.token_urlsafe(18)

            create_resp = requests.post(
                f"{MAILTM_BASE}/accounts",
                headers=_headers(use_json=True),
                json={"address": email, "password": password},
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )
            if create_resp.status_code not in (200, 201):
                continue

            token_resp = requests.post(
                f"{MAILTM_BASE}/token",
                headers=_headers(use_json=True),
                json={"address": email, "password": password},
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )
            if token_resp.status_code == 200:
                token = str(token_resp.json().get("token") or "").strip()
                if token:
                    return MailboxResult(True, "create_mailbox", email=email, token=token, checked_at=_now())

        return MailboxResult(False, "create_mailbox", "token_fetch_failed", detail="mailbox_created_but_token_missing", checked_at=_now())
    except Exception as e:
        return MailboxResult(False, "create_mailbox", "mailtm_request_failed", detail=str(e), checked_at=_now())


def wait_openai_otp(token: str, email: str, proxies: Any = None, max_polls: int = 40, poll_interval: int = 3) -> OtpResult:
    regex = r"(?<!\d)(\d{6})(?!\d)"
    seen_ids: set[str] = set()

    for _ in range(max_polls):
        try:
            resp = requests.get(
                f"{MAILTM_BASE}/messages",
                headers=_headers(token=token),
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )
            if resp.status_code != 200:
                time.sleep(poll_interval)
                continue

            data = resp.json()
            if isinstance(data, list):
                messages = data
            elif isinstance(data, dict):
                messages = data.get("hydra:member") or data.get("messages") or []
            else:
                messages = []

            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                msg_id = str(msg.get("id") or "").strip()
                if not msg_id or msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                read_resp = requests.get(
                    f"{MAILTM_BASE}/messages/{msg_id}",
                    headers=_headers(token=token),
                    proxies=proxies,
                    impersonate="chrome",
                    timeout=15,
                )
                if read_resp.status_code != 200:
                    continue

                mail_data = read_resp.json()
                text = "\n".join([
                    str(mail_data.get("subject") or ""),
                    str(mail_data.get("intro") or ""),
                    str(mail_data.get("text") or ""),
                    str(mail_data.get("html") or ""),
                ])
                m = re.search(regex, text)
                if m:
                    return OtpResult(True, "wait_openai_otp", otp_code=m.group(1), checked_at=_now())
        except Exception as e:
            last_error = str(e)
        time.sleep(poll_interval)

    return OtpResult(False, "wait_openai_otp", "otp_timeout", detail=f"email={email}", checked_at=_now())
