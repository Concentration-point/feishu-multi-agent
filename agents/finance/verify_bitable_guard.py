#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare/validate metadata for a Feishu Bitable finance guard run.

This script does not call Feishu directly. Its job is to normalize the target date
and emit the exact app/table identifiers that an external caller must use.

Why it exists:
- the active formal ledger is currently Feishu Bitable, not the local JSONL ledger
- we still want a deterministic pre-send guard entrypoint in the finance workspace
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY = ROOT / "MEMORY.md"

DEFAULT_APP = "DTBKbMBRcaO9jHsY99ycAc3unid"
DEFAULT_TABLE = "tblX8Jop5niKoOK9"


class GuardPrepError(Exception):
    pass



def validate_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise GuardPrepError("invalid_date_format_expected_yyyy_mm_dd")
    return value



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    try:
        date = validate_date(args.date)
        payload = {
            "ok": True,
            "guard_type": "feishu_bitable",
            "date": date,
            "app_token": DEFAULT_APP,
            "table_id": DEFAULT_TABLE,
            "note": "Query Feishu Bitable as the source of truth before sending finance conclusions.",
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return 0
    except GuardPrepError as e:
        sys.stdout.write(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
