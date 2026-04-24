"""工具: 搜索本地知识库文档（分层 + scope 过滤）"""

from pathlib import Path
from tools import AgentContext
from config import KNOWLEDGE_BASE_PATH


# ── 分层作用域映射（方案 B：语义角色映射）──
#
# scope 决定搜索哪些子目录。默认 "全部" 但会剔除 _DEFAULT_EXCLUDE 里的噪音。
# - 方法论：企业底座 + 服务方法论 + 平台打法 + 规则库
# - 模板：  05_标准模板/（参数标注结构）
# - 正式经验：10_经验沉淀/ + 旧 wiki/（historical）
# - 全部：  除 _DEFAULT_EXCLUDE 外所有
#
# 黑名单：
# - 11_待整理收件箱/：脏数据缓冲区，不应在检索里
# - references/：   爆款对标，用 search_reference 专用工具，避免噪音
_SCOPE_DIRS: dict[str, tuple[str, ...]] = {
    "方法论": ("01_企业底座", "02_服务方法论", "04_平台打法"),
    "模板":   ("05_标准模板",),
    "正式经验": ("10_经验沉淀",),
    # "全部" 在代码里特判
}

_DEFAULT_EXCLUDE: tuple[str, ...] = (
    "11_待整理收件箱",  # 脏数据缓冲区
    "references",         # 由 search_reference 专属
)


def _strip_frontmatter(text: str) -> str:
    """移除 Markdown 开头的 YAML frontmatter 块。

    避免 frontmatter 里的 category/role 字段污染正文搜索的命中排序 —
    搜「电商大促」应命中正文讨论电商大促的文档，而不是所有 frontmatter 里
    category=电商大促 的文档。
    """
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
            "在本地知识库中按 scope 搜索知识文档。支持多关键词，按命中数排序返回摘要。"
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


def _search_files(base_path: Path, keywords: list[str], scope: str = "全部") -> list[dict]:
    """按 scope 遍历 .md 文件，返回命中结果（按命中数降序，限 5 条）。

    搜索范围仅限正文（剥离 YAML frontmatter 后的内容），避免 frontmatter
    的 category/role 字段把所有同类型文件都刷上来。
    """
    results = []
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

        # 上下文片段：第一个命中关键词前后各 200 字
        snippet = ""
        for kw in hits:
            pos = content_lower.find(kw.lower())
            if pos >= 0:
                start = max(0, pos - 200)
                end = min(len(content), pos + len(kw) + 200)
                snippet = content[start:end].replace("\n", " ").strip()
                break

        rel_path = md_file.relative_to(base_path).as_posix()
        results.append({
            "path": rel_path,
            "hit_count": len(hits),
            "hits": hits,
            "snippet": snippet,
        })

    results.sort(key=lambda x: x["hit_count"], reverse=True)
    return results[:5]


async def execute(params: dict, context: AgentContext) -> str:
    query = (params.get("query") or "").strip()
    scope = (params.get("scope") or "全部").strip() or "全部"
    if not query:
        return "错误: query 不能为空"

    keywords = query.split()
    base_path = Path(KNOWLEDGE_BASE_PATH)

    if not base_path.exists():
        return f"未找到与 '{query}' 相关的知识文档。"

    results = _search_files(base_path, keywords, scope)

    if not results:
        return (
            f"未找到与 '{query}' 相关的知识文档"
            + (f"（scope={scope}）" if scope != "全部" else "")
            + "。建议放宽关键词或切换 scope。"
        )

    lines = [f"找到 {len(results)} 个相关文档（scope={scope}）：\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. [命中{r['hit_count']}个] {r['path']}\n"
            f"   ...{r['snippet'][:300]}...\n"
        )
    lines.append("使用 read_knowledge 工具可查看完整内容。")
    return "\n".join(lines)
