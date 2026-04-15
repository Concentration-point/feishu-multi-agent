#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finance summary builder scaffold.

Current role:
- validate date input
- normalize builder request
- optionally validate a provided summary JSON file against the builder contract
- optionally validate a renderable draft against summary numbers

Why scaffold first:
- the formal source of truth is Feishu Bitable
- direct Feishu querying is currently handled by the assistant/tooling layer, not this local script
- this script defines the executable contract so the workflow stops relying on vague prose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_APP = "DTBKbMBRcaO9jHsY99ycAc3unid"
DEFAULT_TABLE = "tblX8Jop5niKoOK9"

REQUIRED_SUMMARY_KEYS = {
    "record_count": int,
    "booked_count": int,
    "pending_count": int,
    "abnormal_count": int,
}


class BuilderError(Exception):
    pass



def validate_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise BuilderError("invalid_date_format_expected_yyyy_mm_dd")
    return value



def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BuilderError(f"invalid_json_file:{e}") from e
    if not isinstance(data, dict):
        raise BuilderError("json_root_must_be_object")
    return data



def validate_summary_payload(data: dict[str, Any], date: str) -> dict[str, Any]:
    if data.get("source_of_truth") != "feishu_bitable":
        raise BuilderError("source_of_truth_must_be_feishu_bitable")
    if data.get("date") != date:
        raise BuilderError("summary_date_mismatch")

    summary = data.get("summary")
    if not isinstance(summary, dict):
        raise BuilderError("missing_summary_object")

    for key, expected in REQUIRED_SUMMARY_KEYS.items():
        if key not in summary:
            raise BuilderError(f"missing_summary_key:{key}")
        if not isinstance(summary[key], expected):
            raise BuilderError(f"invalid_summary_type:{key}")

    if "total_amount" not in summary:
        raise BuilderError("missing_summary_key:total_amount")

    try:
        total_amount = Decimal(str(summary["total_amount"]))
    except Exception as e:
        raise BuilderError("invalid_total_amount") from e

    if summary["record_count"] < 0 or summary["booked_count"] < 0 or summary["pending_count"] < 0 or summary["abnormal_count"] < 0:
        raise BuilderError("negative_counts_not_allowed")

    sendable = summary["record_count"] > 0
    status = "ok" if sendable else "empty"
    reason = "formal_ledger_has_records_and_core_counts_are_ready" if sendable else "formal_ledger_has_no_records_for_date"

    renderable_summary = (
        f"已记录 {summary['record_count']} 笔｜已入账 {summary['booked_count']}｜"
        f"待确认 {summary['pending_count']}｜异常 {summary['abnormal_count']}｜总支出 ¥{total_amount:.2f}。"
    )

    return {
        "ok": True,
        "source_of_truth": "feishu_bitable",
        "app_token": DEFAULT_APP,
        "table_id": DEFAULT_TABLE,
        "date": date,
        "summary": {
            **summary,
            "total_amount": float(total_amount),
        },
        "sendable": sendable,
        "status": status,
        "reason": reason,
        "renderable_summary": data.get("renderable_summary") or renderable_summary,
    }



def validate_renderable_draft(text: str, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    expected_fragments = [
        str(summary["record_count"]),
        str(summary["booked_count"]),
        str(summary["pending_count"]),
        str(summary["abnormal_count"]),
    ]
    missing = [frag for frag in expected_fragments if frag not in text]
    if missing:
        raise BuilderError(f"draft_missing_core_counts:{','.join(missing)}")



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--summary-json", help="path to a structured summary json to validate")
    parser.add_argument("--draft-file", help="optional renderable text draft to validate against the summary")
    args = parser.parse_args()

    try:
        date = validate_date(args.date)

        if not args.summary_json:
            payload = {
                "ok": True,
                "mode": "scaffold",
                "source_of_truth": "feishu_bitable",
                "app_token": DEFAULT_APP,
                "table_id": DEFAULT_TABLE,
                "date": date,
                "next_action": "query_feishu_bitable_and_fill_summary_json",
            }
            sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            return 0

        summary_path = Path(args.summary_json).resolve()
        source_data = load_json(summary_path)
        payload = validate_summary_payload(source_data, date)

        if args.draft_file:
            draft_path = Path(args.draft_file).resolve()
            draft_text = draft_path.read_text(encoding="utf-8")
            validate_renderable_draft(draft_text, payload)
            payload["draft_checked"] = str(draft_path)

        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return 0
    except BuilderError as e:
        sys.stdout.write(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
