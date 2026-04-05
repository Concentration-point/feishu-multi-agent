#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal finance ledger append executor.

Usage:
  python agents/finance/ledger_append.py --ledger expense --record-file /path/to/record.json

Behavior:
- validates the payload
- appends exactly one JSON line with UTF-8
- immediately reads the ledger back and verifies the record exists by id
- prints a compact JSON result to stdout
- exits non-zero on any failure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
EXPENSE_LEDGER = ROOT / "finance-ledger-expense.jsonl"
TOKEN_LEDGER = ROOT / "finance-ledger-token.jsonl"

REQUIRED_EXPENSE_FIELDS = {
    "id": str,
    "date": str,
    "time": str,
    "merchant": str,
    "amount": (int, float),
    "direction": str,
    "category": str,
    "channel": str,
    "note": str,
    "source_type": str,
    "confidence": str,
    "confirmed": bool,
    "raw_ref": str,
    "created_at": str,
}

REQUIRED_TOKEN_FIELDS = {
    "id": str,
    "date": str,
    "time": str,
    "session_key": str,
    "agent_type": str,
    "model": str,
    "input_tokens": int,
    "output_tokens": int,
    "total_tokens": int,
    "estimated_cost": (int, float, type(None)),
    "task_type": str,
    "source_type": str,
    "confidence": str,
    "created_at": str,
}


class LedgerError(Exception):
    pass


def load_json(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        raise LedgerError(f"failed_to_read_record_file: {e}") from e
    try:
        data = json.loads(text)
    except Exception as e:
        raise LedgerError(f"invalid_record_json: {e}") from e
    if not isinstance(data, dict):
        raise LedgerError("record_must_be_object")
    return data


def validate(record: Dict[str, Any], schema: Dict[str, Any], ledger_name: str) -> None:
    missing = [k for k in schema.keys() if k not in record]
    if missing:
        raise LedgerError(f"missing_fields: {','.join(missing)}")

    for key, expected in schema.items():
        value = record[key]
        if not isinstance(value, expected):
            raise LedgerError(
                f"invalid_type:{key}:expected={getattr(expected, '__name__', str(expected))}:got={type(value).__name__}"
            )

    if ledger_name == "expense":
        if record["direction"] not in {"expense", "income"}:
            raise LedgerError("invalid_direction")
        if record["confidence"] not in {"high", "medium", "low"}:
            raise LedgerError("invalid_confidence")

    # lightweight timestamp sanity
    for field in ("created_at",):
        try:
            datetime.fromisoformat(str(record[field]).replace("Z", "+00:00"))
        except Exception as e:
            raise LedgerError(f"invalid_iso_datetime:{field}") from e


def choose_ledger(name: str) -> Path:
    if name == "expense":
        return EXPENSE_LEDGER
    if name == "token":
        return TOKEN_LEDGER
    raise LedgerError("unsupported_ledger")


def read_lines_utf8(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        raise LedgerError(f"failed_to_read_ledger_utf8: {e}") from e


def ensure_no_duplicate_id(lines: list[str], record_id: str) -> None:
    for line in lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("id") == record_id:
            raise LedgerError("duplicate_id")


def append_and_verify(ledger_path: Path, record: Dict[str, Any]) -> Dict[str, Any]:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if not ledger_path.exists():
        ledger_path.write_text("", encoding="utf-8")

    before_lines = read_lines_utf8(ledger_path)
    ensure_no_duplicate_id(before_lines, record["id"])

    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        with ledger_path.open("a", encoding="utf-8", newline="") as f:
            f.write(line)
            f.flush()
    except Exception as e:
        raise LedgerError(f"failed_to_append: {e}") from e

    after_lines = read_lines_utf8(ledger_path)
    found = None
    for raw in reversed(after_lines):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except Exception as e:
            raise LedgerError(f"ledger_corrupted_after_append: {e}") from e
        if isinstance(obj, dict) and obj.get("id") == record["id"]:
            found = obj
            break

    if found is None:
        raise LedgerError("verify_failed_record_not_found")

    if found != record:
        raise LedgerError("verify_failed_record_mismatch")

    return {
        "ok": True,
        "ledger": str(ledger_path),
        "id": record["id"],
        "verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, choices=["expense", "token"])
    parser.add_argument("--record-file", required=True)
    args = parser.parse_args()

    try:
        record_file = Path(args.record_file).resolve()
        record = load_json(record_file)
        schema = REQUIRED_EXPENSE_FIELDS if args.ledger == "expense" else REQUIRED_TOKEN_FIELDS
        validate(record, schema, args.ledger)
        ledger_path = choose_ledger(args.ledger)
        result = append_and_verify(ledger_path, record)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    except LedgerError as e:
        sys.stdout.write(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
