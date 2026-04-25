"""在飞书知识空间创建项目需要的 10 个顶层节点（幂等）。

映射规则严格对齐 sync/wiki_sync.py 和 sync/wiki_download.py：
- 下行源头（01-06）：企业底座 / 服务方法论 / 行业知识 / 平台打法 / 标准模板 / 客户档案
- 上行源头（07-10）：项目档案 / 项目执行记录 / 项目复盘 / 经验沉淀
- 不建 11_待整理收件箱 对应节点
- 不建 references 对应节点

使用项目 .env 的 app（非 lark-cli 全局 app）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from config import FEISHU_BASE_URL, WIKI_SPACE_ID
from feishu.auth import TokenManager
from feishu.wiki import FeishuAPIError, FeishuWikiClient


REQUIRED_NODES: list[str] = [
    "企业底座",
    "服务方法论",
    "行业知识",
    "平台打法",
    "标准模板",
    "客户档案",
    "项目档案",
    "项目执行记录",
    "项目复盘",
    "经验沉淀",
]


async def _try_delete_docx(tm: TokenManager, file_token: str) -> tuple[bool, str]:
    """尝试通过 drive API 删除 docx 文件（让 wiki 节点变成孤儿 → 自动清理）。

    API: DELETE /open-apis/drive/v1/files/:file_token?type=docx
    Returns: (成功与否, 说明)
    """
    url = f"{FEISHU_BASE_URL}/drive/v1/files/{file_token}"
    headers = {
        "Authorization": f"Bearer {await tm.get_token()}",
        "Content-Type": "application/json",
    }
    params = {"type": "docx"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(url, headers=headers, params=params)
        try:
            data = resp.json()
        except Exception:
            return False, f"HTTP {resp.status_code} 非 JSON"
        code = data.get("code", -1)
        if resp.status_code == 200 and code == 0:
            return True, "ok"
        return False, f"code={code} msg={data.get('msg', '?')}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def cleanup_duplicates(
    client: FeishuWikiClient, root_token: str
) -> int:
    """扫描根下重复 title 的节点，保留第一个，删除其余。"""
    existing = await client.list_nodes(WIKI_SPACE_ID, parent_node_token=root_token)
    by_title: dict[str, list[dict]] = {}
    for n in existing:
        by_title.setdefault(n.get("title", ""), []).append(n)

    duplicates = {t: v for t, v in by_title.items() if len(v) > 1}
    if not duplicates:
        print("没有重复节点，无需清理")
        return 0

    print(f"发现 {len(duplicates)} 个 title 存在重复，尝试删除多余副本")
    tm = TokenManager()
    deleted = 0
    failed = 0

    for title, nodes in duplicates.items():
        # 保留第一个（create 时间最早的），删除其余
        keep = nodes[0]
        dup_list = nodes[1:]
        print(f"  [{title}] 保留 {keep.get('node_token')}，删除 {len(dup_list)} 份")
        for dup in dup_list:
            obj_token = dup.get("obj_token", "")
            if not obj_token:
                print(f"    - node={dup.get('node_token')} 无 obj_token，跳过")
                failed += 1
                continue
            ok, msg = await _try_delete_docx(tm, obj_token)
            if ok:
                print(f"    - docx={obj_token} 已删除")
                deleted += 1
            else:
                print(f"    - docx={obj_token} 删除失败: {msg}")
                failed += 1

    client.invalidate_cache(WIKI_SPACE_ID)
    print(f"清理结果: 成功 {deleted}，失败 {failed}")
    return 0 if failed == 0 else 4


async def main() -> int:
    parser = argparse.ArgumentParser(description="初始化飞书知识空间的 10 个顶层节点")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="清理重复节点（每个 title 只保留第一个，删除其余）",
    )
    args = parser.parse_args()

    if not WIKI_SPACE_ID:
        print("错误: 未配置 WIKI_SPACE_ID（.env 里补上）")
        return 1

    client = FeishuWikiClient()

    print(f"目标空间: {WIKI_SPACE_ID}")
    print("=" * 60)

    # 1. 找根节点（空间根 = "首页"）
    try:
        root_level = await client.list_nodes(WIKI_SPACE_ID)
    except FeishuAPIError as e:
        print(f"✗ 列空间根级节点失败: {e}")
        return 2

    if not root_level:
        print("✗ 空间根级无节点——请确认空间是否被正确初始化")
        return 2

    root_token = root_level[0]["node_token"]
    root_title = root_level[0].get("title", "(无标题)")
    print(f"根节点: {root_title} → {root_token}")

    # 如果指定 --cleanup，先跑清理
    if args.cleanup:
        print()
        print("--- CLEANUP 模式 ---")
        rc = await cleanup_duplicates(client, root_token)
        if rc != 0:
            return rc
        print()

    # 2. 列根节点下已有子节点做去重
    try:
        existing_children = await client.list_nodes(
            WIKI_SPACE_ID, parent_node_token=root_token
        )
    except FeishuAPIError as e:
        print(f"✗ 列根下子节点失败: {e}")
        return 2

    # title → list of nodes（可能有重复）
    by_title: dict[str, list[dict]] = {}
    for n in existing_children:
        title = n.get("title", "")
        by_title.setdefault(title, []).append(n)

    print(f"根下现有节点: {len(existing_children)} 个")
    for title in sorted(by_title.keys()):
        count = len(by_title[title])
        tag = f"×{count} [!!]" if count > 1 else ""
        print(f"  - {title} {tag}")
    print()

    # 3. 按 REQUIRED_NODES 建节点（已存在就跳过）
    stats = {"created": 0, "skipped": 0, "failed": 0, "dup_warn": 0}

    for title in REQUIRED_NODES:
        if title in by_title:
            count = len(by_title[title])
            if count == 1:
                print(f"  [SKIP] {title}（已存在）")
            else:
                print(f"  [SKIP] {title}（已存在 {count} 份 [!!] 需要手动清理）")
                stats["dup_warn"] += 1
            stats["skipped"] += 1
            continue

        try:
            node = await client.create_node(WIKI_SPACE_ID, root_token, title)
            print(f"  [OK]   {title} → {node.get('node_token', '?')}")
            stats["created"] += 1
        except FeishuAPIError as e:
            print(f"  [FAIL] {title}: {e}")
            stats["failed"] += 1
        except Exception as e:
            print(f"  [FAIL] {title}: {type(e).__name__}: {e}")
            stats["failed"] += 1

    print()
    print("=" * 60)
    print(
        f"完成: 新建 {stats['created']}，跳过 {stats['skipped']}，"
        f"失败 {stats['failed']}，重复告警 {stats['dup_warn']}"
    )
    if stats["dup_warn"] > 0:
        print(
            f"\n[!!]  检测到 {stats['dup_warn']} 个 title 存在重复节点，"
            "请在飞书 UI 手动删除多余的那份（wiki 节点 API 不支持删除）"
        )
    return 0 if stats["failed"] == 0 else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
