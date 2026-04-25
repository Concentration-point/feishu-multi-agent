"""修复隐患2（历史数据层）：合并近重复的 wiki 文件。

配合 agents/base.py 的 _build_wiki_title 命名策略一起用：
- base.py 侧：新写入的 wiki 文件用「规整化 + md5 指纹」命名，同语义自动覆盖
- 本脚本：扫描既有 wiki/，对同 role + 同 category 下"规整化后相同"的文件做合并

合并策略：
- 按 (role, category, normalized_lesson_fingerprint) 分组
- 每组保留最新 mtime 的文件，其余文件的正文 append 到保留文件底部（带分隔线）
- 从 .sync_state.json 中移除被合并的条目

用法：
  python scripts/dedupe_wiki.py --dry-run
  python scripts/dedupe_wiki.py            # 实际合并
  python scripts/dedupe_wiki.py --verbose
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def normalize_lesson(text: str) -> str:
    """规整化：去空白 / 去标点 / 小写。"""
    return re.sub(r"[\s\W_]+", "", text).lower()


def extract_role(filename: str) -> str:
    """从文件名前缀提取 role_id（到第一个下划线）。"""
    stem = Path(filename).stem
    return stem.split("_", 1)[0] if "_" in stem else ""


def extract_lesson_from_content(content: str) -> str:
    """从文件正文提取"经验教训"段。"""
    # 剥 frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2]
    # 找 "## 经验教训" 段
    m = re.search(r"##\s*经验教训\s*\n(.+?)(?=\n##|\n>|\Z)", content, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 退化：用文件前 40 字作为 lesson 代理
    return content.strip()[:40]


def compute_fingerprint(lesson: str) -> str:
    return hashlib.md5(normalize_lesson(lesson).encode("utf-8")).hexdigest()[:8]


def main() -> int:
    parser = argparse.ArgumentParser(description="合并近重复的 wiki 文件")
    parser.add_argument("--dry-run", action="store_true", help="只打印不改文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="逐组打印")
    parser.add_argument("--wiki-dir", default="knowledge/wiki")
    parser.add_argument("--state-file", default="knowledge/.sync_state.json")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir).resolve()
    state_file = Path(args.state_file).resolve()

    if not wiki_dir.exists():
        print(f"[SKIP] {wiki_dir} 不存在")
        return 0

    # 按 (role, category, fingerprint) 分组
    groups: dict[tuple[str, str, str], list[Path]] = defaultdict(list)
    for md in wiki_dir.rglob("*.md"):
        if md.name.startswith("_"):
            continue
        category = md.parent.name if md.parent != wiki_dir else "未分类"
        content = md.read_text(encoding="utf-8")
        role = extract_role(md.name) or "unknown"
        lesson = extract_lesson_from_content(content)
        fp = compute_fingerprint(lesson)
        groups[(role, category, fp)].append(md)

    # 只处理多于 1 个文件的组
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}

    print(f"[SUMMARY] 扫描 {len(groups)} 组，发现 {len(duplicates)} 组近重复")
    if not duplicates:
        return 0

    total_remove = sum(len(v) - 1 for v in duplicates.values())
    print(f"  - 将保留 {len(duplicates)} 个主文件，合并删除 {total_remove} 个冗余")

    removed_rel_paths: list[str] = []
    kb_root = wiki_dir.parent  # = knowledge/

    for (role, category, fp), files in duplicates.items():
        # 按 mtime 降序，最新的作为主文件
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        primary = files[0]
        merged = files[1:]

        if args.verbose or args.dry_run:
            print(f"\n[GROUP] role={role} category={category} fp={fp}")
            print(f"  KEEP  → {primary.relative_to(kb_root)}")
            for m in merged:
                print(f"  MERGE → {m.relative_to(kb_root)}")

        if args.dry_run:
            continue

        # 把冗余文件的正文（跳过 frontmatter）append 到主文件底部
        addition_parts: list[str] = []
        for m in merged:
            text = m.read_text(encoding="utf-8")
            if text.startswith("---"):
                splits = text.split("---", 2)
                if len(splits) >= 3:
                    text = splits[2]
            stem = m.stem
            addition_parts.append(
                f"\n\n---\n\n<!-- 已合并自 {stem} -->\n\n{text.strip()}"
            )

        if addition_parts:
            with primary.open("a", encoding="utf-8") as f:
                f.write("".join(addition_parts))

        for m in merged:
            rel = m.relative_to(kb_root).as_posix()
            m.unlink()
            removed_rel_paths.append(rel)

    # 清理 .sync_state.json 中被删除条目
    if removed_rel_paths and state_file.exists() and not args.dry_run:
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            for rp in removed_rel_paths:
                state.pop(rp, None)
            state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"\n[STATE] 从 .sync_state.json 移除 {len(removed_rel_paths)} 条冗余条目")
        except Exception as e:
            print(f"[WARN] 更新 .sync_state.json 失败: {e}", file=sys.stderr)

    if args.dry_run:
        print("\n[DRY-RUN] 未实际合并文件")
    else:
        print(f"\n[DONE] 已合并 {total_remove} 个冗余文件，保留 {len(duplicates)} 个主文件")
        print("建议：随后跑一次 python main.py sync 把合并结果推到飞书")
    return 0


if __name__ == "__main__":
    sys.exit(main())
