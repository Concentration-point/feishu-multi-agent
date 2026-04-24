"""多维表格 CRUD 封装。

Copywriter fan-out 场景下多个子 Agent 会并行读写 Bitable，为避免飞书 API 的
QPS 限流，模块级提供一个 asyncio.Semaphore 做全局并发闸门，所有 httpx 请求
在 _get_bitable_sem() 守护下执行。语义：同时在途的 Bitable 请求数 <=
BITABLE_CONCURRENCY_LIMIT（默认 5）。
"""

import asyncio
import logging
from typing import Any

import httpx

from config import FEISHU_BASE_URL, BITABLE_APP_TOKEN
from feishu.auth import TokenManager

logger = logging.getLogger(__name__)

# ── 全局并发闸门 ──
# asyncio.Semaphore 必须在有 running event loop 时创建，懒初始化避免
# import-time 绑定到错误 loop（测试里常为每个 case 新起 loop）。
BITABLE_CONCURRENCY_LIMIT = 5
_BITABLE_SEMAPHORE: asyncio.Semaphore | None = None


def _get_bitable_sem() -> asyncio.Semaphore:
    """Return process-wide Bitable Semaphore, creating it lazily.

    BitableClient 的所有 async 方法在发起 httpx 请求前必须 acquire 这个
    Semaphore，确保全局同时活跃请求数 <= BITABLE_CONCURRENCY_LIMIT。
    """
    global _BITABLE_SEMAPHORE
    if _BITABLE_SEMAPHORE is None:
        _BITABLE_SEMAPHORE = asyncio.Semaphore(BITABLE_CONCURRENCY_LIMIT)
    return _BITABLE_SEMAPHORE


def _reset_bitable_sem_for_test(limit: int | None = None) -> asyncio.Semaphore:
    """测试专用：重置 Semaphore 以便每个 test 在新 loop 里重新建立绑定。

    不要在生产代码里调。limit=None 使用默认 BITABLE_CONCURRENCY_LIMIT。
    """
    global _BITABLE_SEMAPHORE
    _BITABLE_SEMAPHORE = asyncio.Semaphore(
        BITABLE_CONCURRENCY_LIMIT if limit is None else limit
    )
    return _BITABLE_SEMAPHORE


class FeishuAPIError(Exception):
    """飞书 API 返回 code != 0 时抛出"""

    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"FeishuAPIError(code={code}, msg={msg})")


def rich_text_to_str(value: Any) -> str:
    """将飞书富文本字段值统一转为纯字符串。

    飞书 Bitable 文本字段可能返回:
      - 纯字符串: "内容"
      - 富文本数组: [{"type":"text","text":"内容"},...]
      - None
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for seg in value:
            if isinstance(seg, dict):
                parts.append(seg.get("text", ""))
            elif isinstance(seg, str):
                parts.append(seg)
        return "".join(parts)
    return str(value)


class BitableClient:
    """多维表格读写客户端。

    - app_token 从 config.py 读取（同一多维表格下多张表共享）
    - table_id 作为方法参数传入，支持操作不同的表
    """

    def __init__(self, token_manager: TokenManager | None = None):
        self._tm = token_manager or TokenManager()
        self._app_token = BITABLE_APP_TOKEN

    def _table_url(self, table_id: str) -> str:
        return (
            f"{FEISHU_BASE_URL}/bitable/v1"
            f"/apps/{self._app_token}/tables/{table_id}/records"
        )

    async def _headers(self) -> dict[str, str]:
        token = await self._tm.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_resp(resp: httpx.Response) -> dict:
        """解析飞书响应，统一处理 HTTP 错误和业务错误。"""
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()
            raise FeishuAPIError(-1, f"HTTP {resp.status_code}, 响应非 JSON")

        code = data.get("code", -1)
        if resp.status_code != 200 or code != 0:
            msg = data.get("msg", "unknown error")
            raise FeishuAPIError(
                code,
                f"HTTP {resp.status_code} | code={code} | {msg}",
            )
        return data

    # ── 读 ──

    async def get_record(self, table_id: str, record_id: str) -> dict:
        """读取单条记录，返回 fields 字典（富文本已转纯字符串）。"""
        url = f"{self._table_url(table_id)}/{record_id}"
        headers = await self._headers()
        async with _get_bitable_sem():
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers)

        data = self._parse_resp(resp)
        fields = data["data"]["record"]["fields"]
        logger.info("get_record table=%s record=%s OK", table_id, record_id)
        return {k: rich_text_to_str(v) for k, v in fields.items()}

    async def list_records(
        self,
        table_id: str,
        filter_expr: str | None = None,
        page_size: int = 100,
    ) -> list[dict]:
        """列出记录（自动分页），返回 [{record_id, fields}, ...]。"""
        url = self._table_url(table_id)
        headers = await self._headers()
        results: list[dict] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if filter_expr:
                params["filter"] = filter_expr
            if page_token:
                params["page_token"] = page_token

            async with _get_bitable_sem():
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, headers=headers, params=params)

            data = self._parse_resp(resp)
            items = data.get("data", {}).get("items") or []
            for item in items:
                fields = {
                    k: rich_text_to_str(v) for k, v in item["fields"].items()
                }
                results.append({
                    "record_id": item["record_id"],
                    "fields": fields,
                })

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")

        logger.info(
            "list_records table=%s filter=%s count=%d",
            table_id, filter_expr, len(results),
        )
        return results

    # ── 写 ──

    async def create_record(self, table_id: str, fields: dict) -> str:
        """创建单条记录，返回 record_id。"""
        url = self._table_url(table_id)
        headers = await self._headers()
        payload = {"fields": fields}

        async with _get_bitable_sem():
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload)

        data = self._parse_resp(resp)
        record_id = data["data"]["record"]["record_id"]
        logger.info("create_record table=%s record=%s OK", table_id, record_id)
        return record_id

    async def batch_create_records(
        self, table_id: str, records: list[dict]
    ) -> list[str]:
        """批量创建记录，返回 record_id 列表。"""
        url = f"{self._table_url(table_id)}/batch_create"
        headers = await self._headers()
        payload = {"records": [{"fields": r} for r in records]}

        async with _get_bitable_sem():
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload)

        data = self._parse_resp(resp)
        created = data["data"]["records"]
        ids = [r["record_id"] for r in created]
        logger.info(
            "batch_create_records table=%s count=%d OK", table_id, len(ids)
        )
        return ids

    async def update_record(
        self, table_id: str, record_id: str, fields: dict
    ) -> None:
        """更新单条记录的指定字段。"""
        url = f"{self._table_url(table_id)}/{record_id}"
        headers = await self._headers()
        payload = {"fields": fields}

        async with _get_bitable_sem():
            async with httpx.AsyncClient() as client:
                resp = await client.put(url, headers=headers, json=payload)

        data = self._parse_resp(resp)
        logger.info(
            "update_record table=%s record=%s OK", table_id, record_id
        )

    async def delete_record(self, table_id: str, record_id: str) -> None:
        """删除单条记录。"""
        url = f"{self._table_url(table_id)}/{record_id}"
        headers = await self._headers()

        async with _get_bitable_sem():
            async with httpx.AsyncClient() as client:
                resp = await client.request("DELETE", url, headers=headers)

        data = self._parse_resp(resp)
        logger.info(
            "delete_record table=%s record=%s OK", table_id, record_id
        )
