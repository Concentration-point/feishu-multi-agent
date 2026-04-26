from __future__ import annotations

from pathlib import Path

from agents.base import parse_soul
from tools import ToolRegistry


ROOT = Path(__file__).resolve().parents[2]


def test_each_soul_file_defines_a_loadable_agent_contract(agent_test_log):
    registry = ToolRegistry()
    available_tools = set(registry.tool_names)
    soul_paths = sorted((ROOT / "agents").glob("*/soul.md"))
    agent_test_log(
        "all soul.md files: loadable tool contract",
        [
            f"扫描 {len(soul_paths)} 个 agents/*/soul.md",
            "逐个解析 name/role_id/description/tools/max_iterations/body",
            "验证每个 soul 声明的工具都能被 ToolRegistry 注册",
            "这一步防止新增 soul 后引用不存在的工具",
        ],
    )

    assert soul_paths
    for soul_path in soul_paths:
        role_id = soul_path.parent.name
        soul = parse_soul(soul_path.read_text(encoding="utf-8"))

        assert soul.role_id == role_id
        assert soul.name
        assert soul.description
        assert soul.max_iterations > 0
        assert soul.body.strip()
        assert set(soul.tools) <= available_tools
