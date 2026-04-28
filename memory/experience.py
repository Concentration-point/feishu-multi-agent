"""L2 经验池 — 跨项目持久化，Agent 自进化。

ExperienceManager 负责:
- 经验卡片写入 Bitable 经验池表
- 经验双写到本地 Wiki
- 按角色+场景查询 top-K 经验
- 同类经验去重合并
"""

from __future__ import annotations

import json
import hashlib
import logging
import math
import re
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

DEDUP_SIMILARITY_THRESHOLD = 0.85
MERGED_LESSON_COMPRESS_TRIGGER = 200
MERGED_LESSON_MAX_LEN = 100


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


def _parse_experience_payload(content_raw: Any) -> dict:
    if isinstance(content_raw, dict):
        return content_raw
    try:
        payload = json.loads(content_raw or "{}")
        return payload if isinstance(payload, dict) else {"lesson": str(content_raw or "")}
    except (json.JSONDecodeError, TypeError):
        return {"lesson": str(content_raw or "")}


def _tokenize_lesson(text: str) -> set[str]:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return set()

    try:
        import jieba  # type: ignore

        tokens = {token.strip() for token in jieba.lcut(normalized) if token.strip()}
        if tokens:
            return tokens
    except Exception:
        pass

    words = set(re.findall(r"[a-z0-9]+", normalized))
    cjk_text = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    if len(cjk_text) <= 2:
        cjk_tokens = set(cjk_text)
    else:
        cjk_tokens = {cjk_text[i : i + 2] for i in range(len(cjk_text) - 1)}
    return words | cjk_tokens


def _lesson_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize_lesson(left)
    right_tokens = _tokenize_lesson(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _compress_lesson(lesson: str) -> str:
    text = re.sub(r"\s+", " ", _normalize_text(lesson))
    if len(text) <= MERGED_LESSON_COMPRESS_TRIGGER:
        return text

    sentences = [
        item.strip()
        for item in re.split(r"[。！？!?；;\n]", text)
        if item.strip()
    ]
    action_words = (
        "先", "优先", "必须", "避免", "使用", "保留", "检查", "确认", "拆分",
        "合并", "标注", "输出", "写", "做", "补", "删", "压缩",
    )
    prioritized = [
        sentence for sentence in sentences
        if any(word in sentence for word in action_words)
    ] or sentences

    selected: list[str] = []
    for sentence in prioritized:
        candidate = "；".join(selected + [sentence])
        if len(candidate) <= MERGED_LESSON_MAX_LEN:
            selected.append(sentence)
        if len("；".join(selected)) >= MERGED_LESSON_MAX_LEN:
            break

    compressed = "；".join(selected).strip()
    if not compressed:
        compressed = text
    return compressed[:MERGED_LESSON_MAX_LEN]


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

        # 按 applicable_roles 扇出写入：每个角色各写一条 Bitable 记录
        # 这样 reviewer 沉淀的经验也能被 copywriter 的 query_top_k 查到
        roles = card.get("applicable_roles", [])
        if not roles:
            roles = [card.get("role_id", "unknown")]
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

        record_ids: list[str] = []
        for role in roles:
            fields = {
                FE["role"]: role,
                FE["scene"]: category,
                FE["content"]: saol_content,
                FE["confidence"]: confidence,
                FE["use_count"]: 0,
                FE["source_project"]: project_name,
            }
            try:
                record_id = await self._client.create_record(self._table_id, fields)
                logger.info("经验写入 Bitable: role=%s cat=%s conf=%.2f",
                            role, category, confidence)
                record_ids.append(record_id)
            except Exception as e:
                logger.warning("经验写入 Bitable 失败: role=%s err=%s", role, e)

        # 保持返回类型签名 str | None，返回第一条 record_id
        return record_ids[0] if record_ids else None

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

    def _record_payload(self, record: dict) -> dict:
        return _parse_experience_payload(
            record.get("fields", {}).get(FE["content"], "")
        )

    def _record_to_card(self, record: dict, role_id: str, category: str) -> dict:
        payload = self._record_payload(record)
        payload.setdefault("category", category)
        payload.setdefault("applicable_roles", [role_id])
        return payload

    async def _list_bucket_records(self, role_id: str, category: str) -> list[dict]:
        if not self._table_configured:
            return []

        filter_expr = (
            f'AND(CurrentValue.[{FE["role"]}]="{role_id}",'
            f'CurrentValue.[{FE["scene"]}]="{category}")'
        )
        records = await self._client.list_records(self._table_id, filter_expr)
        valid_records: list[dict] = []
        for record in records:
            fields = record.get("fields", {})
            confidence = _safe_float(fields.get(FE["confidence"], 0))
            if confidence <= 0:
                continue
            record["_confidence"] = confidence
            record["_use_count"] = _safe_int(fields.get(FE["use_count"], 0))
            record["_payload"] = self._record_payload(record)
            valid_records.append(record)
        return valid_records

    def _wiki_delete_candidates_for_record(self, record: dict) -> list[Path]:
        fields = record.get("fields", {})
        payload = record.get("_payload") or self._record_payload(record)
        category = _normalize_text(fields.get(FE["scene"]) or payload.get("category") or "未分类")
        role = _normalize_text(fields.get(FE["role"]) or "unknown")
        source_role = _normalize_text(payload.get("source_stage") or role)
        lesson = _normalize_text(payload.get("lesson"))
        title = _normalize_text(payload.get("title"))
        if not title:
            title = f"{category} - {role} - {lesson[:18]}"

        base_path = Path(KNOWLEDGE_BASE_PATH).resolve()
        inbox_dir = (base_path / WIKI_WRITE_SUBDIR).resolve()
        category_dir = (inbox_dir / sanitize_name(category)).resolve()

        candidates = [
            category_dir / f"{sanitize_name(title[:48], 48)}.md",
        ]

        if lesson:
            normalized = re.sub(r"[\s\W_]+", "", lesson).lower() or lesson
            fingerprint = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:8]
            self_written_title = f"{source_role}_{lesson[:20].strip() or '经验'}_{fingerprint}"
            candidates.append(category_dir / f"{sanitize_name(self_written_title)}.md")

        if category_dir.exists() and lesson:
            for md_file in category_dir.glob("*.md"):
                if md_file.name.startswith("_"):
                    continue
                if md_file in candidates:
                    continue
                try:
                    content = md_file.read_text(encoding="utf-8")
                except OSError:
                    continue
                if lesson in content and (role in content or source_role in content):
                    candidates.append(md_file)

        safe_candidates: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_relative_to(inbox_dir) and resolved not in safe_candidates:
                safe_candidates.append(resolved)
        return safe_candidates

    def _delete_local_wiki_for_record(self, record: dict) -> int:
        base_path = Path(KNOWLEDGE_BASE_PATH).resolve()
        inbox_dir = (base_path / WIKI_WRITE_SUBDIR).resolve()
        deleted = 0
        touched_paths: list[str] = []

        for path in self._wiki_delete_candidates_for_record(record):
            if not path.exists():
                continue
            try:
                path.unlink()
                deleted += 1
                touched_paths.append(path.relative_to(base_path).as_posix())
            except OSError as exc:
                logger.warning("删除旧经验 wiki 文件失败: %s err=%s", path, exc)

        for rel_path in touched_paths:
            try:
                mark_dirty(base_path, rel_path)
            except Exception as exc:
                logger.warning("标记旧经验 wiki 删除状态失败: %s err=%s", rel_path, exc)

        if deleted and inbox_dir.exists():
            try:
                update_wiki_index(inbox_dir, url_prefix=WIKI_WRITE_SUBDIR)
                mark_dirty(base_path, f"{WIKI_WRITE_SUBDIR}/_index.md")
            except Exception as exc:
                logger.warning("更新经验 wiki 索引失败: %s", exc)

        return deleted

    async def _delete_experience_record(self, record: dict) -> bool:
        record_id = record.get("record_id", "")
        deleted_bitable = False
        if record_id:
            try:
                await self._client.delete_record(self._table_id, record_id)
                deleted_bitable = True
            except Exception as exc:
                logger.warning("删除旧经验 Bitable 记录失败: %s err=%s", record_id, exc)

        wiki_deleted = self._delete_local_wiki_for_record(record)
        logger.info(
            "删除旧经验: record=%s bitable=%s wiki_files=%d",
            record_id, deleted_bitable, wiki_deleted,
        )
        return deleted_bitable

    def _choose_duplicate_loser(self, left: dict, right: dict) -> dict:
        left_key = (
            _safe_float(left.get("_confidence", left.get("fields", {}).get(FE["confidence"], 0))),
            _safe_int(left.get("_use_count", left.get("fields", {}).get(FE["use_count"], 0))),
        )
        right_key = (
            _safe_float(right.get("_confidence", right.get("fields", {}).get(FE["confidence"], 0))),
            _safe_int(right.get("_use_count", right.get("fields", {}).get(FE["use_count"], 0))),
        )
        return left if left_key < right_key else right

    async def _deduplicate_bucket_records(self, records: list[dict]) -> dict:
        deleted_ids: set[str] = set()
        duplicate_pairs = 0
        deleted_count = 0

        for i, left in enumerate(records):
            left_id = left.get("record_id", "")
            if left_id in deleted_ids:
                continue
            left_lesson = _normalize_text((left.get("_payload") or {}).get("lesson"))
            for right in records[i + 1:]:
                right_id = right.get("record_id", "")
                if right_id in deleted_ids:
                    continue
                right_lesson = _normalize_text((right.get("_payload") or {}).get("lesson"))
                similarity = _lesson_similarity(left_lesson, right_lesson)
                if similarity <= DEDUP_SIMILARITY_THRESHOLD:
                    continue

                duplicate_pairs += 1
                loser = self._choose_duplicate_loser(left, right)
                loser_id = loser.get("record_id", "")
                if await self._delete_experience_record(loser):
                    deleted_count += 1
                    deleted_ids.add(loser_id)
                    if loser is left:
                        break

        return {
            "duplicate_pairs": duplicate_pairs,
            "dedup_deleted": deleted_count,
        }

    async def _merge_bucket_records(
        self,
        records: list[dict],
        role_id: str,
        category: str,
        project_name: str | None = None,
    ) -> list[dict]:
        experiences = []
        max_confidence = 0.0
        for record in records:
            payload = record.get("_payload") or self._record_payload(record)
            max_confidence = max(
                max_confidence,
                _safe_float(record.get("_confidence", record.get("fields", {}).get(FE["confidence"], 0))),
            )
            experiences.append({
                "record_id": record.get("record_id", ""),
                "confidence": _safe_float(record.get("_confidence", 0)),
                "use_count": _safe_int(record.get("_use_count", 0)),
                **payload,
            })

        prompt = (
            "你要优化同一个经验桶内的经验。桶定义为同一适用角色 + 同一场景分类。\n"
            "请把下面所有经验合并为 1-2 条精炼版经验，必须覆盖原有所有关键要点，"
            "删除重复和背景叙述，保留具体可执行建议。\n"
            "输出 JSON 数组，每个元素必须包含 situation、action、outcome、lesson、category、applicable_roles。"
            "lesson 如果超过 200 字，要压缩到 100 字以内。\n"
            "只输出 JSON，不要 markdown 代码块，不要解释。\n\n"
            f"适用角色: {role_id}\n场景分类: {category}\n"
            f"经验列表:\n{json.dumps(experiences, ensure_ascii=False, indent=2)}"
        )

        llm = AsyncOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )
        resp = await llm.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content or ""
        data = json.loads(_clean_llm_json(raw))
        if isinstance(data, dict):
            if isinstance(data.get("experiences"), list):
                merged_items = data["experiences"]
            else:
                merged_items = [data]
        elif isinstance(data, list):
            merged_items = data
        else:
            raise ValueError("LLM 合并结果不是 JSON 对象或数组")

        merged_cards: list[dict] = []
        for item in merged_items[:2]:
            if not isinstance(item, dict):
                continue
            card = dict(item)
            card["category"] = category
            card["applicable_roles"] = [role_id]
            card["source_project"] = project_name or card.get("source_project", "")
            card["source_stage"] = "experience_optimizer"
            card["lesson"] = _compress_lesson(card.get("lesson", ""))
            card.setdefault("title", f"{category} - {role_id} - {card.get('lesson', '')[:18]}")
            ok, reason = _is_card_quality_ok(card)
            if not ok:
                logger.warning("桶合并后经验质量不足，跳过该条: %s", reason)
                continue
            card["_merged_confidence"] = max_confidence
            merged_cards.append(card)

        if not merged_cards:
            raise ValueError("LLM 合并结果没有可写入的有效经验")
        return merged_cards

    async def optimize_bucket(
        self,
        role_id: str,
        category: str,
        project_name: str | None = None,
    ) -> dict:
        """对指定「适用角色 + 场景分类」桶做一次去重、合并和压缩。

        只处理调用方指定的桶，不做全量扫描。
        """
        summary = {
            "role_id": role_id,
            "category": category,
            "before": 0,
            "after_dedup": 0,
            "duplicate_pairs": 0,
            "dedup_deleted": 0,
            "merged_deleted": 0,
            "merged_created": 0,
        }
        if not self._table_configured:
            return summary

        try:
            records = await self._list_bucket_records(role_id, category)
        except Exception as exc:
            logger.warning("经验桶优化查询失败: role=%s cat=%s err=%s", role_id, category, exc)
            return summary

        summary["before"] = len(records)
        if len(records) < 2:
            summary["after_dedup"] = len(records)
            return summary

        dedup_summary = await self._deduplicate_bucket_records(records)
        summary.update(dedup_summary)

        records = await self._list_bucket_records(role_id, category)
        summary["after_dedup"] = len(records)

        if len(records) <= EXPERIENCE_MAX_PER_CATEGORY:
            return summary

        try:
            merged_cards = await self._merge_bucket_records(
                records, role_id, category, project_name
            )
        except Exception as exc:
            logger.warning("经验桶合并失败: role=%s cat=%s err=%s", role_id, category, exc)
            return summary

        max_confidence = max(
            (_safe_float(card.get("_merged_confidence", 0)) for card in merged_cards),
            default=0.0,
        )
        for record in records:
            if await self._delete_experience_record(record):
                summary["merged_deleted"] += 1

        for card in merged_cards:
            confidence = _safe_float(card.pop("_merged_confidence", max_confidence))
            await self.save_experience(card, confidence, project_name or "经验优化")
            await self.save_to_wiki(card, confidence)
            summary["merged_created"] += 1

        logger.info("经验桶优化完成: %s", summary)
        return summary

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
                payload = self._record_payload(r)
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
            merged["lesson"] = _compress_lesson(merged.get("lesson", ""))
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
                await self._delete_experience_record(r)

            return merged
        except Exception as e:
            logger.warning("经验合并失败: %s", e)
            return None

