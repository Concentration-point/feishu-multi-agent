"""修复隐患1：清理 .sync_state.json 中卡死的 dirty 记录。

背景：诊断报告指出 5 条记录 dirty=true 但 synced_at 停留在旧时间戳，
说明某次同步失败但 dirty 标记未正确恢复。此脚本提供安全的重置路径。

策略：
- 识别 dirty=true 的条目
- 对每条检查物理文件是否存在
  - 不存在 → 从 state 移除（孤儿条目）
  - 存在 → 重算当前 hash，强制设为"新文件"（删 state entry）
    让下次 sync_once() 把它识别为 new file 重推一次

用法：
  python scripts/reset_dirty_sync.py --dry-run    # 只打印不改
  python scripts/reset_dirty_sync.py              # 实际写回

进阶：
  --all       不只处理 dirty=true，重置所有条目让全库重推
  --verbose   打印每条决策
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERROR] .sync_state.json 解析失败: {e}", file=sys.stderr)
        sys.exit(2)


def save_state(state_file: Path, state: dict) -> None:
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_stuck_dirty(entry: dict) -> bool:
    """dirty=true 的条目就视为需要重置 —— 正常流程下 sync 成功后会清 dirty。"""
    return bool(entry.get("dirty"))


def main() -> int:
    parser = argparse.ArgumentParser(description="清理 .sync_state.json 中卡死的 dirty 记录")
    parser.add_argument("--dry-run", action="store_true", help="只打印不修改")
    parser.add_argument("--all", action="store_true", help="重置所有条目（强制全库重推）")
    parser.add_argument("--verbose", "-v", action="store_true", help="逐条打印决策")
    parser.add_argument(
        "--knowledge-dir", default="knowledge",
        help="知识库根目录（默认 knowledge）",
    )
    args = parser.parse_args()

    base = Path(args.knowledge_dir).resolve()
    state_file = base / ".sync_state.json"

    if not state_file.exists():
        print(f"[SKIP] {state_file} 不存在")
        return 0

    state = load_state(state_file)
    total_before = len(state)

    to_reset: list[str] = []
    orphans: list[str] = []
    kept: list[str] = []

    for rel_path, entry in state.items():
        if args.all or is_stuck_dirty(entry):
            full = base / rel_path
            if not full.exists():
                orphans.append(rel_path)
            else:
                to_reset.append(rel_path)
        else:
            kept.append(rel_path)

    print(f"[SUMMARY] 总条目 {total_before}")
    print(f"  - 保持不动: {len(kept)}")
    print(f"  - 待重置: {len(to_reset)}")
    print(f"  - 孤儿(物理文件缺失): {len(orphans)}")

    if args.verbose or args.dry_run:
        if to_reset:
            print("\n[RESET 将删除 state entry 让 sync 识别为新文件]")
            for p in to_reset:
                entry = state.get(p, {})
                print(f"  - {p}  dirty={entry.get('dirty')}  synced_at={entry.get('synced_at')}")
        if orphans:
            print("\n[ORPHAN 将从 state 中直接删除]")
            for p in orphans:
                print(f"  - {p}")

    if args.dry_run:
        print("\n[DRY-RUN] 未写回 .sync_state.json")
        return 0

    # 实际写回
    new_state = {k: v for k, v in state.items() if k in kept}
    save_state(state_file, new_state)
    now_iso = datetime.now(timezone.utc).isoformat()
    print(
        f"\n[DONE] 已重置 {len(to_reset)} 条 + 清理 {len(orphans)} 孤儿，"
        f"剩余 {len(new_state)} 条，写回时间 {now_iso}"
    )
    print("下次 sync_once() 会把重置的文件当作新文件重推一次。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
