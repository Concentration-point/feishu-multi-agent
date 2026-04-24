"""tenant_access_token 管理 — 单例 + 自动刷新"""

import time
import logging
import httpx

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BASE_URL

logger = logging.getLogger(__name__)

TOKEN_URL = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"


class TokenManager:
    """飞书 tenant_access_token 管理器（单例）。

    - 缓存 token，有效期 2h，过期前 60s 自动刷新
    - 所有飞书 API 调用共享同一个实例
    """

    _instance: "TokenManager | None" = None

    def __new__(cls) -> "TokenManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._token = ""
            cls._instance._expire_at = 0.0
        return cls._instance

    async def get_token(self) -> str:
        """获取有效的 tenant_access_token，过期前自动刷新。"""
        if self._token and time.time() < self._expire_at:
            return self._token
        await self._refresh()
        return self._token

    async def _refresh(self) -> None:
        """向飞书请求新的 tenant_access_token。"""
        payload = {
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(TOKEN_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise FeishuAuthError(
                f"获取 token 失败: code={data.get('code')}, msg={data.get('msg')}"
            )

        self._token = data["tenant_access_token"]
        expire_in = data.get("expire", 7200)
        # 提前 60s 刷新，避免边界过期
        self._expire_at = time.time() + expire_in - 60
        logger.info("tenant_access_token 已刷新，有效期 %ds", expire_in)


class FeishuAuthError(Exception):
    """飞书鉴权错误"""
