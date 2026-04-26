"""动态路由排查工具 — 给一个 record_id 或客户名关键字，输出状态字段实际值和路由查表结果。

用途:
    定位"动态路由步数 0、啥都没干就结束"类问题，看是状态字段写错了还是状态本身就是终态。

使用:
    python scripts/diagnose_route.py --record recvhUtqzEGCTf
    python scripts/diagnose_route.py --client 烧烤店测试222
    python scripts/diagnose_route.py --client TEST-           # 模糊匹配 [TEST-...] 前缀
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


from config import (  # noqa: E402
    FIELD_MAP_PROJECT,
    PROJECT_TABLE_ID,
    ROUTE_TABLE,
    ROUTE_TERMINAL_STATUSES,
    VALID_STATUSES,
)
from feishu.bitable import BitableClient  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", help="精确 record_id")
    parser.add_argument("--client", help="客户名关键字（模糊匹配）")
    parser.add_argument("--limit", type=int, default=20, help="模糊匹配最多列出多少条")
    args = parser.parse_args()

    if not args.record and not args.client:
        print("✗ 必须提供 --record 或 --client")
        return 2

    client = BitableClient()
    fp = FIELD_MAP_PROJECT

    if args.record:
        records = [await _fetch_one(client, args.record)]
        records = [r for r in records if r]
    else:
        all_records = await client.list_records(PROJECT_TABLE_ID, page_size=200)
        kw = args.client
        records = [
            r for r in all_records
            if kw in str(r["fields"].get(fp["client_name"], ""))
        ][: args.limit]

    if not records:
        print("✗ 未找到匹配记录")
        return 1

    print("=" * 70)
    print(f"路由排查 — {len(records)} 条匹配")
    print("=" * 70)
    print(f"ROUTE_TABLE 键: {list(ROUTE_TABLE.keys())}")
    print(f"终态集合:     {ROUTE_TERMINAL_STATUSES}")
    print(f"VALID_STATUSES: {VALID_STATUSES}")
    print("-" * 70)

    for r in records:
        rid = r["record_id"]
        f = r["fields"]
        status_raw = f.get(fp["status"])
        status_str = str(status_raw).strip() if status_raw else ""
        client_name = f.get(fp["client_name"], "")
        brief = f.get(fp["brief"], "")
        brief_analysis = f.get(fp["brief_analysis"], "")

        print(f"\n[{rid}]  客户: {client_name}")
        print(f"  状态字段原始值: {status_raw!r}")
        print(f"  状态字段 type:  {type(status_raw).__name__}")
        print(f"  归一化:        {status_str!r}")

        # 路由判定
        if not status_str:
            verdict = "✗ 状态为空字符串 → 路由查表未命中 → 直接终止"
        elif status_str in ROUTE_TERMINAL_STATUSES:
            verdict = "✗ 状态已是终态（已完成/已驳回）→ 主循环不进入"
        elif status_str in ROUTE_TABLE:
            next_role = ROUTE_TABLE[status_str]
            verdict = f"✓ 命中路由 → 下一角色: {next_role}"
        else:
            close = [s for s in ROUTE_TABLE if s in status_str or status_str in s]
            verdict = f"✗ 状态不在 ROUTE_TABLE 中（'未知状态'）→ 终止。可能误写: {close or '无近似项'}"

        print(f"  路由判定:      {verdict}")
        print(f"  Brief 长度:    {len(str(brief))}")
        print(f"  Brief 解读长度: {len(str(brief_analysis))}")

    return 0


async def _fetch_one(client: BitableClient, record_id: str) -> dict | None:
    try:
        records = await client.list_records(PROJECT_TABLE_ID, page_size=200)
        for r in records:
            if r["record_id"] == record_id:
                return r
    except Exception as exc:
        print(f"✗ 拉取失败: {type(exc).__name__}: {exc}")
    return None


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[abort] 用户中断")
        raise SystemExit(130)
