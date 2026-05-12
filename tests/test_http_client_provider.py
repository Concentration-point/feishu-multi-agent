"""HttpClientProvider 单元测试。

只验证 provider 自身行为（缓存 / close / 单例），不依赖飞书或外部网络。
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from infra.http_client import (
    HttpClientProvider,
    close_default_provider,
    default_provider,
    set_default_provider,
)


@pytest.mark.asyncio
async def test_get_client_returns_same_instance_for_same_key():
    provider = HttpClientProvider()
    c1 = provider.get_client("foo", timeout=5.0)
    c2 = provider.get_client("foo", timeout=5.0)

    assert c1 is c2, "同一 key 必须返回同一个 AsyncClient 实例"
    await provider.close_all()


@pytest.mark.asyncio
async def test_get_client_distinct_keys_return_different_instances():
    provider = HttpClientProvider()
    feishu = provider.get_client("feishu", timeout=10.0)
    tavily = provider.get_client("tavily", timeout=20.0)

    assert feishu is not tavily
    await provider.close_all()


@pytest.mark.asyncio
async def test_close_all_marks_clients_closed():
    provider = HttpClientProvider()
    c1 = provider.get_client("a")
    c2 = provider.get_client("b")
    assert not c1.is_closed
    assert not c2.is_closed

    await provider.close_all()

    assert c1.is_closed
    assert c2.is_closed


@pytest.mark.asyncio
async def test_close_all_clears_cache_so_next_get_returns_new_instance():
    provider = HttpClientProvider()
    c1 = provider.get_client("foo")
    await provider.close_all()
    c2 = provider.get_client("foo")

    assert c1 is not c2, "close_all 之后必须能拿到新 client，否则后续请求会用已关闭的 client"
    assert not c2.is_closed
    await provider.close_all()


@pytest.mark.asyncio
async def test_get_client_passes_timeout_and_kwargs_to_httpx():
    provider = HttpClientProvider()
    timeout = httpx.Timeout(connect=3.0, read=7.0, write=3.0, pool=2.0)
    headers = {"User-Agent": "test-agent/1.0"}
    client = provider.get_client("custom", timeout=timeout, headers=headers)

    # httpx.Timeout 会被 client.timeout 完整保留
    assert client.timeout.connect == 3.0
    assert client.timeout.read == 7.0
    # 默认 header 透传
    assert client.headers["User-Agent"] == "test-agent/1.0"
    await provider.close_all()


@pytest.mark.asyncio
async def test_close_individual_key_removes_only_that_client():
    provider = HttpClientProvider()
    a = provider.get_client("a")
    b = provider.get_client("b")

    await provider.close(key="a")

    assert a.is_closed
    assert not b.is_closed
    # 重新 get 拿到的是 b 原实例，新 get a 是新实例
    assert provider.get_client("b") is b
    new_a = provider.get_client("a")
    assert new_a is not a
    await provider.close_all()


@pytest.mark.asyncio
async def test_default_provider_returns_singleton():
    set_default_provider(None)  # reset
    p1 = default_provider()
    p2 = default_provider()
    assert p1 is p2
    await close_default_provider()


@pytest.mark.asyncio
async def test_set_default_provider_replaces_singleton():
    custom = HttpClientProvider()
    set_default_provider(custom)
    assert default_provider() is custom
    await close_default_provider()


@pytest.mark.asyncio
async def test_get_client_recreates_when_cached_client_is_closed():
    """显式 aclose() 一个 client 后，再 get_client 必须返回新实例而不是已关闭的旧实例。"""
    provider = HttpClientProvider()
    c1 = provider.get_client("foo")
    await c1.aclose()
    assert c1.is_closed

    c2 = provider.get_client("foo")
    assert c2 is not c1
    assert not c2.is_closed
    await provider.close_all()


def test_get_client_works_without_running_loop():
    """provider.get_client 是同步方法，应允许在非 async 上下文调用（CLI 启动期）。"""
    provider = HttpClientProvider()
    client = provider.get_client("sync-context")
    assert isinstance(client, httpx.AsyncClient)
    # 不 await close 而是同步清理：调用 reset_for_test 避免 ResourceWarning 的话也 OK
    # 这里关键是验证「无 running loop 时也能创建」
    # 真正关闭交给 asyncio.run
    asyncio.run(client.aclose())
