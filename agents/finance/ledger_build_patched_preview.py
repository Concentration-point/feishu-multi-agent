#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a patched ledger preview using repair preview mappings, without touching the original ledger."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "finance-ledger-expense.jsonl"
REPAIR_PREVIEW = ROOT / "ledger-repair-preview-2026-04-05.json"
OUT = ROOT / "finance-ledger-expense.patched-preview-2026-04-05.jsonl"
SUMMARY = ROOT / "finance-ledger-expense.patched-preview-summary-2026-04-05.json"


def main() -> int:
    rows = LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()
    preview_data = json.loads(REPAIR_PREVIEW.read_text(encoding="utf-8"))
    repairs = {
        item["id"]: item["repaired_preview"]
        for item in preview_data.get("preview", [])
        if isinstance(item, dict) and "id" in item and "repaired_preview" in item
    }

    replaced = 0
    output_lines = []
    replaced_ids = []

    for raw in rows:
        if not raw.strip():
            continue
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            continue
        rec_id = obj.get("id")
        if rec_id in repairs:
            output_lines.append(json.dumps(repairs[rec_id], ensure_ascii=False))
            replaced += 1
            replaced_ids.append(rec_id)
        else:
            output_lines.append(json.dumps(obj, ensure_ascii=False))

    OUT.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    summary = {
        "generated_at": "2026-04-05T11:04:00+08:00",
        "mode": "patched_preview_only",
        "source_ledger": str(LEDGER),
        "output": str(OUT),
        "total_rows": len(output_lines),
        "replaced_rows": replaced,
        "replaced_ids": replaced_ids,
        "original_ledger_untouched": True,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(OUT), "replaced_rows": replaced}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
