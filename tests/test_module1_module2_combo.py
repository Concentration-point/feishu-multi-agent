"""模块一 ∩ 模块二 协同闭环冒烟测试。

验证"爆款对标（M1）+ 合规自检（M2）"在文案 Agent 上串成双轨闭环：
- copywriter soul 同时声明 search_reference + search_knowledge
- _REQUIRED_TOOL_CALLS[copywriter] 含两个工具硬约束
- 双轨检索链路：reference 库 + rules 库 都能命中
- reflect prompt 含 reference_pattern + rule_check + conflict_handling
- reviewer→copywriter 经验反哺字段（applicable_roles）正确

运行：
    python tests/test_module1_module2_combo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import ToolRegistry, AgentContext
from agents.base import (
    parse_soul,
    _ROLE_REFLECT_PROMPTS,
    _REQUIRED_TOOL_CALLS,
    _COPYWRITER_REFLECT_PROMPT,
    _REVIEWER_REFLECT_PROMPT,
)


async def main() -> int:
    print("=" * 60)
    print("模块一 ∩ 模块二 协同闭环冒烟测试")
    print("=" * 60)

    fails: list[str] = []

    # 1) copywriter soul 同时声明对标工具 + 规则工具
    soul_path = ROOT / "agents/copywriter/soul.md"
    soul = parse_soul(soul_path.read_text(encoding="utf-8"))
    need = {"search_reference", "search_knowledge", "read_knowledge"}
    missing = need - set(soul.tools)
    if missing:
        fails.append(f"copywriter soul 缺工具 {missing}")
        print(f"[FAIL] copywriter soul 缺工具 {missing}")
    else:
        print(f"[PASS] copywriter soul 含 {need}")

    # 2) 硬约束：copywriter 必调两个工具
    required = _REQUIRED_TOOL_CALLS.get("copywriter", [])
    if "search_reference" in required and "search_knowledge" in required:
        print(f"[PASS] _REQUIRED_TOOL_CALLS[copywriter] = {required}")
    else:
        fails.append(f"copywriter 硬约束不含双工具: {required}")
        print(f"[FAIL] copywriter 硬约束: {required}")

    # 3) reflect prompt 含双轨字段
    prompt = _COPYWRITER_REFLECT_PROMPT
    fields_needed = ["reference_pattern", "rule_check", "conflict_handling"]
    missing_fields = [f for f in fields_needed if f not in prompt]
    if missing_fields:
        fails.append(f"copywriter reflect prompt 缺字段 {missing_fields}")
        print(f"[FAIL] copywriter reflect prompt 缺字段 {missing_fields}")
    else:
        print(f"[PASS] copywriter reflect prompt 含 {fields_needed}")

    # 4) reviewer reflect prompt 正确声明 applicable_roles 含 copywriter（反哺通道）
    if "copywriter" in _REVIEWER_REFLECT_PROMPT:
        print("[PASS] reviewer reflect prompt 已声明 applicable_roles=[reviewer, copywriter]")
    else:
        fails.append("reviewer reflect prompt 未含反哺声明")
        print("[FAIL] reviewer reflect prompt 未含 copywriter")

    # 5) 双链路检索实证
    reg = ToolRegistry()
    ctx = AgentContext(
        record_id="rec_combo_test",
        project_name="组合验证项目",
        role_id="copywriter",
    )

    # 5a) 模块一 search_reference 命中
    r1 = await reg.call_tool(
        "search_reference",
        {"query": "精华液 种草", "platform": "小红书"},
        ctx,
    )
    if "对标参考" in r1 and "开头抓手" in r1 and "内容结构" in r1:
        print("[PASS] 轨道 A（search_reference）命中且返回结构化卡片")
    else:
        fails.append("search_reference 返回异常")
        print(f"[FAIL] search_reference 返回异常: {r1[:200]}")

    # 5b) 模块二 search_knowledge 命中禁用词规则
    r2 = await reg.call_tool(
        "search_knowledge",
        {"query": "禁用词 美妆"},
        ctx,
    )
    if "禁用词" in r2 and "广告法" in r2:
        print("[PASS] 轨道 B-1（search_knowledge 禁用词）命中广告法禁用词.md")
    else:
        fails.append("禁用词规则未命中")
        print(f"[FAIL] 禁用词规则未命中: {r2[:200]}")

    # 5c) 模块二 search_knowledge 命中平台规范
    r3 = await reg.call_tool(
        "search_knowledge",
        {"query": "小红书 规范"},
        ctx,
    )
    if "规范" in r3 and ("小红书" in r3 or "平台" in r3):
        print("[PASS] 轨道 B-2（search_knowledge 平台规范）命中平台规范.md")
    else:
        fails.append("平台规范未命中")
        print(f"[FAIL] 平台规范未命中: {r3[:200]}")

    # 5d) 规则全文可读（Agent 发现规则后用 read_knowledge 深读）
    r4 = await reg.call_tool(
        "read_knowledge",
        {"filepath": "02_服务方法论/广告法禁用词.md"},
        ctx,
    )
    if "错误" not in r4 and len(r4) > 200:
        print(f"[PASS] read_knowledge 可读取广告法禁用词.md（长度={len(r4)}）")
    else:
        fails.append("read_knowledge 读取规则失败")
        print(f"[FAIL] read_knowledge 失败: {r4[:200]}")

    # 6) 反哺通道：模拟 reviewer 蒸馏的经验卡片在 applicable_roles 里含 copywriter
    #    base.py 行 505 有代码级兜底确保这一点
    import inspect
    from agents import base as base_mod

    source = inspect.getsource(base_mod._hook_reflect) if hasattr(base_mod, "_hook_reflect") else ""
    # 退化方案：直接看 BaseAgent._hook_reflect 源代码
    source = inspect.getsource(base_mod.BaseAgent._hook_reflect)
    if 'self.role_id == "reviewer"' in source and '"copywriter"' in source:
        print("[PASS] _hook_reflect 代码级兜底：reviewer→copywriter 反哺确保")
    else:
        fails.append("_hook_reflect 未见 reviewer→copywriter 兜底")
        print("[FAIL] _hook_reflect 反哺兜底逻辑异常")

    # 7) soul.md 包含融合工作流关键词（冲突处理 + 双标注）
    body = soul.body
    workflow_kw = ["强制双轨工作流", "轨道 A", "轨道 B", "规则优先于爆款", "对标参考", "合规自检"]
    missing_kw = [k for k in workflow_kw if k not in body]
    if missing_kw:
        fails.append(f"copywriter soul body 缺融合关键词 {missing_kw}")
        print(f"[FAIL] soul body 缺关键词 {missing_kw}")
    else:
        print(f"[PASS] copywriter soul body 含融合工作流关键词 {workflow_kw}")

    print()
    print("=" * 60)
    if fails:
        print(f"RESULT: FAIL ({len(fails)} 项未通过)")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("RESULT: PASS — 模块一 ∩ 模块二 协同闭环打通")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
