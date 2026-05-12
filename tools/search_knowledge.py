"""工具: 搜索本地知识库文档（分层 + scope 过滤）。

实现路径：
1. 优先用 `memory.knowledge_index.KnowledgeIndex` 倒排索引（含分数 + section_heading + matched_terms）。
2. 索引构建或检索抛异常 → 自动回退到原扫描 grep（保持向后兼容）。

向后兼容：
- 返回字段保留 `path / hit_count / hits / snippet`。
- 叠加新字段 `matched_terms / section_heading / score`（grep fallback 也填）。
"""

import logging
from pathlib import Path

from tools import AgentContext
from config import KNOWLEDGE_BASE_PATH
from memory.knowledge_index import (
    KnowledgeIndex,
    find_section_heading,
    get_index,
)

logger = logging.getLogger(__name__)


# ── 分层作用域映射（方案 B：语义角色映射）──
#
# scope 决定搜索哪些子目录。默认 "全部" 但会剔除 _DEFAULT_EXCLUDE 里的噪音。
_SCOPE_DIRS: dict[str, tuple[str, ...]] = {
    "方法论": ("01_企业底座", "02_服务方法论", "04_平台打法"),
    "模板":   ("05_标准模板",),
    "正式经验": ("10_经验沉淀",),
    # "全部" 在代码里特判
}

_DEFAULT_EXCLUDE: tuple[str, ...] = (
    "06_待整理收件箱",   # 脏数据缓冲区（新版目录）
    "11_待整理收件箱",   # 兼容旧版目录
    "references",       # 由 search_reference 专属
)


def _strip_frontmatter(text: str) -> str:
    """移除 Markdown 开头的 YAML frontmatter 块（grep fallback 用）。"""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2].lstrip("\n")


SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_knowledge",
        "description": (
            "在本地知识库中按 scope 搜索知识文档。支持多关键词，按命中分数排序返回摘要。"
            "scope 决定搜哪层：方法论（企业底座+服务方法论+平台打法+规则库）、"
            "模板（05_标准模板）、正式经验（10_经验沉淀+老 wiki）、全部。"
            "默认 '全部' 但已过滤收件箱和对标素材。搜到后可用 read_knowledge 看全文。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，多个用空格分隔，如 '电商 小红书 种草'",
                },
                "scope": {
                    "type": "string",
                    "enum": ["方法论", "模板", "正式经验", "全部"],
                    "description": "搜索范围。默认 '全部'。方法论用于查规则/打法，模板用于看标准格式，正式经验用于查沉淀过的高置信度经验。",
                },
            },
            "required": ["query"],
        },
    },
}


def _iter_scope_files(base_path: Path, scope: str):
    """按 scope 产出需要扫描的 .md 路径，跳过默认黑名单。"""
    if scope in _SCOPE_DIRS:
        for sub in _SCOPE_DIRS[scope]:
            target = base_path / sub
            if target.exists():
                for md in target.rglob("*.md"):
                    yield md
        return

    # scope == "全部" 或未识别：扫 base_path，剔除黑名单一级目录
    for md in base_path.rglob("*.md"):
        try:
            rel = md.relative_to(base_path).as_posix()
        except ValueError:
            continue
        first = rel.split("/", 1)[0]
        if first in _DEFAULT_EXCLUDE:
            continue
        yield md


def _scope_dirs(scope: str) -> tuple[str, ...] | None:
    """把 scope 转成给倒排索引的一级目录白名单；None=不限。"""
    return _SCOPE_DIRS.get(scope)


def _grep_search(
    base_path: Path,
    keywords: list[str],
    scope: str,
    limit: int = 5,
) -> list[dict]:
    """fallback：原扫描 grep 实现。补齐 matched_terms / section_heading / score 字段。"""
    results: list[dict] = []
    for md_file in _iter_scope_files(base_path, scope):
        if md_file.name.startswith(".") or md_file.name.startswith("_"):
            continue
        if md_file.name.lower() == "readme.md":
            continue
        try:
            raw = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        content = _strip_frontmatter(raw)
        content_lower = content.lower()
        hits = [kw for kw in keywords if kw.lower() in content_lower]
        if not hits:
            continue

        # 上下文片段 + section_heading：第一个命中关键词
        snippet = ""
        section_heading = ""
        for kw in hits:
            pos = content_lower.find(kw.lower())
            if pos >= 0:
                start = max(0, pos - 200)
                end = min(len(content), pos + len(kw) + 200)
                snippet = content[start:end].replace("\n", " ").strip()
                section_heading = find_section_heading(content, pos)
                break

        try:
            rel_path = md_file.relative_to(base_path).as_posix()
        except ValueError:
            rel_path = md_file.name

        # 简单评分：命中关键词数（fallback 模式不算 idf）
        score = float(len(hits))

        results.append({
            "path": rel_path,
            "hit_count": len(hits),
            "hits": hits,
            "matched_terms": hits,
            "section_heading": section_heading,
            "score": score,
            "snippet": snippet,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _search_files(base_path: Path, keywords: list[str], scope: str = "全部") -> list[dict]:
    """向后兼容旧调用方（如 tests/test_pipeline_diagnosis_fixes.py）。

    原行为是直接 grep + 命中数排序，限 5 条；现转发到 _grep_search。
    """
    return _grep_search(base_path, keywords, scope, limit=5)


def search_structured(
    query: str,
    scope: str = "全部",
    base_path: Path | None = None,
    limit: int = 5,
) -> tuple[list[dict], str]:
    """对外暴露的结构化检索：返回 (results, mode)；mode 取值 'index' / 'grep'。

    供测试和未来其他工具直接复用，避免在测试里解析人类可读字符串。
    """
    base = Path(base_path) if base_path else Path(KNOWLEDGE_BASE_PATH)
    if not base.exists():
        return [], "grep"

    keywords = [k for k in (query or "").split() if k]
    if not keywords:
        return [], "grep"

    # 1. 优先走倒排索引
    try:
        idx: KnowledgeIndex = get_index(base)
        scope_dirs = _scope_dirs(scope)
        results = idx.search(query, limit=limit, scope_dirs=scope_dirs)
        if results:
            return results, "index"
        # 索引可用但无命中：依旧返回 'index'（避免无谓的 grep 兜底）
        return [], "index"
    except Exception as e:
        logger.warning("knowledge_index 不可用，回退到 grep: %s", e)

    # 2. fallback
    results = _grep_search(base, keywords, scope, limit=limit)
    return results, "grep"


def _format_results(results: list[dict], scope: str, query: str) -> str:
    """把结构化结果格式化成 LLM 可读字符串。"""
    if not results:
        return (
            f"未找到与 '{query}' 相关的知识文档"
            + (f"（scope={scope}）" if scope != "全部" else "")
            + "。建议放宽关键词或切换 scope。"
        )

    lines = [f"找到 {len(results)} 个相关文档（scope={scope}）：\n"]
    for i, r in enumerate(results, 1):
        terms = r.get("matched_terms") or r.get("hits") or []
        heading = r.get("section_heading") or ""
        score = r.get("score", r.get("hit_count", 0))
        head_part = f" / 章节: {heading}" if heading else ""
        lines.append(
            f"{i}. [score={score} 命中={','.join(terms)}{head_part}] {r['path']}\n"
            f"   ...{(r.get('snippet') or '')[:300]}...\n"
        )
    lines.append("使用 read_knowledge 工具可查看完整内容。")
    return "\n".join(lines)


async def execute(params: dict, context: AgentContext) -> str:
    query = (params.get("query") or "").strip()
    scope = (params.get("scope") or "全部").strip() or "全部"
    if not query:
        return "错误: query 不能为空"

    base_path = Path(KNOWLEDGE_BASE_PATH)
    if not base_path.exists():
        return f"未找到与 '{query}' 相关的知识文档。"

    results, mode = search_structured(query, scope=scope, base_path=base_path, limit=5)
    logger.debug("search_knowledge mode=%s hits=%d", mode, len(results))

    return _format_results(results, scope, query)
