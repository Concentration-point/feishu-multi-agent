"""L2 经验池 — 跨项目持久化，Agent 自进化。

ExperienceManager 负责:
- 经验卡片写入 Bitable 经验池表
- 经验双写到本地 Wiki
- 按角色+场景查询 top-K 经验
- 同类经验去重合并
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from config import (
    EXPERIENCE_TABLE_ID,
    FIELD_MAP_EXPERIENCE as FE,
    KNOWLEDGE_BASE_PATH,
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    EXPERIENCE_CONFIDENCE_THRESHOLD,
    EXPERIENCE_MAX_PER_CATEGORY,
    EXPERIENCE_TOP_K,
    safe_float as _safe_float,
    safe_int as _safe_int,
)
from feishu.bitable import BitableClient
from tools.write_wiki import (
    sanitize_name,
    mark_dirty,
    update_wiki_index,
    build_wiki_frontmatter,
    build_wiki_document,
    WIKI_WRITE_SUBDIR,
)

logger = logging.getLogger(__name__)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _lesson_fingerprint(role_id: str, category: str, lesson: str) -> str:
    role = _normalize_text(role_id).lower()
    cat = _normalize_text(category).lower()
    les = _normalize_text(lesson).lower()
    les = " ".join(les.split())
    return f"{role}::{cat}::{les}"


def _is_card_quality_ok(card: dict) -> tuple[bool, str]:
    situation = _normalize_text(card.get("situation"))
    action = _normalize_text(card.get("action"))
    outcome = _normalize_text(card.get("outcome"))
    lesson = _normalize_text(card.get("lesson"))
    category = _normalize_text(card.get("category"))
    if not category:
        return False, "missing category"
    if len(lesson) < 12:
        return False, "lesson too short"
    if len(action) < 8:
        return False, "action too short"
    if len(situation) < 8:
        return False, "situation too short"
    if len(outcome) < 4:
        return False, "outcome too short"
    return True, "ok"


def _clean_llm_json(raw: str) -> str:
    """清理 LLM 返回的 JSON：去掉 markdown 代码块包裹。"""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


class ExperienceManager:
    """经验池管理器。"""

    def __init__(self, client: BitableClient | None = None):
        self._client = client or BitableClient()
        self._table_id = EXPERIENCE_TABLE_ID

    @property
    def _table_configured(self) -> bool:
        return bool(self._table_id) and not self._table_id.startswith("tblxxx")

    # ── 写入 ──

    async def save_experience(
        self, card: dict, confidence: float, project_name: str
    ) -> str | None:
        """将经验卡片写入 Bitable 经验池表，返回 record_id。"""
        ok, reason = _is_card_quality_ok(card)
        if not ok:
            logger.info("经验卡片质量不足，跳过写入: %s", reason)
            return None

        if not self._table_configured:
            logger.info("经验池表未配置，跳过 Bitable 写入")
            return None

        roles = card.get("applicable_roles", [])
        primary_role = roles[0] if roles else card.get("role_id", "unknown")
        category = card.get("category", "未分类")

        saol_content = json.dumps({
            "situation": card.get("situation", ""),
            "action": card.get("action", ""),
            "outcome": card.get("outcome", ""),
            "lesson": card.get("lesson", ""),
            "title": card.get("title", ""),
            "source_run": card.get("source_run", ""),
            "source_stage": card.get("source_stage", ""),
            "review_status": card.get("review_status", ""),
        }, ensure_ascii=False, indent=2)

        fields = {
            FE["role"]: primary_role,
            FE["scene"]: category,
            FE["content"]: saol_content,
            FE["confidence"]: confidence,
            FE["use_count"]: 0,
            FE["source_project"]: project_name,
        }

        try:
            record_id = await self._client.create_record(self._table_id, fields)
            logger.info("经验写入 Bitable: role=%s cat=%s conf=%.2f",
                        primary_role, category, confidence)
            return record_id
        except Exception as e:
            logger.warning("经验写入 Bitable 失败: %s", e)
            return None

    async def save_to_wiki(self, card: dict, confidence: float = 0.0) -> str | None:
        """将经验卡片写入本地 Wiki .md 文件，并标记 dirty 供后台同步。

        复用 tools/write_wiki.py 的共享函数，保证 frontmatter 和 dirty schema 一致。
        """
        raw_category = card.get("category", "未分类")
        safe_category = sanitize_name(raw_category)
        roles = card.get("applicable_roles", [])
        primary_role = sanitize_name(roles[0] if roles else "unknown", 20)
        lesson = _normalize_text(card.get("lesson", ""))
        title = _normalize_text(card.get("title"))
        if not title:
            title = f"{raw_category} - {primary_role} - {lesson[:18]}"
        safe_title = sanitize_name(title[:48], 48)
        filename = safe_title

        base_path = Path(KNOWLEDGE_BASE_PATH)
        inbox_dir = base_path / WIKI_WRITE_SUBDIR / safe_category
        inbox_dir.mkdir(parents=True, exist_ok=True)

        ok, reason = _is_card_quality_ok(card)
        if not ok:
            logger.info("经验卡片质量不足，跳过 Wiki 写入: %s", reason)
            return None

        trace_lines = []
        if card.get("source_project"):
            trace_lines.append(f"- 来源项目：{card.get('source_project')}")
        if card.get("source_run"):
            trace_lines.append(f"- 来源运行：{card.get('source_run')}")
        if card.get("source_stage"):
            trace_lines.append(f"- 来源阶段：{card.get('source_stage')}")
        if card.get("review_status"):
            trace_lines.append(f"- 人审状态：{card.get('review_status')}")
        trace_block = "\n".join(trace_lines) if trace_lines else "- 来源：未记录"

        body = (
            f"## 溯源\n{trace_block}\n\n"
            f"## 场景\n{card.get('situation', '')}\n\n"
            f"## 策略\n{card.get('action', '')}\n\n"
            f"## 结果\n{card.get('outcome', '')}\n\n"
            f"## 经验教训\n{card.get('lesson', '')}\n"
        )
        file_content = build_wiki_document(
            title=title[:48] or filename,
            content=body,
            category=raw_category,
            role=", ".join(roles) if roles else primary_role,
            confidence=confidence,
        )

        target_file = inbox_dir / f"{filename}.md"
        target_file.write_text(file_content, encoding="utf-8")

        rel_path = f"{WIKI_WRITE_SUBDIR}/{safe_category}/{filename}.md"
        mark_dirty(base_path, rel_path)

        logger.info("经验写入收件箱: %s", rel_path)
        return rel_path

    # ── 查询 ──

    async def query_top_k(
        self, role_id: str, category: str | None = None, k: int | None = None
    ) -> list[dict]:
        """查询 top-K 经验卡片。

        - 过滤 confidence >= 阈值
        - 按 confidence × (1 + log(use_count+1)) 降序
        - 命中的经验使用次数 +1
        """
        if not self._table_configured:
            return []

        k = k or EXPERIENCE_TOP_K

        filter_parts = [f'CurrentValue.[{FE["role"]}]="{role_id}"']
        if category:
            filter_parts.append(f'CurrentValue.[{FE["scene"]}]="{category}"')

        filter_expr = (
            f'AND({",".join(filter_parts)})' if len(filter_parts) > 1
            else filter_parts[0]
        )

        try:
            records = await self._client.list_records(self._table_id, filter_expr)
        except Exception as e:
            logger.warning("查询经验池失败: %s", e)
            return []

        # 过滤置信度 >= 阈值（同时排除已合并的废弃记录）
        filtered = []
        for r in records:
            conf = _safe_float(r["fields"].get(FE["confidence"], 0))
            if conf >= EXPERIENCE_CONFIDENCE_THRESHOLD:
                r["_confidence"] = conf
                r["_use_count"] = _safe_int(r["fields"].get(FE["use_count"], 0))
                filtered.append(r)

        # 排序
        for r in filtered:
            r["_score"] = r["_confidence"] * (1 + math.log(r["_use_count"] + 1))
        filtered.sort(key=lambda x: x["_score"], reverse=True)

        top_k = filtered[:k]

        # 更新使用次数 +1
        for r in top_k:
            try:
                await self._client.update_record(
                    self._table_id, r["record_id"],
                    {FE["use_count"]: r["_use_count"] + 1},
                )
            except Exception:
                pass

        # 解析返回
        results = []
        for r in top_k:
            content_raw = r["fields"].get(FE["content"], "")
            try:
                saol = json.loads(content_raw)
            except (json.JSONDecodeError, TypeError):
                saol = {"lesson": content_raw}
            results.append({
                "record_id": r["record_id"],
                "role": r["fields"].get(FE["role"], ""),
                "category": r["fields"].get(FE["scene"], ""),
                "confidence": r["_confidence"],
                "use_count": r["_use_count"],
                **saol,
            })

        logger.info("query_top_k role=%s cat=%s found=%d", role_id, category, len(results))
        return results

    # ── 去重合并 ──

    async def check_dedup(self, role_id: str, category: str, lesson: str | None = None) -> list[dict]:
        """查询同角色+同分类的有效经验（排除已合并的废弃记录）。

        若提供 lesson，则优先按 lesson 指纹做精确去重候选筛选。
        """
        if not self._table_configured:
            return []

        filter_expr = (
            f'AND(CurrentValue.[{FE["role"]}]="{role_id}",'
            f'CurrentValue.[{FE["scene"]}]="{category}")'
        )
        try:
            records = await self._client.list_records(self._table_id, filter_expr)
            valid_records = [
                r for r in records
                if _safe_float(r["fields"].get(FE["confidence"], 0)) > 0
            ]
            if not lesson:
                return valid_records

            target_fp = _lesson_fingerprint(role_id, category, lesson)
            exact_matches: list[dict] = []
            for r in valid_records:
                content_raw = r["fields"].get(FE["content"], "")
                try:
                    payload = json.loads(content_raw)
                except (json.JSONDecodeError, TypeError):
                    payload = {"lesson": content_raw}
                existing_fp = _lesson_fingerprint(role_id, category, payload.get("lesson", ""))
                if existing_fp == target_fp:
                    exact_matches.append(r)
            return exact_matches or valid_records
        except Exception as e:
            logger.warning("去重检查失败: %s", e)
            return []

    async def merge_experiences(
        self, existing: list[dict], new_card: dict
    ) -> dict | None:
        """合并多条同类经验为一条精炼版。真删除旧记录。"""
        existing_texts = []
        for r in existing:
            content_raw = r["fields"].get(FE["content"], "")
            existing_texts.append(content_raw)

        prompt = (
            "以下是同一角色在同一场景下积累的多条经验。请合并为一条最精炼、最实用的经验。\n"
            "保留最具体的建议，去掉重复内容。输出同样的 JSON 格式。\n\n"
            "已有经验：\n"
        )
        for i, text in enumerate(existing_texts, 1):
            prompt += f"\n{i}. {text}\n"

        prompt += f"\n新增经验：\n{json.dumps(new_card, ensure_ascii=False)}\n"
        prompt += "\n只输出合并后的 JSON，不要其他文字、不要 markdown 代码块。"

        try:
            llm = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES)
            resp = await llm.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content or ""
            cleaned = _clean_llm_json(raw)
            merged = json.loads(cleaned)
            ok, reason = _is_card_quality_ok(merged)
            if not ok:
                logger.warning("合并后经验质量不足，放弃合并结果: %s", reason)
                return None

            # 置信度取已有最高值
            max_conf = max(
                (_safe_float(r["fields"].get(FE["confidence"], 0)) for r in existing),
                default=0.0,
            )
            merged["_merged_confidence"] = max_conf

            # 真删除旧记录
            for r in existing:
                try:
                    await self._client.delete_record(
                        self._table_id, r["record_id"]
                    )
                except Exception as e:
                    logger.warning("删除旧经验 %s 失败: %s", r["record_id"], e)

            return merged
        except Exception as e:
            logger.warning("经验合并失败: %s", e)
            return None

