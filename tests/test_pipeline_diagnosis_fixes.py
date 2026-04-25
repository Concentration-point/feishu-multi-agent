"""知识沉淀链路诊断报告修复的端到端冒烟测试。

覆盖 4 个修复（隐患 1/2/3/5；隐患 4 是运行数据问题不在代码范围）：

- 隐患 5：search_knowledge 剥离 frontmatter，避免 category/role 污染命中
- 隐患 3：wiki_sync 默认黑名单 references/，不推对标素材到飞书
- 隐患 2：base.py _build_wiki_title 用规整化 + md5 指纹，仅标点差异自动去重
- 隐患 1：scripts/reset_dirty_sync.py 能识别 dirty 条目并 dry-run 正确

运行：
    python tests/test_pipeline_diagnosis_fixes.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run_py(script: Path, *args: str) -> subprocess.CompletedProcess:
    """跑 Python 子脚本，强制子进程用 UTF-8 写 stdout，避免 Windows cp936 乱码。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )


async def test_hidden_5_frontmatter_stripped() -> list[str]:
    """隐患5：frontmatter 里含关键词但正文不含，应不命中。"""
    fails: list[str] = []

    from tools.search_knowledge import _strip_frontmatter, _search_files

    # 验证 _strip_frontmatter 正确切掉 YAML 块
    doc_with_fm = "---\ncategory: 电商大促\nrole: copywriter\n---\n\n正文只讨论新品发布。"
    stripped = _strip_frontmatter(doc_with_fm)
    if "category" in stripped or "电商大促" in stripped:
        fails.append("_strip_frontmatter 未切掉 frontmatter")
    else:
        print("[PASS] 隐患5 _strip_frontmatter 正确剥离")

    # 没有 frontmatter 的文本应原样返回
    plain = "# 普通文档\n正文内容"
    if _strip_frontmatter(plain) != plain:
        fails.append("_strip_frontmatter 错误地修改了无 frontmatter 的文本")
    else:
        print("[PASS] 隐患5 无 frontmatter 时不修改原文")

    # 构造临时目录，放两个文件：
    #   A: frontmatter 含"电商大促"但正文不含
    #   B: 正文含"电商大促"
    # 搜"电商大促"应只命中 B
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "a.md").write_text(
            "---\ncategory: 电商大促\n---\n\n正文只谈论新品发布策略。",
            encoding="utf-8",
        )
        (tmp_path / "b.md").write_text(
            "# 真正讨论电商大促的文档\n\n这里正文谈论电商大促活动。",
            encoding="utf-8",
        )
        results = _search_files(tmp_path, ["电商大促"])
        paths = {r["path"] for r in results}
        if "b.md" not in paths:
            fails.append(f"隐患5：正文含关键词的 b.md 应命中，实际命中 {paths}")
        if "a.md" in paths:
            fails.append(f"隐患5：frontmatter 噪音未过滤，a.md 不该命中，实际 {paths}")
        if "b.md" in paths and "a.md" not in paths:
            print(f"[PASS] 隐患5 正文搜索隔离 frontmatter 噪音 命中={paths}")

    return fails


def test_hidden_3_sync_exclude_references() -> list[str]:
    """隐患3：sync 默认黑名单排除 references/，其他目录正常扫描。"""
    fails: list[str] = []

    # 设置环境变量覆盖 KNOWLEDGE_BASE_PATH 到临时目录
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # 构造 wiki/ / raw/ / references/ 三种目录
        (tmp_path / "wiki" / "电商大促").mkdir(parents=True)
        (tmp_path / "wiki" / "电商大促" / "w.md").write_text("wiki-file", encoding="utf-8")

        (tmp_path / "raw").mkdir()
        (tmp_path / "raw" / "r.md").write_text("raw-file", encoding="utf-8")

        (tmp_path / "references" / "小红书").mkdir(parents=True)
        (tmp_path / "references" / "小红书" / "ref.md").write_text("ref-file", encoding="utf-8")

        # 动态覆盖 config.KNOWLEDGE_BASE_PATH
        import config
        old_kb = config.KNOWLEDGE_BASE_PATH
        config.KNOWLEDGE_BASE_PATH = str(tmp_path)

        try:
            # 重新 import，让 WikiSyncService 拿到新的 base_path
            import importlib
            from sync import wiki_sync as wm
            importlib.reload(wm)

            svc = wm.WikiSyncService(space_id="test_space")
            # state 为空，rglob 找到的都算新文件
            dirty = svc._find_dirty_files({})
            paths = set(dirty)

            if not any(p.startswith("wiki/") for p in paths):
                fails.append(f"隐患3：wiki/ 应被扫描到，实际 {paths}")
            if not any(p.startswith("raw/") for p in paths):
                fails.append(f"隐患3：raw/ 应被扫描（文档允许同步到历史方案节点），实际 {paths}")
            if any(p.startswith("references/") for p in paths):
                fails.append(f"隐患3：references/ 不该被扫描，实际 {paths}")
            if not fails:
                print(f"[PASS] 隐患3 sync 过滤 references/ 成功 dirty={sorted(paths)}")

            # 验证 WIKI_SYNC_EXCLUDE_DIRS 环境变量能覆盖
            os.environ["WIKI_SYNC_EXCLUDE_DIRS"] = "raw,references"
            importlib.reload(wm)
            svc2 = wm.WikiSyncService(space_id="test_space")
            dirty2 = set(svc2._find_dirty_files({}))
            if any(p.startswith("raw/") for p in dirty2):
                fails.append(f"隐患3：WIKI_SYNC_EXCLUDE_DIRS 未生效，raw/ 应被过滤 实际 {dirty2}")
            else:
                print(f"[PASS] 隐患3 WIKI_SYNC_EXCLUDE_DIRS 覆盖生效 dirty={sorted(dirty2)}")
            del os.environ["WIKI_SYNC_EXCLUDE_DIRS"]
            importlib.reload(wm)
        finally:
            config.KNOWLEDGE_BASE_PATH = old_kb

    return fails


def test_hidden_2_title_dedup_by_fingerprint() -> list[str]:
    """隐患2：仅标点差异的 lesson 命中同一文件名，自动去重。"""
    fails: list[str] = []

    # 不依赖 LLM，直接用 BaseAgent._build_wiki_title 类方法
    # 但 _build_wiki_title 依赖 self.role_id，用一个最小桩
    from agents.base import BaseAgent

    class _Stub:
        role_id = "reviewer"
        # 借用 BaseAgent 的非 bound 方法
        _build_wiki_title = BaseAgent._build_wiki_title

    stub = _Stub()

    # 报告里给的三个例子：仅标点差异
    lesson_a = "下次文案在撰写这类内容前必须先检查：1)"
    lesson_b = "下次文案在撰写这类内容前必须先检查：1）"  # 全角括号
    lesson_c = "下次文案在撰写这类内容前，必须先检查：1"  # 加了逗号

    t_a = stub._build_wiki_title(lesson_a)
    t_b = stub._build_wiki_title(lesson_b)
    t_c = stub._build_wiki_title(lesson_c)

    # 提取 fingerprint 部分（最后 8 字符）
    fp_a = t_a[-8:]
    fp_b = t_b[-8:]
    fp_c = t_c[-8:]
    if not (fp_a == fp_b == fp_c):
        fails.append(f"隐患2：同语义标点差异 lesson 指纹不一致 a={fp_a} b={fp_b} c={fp_c}")
    else:
        print(f"[PASS] 隐患2 同语义标点差异合并为同 fingerprint={fp_a}")

    # 不同语义必须产生不同指纹
    lesson_diff = "下次撰写小红书种草时先搜对标爆款"
    t_d = stub._build_wiki_title(lesson_diff)
    if t_d[-8:] == fp_a:
        fails.append(f"隐患2：不同语义 lesson 指纹碰撞 {fp_a}")
    else:
        print(f"[PASS] 隐患2 不同语义 lesson 指纹区分 {fp_a} vs {t_d[-8:]}")

    # 命名格式校验
    if not t_a.startswith("reviewer_"):
        fails.append(f"隐患2：title 前缀不含 role_id reviewer_，实际 {t_a}")
    else:
        print(f"[PASS] 隐患2 title 格式 {t_a}")

    return fails


def test_hidden_1_reset_dirty_dry_run() -> list[str]:
    """隐患1：reset_dirty_sync.py --dry-run 能识别 dirty 条目，不改文件。"""
    fails: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # 构造 .sync_state.json
        state = {
            "wiki/电商大促/a.md": {
                "hash": "abc", "dirty": True,
                "updated_at": "2026-04-15T00:00:00",
                "synced_at": "2026-04-10T00:00:00",
            },
            "wiki/电商大促/b.md": {
                "hash": "xyz", "dirty": False,
                "updated_at": "2026-04-16T00:00:00",
                "synced_at": "2026-04-16T00:00:00",
            },
            "wiki/电商大促/ghost.md": {
                "hash": "000", "dirty": True,
                "updated_at": "2026-04-15T00:00:00",
            },
        }
        # 实体文件：a.md 存在，ghost.md 不存在（孤儿）
        (tmp_path / "wiki" / "电商大促").mkdir(parents=True)
        (tmp_path / "wiki" / "电商大促" / "a.md").write_text("hello", encoding="utf-8")
        (tmp_path / "wiki" / "电商大促" / "b.md").write_text("world", encoding="utf-8")

        state_file = tmp_path / ".sync_state.json"
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        # 跑 dry-run
        script = ROOT / "scripts" / "reset_dirty_sync.py"
        result = _run_py(script, "--dry-run", "--knowledge-dir", str(tmp_path), "-v")
        out = result.stdout + result.stderr
        if result.returncode != 0:
            fails.append(f"隐患1：reset 脚本返回码 {result.returncode}\n{out}")
            return fails

        # dry-run 不应修改 state file
        after = json.loads(state_file.read_text(encoding="utf-8"))
        if after != state:
            fails.append("隐患1：--dry-run 居然修改了 .sync_state.json")
        else:
            print("[PASS] 隐患1 --dry-run 不修改 state 文件")

        # 输出应识别出 2 条 dirty（a.md 待重置 + ghost.md 孤儿）
        if "待重置: 1" not in out or "孤儿" not in out:
            fails.append(f"隐患1：dry-run 未正确识别 dirty 条目，输出:\n{out}")
        else:
            print("[PASS] 隐患1 dry-run 正确识别 1 待重置 + 1 孤儿")

        # 实际跑一次（非 dry-run）验证真的能清理
        result2 = _run_py(script, "--knowledge-dir", str(tmp_path))
        if result2.returncode != 0:
            fails.append(f"隐患1：reset 非 dry-run 返回码 {result2.returncode}")
            return fails

        after2 = json.loads(state_file.read_text(encoding="utf-8"))
        # a.md 和 ghost.md 应被移除，b.md 保留
        if "wiki/电商大促/a.md" in after2:
            fails.append("隐患1：dirty 条目 a.md 应被移除")
        if "wiki/电商大促/ghost.md" in after2:
            fails.append("隐患1：孤儿条目 ghost.md 应被移除")
        if "wiki/电商大促/b.md" not in after2:
            fails.append("隐患1：非 dirty 条目 b.md 不应被移除")
        if not fails:
            print(f"[PASS] 隐患1 实际执行后 state 缩减为 {list(after2.keys())}")

    return fails


def test_dedupe_wiki_dry_run() -> list[str]:
    """附加：隐患2 历史清理脚本 dry-run 能识别近重复。"""
    fails: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wiki = tmp_path / "wiki" / "电商大促"
        wiki.mkdir(parents=True)
        # 三个近重复（标点差异）
        common_body = "## 经验教训\n下次文案在撰写这类内容前必须先检查禁用词"
        (wiki / "reviewer_下次文案前检查_1.md").write_text(common_body, encoding="utf-8")
        (wiki / "reviewer_下次文案前检查_2.md").write_text(common_body + "。", encoding="utf-8")
        (wiki / "reviewer_下次文案前检查_3.md").write_text(common_body + "！", encoding="utf-8")
        # 一个独立
        (wiki / "copywriter_爆款对标_x.md").write_text(
            "## 经验教训\n小红书先搜爆款再动笔", encoding="utf-8",
        )

        script = ROOT / "scripts" / "dedupe_wiki.py"
        result = _run_py(
            script,
            "--dry-run",
            "--wiki-dir", str(tmp_path / "wiki"),
            "--state-file", str(tmp_path / ".sync_state.json"),
            "-v",
        )
        out = result.stdout + result.stderr
        if result.returncode != 0:
            fails.append(f"dedupe_wiki 返回码 {result.returncode}\n{out}")
            return fails

        # dry-run 下应报告 1 组近重复 + 2 个待合并
        if "1 组近重复" not in out or "合并删除 2" not in out:
            fails.append(f"dedupe_wiki dry-run 输出异常:\n{out}")
        else:
            print("[PASS] dedupe_wiki dry-run 识别 1 组近重复 + 2 待合并")

        # 物理文件未动
        if not (wiki / "reviewer_下次文案前检查_2.md").exists():
            fails.append("dedupe_wiki dry-run 居然删了文件")
        else:
            print("[PASS] dedupe_wiki dry-run 不修改物理文件")

    return fails


async def main() -> int:
    print("=" * 70)
    print("知识沉淀链路诊断报告修复 · 端到端冒烟测试")
    print("=" * 70)

    all_fails: list[str] = []

    print("\n--- 隐患 5：search_knowledge 剥离 frontmatter ---")
    all_fails.extend(await test_hidden_5_frontmatter_stripped())

    print("\n--- 隐患 3：sync 黑名单 references/ ---")
    all_fails.extend(test_hidden_3_sync_exclude_references())

    print("\n--- 隐患 2：wiki title 指纹去重 ---")
    all_fails.extend(test_hidden_2_title_dedup_by_fingerprint())

    print("\n--- 隐患 1：reset_dirty_sync 脚本 ---")
    all_fails.extend(test_hidden_1_reset_dirty_dry_run())

    print("\n--- 附加：dedupe_wiki 历史清理脚本 ---")
    all_fails.extend(test_dedupe_wiki_dry_run())

    print("\n" + "=" * 70)
    if all_fails:
        print(f"RESULT: FAIL ({len(all_fails)} 项未通过)")
        for f in all_fails:
            # 兜底：遇到终端编码问题时用 ASCII 可表示
            safe = f.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                sys.stdout.encoding or "utf-8", errors="replace"
            )
            print(f"  - {safe}")
        return 1
    print("RESULT: PASS — 4 个诊断问题 + 1 个历史清理脚本全部打通")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
