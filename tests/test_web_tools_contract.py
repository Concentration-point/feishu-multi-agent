from __future__ import annotations

from tools.search_web import _clean_query, _clean_snippet
from tools.web_fetch import SCHEMA as FETCH_SCHEMA
from tools.web_fetch import _is_safe_url, _normalize_url


def test_web_fetch_schema_requires_url_and_prompt():
    params = FETCH_SCHEMA["function"]["parameters"]

    assert set(params["required"]) == {"url", "prompt"}
    assert "max_tokens" in params["properties"]
    assert params["properties"]["format"]["enum"] == ["markdown", "text", "raw_html"]


def test_normalize_url_defaults_to_https():
    normalized, err = _normalize_url("example.com/path")

    assert err is None
    assert normalized == "https://example.com/path"


def test_ssrf_blocks_local_and_private_ip_literals():
    blocked = [
        "http://localhost/admin",
        "http://127.0.0.1:8080",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "file:///etc/passwd",
    ]

    for url in blocked:
        ok, reason = _is_safe_url(url)
        assert not ok, (url, reason)


def test_search_query_cleaning_removes_wrapping_quotes_and_site_operator():
    assert _clean_query('"site:example.com 2026 beauty trends"') == "2026 beauty trends"


def test_search_snippet_is_compact_and_bounded():
    snippet = _clean_snippet("a\n\n" + "b" * 400)

    assert "\n" not in snippet
    assert len(snippet) <= 303
    assert snippet.endswith("...")
