"""L1 项目记忆 — 多维表格语义化读写封装。

ProjectMemory: 项目主表一条记录的读写
ContentMemory: 内容排期表的读写
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config import (
    PROJECT_TABLE_ID,
    CONTENT_TABLE_ID,
    FIELD_MAP_PROJECT as FP,
    FIELD_MAP_CONTENT as FC,
    safe_float as _safe_float,
    safe_int as _safe_int,
)
from feishu.bitable import BitableClient


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Dataclasses
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class BriefProject:
    """项目主表一行的类型化表示。"""
    record_id: str
    client_name: str = ""
    brief: str = ""
    project_type: str = ""
    brand_tone: str = ""
    dept_style: str = ""
    status: str = ""
    brief_analysis: str = ""
    strategy: str = ""
    review_summary: str = ""
    review_pass_rate: float = 0.0
    review_threshold: float = 0.0
    review_red_flag: str = ""
    delivery: str = ""
    knowledge_ref: str = ""
    # ── 人审门禁相关字段（由 Orchestrator 写入） ──
    review_status: str = ""       # 待人审/通过/需修改/超时
    pending_meta: str = ""        # JSON 字符串: {msg_id, deadline, send_count, sent_at}
    human_feedback: str = ""      # 人类要求修改时的原话，AM 下一轮重写时读入


@dataclass
class ContentItem:
    """策略师创建内容行时传入的数据结构。"""
    seq: int
    title: str
    platform: str
    content_type: str
    key_point: str
    target_audience: str
    remark: str = ""


@dataclass
class ContentRecord:
    """从内容排期表读取的完整记录。"""
    record_id: str
    project_name: str = ""
    seq: int = 0
    title: str = ""
    platform: str = ""
    content_type: str = ""
    key_point: str = ""
    target_audience: str = ""
    draft: str = ""
    word_count: int = 0
    review_status: str = ""
    review_feedback: str = ""
    publish_date: str = ""
    remark: str = ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ProjectMemory — 项目主表
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ProjectMemory:
    """封装对项目主表一条记录的语义化读写。"""

    def __init__(self, record_id: str, client: BitableClient | None = None):
        self._record_id = record_id
        self._client = client or BitableClient()
        self._table_id = PROJECT_TABLE_ID

    async def load(self) -> BriefProject:
        """加载完整记录为 BriefProject dataclass。"""
        fields = await self._client.get_record(self._table_id, self._record_id)
        return BriefProject(
            record_id=self._record_id,
            client_name=fields.get(FP["client_name"], ""),
            brief=fields.get(FP["brief"], ""),
            project_type=fields.get(FP["project_type"], ""),
            brand_tone=fields.get(FP["brand_tone"], ""),
            dept_style=fields.get(FP["dept_style"], ""),
            status=fields.get(FP["status"], ""),
            brief_analysis=fields.get(FP["brief_analysis"], ""),
            strategy=fields.get(FP["strategy"], ""),
            review_summary=fields.get(FP["review_summary"], ""),
            review_pass_rate=_safe_float(fields.get(FP["review_pass_rate"], 0)),
            review_threshold=_safe_float(fields.get(FP.get("review_threshold", ""), 0)),
            review_red_flag=fields.get(FP.get("review_red_flag", ""), ""),
            delivery=fields.get(FP["delivery"], ""),
            knowledge_ref=fields.get(FP["knowledge_ref"], ""),
            review_status=fields.get(FP.get("review_status", ""), ""),
            pending_meta=fields.get(FP.get("pending_meta", ""), ""),
            human_feedback=fields.get(FP.get("human_feedback", ""), ""),
        )

    async def _read_field(self, key: str) -> str:
        fields = await self._client.get_record(self._table_id, self._record_id)
        return fields.get(FP[key], "")

    async def get_brief(self) -> str:
        return await self._read_field("brief")

    async def get_brand_tone(self) -> str:
        return await self._read_field("brand_tone")

    async def get_dept_style(self) -> str:
        return await self._read_field("dept_style")

    async def get_project_type(self) -> str:
        return await self._read_field("project_type")

    async def update_status(self, status: str) -> None:
        await self._client.update_record(
            self._table_id, self._record_id, {FP["status"]: status}
        )

    async def write_brief_analysis(self, content: str) -> None:
        """客户经理写 Brief 解读。"""
        await self._client.update_record(
            self._table_id, self._record_id, {FP["brief_analysis"]: content}
        )

    async def write_strategy(self, content: str) -> None:
        """策略师写策略方案。"""
        await self._client.update_record(
            self._table_id, self._record_id, {FP["strategy"]: content}
        )

    async def write_review_summary(
        self,
        content: str,
        pass_rate: float,
        threshold: float | None = None,
        red_flag: str = "",
    ) -> None:
        """审核写审核总评 + 通过率 + 阈值 + 红线风险。"""
        fields = {
            FP["review_summary"]: content,
            FP["review_pass_rate"]: pass_rate,
        }
        if "review_threshold" in FP:
            fields[FP["review_threshold"]] = threshold if threshold is not None else 0
        if "review_red_flag" in FP:
            fields[FP["review_red_flag"]] = red_flag
        await self._client.update_record(
            self._table_id,
            self._record_id,
            fields,
        )

    async def write_delivery(self, content: str) -> None:
        """项目经理写交付摘要。"""
        await self._client.update_record(
            self._table_id, self._record_id, {FP["delivery"]: content}
        )

    async def _safe_update(self, key: str, value) -> None:
        """按 FIELD_MAP_PROJECT 安全写字段：key 未映射则 skip，写失败则 warn 不抛。

        用于人审门禁相关的新字段（review_status / pending_meta / human_feedback）——
        飞书侧若尚未建列，代码也能跑通，只是不持久化。
        """
        import logging
        logger = logging.getLogger(__name__)
        field_name = FP.get(key)
        if not field_name:
            logger.debug("[ProjectMemory] 字段 %s 未映射，跳过写入", key)
            return
        try:
            await self._client.update_record(
                self._table_id, self._record_id, {field_name: value}
            )
        except Exception as exc:
            logger.warning(
                "[ProjectMemory] 写字段 %s 失败 (飞书列可能未建)：%s",
                field_name, exc,
            )

    async def write_review_status(self, status: str) -> None:
        """写人审状态：待人审/通过/需修改/超时。"""
        await self._safe_update("review_status", status)

    async def write_pending_meta(self, meta: dict) -> None:
        """写人审元数据（JSON 字符串）。"""
        import json
        await self._safe_update(
            "pending_meta",
            json.dumps(meta, ensure_ascii=False),
        )

    async def write_human_feedback(self, feedback: str) -> None:
        """写人类修改意见原话。"""
        await self._safe_update("human_feedback", feedback)

    async def write_agent_error_log(self, message: str) -> None:
        """写入 Agent 执行失败日志，供运营侧从 Bitable 感知异常。
        使用 _safe_update：飞书列未建时静默跳过，不影响主流程。
        """
        await self._safe_update("agent_error_log", message)

    async def clear_pending_state(self) -> None:
        """放行或重置时清空三个门禁字段，避免脏数据误导下次恢复。"""
        await self._safe_update("pending_meta", "")
        await self._safe_update("human_feedback", "")

    async def write_knowledge_ref(self, refs: list[str]) -> None:
        """写入知识引用列表。"""
        await self._client.update_record(
            self._table_id,
            self._record_id,
            {FP["knowledge_ref"]: "\n".join(refs)},
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ContentMemory — 内容排期表
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ContentMemory:
    """封装对内容排期表的读写操作。"""

    def __init__(self, client: BitableClient | None = None):
        self._client = client or BitableClient()
        self._table_id = CONTENT_TABLE_ID

    async def create_content_item(
        self, project_name: str, item: ContentItem
    ) -> str:
        """创建单条内容行，返回 record_id。"""
        fields = self._item_to_fields(project_name, item)
        return await self._client.create_record(self._table_id, fields)

    async def batch_create_content_items(
        self, project_name: str, items: list[ContentItem]
    ) -> list[str]:
        """批量创建内容行，返回 record_id 列表。"""
        records = [self._item_to_fields(project_name, item) for item in items]
        return await self._client.batch_create_records(self._table_id, records)

    async def list_by_project(self, project_name: str) -> list[ContentRecord]:
        """按项目名称列出所有内容行。"""
        filter_expr = (
            f'CurrentValue.[{FC["project_name"]}]="{project_name}"'
        )
        raw = await self._client.list_records(self._table_id, filter_expr)
        return [self._parse_record(r) for r in raw]

    async def write_draft(
        self, record_id: str, content: str, word_count: int
    ) -> None:
        """文案写成稿内容 + 字数。"""
        await self._client.update_record(
            self._table_id,
            record_id,
            {FC["draft"]: content, FC["word_count"]: word_count},
        )

    async def write_review(
        self, record_id: str, status: str, feedback: str
    ) -> None:
        """审核写审核状态 + 反馈。"""
        await self._client.update_record(
            self._table_id,
            record_id,
            {FC["review_status"]: status, FC["review_feedback"]: feedback},
        )

    async def write_publish_date(self, record_id: str, date: str) -> None:
        """项目经理写计划发布日期。date 格式: YYYY-MM-DD。"""
        ts_ms = _date_to_timestamp_ms(date)
        await self._client.update_record(
            self._table_id,
            record_id,
            {FC["publish_date"]: ts_ms},
        )

    # ── 内部工具 ──

    @staticmethod
    def _item_to_fields(project_name: str, item: ContentItem) -> dict:
        return {
            FC["project_name"]:    project_name,
            FC["seq"]:             item.seq,
            FC["title"]:           item.title,
            FC["platform"]:        item.platform,
            FC["content_type"]:    item.content_type,
            FC["key_point"]:       item.key_point,
            FC["target_audience"]: item.target_audience,
            FC["remark"]:          item.remark,
        }

    @staticmethod
    def _parse_record(raw: dict) -> ContentRecord:
        f = raw["fields"]
        return ContentRecord(
            record_id=raw["record_id"],
            project_name=f.get(FC["project_name"], ""),
            seq=_safe_int(f.get(FC["seq"], 0)),
            title=f.get(FC["title"], ""),
            platform=f.get(FC["platform"], ""),
            content_type=f.get(FC["content_type"], ""),
            key_point=f.get(FC["key_point"], ""),
            target_audience=f.get(FC["target_audience"], ""),
            draft=f.get(FC["draft"], ""),
            word_count=_safe_int(f.get(FC["word_count"], 0)),
            review_status=f.get(FC["review_status"], ""),
            review_feedback=f.get(FC["review_feedback"], ""),
            publish_date=_timestamp_ms_to_date(f.get(FC["publish_date"])),
            remark=f.get(FC["remark"], ""),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  工具函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _timestamp_ms_to_date(val) -> str:
    """将飞书毫秒时间戳转为 YYYY-MM-DD 字符串。"""
    if not val:
        return ""
    try:
        from datetime import datetime, timezone
        ts = int(val) / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(val)


def _date_to_timestamp_ms(date_str: str) -> int:
    """将 YYYY-MM-DD 日期字符串转为飞书日期字段所需的毫秒时间戳。"""
    from datetime import datetime, timezone
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

