"""Submit inbox candidates to Feishu promotion review table.

Scans knowledge/11_待整理收件箱/ for all .md files auto-produced by agents.
For each file not yet submitted, creates a 待审批 record in the Feishu
经验升格审批 multi-dim table. Approvals are then applied by
scripts/apply_approved_promotions.py.

After a successful submission we tag the .sync_state.json entry with:
    promotion_submitted: true
    promotion_record_id: recXXXXXX
    promotion_submitted_at: iso8601
Duplicate submissions are prevented by the promotion_submitted flag.

Usage:
    python scripts/submit_inbox_to_review.py --dry-run
    python scripts/submit_inbox_to_review.py
    python scripts/submit_inbox_to_review.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (
    FIELD_MAP_PROMOTION as FP,
    KNOWLEDGE_BASE_PATH,
    PROMOTION_REVIEW_TABLE_ID,
    PROMOTION_STATUS_PENDING,
)
from feishu.bitable import BitableClient

logger = logging.getLogger("submit_inbox_to_review")

INBOX_DIR_NAME = "11_待整理收件箱"
SUMMARY_MAX_CHARS = 300
SKIP_FILENAMES = {"_index.md", "README.md"}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_block = m.group(1)
    body = text[m.end():]
    fm = {}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        fm[key.strip()] = val.strip().strip("\"'")
    return fm, body


def extract_summary(body, limit=SUMMARY_MAX_CHARS):
    text = body.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def load_state(state_file):
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error(".sync_state.json parse failed: %s", e)
        raise SystemExit(2)


def save_state(state_file, state):
    tmp = state_file.with_suffix(state_file.suffix + ".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(state_file)


def scan_inbox(base_path):
    inbox = base_path / INBOX_DIR_NAME
    if not inbox.exists():
        return []
    files = []
    for p in sorted(inbox.rglob("*.md")):
        if p.name in SKIP_FILENAMES:
            continue
        if p.name.startswith("_"):
            continue
        files.append(p)
    return files


def build_submission_payload(*, rel_path, fm, summary):
    try:
        confidence = float(fm.get("confidence", "0") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    submitted_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        FP["file_path"]: rel_path,
        FP["category"]: fm.get("category", "") or "",
        FP["role"]: fm.get("role", "") or "",
        FP["summary"]: summary,
        FP["confidence"]: confidence,
        FP["source_project"]: fm.get("source_project", "") or fm.get("source", "") or "",
        FP["approval_status"]: PROMOTION_STATUS_PENDING,
        FP["submitted_at"]: submitted_ts_ms,
    }


async def submit(*, base_path, dry_run, limit, client=None, table_id=None):
    state_file = base_path / ".sync_state.json"
    state = load_state(state_file)

    candidates = scan_inbox(base_path)
    to_submit = []
    skipped_already = []

    for f in candidates:
        rel = f.relative_to(base_path).as_posix()
        entry = state.get(rel, {})
        if entry.get("promotion_submitted"):
            skipped_already.append(rel)
            continue

        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("read file failed, skip %s: %s", rel, e)
            continue

        fm, body = parse_frontmatter(text)
        summary = extract_summary(body or text)
        to_submit.append((f, rel, fm, summary))
        if limit and len(to_submit) >= limit:
            break

    print(
        f"[SUMMARY] scanned={len(candidates)} "
        f"to_submit={len(to_submit)} "
        f"skipped_already={len(skipped_already)}"
    )

    if dry_run:
        for f, rel, fm, summary in to_submit:
            print(
                f"  [DRY] {rel}  category={fm.get('category','')}"
                f"  role={fm.get('role','')}  summary={summary[:60]}..."
            )
        print("[DRY-RUN] no Feishu API / state not written")
        return {
            "scanned": len(candidates),
            "submitted": 0,
            "pending": len(to_submit),
            "skipped_already": len(skipped_already),
        }

    if not to_submit:
        return {
            "scanned": len(candidates),
            "submitted": 0,
            "pending": 0,
            "skipped_already": len(skipped_already),
        }

    client = client or BitableClient()
    table_id = table_id or PROMOTION_REVIEW_TABLE_ID
    if not table_id:
        print("[ERROR] PROMOTION_REVIEW_TABLE_ID not configured", file=sys.stderr)
        raise SystemExit(2)

    submitted = 0
    for f, rel, fm, summary in to_submit:
        payload = build_submission_payload(rel_path=rel, fm=fm, summary=summary)
        try:
            record_id = await client.create_record(table_id, payload)
        except Exception as e:
            logger.warning("submit failed %s: %s", rel, e)
            continue

        entry = state.get(rel, {})
        entry.update({
            "promotion_submitted": True,
            "promotion_record_id": record_id,
            "promotion_submitted_at": datetime.now(timezone.utc).isoformat(),
        })
        state[rel] = entry
        submitted += 1
        print(f"  [OK] {rel} -> {record_id}")
        save_state(state_file, state)

    print(f"[DONE] submitted {submitted}/{len(to_submit)}")
    return {
        "scanned": len(candidates),
        "submitted": submitted,
        "pending": len(to_submit),
        "skipped_already": len(skipped_already),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Submit 11_inbox candidates to Feishu promotion review table"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--knowledge-dir", default=KNOWLEDGE_BASE_PATH)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    base = Path(args.knowledge_dir).resolve()
    if not base.exists():
        print(f"[ERROR] knowledge dir not found: {base}", file=sys.stderr)
        return 2

    asyncio.run(submit(
        base_path=base,
        dry_run=args.dry_run,
        limit=args.limit,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
