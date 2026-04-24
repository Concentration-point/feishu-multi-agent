"""工具: 搜索真实博主的爆款内容，作为文案撰写的对标参考。

实现方案（方案 C 为主 + 方案 A 为可选降级）：
- 主路径：在 knowledge/references/ 下按平台 + 多关键词 grep 检索，
  解析每篇 frontmatter（platform/category/hook/structure/cta/engagement）
  返回结构化对标卡片，供文案直接模仿。
- 可选扩展：如果配置了 REFERENCE_SEARCH_API_KEY（SerpAPI），
  且本地命中不足，可动态补充网络检索结果。Demo 默认不启用。

设计考量：
- 不依赖外部网络，避免 Demo 现场翻车
- 返回格式对文案 Agent 友好：hook / structure / cta 明示可模仿点
- 复用 search_knowledge 的 grep 语义，Agent 学习成本低
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from tools import AgentContext
from config import KNOWLEDGE_BASE_PATH

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_reference",
        "description": (
            "搜索真实博主的爆款内容作为写作对标参考。"
            "返回结构化的参考卡片，包含开头抓手 hook、内容结构 structure、"
            "结尾 CTA 和互动数据 engagement，供文案直接借鉴模仿。"
            "建议在撰写每条内容前调用，明确「参考了哪些爆款的什么元素」。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，建议格式：品类+角度，如「精华液 种草」「扫地机 双十一」",
                },
                "platform": {
                    "type": "string",
                    "description": "目标平台筛选：小红书 / 抖音 / 公众号。不填则搜索全平台",
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回的最大参考数量，默认 5",
                },
            },
            "required": ["query"],
        },
    },
}

# 目录约定：knowledge/references/{platform}/*.md
_REFERENCES_SUBDIR = "references"


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析 Markdown 开头的 YAML frontmatter。

    Returns:
        (meta_dict, body_without_frontmatter)
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    raw = parts[1].strip()
    body = parts[2].strip()

    meta: dict[str, Any] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip()
        # 简单去引号
        if val.startswith(("\"", "'")) and val.endswith(("\"", "'")) and len(val) >= 2:
            val = val[1:-1]
        # list 语法 [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            items = val[1:-1].split(",")
            meta[key] = [i.strip().strip("\"'") for i in items if i.strip()]
        else:
            meta[key] = val
    return meta, body


def _extract_title(body: str, fallback: str) -> str:
    """从 body 中提取第一个 # 标题。"""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return fallback


def _extract_opening(body: str, max_chars: int = 220) -> str:
    """提取文章开头（跳过标题后的第一段实质内容）。"""
    lines = []
    seen_title = False
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and not seen_title:
            seen_title = True
            continue
        if stripped.startswith("#"):
            break
        lines.append(stripped)
        if sum(len(l) for l in lines) >= max_chars:
            break
    opening = " ".join(lines)
    if len(opening) > max_chars:
        opening = opening[:max_chars] + "…"
    return opening


def _score(meta: dict[str, Any], body: str, keywords: list[str]) -> int:
    """多关键词命中打分：meta 命中权重更高。"""
    if not keywords:
        return 0
    meta_blob = " ".join(
        str(v) if not isinstance(v, list) else " ".join(v)
        for v in meta.values()
    ).lower()
    body_lower = body.lower()
    score = 0
    for kw in keywords:
        lk = kw.lower()
        if not lk:
            continue
        if lk in meta_blob:
            score += 3
        if lk in body_lower:
            score += 1
    return score


def _parse_engagement_score(engagement: str) -> float:
    """从 engagement 字段（如 '1.2w赞 · 3800收藏'）提取首个数字用于排序。

    支持 'w' / '万' 单位（×10000）。解析失败返回 0.0。
    """
    import re
    if not engagement:
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(w|万|k)?", engagement)
    if not m:
        return 0.0
    try:
        val = float(m.group(1))
    except ValueError:
        return 0.0
    unit = (m.group(2) or "").lower()
    if unit in ("w", "万"):
        val *= 10000
    elif unit == "k":
        val *= 1000
    return val


def _iter_reference_cards(base: Path) -> list[dict[str, Any]]:
    """扫描 references/ 下所有 .md，返回标准化的参考卡片列表（不打分不过滤）。"""
    if not base.exists():
        return []
    cards: list[dict[str, Any]] = []
    for md in base.rglob("*.md"):
        if md.name.startswith(".") or md.name.lower() == "readme.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        meta, body = _parse_frontmatter(text)
        rel_path = md.relative_to(base.parent).as_posix()
        title = _extract_title(body, md.stem)
        cards.append({
            "path": rel_path,
            "title": title,
            "platform": meta.get("platform", ""),
            "category": meta.get("category", ""),
            "engagement": meta.get("engagement", ""),
            "engagement_score": _parse_engagement_score(meta.get("engagement", "")),
            "hook": meta.get("hook", ""),
            "structure": meta.get("structure", ""),
            "cta": meta.get("cta", ""),
            "tags": meta.get("tags", []),
            "opening": _extract_opening(body),
            "_meta": meta,
            "_body": body,
        })
    return cards


def _find_references(
    base: Path, keywords: list[str], platform: str | None, max_results: int
) -> list[dict[str, Any]]:
    """在 references 目录下按关键词打分搜索匹配的参考笔记。"""
    if not base.exists():
        return []

    results: list[dict[str, Any]] = []
    for card in _iter_reference_cards(base):
        # 平台过滤
        if platform:
            meta_platform = str(card.get("platform", "")).strip()
            if meta_platform and meta_platform != platform:
                continue
        score = _score(card["_meta"], card["_body"], keywords)
        if score == 0:
            continue
        card = {k: v for k, v in card.items() if not k.startswith("_")}
        card["score"] = score
        results.append(card)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:max_results]


def _fallback_by_platform(
    base: Path, platform: str | None, max_results: int
) -> list[dict[str, Any]]:
    """关键词 0 命中时的降级：按 platform 过滤（或全库），按 engagement 热度取 top-N。

    返回的卡片没有 score 字段，Agent 应当只把它当作「通用结构启发」而非精准对标。
    """
    cards = _iter_reference_cards(base)
    if platform:
        cards = [c for c in cards if str(c.get("platform", "")).strip() == platform]
    cards.sort(key=lambda r: r.get("engagement_score", 0.0), reverse=True)
    # 清掉内部字段
    cleaned = []
    for c in cards[:max_results]:
        cleaned.append({k: v for k, v in c.items() if not k.startswith("_")})
    return cleaned


def _library_inventory(base: Path) -> dict[str, list[str]]:
    """统计库内现有 platform → [categories] 组合，供 Agent 了解库的覆盖面。"""
    inventory: dict[str, set[str]] = {}
    for card in _iter_reference_cards(base):
        p = str(card.get("platform", "")).strip() or "未标"
        c = str(card.get("category", "")).strip() or "未分类"
        inventory.setdefault(p, set()).add(c)
    return {k: sorted(v) for k, v in sorted(inventory.items())}


def _format_card(idx: int, r: dict[str, Any]) -> str:
    """格式化单条参考卡片。"""
    engagement = r.get("engagement") or "—"
    platform = r.get("platform") or "未知平台"
    parts = [f"{idx}. [{platform} · {engagement}] {r['title']}"]
    if r.get("category"):
        parts.append(f"   品类：{r['category']}")
    if r.get("hook"):
        parts.append(f"   开头抓手：{r['hook']}")
    if r.get("structure"):
        parts.append(f"   内容结构：{r['structure']}")
    if r.get("cta"):
        parts.append(f"   结尾 CTA：{r['cta']}")
    if r.get("opening"):
        parts.append(f"   开场原文：{r['opening']}")
    parts.append(f"   路径：{r['path']}（可用 read_knowledge 读全文）")
    return "\n".join(parts)


def _format_inventory(inv: dict[str, list[str]]) -> str:
    if not inv:
        return "（对标库当前为空）"
    parts = []
    for platform, cats in inv.items():
        parts.append(f"  - {platform}: {', '.join(cats)}")
    return "\n".join(parts)


async def execute(params: dict, context: AgentContext) -> str:
    query = (params.get("query") or "").strip()
    platform = (params.get("platform") or "").strip() or None
    max_results = int(params.get("max_results") or 5)
    max_results = max(1, min(max_results, 10))

    if not query:
        return "错误: query 不能为空，请至少提供一个搜索关键词。"

    keywords = [k for k in query.split() if k.strip()]

    base = Path(KNOWLEDGE_BASE_PATH) / _REFERENCES_SUBDIR
    results = _find_references(base, keywords, platform, max_results)

    # —— 精准命中路径 ——
    if results:
        lines = [
            f"找到 {len(results)} 篇对标参考"
            + (f"（平台：{platform}）" if platform else "")
            + "：",
            "",
        ]
        for i, r in enumerate(results, 1):
            lines.append(_format_card(i, r))
            lines.append("")
        lines.append(
            "撰写前请总结对标共性（hook 类型 / structure / cta 方式），"
            "并在成稿中明示你借鉴了哪些元素。"
        )
        return "\n".join(lines)

    # —— 降级路径 1：按平台取热度 top-N 作为通用结构启发 ——
    fallback_cards = _fallback_by_platform(base, platform, max_results=3)
    inventory = _library_inventory(base)

    if fallback_cards:
        lines = [
            f"⚠️ 关键词「{query}」未命中精准对标"
            + (f"（平台过滤：{platform}）" if platform else "")
            + "。以下是**同平台热度 top-3** 作为通用结构启发"
            + "（**非精准对标，只能抽象套结构骨架，不要照搬措辞或场景**）：",
            "",
        ]
        for i, r in enumerate(fallback_cards, 1):
            lines.append(_format_card(i, r))
            lines.append("")
        lines.append("📚 对标库当前覆盖的 platform × category：")
        lines.append(_format_inventory(inventory))
        lines.append("")
        lines.append(
            "撰写建议：从以上降级样本抽『通用开头抓手 / 结构骨架 / CTA 模式』，"
            "不要套用里面的具体品类描述。成稿注释里请如实写明「未命中精准，已用 XX 降级」。"
        )
        return "\n".join(lines)

    # —— 降级路径 2：SerpAPI（需配 REFERENCE_SEARCH_API_KEY）——
    fallback = _try_serpapi_fallback(query, platform, max_results)
    if fallback:
        return fallback

    # —— 库完全为空 ——
    return (
        f"对标库完全为空或过滤器过严：query='{query}' platform={platform}。\n"
        f"📚 当前覆盖：\n{_format_inventory(inventory)}\n\n"
        "建议：① 放宽关键词 ② 去掉 platform 过滤 ③ 若库真无此品类，"
        "请在成稿注释里如实声明「对标库无此品类样本」，并用平台通用爆款结构撰写。"
    )


def _try_serpapi_fallback(
    query: str, platform: str | None, max_results: int
) -> str | None:
    """可选的 SerpAPI 降级路径。

    仅当配置了 REFERENCE_SEARCH_API_KEY 环境变量时启用，
    Demo 默认走本地库，避免现场网络风险。
    """
    api_key = os.getenv("REFERENCE_SEARCH_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        import httpx  # 延迟导入，未启用时不拉依赖路径

        engine = "bing" if "bing" in os.getenv("REFERENCE_SEARCH_ENGINE", "").lower() else "google"
        q = f"{platform or ''} {query}".strip()
        url = "https://serpapi.com/search"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params={
                "engine": engine,
                "q": q,
                "num": max_results,
                "api_key": api_key,
            })
            if resp.status_code != 200:
                logger.warning("[search_reference] SerpAPI 非 200: %s", resp.status_code)
                return None
            data = resp.json()
    except Exception as e:
        logger.warning("[search_reference] SerpAPI 调用失败: %s", e)
        return None

    items = data.get("organic_results") or []
    if not items:
        return None

    lines = [f"（本地未命中，调用 SerpAPI 补充 {len(items)} 条网络结果）", ""]
    for i, item in enumerate(items[:max_results], 1):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        lines.append(f"{i}. {title}\n   摘要：{snippet}\n   链接：{link}")
    lines.append("")
    lines.append("注意：网络结果仅供启发，撰写时仍需确认平台调性与合规边界。")
    return "\n".join(lines)
