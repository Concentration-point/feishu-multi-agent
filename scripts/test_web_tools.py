"""Manual checks for search_web and web_fetch."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools import AgentContext


def _h1(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def _h2(title: str) -> None:
    print(f"\n--- {title} ---")


def _kv(key: str, value) -> None:
    print(f"  {key:<26} {value}")


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _dump_tool_output(output, max_lines: int = 40) -> None:
    if not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False, indent=2)
    lines = output.splitlines()
    for line in lines[:max_lines]:
        print(f"  | {line}")
    if len(lines) > max_lines:
        print(f"  | ... ({len(lines) - max_lines} more lines)")
    print(f"  -> total {len(output)} chars / {len(lines)} lines")


def _is_error(output) -> bool:
    if isinstance(output, dict):
        return output.get("ok") is False
    return isinstance(output, str) and output.startswith("错误:")


def cmd_check(_args) -> int:
    _h1("environment check")
    from config import (
        TAVILY_API_KEY,
        TAVILY_API_URL,
        TAVILY_DEFAULT_MAX_RESULTS,
        TAVILY_TIMEOUT_SECONDS,
        WEB_FETCH_MAX_BYTES,
        WEB_FETCH_MAX_CHARS_DEFAULT,
        WEB_FETCH_MAX_CHARS_LIMIT,
        WEB_FETCH_TIMEOUT_SECONDS,
        WEB_FETCH_USER_AGENT,
    )

    _kv("TAVILY_API_KEY", "configured" if TAVILY_API_KEY else "missing")
    _kv("TAVILY_API_URL", TAVILY_API_URL)
    _kv("TAVILY_DEFAULT_MAX_RESULTS", TAVILY_DEFAULT_MAX_RESULTS)
    _kv("TAVILY_TIMEOUT_SECONDS", TAVILY_TIMEOUT_SECONDS)
    _kv("WEB_FETCH_MAX_CHARS_DEFAULT", WEB_FETCH_MAX_CHARS_DEFAULT)
    _kv("WEB_FETCH_MAX_CHARS_LIMIT", WEB_FETCH_MAX_CHARS_LIMIT)
    _kv("WEB_FETCH_MAX_BYTES", WEB_FETCH_MAX_BYTES)
    _kv("WEB_FETCH_TIMEOUT_SECONDS", WEB_FETCH_TIMEOUT_SECONDS)
    _kv("WEB_FETCH_USER_AGENT", WEB_FETCH_USER_AGENT)

    import httpx

    _ok(f"httpx {httpx.__version__}")
    try:
        import trafilatura

        _ok(f"trafilatura {getattr(trafilatura, '__version__', 'unknown')}")
    except ImportError:
        _warn("trafilatura missing; web_fetch cannot clean HTML")

    from agents.base import parse_soul
    from tools import ToolRegistry

    reg = ToolRegistry()
    for required in ("search_web", "web_fetch"):
        if required in reg.tool_names:
            _ok(f"{required} registered")
        else:
            _fail(f"{required} not registered")
            return 1

    soul_path = ROOT / "agents" / "strategist" / "soul.md"
    soul = parse_soul(soul_path.read_text(encoding="utf-8"))
    for required in ("search_web", "web_fetch"):
        if required in soul.tools:
            _ok(f"strategist can use {required}")
        else:
            _fail(f"strategist cannot use {required}")
            return 1
    return 0


def cmd_ssrf(_args) -> int:
    _h1("SSRF safety checks")
    from tools.web_fetch import _is_safe_url

    cases = [
        ("http://localhost/admin", False, "localhost"),
        ("http://LOCALHOST:8080/", False, "LOCALHOST uppercase"),
        ("http://127.0.0.1:8080", False, "127.0.0.1"),
        ("http://10.0.0.1/", False, "10.x private"),
        ("http://192.168.1.1/", False, "192.168 private"),
        ("http://172.16.0.1/", False, "172.16 private"),
        ("http://169.254.169.254/latest/meta-data/", False, "metadata link-local"),
        ("http://[::1]/", False, "IPv6 loopback"),
        ("file:///etc/passwd", False, "file scheme"),
        ("ftp://example.com/", False, "ftp scheme"),
        ("javascript:alert(1)", False, "javascript scheme"),
        ("", False, "empty URL"),
        ("https://", False, "missing host"),
        ("https://www.example.com/", True, "public https"),
        ("example.com/path?x=1", True, "scheme normalized"),
    ]

    failures = 0
    for url, expect_ok, label in cases:
        ok, reason = _is_safe_url(url)
        if ok == expect_ok:
            _ok(f"{label}: ok={ok} reason={reason!r}")
        else:
            _fail(f"{label}: ok={ok} reason={reason!r}")
            failures += 1
    return 1 if failures else 0


async def _run_search(query: str, topic: str | None, time_range: str | None, max_results: int):
    from tools.search_web import execute

    params: dict = {"query": query, "max_results": max_results}
    if topic:
        params["topic"] = topic
    if time_range:
        params["time_range"] = time_range
    ctx = AgentContext(record_id="test_rec", project_name="test_project", role_id="strategist")
    return await execute(params, ctx)


def cmd_search(args) -> int:
    _h1("search_web")
    output = asyncio.run(_run_search("", None, None, 3))
    _dump_tool_output(output, max_lines=8)
    if _is_error(output):
        _ok("empty query rejected")
    else:
        _fail("empty query not rejected")

    queries = [args.query] if args.query else [
        "2026 domestic beauty Double 11 marketing strategy",
        "Gen Z beauty consumption trend report",
    ]
    rc = 0
    for query in queries:
        _h2(f"query={query}")
        output = asyncio.run(_run_search(query, args.topic, args.time_range, args.max_results))
        _dump_tool_output(output, max_lines=50)
        if _is_error(output):
            _warn("search failed; check API key, quota, or network")
            rc = 1
        else:
            _ok("search returned structured content")
    return rc


async def _run_fetch(url: str, max_chars: int | None, prompt: str | None = None):
    from tools.web_fetch import execute

    params: dict = {
        "url": url,
        "prompt": prompt or "Extract the main facts, claims, and source details relevant to strategy research.",
    }
    if max_chars is not None:
        params["max_chars"] = max_chars
    ctx = AgentContext(record_id="test_rec", project_name="test_project", role_id="strategist")
    return await execute(params, ctx)


def cmd_fetch(args) -> int:
    _h1("web_fetch")

    output = asyncio.run(_run_fetch("", None, args.prompt))
    _dump_tool_output(output, max_lines=8)
    if _is_error(output):
        _ok("empty URL rejected")
    else:
        _fail("empty URL not rejected")

    output = asyncio.run(_run_fetch("http://127.0.0.1:8080/", None, args.prompt))
    _dump_tool_output(output, max_lines=8)
    if _is_error(output) and output.get("error_type") == "ssrf_blocked":
        _ok("SSRF blocked")
    else:
        _fail("SSRF not blocked")

    urls = [args.url] if args.url else ["https://example.com/"]
    rc = 0
    for url in urls:
        _h2(f"url={url}")
        output = asyncio.run(_run_fetch(url, args.max_chars, args.prompt))
        _dump_tool_output(output, max_lines=50)
        if _is_error(output):
            _warn("fetch failed")
            rc = 1
        else:
            _ok("fetch returned structured content")
    return rc


_URL_RE = re.compile(r"https?://[^\s)<>\"']+")
_BINARY_EXTS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp4", ".mp3", ".avi", ".mov",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
)


def _extract_first_url_from_search(search_output) -> str | None:
    if isinstance(search_output, dict):
        for item in search_output.get("results") or []:
            url = (item.get("url") or "").rstrip(".,)")
            path = url.split("?", 1)[0].split("#", 1)[0].lower()
            if url and not any(path.endswith(ext) for ext in _BINARY_EXTS):
                return url
        return None

    for match in _URL_RE.finditer(search_output):
        url = match.group(0).rstrip(".,)")
        path = url.split("?", 1)[0].split("#", 1)[0].lower()
        if not any(path.endswith(ext) for ext in _BINARY_EXTS):
            return url
    return None


def cmd_combo(args) -> int:
    _h1("combo: search_web -> web_fetch")
    query = args.query or "2026 domestic beauty Double 11 marketing strategy"
    search_out = asyncio.run(_run_search(query, args.topic, args.time_range, args.max_results))
    _dump_tool_output(search_out, max_lines=30)
    if _is_error(search_out):
        _fail("search failed")
        return 1

    first_url = _extract_first_url_from_search(search_out)
    if not first_url:
        _fail("no HTML-looking URL found")
        return 1

    prompt = args.prompt or f"Extract facts relevant to this strategy research query: {query}"
    fetch_out = asyncio.run(_run_fetch(first_url, args.max_chars, prompt))
    _dump_tool_output(fetch_out, max_lines=50)
    if _is_error(fetch_out):
        _warn("fetch failed after search")
        return 1
    _ok("search -> fetch loop complete")
    return 0


def cmd_all(args) -> int:
    rc = 0
    for fn in (cmd_check, cmd_ssrf, cmd_search, cmd_fetch, cmd_combo):
        sub_rc = fn(args)
        if sub_rc != 0:
            rc = sub_rc
            print(f"\n!!! {fn.__name__} returned non-zero; continuing !!!")
    return rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="search_web + web_fetch manual checks")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="environment and registration checks")
    sub.add_parser("ssrf", help="SSRF checks without network")

    p_search = sub.add_parser("search", help="run Tavily search")
    p_search.add_argument("--query")
    p_search.add_argument("--topic", choices=["general", "news"], default=None)
    p_search.add_argument("--time-range", dest="time_range", choices=["day", "week", "month", "year"], default=None)
    p_search.add_argument("--max-results", dest="max_results", type=int, default=5)

    p_fetch = sub.add_parser("fetch", help="run web fetch")
    p_fetch.add_argument("--url")
    p_fetch.add_argument("--max-chars", dest="max_chars", type=int, default=None)
    p_fetch.add_argument("--prompt", default=None)

    p_combo = sub.add_parser("combo", help="search top URL then fetch")
    p_combo.add_argument("--query", default=None)
    p_combo.add_argument("--topic", choices=["general", "news"], default=None)
    p_combo.add_argument("--time-range", dest="time_range", choices=["day", "week", "month", "year"], default=None)
    p_combo.add_argument("--max-results", dest="max_results", type=int, default=5)
    p_combo.add_argument("--max-chars", dest="max_chars", type=int, default=None)
    p_combo.add_argument("--prompt", default=None)

    p_all = sub.add_parser("all", help="run all checks")
    p_all.add_argument("--query", default=None)
    p_all.add_argument("--topic", choices=["general", "news"], default=None)
    p_all.add_argument("--time-range", dest="time_range", choices=["day", "week", "month", "year"], default=None)
    p_all.add_argument("--max-results", dest="max_results", type=int, default=5)
    p_all.add_argument("--url", default=None)
    p_all.add_argument("--max-chars", dest="max_chars", type=int, default=None)
    p_all.add_argument("--prompt", default=None)
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
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
