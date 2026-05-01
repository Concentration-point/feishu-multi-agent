"""禁用词预检模块（纯函数，非 Agent 工具）

设计动机
--------
文案写作前，让 LLM 自行扫描几百个禁用词命中率低且占用大量 token。
本模块把硬规则下沉到代码层，纯字符串子串匹配，绕过 LLM 不确定性。

刻意不导出 SCHEMA
-----------------
ToolRegistry._scan 仅注册同时具备 SCHEMA + execute 的模块（见 tools/__init__.py）。
本模块只导出纯函数，不会被 LLM 看到，从而隔离硬规则与 ReAct 循环。

调用者
------
tools/write_content.py 在 draft_content 写入后调用，把扫描结果合并进
内容行的「备注」字段，供审核 Agent 后续读取。
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path

from config import KNOWLEDGE_BASE_PATH

logger = logging.getLogger(__name__)


# ── 词表文件路径 ──
# 不写死绝对路径：以 KNOWLEDGE_BASE_PATH 为基（默认 "knowledge"），
# 相对路径解析以项目根目录为锚（本文件在 tools/ 下，根 = parents[1]）。
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN_RELATIVE = "02_服务方法论/广告法禁用词.md"


def _resolve_forbidden_file() -> Path:
    """解析禁用词文件的绝对路径。

    KNOWLEDGE_BASE_PATH 既可能是相对路径（默认 "knowledge"）也可能是绝对路径。
    """
    base = Path(KNOWLEDGE_BASE_PATH)
    if not base.is_absolute():
        base = _PROJECT_ROOT / base
    return base / _FORBIDDEN_RELATIVE


# ── 模块级单例缓存（按 mtime 失效）──
_CACHE_LOCK = threading.Lock()
_CACHED_WORDS: list[str] = []
_CACHED_MTIME: float | None = None
_CACHED_PATH: str | None = None


# 章节标题里出现这些关键词，则该节的 bullet 都是"正向建议"，应整节跳过。
# "允许"覆盖：允许更稳妥的表达
# "建议"覆盖：替代表达建议
# "可替代" / "替代"覆盖：可替代表达
_POSITIVE_SECTION_KEYWORDS = ("允许", "建议", "可替代", "替代表达")


def _is_positive_section(heading_text: str) -> bool:
    """判断章节标题是否属于正向建议节（应整节跳过）。"""
    return any(k in heading_text for k in _POSITIVE_SECTION_KEYWORDS)


def _parse_forbidden_file(path: Path) -> list[str]:
    """解析禁用词 Markdown 文件，提取 bullet 词条。

    解析规则：
      1. 维护一个"是否在跳过节"状态。
      2. 遇到以 `#` 开头的标题：判断是否正向节，更新状态。
      3. 遇到 `- xxx` bullet：若在禁用节内则收集，去除前缀、strip。
      4. 跳过空行与表格行（| 开头）。
    """
    if not path.exists():
        logger.warning("禁用词文件不存在: %s，预检词表为空", path)
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("禁用词文件读取失败 %s: %s", path, exc)
        return []

    skipping = False
    words: list[str] = []
    seen: set[str] = set()

    # bullet 行：以 `- ` 或 `* ` 开头，但要排除表格行 `|`
    bullet_re = re.compile(r"^\s*[-*]\s+(.+?)\s*$")

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        # 跳过表格行（避免把"高风险表达 | 建议替换"的左列误当 bullet）
        if line.lstrip().startswith("|"):
            continue
        # 标题行：判断是否进入正向跳过节
        if line.lstrip().startswith("#"):
            heading = line.lstrip("# ").strip()
            skipping = _is_positive_section(heading)
            continue
        # 段落级正向提示：如 "允许更稳妥的表达：" 这种行
        # 出现这种段落后到下一个标题前的 bullet 都属于正向建议。
        stripped = line.strip()
        if (
            stripped.endswith(("：", ":"))
            and any(k in stripped for k in _POSITIVE_SECTION_KEYWORDS)
        ):
            skipping = True
            continue
        if skipping:
            continue
        m = bullet_re.match(line)
        if not m:
            continue
        word = m.group(1).strip()
        if not word:
            continue
        # 去重
        if word in seen:
            continue
        seen.add(word)
        words.append(word)

    return words


def _load_words() -> list[str]:
    """加载禁用词表，使用 mtime + path 双重失效的单例缓存。

    切换 KNOWLEDGE_BASE_PATH（测试场景）或文件被修改时自动重载。
    """
    global _CACHED_WORDS, _CACHED_MTIME, _CACHED_PATH
    path = _resolve_forbidden_file()
    path_str = str(path)
    try:
        mtime = path.stat().st_mtime if path.exists() else None
    except OSError:
        mtime = None

    with _CACHE_LOCK:
        if (
            _CACHED_PATH == path_str
            and _CACHED_MTIME == mtime
            and _CACHED_WORDS is not None
        ):
            return _CACHED_WORDS

        if mtime is None:
            words: list[str] = []
        else:
            words = _parse_forbidden_file(path)

        _CACHED_WORDS = words
        _CACHED_MTIME = mtime
        _CACHED_PATH = path_str
        logger.info("禁用词表已加载: %d 词，来源 %s", len(words), path)
        return words


# ── 内部测试钩子 ──
def _reset_cache_for_test() -> None:
    """测试时重置缓存（不在生产代码调用）。"""
    global _CACHED_WORDS, _CACHED_MTIME, _CACHED_PATH
    with _CACHE_LOCK:
        _CACHED_WORDS = []
        _CACHED_MTIME = None
        _CACHED_PATH = None


# ── 公共 API ──
# 用于占位符替换的字符：U+0000（NUL）是文本不可能出现的字符，
# 单字符占位避免影响后续词的匹配长度。
_PLACEHOLDER = "\x00"


def scan_forbidden_words(text: str) -> list[dict]:
    """扫描文本中命中的禁用词。

    返回形如 [{"word": "最有效", "count": 2}, ...]，按 count 降序、word
    字典序兜底。无命中返回 []。

    匹配语义：
      - 子串匹配（不分词、不正则、大小写敏感）
      - 最长优先：词表按长度降序遍历，匹配位置用 NUL 占位符替换原文片段，
        避免短词重复命中已被长词覆盖的位置（如"最"与"最有效"）。
    """
    if not text:
        return []
    words = _load_words()
    if not words:
        return []

    # 长度降序，长度相同按字典序保稳定
    sorted_words = sorted(set(words), key=lambda w: (-len(w), w))

    working = text
    counts: dict[str, int] = {}

    for w in sorted_words:
        if not w:
            continue
        cnt = working.count(w)
        if cnt <= 0:
            continue
        counts[w] = cnt
        # 用同长度的占位符替换，避免短词在已匹配区间再次命中
        working = working.replace(w, _PLACEHOLDER * len(w))

    if not counts:
        return []

    # 按 count 降序、word 字典序兜底
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"word": w, "count": c} for w, c in items]


def format_preflight_result(hits: list[dict]) -> str:
    """把 scan_forbidden_words 结果格式化为人类可读字符串。

    必须以 '[预检]' 开头，便于审核 Agent 用前缀识别和去重。
    """
    if not hits:
        return "[预检] 无禁用词命中"
    parts = [f"{h['word']}（共{h['count']}次）" for h in hits]
    return "[预检] 命中禁用词：" + "、".join(parts)


# ── 自验证入口 ──
if __name__ == "__main__":
    samples = [
        "我们这款产品是最有效的，市面上顶级品质，最有效的解决方案。",
        "采用高标准配方，体验温和，适合敏感肌肤的日常护理场景。",
        "保证不过敏，治疗痘痘，根治色斑，绝对安全。",
    ]
    for i, s in enumerate(samples, 1):
        hits = scan_forbidden_words(s)
        print(f"[样例{i}] 输入: {s}")
        print(f"        scan: {hits}")
        print(f"        format: {format_preflight_result(hits)}")
        print()
