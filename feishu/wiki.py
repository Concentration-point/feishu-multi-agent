"""飞书知识空间 API 封装 — 节点管理 + 文档写入。"""

import asyncio
import logging
import time
from typing import Any

import httpx

from config import FEISHU_BASE_URL
from feishu.auth import TokenManager
from feishu.bitable import FeishuAPIError

logger = logging.getLogger(__name__)


class FeishuWikiClient:
    """飞书知识空间读写客户端。"""

    def __init__(self, token_manager: TokenManager | None = None):
        self._tm = token_manager or TokenManager()
        self._node_cache: dict[str, dict] = {}

    async def _headers(self) -> dict[str, str]:
        token = await self._tm.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_resp(resp: httpx.Response) -> dict:
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()
            raise FeishuAPIError(-1, f"HTTP {resp.status_code}, 响应非JSON")
        code = data.get("code", -1)
        if resp.status_code != 200 or code != 0:
            msg = data.get("msg", "unknown error")
            raise FeishuAPIError(code, f"HTTP {resp.status_code} | code={code} | {msg}")
        return data

    async def _request_with_retry(self, method: str, url: str, *, headers: dict[str, str], params: dict[str, Any] | None = None, json_body: dict | None = None) -> httpx.Response:
        delays = [1, 2, 4]
        last_exc: Exception | None = None
        for attempt, delay in enumerate([0] + delays, start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.request(method, url, headers=headers, params=params, json=json_body)
                try:
                    data = resp.json()
                    code = data.get("code", -1)
                    msg = str(data.get("msg", ""))
                    if code == 131009 or "lock contention" in msg.lower():
                        raise FeishuAPIError(code, f"HTTP {resp.status_code} | code={code} | {msg}")
                except ValueError:
                    pass
                return resp
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, FeishuAPIError) as exc:
                last_exc = exc
                retryable = True
                if isinstance(exc, FeishuAPIError) and exc.code != 131009:
                    retryable = False
                if not retryable or attempt > len(delays):
                    raise
                logger.warning("wiki request retry %s %s attempt=%d reason=%s", method, url, attempt, exc)
        if last_exc:
            raise last_exc
        raise RuntimeError("unexpected retry flow")

    async def list_nodes(
        self, space_id: str, parent_node_token: str | None = None
    ) -> list[dict]:
        """获取知识空间某层节点。

        Args:
            space_id: 空间 ID
            parent_node_token: 指定父节点 token 时列该父节点的直接子节点；
                               None 时只列空间根下的顶层节点（API 默认行为）
        """
        cache_key = f"{space_id}::{parent_node_token or '__root__'}"
        cached = self._node_cache.get(cache_key)
        if cached and time.time() < cached["expire_at"]:
            return cached["data"]

        url = f"{FEISHU_BASE_URL}/wiki/v2/spaces/{space_id}/nodes"
        headers = await self._headers()
        nodes: list[dict] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            if parent_node_token:
                params["parent_node_token"] = parent_node_token

            resp = await self._request_with_retry("GET", url, headers=headers, params=params)
            data = self._parse_resp(resp)
            items = data.get("data", {}).get("items") or []
            nodes.extend(items)

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")

        self._node_cache[cache_key] = {"data": nodes, "expire_at": time.time() + 300}
        logger.info(
            "list_nodes space=%s parent=%s count=%d",
            space_id, parent_node_token or "(root)", len(nodes),
        )
        return nodes

    def invalidate_cache(self, space_id: str) -> None:
        """清除指定空间所有 parent 分页的缓存。"""
        prefix = f"{space_id}::"
        for k in list(self._node_cache.keys()):
            if k == space_id or k.startswith(prefix):
                self._node_cache.pop(k, None)

    async def find_node_by_title(self, space_id: str, title: str, parent_token: str | None = None) -> dict | None:
        """按 title 查找节点。传入 parent_token 会直接在该父节点下查（精确 + 高效）。"""
        nodes = await self.list_nodes(space_id, parent_node_token=parent_token)
        for node in nodes:
            if node.get("title") == title:
                return node
        return None

    async def create_node(self, space_id: str, parent_node_token: str, title: str) -> dict:
        url = f"{FEISHU_BASE_URL}/wiki/v2/spaces/{space_id}/nodes"
        headers = await self._headers()
        payload = {
            "obj_type": "docx",
            "parent_node_token": parent_node_token,
            "node_type": "origin",
            "title": title,
        }

        resp = await self._request_with_retry("POST", url, headers=headers, json_body=payload)
        data = self._parse_resp(resp)
        node = data["data"]["node"]
        self.invalidate_cache(space_id)
        logger.info("create_node space=%s title=%s node_token=%s", space_id, title, node.get("node_token"))
        return node

    async def get_doc_blocks(self, document_id: str) -> list[dict]:
        url = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks"
        headers = await self._headers()
        all_blocks: list[dict] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            resp = await self._request_with_retry("GET", url, headers=headers, params=params)
            data = self._parse_resp(resp)
            items = data.get("data", {}).get("items") or []
            all_blocks.extend(items)
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")

        logger.info("get_doc_blocks doc=%s count=%d", document_id, len(all_blocks))
        return all_blocks

    async def update_doc_content(self, document_id: str, content: str) -> None:
        headers = await self._headers()
        url_blocks = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks"

        all_blocks: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            resp = await self._request_with_retry("GET", url_blocks, headers=headers, params=params)
            data = self._parse_resp(resp)
            items = data.get("data", {}).get("items") or []
            all_blocks.extend(items)
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")

        root_block_id = all_blocks[0]["block_id"] if all_blocks else document_id

        child_count = sum(
            1 for b in all_blocks
            if b.get("parent_id") == root_block_id and b["block_id"] != root_block_id
        )
        if child_count > 0:
            url_delete = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks/{root_block_id}/children/batch_delete"
            delete_payload = {"start_index": 0, "end_index": child_count}
            resp = await self._request_with_retry("DELETE", url_delete, headers=headers, json_body=delete_payload)
            self._parse_resp(resp)
            logger.info("update_doc_content doc=%s cleared %d old blocks", document_id, child_count)

        paragraphs = content.split("\n")
        children: list[dict] = []
        for para in paragraphs:
            if not para.strip():
                continue
            children.append({
                "block_type": 2,
                "text": {
                    "elements": [{"text_run": {"content": para.strip()}}],
                    "style": {},
                },
            })

        if not children:
            return

        url_children = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks/{root_block_id}/children"
        batch_size = 20
        wrote = 0
        for index in range(0, len(children), batch_size):
            batch = children[index:index + batch_size]
            payload = {"children": batch, "index": index}
            resp = await self._request_with_retry("POST", url_children, headers=headers, json_body=payload)
            self._parse_resp(resp)
            wrote += len(batch)

        logger.info("update_doc_content doc=%s wrote %d paragraphs in batches (overwrite mode)", document_id, wrote)
