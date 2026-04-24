"""工具: 抓取指定 URL 的网页正文，返回清洗后的 Markdown。

定位边界：
- 只负责【读全文】，不做搜索（搜索走 search_web）
- 只处理 HTTP/HTTPS 网页，内网/本地地址一律拒绝（SSRF 防护）
- 使用 trafilatura 抽取正文，剔除导航/广告/评论
"""

from __future__ import annotations

import logging
from ipaddress import ip_address
from urllib.parse import urlparse

import httpx

try:
    import trafilatura
except ImportError:  # noqa: F401
    trafilatura = None  # type: ignore

from config import (
    WEB_FETCH_MAX_CHARS_DEFAULT,
    WEB_FETCH_MAX_CHARS_LIMIT,
    WEB_FETCH_MAX_BYTES,
    WEB_FETCH_TIMEOUT_SECONDS,
    WEB_FETCH_USER_AGENT,
)
from tools import AgentContext

logger = logging.getLogger(__name__)


SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": (
            "抓取指定 URL 的网页正文，返回清洗后的 Markdown 格式。"
            "通常在 search_web 返回 URL 列表后，对关心的条目调用本工具读全文。"
            "不要用它做搜索（用 search_web）；不要用它读本地文件（用 read_knowledge）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "完整 HTTP(S) URL",
                },
                "max_chars": {
                    "type": "integer",
                    "default": WEB_FETCH_MAX_CHARS_DEFAULT,
                    "minimum": 500,
                    "maximum": WEB_FETCH_MAX_CHARS_LIMIT,
                    "description": (
                        f"正文最大字符数，超出截断。默认 {WEB_FETCH_MAX_CHARS_DEFAULT}，"
                        f"上限 {WEB_FETCH_MAX_CHARS_LIMIT}"
                    ),
                },
            },
            "required": ["url"],
        },
    },
}


def _is_safe_url(url: str) -> tuple[bool, str]:
    """SSRF 防护：只允许 http/https，拒绝本地/内网地址。"""
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL 解析失败: {e}"

    if parsed.scheme not in ("http", "https"):
        return False, f"协议不允许: {parsed.scheme or '(空)'}"

    host = (parsed.hostname or "").strip()
    if not host:
        return False, "URL 缺少 host"

    low = host.lower()
    if low in ("localhost", "0.0.0.0", "::", "ip6-localhost", "ip6-loopback"):
        return False, f"拒绝访问本地地址: {host}"

    # 如果 host 本身是 IP，检查是否是内网/回环/链路本地
    try:
        ip = ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f"拒绝访问内网/保留地址: {host}"
    except ValueError:
        # 是域名，交给 DNS，这里不做 DNS 解析拦截（demo 场景足够）
        pass

    return True, ""


async def execute(params: dict, context: AgentContext) -> str:
    url = (params.get("url") or "").strip()
    if not url:
        return "错误: url 不能为空"

    max_chars = int(params.get("max_chars") or WEB_FETCH_MAX_CHARS_DEFAULT)
    max_chars = max(500, min(WEB_FETCH_MAX_CHARS_LIMIT, max_chars))

    ok, reason = _is_safe_url(url)
    if not ok:
        return f"错误: {reason}"

    if trafilatura is None:
        return "错误: 缺少依赖 trafilatura。请执行 pip install trafilatura"

    # 加固：代理链路 TLS 握手偶发抽风，Transport retries=2 专治 connect 层
    transport = httpx.AsyncHTTPTransport(retries=2)
    timeout = httpx.Timeout(
        connect=10.0,
        read=WEB_FETCH_TIMEOUT_SECONDS,
        write=10.0,
        pool=5.0,
    )
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            http2=False,
            headers={"User-Agent": WEB_FETCH_USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        return f"错误: 请求超时（>{WEB_FETCH_TIMEOUT_SECONDS}s）: {url}"
    except Exception as e:
        logger.exception("web_fetch 请求异常")
        return f"错误: 请求异常 {type(e).__name__}: {e}"

    if resp.status_code >= 400:
        return f"错误: HTTP {resp.status_code}，url={url}"

    content_type = resp.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return (
            f"错误: 不支持的内容类型 content-type={content_type}；"
            "本工具仅处理 HTML 网页，PDF/图片/JSON 等请换工具"
        )

    if len(resp.content) > WEB_FETCH_MAX_BYTES:
        return f"错误: 响应体 {len(resp.content)} 字节超过上限 {WEB_FETCH_MAX_BYTES}"

    html = resp.text
    extracted = trafilatura.extract(
        html,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if not extracted:
        return (
            f"提示: 正文提取为空，可能是动态渲染页面/登录墙/反爬页。url={url}"
        )

    title = ""
    try:
        meta = trafilatura.extract_metadata(html)
        if meta and meta.title:
            title = meta.title.strip()
    except Exception:
        pass
    if not title:
        title = urlparse(url).netloc

    total = len(extracted)
    truncated = extracted[:max_chars]
    marker = ""
    if total > max_chars:
        marker = f"\n\n[已截断，完整 {total} 字符，返回前 {max_chars} 字符]"

    return (
        f"# {title}\n\n"
        f"**来源**: {url}\n\n"
        f"---\n\n"
        f"{truncated}{marker}"
    )
