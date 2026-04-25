"""本地 knowledge/ 目录 → 飞书知识空间节点树 全量同步（幂等）。

范围：01_企业底座 ~ 10_经验沉淀 十个顶层目录，完整保持目录层级。
排除：11_待整理收件箱 / references / 隐藏文件 / _index.md / README.md / 非 .md 文件

执行语义：
- 本地目录 → 飞书节点（obj_type=docx，但不写内容）
- 本地 .md → 飞书节点 + 写入 docx 内容
- 同 title 已存在的子节点 → 复用 + 覆盖内容（不会重复创建）

API 依赖：
- wiki.spaces.list_nodes (parent_node_token 分页)
- wiki.spaces.create_node
- docx.update_doc_content

命令行：
    python -m scripts.sync_local_to_wiki [--dry-run] [--only=01_企业底座,10_经验沉淀]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from config import KNOWLEDGE_BASE_PATH, WIKI_SPACE_ID
from feishu.wiki import FeishuAPIError, FeishuWikiClient
from tools.write_wiki import prepare_docx_markdown

logger = logging.getLogger(__name__)


# 本地顶层目录 → 飞书节点 title（必须和 sync/wiki_sync.py 的 _LAYER_LABELS 一致）
TOP_DIR_MAP: dict[str, str] = {
    "01_企业底座": "企业底座",
    "02_服务方法论": "服务方法论",
    "03_行业知识": "行业知识",
    "04_平台打法": "平台打法",
    "05_标准模板": "标准模板",
    "06_客户档案": "客户档案",
    "07_项目档案": "项目档案",
    "08_项目执行记录": "项目执行记录",
    "09_项目复盘": "项目复盘",
    "10_经验沉淀": "经验沉淀",
}

# 文件级和文件夹级排除
_EXCLUDED_FILENAMES = {"README.md", "_index.md", ".DS_Store"}
_EXCLUDED_DIRNAMES = {"__pycache__", ".git"}


class Stats:
    def __init__(self) -> None:
        self.dirs_created = 0
        self.dirs_reused = 0
        self.files_created = 0
        self.files_updated = 0
        self.files_skipped = 0
        self.failed = 0

    def print_summary(self) -> None:
        print("=" * 60)
        print(
            f"目录: 新建 {self.dirs_created}，复用 {self.dirs_reused}"
        )
        print(
            f"文档: 新建 {self.files_created}，更新 {self.files_updated}，"
            f"跳过 {self.files_skipped}"
        )
        print(f"失败: {self.failed}")


def _should_skip_item(item: Path) -> bool:
    """判断本地 item（目录或文件）是否该跳过。"""
    name = item.name
    if name.startswith("."):
        return True
    if item.is_dir() and name in _EXCLUDED_DIRNAMES:
        return True
    if item.is_file() and name in _EXCLUDED_FILENAMES:
        return True
    if item.is_file() and item.suffix != ".md":
        return True
    return False


async def _ensure_child_node(
    wiki: FeishuWikiClient,
    space_id: str,
    parent_token: str,
    title: str,
    existing_by_title: dict[str, dict],
    stats: Stats,
    dry_run: bool,
) -> dict | None:
    """确保父节点下有一个叫 title 的子节点；已存在就复用，否则创建。"""
    if title in existing_by_title:
        stats.dirs_reused += 1
        return existing_by_title[title]

    if dry_run:
        print(f"    [DRY] 会创建节点: {title}")
        stats.dirs_created += 1
        return {
            "node_token": f"dry_{title}",
            "obj_token": f"dry_{title}",
            "title": title,
        }

    try:
        node = await wiki.create_node(space_id, parent_token, title)
        print(f"    [DIR+] {title} → {node.get('node_token')}")
        stats.dirs_created += 1
        existing_by_title[title] = node
        return node
    except FeishuAPIError as e:
        print(f"    [FAIL] 建目录节点 {title} 失败: {e}")
        stats.failed += 1
        return None


async def _preview_dir_dry(local_dir: Path, stats: Stats, depth: int) -> None:
    """DRY-RUN 下递归预览某个不存在于飞书的目录会创建什么（不调 API）。"""
    indent = "  " * depth
    items = sorted(
        [i for i in local_dir.iterdir() if not _should_skip_item(i)],
        key=lambda p: (not p.is_dir(), p.name),
    )
    for item in items:
        if item.is_dir():
            print(f"{indent}📁 {item.name}/")
            print(f"{indent}  [DRY] 会创建节点: {item.name}")
            stats.dirs_created += 1
            await _preview_dir_dry(item, stats, depth + 1)
        elif item.is_file():
            raw = item.read_text(encoding="utf-8")
            if not raw.strip():
                stats.files_skipped += 1
                continue
            cleaned = prepare_docx_markdown(raw)
            print(f"{indent}  [DRY] 会创建: {item.name} ({len(cleaned)} 字符)")
            stats.files_created += 1


async def _sync_dir(
    local_dir: Path,
    wiki_parent_token: str,
    wiki: FeishuWikiClient,
    space_id: str,
    stats: Stats,
    dry_run: bool,
    depth: int,
) -> None:
    """递归同步一个本地目录到飞书节点（其所有子目录和 .md 文件）。"""
    indent = "  " * depth

    # 列飞书父节点下现有的所有直接子节点
    try:
        existing = await wiki.list_nodes(space_id, parent_node_token=wiki_parent_token)
    except FeishuAPIError as e:
        print(f"{indent}✗ 列 {local_dir.name} 的飞书子节点失败: {e}")
        stats.failed += 1
        return

    existing_by_title: dict[str, dict] = {}
    # 同名节点取第一个（避免之前重复创建的污染）
    for n in existing:
        t = n.get("title", "")
        if t not in existing_by_title:
            existing_by_title[t] = n

    # 先处理子目录，再处理文件，排序保证稳定
    items = sorted(
        [i for i in local_dir.iterdir() if not _should_skip_item(i)],
        key=lambda p: (not p.is_dir(), p.name),  # 目录优先，同级按名字
    )

    for item in items:
        if item.is_dir():
            print(f"{indent}📁 {item.name}/")
            node = await _ensure_child_node(
                wiki, space_id, wiki_parent_token, item.name,
                existing_by_title, stats, dry_run,
            )
            if node is None:
                continue
            # DRY-RUN: 假 token 不能递归查飞书，改走本地预览
            if dry_run and str(node.get("node_token", "")).startswith("dry_"):
                await _preview_dir_dry(item, stats, depth + 1)
            else:
                await _sync_dir(
                    item, node["node_token"], wiki, space_id, stats, dry_run, depth + 1
                )

        elif item.is_file():
            title = item.stem  # 去掉 .md
            raw = item.read_text(encoding="utf-8")
            if not raw.strip():
                print(f"{indent}  ⊘ {item.name}（空文件，跳过）")
                stats.files_skipped += 1
                continue

            cleaned = prepare_docx_markdown(raw)
            existing_node = existing_by_title.get(title)

            if dry_run:
                action = "更新" if existing_node else "创建"
                print(f"{indent}  [DRY] 会{action}: {item.name} ({len(cleaned)} 字符)")
                if existing_node:
                    stats.files_updated += 1
                else:
                    stats.files_created += 1
                continue

            try:
                if existing_node:
                    obj_token = existing_node.get("obj_token", "")
                    if not obj_token:
                        print(f"{indent}  [SKIP] {title}: 节点无 obj_token")
                        stats.files_skipped += 1
                        continue
                    await wiki.update_doc_content(obj_token, cleaned)
                    print(f"{indent}  [FILE→] {item.name} 内容已覆盖")
                    stats.files_updated += 1
                else:
                    node = await wiki.create_node(space_id, wiki_parent_token, title)
                    obj_token = node.get("obj_token", "")
                    if obj_token:
                        await wiki.update_doc_content(obj_token, cleaned)
                    print(f"{indent}  [FILE+] {item.name} → {node.get('node_token')}")
                    stats.files_created += 1
                    existing_by_title[title] = node
            except FeishuAPIError as e:
                print(f"{indent}  [FAIL] {item.name}: {e}")
                stats.failed += 1


async def main() -> int:
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="本地 knowledge/ → 飞书知识空间 全量同步")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不调 API")
    parser.add_argument(
        "--only",
        default="",
        help="只同步指定的顶层目录，多个逗号分隔（如 10_经验沉淀,01_企业底座）",
    )
    args = parser.parse_args()

    if not WIKI_SPACE_ID:
        print("错误: .env 没配置 WIKI_SPACE_ID")
        return 1

    base_path = Path(KNOWLEDGE_BASE_PATH)
    if not base_path.is_absolute():
        base_path = Path.cwd() / base_path
    if not base_path.exists():
        print(f"错误: 知识库目录不存在 {base_path}")
        return 1

    only_set: set[str] | None = None
    if args.only.strip():
        only_set = {p.strip() for p in args.only.split(",") if p.strip()}

    wiki = FeishuWikiClient()
    stats = Stats()

    print(f"目标空间: {WIKI_SPACE_ID}")
    print(f"本地路径: {base_path}")
    if args.dry_run:
        print("模式: DRY-RUN（不执行任何 API 写操作）")
    if only_set:
        print(f"只同步: {only_set}")
    print("=" * 60)

    # 1. 列空间根下的顶层节点
    try:
        root_level = await wiki.list_nodes(WIKI_SPACE_ID)
    except FeishuAPIError as e:
        print(f"✗ 列空间根节点失败: {e}")
        return 2

    if not root_level:
        print("✗ 空间根级为空，请先跑 scripts.init_wiki_tree")
        return 2

    root_token = root_level[0]["node_token"]
    print(f"空间根节点: {root_level[0].get('title', '?')} → {root_token}")
    print()

    # 2. 在"首页"（根节点）下列出已有的顶层分类节点
    try:
        top_children = await wiki.list_nodes(WIKI_SPACE_ID, parent_node_token=root_token)
    except FeishuAPIError as e:
        print(f"✗ 列顶层分类节点失败: {e}")
        return 2

    # title → node（同名取第一个）
    top_by_title: dict[str, dict] = {}
    for n in top_children:
        t = n.get("title", "")
        if t not in top_by_title:
            top_by_title[t] = n

    # 3. 按 TOP_DIR_MAP 处理每个本地顶层目录
    for local_name, wiki_title in TOP_DIR_MAP.items():
        if only_set and local_name not in only_set:
            continue

        local_top = base_path / local_name
        if not local_top.exists() or not local_top.is_dir():
            print(f"⊘ 本地缺失 {local_name}/，跳过")
            continue

        wiki_top_node = top_by_title.get(wiki_title)
        if not wiki_top_node:
            print(
                f"✗ 飞书顶层节点 「{wiki_title}」 不存在，请先跑 "
                "`python -m scripts.init_wiki_tree`"
            )
            stats.failed += 1
            continue

        print(f"📁 {local_name}/  →  「{wiki_title}」")
        await _sync_dir(
            local_top,
            wiki_top_node["node_token"],
            wiki,
            WIKI_SPACE_ID,
            stats,
            args.dry_run,
            depth=1,
        )
        print()

    print()
    stats.print_summary()
    return 0 if stats.failed == 0 else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
