#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit finance ledgers for corruption signals without mutating them."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EXPENSE_LEDGER = ROOT / "finance-ledger-expense.jsonl"
TOKEN_LEDGER = ROOT / "finance-ledger-token.jsonl"

REPLACEMENT_MARKERS = {"�", "?"}
TEXT_FIELDS_EXPENSE = ["merchant", "category", "channel", "note"]
TEXT_FIELDS_TOKEN = ["session_key", "agent_type", "model", "task_type"]


def suspicious_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if any(marker in value for marker in REPLACEMENT_MARKERS):
        return True
    return False


def audit(path: Path, text_fields: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ledger": str(path),
        "exists": path.exists(),
        "total_lines": 0,
        "data_rows": 0,
        "invalid_json_lines": [],
        "duplicate_ids": [],
        "suspicious_rows": [],
    }
    if not path.exists():
        return summary

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    summary["total_lines"] = len(lines)
    id_counter: Counter[str] = Counter()

    for idx, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            summary["invalid_json_lines"].append(idx)
            continue
        if not isinstance(obj, dict):
            summary["invalid_json_lines"].append(idx)
            continue

        summary["data_rows"] += 1
        rec_id = obj.get("id")
        if isinstance(rec_id, str) and rec_id:
            id_counter[rec_id] += 1

        flagged_fields = []
        for field in text_fields:
            if suspicious_text(obj.get(field)):
                flagged_fields.append(field)
        if flagged_fields:
            summary["suspicious_rows"].append(
                {
                    "line": idx,
                    "id": obj.get("id"),
                    "fields": flagged_fields,
                }
            )

    summary["duplicate_ids"] = [rid for rid, count in id_counter.items() if count > 1]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", choices=["expense", "token", "all"], default="all")
    args = parser.parse_args()

    reports = []
    if args.ledger in {"expense", "all"}:
        reports.append(audit(EXPENSE_LEDGER, TEXT_FIELDS_EXPENSE))
    if args.ledger in {"token", "all"}:
        reports.append(audit(TOKEN_LEDGER, TEXT_FIELDS_TOKEN))

    print(json.dumps({"ok": True, "reports": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
