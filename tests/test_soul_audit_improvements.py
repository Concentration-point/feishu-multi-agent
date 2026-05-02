"""灵魂审计改善验证 — 量化知识注入 + 工具数 + max_iterations 的改善效果。"""

from __future__ import annotations

import pytest

from agents.base import (
    load_shared_knowledge,
    parse_soul,
    _COMMON_METHOD_FILES,
    _ROLE_METHOD_FILES,
)
from pathlib import Path

_AGENTS_DIR = Path(__file__).parent.parent / "agents"


# ── 知识分层验证 ──

def test_strategist_not_injected_reviewer_knowledge():
    """策略师不应被注入审核规则、广告法禁用词、品牌调性等 reviewer 专属知识。"""
    knowledge = load_shared_knowledge("strategist")
    assert "广告法禁用词" not in knowledge
    assert "审核规则与风险边界" not in knowledge
    assert "质量红线标准" not in knowledge
    assert "品牌调性检查清单" not in knowledge


def test_project_manager_not_injected_reviewer_knowledge():
    """PM 不应被注入审核规则、广告法禁用词等。"""
    knowledge = load_shared_knowledge("project_manager")
    assert "广告法禁用词" not in knowledge
    assert "审核规则与风险边界" not in knowledge
    assert "品牌调性检查清单" not in knowledge
    assert "Brief 解读规则" not in knowledge


def test_data_analyst_not_injected_reviewer_knowledge():
    """数据分析师不应被注入审核规则、广告法禁用词等。"""
    knowledge = load_shared_knowledge("data_analyst")
    assert "广告法禁用词" not in knowledge
    assert "审核规则与风险边界" not in knowledge


def test_reviewer_still_gets_full_rules():
    """审核角色应保留全部规则知识。"""
    knowledge = load_shared_knowledge("reviewer")
    assert "广告法禁用词" in knowledge
    assert "审核规则与风险边界" in knowledge
    assert "质量红线标准" in knowledge
    assert "品牌调性检查清单" in knowledge


def test_all_roles_get_common_method_files():
    """所有角色都应拿到公共方法论文件（内容生产主流程 + 项目类型SOP）。"""
    for role in ("strategist", "project_manager", "data_analyst", "reviewer", "copywriter"):
        knowledge = load_shared_knowledge(role)
        for f in _COMMON_METHOD_FILES:
            name_without_ext = f.replace(".md", "")
            assert name_without_ext in knowledge, f"{role} 缺少公共文件 {f}"


# ── 工具瘦身验证 ──

def _load_soul(role_id: str):
    soul_path = _AGENTS_DIR / role_id / "soul.md"
    return parse_soul(soul_path.read_text(encoding="utf-8"))


def test_strategist_tool_count_reduced():
    """策略师工具数应从 12 降到 10（删除 get_experience, write_wiki）。"""
    soul = _load_soul("strategist")
    assert "get_experience" not in soul.tools
    assert "write_wiki" not in soul.tools
    assert len(soul.tools) == 10


def test_project_manager_tool_count_reduced():
    """PM 工具数应从 13 降到 6（删除 7 个冗余工具）。"""
    soul = _load_soul("project_manager")
    removed = {"search_knowledge", "read_knowledge", "read_template",
               "write_wiki", "create_content", "get_experience", "negotiate"}
    for tool in removed:
        assert tool not in soul.tools, f"PM 仍含冗余工具 {tool}"
    assert len(soul.tools) == 6


def test_data_analyst_tool_count_reduced():
    """数据分析师工具数应从 6 降到 3（删除 search_knowledge, read_knowledge, get_experience）。"""
    soul = _load_soul("data_analyst")
    assert "search_knowledge" not in soul.tools
    assert "read_knowledge" not in soul.tools
    assert "get_experience" not in soul.tools
    assert len(soul.tools) == 3


# ── max_iterations 验证 ──

def test_max_iterations_reduced():
    """三个角色的 max_iterations 应降低到审计建议值。"""
    assert _load_soul("strategist").max_iterations == 9      # was 15
    assert _load_soul("project_manager").max_iterations == 6  # was 10
    assert _load_soul("data_analyst").max_iterations == 5     # was 8


# ── PM soul.md 行数验证 ──

def test_pm_soul_line_count_reduced():
    """PM soul.md 应从 253 行精简到 ~142 行。"""
    soul_path = _AGENTS_DIR / "project_manager" / "soul.md"
    line_count = len(soul_path.read_text(encoding="utf-8").splitlines())
    assert line_count < 160, f"PM soul.md 仍有 {line_count} 行，应 < 160"
