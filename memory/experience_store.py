"""Chroma 向量存储 — 经验池语义检索。"""

from __future__ import annotations

import logging
from typing import Any

import chromadb

import config as _config

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "experiences"


class ExperienceVectorStore:
    """封装 Chroma PersistentClient，提供经验池的语义读写。

    document 内容为经验 lesson 全文。
    metadata 包含 role_id / category / confidence / use_count /
               source_project / created_at 等字段。
    """

    def __init__(self, path: str | None = None):
        db_path = path or _config.CHROMA_DB_PATH
        self._client = chromadb.PersistentClient(path=db_path)
        # cosine 空间：distance = 1 - cosine_similarity，与阈值比较时用 similarity = 1 - distance
        self._col = self._client.get_or_create_collection(
            _COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, id: str, document: str, metadata: dict[str, Any]) -> None:
        """写入一条经验（id 与 Bitable record_id 保持一致）。重复 id 会覆盖。"""
        clean_meta = {k: ("" if v is None else v) for k, v in metadata.items()}
        self._col.upsert(documents=[document], ids=[id], metadatas=[clean_meta])
        logger.debug("Chroma 写入经验: id=%s", id)

    def query(
        self, query_text: str, role_id: str | None = None, k: int = 5
    ) -> list[dict]:
        """语义检索，返回按相似度升序（距离越小越相似）排序的结果列表。

        每项: { id, document, metadata, distance }
        """
        total = self._col.count()
        if total == 0:
            return []

        where: dict | None = {"role_id": {"$eq": role_id}} if role_id else None

        # n_results 不能超过实际条数，否则 Chroma 会报错
        n_results = min(k, total)

        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            result = self._col.query(**kwargs)
        except Exception as exc:
            logger.warning("Chroma 查询失败: %s", exc)
            return []

        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        return [
            {
                "id": ids[i],
                "document": docs[i],
                "metadata": metas[i],
                "distance": dists[i],
            }
            for i in range(len(ids))
        ]

    def delete(self, id: str) -> None:
        """删除指定 id 的记录。"""
        self._col.delete(ids=[id])
        logger.debug("Chroma 删除经验: id=%s", id)

    def update_metadata(self, id: str, metadata: dict[str, Any]) -> None:
        """更新指定 id 的 metadata（不改变向量）。"""
        clean_meta = {k: ("" if v is None else v) for k, v in metadata.items()}
        self._col.update(ids=[id], metadatas=[clean_meta])
        logger.debug("Chroma 更新 metadata: id=%s", id)
