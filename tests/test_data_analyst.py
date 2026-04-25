"""数据分析师 Agent 单元测试。

测试工具注册、soul.md 加载、query_project_stats schema 验证。
使用方式:
    pytest tests/test_data_analyst.py -v
"""

import json
import pytest
from pathlib import Path


def test_soul_md_exists():
    """soul.md 文件存在且 frontmatter 包含必要字段。"""
    soul_path = Path(__file__).parent.parent / "agents" / "data_analyst" / "soul.md"
    assert soul_path.exists(), "agents/data_analyst/soul.md 不存在"

    text = soul_path.read_text(encoding="utf-8")
    assert "---" in text, "缺少 YAML frontmatter 分隔符"
    assert "role_id: data_analyst" in text
    assert "query_project_stats" in text
    assert "send_report" in text


def test_contract_exists():
    """contract.json 存在且结构正确。"""
    path = Path(__file__).parent.parent / "agents" / "contracts" / "data_analyst.contract.json"
    assert path.exists(), "data_analyst.contract.json 不存在"

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["role_id"] == "data_analyst"
    assert "output" in data
    assert "report_type" in data["output"]


def test_query_project_stats_schema():
    """query_project_stats 工具 schema 符合 OpenAI function calling 格式。"""
    from tools.query_project_stats import SCHEMA

    assert SCHEMA["type"] == "function"
    fn = SCHEMA["function"]
    assert fn["name"] == "query_project_stats"
    assert "parameters" in fn
    props = fn["parameters"]["properties"]
    assert "scope" in props
    assert set(props["scope"]["enum"]) == {"all", "projects", "content", "experience"}


def test_send_report_schema():
    """send_report 工具 schema 符合 OpenAI function calling 格式。"""
    from tools.send_report import SCHEMA

    assert SCHEMA["type"] == "function"
    fn = SCHEMA["function"]
    assert fn["name"] == "send_report"
    assert "title" in fn["parameters"]["required"]
    assert "content" in fn["parameters"]["required"]
    props = fn["parameters"]["properties"]
    assert set(props["report_type"]["enum"]) == {"weekly", "insight", "decision"}


def test_tool_registry_discovers_new_tools():
    """ToolRegistry 能扫描到 query_project_stats 和 send_report。"""
    from tools import ToolRegistry

    registry = ToolRegistry()
    assert "query_project_stats" in registry.tool_names
    assert "send_report" in registry.tool_names


def test_role_names_consistency():
    """data_analyst 在三处 _ROLE_NAMES 中均已注册。"""
    from agents.base import BaseAgent

    assert "data_analyst" in BaseAgent._ROLE_NAMES
    assert BaseAgent._ROLE_NAMES["data_analyst"] == "数据分析师"


def test_soul_loads_via_base_agent_parser():
    """BaseAgent 的 soul 解析器能正确加载 data_analyst 的 soul.md。"""
    from agents.base import load_soul_with_platform_patch

    soul, patched = load_soul_with_platform_patch("data_analyst", None)
    assert soul.name == "数据分析师"
    assert soul.role_id == "data_analyst"
    assert "query_project_stats" in soul.tools
    assert "send_report" in soul.tools
    assert not patched


def test_cli_parser_has_report_command():
    """CLI parser 包含 report 子命令。"""
    from main import build_parser

    parser = build_parser()
    args = parser.parse_args(["report", "--type", "insight"])
    assert args.command == "report"
    assert args.report_type == "insight"

    args_default = parser.parse_args(["report"])
    assert args_default.report_type == "weekly"
