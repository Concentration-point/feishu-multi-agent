#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a minimal expense record JSON for ledger_append.py.

Example:
  python agents/finance/ledger_make_record.py \
    --output agents/finance/tmp-record.json \
    --date 2026-04-05 \
    --time 18:36 \
    --merchant "乡村基（南京宜悦里店）" \
    --amount 19.50 \
    --category "餐饮/外卖" \
    --channel "外卖订单页" \
    --note "用户主动发送金额图，按已确认消费入账。" \
    --source-type "screenshot+user_confirmation" \
    --confidence high \
    --confirmed true \
    --raw-ref "feishu:om_xxx"
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


def slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "record"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--time", default="")
    parser.add_argument("--merchant", required=True)
    parser.add_argument("--amount", required=True, type=float)
    parser.add_argument("--direction", default="expense", choices=["expense", "income"])
    parser.add_argument("--category", required=True)
    parser.add_argument("--channel", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--source-type", default="manual")
    parser.add_argument("--confidence", default="high", choices=["high", "medium", "low"])
    parser.add_argument("--confirmed", default="true", choices=["true", "false"])
    parser.add_argument("--raw-ref", default="")
    parser.add_argument("--id", default="")
    args = parser.parse_args()

    now = datetime.now().astimezone()
    record_id = args.id or (
        f"expense-{args.date}-{(args.time or '0000').replace(':', '')}-{slug(args.merchant)[:24]}-{int(round(args.amount * 100))}"
    )

    record = {
        "id": record_id,
        "date": args.date,
        "time": args.time,
        "merchant": args.merchant,
        "amount": round(float(args.amount), 2),
        "direction": args.direction,
        "category": args.category,
        "channel": args.channel,
        "note": args.note,
        "source_type": args.source_type,
        "confidence": args.confidence,
        "confirmed": args.confirmed == "true",
        "raw_ref": args.raw_ref,
        "created_at": now.isoformat(timespec="seconds"),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(out), "id": record_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
