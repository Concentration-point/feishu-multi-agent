"""轻量倒排索引 — 本地知识库的关键词检索加速。

设计目标:
- **零额外依赖**: 只用标准库（re, json, pathlib, threading）。
- **稳健 fallback**: 索引构建/检索失败时由调用方回退到 grep。
- **增量 mtime 更新**: search 入口比对 .md 文件 mtime 集，只重建变化的文件。
- **结构化结果**: 每条命中包含 `path / matched_terms / section_heading / score / snippet`。

不做:
- 不引入 embedding / 向量检索 / jieba 等重依赖。
- 不依赖磁盘缓存（可选 cache，本实现先全内存，构建成本可接受）。

分词策略（简单稳健）:
- 英文/数字：连续 ASCII 字母数字切片，转小写。
- 中文：连续 CJK 字符做 unigram + bigram（"电商大促" -> "电","商","大","促","电商","商大","大促"）。
- 其他字符直接作为分隔符丢弃。

打分:
- score = Σ over matched_terms ( term_freq_in_doc * idf ) ；idf = log(N / df + 1)。
- 同时返回 matched_terms（命中的查询 token 集合），方便 LLM 解释命中原因。
"""

from __future__ import annotations

import logging
import math
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


# ── 分词正则 ──
# ASCII 字母数字组（英文 token）
_RE_ASCII = re.compile(r"[A-Za-z0-9]+")
# CJK 统一表意文字范围 + 兼容扩展（粗略覆盖中文）
_RE_CJK = re.compile(r"[一-鿿]+")

# 标题行匹配：#/##/### 等
_RE_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# 默认排除目录（脏缓冲、对标素材等）
_DEFAULT_EXCLUDE_DIRS: tuple[str, ...] = (
    "06_待整理收件箱",
    "11_待整理收件箱",
    "references",
)


def tokenize(text: str) -> list[str]:
    """把一段文本切成小写 token 列表（英文整词 + 中文 unigram+bigram）。

    注意:
    - 不去停用词（保留简单稳健，否则中文停用词难定义）。
    - 同一 token 可能重复出现，调用方需要的话再去重。
    """
    tokens: list[str] = []
    if not text:
        return tokens

    # 英文/数字
    for m in _RE_ASCII.findall(text):
        tokens.append(m.lower())

    # 中文 unigram + bigram
    for chunk in _RE_CJK.findall(text):
        # unigram
        for ch in chunk:
            tokens.append(ch)
        # bigram
        for i in range(len(chunk) - 1):
            tokens.append(chunk[i:i + 2])

    return tokens


def _strip_frontmatter(text: str) -> str:
    """剥离 Markdown 开头的 YAML frontmatter。"""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2].lstrip("\n")


def find_section_heading(content: str, char_pos: int) -> str:
    """返回 char_pos 所在位置最近的上方标题文本（# / ## / ...）；找不到返回 ""。"""
    if char_pos < 0 or not content:
        return ""
    head = content[:char_pos]
    last_heading = ""
    for line in head.splitlines():
        m = _RE_HEADING.match(line)
        if m:
            last_heading = m.group(2).strip()
    return last_heading


@dataclass
class _DocEntry:
    """单文档的索引信息（驻内存）。"""
    path: str                                 # 相对 base 的 posix 路径
    mtime: float
    content: str                              # 已剥离 frontmatter 的正文
    # token -> [出现位置 char_pos, ...]
    token_positions: dict[str, list[int]] = field(default_factory=dict)


class KnowledgeIndex:
    """本地知识库倒排索引（驻内存，按需增量重建）。

    用法:
        idx = KnowledgeIndex(base_path)
        idx.refresh()                                # 可选：主动重建
        results = idx.search("电商 小红书", limit=5)
    """

    def __init__(
        self,
        base_path: Path | str,
        exclude_dirs: Iterable[str] = _DEFAULT_EXCLUDE_DIRS,
    ) -> None:
        self.base_path = Path(base_path)
        self.exclude_dirs = tuple(exclude_dirs)
        # 文档表：rel_path -> _DocEntry
        self._docs: dict[str, _DocEntry] = {}
        # 倒排表：token -> {rel_path: freq}
        self._postings: dict[str, dict[str, int]] = {}
        self._lock = threading.RLock()
        self._built = False

    # ── 公开 API ──
    def search(
        self,
        query: str,
        limit: int = 5,
        scope_dirs: Iterable[str] | None = None,
    ) -> list[dict]:
        """检索 query，返回命中文档列表（已按 score 降序）。

        Args:
            query: 用户查询字符串（多关键词空格分隔）。
            limit: 返回 top-N。
            scope_dirs: 限定一级子目录白名单；None=不限。

        Returns:
            list of dict，每条字段:
              - path: 相对 base 的 posix 路径
              - matched_terms: 命中的原始查询词列表
              - section_heading: 第一个命中所在的最近标题
              - score: float
              - snippet: 命中片段（200 字上下文）
              - hit_count / hits: 兼容老格式
        """
        self._refresh_if_needed()

        query = (query or "").strip()
        if not query:
            return []

        # 用户原始关键词（用于 matched_terms 和兜底子串命中）
        raw_terms = [t for t in query.split() if t]
        # 倒排查找用的 token 列表（小写化 + 中文切片）
        query_tokens = list(set(tokenize(query)))
        if not query_tokens:
            return []

        n_docs = max(len(self._docs), 1)
        # 计算每个 query token 的 idf
        idf: dict[str, float] = {}
        for tok in query_tokens:
            df = len(self._postings.get(tok, {}))
            idf[tok] = math.log(n_docs / (df + 1)) + 1.0

        scope_set: set[str] | None = set(scope_dirs) if scope_dirs else None

        scored: dict[str, float] = {}
        per_doc_hits: dict[str, set[str]] = {}
        for tok in query_tokens:
            postings = self._postings.get(tok)
            if not postings:
                continue
            w = idf[tok]
            for rel_path, freq in postings.items():
                if scope_set is not None:
                    first = rel_path.split("/", 1)[0]
                    if first not in scope_set:
                        continue
                scored[rel_path] = scored.get(rel_path, 0.0) + freq * w
                per_doc_hits.setdefault(rel_path, set()).add(tok)

        # 排序
        ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)

        results: list[dict] = []
        lower_terms = [t.lower() for t in raw_terms]
        for rel_path, score in ranked[: limit * 2]:  # 多取一点，做 matched_terms 兜底
            doc = self._docs.get(rel_path)
            if not doc:
                continue

            # 计算 matched_terms：要求**原始 raw 关键词作为子串**真出现在正文里，
            # 避免 bigram 拆分后的伪命中（如查 "完全不存在的xyz" 把每个中文字都摸过去）。
            content_lower = doc.content.lower()
            matched_terms: list[str] = []
            for raw, low in zip(raw_terms, lower_terms):
                if low and low in content_lower:
                    matched_terms.append(raw)

            if not matched_terms:
                # 无原词子串命中，跳过
                continue

            # snippet + section_heading：找第一个原始 term 的位置
            snippet = ""
            section_heading = ""
            for raw, low in zip(raw_terms, lower_terms):
                if not low:
                    continue
                pos = content_lower.find(low)
                if pos >= 0:
                    start = max(0, pos - 200)
                    end = min(len(doc.content), pos + len(raw) + 200)
                    snippet = doc.content[start:end].replace("\n", " ").strip()
                    section_heading = find_section_heading(doc.content, pos)
                    break

            results.append({
                "path": rel_path,
                "matched_terms": matched_terms,
                "section_heading": section_heading,
                "score": round(score, 4),
                "snippet": snippet,
                "hit_count": len(matched_terms),
                "hits": matched_terms,
            })
            if len(results) >= limit:
                break

        return results

    def refresh(self) -> None:
        """强制全量重建索引（供测试或维护使用）。"""
        with self._lock:
            self._docs.clear()
            self._postings.clear()
            self._built = False
            self._refresh_if_needed(force=True)

    # ── 内部 ──
    def _iter_md_files(self) -> Iterable[Path]:
        """枚举 base_path 下所有 .md 文件，跳过默认排除目录与隐藏/下划线文件。"""
        if not self.base_path.exists():
            return
        for md in self.base_path.rglob("*.md"):
            try:
                rel = md.relative_to(self.base_path).as_posix()
            except ValueError:
                continue
            first = rel.split("/", 1)[0]
            if first in self.exclude_dirs:
                continue
            name = md.name
            if name.startswith(".") or name.startswith("_"):
                continue
            if name.lower() == "readme.md":
                continue
            yield md

    def _refresh_if_needed(self, force: bool = False) -> None:
        """比对 mtime，增量重建变化的文件。"""
        with self._lock:
            try:
                current: dict[str, float] = {}
                for md in self._iter_md_files():
                    try:
                        rel = md.relative_to(self.base_path).as_posix()
                        current[rel] = md.stat().st_mtime
                    except Exception:
                        continue

                if force:
                    to_index = set(current.keys())
                    to_remove = set(self._docs.keys()) - set(current.keys())
                else:
                    to_index: set[str] = set()
                    for rel, mt in current.items():
                        doc = self._docs.get(rel)
                        if doc is None or doc.mtime != mt:
                            to_index.add(rel)
                    to_remove = set(self._docs.keys()) - set(current.keys())

                # 删除已不存在的文件
                for rel in to_remove:
                    self._remove_doc(rel)

                # 重建/新增
                for rel in to_index:
                    full = self.base_path / rel
                    try:
                        raw = full.read_text(encoding="utf-8")
                    except Exception as e:
                        logger.debug("读取失败跳过: %s — %s", rel, e)
                        continue
                    content = _strip_frontmatter(raw)
                    self._remove_doc(rel)  # 先清旧倒排
                    doc = _DocEntry(path=rel, mtime=current[rel], content=content)
                    self._add_doc(doc)

                self._built = True
            except Exception as e:
                # 索引构建失败：抛 RuntimeError 给上层 fallback
                logger.warning("KnowledgeIndex 刷新失败: %s", e)
                raise

    def _remove_doc(self, rel: str) -> None:
        """从倒排表中清除某文档的所有 token。"""
        doc = self._docs.pop(rel, None)
        if not doc:
            return
        for tok in doc.token_positions.keys():
            posting = self._postings.get(tok)
            if posting and rel in posting:
                del posting[rel]
                if not posting:
                    self._postings.pop(tok, None)

    def _add_doc(self, doc: _DocEntry) -> None:
        """把单个文档加入倒排表。"""
        # 用 finditer 找原文中 ascii / cjk 出现位置，记录每个 token 的首位置和频次
        positions: dict[str, list[int]] = {}

        for m in _RE_ASCII.finditer(doc.content):
            tok = m.group(0).lower()
            positions.setdefault(tok, []).append(m.start())

        for m in _RE_CJK.finditer(doc.content):
            chunk = m.group(0)
            base = m.start()
            for i, ch in enumerate(chunk):
                positions.setdefault(ch, []).append(base + i)
            for i in range(len(chunk) - 1):
                positions.setdefault(chunk[i:i + 2], []).append(base + i)

        doc.token_positions = positions
        self._docs[doc.path] = doc
        for tok, plist in positions.items():
            self._postings.setdefault(tok, {})[doc.path] = len(plist)


# ── 模块级单例（按 base_path 缓存）──
_INDEX_CACHE: dict[str, KnowledgeIndex] = {}
_CACHE_LOCK = threading.Lock()


def get_index(base_path: Path | str) -> KnowledgeIndex:
    """按路径缓存的单例索引。同一 base_path 复用同一实例。"""
    key = str(Path(base_path).resolve())
    with _CACHE_LOCK:
        idx = _INDEX_CACHE.get(key)
        if idx is None:
            idx = KnowledgeIndex(base_path)
            _INDEX_CACHE[key] = idx
        return idx


def reset_cache() -> None:
    """清空单例缓存（测试用）。"""
    with _CACHE_LOCK:
        _INDEX_CACHE.clear()
