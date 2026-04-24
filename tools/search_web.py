"""工具: 通过 Tavily API 搜索互联网，用于策略师获取行业动态/竞品策略/营销趋势。

定位边界：
- 搜的是【互联网】行业报告、竞品新闻、营销趋势 — 不是单条爆款帖（那走 search_reference）
- 搜的是【外部】实时信息 — 不是本地沉淀知识（那走 search_knowledge）
- 只返回 URL 列表 + AI 摘要 — 要读全文请继续调 web_fetch
"""

from __future__ import annotations

import json
import logging

import httpx

from config import (
    TAVILY_API_KEY,
    TAVILY_API_URL,
    TAVILY_DEFAULT_MAX_RESULTS,
    TAVILY_TIMEOUT_SECONDS,
)
from tools import AgentContext

logger = logging.getLogger(__name__)


SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "通过 Tavily 搜索互联网，获取行业动态、竞品策略、营销趋势等实时信息，"
            "用于辅助策略制定。返回 AI 合成摘要 + URL 列表 + 每条片段。"
            "如果需要读某条 URL 的全文，请再调 web_fetch。"
            "不要用它搜本地知识（用 search_knowledge）；不要用它搜爆款帖（用 search_reference）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，建议 5-20 字，包含【行业/品类/时间/主题】，如 '2025 国货美妆 双十一 营销策略'",
                },
                "topic": {
                    "type": "string",
                    "enum": ["general", "news"],
                    "default": "general",
                    "description": "general=综合报告/分析；news=近期新闻/竞品动态",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "description": "时效性过滤，可选。查竞品新品动态建议 week，查营销趋势建议 month/year",
                },
                "max_results": {
                    "type": "integer",
                    "default": TAVILY_DEFAULT_MAX_RESULTS,
                    "minimum": 1,
                    "maximum": 10,
                    "description": f"返回结果数，默认 {TAVILY_DEFAULT_MAX_RESULTS}",
                },
            },
            "required": ["query"],
        },
    },
}


async def execute(params: dict, context: AgentContext) -> str:
    query = (params.get("query") or "").strip()
    if not query:
        return "错误: query 不能为空"

    if not TAVILY_API_KEY:
        return "错误: 未配置 TAVILY_API_KEY，无法调用联网搜索。请在 .env 中配置。"

    topic = params.get("topic") or "general"
    time_range = params.get("time_range")
    max_results = int(params.get("max_results") or TAVILY_DEFAULT_MAX_RESULTS)
    max_results = max(1, min(10, max_results))

    payload: dict = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "topic": topic,
        "search_depth": "advanced",
        "include_answer": True,
        "include_raw_content": False,
        "max_results": max_results,
    }
    if time_range:
        payload["time_range"] = time_range

    # 加固：代理链路（尤其 Windows + Clash）在 TLS 握手偶发抽风，
    # Transport retries=2 专治 connect 层 ConnectError，不影响 HTTP 语义
    transport = httpx.AsyncHTTPTransport(retries=2)
    timeout = httpx.Timeout(
        connect=10.0,
        read=TAVILY_TIMEOUT_SECONDS,
        write=10.0,
        pool=5.0,
    )
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            http2=False,
        ) as client:
            resp = await client.post(TAVILY_API_URL, json=payload)
    except httpx.TimeoutException:
        return f"错误: Tavily 请求超时（>{TAVILY_TIMEOUT_SECONDS}s），query='{query}'"
    except Exception as e:
        logger.exception("Tavily 请求异常")
        return f"错误: Tavily 请求异常 {type(e).__name__}: {e}"

    if resp.status_code == 401:
        return "错误: Tavily API Key 无效或已过期"
    if resp.status_code == 429:
        return "错误: Tavily 额度耗尽或触发限流，请稍后重试"
    if resp.status_code >= 400:
        return f"错误: Tavily 返回 HTTP {resp.status_code}: {resp.text[:200]}"

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return f"错误: Tavily 返回内容无法解析为 JSON: {resp.text[:200]}"

    answer = (data.get("answer") or "").strip()
    results = data.get("results") or []

    if not results and not answer:
        return f"未找到与 '{query}' 相关的网页信息。"

    lines = [f"# 联网搜索结果: {query}\n"]
    if answer:
        lines.append("## AI 摘要\n")
        lines.append(answer)
        lines.append("")

    if results:
        lines.append("## 相关来源\n")
        for i, item in enumerate(results, 1):
            title = (item.get("title") or "").strip() or "(无标题)"
            url = item.get("url") or ""
            snippet = (item.get("content") or "").strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            lines.append(f"{i}. **{title}**")
            lines.append(f"   {url}")
            if snippet:
                lines.append(f"   > {snippet}")
            lines.append("")

    lines.append("如需查看某条 URL 全文，请调用 web_fetch。")
    return "\n".join(lines)
