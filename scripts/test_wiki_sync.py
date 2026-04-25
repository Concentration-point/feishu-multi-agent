"""本地 wiki ↔ 飞书知识空间 异步写入测试脚手架。

六子命令覆盖全生命周期，反复可跑：

    python scripts/test_wiki_sync.py status         # 只读统计当前同步状态
    python scripts/test_wiki_sync.py seed           # 造一条测试 wiki 条目
    python scripts/test_wiki_sync.py once           # 等同 main.py sync，详细日志
    python scripts/test_wiki_sync.py watch -d 30    # 后台异步线程跑 30 秒
    python scripts/test_wiki_sync.py clean          # 清理测试产物
    python scripts/test_wiki_sync.py e2e            # 组合：seed → once → status → clean

每个同步子命令都支持 --dry-run：不打飞书 API，只打印即将发生的同步动作。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows cp936 兼容：把 stdout 强制 UTF-8，避免 print 中文崩
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import KNOWLEDGE_BASE_PATH, WIKI_SPACE_ID, SYNC_INTERVAL
from tools.write_wiki import sanitize_name

logger = logging.getLogger("test_wiki_sync")

# 测试产物目录（seed 命令写这里，clean 命令删这里）
# 注：write_wiki.sanitize_name 会 strip 前导下划线，所以这里用不含特殊前缀的名字
# 让脚本拼出的路径和实际落盘路径一致
_TEST_DIR_NAME = "sync_probe"
_SAFE_TEST_DIR = sanitize_name(_TEST_DIR_NAME)


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso[:19]


def _load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


# ── 子命令 status：只读统计当前状态 ─────────────────────────────
def cmd_status(base: Path) -> int:
    state_file = base / ".sync_state.json"
    state = _load_state(state_file)

    if not state:
        print(f"[STATUS] {state_file} 不存在或为空")
        return 0

    total = len(state)
    dirty: list[tuple[str, dict]] = []
    synced: list[tuple[str, dict]] = []
    orphans: list[str] = []
    bucket: dict[str, int] = defaultdict(int)
    oldest_dirty: str | None = None

    for rel, entry in state.items():
        full = base / rel
        bucket_name = rel.split("/", 1)[0] if "/" in rel else "root"
        bucket[bucket_name] += 1
        if not full.exists():
            orphans.append(rel)
            continue
        if entry.get("dirty"):
            dirty.append((rel, entry))
            ts = entry.get("updated_at", "")
            if ts and (oldest_dirty is None or ts < oldest_dirty):
                oldest_dirty = ts
        else:
            synced.append((rel, entry))

    print("=" * 66)
    print(f"[STATUS] knowledge 根目录: {base}")
    print(f"[STATUS] .sync_state.json 总条目: {total}")
    print(f"  - 已同步 synced : {len(synced)}")
    print(f"  - 待同步 dirty  : {len(dirty)}")
    print(f"  - 孤儿 orphans  : {len(orphans)}")
    if oldest_dirty:
        print(f"  - 最老 dirty    : {_fmt_time(oldest_dirty)}")
    print("\n[STATUS] 按目录分桶:")
    for name, n in sorted(bucket.items(), key=lambda x: -x[1]):
        print(f"    {name:15s}  {n:4d}")
    if dirty:
        print(f"\n[STATUS] 待同步清单（最多 20 条）:")
        for rel, entry in dirty[:20]:
            ts = _fmt_time(entry.get("updated_at"))
            print(f"    · {rel}  (updated_at={ts})")
    if orphans:
        print(f"\n[STATUS] 孤儿条目（物理文件缺失，需 reset_dirty_sync 清理）:")
        for rel in orphans[:10]:
            print(f"    · {rel}")

    print("=" * 66)
    print(f"配置: WIKI_SPACE_ID={'已配置' if WIKI_SPACE_ID else '❌ 未配置'}")
    print(f"       SYNC_INTERVAL={SYNC_INTERVAL}s")
    return 0


# ── 子命令 seed：造一条测试 wiki 条目 ──────────────────────────
async def cmd_seed(base: Path, content_hint: str = "") -> int:
    from tools.write_wiki import execute as write_wiki_execute
    from tools import AgentContext

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    title = f"probe_{ts}"
    category = _TEST_DIR_NAME
    content = (
        f"# 同步链路探针 · {ts}\n\n"
        f"此文档由 scripts/test_wiki_sync.py seed 命令生成，用于验证本地 wiki → 飞书知识空间的异步写入链路。\n\n"
        f"## 探针数据\n"
        f"- 生成时刻: {ts}\n"
        f"- hint: {content_hint or 'none'}\n"
        f"- 预期: 下一轮 sync_once 会把这条推到飞书的 Wiki-{_SAFE_TEST_DIR} 节点下。\n"
    )

    ctx = AgentContext(record_id="probe", project_name="sync_probe", role_id="probe")
    result = await write_wiki_execute(
        {"category": category, "title": title, "content": content}, ctx
    )
    # 使用和 write_wiki 相同的 sanitize 规则计算真实落盘路径
    safe_category = sanitize_name(category)
    safe_title = sanitize_name(title)
    rel_path = f"11_待整理收件箱/{safe_category}/{safe_title}.md"

    # 校验
    target = base / rel_path
    state_file = base / ".sync_state.json"
    state = _load_state(state_file)

    print("=" * 66)
    print(f"[SEED] 已写入 {rel_path}")
    print(f"[SEED] write_wiki 返回: {result}")
    print(f"[SEED] 物理文件存在: {target.exists()}  (size={target.stat().st_size if target.exists() else 0})")
    entry = state.get(rel_path, {})
    print(f"[SEED] .sync_state.json 条目:")
    print(f"    - dirty     : {entry.get('dirty')}")
    print(f"    - hash      : {entry.get('hash', '')[:16]}...")
    print(f"    - updated_at: {_fmt_time(entry.get('updated_at'))}")
    print("=" * 66)
    print("下一步：python scripts/test_wiki_sync.py once   # 触发同步")
    return 0


# ── 子命令 once：触发一次同步（支持 dry-run）──────────────────
async def cmd_once(base: Path, dry_run: bool = False) -> int:
    from sync.wiki_sync import WikiSyncService

    if not WIKI_SPACE_ID and not dry_run:
        print("[ONCE] ❌ WIKI_SPACE_ID 未配置，请在 .env 中设置，或用 --dry-run 仅打印同步计划")
        return 1

    space_id = WIKI_SPACE_ID or "dryrun_space"
    svc = WikiSyncService(space_id, SYNC_INTERVAL)

    # 打印将要同步的文件
    state = _load_state(svc._state_file)
    dirty = svc._find_dirty_files(state)
    print("=" * 66)
    print(f"[ONCE] {'DRY-RUN' if dry_run else 'LIVE'} 模式")
    print(f"[ONCE] 即将同步的文件数: {len(dirty)}")
    for i, rel in enumerate(dirty[:30], 1):
        parent, doc = svc._map_node_path(rel)
        print(f"    {i:3d}. {rel}  →  飞书节点: {parent} / {doc}")
    if len(dirty) > 30:
        print(f"    ... （还有 {len(dirty) - 30} 条未列出）")

    if dry_run:
        print(f"\n[ONCE] DRY-RUN 未实际调用飞书 API")
        return 0

    if not dirty:
        print("[ONCE] 无 dirty 文件，跳过同步")
        return 0

    print(f"\n[ONCE] 开始调用飞书 API 同步...")
    t0 = time.perf_counter()
    before_synced = sum(1 for e in state.values() if not e.get("dirty"))
    try:
        await svc.sync_once()
    except Exception as e:
        print(f"[ONCE] ❌ 同步异常: {type(e).__name__}: {e}")
        return 2
    elapsed = time.perf_counter() - t0

    after_state = _load_state(svc._state_file)
    remaining_dirty = sum(1 for e in after_state.values() if e.get("dirty"))
    failed = [
        (rel, entry) for rel, entry in after_state.items()
        if entry.get("sync_status") == "failed" and entry.get("last_attempt_at")
    ]
    succeeded = [
        (rel, entry) for rel, entry in after_state.items()
        if entry.get("sync_status") == "success" and entry.get("last_attempt_at")
    ]

    print(f"[ONCE] ✅ 同步完成，耗时 {elapsed:.1f}s")
    print(f"       同步成功 {len(succeeded)} 条，剩余 dirty {remaining_dirty} 条，失败 {len(failed)} 条")
    if failed:
        print("[ONCE] 失败文件：")
        for rel, entry in failed[:20]:
            print(f"    · {rel}  ({entry.get('last_error', '')})")
    if remaining_dirty > 0:
        print(f"[ONCE] ⚠️  仍有 {remaining_dirty} 条未同步，查看日志排查具体错误")
    return 0


# ── 子命令 watch：启动异步后台线程 N 秒，观察真实 Agent 场景 ───
async def cmd_watch(base: Path, duration: int, interval: int) -> int:
    from sync.wiki_sync import WikiSyncService

    if not WIKI_SPACE_ID:
        print("[WATCH] ❌ WIKI_SPACE_ID 未配置，无法启动后台线程")
        return 1

    svc = WikiSyncService(WIKI_SPACE_ID, interval)
    print(f"[WATCH] 启动后台 sync 线程，间隔={interval}s，总时长={duration}s")
    print(f"[WATCH] 这模拟 main.py serve 启动后的真实异步同步行为")
    print("=" * 66)

    task = asyncio.create_task(svc.start())

    try:
        elapsed = 0
        while elapsed < duration:
            await asyncio.sleep(min(interval, duration - elapsed))
            elapsed += interval
            state = _load_state(svc._state_file)
            dirty_now = sum(1 for e in state.values() if e.get("dirty"))
            synced_now = sum(1 for e in state.values() if not e.get("dirty"))
            print(
                f"[WATCH t={elapsed:3d}s] dirty={dirty_now:4d}  synced={synced_now:4d}"
            )
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    print("=" * 66)
    print(f"[WATCH] 已停止后台线程")
    return 0


# ── 子命令 clean：清理测试产物 ──────────────────────────────
def cmd_clean(base: Path) -> int:
    probe_dir = base / "11_待整理收件箱" / _SAFE_TEST_DIR
    removed_files = 0
    if probe_dir.exists():
        for f in probe_dir.rglob("*"):
            if f.is_file():
                f.unlink()
                removed_files += 1
        try:
            probe_dir.rmdir()
        except OSError:
            pass
        print(f"[CLEAN] 已删除 {removed_files} 个探针文件，目录 {probe_dir}")
    else:
        print(f"[CLEAN] 探针目录不存在，无需清理")

    # 同步移除 .sync_state.json 里对应条目
    state_file = base / ".sync_state.json"
    state = _load_state(state_file)
    prefix = f"11_待整理收件箱/{_SAFE_TEST_DIR}/"
    keys_to_del = [k for k in state.keys() if k.startswith(prefix)]
    if keys_to_del:
        for k in keys_to_del:
            state.pop(k, None)
        state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[CLEAN] 已从 .sync_state.json 移除 {len(keys_to_del)} 条探针记录")
    return 0


# ── 子命令 e2e：组合流程 seed → status → once → status → clean ─
async def cmd_e2e(base: Path, dry_run: bool = False) -> int:
    print(">>> [E2E 1/5] 当前状态")
    cmd_status(base)

    print("\n>>> [E2E 2/5] 造一条探针")
    rc = await cmd_seed(base, content_hint="e2e combo run")
    if rc != 0:
        return rc

    print("\n>>> [E2E 3/5] 触发一次同步")
    rc = await cmd_once(base, dry_run=dry_run)
    if rc != 0 and not dry_run:
        print("[E2E] once 失败，保留探针文件供排查")
        return rc

    print("\n>>> [E2E 4/5] 同步后状态")
    cmd_status(base)

    print("\n>>> [E2E 5/5] 清理探针")
    return cmd_clean(base)


# ── CLI 入口 ─────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="本地 wiki ↔ 飞书知识空间 异步写入测试脚手架",
    )
    parser.add_argument(
        "--knowledge-dir", default=KNOWLEDGE_BASE_PATH,
        help=f"知识库根目录，默认 {KNOWLEDGE_BASE_PATH}",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="只读统计当前同步状态")

    p_seed = sub.add_parser("seed", help="造一条测试 wiki 条目触发 dirty")
    p_seed.add_argument("--hint", default="", help="可选注释信息")

    p_once = sub.add_parser("once", help="触发一次同步，带详细日志")
    p_once.add_argument("--dry-run", action="store_true",
                        help="只打印同步计划，不实际调飞书 API")

    p_watch = sub.add_parser("watch", help="启动后台异步线程 N 秒")
    p_watch.add_argument("-d", "--duration", type=int, default=30,
                         help="运行时长，默认 30 秒")
    p_watch.add_argument("-i", "--interval", type=int, default=None,
                         help=f"扫描间隔，默认 SYNC_INTERVAL={SYNC_INTERVAL}")

    sub.add_parser("clean", help="清理 seed 产生的探针文件")

    p_e2e = sub.add_parser("e2e", help="组合：seed → once → status → clean")
    p_e2e.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    base = Path(args.knowledge_dir).resolve()
    if not base.exists():
        print(f"❌ 知识库目录不存在: {base}")
        return 2

    if args.cmd == "status":
        return cmd_status(base)
    if args.cmd == "seed":
        return asyncio.run(cmd_seed(base, content_hint=args.hint))
    if args.cmd == "once":
        return asyncio.run(cmd_once(base, dry_run=args.dry_run))
    if args.cmd == "watch":
        interval = args.interval if args.interval is not None else SYNC_INTERVAL
        return asyncio.run(cmd_watch(base, args.duration, interval))
    if args.cmd == "clean":
        return cmd_clean(base)
    if args.cmd == "e2e":
        return asyncio.run(cmd_e2e(base, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
