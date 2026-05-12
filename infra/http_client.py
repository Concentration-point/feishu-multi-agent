"""HttpClientProvider — 按用途复用 httpx.AsyncClient 的轻量管理器。

背景:
    `feishu/bitable.py` 每次 Bitable 请求都新建一个 AsyncClient；
    `tools/search_web.py` / `tools/web_fetch.py` 也是每次工具调用都 `async with
    httpx.AsyncClient(...)`，连接池和 TLS 握手都没机会复用。

设计目标:
    1. 按 key（如 "feishu" / "tavily" / "metaso" / "web_fetch"）缓存 AsyncClient
       实例，命中即复用，避免反复建连。
    2. CLI 和 pytest 场景都可用，不强依赖 FastAPI lifespan。
    3. 进程结束 / pytest case 切换时能显式 `close_all()`，避免 ResourceWarning。
    4. 单实例 `default_provider()`，测试可注入新实例。

并发与事件循环:
    httpx.AsyncClient 内部的连接池绑定到「创建时所在的事件循环」。
    pytest 一般为每个 async case 起新的 event loop，复用前需检测：
      - client.is_closed
      - 绑定的 loop 是否还是当前 running loop
    若任意一项不满足，丢弃并重建一个新的 client。这样既保留生产环境的复用
    收益，又不会让测试用例因 loop mismatch 而炸掉。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HttpClientProvider:
    """按 key 缓存复用 httpx.AsyncClient 的进程级管理器。"""

    def __init__(self) -> None:
        # key -> (client, bound_loop) 元组；bound_loop 用来检测跨 loop 复用
        self._clients: dict[str, tuple[httpx.AsyncClient, asyncio.AbstractEventLoop | None]] = {}
        # 创建客户端时的 kwargs，便于 loop 失效时按相同参数重建
        self._kwargs: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def get_client(
        self,
        key: str,
        *,
        timeout: httpx.Timeout | float | None = None,
        **kwargs: Any,
    ) -> httpx.AsyncClient:
        """返回 key 对应的 AsyncClient，缺失或失效时按 timeout/**kwargs 创建。

        注意:
            httpx.AsyncClient 的构造是同步的，无需 await；只有发出请求时才需要
            running loop。因此这里也是同步函数，调用方可在 sync 上下文里取出
            client，再在 async 上下文里 `await client.get(...)`。

        参数:
            key: 缓存键，按用途/域名命名，如 "feishu" / "tavily" / "metaso"。
            timeout: 透传给 httpx.AsyncClient。
            **kwargs: 透传给 httpx.AsyncClient，如 transport / headers / http2。
        """
        cached = self._clients.get(key)
        running_loop = _safe_get_running_loop()
        if cached is not None:
            client, bound_loop = cached
            # 复用条件：未关闭，且 (创建时没绑定 loop) 或 (绑定 loop == 当前 loop)
            if not client.is_closed and (
                bound_loop is None
                or running_loop is None
                or bound_loop is running_loop
            ):
                return client
            # 失效则清掉，重新建一个；老 client 交给 GC（或测试主动 close_all）
            logger.debug(
                "HttpClientProvider: dropping stale client key=%s (closed=%s loop_match=%s)",
                key,
                client.is_closed,
                bound_loop is running_loop if running_loop else "no-loop",
            )
            self._clients.pop(key, None)

        # 保存 kwargs 以便后续 loop 切换后用同样参数重建
        merged_kwargs: dict[str, Any] = dict(kwargs)
        if timeout is not None:
            merged_kwargs["timeout"] = timeout
        self._kwargs[key] = merged_kwargs

        client = httpx.AsyncClient(**merged_kwargs)
        self._clients[key] = (client, running_loop)
        logger.debug("HttpClientProvider: created new client key=%s", key)
        return client

    async def close(self, key: str) -> None:
        """关闭并丢弃指定 key 的 client。不存在则静默。"""
        cached = self._clients.pop(key, None)
        if cached is None:
            return
        client, _ = cached
        if not client.is_closed:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - aclose 几乎不抛
                logger.warning("HttpClientProvider: aclose failed for key=%s", key, exc_info=True)

    async def close_all(self) -> None:
        """关闭并清空所有 client。pytest / shutdown 调用。"""
        keys = list(self._clients.keys())
        for key in keys:
            await self.close(key)

    def reset_for_test(self) -> None:
        """测试专用：丢弃所有 client（不 await close），避免跨 loop 复用。

        与 close_all 的区别：这里不会 `await aclose()`，因此可以在 sync 上下文
        （如 pytest fixture 的 tearDown）里直接调用。代价是被丢弃的 client 的
        底层连接会等 GC，引擎压力下不建议在生产里用。
        """
        self._clients.clear()
        self._kwargs.clear()


def _safe_get_running_loop() -> asyncio.AbstractEventLoop | None:
    """`asyncio.get_running_loop()` 在非 async 上下文会抛；这里吞掉返回 None。"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


# ── 进程级单例 ────────────────────────────────────────────────
_DEFAULT_PROVIDER: HttpClientProvider | None = None


def default_provider() -> HttpClientProvider:
    """进程级单例 HttpClientProvider。首次调用时懒初始化。"""
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        _DEFAULT_PROVIDER = HttpClientProvider()
    return _DEFAULT_PROVIDER


def set_default_provider(provider: HttpClientProvider | None) -> None:
    """测试专用：替换 / 清空全局 provider。生产代码不要调。"""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider


async def close_default_provider() -> None:
    """关停并清空全局 provider。FastAPI shutdown / CLI 收尾用。"""
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        return
    await _DEFAULT_PROVIDER.close_all()
    _DEFAULT_PROVIDER = None
