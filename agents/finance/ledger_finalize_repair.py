#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path

root = Path(__file__).resolve().parent
ledger = root / 'finance-ledger-expense.jsonl'
audit = root / 'finance-ledger-expense.repair-audit-2026-04-05.jsonl'

rows = ledger.read_text(encoding='utf-8').splitlines()
clean_lines = []
audit_lines = []

for raw in rows:
    if not raw.strip():
        continue
    obj = json.loads(raw)
    if 'repair_meta' in obj:
        audit_obj = {
            'id': obj.get('id'),
            'repair_meta': obj.get('repair_meta'),
            'raw_ref': obj.get('raw_ref'),
            'date': obj.get('date'),
            'amount': obj.get('amount')
        }
        audit_lines.append(json.dumps(audit_obj, ensure_ascii=False))
        obj.pop('repair_meta', None)
    clean_lines.append(json.dumps(obj, ensure_ascii=False))

ledger.write_text('\n'.join(clean_lines) + '\n', encoding='utf-8')
audit.write_text('\n'.join(audit_lines) + ('\n' if audit_lines else ''), encoding='utf-8')

print(json.dumps({'ok': True, 'cleaned_rows': len(audit_lines), 'audit': str(audit)}, ensure_ascii=False))
