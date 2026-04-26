"""工具: 查询跨项目业务数据统计，供数据分析师生成运营报告。

从项目主表、内容排期表、经验池表三张多维表格中拉取全量数据，
按多维度聚合后返回结构化统计结果。
"""

import json
import logging
from collections import Counter

from tools import AgentContext
from config import (
    PROJECT_TABLE_ID,
    CONTENT_TABLE_ID,
    EXPERIENCE_TABLE_ID,
    FIELD_MAP_PROJECT as FP,
    FIELD_MAP_CONTENT as FC,
    FIELD_MAP_EXPERIENCE as FE,
    safe_float as _safe_float,
    safe_int as _safe_int,
)
from feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_project_stats",
        "description": (
            "查询多维表格中的跨项目业务数据，返回项目、内容、经验池的汇总统计。"
            "用于生成运营周报、数据洞察或决策建议。"
            "scope 参数可选 all/projects/content/experience，默认 all。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["all", "projects", "content", "experience"],
                    "description": (
                        "查询范围。all=全部三张表汇总（默认），"
                        "projects=仅项目主表，content=仅内容表，experience=仅经验池"
                    ),
                },
            },
        },
    },
}



async def _query_projects(client: BitableClient) -> dict:
    """项目主表多维聚合。"""
    records = await client.list_records(PROJECT_TABLE_ID)
    status_counter: Counter = Counter()
    type_counter: Counter = Counter()
    pass_rates_by_type: dict[str, list[float]] = {}
    red_flag_count = 0
    project_summaries: list[dict] = []

    for rec in records:
        f = rec["fields"]
        status = f.get(FP["status"], "未知")
        ptype = f.get(FP["project_type"], "未分类") or "未分类"
        status_counter[status] += 1
        type_counter[ptype] += 1

        rate = _safe_float(f.get(FP["review_pass_rate"], 0))
        if rate > 0:
            pass_rates_by_type.setdefault(ptype, []).append(rate)

        red_flag = f.get(FP.get("review_red_flag", ""), "")
        if red_flag and red_flag.strip():
            red_flag_count += 1

        project_summaries.append({
            "record_id": rec["record_id"],
            "client_name": f.get(FP["client_name"], ""),
            "project_type": ptype,
            "status": status,
            "review_pass_rate": rate,
            "has_red_flag": bool(red_flag and red_flag.strip()),
        })

    avg_rates = {
        k: round(sum(v) / len(v), 3) for k, v in pass_rates_by_type.items()
    }
    all_rates = [r for rates in pass_rates_by_type.values() for r in rates]
    overall_avg = round(sum(all_rates) / len(all_rates), 3) if all_rates else 0

    completed = status_counter.get("已完成", 0)
    total = len(records)

    return {
        "total": total,
        "completion_rate": round(completed / total, 3) if total else 0,
        "by_status": dict(status_counter),
        "by_type": dict(type_counter),
        "avg_review_pass_rate": overall_avg,
        "avg_review_pass_rate_by_type": avg_rates,
        "red_flag_count": red_flag_count,
        "details": project_summaries,
    }


async def _query_content(client: BitableClient) -> dict:
    """内容排期表多维聚合。"""
    records = await client.list_records(CONTENT_TABLE_ID)
    platform_counter: Counter = Counter()
    content_type_counter: Counter = Counter()
    review_status_counter: Counter = Counter()
    word_counts: list[int] = []
    has_draft_count = 0

    # 按平台统计审核状态
    platform_review: dict[str, Counter] = {}

    for rec in records:
        f = rec["fields"]
        platform = f.get(FC["platform"], "未知") or "未知"
        ctype = f.get(FC["content_type"], "未知") or "未知"
        rstatus = f.get(FC["review_status"], "") or "未审核"
        platform_counter[platform] += 1
        content_type_counter[ctype] += 1
        review_status_counter[rstatus] += 1

        platform_review.setdefault(platform, Counter())[rstatus] += 1

        wc = _safe_int(f.get(FC["word_count"], 0))
        draft = f.get(FC["draft"], "")
        if draft and str(draft).strip():
            has_draft_count += 1
        if wc > 0:
            word_counts.append(wc)

    total = len(records)
    return {
        "total": total,
        "has_draft_count": has_draft_count,
        "draft_rate": round(has_draft_count / total, 3) if total else 0,
        "by_platform": dict(platform_counter),
        "by_content_type": dict(content_type_counter),
        "by_review_status": dict(review_status_counter),
        "platform_review_detail": {
            k: dict(v) for k, v in platform_review.items()
        },
        "word_count_stats": {
            "total_words": sum(word_counts),
            "avg_words": round(sum(word_counts) / len(word_counts)) if word_counts else 0,
            "min_words": min(word_counts) if word_counts else 0,
            "max_words": max(word_counts) if word_counts else 0,
            "count_with_wordcount": len(word_counts),
        },
    }


async def _query_experience(client: BitableClient) -> dict:
    """经验池表多维聚合。"""
    records = await client.list_records(EXPERIENCE_TABLE_ID)
    role_counter: Counter = Counter()
    scene_counter: Counter = Counter()
    confidences: list[float] = []

    for rec in records:
        f = rec["fields"]
        role = f.get(FE["role"], "未知") or "未知"
        scene = f.get(FE["scene"], "未分类") or "未分类"
        role_counter[role] += 1
        scene_counter[scene] += 1

        conf = _safe_float(f.get(FE["confidence"], 0))
        if conf > 0:
            confidences.append(conf)

    return {
        "total": len(records),
        "by_role": dict(role_counter),
        "by_scene": dict(scene_counter),
        "confidence_stats": {
            "avg": round(sum(confidences) / len(confidences), 3) if confidences else 0,
            "min": round(min(confidences), 3) if confidences else 0,
            "max": round(max(confidences), 3) if confidences else 0,
        },
    }


async def execute(params: dict, context: AgentContext) -> str:
    scope = params.get("scope", "all")
    client = BitableClient()
    result: dict = {}

    if scope in ("all", "projects"):
        try:
            result["projects"] = await _query_projects(client)
        except Exception as e:
            logger.warning("查询项目主表失败: %s", e)
            result["projects"] = {"error": str(e)}

    if scope in ("all", "content"):
        try:
            result["content"] = await _query_content(client)
        except Exception as e:
            logger.warning("查询内容排期表失败: %s", e)
            result["content"] = {"error": str(e)}

    if scope in ("all", "experience"):
        try:
            result["experience"] = await _query_experience(client)
        except Exception as e:
            logger.warning("查询经验池表失败: %s", e)
            result["experience"] = {"error": str(e)}

    return json.dumps(result, ensure_ascii=False, indent=2)
