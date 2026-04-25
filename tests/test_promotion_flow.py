"""Promotion flow tests — submit_inbox_to_review + apply_approved_promotions.

Runs fully offline: temp dir + a FakeBitableClient swapped in via the
script function signatures.

Invoke:
    python tests/test_promotion_flow.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import AFTER sys.path injection.
from scripts.submit_inbox_to_review import submit, INBOX_DIR_NAME
from scripts.apply_approved_promotions import apply, FORMAL_DIR_NAME
from config import FIELD_MAP_PROMOTION as FP


class FakeBitableClient:
    """In-memory stand-in for feishu.bitable.BitableClient.

    Records are stored keyed by record_id. Each record is {record_id, fields}.
    """

    def __init__(self):
        self._records: dict[str, dict] = {}
        self._counter = 0
        self.created_log: list[tuple[str, dict]] = []
        self.updated_log: list[tuple[str, str, dict]] = []

    async def create_record(self, table_id, fields):
        self._counter += 1
        rid = f"rec_{self._counter:04d}"
        self._records[rid] = {"record_id": rid, "fields": dict(fields)}
        self.created_log.append((table_id, dict(fields)))
        return rid

    async def list_records(self, table_id, filter_expr=None, page_size=100):
        return [dict(r, fields=dict(r["fields"])) for r in self._records.values()]

    async def update_record(self, table_id, record_id, fields):
        if record_id not in self._records:
            raise RuntimeError(f"no such record {record_id}")
        self._records[record_id]["fields"].update(fields)
        self.updated_log.append((table_id, record_id, dict(fields)))

    async def delete_record(self, table_id, record_id):
        self._records.pop(record_id, None)

    # Test helper to force-set status + clear processed
    def set_approval(self, record_id, status, processed_at=None):
        self._records[record_id]["fields"][FP["approval_status"]] = status
        if processed_at is None:
            self._records[record_id]["fields"].pop(FP["processed_at"], None)
        else:
            self._records[record_id]["fields"][FP["processed_at"]] = processed_at



def make_inbox_file(base, category, filename, *, role="copywriter", conf=0.85):
    """Create a markdown file under inbox with frontmatter."""
    d = base / INBOX_DIR_NAME / category
    d.mkdir(parents=True, exist_ok=True)
    fm = [
        "---",
        "created: 2026-04-17",
        "source: Agent test",
        f"category: {category}",
        f"role: {role}",
        f"confidence: {conf}",
        "---",
    ]
    body = (
        f"# {filename}" + chr(10) + chr(10)
        + "## 正文" + chr(10)
        + f"This is a test experience about {category}."
        + " It contains enough substantive text to survive the summary cut."
        + " " * 50
    )
    content = chr(10).join(fm) + chr(10) + chr(10) + body + chr(10)
    (d / f"{filename}.md").write_text(content, encoding="utf-8")
    return f"{INBOX_DIR_NAME}/{category}/{filename}.md"


def init_state(base, rel_paths):
    """Seed .sync_state.json with hash entries for the given rel paths."""
    import hashlib
    state = {}
    for rp in rel_paths:
        fp = base / rp
        content = fp.read_text(encoding="utf-8") if fp.exists() else ""
        state[rp] = {
            "hash": hashlib.md5(content.encode()).hexdigest(),
            "dirty": False,
            "synced_at": "2026-04-16T00:00:00+00:00",
        }
    (base / ".sync_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_state(base):
    f = base / ".sync_state.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}



async def test_submit_three_candidates():
    """Three inbox files -> three pending records + three state flags."""
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rels = [
            make_inbox_file(base, "电商大促", "小红书种草笔记套路"),
            make_inbox_file(base, "新品发布", "发布会传播节奏", role="strategist", conf=0.9),
            make_inbox_file(base, "品牌传播", "长图文叙事", role="copywriter", conf=0.7),
        ]
        init_state(base, rels)

        fake = FakeBitableClient()
        result = await submit(
            base_path=base,
            dry_run=False,
            limit=None,
            client=fake,
            table_id="tbl_fake_promotion",
        )

        if result["submitted"] != 3:
            fails.append(f"submitted expected 3, got {result['submitted']}")
        if len(fake.created_log) != 3:
            fails.append(f"fake create_record called {len(fake.created_log)} times, expected 3")

        state = load_state(base)
        flagged = [rp for rp in rels if state.get(rp, {}).get("promotion_submitted")]
        if len(flagged) != 3:
            fails.append(f"promotion_submitted set on {len(flagged)} entries, expected 3")
        # Record_id captured?
        for rp in rels:
            rid = state.get(rp, {}).get("promotion_record_id")
            if not rid or not rid.startswith("rec_"):
                fails.append(f"record_id missing/bad for {rp}: {rid}")

        # First record fields: check category/role/confidence propagated.
        first_fields = fake.created_log[0][1]
        if first_fields.get(FP["approval_status"]) != "待审批":
            fails.append(f"approval_status not '待审批': {first_fields.get(FP['approval_status'])}")
        if not first_fields.get(FP["summary"]):
            fails.append("summary should not be empty")

    if not fails:
        print("[PASS] test_submit_three_candidates")
    return fails


async def test_submit_skips_already_submitted():
    """Files with promotion_submitted=true in state should be skipped."""
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rel_a = make_inbox_file(base, "电商大促", "alpha")
        rel_b = make_inbox_file(base, "电商大促", "beta")
        init_state(base, [rel_a, rel_b])
        # Mark rel_a as already submitted
        state_path = base / ".sync_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state[rel_a]["promotion_submitted"] = True
        state[rel_a]["promotion_record_id"] = "rec_old"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        fake = FakeBitableClient()
        result = await submit(
            base_path=base,
            dry_run=False,
            limit=None,
            client=fake,
            table_id="tbl_fake",
        )
        if result["submitted"] != 1:
            fails.append(f"expected submit 1 (only beta), got {result['submitted']}")
        if result["skipped_already"] != 1:
            fails.append(f"expected skipped_already=1, got {result['skipped_already']}")
    if not fails:
        print("[PASS] test_submit_skips_already_submitted")
    return fails


async def test_submit_dry_run_no_state_change():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rel = make_inbox_file(base, "电商大促", "gamma")
        init_state(base, [rel])
        before = load_state(base)

        fake = FakeBitableClient()
        result = await submit(
            base_path=base,
            dry_run=True,
            limit=None,
            client=fake,
            table_id="tbl_fake",
        )
        after = load_state(base)
        if fake.created_log:
            fails.append("dry_run should not call create_record")
        if before != after:
            fails.append("dry_run should not mutate state")
        if result["submitted"] != 0 or result["pending"] != 1:
            fails.append(f"dry_run counters wrong: {result}")
    if not fails:
        print("[PASS] test_submit_dry_run_no_state_change")
    return fails



async def test_apply_approved_migrates_file():
    """Approved record should copy file 11_ -> 10_ and rewrite state."""
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rel = make_inbox_file(base, "电商大促", "delta")
        init_state(base, [rel])

        fake = FakeBitableClient()
        # First submit to create a pending record.
        await submit(
            base_path=base, dry_run=False, limit=None,
            client=fake, table_id="tbl_fake",
        )
        state_after_submit = load_state(base)
        rid = state_after_submit[rel]["promotion_record_id"]

        # Flip to approved.
        fake.set_approval(rid, "通过")

        result = await apply(
            base_path=base, dry_run=False,
            client=fake, table_id="tbl_fake",
        )
        if result["approved"] != 1:
            fails.append(f"expected approved=1, got {result}")

        src = base / INBOX_DIR_NAME / "电商大促" / "delta.md"
        dst = base / FORMAL_DIR_NAME / "电商大促" / "delta.md"
        if src.exists():
            fails.append(f"source file should be deleted: {src}")
        if not dst.exists():
            fails.append(f"dest file missing: {dst}")
        else:
            content = dst.read_text(encoding="utf-8")
            if "promoted_from" not in content:
                fails.append("promoted_from missing in migrated frontmatter")
            if "promoted_at" not in content:
                fails.append("promoted_at missing in migrated frontmatter")

        # State: old removed, new entry dirty
        state_after = load_state(base)
        if rel in state_after:
            fails.append(f"old state entry should be removed: {rel}")
        new_rel = f"{FORMAL_DIR_NAME}/电商大促/delta.md"
        if new_rel not in state_after:
            fails.append(f"new state entry missing: {new_rel}")
        elif not state_after[new_rel].get("dirty"):
            fails.append("new state entry should be dirty=true")

        # 处理时间 was written back
        if not fake.updated_log:
            fails.append("apply should have written back processed_at")
        else:
            _, urid, ufields = fake.updated_log[-1]
            if urid != rid:
                fails.append(f"write-back target wrong: {urid} vs {rid}")
            if FP["processed_at"] not in ufields:
                fails.append(f"processed_at not in write-back: {ufields}")

    if not fails:
        print("[PASS] test_apply_approved_migrates_file")
    return fails


async def test_apply_rejected_deletes_file():
    """Rejected record should delete inbox file + drop state entry."""
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rel = make_inbox_file(base, "电商大促", "epsilon")
        init_state(base, [rel])

        fake = FakeBitableClient()
        await submit(
            base_path=base, dry_run=False, limit=None,
            client=fake, table_id="tbl_fake",
        )
        rid = load_state(base)[rel]["promotion_record_id"]
        fake.set_approval(rid, "驳回")

        result = await apply(
            base_path=base, dry_run=False,
            client=fake, table_id="tbl_fake",
        )
        if result["rejected"] != 1:
            fails.append(f"expected rejected=1, got {result}")

        src = base / INBOX_DIR_NAME / "电商大促" / "epsilon.md"
        if src.exists():
            fails.append(f"rejected file should be deleted: {src}")

        state = load_state(base)
        if rel in state:
            fails.append(f"state entry should be dropped: {rel}")
        new_rel = f"{FORMAL_DIR_NAME}/电商大促/epsilon.md"
        if new_rel in state:
            fails.append(f"rejected should NOT create entry in 10_: {new_rel}")

        # processed_at written back
        if not any(FP["processed_at"] in fields for _, _, fields in fake.updated_log):
            fails.append("apply should write back processed_at on reject")

    if not fails:
        print("[PASS] test_apply_rejected_deletes_file")
    return fails



async def test_apply_skips_already_processed():
    """Records with non-empty processed_at should be skipped."""
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rel = make_inbox_file(base, "电商大促", "zeta")
        init_state(base, [rel])
        fake = FakeBitableClient()
        await submit(
            base_path=base, dry_run=False, limit=None,
            client=fake, table_id="tbl_fake",
        )
        rid = load_state(base)[rel]["promotion_record_id"]
        # Mark record as approved AND already processed.
        fake.set_approval(rid, "通过", processed_at=1234567890000)

        result = await apply(
            base_path=base, dry_run=False,
            client=fake, table_id="tbl_fake",
        )
        if result["approved"] != 0 or result["rejected"] != 0:
            fails.append(f"already-processed should yield 0 actions, got {result}")

        # File should still be in inbox (unchanged).
        src = base / INBOX_DIR_NAME / "电商大促" / "zeta.md"
        if not src.exists():
            fails.append("already-processed source should NOT be migrated")

    if not fails:
        print("[PASS] test_apply_skips_already_processed")
    return fails


async def test_apply_dedupe_duplicate_paths():
    """If same file_path appears twice (duplicate submission), migrate only once."""
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rel = make_inbox_file(base, "电商大促", "eta")
        init_state(base, [rel])
        fake = FakeBitableClient()

        # Submit once normally.
        await submit(
            base_path=base, dry_run=False, limit=None,
            client=fake, table_id="tbl_fake",
        )
        rid_a = load_state(base)[rel]["promotion_record_id"]

        # Simulate an orphan duplicate record with the same file_path (as if
        # a human re-cleared state and resubmitted, or a stale record).
        await fake.create_record(
            "tbl_fake",
            {
                FP["file_path"]: rel,
                FP["approval_status"]: "通过",
                FP["category"]: "电商大促",
                FP["role"]: "copywriter",
                FP["summary"]: "dup",
            },
        )
        fake.set_approval(rid_a, "通过")

        result = await apply(
            base_path=base, dry_run=False,
            client=fake, table_id="tbl_fake",
        )
        # Should migrate only one of the two duplicate records this run.
        if result["approved"] != 1:
            fails.append(f"dedup broken: approved={result['approved']}, expected 1")

    if not fails:
        print("[PASS] test_apply_dedupe_duplicate_paths")
    return fails


async def main():
    print("=" * 70)
    print("Promotion flow tests")
    print("=" * 70)

    all_fails = []
    for coro in (
        test_submit_three_candidates(),
        test_submit_skips_already_submitted(),
        test_submit_dry_run_no_state_change(),
        test_apply_approved_migrates_file(),
        test_apply_rejected_deletes_file(),
        test_apply_skips_already_processed(),
        test_apply_dedupe_duplicate_paths(),
    ):
        fails = await coro
        all_fails.extend(fails)

    print("=" * 70)
    if all_fails:
        print(f"FAIL ({len(all_fails)} assertions failed)")
        for f in all_fails:
            print(f"  - {f}")
        return 1
    print("PASS — all promotion flow tests green")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
