#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a non-destructive repair plan for suspicious expense ledger rows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "finance-ledger-expense.jsonl"
DOCTOR_REPORT = ROOT / "ledger-doctor-report-2026-04-05.json"
OUT = ROOT / "ledger-repair-plan-2026-04-05.json"


def parse_id_hints(rec_id: str) -> dict[str, Any]:
    parts = rec_id.split("-")
    out: dict[str, Any] = {
        "date_hint": None,
        "merchant_hint": None,
        "amount_hint": None,
    }
    if len(parts) >= 5:
        # expense-YYYY-MM-DD-...
        if parts[0] == "expense":
            out["date_hint"] = "-".join(parts[1:4])
            tail = parts[4:]
            if tail:
                last = tail[-1]
                if last.isdigit():
                    out["amount_hint"] = int(last) / 100
                    merchant_parts = tail[:-1]
                else:
                    merchant_parts = tail
                if merchant_parts:
                    out["merchant_hint"] = "-".join(merchant_parts)
    return out


def main() -> int:
    _report = json.loads(DOCTOR_REPORT.read_text(encoding="utf-8"))

    # repair plan intentionally recomputes suspicious rows from ledger content,
    # so it does not depend on the report shape.
    rows = LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()

    plan: list[dict[str, Any]] = []
    for idx, raw in enumerate(rows, start=1):
        if not raw.strip():
            continue
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            continue
        text_blob = " ".join(str(obj.get(k, "")) for k in ["merchant", "category", "channel", "note"])
        if "�" not in text_blob and "?" not in text_blob:
            continue

        hints = parse_id_hints(str(obj.get("id", "")))
        plan.append(
            {
                "line": idx,
                "id": obj.get("id"),
                "raw_record": obj,
                "repair_strategy": "manual_or_context_rebuild",
                "recoverable_fields": {
                    "date": obj.get("date") or hints["date_hint"],
                    "time": obj.get("time"),
                    "amount": obj.get("amount") if isinstance(obj.get("amount"), (int, float)) else hints["amount_hint"],
                },
                "hints": hints,
                "needs": [
                    "merchant",
                    "category",
                    "channel",
                    "note"
                ],
                "confidence": "medium" if hints.get("merchant_hint") else "low",
                "suggestion": "优先按 raw_ref 回查原消息/原图；若拿不到，再根据 id hint + 上下文人工补录。",
            }
        )

    out = {
        "generated_at": "2026-04-05T10:57:00+08:00",
        "mode": "non_destructive_plan_only",
        "ledger": str(LEDGER),
        "suspicious_count": len(plan),
        "plan": plan,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(OUT), "suspicious_count": len(plan)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
