"""scripts/test_wiki_sync.py 自身的冒烟测试。

在临时目录覆盖 KNOWLEDGE_BASE_PATH，验证六个子命令在不打真飞书 API 的前提下
都能走通。确保脚本改动不会悄悄破坏 Demo 时的演示链路。

运行：
    python tests/test_wiki_sync_harness.py
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


def _run_script(*args: str, knowledge_dir: Path | None = None) -> subprocess.CompletedProcess:
    """跑 scripts/test_wiki_sync.py，强制 UTF-8 stdout 避免 Windows 乱码。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if knowledge_dir:
        # 让 config.KNOWLEDGE_BASE_PATH 通过 env 覆盖
        env["KNOWLEDGE_BASE_PATH"] = str(knowledge_dir)
    script = ROOT / "scripts" / "test_wiki_sync.py"
    cmd = [sys.executable, str(script)]
    if knowledge_dir:
        cmd += ["--knowledge-dir", str(knowledge_dir)]
    cmd += list(args)
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env,
    )


def _seed_state(base: Path, entries: dict) -> None:
    (base / ".sync_state.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def test_status() -> list[str]:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "wiki" / "电商大促").mkdir(parents=True)
        (base / "wiki" / "电商大促" / "a.md").write_text("aaa", encoding="utf-8")
        _seed_state(base, {
            "wiki/电商大促/a.md": {
                "hash": "abc", "dirty": True,
                "updated_at": "2026-04-16T00:00:00",
                "synced_at": "2026-04-10T00:00:00",
            },
            "wiki/电商大促/ghost.md": {
                "hash": "000", "dirty": False,
                "synced_at": "2026-04-10T00:00:00",
            },
        })
        r = _run_script("status", knowledge_dir=base)
        if r.returncode != 0:
            fails.append(f"status rc={r.returncode}\n{r.stdout}\n{r.stderr}")
            return fails
        out = r.stdout
        for kw in ["总条目: 2", "dirty  : 1", "孤儿 orphans  : 1", "wiki/电商大促/a.md"]:
            if kw not in out:
                fails.append(f"status 缺关键字 {kw!r}\n输出:\n{out}")
        if not fails:
            print("[PASS] status 正确统计 dirty=1 / orphans=1")
    return fails


def test_seed_and_clean() -> list[str]:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        r = _run_script("seed", "--hint", "harness", knowledge_dir=base)
        if r.returncode != 0:
            fails.append(f"seed rc={r.returncode}\n{r.stderr}")
            return fails
        if "物理文件存在: True" not in r.stdout:
            fails.append(f"seed 未落盘\n{r.stdout}")
        if "dirty     : True" not in r.stdout:
            fails.append(f"seed 未标记 dirty\n{r.stdout}")
        probe_dir = base / "wiki" / "sync_probe"
        if not probe_dir.exists():
            fails.append("seed 目录 wiki/sync_probe/ 未生成")
        elif not list(probe_dir.glob("*.md")):
            fails.append("seed 目录无 .md 文件")
        else:
            print(f"[PASS] seed 生成 {len(list(probe_dir.glob('*.md')))} 个探针文件")

        r2 = _run_script("clean", knowledge_dir=base)
        if r2.returncode != 0:
            fails.append(f"clean rc={r2.returncode}\n{r2.stderr}")
            return fails
        if probe_dir.exists() and list(probe_dir.glob("*.md")):
            fails.append(f"clean 未清 {probe_dir}")
        else:
            print("[PASS] clean 清空探针目录")
        state = json.loads((base / ".sync_state.json").read_text(encoding="utf-8"))
        probe_entries = [k for k in state if k.startswith("wiki/sync_probe/")]
        if probe_entries:
            fails.append(f"clean 未清 state 条目 {probe_entries}")
        else:
            print("[PASS] clean 同步清理 state 条目")
    return fails


def test_once_dry_run() -> list[str]:
    """once --dry-run 不打飞书 API，只打印同步计划。"""
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "wiki" / "电商大促").mkdir(parents=True)
        (base / "wiki" / "电商大促" / "x.md").write_text("文档 x", encoding="utf-8")

        # state 为空 → 所有 .md 都算新文件
        r = _run_script("once", "--dry-run", knowledge_dir=base)
        if r.returncode != 0:
            fails.append(f"once --dry-run rc={r.returncode}\n{r.stderr}")
            return fails
        out = r.stdout
        for kw in ["DRY-RUN", "即将同步的文件数: 1", "wiki/电商大促/x.md", "未实际调用飞书 API"]:
            if kw not in out:
                fails.append(f"once --dry-run 缺关键字 {kw!r}\n{out}")
        if not fails:
            print("[PASS] once --dry-run 只打印计划不触发真实 API")
    return fails


def test_once_dry_run_filters_references() -> list[str]:
    """once --dry-run 结合 sync 黑名单：references/ 不应进入同步计划。"""
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "wiki" / "电商大促").mkdir(parents=True)
        (base / "wiki" / "电商大促" / "w.md").write_text("wiki 正文", encoding="utf-8")
        (base / "references" / "小红书").mkdir(parents=True)
        (base / "references" / "小红书" / "r.md").write_text("ref 素材", encoding="utf-8")

        r = _run_script("once", "--dry-run", knowledge_dir=base)
        out = r.stdout
        if "wiki/电商大促/w.md" not in out:
            fails.append(f"wiki 文件应出现在同步计划\n{out}")
        if "references/" in out:
            fails.append(f"references/ 不应出现在同步计划\n{out}")
        if not fails:
            print("[PASS] once --dry-run 正确过滤 references/")
    return fails


def test_e2e_dry_run() -> list[str]:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        r = _run_script("e2e", "--dry-run", knowledge_dir=base)
        if r.returncode != 0:
            fails.append(f"e2e rc={r.returncode}\n{r.stderr}\n{r.stdout[-500:]}")
            return fails
        out = r.stdout
        # 五个阶段都要出现
        stages = ["[E2E 1/5]", "[E2E 2/5]", "[E2E 3/5]", "[E2E 4/5]", "[E2E 5/5]"]
        for s in stages:
            if s not in out:
                fails.append(f"e2e 缺阶段 {s}")
        if "DRY-RUN 未实际调用飞书 API" not in out:
            fails.append("e2e dry-run 未标识")
        if not fails:
            print("[PASS] e2e --dry-run 五阶段全走通")

        # e2e 结束后探针目录应被清理
        probe_dir = base / "wiki" / "sync_probe"
        if probe_dir.exists() and list(probe_dir.glob("*.md")):
            fails.append("e2e 结束后探针目录未清")
    return fails


def test_invalid_knowledge_dir() -> list[str]:
    fails: list[str] = []
    r = _run_script("status", "--knowledge-dir", "/nonexistent/no/way")
    if r.returncode == 0:
        fails.append("不存在的 knowledge-dir 应返回非 0")
    else:
        print(f"[PASS] 不存在目录返回 rc={r.returncode}")
    return fails


def main() -> int:
    print("=" * 66)
    print("scripts/test_wiki_sync.py 自身冒烟测试")
    print("=" * 66)

    all_fails: list[str] = []

    print("\n--- status ---")
    all_fails.extend(test_status())
    print("\n--- seed + clean ---")
    all_fails.extend(test_seed_and_clean())
    print("\n--- once --dry-run ---")
    all_fails.extend(test_once_dry_run())
    print("\n--- once --dry-run 过滤 references ---")
    all_fails.extend(test_once_dry_run_filters_references())
    print("\n--- e2e --dry-run ---")
    all_fails.extend(test_e2e_dry_run())
    print("\n--- 无效 knowledge-dir ---")
    all_fails.extend(test_invalid_knowledge_dir())

    print("\n" + "=" * 66)
    if all_fails:
        print(f"RESULT: FAIL ({len(all_fails)} 项未通过)")
        for f in all_fails:
            safe = f.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                sys.stdout.encoding or "utf-8", errors="replace"
            )
            print(f"  - {safe}")
        return 1
    print("RESULT: PASS — test_wiki_sync 六子命令全部可反复跑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
