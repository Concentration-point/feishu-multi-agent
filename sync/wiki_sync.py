"""后台 Wiki 同步服务 — 本地知识库 → 飞书知识空间。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from config import KNOWLEDGE_BASE_PATH
from feishu.wiki import FeishuWikiClient, FeishuAPIError
from tools.write_wiki import prepare_docx_markdown, prepare_docx_plaintext

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# 同步方向的顶层设计
#
# 01-06：人类维护的知识库（企业底座 / 方法论 / 行业 / 平台 / 模板 / 客户档案）
#   → source of truth 在飞书，只允许 飞书 → 本地 下行，**禁止本地覆盖飞书**
#
# 07-10：Agent / 系统产出的项目档案、执行记录、复盘、经验
#   → source of truth 在本地，允许 本地 → 飞书 上行
#
# 11_待整理收件箱：Agent 自动蒸馏缓冲区，脏数据不外推
# references/：本地对标素材，search_reference 专用，不外推
# ─────────────────────────────────────────────────────────────────────

# 允许上行（本地 → 飞书）的顶层目录白名单
_DEFAULT_UPLOAD_INCLUDE_DIRS: tuple[str, ...] = (
    "07_项目档案",
    "08_项目执行记录",
    "09_项目复盘",
    "10_经验沉淀",
)


def _load_upload_include_dirs() -> tuple[str, ...]:
    """允许上行同步的顶层目录白名单。

    默认只同步 Agent / 系统产出（07-10）。可通过 WIKI_SYNC_UPLOAD_DIRS
    环境变量覆盖（逗号分隔）。

    历史变量 WIKI_SYNC_EXCLUDE_DIRS 仍读，用于追加排除（和白名单取交差）。
    """
    override = os.getenv("WIKI_SYNC_UPLOAD_DIRS", "").strip()
    if override:
        return tuple(part.strip() for part in override.split(",") if part.strip())
    return _DEFAULT_UPLOAD_INCLUDE_DIRS


def _load_extra_excludes() -> tuple[str, ...]:
    """向后兼容：WIKI_SYNC_EXCLUDE_DIRS 叠加到白名单之上的额外排除。"""
    override = os.getenv("WIKI_SYNC_EXCLUDE_DIRS", "").strip()
    if not override:
        return ()
    return tuple(part.strip() for part in override.split(",") if part.strip())


class WikiSyncService:
    """后台同步服务，将本地 knowledge/ 变更推送到飞书知识空间。

    - 定时扫描 .sync_state.json 中标记为 dirty 的文件
    - 在飞书知识空间中创建/更新对应文档
    - 单个文件失败不影响其他文件
    """

    def __init__(self, space_id: str, sync_interval: int = 3600):
        self.space_id = space_id
        self.sync_interval = sync_interval
        self._wiki = FeishuWikiClient()
        self._base_path = Path(KNOWLEDGE_BASE_PATH)
        self._state_file = self._base_path / ".sync_state.json"
        # 缓存: 飞书节点 title → node info
        self._parent_cache: dict[str, dict] = {}
        # 上行白名单：只有 07-10 项目档案 / 执行记录 / 复盘 / 经验沉淀 允许推到飞书
        self._upload_include_dirs: tuple[str, ...] = _load_upload_include_dirs()
        self._extra_excludes: tuple[str, ...] = _load_extra_excludes()

    def _is_excluded(self, rel_path: str) -> bool:
        """判断相对路径顶层目录是否允许上行同步（白名单模式）。

        True = 不允许上行（落在白名单外 或 命中额外排除）
        """
        first = rel_path.split("/", 1)[0]
        if first in self._extra_excludes:
            return True
        return first not in self._upload_include_dirs

    async def start(self) -> None:
        """启动无限循环的后台同步任务。"""
        logger.info("[WikiSync] 后台同步已启动，间隔 %ds", self.sync_interval)
        while True:
            try:
                await self.sync_once()
            except Exception as e:
                logger.error("[WikiSync] 同步异常: %s", e)
            await asyncio.sleep(self.sync_interval)

    async def trigger(self) -> None:
        """手动触发一次同步。"""
        await self.sync_once()

    async def sync_once(self) -> None:
        """执行一次同步扫描。"""
        if not self.space_id:
            return

        state = self._load_state()
        dirty_files = self._find_dirty_files(state)

        if not dirty_files:
            return

        start = time.perf_counter()
        synced_count = 0

        for rel_path in dirty_files:
            full_path = self._base_path / rel_path
            if not full_path.exists():
                state.pop(rel_path, None)
                continue

            entry = state.get(rel_path, {})
            try:
                mode = await self._sync_file(rel_path, full_path)
                content = full_path.read_text(encoding="utf-8")
                entry.update({
                    "hash": hashlib.md5(content.encode()).hexdigest(),
                    "dirty": False,
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                    "sync_status": "success",
                    "sync_mode": mode,
                    "last_error": "",
                    "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                })
                state[rel_path] = entry
                synced_count += 1
            except FeishuAPIError as e:
                entry.update({
                    "sync_status": "failed",
                    "last_error": str(e),
                    "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                })
                state[rel_path] = entry
                logger.warning("[WikiSync] 文件 %s 同步失败: %s", rel_path, e)
            except Exception as e:
                entry.update({
                    "sync_status": "failed",
                    "last_error": str(e),
                    "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                })
                state[rel_path] = entry
                logger.warning("[WikiSync] 文件 %s 同步异常: %s", rel_path, e)

        self._save_state(state)
        elapsed = time.perf_counter() - start
        logger.info(
            "[WikiSync] 同步完成: 更新 %d 个文件, 耗时 %.1fs",
            synced_count, elapsed,
        )

    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: dict) -> None:
        self._state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find_dirty_files(self, state: dict) -> list[str]:
        """扫描 knowledge/ 下所有 .md 文件，找出需要同步的（剔除黑名单目录）。"""
        dirty: list[str] = []

        for md_file in self._base_path.rglob("*.md"):
            if md_file.name.startswith("."):
                continue
            rel_path = md_file.relative_to(self._base_path).as_posix()

            # 黑名单过滤：收件箱 / 档案层 / references
            if self._is_excluded(rel_path):
                continue

            # 已在 state 中且标记为 dirty
            if rel_path in state and state[rel_path].get("dirty"):
                dirty.append(rel_path)
                continue

            # 不在 state 中 = 新文件
            if rel_path not in state:
                dirty.append(rel_path)
                continue

            # hash 变了
            content = md_file.read_text(encoding="utf-8")
            current_hash = hashlib.md5(content.encode()).hexdigest()
            if state[rel_path].get("hash") != current_hash:
                dirty.append(rel_path)

        return dirty

    async def _sync_file(self, rel_path: str, full_path: Path) -> str:
        """将单个文件同步到飞书知识空间。返回实际使用的同步模式。"""
        raw_content = full_path.read_text(encoding="utf-8")
        content = prepare_docx_markdown(raw_content)
        sync_mode = "markdown"
        if rel_path.startswith("10_经验沉淀/"):
            content = prepare_docx_plaintext(raw_content)
            sync_mode = "plain_safe"

        # 映射飞书节点路径
        parent_title, doc_title = self._map_node_path(rel_path)

        # 确保父节点存在
        parent_node = await self._ensure_parent_node(parent_title)
        parent_token = parent_node["node_token"]

        # 查找或创建文档节点
        existing = await self._wiki.find_node_by_title(
            self.space_id, doc_title, parent_token
        )

        if existing:
            obj_token = existing.get("obj_token", "")
            if obj_token:
                await self._wiki.update_doc_content(obj_token, content)
                logger.info("[WikiSync] 更新文档: %s → %s (%s)", rel_path, doc_title, sync_mode)
        else:
            node = await self._wiki.create_node(
                self.space_id, parent_token, doc_title
            )
            obj_token = node.get("obj_token", "")
            if obj_token:
                await self._wiki.update_doc_content(obj_token, content)
            logger.info("[WikiSync] 创建文档: %s → %s (%s)", rel_path, doc_title, sync_mode)
        return sync_mode

    # ── 飞书父节点中文名映射 ──
    #
    # 上行（本地 → 飞书）：只有白名单 _DEFAULT_UPLOAD_INCLUDE_DIRS 里的会真被推送
    # 下行（飞书 → 本地）：01-06 的映射给未来 WikiDownloadService 用，保留完整结构
    _LAYER_LABELS: dict[str, str] = {
        # 01-06 · 人类维护，source of truth 在飞书（仅用于下行映射）
        "01_企业底座": "企业底座",
        "02_服务方法论": "服务方法论",
        "03_行业知识": "行业知识",
        "04_平台打法": "平台打法",
        "05_标准模板": "标准模板",
        "06_客户档案": "客户档案",
        # 07-10 · Agent/系统产出，source of truth 在本地（真正上行目标）
        "07_项目档案": "项目档案",
        "08_项目执行记录": "项目执行记录",
        "09_项目复盘": "项目复盘",
        "10_经验沉淀": "经验沉淀",
    }

    def _map_node_path(self, rel_path: str) -> tuple[str, str]:
        """映射本地路径 → 飞书节点路径。

        Returns:
            (parent_title, doc_title)
        """
        parts = rel_path.split("/")

        if parts[0] in self._LAYER_LABELS:
            # 新分层：01_企业底座/xxx.md → 「企业底座」节点下「xxx」
            # 01_企业底座/子分类/xxx.md → 「企业底座-子分类」节点下「xxx」
            label = self._LAYER_LABELS[parts[0]]
            if len(parts) >= 3:
                parent_title = f"{label}-{parts[1]}"
            else:
                parent_title = label
            doc_title = Path(parts[-1]).stem
        else:
            parent_title = "其他"
            doc_title = Path(parts[-1]).stem

        return parent_title, doc_title

    def preview_docx_payload(self, rel_path: str) -> dict:
        """本地 dry-run：预览某个知识文件同步到 docx 前的最终内容。"""
        full_path = self._base_path / rel_path
        raw_content = full_path.read_text(encoding="utf-8")
        cleaned = prepare_docx_markdown(raw_content)
        parent_title, doc_title = self._map_node_path(rel_path)
        return {
            "rel_path": rel_path,
            "parent_title": parent_title,
            "doc_title": doc_title,
            "raw_length": len(raw_content),
            "cleaned_length": len(cleaned),
            "cleaned_markdown": cleaned,
        }

    def preview_dirty_files(self) -> list[dict]:
        """本地 dry-run：预览所有 dirty 文件同步前的 docx payload。"""
        state = self._load_state()
        dirty_files = self._find_dirty_files(state)
        return [self.preview_docx_payload(rel_path) for rel_path in dirty_files]

    async def _ensure_parent_node(self, title: str) -> dict:
        """确保父节点存在，不存在则在根节点下创建。"""
        if title in self._parent_cache:
            return self._parent_cache[title]

        node = await self._wiki.find_node_by_title(self.space_id, title)
        if node:
            self._parent_cache[title] = node
            return node

        # 获取根节点
        nodes = await self._wiki.list_nodes(self.space_id)
        root_token = ""
        if nodes:
            # 找一个没有 parent 的节点作为空间根
            for n in nodes:
                if not n.get("parent_node_token"):
                    root_token = n["node_token"]
                    break
            if not root_token:
                root_token = nodes[0].get("parent_node_token", "")

        node = await self._wiki.create_node(self.space_id, root_token, title)
        self._parent_cache[title] = node
        return node
