"""独立测试三个 Agent（策略师/项目经理/数据分析师）— 使用真实 LLM API + Mock 工具。

用法:
    python scripts/test_agents_standalone.py
    python scripts/test_agents_standalone.py --agent strategist
    python scripts/test_agents_standalone.py --agent project_manager
    python scripts/test_agents_standalone.py --agent data_analyst
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── 1. 强制设置环境变量（必须在 import config 之前）──
os.environ["LLM_API_KEY"] = "sk-9iB05TNrJD2CpKcWf"
os.environ["LLM_BASE_URL"] = "https://api.luhengcheng.top/v1"
os.environ["LLM_MODEL"] = "gpt-5.4-mini"
# 禁用飞书相关功能，避免连接错误
os.environ.setdefault("FEISHU_APP_ID", "")
os.environ.setdefault("FEISHU_APP_SECRET", "")
os.environ.setdefault("FEISHU_CHAT_ID", "")
os.environ.setdefault("WIKI_DOWNLOAD_ENABLED", "false")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import AsyncOpenAI
from tools import AgentContext

# ── 2. 日志配置 ──
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = LOG_DIR / f"agent_test_{timestamp}.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-7s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)
logger = logging.getLogger("test_agents")


# ── 3. Mock ToolRegistry ──

# 模拟数据：策略师读取的项目上下文
_MOCK_PROJECT = {
    "client_name": "某护肤品牌",
    "project_type": "电商大促",
    "brand_tone": "科技感、专业、可信赖，避免廉价促销腔",
    "dept_style": "每条内容必须带明确卖点、适用人群和行动号召，优先强调成分与功效证据",
    "status": "策略中",
    "brief_analysis": (
        "## Brief 解读报告\n\n"
        "### 核心信息提取\n"
        "- 客户: 某护肤品牌\n"
        "- 核心产品: 玻尿酸精华液\n"
        "- 预算: 5万\n"
        "- 目标人群: 25-35岁女性\n"
        "- 平台需求: 公众号长文、小红书种草、抖音短视频脚本\n"
        "- 核心卖点: 成分科技感、补水修护效果、大促转化效率\n\n"
        "### 风险提示\n"
        "- 预算5万属于中等，需合理控制内容数量\n"
        "- 双十一竞争激烈，需差异化内容策略"
    ),
    "strategy": "",
    "review_summary": (
        "## 审核总评\n\n"
        "共审核 4 条内容，通过 3 条，需修改 1 条。\n"
        "整体质量良好，合规性达标。\n\n"
        "### 各维度评分\n"
        "- 事实准确: 4/5\n"
        "- 合规表达: 5/5\n"
        "- 品牌一致: 4/5\n"
        "- 平台适配: 4/5\n"
        "- 受众匹配: 4/5"
    ),
    "review_pass_rate": 0.75,
    "delivery": "",
    "knowledge_ref": "",
}

# 模拟数据：项目经理/数据分析师需要的内容行
_today = datetime.now()
_MOCK_CONTENT_ROWS = [
    {
        "record_id": "recMOCK001",
        "seq": 1,
        "title": "玻尿酸精华液「科技补水」深度测评",
        "platform": "公众号",
        "content_type": "深度长文",
        "key_point": "玻尿酸三重分子量渗透技术",
        "target_audience": "25-30岁成分党女性",
        "draft": "（2000字成稿内容...）",
        "word_count": 2000,
        "review_status": "通过",
        "review_feedback": "事实准确，表达合规，符合品牌调性",
        "publish_date": "",
        "remark": "",
    },
    {
        "record_id": "recMOCK002",
        "seq": 2,
        "title": "双十一囤货指南｜这瓶精华液凭什么值得入",
        "platform": "小红书",
        "content_type": "种草笔记",
        "key_point": "性价比+补水修护效果对比",
        "target_audience": "25-35岁关注大促的女性",
        "draft": "（800字种草笔记...）",
        "word_count": 800,
        "review_status": "通过",
        "review_feedback": "种草感强，CTA清晰",
        "publish_date": "",
        "remark": "",
    },
    {
        "record_id": "recMOCK003",
        "seq": 3,
        "title": "30秒看懂玻尿酸精华液的正确用法",
        "platform": "抖音脚本",
        "content_type": "口播脚本",
        "key_point": "使用方法+即时补水效果可视化",
        "target_audience": "25-35岁短视频重度用户",
        "draft": "（300字口播脚本...）",
        "word_count": 300,
        "review_status": "通过",
        "review_feedback": "节奏感好，卖点突出",
        "publish_date": "",
        "remark": "",
    },
    {
        "record_id": "recMOCK004",
        "seq": 4,
        "title": "敏感肌急救｜医生推荐的玻尿酸精华",
        "platform": "小红书",
        "content_type": "种草笔记",
        "key_point": "敏感肌适用+舒缓修护",
        "target_audience": "敏感肌女性用户",
        "draft": "（600字种草笔记...）",
        "word_count": 600,
        "review_status": "需修改",
        "review_feedback": "标题暗示医疗推荐，需修改为非医疗表述",
        "publish_date": "",
        "remark": "",
    },
]

# 模拟数据：数据分析师的跨项目统计
_MOCK_STATS = {
    "projects": {
        "total": 8,
        "completion_rate": 0.5,
        "by_status": {
            "已完成": 4, "审核中": 1, "撰写中": 1,
            "策略中": 1, "待处理": 1,
        },
        "by_type": {
            "电商大促": 3, "新品发布": 2, "品牌传播": 2, "日常运营": 1,
        },
        "avg_review_pass_rate": 0.72,
        "avg_review_pass_rate_by_type": {
            "电商大促": 0.65, "新品发布": 0.78,
            "品牌传播": 0.80, "日常运营": 0.70,
        },
        "red_flag_count": 1,
        "details": [
            {"record_id": "rec001", "client_name": "某护肤品牌", "project_type": "电商大促", "status": "已完成", "review_pass_rate": 0.75, "has_red_flag": False},
            {"record_id": "rec002", "client_name": "某母婴品牌", "project_type": "新品发布", "status": "已完成", "review_pass_rate": 0.80, "has_red_flag": False},
            {"record_id": "rec003", "client_name": "某运动品牌", "project_type": "品牌传播", "status": "已完成", "review_pass_rate": 0.85, "has_red_flag": False},
            {"record_id": "rec004", "client_name": "某饮料品牌", "project_type": "电商大促", "status": "已完成", "review_pass_rate": 0.60, "has_red_flag": False},
            {"record_id": "rec005", "client_name": "某美妆品牌", "project_type": "电商大促", "status": "审核中", "review_pass_rate": 0.55, "has_red_flag": True},
            {"record_id": "rec006", "client_name": "某家电品牌", "project_type": "新品发布", "status": "撰写中", "review_pass_rate": 0, "has_red_flag": False},
            {"record_id": "rec007", "client_name": "某食品品牌", "project_type": "品牌传播", "status": "策略中", "review_pass_rate": 0, "has_red_flag": False},
            {"record_id": "rec008", "client_name": "某服装品牌", "project_type": "日常运营", "status": "待处理", "review_pass_rate": 0, "has_red_flag": False},
        ],
    },
    "content": {
        "total": 28,
        "has_draft_count": 18,
        "draft_rate": 0.643,
        "by_platform": {"小红书": 12, "公众号": 8, "抖音脚本": 5, "微博": 3},
        "by_content_type": {"种草笔记": 10, "深度长文": 8, "口播脚本": 5, "话题文案": 3, "图文卡片": 2},
        "by_review_status": {"通过": 14, "需修改": 3, "未审核": 11},
        "platform_review_detail": {
            "小红书": {"通过": 7, "需修改": 2, "未审核": 3},
            "公众号": {"通过": 5, "需修改": 1, "未审核": 2},
            "抖音脚本": {"通过": 2, "未审核": 3},
            "微博": {"未审核": 3},
        },
        "word_count_stats": {
            "total_words": 22000, "avg_words": 1222,
            "min_words": 200, "max_words": 3500, "count_with_wordcount": 18,
        },
    },
    "experience": {
        "total": 15,
        "by_role": {"account_manager": 4, "copywriter": 5, "reviewer": 3, "strategist": 2, "project_manager": 1},
        "by_scene": {"电商大促": 6, "新品发布": 4, "品牌传播": 3, "日常运营": 2},
        "confidence_stats": {"avg": 0.73, "min": 0.55, "max": 0.92},
    },
}


class MockToolRegistry:
    """返回预设 mock 数据的工具注册表，用于隔离飞书依赖。"""

    def __init__(self):
        self._real_registry = None
        self._call_log: list[dict] = []

    def _get_real_registry(self):
        if self._real_registry is None:
            from tools import ToolRegistry
            self._real_registry = ToolRegistry()
        return self._real_registry

    def get_tools(self, tool_names: list[str]) -> list[dict]:
        return self._get_real_registry().get_tools(tool_names)

    async def call_tool(self, tool_name: str, params: dict, context: AgentContext) -> str:
        """拦截工具调用，返回 mock 数据。"""
        self._call_log.append({
            "tool": tool_name,
            "params": params,
            "time": datetime.now().isoformat(),
        })
        logger.info("🔧 [MOCK] %s(%s)", tool_name, json.dumps(params, ensure_ascii=False)[:200])

        result = self._dispatch(tool_name, params, context)
        logger.info("🔧 [MOCK] %s → %s", tool_name, str(result)[:300])
        return result

    def _dispatch(self, name: str, params: dict, ctx: AgentContext) -> str:
        handlers = {
            "read_project": self._read_project,
            "write_project": self._write_project,
            "update_status": self._update_status,
            "create_content": self._create_content,
            "batch_create_content": self._batch_create_content,
            "list_content": self._list_content,
            "write_content": self._write_content,
            "search_knowledge": self._search_knowledge,
            "read_knowledge": self._read_knowledge,
            "search_web": self._search_web,
            "web_fetch": self._web_fetch,
            "get_experience": self._get_experience,
            "write_wiki": self._write_wiki,
            "send_message": self._send_message,
            "query_project_stats": self._query_project_stats,
            "send_report": self._send_report,
            "generate_report_doc": self._generate_report_doc,
            "read_template": self._read_template,
            "negotiate": self._negotiate,
        }
        handler = handlers.get(name)
        if handler:
            return handler(params, ctx)
        return f"[MOCK] 工具 {name} 无 mock 实现，返回空结果"

    # ── 各工具 mock 实现 ──

    def _read_project(self, params: dict, ctx: AgentContext) -> str:
        fields = params.get("fields", [])
        result = {}
        for f in fields:
            alias = {"brief_content": "brief_analysis", "delivery_summary": "delivery"}.get(f, f)
            result[f] = _MOCK_PROJECT.get(alias, _MOCK_PROJECT.get(f, f"未知字段: {f}"))
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _write_project(self, params: dict, ctx: AgentContext) -> str:
        for k, v in params.items():
            if k in _MOCK_PROJECT:
                _MOCK_PROJECT[k] = v
        logger.info("📝 [MOCK write_project] 字段已更新: %s", list(params.keys()))
        return "写入成功"

    def _update_status(self, params: dict, ctx: AgentContext) -> str:
        new_status = params.get("status", "")
        logger.info("📝 [MOCK update_status] %s → %s", _MOCK_PROJECT["status"], new_status)
        _MOCK_PROJECT["status"] = new_status
        return f"状态已更新为: {new_status}"

    def _create_content(self, params: dict, ctx: AgentContext) -> str:
        return json.dumps({"record_id": f"recNEW{len(_MOCK_CONTENT_ROWS)+1:03d}", "status": "created"}, ensure_ascii=False)

    def _batch_create_content(self, params: dict, ctx: AgentContext) -> str:
        items = params.get("items", [])
        results = [{"seq": i+1, "record_id": f"recNEW{i+1:03d}", "status": "created"} for i in range(len(items))]
        logger.info("📝 [MOCK batch_create_content] 创建 %d 条内容行", len(items))
        return json.dumps({"created": len(items), "results": results}, ensure_ascii=False)

    def _list_content(self, params: dict, ctx: AgentContext) -> str:
        platform = (params.get("platform") or "").strip().lower()
        rows = _MOCK_CONTENT_ROWS
        if platform:
            rows = [r for r in rows if r["platform"].lower() == platform]
        return json.dumps(rows, ensure_ascii=False, indent=2)

    def _write_content(self, params: dict, ctx: AgentContext) -> str:
        record_id = params.get("record_id", "")
        logger.info("📝 [MOCK write_content] %s: %s", record_id, {k: v for k, v in params.items() if k != "record_id"})
        return f"内容行 {record_id} 更新成功"

    def _search_knowledge(self, params: dict, ctx: AgentContext) -> str:
        query = params.get("query", "")
        return json.dumps([
            {"path": "02_服务方法论/Brief 解读规则.md", "score": 0.85, "snippet": "Brief 解读需关注核心卖点、目标人群、预算匹配度..."},
            {"path": "04_平台打法/小红书内容打法.md", "score": 0.80, "snippet": "小红书种草笔记需突出真实体验感，避免硬广痕迹..."},
            {"path": "02_服务方法论/人审规则与超时策略.md", "score": 0.72, "snippet": "审核通过率低于60%时建议返工..."},
        ], ensure_ascii=False, indent=2)

    def _read_knowledge(self, params: dict, ctx: AgentContext) -> str:
        return (
            "# 小红书内容打法\n\n"
            "## 核心策略\n"
            "1. 标题必须含有效关键词，命中用户搜索意图\n"
            "2. 首图决定点击率，建议使用对比图/使用前后对比\n"
            "3. 正文采用 pain-agitate-solve 结构\n"
            "4. 避免直接出现价格信息\n"
            "5. CTA 引导收藏 > 点赞 > 评论"
        )

    def _search_web(self, params: dict, ctx: AgentContext) -> str:
        query = params.get("query", "")
        return json.dumps({
            "results": [
                {"title": "2024双十一护肤品营销趋势报告", "url": "https://example.com/report1", "snippet": "今年双十一护肤品赛道竞争加剧，成分党内容占比提升至45%..."},
                {"title": "玻尿酸精华液品类竞争分析", "url": "https://example.com/report2", "snippet": "头部品牌通过小红书KOC种草+抖音短视频组合拳，转化率提升30%..."},
                {"title": "小红书护肤赛道爆文拆解", "url": "https://example.com/report3", "snippet": "高赞笔记共性：真实感体验+成分科普+使用前后对比..."},
            ]
        }, ensure_ascii=False, indent=2)

    def _web_fetch(self, params: dict, ctx: AgentContext) -> str:
        return (
            "# 2024双十一护肤品营销趋势报告\n\n"
            "## 市场趋势\n"
            "- 成分党内容占比从去年的32%提升至45%\n"
            "- 短视频种草转化路径：内容曝光 → 搜索 → 比价 → 下单\n"
            "- 玻尿酸品类搜索量同比增长28%\n\n"
            "## 竞品动态\n"
            "- A品牌：小红书为主阵地，KOC矩阵 + 成分科普长文\n"
            "- B品牌：抖音短视频 + 达人测评，侧重即时效果可视化\n"
            "- C品牌：公众号深度长文 + 社群私域转化\n\n"
            "## 策略建议\n"
            "- 小红书：成分科普 + 使用教程 + 大促囤货指南\n"
            "- 抖音：30秒效果可视化 + 价格机制解读\n"
            "- 公众号：深度测评 + 成分背书 + 品牌故事"
        )

    def _get_experience(self, params: dict, ctx: AgentContext) -> str:
        return json.dumps([
            {"category": "电商大促", "lesson": "双十一护肤品内容需提前2周预热，小红书种草→抖音引爆→公众号收割的节奏最有效", "confidence": 0.85},
            {"category": "电商大促", "lesson": "成分科普类内容审核通过率最高(85%)，促销导向内容通过率最低(55%)", "confidence": 0.78},
        ], ensure_ascii=False, indent=2)

    def _write_wiki(self, params: dict, ctx: AgentContext) -> str:
        logger.info("📝 [MOCK write_wiki] 分类=%s 标题=%s", params.get("category"), params.get("title"))
        return "wiki 写入成功"

    def _send_message(self, params: dict, ctx: AgentContext) -> str:
        msg = params.get("message", "")
        logger.info("💬 [MOCK send_message] %s", msg[:200])
        return f"消息已记录（测试模式）: {msg[:80]}..."

    def _query_project_stats(self, params: dict, ctx: AgentContext) -> str:
        scope = params.get("scope", "all")
        if scope == "all":
            return json.dumps(_MOCK_STATS, ensure_ascii=False, indent=2)
        if scope in _MOCK_STATS:
            return json.dumps({scope: _MOCK_STATS[scope]}, ensure_ascii=False, indent=2)
        return json.dumps(_MOCK_STATS, ensure_ascii=False, indent=2)

    def _send_report(self, params: dict, ctx: AgentContext) -> str:
        logger.info("📊 [MOCK send_report] 类型=%s", params.get("report_type", "weekly"))
        return "报告已推送到飞书群聊（测试模式）"

    def _generate_report_doc(self, params: dict, ctx: AgentContext) -> str:
        logger.info("📊 [MOCK generate_report_doc] 标题=%s", params.get("title", ""))
        return json.dumps({
            "doc_url": "https://example.feishu.cn/docx/mock_report_doc",
            "status": "created",
        }, ensure_ascii=False)

    def _read_template(self, params: dict, ctx: AgentContext) -> str:
        return "（模板内容 — 测试环境无实际模板）"

    def _negotiate(self, params: dict, ctx: AgentContext) -> str:
        return json.dumps({"result": "accepted", "note": "模拟协商通过"}, ensure_ascii=False)


# ── 4. 各 Agent 测试输入 ──

STRATEGIST_INPUT = (
    "项目背景：\n"
    "客户「某护肤品牌」的双十一电商大促项目。\n"
    "核心产品：玻尿酸精华液\n"
    "预算：5万\n"
    "目标人群：25-35岁女性\n"
    "平台需求：公众号长文、小红书种草、抖音短视频脚本\n"
    "核心卖点：成分科技感、补水修护效果、大促转化效率\n"
    "品牌调性：科技感、专业、可信赖，避免廉价促销腔\n\n"
    "Brief 解读已完成，请基于以上信息制定内容策略方案并创建内容排期行。"
)

PROJECT_MANAGER_INPUT = (
    "项目背景：\n"
    "客户「某护肤品牌」的双十一电商大促项目已完成内容撰写和审核。\n"
    "审核总评：共审核 4 条内容，通过 3 条，需修改 1 条，整体通过率 75%。\n"
    "当前状态：排期中\n\n"
    "请读取项目和内容信息，为审核通过的内容安排发布日期，生成交付摘要，并推动项目完成。"
)

DATA_ANALYST_INPUT = (
    "请生成一份运营周报（report_type=weekly），覆盖所有项目的运营数据。\n"
    "需要包含：项目运营概览、内容质量分析、内容产出效率、经验沉淀健康度、趋势洞察与决策建议。"
)


# ── 5. 测试运行函数 ──

async def test_agent(role_id: str, input_data: str, strategy: dict, context: dict) -> dict:
    """运行单个 Agent 测试，返回结果摘要。"""
    from agents.base import BaseAgent

    logger.info("=" * 80)
    logger.info("🚀 开始测试 Agent: %s", role_id)
    logger.info("=" * 80)

    mock_registry = MockToolRegistry()

    # 代理服务器拦截 OpenAI SDK 的 x-stainless-* 追踪头，需覆盖为空
    llm_client = AsyncOpenAI(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        timeout=180,
        max_retries=2,
        default_headers={
            "User-Agent": "python-httpx",
            "x-stainless-os": "",
            "x-stainless-arch": "",
            "x-stainless-lang": "",
            "x-stainless-package-version": "",
            "x-stainless-runtime": "",
            "x-stainless-runtime-version": "",
            "x-stainless-retry-count": "",
        },
    )

    agent = BaseAgent(
        role_id=role_id,
        record_id="recTEST001",
        tool_registry=mock_registry,
        llm_client=llm_client,
        shared_knowledge="（测试模式：共享知识已省略）",
    )

    logger.info("Agent 配置: name=%s, tools=%s, max_iterations=%d",
                agent.soul.name, agent.soul.tools, agent.soul.max_iterations)

    t0 = time.perf_counter()
    try:
        result = await agent.run_unit(
            input_data=input_data,
            strategy=strategy,
            context=context,
        )
        elapsed = time.perf_counter() - t0

        logger.info("-" * 60)
        logger.info("✅ %s 执行完成 (%.1fs)", role_id, elapsed)
        logger.info("输出长度: %d 字符", len(result.output))
        logger.info("工具调用次数: %d", len(result.tool_calls))
        logger.info("缺失必调工具: %s", result.missing_required_tools or "无")
        logger.info("消息轮次: %d", len(result.messages))

        # 打印工具调用明细
        if result.tool_calls:
            logger.info("\n--- 工具调用明细 ---")
            for i, tc in enumerate(result.tool_calls, 1):
                logger.info(
                    "  [%d] %s(%s) → %s",
                    i, tc["tool_name"],
                    json.dumps(tc["arguments"], ensure_ascii=False)[:100],
                    str(tc["result"])[:200],
                )

        # 打印最终输出
        logger.info("\n--- 最终输出 ---")
        logger.info(result.output)
        logger.info("-" * 60)

        # 保存详细结果到文件
        detail_file = LOG_DIR / f"agent_test_{timestamp}_{role_id}.json"
        detail = {
            "role_id": role_id,
            "elapsed_seconds": round(elapsed, 2),
            "output": result.output,
            "tool_calls": result.tool_calls,
            "missing_required_tools": result.missing_required_tools,
            "meta": result.meta,
            "mock_call_log": mock_registry._call_log,
            "message_count": len(result.messages),
        }
        detail_file.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("详细结果已保存: %s", detail_file)

        return {
            "role_id": role_id,
            "status": "OK",
            "elapsed": round(elapsed, 2),
            "output_length": len(result.output),
            "tool_calls": len(result.tool_calls),
            "missing_tools": result.missing_required_tools,
        }

    except Exception as e:
        elapsed = time.perf_counter() - t0
        logger.error("❌ %s 执行失败 (%.1fs): %s", role_id, elapsed, e, exc_info=True)
        return {
            "role_id": role_id,
            "status": "FAIL",
            "elapsed": round(elapsed, 2),
            "error": str(e),
        }


async def main():
    parser = argparse.ArgumentParser(description="独立测试 Agent（策略师/项目经理/数据分析师）")
    parser.add_argument("--agent", choices=["strategist", "project_manager", "data_analyst"],
                       help="只测试指定 Agent，不传则测全部")
    args = parser.parse_args()

    logger.info("🏁 Agent 独立测试开始")
    logger.info("LLM: model=%s base_url=%s", os.environ["LLM_MODEL"], os.environ["LLM_BASE_URL"])
    logger.info("日志文件: %s", log_file)

    test_cases = {
        "strategist": {
            "input": STRATEGIST_INPUT,
            "strategy": {},
            "context": {
                "record_id": "recTEST001",
                "client_name": "某护肤品牌",
                "project_type": "电商大促",
            },
        },
        "project_manager": {
            "input": PROJECT_MANAGER_INPUT,
            "strategy": {},
            "context": {
                "record_id": "recTEST001",
                "client_name": "某护肤品牌",
                "project_type": "电商大促",
            },
        },
        "data_analyst": {
            "input": DATA_ANALYST_INPUT,
            "strategy": {},
            "context": {
                "record_id": "recTEST001",
                "project_name": "跨项目数据分析",
            },
        },
    }

    if args.agent:
        agents_to_test = [args.agent]
    else:
        agents_to_test = ["strategist", "project_manager", "data_analyst"]

    results = []
    for role_id in agents_to_test:
        tc = test_cases[role_id]
        r = await test_agent(role_id, tc["input"], tc["strategy"], tc["context"])
        results.append(r)

    # 汇总
    logger.info("\n" + "=" * 80)
    logger.info("📋 测试汇总")
    logger.info("=" * 80)
    for r in results:
        status_icon = "✅" if r["status"] == "OK" else "❌"
        logger.info(
            "%s %s: %s | 耗时 %.1fs | 输出 %s字符 | 工具调用 %s次",
            status_icon,
            r["role_id"],
            r["status"],
            r["elapsed"],
            r.get("output_length", "-"),
            r.get("tool_calls", "-"),
        )
        if r.get("missing_tools"):
            logger.info("   ⚠️ 缺失必调工具: %s", r["missing_tools"])
        if r.get("error"):
            logger.info("   ❌ 错误: %s", r["error"])
    logger.info("=" * 80)
    logger.info("日志文件: %s", log_file)


if __name__ == "__main__":
    asyncio.run(main())
