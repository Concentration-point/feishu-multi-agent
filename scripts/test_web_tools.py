"""search_web + web_fetch 工具的本地手工测试脚本。

六子命令覆盖全路径，反复可跑：

    python scripts/test_web_tools.py check                     # 环境预检：key、依赖、工具注册
    python scripts/test_web_tools.py ssrf                      # SSRF 防护对抗（无需网络）
    python scripts/test_web_tools.py search                    # 跑一组 Tavily 搜索
    python scripts/test_web_tools.py search --query "2025 国货美妆 双十一 营销策略" --time-range month
    python scripts/test_web_tools.py fetch                     # 抓固定公开页
    python scripts/test_web_tools.py fetch --url https://example.com/ --max-chars 2000
    python scripts/test_web_tools.py combo                     # 端到端: search → top1 URL → fetch
    python scripts/test_web_tools.py all                       # 全套跑一遍

要求：
- 跑 search 和 combo 前先在 .env 配 TAVILY_API_KEY
- 跑 fetch 和 combo 前先 pip install trafilatura
- 跑 ssrf 和 check 无需任何网络/依赖
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows cp936 兼容：把 stdout 强制 UTF-8，避免 print 中文崩
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools import AgentContext


# ───────────────────── 输出小工具 ─────────────────────

def _h1(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def _h2(title: str) -> None:
    print(f"\n─── {title} ───")


def _kv(key: str, value) -> None:
    print(f"  {key:<26} {value}")


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _dump_tool_output(output: str, max_lines: int = 40) -> None:
    """把工具返回的字符串摘要打出来，超行截断。"""
    if not isinstance(output, str):
        print(f"  [非字符串返回] type={type(output).__name__} value={output!r}")
        return
    lines = output.splitlines()
    for line in lines[:max_lines]:
        print(f"  | {line}")
    if len(lines) > max_lines:
        print(f"  | ... (剩余 {len(lines) - max_lines} 行被截断)")
    print(f"  → 返回总长度 {len(output)} 字符 / {len(lines)} 行")


# ───────────────────── check: 环境预检 ─────────────────────

def cmd_check(_args) -> int:
    _h1("环境预检 check")

    # 1. 配置
    _h2("1. 配置项")
    try:
        from config import (
            TAVILY_API_KEY,
            TAVILY_API_URL,
            TAVILY_DEFAULT_MAX_RESULTS,
            TAVILY_TIMEOUT_SECONDS,
            WEB_FETCH_MAX_CHARS_DEFAULT,
            WEB_FETCH_MAX_CHARS_LIMIT,
            WEB_FETCH_MAX_BYTES,
            WEB_FETCH_TIMEOUT_SECONDS,
            WEB_FETCH_USER_AGENT,
        )
    except Exception as e:
        _fail(f"config 导入失败: {e}")
        return 1

    if TAVILY_API_KEY:
        masked = TAVILY_API_KEY[:6] + "***" + TAVILY_API_KEY[-4:] if len(TAVILY_API_KEY) > 12 else "***"
        _ok(f"TAVILY_API_KEY 已配置 ({masked})")
    else:
        _warn("TAVILY_API_KEY 未配置 — search / combo 子命令会被拒")

    _kv("TAVILY_API_URL", TAVILY_API_URL)
    _kv("TAVILY_DEFAULT_MAX_RESULTS", TAVILY_DEFAULT_MAX_RESULTS)
    _kv("TAVILY_TIMEOUT_SECONDS", TAVILY_TIMEOUT_SECONDS)
    _kv("WEB_FETCH_MAX_CHARS_DEFAULT", WEB_FETCH_MAX_CHARS_DEFAULT)
    _kv("WEB_FETCH_MAX_CHARS_LIMIT", WEB_FETCH_MAX_CHARS_LIMIT)
    _kv("WEB_FETCH_MAX_BYTES", f"{WEB_FETCH_MAX_BYTES} ({WEB_FETCH_MAX_BYTES // 1024 // 1024} MB)")
    _kv("WEB_FETCH_TIMEOUT_SECONDS", WEB_FETCH_TIMEOUT_SECONDS)
    _kv("WEB_FETCH_USER_AGENT", WEB_FETCH_USER_AGENT)

    # 2. 依赖
    _h2("2. 第三方依赖")
    try:
        import httpx
        _ok(f"httpx {httpx.__version__}")
    except ImportError:
        _fail("httpx 未安装")

    try:
        import trafilatura  # noqa: F401
        ver = getattr(trafilatura, "__version__", "unknown")
        _ok(f"trafilatura {ver}")
    except ImportError:
        _warn("trafilatura 未安装 — fetch / combo 会返回错误（web_fetch 有 ImportError 兜底，不会崩）")
        _warn("执行: pip install trafilatura")

    # 3. 工具注册
    _h2("3. 工具注册表")
    from tools import ToolRegistry
    reg = ToolRegistry()
    names = reg.tool_names
    _kv("注册总数", len(names))
    for required in ("search_web", "web_fetch"):
        if required in names:
            _ok(f"{required} 已注册")
        else:
            _fail(f"{required} 未注册")
            return 1

    # 4. 策略师权限
    _h2("4. 策略师 soul.md 权限")
    from agents.base import parse_soul
    soul_path = ROOT / "agents" / "strategist" / "soul.md"
    if not soul_path.exists():
        _fail(f"找不到 {soul_path}")
        return 1
    soul = parse_soul(soul_path.read_text(encoding="utf-8"))
    _kv("策略师 max_iterations", soul.max_iterations)
    _kv("工具权限", soul.tools)
    for required in ("search_web", "web_fetch"):
        if required in soul.tools:
            _ok(f"策略师已授权 {required}")
        else:
            _fail(f"策略师未授权 {required}")
            return 1

    print("\n环境预检通过")
    return 0


# ───────────────────── ssrf: 对抗用例 ─────────────────────

def cmd_ssrf(_args) -> int:
    _h1("SSRF 防护对抗 ssrf（不访问网络）")

    try:
        from tools.web_fetch import _is_safe_url
    except Exception as e:
        _fail(f"导入 _is_safe_url 失败: {e}")
        return 1

    cases = [
        # (url, expect_ok, label)
        ("http://localhost/admin",                         False, "localhost"),
        ("http://LOCALHOST:8080/",                         False, "LOCALHOST 大写"),
        ("http://127.0.0.1:8080",                          False, "127.0.0.1 IPv4 回环"),
        ("http://10.0.0.1/",                               False, "10.x 内网"),
        ("http://192.168.1.1/",                            False, "192.168 内网"),
        ("http://172.16.0.1/",                             False, "172.16 内网"),
        ("http://169.254.169.254/latest/meta-data/",       False, "AWS metadata link-local"),
        ("http://[::1]/",                                  False, "IPv6 回环"),
        ("file:///etc/passwd",                             False, "file 协议"),
        ("ftp://example.com/",                             False, "ftp 协议"),
        ("gopher://example.com/",                          False, "gopher 协议"),
        ("javascript:alert(1)",                            False, "javascript 协议"),
        ("",                                               False, "空 URL"),
        ("https://",                                       False, "缺 host"),
        ("https://www.example.com/",                       True,  "正常 https 公网"),
        ("http://example.com/path?x=1",                    True,  "正常 http 公网"),
    ]

    pass_count = 0
    fail_count = 0
    for url, expect_ok, label in cases:
        ok, reason = _is_safe_url(url)
        verdict = (ok == expect_ok)
        marker = "PASS" if verdict else "FAIL"
        print(f"  [{marker}] {label:30s} → ok={ok:<5} reason={reason!r}")
        if verdict:
            pass_count += 1
        else:
            fail_count += 1

    print(f"\nSSRF 用例: {pass_count} PASS / {fail_count} FAIL / 共 {len(cases)}")
    return 0 if fail_count == 0 else 1


# ───────────────────── search: Tavily 搜索 ─────────────────────

async def _run_search(query: str, topic: str | None, time_range: str | None, max_results: int) -> str:
    from tools.search_web import execute
    params: dict = {"query": query, "max_results": max_results}
    if topic:
        params["topic"] = topic
    if time_range:
        params["time_range"] = time_range
    ctx = AgentContext(record_id="test_rec", project_name="测试项目", role_id="strategist")
    return await execute(params, ctx)


def cmd_search(args) -> int:
    _h1(f"search_web 测试 search")

    # 边界 1：空 query
    _h2("边界 case: 空 query（不打网络，立即返回错误）")
    output = asyncio.run(_run_search("", None, None, 3))
    _dump_tool_output(output, max_lines=5)
    if output.startswith("错误:"):
        _ok("空 query 被正确拒绝")
    else:
        _fail("空 query 未拦截")

    # 正常 case
    queries = (
        [args.query] if args.query else [
            "2025 国货美妆 双十一 营销策略",
            "Z世代 美妆消费趋势 报告",
        ]
    )
    for q in queries:
        _h2(f"真实调用: query='{q}' topic={args.topic or 'general'} time_range={args.time_range or '(未指定)'} max_results={args.max_results}")
        output = asyncio.run(_run_search(q, args.topic, args.time_range, args.max_results))
        _dump_tool_output(output, max_lines=50)
        if output.startswith("错误:"):
            _warn(f"该 query 失败（可能是 key 未配/额度/限流）")
        else:
            _ok("返回非错误内容")

    return 0


# ───────────────────── fetch: 网页抓取 ─────────────────────

async def _run_fetch(url: str, max_chars: int | None) -> str:
    from tools.web_fetch import execute
    params: dict = {"url": url}
    if max_chars is not None:
        params["max_chars"] = max_chars
    ctx = AgentContext(record_id="test_rec", project_name="测试项目", role_id="strategist")
    return await execute(params, ctx)


def cmd_fetch(args) -> int:
    _h1("web_fetch 测试 fetch")

    # 边界 1：空 URL
    _h2("边界 case: 空 URL")
    output = asyncio.run(_run_fetch("", None))
    _dump_tool_output(output, max_lines=3)
    if output.startswith("错误:"):
        _ok("空 URL 被正确拒绝")
    else:
        _fail("空 URL 未拦截")

    # 边界 2：SSRF（跑一条就够了，完整对抗见 ssrf 子命令）
    _h2("边界 case: localhost（SSRF 防护）")
    output = asyncio.run(_run_fetch("http://127.0.0.1:8080/", None))
    _dump_tool_output(output, max_lines=3)
    if output.startswith("错误:") and "内网" in output or "本地" in output:
        _ok("SSRF 被正确拦截")
    else:
        _fail("SSRF 未拦截")

    # 边界 3：非 HTML content-type（example.com 本身是 html，这里用一个 JSON 端点）
    # 不强测，看情况

    # 正常 case
    urls = (
        [args.url] if args.url else [
            "https://example.com/",  # 稳定公开 HTML，最适合冒烟
        ]
    )
    for u in urls:
        _h2(f"真实抓取: url={u} max_chars={args.max_chars or '(默认)'}")
        output = asyncio.run(_run_fetch(u, args.max_chars))
        _dump_tool_output(output, max_lines=40)
        if output.startswith("错误:"):
            _warn("抓取失败，请检查 trafilatura 是否已装、URL 是否可达")
        else:
            _ok("抓取成功")

    return 0


# ───────────────────── combo: 端到端联动 ─────────────────────

_URL_RE = re.compile(r"https?://[^\s)<>\"']+")
# web_fetch 只处理 HTML，跳过明显的二进制/文档类 URL
_BINARY_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                ".zip", ".rar", ".7z", ".tar", ".gz",
                ".mp4", ".mp3", ".avi", ".mov",
                ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")


def _extract_first_url_from_search(search_output: str) -> str | None:
    """从 search_web 的 Markdown 输出里抠第一个**非二进制** URL。

    web_fetch 只处理 HTML，PDF/图片/压缩包等会被直接拒绝，combo 测试没必要
    选这些 URL — 跳过它们挑下一个 HTML 链接，测试才有意义。
    """
    for m in _URL_RE.finditer(search_output):
        url = m.group(0).rstrip(".,)")
        # 去掉 query string 再判扩展名
        path = url.split("?", 1)[0].split("#", 1)[0].lower()
        if any(path.endswith(ext) for ext in _BINARY_EXTS):
            continue
        return url
    return None


def cmd_combo(args) -> int:
    _h1("端到端联动 combo: search_web → web_fetch")

    query = args.query or "2025 国货美妆 双十一 营销策略"
    _h2(f"Step 1: search_web query='{query}'")
    search_out = asyncio.run(_run_search(query, args.topic, args.time_range, args.max_results))
    _dump_tool_output(search_out, max_lines=25)

    if search_out.startswith("错误:"):
        _fail("search_web 失败，终止联动")
        return 1

    first_url = _extract_first_url_from_search(search_out)
    if not first_url:
        _fail("未能从搜索结果抠出 URL，终止联动")
        return 1

    _h2(f"Step 2: web_fetch url={first_url}")
    fetch_out = asyncio.run(_run_fetch(first_url, args.max_chars))
    _dump_tool_output(fetch_out, max_lines=40)

    if fetch_out.startswith("错误:"):
        _warn("fetch 失败，但 search 已 pass")
        return 1

    _ok("端到端联动闭环")
    return 0


# ───────────────────── all: 全套 ─────────────────────

def cmd_all(args) -> int:
    rc = 0
    for fn in (cmd_check, cmd_ssrf, cmd_search, cmd_fetch, cmd_combo):
        sub_rc = fn(args)
        if sub_rc != 0:
            rc = sub_rc
            print(f"\n!!! {fn.__name__} 返回非零，继续跑剩余步骤 !!!")
    print("\n" + "=" * 70)
    print(f"  总体结果: {'PASS' if rc == 0 else 'FAIL'}")
    print("=" * 70)
    return rc


# ───────────────────── argparse ─────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="search_web + web_fetch 手工测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="环境预检（key/依赖/工具注册/策略师权限）")
    sub.add_parser("ssrf", help="SSRF 防护对抗（无需网络）")

    p_search = sub.add_parser("search", help="跑 Tavily 搜索")
    p_search.add_argument("--query", help="搜索词；未传则跑内置两条")
    p_search.add_argument("--topic", choices=["general", "news"], default=None)
    p_search.add_argument("--time-range", dest="time_range", choices=["day", "week", "month", "year"], default=None)
    p_search.add_argument("--max-results", dest="max_results", type=int, default=5)

    p_fetch = sub.add_parser("fetch", help="跑网页抓取")
    p_fetch.add_argument("--url", help="目标 URL；未传则抓 example.com")
    p_fetch.add_argument("--max-chars", dest="max_chars", type=int, default=None)

    p_combo = sub.add_parser("combo", help="端到端: search → 取 top1 URL → fetch")
    p_combo.add_argument("--query", default=None)
    p_combo.add_argument("--topic", choices=["general", "news"], default=None)
    p_combo.add_argument("--time-range", dest="time_range", choices=["day", "week", "month", "year"], default=None)
    p_combo.add_argument("--max-results", dest="max_results", type=int, default=5)
    p_combo.add_argument("--max-chars", dest="max_chars", type=int, default=None)

    p_all = sub.add_parser("all", help="check → ssrf → search → fetch → combo 全套")
    p_all.add_argument("--query", default=None)
    p_all.add_argument("--topic", choices=["general", "news"], default=None)
    p_all.add_argument("--time-range", dest="time_range", choices=["day", "week", "month", "year"], default=None)
    p_all.add_argument("--max-results", dest="max_results", type=int, default=5)
    p_all.add_argument("--url", default=None)
    p_all.add_argument("--max-chars", dest="max_chars", type=int, default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "check": cmd_check,
        "ssrf": cmd_ssrf,
        "search": cmd_search,
        "fetch": cmd_fetch,
        "combo": cmd_combo,
        "all": cmd_all,
    }
    fn = dispatch[args.cmd]
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
