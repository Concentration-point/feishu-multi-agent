"""Apply approved / rejected promotion decisions from Feishu review table.

Pulls records from the Feishu 经验升格审批 table, filters those whose 审批状态
is 通过 or 驳回 AND whose 处理时间 is empty, and for each:

* 通过  -> copy knowledge/11_待整理收件箱/<cat>/<file>.md to
          knowledge/10_经验沉淀/<cat>/<file>.md (adding promoted_from /
          promoted_at to frontmatter), delete the source, rewrite
          .sync_state.json (old entry removed, new entry mark_dirty=true
          so wiki_sync pushes it to Feishu), then write back 处理时间.
* 驳回  -> delete the inbox file, drop the entry from .sync_state.json,
          then write back 处理时间.

Atomicity:
* Approved path: write to 10_ FIRST; only after that succeeds do we
  delete the source. If Feishu write-back fails after the filesystem
  move, the next run finds the record still "unprocessed" but the source
  file is gone -> we idempotently skip the file move and just rewrite
  处理时间.
* Rejected path: unlink source, then mutate state, then write back time.

Usage:
    python scripts/apply_approved_promotions.py --dry-run
    python scripts/apply_approved_promotions.py
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
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
    PROMOTION_STATUS_APPROVED,
    PROMOTION_STATUS_REJECTED,
)
from feishu.bitable import BitableClient

logger = logging.getLogger("apply_approved_promotions")

INBOX_DIR_NAME = "11_待整理收件箱"
FORMAL_DIR_NAME = "10_经验沉淀"



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


def inject_promotion_meta(text, *, source_rel, promoted_at_iso):
    """Insert promoted_from / promoted_at into YAML frontmatter, or synth one."""
    marker = "---" + chr(10)
    closer = chr(10) + "---" + chr(10)
    if text.startswith(marker):
        end = text.find(closer, 4)
        if end != -1:
            fm_block = text[4:end]
            rest = text[end + 5:]
            extra = (
                chr(10) + f"promoted_from: {source_rel}"
                + chr(10) + f"promoted_at: {promoted_at_iso}"
                + chr(10)
            )
            new_fm = fm_block.rstrip(chr(10)) + extra
            return marker + new_fm + "---" + chr(10) + rest
    header = (
        marker
        + f"promoted_from: {source_rel}" + chr(10)
        + f"promoted_at: {promoted_at_iso}" + chr(10)
        + "---" + chr(10) + chr(10)
    )
    return header + text

def compute_md5(content):
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def pick_unprocessed(records):
    picked = []
    for r in records:
        fields = r.get("fields", {})
        status = str(fields.get(FP["approval_status"], "")).strip()
        processed = fields.get(FP["processed_at"], None)
        if status not in (PROMOTION_STATUS_APPROVED, PROMOTION_STATUS_REJECTED):
            continue
        if processed not in (None, "", 0):
            continue
        picked.append(r)
    return picked



def process_approved(*, base_path, state, file_rel, promoted_at_iso):
    """Move a single inbox file into 10_ and mutate state in place.

    Returns (status, new_rel) where status is one of:
      migrated / already_migrated / missing / unsafe_path
    """
    inbox_root = (base_path / INBOX_DIR_NAME).resolve()
    formal_root = (base_path / FORMAL_DIR_NAME).resolve()

    parts = Path(file_rel).parts
    if not parts or parts[0] != INBOX_DIR_NAME:
        logger.warning("file_rel %s not under inbox, skip", file_rel)
        return "unsafe_path", None

    subpath = Path(*parts[1:])
    src = (inbox_root / subpath).resolve()
    dst = (formal_root / subpath).resolve()

    try:
        src.relative_to(inbox_root)
        dst.relative_to(formal_root)
    except ValueError:
        logger.warning("unsafe path traversal for %s, skip", file_rel)
        return "unsafe_path", None

    new_rel = f"{FORMAL_DIR_NAME}/{subpath.as_posix()}"

    src_exists = src.exists()
    dst_exists = dst.exists()

    if not src_exists and dst_exists:
        # Idempotent replay: previous run migrated but failed write-back.
        state.pop(file_rel, None)
        if new_rel not in state:
            content = dst.read_text(encoding="utf-8")
            state[new_rel] = {
                "hash": compute_md5(content),
                "dirty": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        return "already_migrated", new_rel

    if not src_exists and not dst_exists:
        logger.warning("source missing for %s, nothing to migrate", file_rel)
        state.pop(file_rel, None)
        return "missing", None

    text = src.read_text(encoding="utf-8")
    promoted_text = inject_promotion_meta(
        text, source_rel=file_rel, promoted_at_iso=promoted_at_iso
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(promoted_text, encoding="utf-8")

    try:
        src.unlink()
    except OSError as e:
        logger.warning("failed to remove source %s: %s", src, e)

    state.pop(file_rel, None)
    state[new_rel] = {
        "hash": compute_md5(promoted_text),
        "dirty": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return "migrated", new_rel


def process_rejected(*, base_path, state, file_rel):
    inbox_root = (base_path / INBOX_DIR_NAME).resolve()
    parts = Path(file_rel).parts
    if not parts or parts[0] != INBOX_DIR_NAME:
        return "unsafe_path"
    src = (inbox_root / Path(*parts[1:])).resolve()
    try:
        src.relative_to(inbox_root)
    except ValueError:
        return "unsafe_path"
    if src.exists():
        try:
            src.unlink()
        except OSError as e:
            logger.warning("failed to delete rejected %s: %s", src, e)
            return "delete_failed"
    state.pop(file_rel, None)
    return "deleted"



async def apply(*, base_path, dry_run, client=None, table_id=None):
    state_file = base_path / ".sync_state.json"
    state = load_state(state_file)

    table_id = table_id or PROMOTION_REVIEW_TABLE_ID
    if not table_id:
        if dry_run:
            print("[DRY-RUN] PROMOTION_REVIEW_TABLE_ID not configured -- "
                  "cannot list records; nothing to preview.")
            return {"total": 0, "unique": 0, "approved": 0, "rejected": 0, "skipped": 0}
        print("[ERROR] PROMOTION_REVIEW_TABLE_ID not configured", file=sys.stderr)
        raise SystemExit(2)
    client = client or BitableClient()

    try:
        all_records = await client.list_records(table_id)
    except Exception as e:
        print(f"[ERROR] list_records failed: {e}", file=sys.stderr)
        raise SystemExit(3)

    targets = pick_unprocessed(all_records)
    approved_n = 0
    rejected_n = 0
    skipped_n = 0

    # Dedup by file path within one run so a duplicate-submission bug
    # upstream does not cause double migration here.
    seen_paths = set()
    ordered = []
    for r in targets:
        path = str(r["fields"].get(FP["file_path"], "")).strip()
        if not path:
            skipped_n += 1
            continue
        if path in seen_paths:
            logger.warning(
                "duplicate submission for %s, only the first is applied this run",
                path,
            )
            continue
        seen_paths.add(path)
        ordered.append(r)

    print(
        f"[SUMMARY] approved_or_rejected={len(targets)} "
        f"unique_paths={len(ordered)} skipped_no_path={skipped_n}"
    )

    if dry_run:
        for r in ordered:
            fields = r["fields"]
            status = fields.get(FP["approval_status"], "")
            path = fields.get(FP["file_path"], "")
            print(f"  [DRY] status={status}  path={path}  record={r.get('record_id')}")
        print("[DRY-RUN] no filesystem / state / write-back")
        return {
            "total": len(targets),
            "unique": len(ordered),
            "approved": 0,
            "rejected": 0,
            "skipped": skipped_n,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    for r in ordered:
        fields = r["fields"]
        record_id = r["record_id"]
        status = str(fields.get(FP["approval_status"], "")).strip()
        file_rel = str(fields.get(FP["file_path"], "")).strip()

        try:
            if status == PROMOTION_STATUS_APPROVED:
                result, new_rel = process_approved(
                    base_path=base_path,
                    state=state,
                    file_rel=file_rel,
                    promoted_at_iso=now_iso,
                )
                save_state(state_file, state)
                if result in ("migrated", "already_migrated"):
                    approved_n += 1
                    print(f"  [APPROVE] {file_rel} -> {new_rel} ({result})")
                else:
                    skipped_n += 1
                    print(f"  [SKIP-APPROVE] {file_rel} ({result})")

            elif status == PROMOTION_STATUS_REJECTED:
                result = process_rejected(
                    base_path=base_path, state=state, file_rel=file_rel
                )
                save_state(state_file, state)
                if result == "deleted":
                    rejected_n += 1
                    print(f"  [REJECT] {file_rel} deleted")
                else:
                    skipped_n += 1
                    print(f"  [SKIP-REJECT] {file_rel} ({result})")
            else:
                skipped_n += 1
                continue

            try:
                await client.update_record(
                    table_id, record_id, {FP["processed_at"]: now_ts_ms}
                )
            except Exception as e:
                logger.warning(
                    "write-back processed_at failed for %s: %s "
                    "(will retry next run; state already reflects migration)",
                    record_id, e,
                )
        except Exception as e:
            logger.error("apply %s failed: %s", file_rel, e)
            skipped_n += 1

    print(
        f"[DONE] approved={approved_n} rejected={rejected_n} "
        f"skipped={skipped_n}"
    )
    return {
        "total": len(targets),
        "unique": len(ordered),
        "approved": approved_n,
        "rejected": rejected_n,
        "skipped": skipped_n,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Apply approved/rejected promotion decisions from Feishu review table"
    )
    parser.add_argument("--dry-run", action="store_true")
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

    asyncio.run(apply(
        base_path=base,
        dry_run=args.dry_run,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
