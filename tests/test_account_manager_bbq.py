"""客户经理 (account_manager) 端到端单测 — 烧烤店 brief 场景。

使用方法:
    python tests/test_account_manager_bbq.py

底层逻辑:
    - 真实 LLM + 真实 Bitable，建一条测试 record，跑 BaseAgent("account_manager")，
      校验 7 项硬指标（状态推进 / 字段长度 / 10 节结构 / 三类工具调用 / 缺失信息识别 /
      行业风险命中）。
    - 客户名称带 [TEST-yyyymmdd-HHMMSS] 前缀，便于事后批量识别和清理；record 跑完保留。
    - brief 写死，不参数化；想换场景请 fork 一份。

前置条件:
    1. .env 中已配置 LLM_API_KEY、FEISHU_APP_ID/SECRET、TAVILY_API_KEY
    2. Bitable 项目主表字段映射与 config.FIELD_MAP_PROJECT 一致
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 注：Windows asyncio loop policy 修复已统一拉到 _runtime.py，由 config.py 顶部
# 触发，所有入口共享，本脚本无需重复处理。


# ── brief 场景常量（写死） ───────────────────────────────────────────────

CLIENT_NAME_RAW = "鲜烤记本地烧烤"
BRIEF_TEXT = (
    "客户为本地烧烤店（行业：本地生活 / 餐饮），核心差异化在于鲜货现烤而非市面"
    "常见的冷冻食材，且食材品类丰富。目标是提升店面到店客流。"
    "主力人群：25-40 岁本地居民，情侣，年轻人。"
)
PROJECT_TYPE = "日常运营"  # 贴近的现有枚举值（餐饮拓客在 config 里没单独类型）
BRAND_TONE = "街坊烟火气、真实可信、强调新鲜与品质"
DEPT_STYLE = "所有产出必须包含到店转化引导（地址、营业时间或预约入口）"


# ── 断言阈值 ──────────────────────────────────────────────────────────

MIN_BRIEF_ANALYSIS_CHARS = 800
EXPECTED_SECTIONS = [
    "### 1. 品牌调研",
    "### 2. 项目摘要",
    "### 3. 目标理解",
    "### 4. 受众与场景",
    "### 5. 关键约束",
    "### 6. 合规与风险提醒",
    "### 7. 已明确的信息",
    "### 8. 缺失信息",
    "### 9. 准入结论",
]
REQUIRED_TOOLS = ["search_web", "web_fetch", "search_knowledge"]
MISSING_INFO_KEYWORDS = ["预算", "时间", "平台", "节点", "档期"]
INDUSTRY_RISK_KEYWORDS = ["食品", "餐饮", "卫生", "合规", "广告法", "虚假宣传"]


# ── .env 加载 ────────────────────────────────────────────────────────

def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


# ── ReAct 日志 handler，抓工具调用顺序 ────────────────────────────────

class ReActLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.iterations = 0
        self.tools: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        if "调用工具" in message:
            self.iterations += 1
            tool_name = message.split("调用工具", 1)[-1].strip()
            tool_name = tool_name.split("(", 1)[0].strip()
            print(f"  [iter {self.iterations}] -> {tool_name}", flush=True)
            if tool_name and tool_name not in self.tools:
                self.tools.append(tool_name)
        elif "输出最终结果" in message or "循环结束" in message:
            print(f"  [done] {message}", flush=True)


async def _heartbeat(started_at: float, stop_evt: asyncio.Event, interval: float = 10.0) -> None:
    """每 interval 秒输出一次心跳，让人知道脚本没卡死。"""
    try:
        while not stop_evt.is_set():
            try:
                await asyncio.wait_for(stop_evt.wait(), timeout=interval)
            except asyncio.TimeoutError:
                elapsed = time.perf_counter() - started_at
                print(f"  [heartbeat] 已运行 {elapsed:.0f}s ...", flush=True)
    except asyncio.CancelledError:
        pass


# ── 断言收集器 ────────────────────────────────────────────────────────

class Assertions:
    def __init__(self) -> None:
        self.passed: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []

    def check(self, ok: bool, name: str, detail: str) -> None:
        if ok:
            self.passed.append((name, detail))
        else:
            self.failed.append((name, detail))

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed)

    @property
    def all_passed(self) -> bool:
        return not self.failed


# ── 主流程 ────────────────────────────────────────────────────────────

async def main() -> int:
    env_path = ROOT / ".env"
    file_values = load_env_file(env_path)
    llm_key = os.getenv("LLM_API_KEY") or file_values.get("LLM_API_KEY", "")
    feishu_app_id = os.getenv("FEISHU_APP_ID") or file_values.get("FEISHU_APP_ID", "")

    if not env_path.exists() or not llm_key or not feishu_app_id:
        print("✗ 跳过：缺少 .env 配置（需 LLM_API_KEY + FEISHU_APP_ID）")
        return 0

    from agents.base import BaseAgent
    from config import FIELD_MAP_PROJECT as FP, PROJECT_TABLE_ID
    from feishu.bitable import BitableClient
    from memory.project import ProjectMemory

    test_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    test_client_name = f"[TEST-{test_tag}] {CLIENT_NAME_RAW}"

    payload = {
        FP["client_name"]: test_client_name,
        FP["brief"]: BRIEF_TEXT,
        FP["project_type"]: PROJECT_TYPE,
        FP["brand_tone"]: BRAND_TONE,
        FP["dept_style"]: DEPT_STYLE,
        FP["status"]: "待处理",
    }

    print("=" * 60)
    print("客户经理 单测 — 烧烤店场景")
    print("=" * 60)
    print(f"客户名称: {test_client_name}")
    print(f"项目类型: {PROJECT_TYPE}")
    print(f"Brief: {BRIEF_TEXT}")
    print(f"品牌调性: {BRAND_TONE}")
    print(f"部门风格: {DEPT_STYLE}")
    print("-" * 60)

    started_at = time.perf_counter()

    client = BitableClient()
    record_id = await client.create_record(PROJECT_TABLE_ID, payload)
    print(f"✓ 测试记录已创建: {record_id}")
    print(f"  (前缀 [TEST-{test_tag}] 便于事后批量清理)")
    print("-" * 60)
    print("开始跑 ReAct 循环（预计 60–180 秒）...")

    # ReAct 工具调用计数 handler（保留原行为，提取工具序列）
    handler = ReActLogHandler()
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))

    # 同时把 agents.base 的 INFO 日志打到 stdout，避免"屏幕一片空白"
    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(logging.INFO)
    stream.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))

    agent_logger = logging.getLogger("agents.base")
    old_level = agent_logger.level
    agent_logger.setLevel(logging.INFO)
    agent_logger.addHandler(handler)
    agent_logger.addHandler(stream)

    # 心跳协程，每 10s 打一次时间，让人知道在跑
    stop_evt = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat(started_at, stop_evt, interval=10.0))

    final_output = ""
    error: Exception | None = None

    try:
        agent = BaseAgent(role_id="account_manager", record_id=record_id)
        final_output = await agent.run()
    except Exception as exc:
        error = exc
    finally:
        stop_evt.set()
        try:
            await heartbeat_task
        except Exception:
            pass
        agent_logger.removeHandler(handler)
        agent_logger.removeHandler(stream)
        agent_logger.setLevel(old_level)

    elapsed = time.perf_counter() - started_at

    if error is not None:
        print(f"\n✗ Agent 运行抛错: {type(error).__name__}: {error}")
        print(f"  测试记录 {record_id} 已保留")
        return 1

    print(f"\n✓ Agent 跑完，{handler.iterations} 轮 ReAct，耗时 {elapsed:.1f} 秒")
    print(f"  最终输出预览（前 200 字）: {(final_output or '(空)')[:200]}")
    print("-" * 60)

    # ── 拉取产出做断言 ──
    pm = ProjectMemory(record_id)
    proj = await pm.load()
    brief_analysis = proj.brief_analysis or ""
    status_value = proj.status or ""

    a = Assertions()

    # 1. 状态推进到"解读中"
    a.check(
        status_value == "解读中",
        "状态推进",
        f'期望"解读中"，实际"{status_value}"',
    )

    # 2. Brief 解读字段长度 ≥ 阈值
    a.check(
        len(brief_analysis) >= MIN_BRIEF_ANALYSIS_CHARS,
        "Brief 解读字段长度",
        f"{len(brief_analysis)} 字，阈值 {MIN_BRIEF_ANALYSIS_CHARS}",
    )

    # 3. 10 节结构（第 1~9 节，第 10 节是修订说明，首轮可空，不强校验）
    missing_sections = [s for s in EXPECTED_SECTIONS if s not in brief_analysis]
    a.check(
        not missing_sections,
        "Brief 解读 9 节结构完整",
        "全部命中" if not missing_sections else f"缺: {missing_sections}",
    )

    # 4–6. 工具调用：search_web / web_fetch / search_knowledge
    for tool in REQUIRED_TOOLS:
        a.check(
            tool in handler.tools,
            f"工具调用 {tool}",
            "已调用" if tool in handler.tools else f"未调用，实际工具列表 {handler.tools}",
        )

    # 7. 缺失信息识别（第 8 节内应命中至少一个关键字）
    section8 = _extract_section(brief_analysis, "### 8. 缺失信息", "### 9.")
    hit_missing = [k for k in MISSING_INFO_KEYWORDS if k in section8]
    a.check(
        bool(hit_missing),
        "缺失信息识别",
        f"命中关键字 {hit_missing}" if hit_missing
        else f"未命中任何 {MISSING_INFO_KEYWORDS}，第 8 节内容: {section8[:200]}",
    )

    # 8. 行业风险命中（第 6 节内应命中至少一个餐饮/食品类关键字）
    section6 = _extract_section(brief_analysis, "### 6. 合规与风险提醒", "### 7.")
    hit_risk = [k for k in INDUSTRY_RISK_KEYWORDS if k in section6]
    a.check(
        bool(hit_risk),
        "行业风险命中（餐饮/食品类）",
        f"命中关键字 {hit_risk}" if hit_risk
        else f"未命中任何 {INDUSTRY_RISK_KEYWORDS}，第 6 节内容: {section6[:200]}",
    )

    # ── 报告 ──
    print("\n" + "=" * 60)
    print(f"断言报告: {len(a.passed)}/{a.total} 通过")
    print("=" * 60)
    if a.passed:
        print("\n通过:")
        for name, detail in a.passed:
            print(f"  ✓ {name}  — {detail}")
    if a.failed:
        print("\n失败:")
        for name, detail in a.failed:
            print(f"  ✗ {name}  — {detail}")

    print("\n" + "-" * 60)
    print(f"ReAct 循环轮次: {handler.iterations}")
    print(f"调用工具列表: {', '.join(handler.tools) if handler.tools else '(无)'}")
    print(f"Brief 解读字段长度: {len(brief_analysis)} 字")
    print(f"状态: {status_value}")
    print(f"耗时: {elapsed:.1f} 秒")
    print(f"测试记录 ID: {record_id}（前缀 [TEST-{test_tag}] 已保留，可批量清理）")
    print("=" * 60)

    return 0 if a.all_passed else 1


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    """提取两个 section 标题之间的内容，end_marker 用前缀匹配避免标题数字漂移。"""
    start = text.find(start_marker)
    if start < 0:
        return ""
    tail = text[start + len(start_marker):]
    # end_marker 可能是 "### 9." 这种前缀，找最近的下一个匹配
    m = re.search(r"\n###\s+\d+\.", tail)
    if m:
        return tail[: m.start()]
    return tail


def _run() -> int:
    """包一层入口，捕获 KeyboardInterrupt，避免 loop close 时再次卡死。"""
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[abort] 用户中断，正在退出...", flush=True)
        return 130  # 标准 SIGINT 退出码


if __name__ == "__main__":
    raise SystemExit(_run())
