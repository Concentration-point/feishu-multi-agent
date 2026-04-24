"""工具: 写入知识收件箱（本地 + 标记同步）

新分层后所有自动产出的经验写入 knowledge/11_待整理收件箱/，等升格机制
通过后才迁入 knowledge/10_经验沉淀/。旧 knowledge/wiki/ 目录作为历史
数据保留但不再新写。

同时导出共享函数供 memory/experience.py 和 sync/wiki_sync.py 复用：
  - sanitize_name: 文件名清洗（覆盖 Windows 非法字符）
  - mark_dirty: 标记 .sync_state.json dirty
  - update_wiki_index: 重新生成指定目录下的 _index.md
  - build_wiki_frontmatter: 统一 frontmatter 格式
  - build_wiki_document: 统一 wiki 正文模板
  - strip_frontmatter / prepare_docx_markdown: 同步到飞书前的 Markdown 清洗
"""

# 新分层：自动产出默认落点
WIKI_WRITE_SUBDIR = "11_待整理收件箱"
# 旧分层：历史数据留存，不再新写
LEGACY_WIKI_SUBDIR = "wiki"

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from tools import AgentContext
from config import KNOWLEDGE_BASE_PATH

SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_wiki",
        "description": (
            "将经验或知识沉淀写入本地 11_待整理收件箱/（新分层缓冲区）。"
            "后台同步线程会把收件箱以外的正式知识推到飞书知识空间；"
            "收件箱数据不外推，等升格后才进入 10_经验沉淀/。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "分类目录名，如 '电商大促'、'新品发布'、'品牌传播'",
                },
                "title": {
                    "type": "string",
                    "description": "文档标题，如 '小红书种草笔记写法总结'",
                },
                "content": {
                    "type": "string",
                    "description": "文档正文内容（Markdown 格式）",
                },
            },
            "required": ["category", "title", "content"],
        },
    },
}

# ── 共享工具函数（供 memory/experience.py 复用）──

# 文件名/目录名允许的字符：字母、数字、中文、下划线、短横线、空格
_SAFE_NAME_RE = re.compile(r'[^a-zA-Z0-9\u4e00-\u9fff_\- ]')


def sanitize_name(name: str, max_len: int = 40) -> str:
    """清洗文件名/目录名，替换所有不安全字符为下划线。

    覆盖 Windows 非法字符（: ? * < > | " ）和路径穿越字符（.. / \\）。
    """
    cleaned = _SAFE_NAME_RE.sub("_", name)
    cleaned = cleaned.strip("_. ")
    # 压缩连续下划线
    cleaned = re.sub(r'_+', '_', cleaned)
    return cleaned[:max_len] or "unnamed"


def mark_dirty(base_path: Path, rel_path: str) -> None:
    """在 .sync_state.json 中标记文件为 dirty。

    统一 schema: {hash, dirty, updated_at}
    同步成功后由 wiki_sync.py 追加 synced_at 并设 dirty=False。
    """
    state_file = base_path / ".sync_state.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    full_file = base_path / rel_path
    content = full_file.read_text(encoding="utf-8") if full_file.exists() else ""
    file_hash = hashlib.md5(content.encode()).hexdigest()

    entry = state.get(rel_path, {})
    entry.update({
        "hash": file_hash,
        "dirty": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    # 保留已有的 synced_at（如果之前同步过）
    state[rel_path] = entry

    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_wiki_index(wiki_dir: Path, *, url_prefix: str | None = None) -> None:
    """扫描 wiki_dir 下所有文件，重新生成 _index.md。

    url_prefix：索引条目前缀（如 'wiki' 或 '11_待整理收件箱'）。
    默认使用 wiki_dir 的目录名，保持可读性。
    """
    entries: list[str] = []
    prefix = url_prefix or wiki_dir.name
    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.name.startswith("_"):
            continue
        rel = md_file.relative_to(wiki_dir).as_posix()
        category = md_file.parent.name if md_file.parent != wiki_dir else "未分类"
        title = md_file.stem
        entries.append(f"- [{category}] {title} — `{prefix}/{rel}`")

    index_content = (
        f"# {wiki_dir.name} 索引\n\n"
        "> 此索引由 Agent 自动维护，每次知识沉淀后自动更新。\n\n"
        "## 目录\n\n"
    )
    if entries:
        index_content += "\n".join(entries) + "\n"
    else:
        index_content += "（暂无条目，Agent 运行后会自动填充）\n"

    (wiki_dir / "_index.md").write_text(index_content, encoding="utf-8")


def build_wiki_frontmatter(
    *,
    category: str,
    role: str = "",
    confidence: float = 0.0,
) -> str:
    """构造统一的 wiki frontmatter。所有写入路径使用同一格式。"""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "---",
        f"created: {now_str}",
        "source: Agent 自动蒸馏",
        f"category: {category}",
    ]
    if role:
        lines.append(f"role: {role}")
    if confidence > 0:
        lines.append(f"confidence: {confidence}")
    lines.append("---")
    return "\n".join(lines)


def build_wiki_document(*, title: str, content: str, category: str, role: str = "", confidence: float = 0.0) -> str:
    """构造统一 wiki 文档模板。

    约定结构：frontmatter + H1 标题 + 元信息块 + 正文。
    这样本地 wiki 和后续 docx 同步都能吃同一种稳定结构。
    """
    frontmatter = build_wiki_frontmatter(category=category, role=role, confidence=confidence)
    meta_lines = [f"- 分类：{category}"]
    if role:
        meta_lines.append(f"- 角色：{role}")
    if confidence > 0:
        meta_lines.append(f"- 置信度：{confidence:.2f}")
    meta_block = "\n".join(meta_lines)
    body = (content or "").strip()
    return f"{frontmatter}\n\n# {title}\n\n## 元信息\n{meta_block}\n\n## 正文\n{body}\n"


def strip_frontmatter(markdown: str) -> str:
    text = (markdown or "").replace("\r\n", "\n")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :].lstrip()
    return text


def prepare_docx_markdown(markdown: str) -> str:
    """为飞书 docx 写入做最小清洗，尽量避开 field validation failed。"""
    text = strip_frontmatter(markdown)
    text = text.replace("\x00", "")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def prepare_docx_plaintext(markdown: str) -> str:
    """为飞书 docx 写入做安全纯文本降级。"""
    text = strip_frontmatter(markdown)
    text = text.replace("\r\n", "\n").replace("\x00", "")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^>+\s*", "", text, flags=re.M)
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.M)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.M)
    text = re.sub(r"^\s*[-:| ]+\s*$", "", text, flags=re.M)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text + "\n" if text else ""


# ── 工具入口 ──

async def execute(params: dict, context: AgentContext) -> str:
    category = params.get("category", "").strip()
    title = params.get("title", "").strip()
    content = params.get("content", "").strip()

    if not category or not title or not content:
        return "错误: category、title、content 均不能为空"

    # 清洗文件名
    safe_category = sanitize_name(category)
    safe_title = sanitize_name(title)

    base_path = Path(KNOWLEDGE_BASE_PATH)
    # 写入新分层「11_待整理收件箱」
    inbox_dir = (base_path / WIKI_WRITE_SUBDIR).resolve()
    cat_dir = (inbox_dir / safe_category).resolve()
    target_file = (cat_dir / f"{safe_title}.md").resolve()

    # 安全校验：路径边界（防止 resolve 后逃逸）
    if not target_file.is_relative_to(inbox_dir):
        return f"错误: 路径越界，只能写入 knowledge/{WIKI_WRITE_SUBDIR}/ 目录内"

    cat_dir.mkdir(parents=True, exist_ok=True)

    # 写入文件（统一 wiki 模板）
    file_content = build_wiki_document(
        title=title,
        content=content,
        category=category,
        role=context.role_id,
    )
    target_file.write_text(file_content, encoding="utf-8")

    # 更新索引（指向新分层）
    update_wiki_index(inbox_dir, url_prefix=WIKI_WRITE_SUBDIR)

    # 标记 dirty（使用新分层路径；sync 会根据黑名单决定是否实际推送）
    rel_path = f"{WIKI_WRITE_SUBDIR}/{safe_category}/{safe_title}.md"
    mark_dirty(base_path, rel_path)
    mark_dirty(base_path, f"{WIKI_WRITE_SUBDIR}/_index.md")

    return (
        f"已写入 {WIKI_WRITE_SUBDIR}/{safe_category}/{safe_title}.md"
        "（收件箱缓冲区，等待升格到 10_经验沉淀/ 后才对外同步）"
    )
