"""全链路诊断运行脚本 — 调用真实 API，详细记录每个环节的日志和 Agent 回复。

用法:
    py -3 scripts/run_diagnostic.py [--scene 电商大促] [--record-id recXXX]

输出:
    logs/diagnostic_YYYYMMDD_HHMMSS.json  — 结构化诊断报告
    终端同时打印实时摘要
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# 强制跳过人审
os.environ["AUTO_APPROVE_HUMAN_REVIEW"] = "true"

# ── 详细日志配置 ──
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = LOG_DIR / f"diagnostic_{ts_str}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(log_file), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)
logger = logging.getLogger("diagnostic")

# ── 诊断数据收集器 ──
diag_data: dict = {
    "start_time": "",
    "end_time": "",
    "total_seconds": 0,
    "record_id": "",
    "scene": "",
    "auto_approve": True,
    "stages": [],
    "tool_calls_summary": {},
    "errors": [],
    "warnings": [],
    "agent_outputs": {},
    "project_summary": {},
    "llm_cost": {},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="全链路诊断运行")
    parser.add_argument("--scene", default="电商大促", help="预设场景名称")
    parser.add_argument("--record-id", help="使用已有 record_id")
    return parser


async def create_demo_brief(scene: str) -> str:
    """在 Bitable 创建 demo brief，返回 record_id。"""
    from config import FIELD_MAP_PROJECT as FP, PROJECT_TABLE_ID
    from feishu.bitable import BitableClient

    briefs_dir = ROOT / "demo" / "briefs"
    path = briefs_dir / f"{scene}.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到场景预设: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))

    # 客户名追加时间戳后缀，避免与已有项目重名导致 list_content 混合新旧数据
    ts_suffix = datetime.now().strftime("%m%d_%H%M")
    unique_client_name = f"{payload['client_name']}_诊断{ts_suffix}"

    client = BitableClient()
    fields = {
        FP["client_name"]: unique_client_name,
        FP["brief"]: payload["brief"],
        FP["project_type"]: payload["project_type"],
        FP["brand_tone"]: payload["brand_tone"],
        FP["dept_style"]: payload["dept_style"],
        FP["status"]: "待处理",
    }
    record_id = await client.create_record(PROJECT_TABLE_ID, fields)
    logger.info("创建 demo brief 成功: record_id=%s, 场景=%s", record_id, scene)
    return record_id


async def collect_project_summary(record_id: str) -> dict:
    """收集项目最终状态摘要。"""
    try:
        from memory.project import ContentMemory, ProjectMemory
        pm = ProjectMemory(record_id)
        project = await pm.load()
        cm = ContentMemory()
        rows = await cm.list_by_project(project.client_name)

        drafted = [r for r in rows if r.draft and r.draft.strip()]
        approved = [r for r in rows if r.review_status == "通过"]
        scheduled = [r for r in rows if r.publish_date]

        summary = {
            "record_id": record_id,
            "client_name": project.client_name,
            "project_type": project.project_type,
            "status": project.status,
            "brief_analysis_length": len(project.brief_analysis or ""),
            "strategy_length": len(project.strategy or ""),
            "review_summary_length": len(project.review_summary or ""),
            "delivery_length": len(project.delivery or ""),
            "review_pass_rate": project.review_pass_rate,
            "content_total": len(rows),
            "content_drafted": len(drafted),
            "content_approved": len(approved),
            "content_scheduled": len(scheduled),
            "content_details": [],
        }
        for row in rows:
            summary["content_details"].append({
                "seq": row.seq,
                "title": row.title,
                "platform": row.platform,
                "content_type": row.content_type,
                "draft_length": len(row.draft or ""),
                "review_status": row.review_status,
                "publish_date": row.publish_date,
            })
        return summary
    except Exception as e:
        logger.error("收集项目摘要失败: %s", e)
        return {"error": str(e)}


def collect_tool_stats(record_id: str) -> dict:
    """从 logs/tool_calls.jsonl 收集本次运行的工具调用统计。"""
    jsonl = ROOT / "logs" / "tool_calls.jsonl"
    if not jsonl.exists():
        return {}

    calls = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("record_id") == record_id:
                calls.append(rec)
        except Exception:
            continue

    # 聚合
    stats: dict = {}
    for c in calls:
        tool = c.get("tool", "unknown")
        if tool not in stats:
            stats[tool] = {"total": 0, "ok": 0, "fail": 0, "errors": [], "avg_ms": 0, "durations": []}
        stats[tool]["total"] += 1
        if c.get("success"):
            stats[tool]["ok"] += 1
        else:
            stats[tool]["fail"] += 1
            if c.get("error"):
                stats[tool]["errors"].append(c["error"])
        d = c.get("duration_ms")
        if d is not None:
            stats[tool]["durations"].append(d)

    for tool, s in stats.items():
        ds = s.pop("durations")
        s["avg_ms"] = round(sum(ds) / len(ds)) if ds else 0
        s["max_ms"] = max(ds) if ds else 0
        s["errors"] = list(dict.fromkeys(s["errors"]))[:5]

    return stats


def collect_llm_cost(record_id: str) -> dict:
    """从 cost_tracker 收集 LLM 成本。"""
    try:
        from memory.cost_tracker import cost_tracker
        return cost_tracker.get_project_summary(record_id)
    except Exception as e:
        return {"error": str(e)}


async def main() -> int:
    args = build_parser().parse_args()
    diag_data["scene"] = args.scene
    diag_data["start_time"] = datetime.now().isoformat()
    started = time.perf_counter()

    logger.info("=" * 70)
    logger.info("全链路诊断运行启动")
    logger.info("  场景: %s", args.scene)
    logger.info("  AUTO_APPROVE_HUMAN_REVIEW: true")
    logger.info("  日志文件: %s", log_file)
    logger.info("=" * 70)

    # 1. 创建或复用 record_id
    if args.record_id:
        record_id = args.record_id
        logger.info("使用已有 record_id: %s", record_id)
    else:
        logger.info("创建 demo brief: %s", args.scene)
        try:
            record_id = await create_demo_brief(args.scene)
        except Exception as e:
            logger.error("创建 brief 失败: %s", e, exc_info=True)
            diag_data["errors"].append({"stage": "create_brief", "error": str(e)})
            diag_data["end_time"] = datetime.now().isoformat()
            diag_data["total_seconds"] = round(time.perf_counter() - started, 1)
            _save_report()
            return 1

    diag_data["record_id"] = record_id
    logger.info("record_id: %s", record_id)

    # 2. 运行 Orchestrator
    logger.info("")
    logger.info("=" * 70)
    logger.info("启动 Orchestrator 流水线")
    logger.info("=" * 70)

    from orchestrator import Orchestrator

    orchestrator = Orchestrator(record_id=record_id)
    try:
        results = await orchestrator.run()
    except Exception as e:
        logger.error("Orchestrator 异常退出: %s", e, exc_info=True)
        diag_data["errors"].append({"stage": "orchestrator", "error": str(e)})
        results = orchestrator.stage_results

    # 3. 分析阶段结果
    logger.info("")
    logger.info("=" * 70)
    logger.info("阶段执行结果")
    logger.info("=" * 70)

    for i, item in enumerate(results, 1):
        mark = "OK" if item.ok else "FAIL"
        logger.info(
            "  [%d] %s: %s (耗时 %.1fs)",
            i, item.role_id, mark, item.duration_sec,
        )
        if item.error:
            logger.warning("      错误: %s", item.error[:300])
            diag_data["errors"].append({
                "stage": item.role_id,
                "error": item.error[:500],
            })
        if item.output:
            preview = item.output[:200].replace("\n", " ")
            logger.info("      输出: %s...", preview)

        diag_data["stages"].append({
            "index": i,
            "role_id": item.role_id,
            "ok": item.ok,
            "duration_sec": round(item.duration_sec, 2),
            "output_length": len(item.output or ""),
            "error": item.error[:500] if item.error else "",
            "output_preview": (item.output or "")[:500],
        })
        diag_data["agent_outputs"][item.role_id] = (item.output or "")[:2000]

    # 4. 收集项目最终摘要
    logger.info("")
    logger.info("=" * 70)
    logger.info("项目最终状态")
    logger.info("=" * 70)

    summary = await collect_project_summary(record_id)
    diag_data["project_summary"] = summary

    if "error" not in summary:
        logger.info("  客户名称: %s", summary.get("client_name"))
        logger.info("  项目状态: %s", summary.get("status"))
        logger.info("  Brief 解读长度: %d 字", summary.get("brief_analysis_length", 0))
        logger.info("  策略方案长度: %d 字", summary.get("strategy_length", 0))
        logger.info("  审核总评长度: %d 字", summary.get("review_summary_length", 0))
        logger.info("  交付摘要长度: %d 字", summary.get("delivery_length", 0))
        logger.info("  审核通过率: %s", summary.get("review_pass_rate"))
        logger.info("  内容总数: %d", summary.get("content_total", 0))
        logger.info("  已有成稿: %d", summary.get("content_drafted", 0))
        logger.info("  审核通过: %d", summary.get("content_approved", 0))
        logger.info("  已排期: %d", summary.get("content_scheduled", 0))
        for cd in summary.get("content_details", []):
            logger.info(
                "    #%s %s | %s | %s | 稿=%d字 | 审=%s | 发=%s",
                cd.get("seq", "?"),
                cd.get("title", "?")[:20],
                cd.get("platform", "?"),
                cd.get("content_type", "?"),
                cd.get("draft_length", 0),
                cd.get("review_status", "-"),
                cd.get("publish_date", "-"),
            )
    else:
        logger.error("  收集失败: %s", summary.get("error"))

    # 5. 工具调用统计
    logger.info("")
    logger.info("=" * 70)
    logger.info("工具调用统计")
    logger.info("=" * 70)

    tool_stats = collect_tool_stats(record_id)
    diag_data["tool_calls_summary"] = tool_stats

    for tool, s in sorted(tool_stats.items()):
        rate = round(s["ok"] / s["total"] * 100, 1) if s["total"] else 0
        logger.info(
            "  %-25s 总=%d 成功=%d 失败=%d 成功率=%s%% 平均=%dms 最大=%dms",
            tool, s["total"], s["ok"], s["fail"], rate, s["avg_ms"], s["max_ms"],
        )
        if s["errors"]:
            for err in s["errors"]:
                logger.warning("    → 错误类型: %s", err)

    # 6. LLM 成本
    logger.info("")
    logger.info("=" * 70)
    logger.info("LLM Token 成本")
    logger.info("=" * 70)

    cost = collect_llm_cost(record_id)
    diag_data["llm_cost"] = cost

    if isinstance(cost, dict) and "error" not in cost:
        logger.info("  总 prompt_tokens: %s", cost.get("total_prompt_tokens", "?"))
        logger.info("  总 completion_tokens: %s", cost.get("total_completion_tokens", "?"))
        logger.info("  总 tokens: %s", cost.get("total_tokens", "?"))
        for role_data in cost.get("by_role", []):
            logger.info(
                "    %s: prompt=%s completion=%s calls=%s",
                role_data.get("role_id", "?"),
                role_data.get("prompt_tokens", "?"),
                role_data.get("completion_tokens", "?"),
                role_data.get("calls", "?"),
            )

    # 7. 总结
    elapsed = time.perf_counter() - started
    diag_data["end_time"] = datetime.now().isoformat()
    diag_data["total_seconds"] = round(elapsed, 1)

    ok_count = sum(1 for s in diag_data["stages"] if s["ok"])
    total_count = len(diag_data["stages"])
    error_count = len(diag_data["errors"])

    logger.info("")
    logger.info("=" * 70)
    logger.info("诊断运行总结")
    logger.info("=" * 70)
    logger.info("  record_id: %s", record_id)
    logger.info("  总耗时: %.1fs", elapsed)
    logger.info("  阶段通过: %d/%d", ok_count, total_count)
    logger.info("  错误数: %d", error_count)
    logger.info("  最终状态: %s", summary.get("status", "未知"))

    if error_count > 0:
        logger.info("")
        logger.info("  ⚠ 错误清单:")
        for err in diag_data["errors"]:
            logger.info("    [%s] %s", err.get("stage", "?"), err.get("error", "?")[:200])

    # 保存结构化报告
    _save_report()

    logger.info("")
    logger.info("诊断报告已保存: logs/diagnostic_%s.json", ts_str)
    logger.info("详细日志已保存: %s", log_file)
    return 0 if error_count == 0 else 1


def _save_report():
    report_file = LOG_DIR / f"diagnostic_{ts_str}.json"
    report_file.write_text(
        json.dumps(diag_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
