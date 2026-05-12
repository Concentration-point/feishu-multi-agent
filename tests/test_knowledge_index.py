"""pytest: 轻量倒排索引 + search_knowledge 集成回归。

覆盖点:
- 多关键词时高命中分数文档排前
- mtime 变更后增量更新
- 索引构建失败时 fallback 到 grep（行为可用）
- 返回结果包含新字段 matched_terms / section_heading / score，且兼容老字段
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

# 让 tests 可独立 import 项目源码
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from memory.knowledge_index import (
    KnowledgeIndex,
    find_section_heading,
    reset_cache,
    tokenize,
)
from tools.search_knowledge import search_structured, _grep_search


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture()
def kb_dir(tmp_path: Path) -> Path:
    """构造一个临时知识库目录，含若干 .md 文件。"""
    base = tmp_path / "kb"
    (base / "04_平台打法").mkdir(parents=True)
    (base / "10_经验沉淀").mkdir(parents=True)
    (base / "06_待整理收件箱").mkdir(parents=True)  # 排除目录

    # doc1: 多次出现 "电商" 和 "小红书"，应排前
    (base / "04_平台打法" / "doc1.md").write_text(
        "---\ncategory: 平台\n---\n"
        "# 平台打法总览\n\n"
        "电商行业里，小红书种草是主流路径。电商品牌都在小红书做内容。\n\n"
        "## 电商案例\n\n"
        "某电商品牌在小红书做了 100 篇笔记。\n",
        encoding="utf-8",
    )

    # doc2: 只出现 "小红书" 一次
    (base / "10_经验沉淀" / "doc2.md").write_text(
        "# 经验总结\n\n"
        "## 渠道经验\n\n"
        "小红书是种草渠道，但要注意调性。\n",
        encoding="utf-8",
    )

    # doc3: 完全无关
    (base / "10_经验沉淀" / "doc3.md").write_text(
        "# 其他主题\n\n抖音直播带货的策略。\n",
        encoding="utf-8",
    )

    # 收件箱里的脏数据：不应被检索到
    (base / "06_待整理收件箱" / "dirty.md").write_text(
        "电商 小红书 电商 小红书 电商 小红书\n",
        encoding="utf-8",
    )

    reset_cache()
    return base


@pytest.fixture(autouse=True)
def _cleanup_cache():
    """每个用例前后清空索引单例，避免互相污染。"""
    reset_cache()
    yield
    reset_cache()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  分词 / heading helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_tokenize_mixed():
    """分词应同时产出英文整词、中文 unigram、中文 bigram。"""
    toks = set(tokenize("电商Demo 小红书"))
    assert "demo" in toks
    assert "电" in toks
    assert "电商" in toks
    assert "小红" in toks


def test_find_section_heading():
    text = "# A\n正文1\n## B\n正文2 命中点"
    pos = text.index("命中点")
    assert find_section_heading(text, pos) == "B"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  排序
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_multi_keyword_ranking(kb_dir: Path):
    """多关键词命中分数高的应排前。"""
    idx = KnowledgeIndex(kb_dir)
    idx.refresh()
    results = idx.search("电商 小红书", limit=5)
    assert results, "至少应有结果"
    # doc1 多次命中，应排第一
    assert results[0]["path"].endswith("doc1.md"), f"实际: {results[0]['path']}"
    # doc1 分数应严格高于后续
    if len(results) >= 2:
        assert results[0]["score"] > results[1]["score"]


def test_excluded_dir_not_searched(kb_dir: Path):
    """06_待整理收件箱 / references 不应出现在结果里。"""
    idx = KnowledgeIndex(kb_dir)
    idx.refresh()
    results = idx.search("电商 小红书", limit=10)
    for r in results:
        assert "06_待整理收件箱" not in r["path"]
        assert "references" not in r["path"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  增量更新（mtime）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_incremental_update_on_mtime_change(kb_dir: Path):
    """修改一份 md 后下一次查询应能命中新内容。"""
    idx = KnowledgeIndex(kb_dir)
    idx.refresh()

    # 初始查 "独家秘籍" 应无命中
    r0 = idx.search("独家秘籍", limit=5)
    assert r0 == [], f"初始不应命中: {r0}"

    # 改 doc2，加入新关键词
    doc2 = kb_dir / "10_经验沉淀" / "doc2.md"
    new_content = doc2.read_text(encoding="utf-8") + "\n\n## 新章节\n独家秘籍：先做种子用户。\n"
    # 确保 mtime 一定变（windows 上 mtime 精度可能 1s）
    time.sleep(1.1)
    doc2.write_text(new_content, encoding="utf-8")
    os.utime(doc2, None)  # 显式触发 mtime

    r1 = idx.search("独家秘籍", limit=5)
    assert r1, f"修改后应命中新内容: {r1}"
    assert r1[0]["path"].endswith("doc2.md")
    assert r1[0]["section_heading"] == "新章节"


def test_deleted_file_drops_from_index(kb_dir: Path):
    """删除文件后增量更新应把它从结果中移除。"""
    idx = KnowledgeIndex(kb_dir)
    idx.refresh()
    r0 = idx.search("抖音", limit=5)
    assert r0, "doc3 应命中 '抖音'"
    target = kb_dir / "10_经验沉淀" / "doc3.md"
    target.unlink()
    r1 = idx.search("抖音", limit=5)
    assert all(not r["path"].endswith("doc3.md") for r in r1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Fallback 路径
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_grep_fallback_results_usable(kb_dir: Path):
    """直接调 _grep_search，结果集字段齐全（充当 index 失败时的兜底）。"""
    results = _grep_search(kb_dir, ["电商", "小红书"], scope="全部", limit=5)
    assert results
    top = results[0]
    assert top["path"].endswith("doc1.md")
    # 新字段
    assert "matched_terms" in top
    assert "section_heading" in top
    assert "score" in top
    # 老字段保留
    assert "hit_count" in top
    assert "hits" in top
    assert "snippet" in top


def test_search_structured_falls_back_on_index_error(kb_dir: Path, monkeypatch):
    """模拟索引刷新抛异常，search_structured 应回退到 grep 仍返回可用结果。"""
    from memory import knowledge_index as ki_mod

    # 把 KnowledgeIndex.search 打成抛异常
    def _broken_search(self, *a, **kw):
        raise RuntimeError("simulated index failure")

    monkeypatch.setattr(ki_mod.KnowledgeIndex, "search", _broken_search)

    results, mode = search_structured(
        "电商 小红书", scope="全部", base_path=kb_dir, limit=5
    )
    assert mode == "grep", f"应回退到 grep，实际 mode={mode}"
    assert results, "fallback 应返回结果"
    assert results[0]["path"].endswith("doc1.md")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  新字段 + 老字段兼容
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_result_has_new_and_legacy_fields(kb_dir: Path):
    """索引模式下的结果同时包含新字段和老字段。"""
    results, mode = search_structured(
        "电商 小红书", scope="全部", base_path=kb_dir, limit=5
    )
    assert mode == "index"
    assert results
    top = results[0]
    # 新字段
    assert isinstance(top["matched_terms"], list)
    assert top["matched_terms"], "matched_terms 不应为空"
    assert "section_heading" in top
    assert isinstance(top["score"], (int, float))
    # 老字段兼容
    assert "path" in top
    assert "hit_count" in top
    assert "hits" in top
    assert "snippet" in top


def test_section_heading_pinpoints_subsection(kb_dir: Path):
    """命中如果落在子标题段落，section_heading 应是该子标题。"""
    results, mode = search_structured("种草", scope="全部", base_path=kb_dir, limit=5)
    assert results, "应该命中 doc1/doc2"
    # 至少有一个结果的 section_heading 非空
    headings = [r["section_heading"] for r in results]
    assert any(h for h in headings), f"section_heading 全为空: {headings}"
