"""tenant_access_token 管理 — 单例 + 自动刷新"""

import asyncio
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
        """向飞书请求新的 tenant_access_token，网络抖动时最多重试 3 次（指数退避）。

        - 业务错误（code != 0，如 app_id 错误）不重试，直接抛 FeishuAuthError。
        - 网络/超时/5xx 错误重试，间隔 1s → 2s → 4s。
        """
        payload = {
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET,
        }
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
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
                return

            except FeishuAuthError:
                raise  # 业务错误不重试
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    wait = 2 ** (attempt - 1)  # 1s, 2s
                    logger.warning(
                        "token 刷新失败（第%d次），%.0fs 后重试: %s", attempt, wait, exc
                    )
                    await asyncio.sleep(wait)

        raise FeishuAuthError(f"token 刷新失败（已重试3次）: {last_exc}")


class FeishuAuthError(Exception):
    """飞书鉴权错误"""
