"""飞书知识空间 API 封装 — 节点管理 + 文档写入。"""

import asyncio
import logging
import time
from typing import Any

import httpx

from config import FEISHU_BASE_URL
from feishu.auth import TokenManager
from feishu.bitable import FeishuAPIError
from feishu.wiki_markdown import _LANGUAGE_REVERSE_MAP

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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  交付文档：结构化写入（heading / callout / table / image）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _get_root_block_id(self, document_id: str) -> str:
        """获取文档根 block_id 并清空已有子块。"""
        headers = await self._headers()
        url = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks"
        resp = await self._request_with_retry("GET", url, headers=headers, params={"page_size": 50})
        data = self._parse_resp(resp)
        all_blocks = data.get("data", {}).get("items") or []
        root_id = all_blocks[0]["block_id"] if all_blocks else document_id

        child_count = sum(
            1 for b in all_blocks
            if b.get("parent_id") == root_id and b["block_id"] != root_id
        )
        if child_count > 0:
            url_del = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks/{root_id}/children/batch_delete"
            resp = await self._request_with_retry("DELETE", url_del, headers=headers, json_body={
                "start_index": 0, "end_index": child_count,
            })
            self._parse_resp(resp)
            logger.info("delivery_doc cleared %d old blocks from doc=%s", child_count, document_id)
        return root_id

    async def _append_children(
        self, document_id: str, parent_block_id: str, children: list[dict], *, start_index: int = 0,
    ) -> list[dict]:
        """向指定父块追加子块，返回创建的块列表。"""
        if not children:
            return []
        headers = await self._headers()
        url = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks/{parent_block_id}/children"
        batch_size = 20
        created: list[dict] = []
        for i in range(0, len(children), batch_size):
            batch = children[i:i + batch_size]
            payload = {"children": batch, "index": start_index + i}
            resp = await self._request_with_retry("POST", url, headers=headers, json_body=payload)
            data = self._parse_resp(resp)
            created.extend(data.get("data", {}).get("children") or [])
        return created

    async def create_table_via_descendant(
        self,
        document_id: str,
        parent_block_id: str,
        rows: list[list[str]],
        *,
        index: int = 0,
        header_row: bool = True,
    ) -> None:
        """用 descendant API 一次性创建带内容的表格。

        Args:
            rows: 二维字符串数组，rows[0] 为表头
        """
        if not rows or not rows[0]:
            return
        row_size = len(rows)
        col_size = len(rows[0])

        # 构建 block ID
        table_id = f"tbl_{id(rows)}"
        descendants: list[dict] = []
        children_ids: list[str] = [table_id]
        cell_ids: list[str] = []

        for r_idx, row in enumerate(rows):
            for c_idx, _ in enumerate(row):
                cell_id = f"{table_id}_r{r_idx}c{c_idx}"
                cell_ids.append(cell_id)

        # table block
        descendants.append({
            "block_id": table_id,
            "block_type": 31,
            "table": {
                "property": {
                    "row_size": row_size,
                    "column_size": col_size,
                    "header_row": header_row,
                },
            },
            "children": cell_ids,
        })

        # cell blocks + text children
        cell_idx = 0
        for r_idx, row in enumerate(rows):
            for c_idx, cell_text in enumerate(row):
                cell_id = cell_ids[cell_idx]
                text_id = f"{cell_id}_t"
                descendants.append({
                    "block_id": cell_id,
                    "block_type": 32,
                    "table_cell": {},
                    "children": [text_id],
                })
                # 表头加粗
                style = {}
                text_element: dict = {"text_run": {"content": cell_text}}
                if r_idx == 0 and header_row:
                    text_element = {"text_run": {"content": cell_text, "text_element_style": {"bold": True}}}
                descendants.append({
                    "block_id": text_id,
                    "block_type": 2,
                    "text": {"elements": [text_element], "style": style},
                    "children": [],
                })
                cell_idx += 1

        headers = await self._headers()
        url = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks/{parent_block_id}/descendant"
        payload = {
            "children_id": children_ids,
            "descendants": descendants,
            "index": index,
        }
        resp = await self._request_with_retry("POST", url, headers=headers, json_body=payload)
        self._parse_resp(resp)
        logger.info("create_table doc=%s rows=%d cols=%d", document_id, row_size, col_size)

    async def upload_image_to_doc(self, document_id: str, parent_block_id: str, image_bytes: bytes, file_name: str = "chart.png", *, index: int = 0) -> None:
        """三步插入图片：创建空 Image Block → 上传素材 → 绑定。

        Args:
            document_id: 文档 ID
            parent_block_id: 图片要插入的父块 ID
            image_bytes: PNG 图片二进制内容
            file_name: 文件名
            index: 插入位置
        """
        if not image_bytes:
            return

        headers = await self._headers()

        # Step 1: 创建空 Image Block
        url_children = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks/{parent_block_id}/children"
        payload = {"children": [{"block_type": 27, "image": {}}], "index": index}
        resp = await self._request_with_retry("POST", url_children, headers=headers, json_body=payload)
        data = self._parse_resp(resp)
        created = data.get("data", {}).get("children") or []
        if not created:
            logger.warning("upload_image: 创建 Image Block 失败")
            return
        image_block_id = created[0]["block_id"]

        # Step 2: 上传素材（httpx multipart）
        token = await self._tm.get_token()
        upload_url = f"{FEISHU_BASE_URL}/drive/v1/medias/upload_all"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp_upload = await client.post(
                upload_url,
                data={
                    "file_name": file_name,
                    "parent_type": "docx_image",
                    "parent_node": image_block_id,
                    "size": str(len(image_bytes)),
                    "extra": f'{{"drive_route_token":"{document_id}"}}',
                },
                files={"file": (file_name, image_bytes, "image/png")},
                headers={"Authorization": f"Bearer {token}"},
            )
        try:
            resp_json = resp_upload.json()
        except Exception:
            logger.warning("upload_image: 上传素材响应非 JSON")
            return
        if resp_json.get("code") != 0:
            logger.warning("upload_image: 上传素材失败: %s", resp_json)
            return
        file_token = resp_json["data"]["file_token"]

        # Step 3: 绑定图片到 Block
        patch_url = f"{FEISHU_BASE_URL}/docx/v1/documents/{document_id}/blocks/{image_block_id}"
        patch_payload = {"replace_image": {"token": file_token}}
        resp = await self._request_with_retry("PATCH", patch_url, headers=headers, json_body=patch_payload)
        self._parse_resp(resp)
        logger.info("upload_image doc=%s block=%s token=%s", document_id, image_block_id, file_token)

    async def write_delivery_doc(
        self,
        document_id: str,
        blocks: list[dict],
    ) -> None:
        """写入结构化交付文档。

        每个 block 为 dict，支持以下 type：
        - {"type": "heading1", "text": "..."}  或  {"type": "heading1", "elements": [...]}
        - {"type": "heading2", "text": "..."}
        - {"type": "heading3", "text": "..."}
        - {"type": "text", "text": "...", "bold": False}  或  {"type": "text", "elements": [...]}
        - {"type": "divider"}
        - {"type": "callout", "text": "...", "emoji": "📊", "bg_color": 5}
           bg_color: 1红 2橙 3黄 4绿 5蓝 6紫 7灰
        - {"type": "bullet", "text": "..."}  或  {"type": "bullet", "elements": [...]}
        - {"type": "ordered", "text": "..."}  或  {"type": "ordered", "elements": [...]}
        - {"type": "code", "text": "...", "language": "python"}
        - {"type": "table", "rows": [["H1","H2"], ["A","B"]]}
        - {"type": "image", "data": bytes, "name": "chart.png"}
        """
        root_id = await self._get_root_block_id(document_id)

        current_index = 0
        for block in blocks:
            btype = block.get("type", "")

            if btype in ("heading1", "heading2", "heading3"):
                bt_map = {"heading1": 3, "heading2": 4, "heading3": 5}
                field_map = {"heading1": "heading1", "heading2": "heading2", "heading3": "heading3"}
                elements = block.get("elements")
                if elements is None:
                    elements = [{"text_run": {"content": block["text"]}}]
                child = {
                    "block_type": bt_map[btype],
                    field_map[btype]: {
                        "elements": elements,
                        "style": {},
                    },
                }
                await self._append_children(document_id, root_id, [child], start_index=current_index)
                current_index += 1

            elif btype == "text":
                elements = block.get("elements")
                if elements is None:
                    elements = [{"text_run": {"content": block["text"]}}]
                    if block.get("bold"):
                        elements = [{"text_run": {"content": block["text"], "text_element_style": {"bold": True}}}]
                child = {
                    "block_type": 2,
                    "text": {"elements": elements, "style": {}},
                }
                await self._append_children(document_id, root_id, [child], start_index=current_index)
                current_index += 1

            elif btype in ("bullet", "ordered"):
                bt = 12 if btype == "bullet" else 13
                field = "bullet" if btype == "bullet" else "ordered"
                elements = block.get("elements")
                if elements is None:
                    elements = [{"text_run": {"content": block["text"]}}]
                child = {
                    "block_type": bt,
                    field: {
                        "elements": elements,
                        "style": {},
                    },
                }
                await self._append_children(document_id, root_id, [child], start_index=current_index)
                current_index += 1

            elif btype == "code":
                lang = block.get("language", "plain")
                lang_code = _LANGUAGE_REVERSE_MAP.get(lang.lower(), 1)
                code_text = block.get("text", "")
                child = {
                    "block_type": 14,
                    "code": {
                        "elements": [{"text_run": {"content": code_text}}],
                        "style": {"language": lang_code, "wrap": True},
                    },
                }
                await self._append_children(document_id, root_id, [child], start_index=current_index)
                current_index += 1

            elif btype == "divider":
                child = {"block_type": 22, "divider": {}}
                await self._append_children(document_id, root_id, [child], start_index=current_index)
                current_index += 1

            elif btype == "callout":
                bg = block.get("bg_color", 5)
                border_map = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7}
                callout_child = {
                    "block_type": 19,
                    "callout": {
                        "background_color": bg,
                        "border_color": border_map.get(bg, 5),
                        "emoji_id": block.get("emoji", "bulb"),
                    },
                }
                created = await self._append_children(document_id, root_id, [callout_child], start_index=current_index)
                current_index += 1
                # 向 callout 内部添加文本
                if created and block.get("text"):
                    callout_block_id = created[0]["block_id"]
                    lines = block["text"].split("\n")
                    text_children = []
                    for line in lines:
                        if not line.strip():
                            continue
                        text_children.append({
                            "block_type": 2,
                            "text": {
                                "elements": [{"text_run": {"content": line.strip()}}],
                                "style": {},
                            },
                        })
                    if text_children:
                        await self._append_children(document_id, callout_block_id, text_children)

            elif btype == "table":
                rows = block.get("rows", [])
                if rows:
                    await self.create_table_via_descendant(
                        document_id, root_id, rows,
                        index=current_index, header_row=block.get("header_row", True),
                    )
                    current_index += 1

            elif btype == "image":
                image_data = block.get("data", b"")
                if image_data:
                    await self.upload_image_to_doc(
                        document_id, root_id, image_data,
                        file_name=block.get("name", "chart.png"),
                        index=current_index,
                    )
                    current_index += 1

            else:
                logger.warning("write_delivery_doc: 未知 block type=%s，跳过", btype)

        logger.info("write_delivery_doc doc=%s wrote %d blocks", document_id, current_index)
