from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.read_knowledge import execute as read_knowledge_execute
from tools.search_knowledge import execute as search_knowledge_execute
from tools import AgentContext


async def main() -> int:
    ctx = AgentContext(record_id="test-reviewer", project_name="test", role_id="reviewer")

    queries = [
        "禁用词 美妆",
        "小红书 规范",
        "品牌调性 检查",
        "事实核查 数据 来源",
    ]

    print("=" * 60)
    print("审核 Agent 规则库自检")
    print("=" * 60)

    all_ok = True

    for query in queries:
        print(f"\n[QUERY] {query}")
        result = await search_knowledge_execute({"query": query}, ctx)
        if not result or "未找到" in result:
            print("  FAIL: 搜索无结果")
            all_ok = False
            continue
        print("  OK: 搜索命中")
        print(result[:400])

    rule_files = [
        "raw/rules/广告法禁用词.md",
        "raw/rules/平台规范.md",
        "raw/rules/品牌调性检查清单.md",
        "raw/rules/事实核查要点.md",
    ]

    for rel_path in rule_files:
        print(f"\n[READ] {rel_path}")
        content = await read_knowledge_execute({"filepath": rel_path}, ctx)
        if not content or "错误" in content:
            print("  FAIL: 读取失败")
            all_ok = False
            continue
        print(f"  OK: 读取成功，长度={len(content)}")
        print(content[:240])

    print("\n" + "=" * 60)
    if all_ok:
        print("RESULT: PASS")
        return 0
    print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
