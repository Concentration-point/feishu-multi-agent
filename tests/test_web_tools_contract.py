from __future__ import annotations

from tools.search_web import _clean_query, _clean_snippet
import pytest

from tools import AgentContext
from tools.web_fetch import SCHEMA as FETCH_SCHEMA
from tools.web_fetch import _DOMAIN_HITS, _check_rate_limit, _is_safe_url, _normalize_url, execute


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


@pytest.mark.asyncio
async def test_web_fetch_missing_prompt_returns_contract_error():
    result = await execute(
        {"url": "https://example.com"},
        AgentContext(record_id="rec", project_name="proj", role_id="strategist"),
    )

    assert result["ok"] is False
    assert result["error_type"] == "missing_prompt"
    assert result["retryable"] is False


def test_web_fetch_rate_limits_after_twelve_same_domain_hits():
    _DOMAIN_HITS.clear()

    for _ in range(12):
        ok, reason = _check_rate_limit("https://example.com/page")
        assert ok, reason

    ok, reason = _check_rate_limit("https://example.com/other")
    assert not ok
    assert "rate limited" in reason
    assert "example.com" in reason
