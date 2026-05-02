"""灵魂审计 Live 验收 — 调真实 LLM API 验证策略师/PM/数据分析师改动后行为正常。

使用 run_unit 模式（不依赖 Bitable），只需 .env 中 LLM 配置可用。

运行:
    py -3 -m pytest tests/test_soul_audit_live.py -v -s --tb=short
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)


def _env_ready() -> bool:
    """检查 .env 中 LLM 配置是否可用。"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("LLM_API_KEY=") and len(line.split("=", 1)[1].strip()) > 5:
            return True
    return False


skip_reason = "跳过：.env 中无可用 LLM_API_KEY"
pytestmark = pytest.mark.skipif(not _env_ready(), reason=skip_reason)


def _print_result(role: str, result, elapsed: float):
    """打印验收结果摘要。"""
    print(f"\n{'='*60}")
    print(f"角色: {role}")
    print(f"耗时: {elapsed:.1f}s")
    print(f"迭代轮次: {len([m for m in result.messages if m.get('role') == 'assistant'])}")
    tools_called = [tc['tool_name'] for tc in result.tool_calls]
    print(f"工具调用: {tools_called}")
    print(f"输出长度: {len(result.output)} 字")
    print(f"输出预览: {result.output[:200]}...")
    print(f"缺失必调工具: {result.missing_required_tools or '无'}")
    print(f"{'='*60}")


@pytest.mark.asyncio
async def test_strategist_live():
    """策略师 live 验收：输入 Brief，验证能产出策略方案。"""
    from agents.base import BaseAgent

    agent = BaseAgent(
        role_id="strategist",
        record_id="rec_live_strategist",
    )

    print(f"\n[strategist] soul tools: {agent.soul.tools}")
    print(f"[strategist] max_iterations: {agent.soul.max_iterations}")
    print(f"[strategist] shared_knowledge length: {len(agent.shared_knowledge)} chars")

    t0 = time.perf_counter()
    result = await agent.run(
        input_data=(
            "客户 Brief：双十一国货美妆大促，品牌「花知晓」，"
            "主推新款花瓣唇釉系列，预算 5 万，"
            "目标 18-28 岁 Z 世代女性消费者，"
            "主打平台小红书和抖音，需要种草笔记 + 口播脚本。"
        ),
        strategy={"项目类型": "电商大促", "目标平台": ["小红书", "抖音"]},
        context={"record_id": "rec_live_strategist", "project_name": "花知晓双十一"},
    )
    elapsed = time.perf_counter() - t0
    _print_result("策略师", result, elapsed)

    assert result.role_id == "strategist"
    assert len(result.output) > 50, "策略师输出过短"
    assert result.missing_required_tools == []


@pytest.mark.asyncio
async def test_project_manager_live():
    """PM live 验收：输入审核结果，验证能产出排期 + 交付摘要。"""
    from agents.base import BaseAgent

    agent = BaseAgent(
        role_id="project_manager",
        record_id="rec_live_pm",
    )

    print(f"\n[project_manager] soul tools: {agent.soul.tools}")
    print(f"[project_manager] max_iterations: {agent.soul.max_iterations}")
    print(f"[project_manager] shared_knowledge length: {len(agent.shared_knowledge)} chars")

    t0 = time.perf_counter()
    result = await agent.run(
        input_data=(
            "审核已完成。审核通过率 0.75（3/4 通过）。\n"
            "内容行：\n"
            "1. 小红书种草笔记「花瓣唇釉测评」— 审核通过\n"
            "2. 抖音口播脚本「唇釉试色 vlog」— 审核通过\n"
            "3. 公众号长文「成分解析」— 审核通过\n"
            "4. 微博话题「限定色号投票」— 审核驳回（缺少合规声明）"
        ),
        strategy={"deliverable": "交付摘要"},
        context={"record_id": "rec_live_pm", "project_name": "花知晓双十一"},
    )
    elapsed = time.perf_counter() - t0
    _print_result("项目经理", result, elapsed)

    assert result.role_id == "project_manager"
    assert len(result.output) > 50, "PM 输出过短"
    assert result.missing_required_tools == []


@pytest.mark.asyncio
async def test_data_analyst_live():
    """数据分析师 live 验收：请求生成周报，验证能产出分析报告。"""
    from agents.base import BaseAgent

    agent = BaseAgent(
        role_id="data_analyst",
        record_id="rec_live_data",
        task_filter={"report_type": "weekly"},
    )

    print(f"\n[data_analyst] soul tools: {agent.soul.tools}")
    print(f"[data_analyst] max_iterations: {agent.soul.max_iterations}")
    print(f"[data_analyst] shared_knowledge length: {len(agent.shared_knowledge)} chars")

    t0 = time.perf_counter()
    result = await agent.run(
        input_data="请生成本周运营周报。",
        strategy={"report_type": "weekly", "audience": "团队全员"},
        context={"record_id": "rec_live_data", "project_name": "运营中台"},
    )
    elapsed = time.perf_counter() - t0
    _print_result("数据分析师", result, elapsed)

    assert result.role_id == "data_analyst"
    assert len(result.output) > 30, "数据分析师输出过短"
    assert result.missing_required_tools == []
