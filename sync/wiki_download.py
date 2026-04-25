"""后台 Wiki 下行同步服务 — 飞书知识空间 → 本地知识库。

与上行同步（sync/wiki_sync.py）的对称实现：
- 上行只推 07-10（Agent / 系统产出），source of truth = 本地
- 下行只拉 01-06（人类维护知识），source of truth = 飞书

目录映射规则与上行共享 WikiSyncService._LAYER_LABELS：
    飞书「企业底座」节点下的所有文档 → 本地 knowledge/01_企业底座/
    飞书「企业底座-子分类」节点下的所有文档 → knowledge/01_企业底座/子分类/
    以此类推到 06_客户档案。

.sync_state.json 为每条下行记录追加:
    remote_obj_token: 飞书文档的 obj_token
    remote_fetched_at: 最近一次下载时间
    remote_hash: 上一次下载后 markdown 的 md5（防回写 loop）
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from config import KNOWLEDGE_BASE_PATH
from feishu.wiki import FeishuAPIError, FeishuWikiClient
from feishu.wiki_markdown import blocks_to_markdown

logger = logging.getLogger(__name__)


# 只下行这些顶层（01-06，人类维护）
# 本地顶层目录 → 飞书父节点中文名
_DOWNLOAD_LAYER_LABELS: dict[str, str] = {
    "01_企业底座": "企业底座",
    "02_服务方法论": "服务方法论",
    "03_行业知识": "行业知识",
    "04_平台打法": "平台打法",
    "05_标准模板": "标准模板",
    "06_客户档案": "客户档案",
}


class WikiDownloadService:
    """下行同步服务：飞书知识空间 → 本地 knowledge/01-06/。

    - 启动时和定时拉取
    - 只对映射到 01-06 的飞书节点生效
    - 飞书侧的 title / 层级变化会自动反映到本地（删除/重命名除外 —— 本地不主动删文件）
    """

    def __init__(self, space_id: str, interval: int = 1800):
        self.space_id = space_id
        self.interval = interval
        self._wiki = FeishuWikiClient()
        self._base_path = Path(KNOWLEDGE_BASE_PATH)
        self._state_file = self._base_path / ".sync_state.json"

    # ── 对外接口 ──

    async def start(self) -> None:
        """启动无限循环的下行同步后台任务。"""
        logger.info(
            "[WikiDownload] 后台下行同步已启动，间隔 %ds，空间 %s",
            self.interval, self.space_id,
        )
        # 启动时先跑一次，保证本地是最新
        try:
            await self.download_once()
        except Exception as e:
            logger.error("[WikiDownload] 首次下行同步异常: %s", e)

        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.download_once()
            except Exception as e:
                logger.error("[WikiDownload] 下行同步异常: %s", e)

    async def trigger(self) -> dict:
        """手动触发一次下行同步。返回本次同步统计。"""
        return await self.download_once()

    async def download_once(self) -> dict:
        """执行一次下行同步扫描，返回统计信息。"""
        if not self.space_id:
            logger.info("[WikiDownload] 未配置 WIKI_SPACE_ID，跳过")
            return {"downloaded": 0, "skipped": 0, "failed": 0, "elapsed": 0.0}

        start = time.perf_counter()
        stats = {"downloaded": 0, "skipped": 0, "failed": 0}

        try:
            nodes = await self._wiki.list_nodes(self.space_id)
        except FeishuAPIError as e:
            logger.error("[WikiDownload] 获取节点列表失败: %s", e)
            return {**stats, "elapsed": round(time.perf_counter() - start, 2)}

        # 建立 node_token → node 映射用于按 parent_node_token 回溯
        node_map = {n["node_token"]: n for n in nodes}

        state = self._load_state()

        for node in nodes:
            # 只下行顶层是 01-06 对应飞书中文名的节点子孙
            local_rel_path = self._map_remote_to_local(node, node_map)
            if not local_rel_path:
                continue

            obj_type = node.get("obj_type", "")
            if obj_type != "docx":
                continue

            obj_token = node.get("obj_token", "")
            if not obj_token:
                continue

            try:
                result = await self._download_node(
                    node=node,
                    local_rel_path=local_rel_path,
                    obj_token=obj_token,
                    state=state,
                )
                stats[result] = stats.get(result, 0) + 1
            except FeishuAPIError as e:
                logger.warning(
                    "[WikiDownload] 节点 %s 下载失败: %s",
                    node.get("title", "?"), e,
                )
                stats["failed"] += 1
            except Exception as e:
                logger.warning(
                    "[WikiDownload] 节点 %s 下载异常: %s",
                    node.get("title", "?"), e,
                )
                stats["failed"] += 1

        self._save_state(state)
        elapsed = round(time.perf_counter() - start, 2)

        logger.info(
            "[WikiDownload] 下行完成: 下载 %d，跳过未变 %d，失败 %d，耗时 %.1fs",
            stats["downloaded"], stats["skipped"], stats["failed"], elapsed,
        )
        return {**stats, "elapsed": elapsed}

    # ── 核心逻辑 ──

    async def _download_node(
        self,
        *,
        node: dict,
        local_rel_path: str,
        obj_token: str,
        state: dict,
    ) -> str:
        """下载单个节点到本地。

        Returns: "downloaded" | "skipped" | "failed"
        """
        blocks = await self._wiki.get_doc_blocks(obj_token)
        md = blocks_to_markdown(blocks)

        if not md.strip():
            logger.info(
                "[WikiDownload] 节点 %s 内容为空，跳过",
                node.get("title", "?"),
            )
            return "skipped"

        content_bytes = md.encode("utf-8")
        remote_hash = hashlib.md5(content_bytes).hexdigest()

        entry = state.get(local_rel_path, {})
        if entry.get("remote_hash") == remote_hash:
            return "skipped"

        # 写本地
        full_path = self._base_path / local_rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(md, encoding="utf-8")

        # 更新 state
        entry.update({
            "hash": remote_hash,            # 下次 search_knowledge 等用
            "remote_obj_token": obj_token,
            "remote_hash": remote_hash,
            "remote_fetched_at": datetime.now(timezone.utc).isoformat(),
            "dirty": False,                 # 来自远端，不需要上行
            "direction": "down",
        })
        state[local_rel_path] = entry

        logger.info("[WikiDownload] 下载: %s → %s", node.get("title", "?"), local_rel_path)
        return "downloaded"

    def _map_remote_to_local(
        self, node: dict, node_map: dict[str, dict]
    ) -> str | None:
        """把飞书节点映射成本地相对路径（如 "02_服务方法论/brief解读.md"）。

        规则：
        - 顶层父节点 title 必须命中 01-06 反向映射
        - 二级结构（顶层 → 直接父节点 title → 当前节点 title）折成
          顶层目录/父节点title/当前title.md
        - 更深层暂时拍平到二级（罕见场景，先不处理嵌套爆炸）

        Returns: 本地相对路径，None 表示此节点不在下行范围内
        """
        # 回溯到顶层父节点
        chain: list[dict] = [node]
        current = node
        while current.get("parent_node_token"):
            parent = node_map.get(current["parent_node_token"])
            if not parent:
                break
            chain.append(parent)
            current = parent

        # chain 最后一个是根节点；倒数第二个是顶层父节点（我们关心的那个）
        if len(chain) < 2:
            return None

        # 顶层父节点（可能是「企业底座」「企业底座-子分类」）
        top_parent_title = chain[-2].get("title", "")

        # 命中白名单
        local_top, sub_segment = self._resolve_top_and_sub(top_parent_title)
        if not local_top:
            return None

        # 当前节点是 chain[0]，是要下载的 docx
        doc_title = node.get("title", "").strip()
        if not doc_title:
            return None

        # 文件名用 title 本身，去掉 Windows 非法字符
        safe_name = _sanitize_filename(doc_title)

        if sub_segment:
            # 顶层 title 本身是 "label-sub" 复合命名，sub 直接当子目录
            rel = f"{local_top}/{sub_segment}/{safe_name}.md"
        elif len(chain) >= 4:
            # chain = [当前节点(docx), 中间目录节点, 顶层label节点, 根]
            # chain[-3] 才是真正的中间目录（不是当前节点自己）
            mid_title = chain[-3].get("title", "").strip()
            if mid_title and mid_title != top_parent_title:
                mid = _sanitize_filename(mid_title)
                rel = f"{local_top}/{mid}/{safe_name}.md"
            else:
                rel = f"{local_top}/{safe_name}.md"
        else:
            # chain == [当前节点(docx), 顶层label节点, 根]
            # 当前节点直接挂在 label 下，无子目录
            rel = f"{local_top}/{safe_name}.md"

        return rel

    def _resolve_top_and_sub(self, parent_title: str) -> tuple[str | None, str | None]:
        """把顶层父节点 title 解析成 (本地顶层目录, 子分类段)。

        规则：
        - 「企业底座」 → ("01_企业底座", None)
        - 「企业底座-brief_sop」 → ("01_企业底座", "brief_sop")
        - 其它 → (None, None)
        """
        # 先尝试完全匹配
        for local_top, remote_label in _DOWNLOAD_LAYER_LABELS.items():
            if parent_title == remote_label:
                return local_top, None
            # 复合命名 "label-sub"
            if parent_title.startswith(f"{remote_label}-"):
                sub = parent_title[len(remote_label) + 1 :].strip()
                if sub:
                    return local_top, _sanitize_filename(sub)
        return None, None

    # ── state 读写 ──

    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: dict) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ── 辅助 ──

_FORBIDDEN_CHARS = '<>:"/\\|?*'


def _sanitize_filename(name: str) -> str:
    """清洗 Windows 非法字符 + 压缩空白。"""
    out = []
    for ch in name:
        if ch in _FORBIDDEN_CHARS or ord(ch) < 32:
            out.append("_")
        else:
            out.append(ch)
    cleaned = "".join(out).strip().strip(".")
    return cleaned or "未命名"
