#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finance report guard: validate report claims against the formal local ledger.

Usage examples:
  python agents/finance/verify_report_guard.py --date 2026-04-14 --must-include-counts
  python agents/finance/verify_report_guard.py --date 2026-04-14 --report-file draft.md --must-include-counts

Behavior:
- reads the local expense ledger JSONL
- computes record_count / booked_count / pending_count / abnormal_count / total_amount
- if a report file is provided, enforces numeric presence and blocks stale status phrases
- exits non-zero on any guard failure
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "finance-ledger-expense.jsonl"

STALE_STATUS_PATTERNS = [
    r"账本空白",
    r"漏记",
    r"未落实",
    r"明天补账",
    r"仍是空白",
    r"还没补",
]

ASSERTIVE_PATTERNS = [
    r"已记",
    r"已入账",
    r"已落实",
    r"已补完",
]


class GuardError(Exception):
    pass


def load_records() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    records: list[dict[str, Any]] = []
    for idx, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception as e:
            raise GuardError(f"invalid_jsonl_line:{idx}:{e}") from e
        if isinstance(obj, dict):
            records.append(obj)
    return records


def summarize(records: list[dict[str, Any]], date: str) -> dict[str, Any]:
    day = [r for r in records if str(r.get("date", "")) == date]
    record_count = len(day)
    booked_count = sum(1 for r in day if bool(r.get("confirmed")) is True)
    pending_count = sum(1 for r in day if bool(r.get("confirmed")) is False)
    abnormal_count = sum(1 for r in day if str(r.get("confidence", "")).lower() == "low")
    total_amount = sum(Decimal(str(r.get("amount", 0))) for r in day)
    return {
        "date": date,
        "record_count": record_count,
        "booked_count": booked_count,
        "pending_count": pending_count,
        "abnormal_count": abnormal_count,
        "total_amount": f"{total_amount:.2f}",
    }


def enforce_numeric_presence(text: str, summary: dict[str, Any]) -> None:
    required_numbers = [
        str(summary["record_count"]),
        str(summary["booked_count"]),
        str(summary["pending_count"]),
        str(summary["abnormal_count"]),
    ]
    missing = [n for n in required_numbers if n not in text]
    if missing:
        raise GuardError(f"report_missing_required_counts:{','.join(missing)}")



def enforce_status_consistency(text: str, summary: dict[str, Any]) -> None:
    for pattern in STALE_STATUS_PATTERNS:
        if re.search(pattern, text):
            if summary["record_count"] > 0:
                raise GuardError(f"stale_status_phrase_blocked:{pattern}")

    for pattern in ASSERTIVE_PATTERNS:
        if re.search(pattern, text):
            if summary["record_count"] <= 0:
                raise GuardError(f"assertive_phrase_without_records:{pattern}")
            if summary["booked_count"] <= 0:
                raise GuardError(f"assertive_phrase_without_confirmed_records:{pattern}")



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--report-file", help="optional markdown/text report to validate")
    parser.add_argument("--must-include-counts", action="store_true")
    args = parser.parse_args()

    try:
        records = load_records()
        summary = summarize(records, args.date)

        output: dict[str, Any] = {"ok": True, "summary": summary}

        if args.report_file:
            report_path = Path(args.report_file).resolve()
            text = report_path.read_text(encoding="utf-8")
            if args.must_include_counts:
                enforce_numeric_presence(text, summary)
            enforce_status_consistency(text, summary)
            output["report_checked"] = str(report_path)

        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
        return 0
    except GuardError as e:
        sys.stdout.write(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
