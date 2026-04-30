from __future__ import annotations

import argparse
import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import (
    SYNC_INTERVAL,
    WEBHOOK_PORT,
    WEBHOOK_VERIFICATION_TOKEN,
    WIKI_DOWNLOAD_ENABLED,
    WIKI_DOWNLOAD_INTERVAL,
    WIKI_SPACE_ID,
)
from dashboard.event_bus import event_bus
from orchestrator import Orchestrator

logger = logging.getLogger(__name__)

_processed_record_ids: set[str] = set()   # 飞书 webhook 幂等（防短时间重发）
_running_record_ids: set[str] = set()     # 当前正在运行的 record_id（运行中锁）
_sync_service = None
_sync_task: asyncio.Task | None = None
_download_service = None
_download_task: asyncio.Task | None = None
_pipeline_tasks: set[asyncio.Task] = set()  # 跟踪所有运行中的 pipeline task


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI 应用生命周期：启动后台同步，优雅关停所有 pipeline。"""
    await _start_background_sync()
    await _start_background_download()
    try:
        yield
    finally:
        await _cancel_all_pipelines()
        await _stop_background_download()
        await _stop_background_sync()


app = FastAPI(title="multi-agent-feishu webhook", lifespan=lifespan)

# CORS — 允许本地开发访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务
_DASHBOARD_DIR = Path(__file__).parent / "dashboard" / "static"
if _DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_DASHBOARD_DIR)), name="dashboard-static")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-agent Feishu pipeline CLI")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the full orchestrator pipeline")
    run_parser.add_argument("record_id", help="Bitable project record_id")

    sync_parser = subparsers.add_parser(
        "sync",
        help="Manually sync knowledge (default: upload 07-10 local → Feishu)",
    )
    sync_parser.add_argument(
        "--direction",
        choices=["up", "down", "both"],
        default="up",
        help="up: 本地 → 飞书 (仅 07-10); down: 飞书 → 本地 (仅 01-06); both: 先下再上",
    )

    subparsers.add_parser("serve", help="Run FastAPI webhook server")

    report_parser = subparsers.add_parser(
        "report",
        help="Run data analyst to generate business report",
    )
    report_parser.add_argument(
        "--type",
        choices=["weekly", "insight", "decision"],
        default="weekly",
        dest="report_type",
        help="报告类型: weekly=运营周报, insight=数据洞察, decision=决策建议",
    )

    return parser


async def _create_sync_service():
    if not WIKI_SPACE_ID:
        return None
    from sync.wiki_sync import WikiSyncService

    return WikiSyncService(WIKI_SPACE_ID, SYNC_INTERVAL)


async def _start_background_sync() -> asyncio.Task | None:
    global _sync_service, _sync_task
    if _sync_task and not _sync_task.done():
        return _sync_task

    _sync_service = await _create_sync_service()
    if not _sync_service:
        return None

    _sync_task = asyncio.create_task(_sync_service.start())
    return _sync_task


async def _stop_background_sync() -> None:
    global _sync_task
    if _sync_task:
        _sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await _sync_task
        _sync_task = None


async def _create_download_service():
    if not WIKI_SPACE_ID or not WIKI_DOWNLOAD_ENABLED:
        return None
    from sync.wiki_download import WikiDownloadService

    return WikiDownloadService(WIKI_SPACE_ID, WIKI_DOWNLOAD_INTERVAL)


async def _start_background_download() -> asyncio.Task | None:
    """启动下行同步后台任务（飞书 → 本地，仅 01-06 人类维护层）。"""
    global _download_service, _download_task
    if _download_task and not _download_task.done():
        return _download_task

    _download_service = await _create_download_service()
    if not _download_service:
        return None

    _download_task = asyncio.create_task(_download_service.start())
    return _download_task


async def _stop_background_download() -> None:
    global _download_task
    if _download_task:
        _download_task.cancel()
        with suppress(asyncio.CancelledError):
            await _download_task
        _download_task = None


async def _trigger_download_once() -> dict | None:
    service = _download_service or await _create_download_service()
    if not service:
        return None
    return await service.trigger()


def _track_task(coro) -> asyncio.Task:
    """创建 asyncio task 并注册到 _pipeline_tasks，完成后自动移除。"""
    task = asyncio.create_task(coro)
    _pipeline_tasks.add(task)
    task.add_done_callback(_pipeline_tasks.discard)
    return task


async def _cancel_all_pipelines() -> None:
    """取消所有运行中的 pipeline task，用于 graceful shutdown。"""
    if not _pipeline_tasks:
        return
    logger.info("[Shutdown] 取消 %d 个运行中的 pipeline task...", len(_pipeline_tasks))
    for task in _pipeline_tasks:
        task.cancel()
    results = await asyncio.gather(*_pipeline_tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError):
            logger.warning("[Shutdown] pipeline task 异常: %s", r)
    _pipeline_tasks.clear()


async def _trigger_sync_once() -> None:
    service = _sync_service or await _create_sync_service()
    if service:
        await service.trigger()


async def run_pipeline(record_id: str) -> int:
    sync_task = await _start_background_sync() if WIKI_SPACE_ID else None

    orchestrator = Orchestrator(record_id=record_id, event_bus=event_bus)
    await orchestrator.run()

    if WIKI_SPACE_ID:
        await _trigger_sync_once()

    if sync_task:
        await _stop_background_sync()

    return 0


async def run_report(report_type: str = "weekly") -> int:
    """运行数据分析师 Agent，生成并推送业务报告。"""
    import time
    from agents.base import BaseAgent

    record_id = f"report_{int(time.time())}"
    agent = BaseAgent(
        role_id="data_analyst",
        record_id=record_id,
        event_bus=event_bus,
        task_filter={"report_type": report_type},
    )
    result = await agent.run()
    print(f"\n{'='*60}")
    print(f"数据分析报告（{report_type}）")
    print(f"{'='*60}")
    print(result)
    return 0


async def run_sync(direction: str = "up") -> int:
    if not WIKI_SPACE_ID:
        print("错误: WIKI_SPACE_ID 未配置，请在 .env 中设置")
        return 1

    if direction in ("down", "both"):
        stats = await _trigger_download_once()
        if stats:
            print(
                f"[sync down] 下载 {stats['downloaded']}，跳过未变 {stats['skipped']}，"
                f"失败 {stats['failed']}，耗时 {stats['elapsed']}s"
            )
        else:
            print("[sync down] 下行同步未启用（WIKI_DOWNLOAD_ENABLED=false）")

    if direction in ("up", "both"):
        await _trigger_sync_once()
        print("[sync up] 上行同步完成")

    return 0


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ── Dashboard 端点 ──

@app.get("/dashboard")
async def dashboard_page():
    """返回 Dashboard 主页面。

    强制 no-cache 防止浏览器持有旧 index.html：
      - hash 文件 (assets/index-XXXX.js) 由 vite 输出含哈希文件名，URL 变了浏览器自动拉新，可长期缓存
      - 但 index.html 文件名固定，必须每次拉最新才能拿到新的 hash 引用，否则页面会卡在旧 bundle
    """
    index_path = _DASHBOARD_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="dashboard not built")
    return HTMLResponse(
        index_path.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/pipelines")
async def list_pipelines():
    """返回所有已知 pipeline 列表（供前端自动发现）。"""
    return JSONResponse(event_bus.list_pipelines())


@app.get("/api/runs")
async def list_runs():
    """列出磁盘上所有执行记录。"""
    from dashboard.event_bus import EventBus
    return JSONResponse({"ok": True, "runs": EventBus.list_runs()})


@app.get("/api/runs/{record_id}")
async def get_run(record_id: str):
    """查询指定 record_id 的执行记录。有则返回完整事件列表，无则 has_run=false。"""
    from dashboard.event_bus import EventBus
    if not EventBus.has_run(record_id):
        return JSONResponse({"ok": True, "has_run": False, "events": []})
    events = EventBus.load_run(record_id)
    return JSONResponse({"ok": True, "has_run": True, "events": events})


@app.get("/api/costs")
async def get_costs(record_id: str | None = None):
    """查询 LLM 调用 token 成本统计。

    - 无 record_id：返回所有项目聚合，按总 token 降序
    - 有 record_id：返回指定项目的成本摘要 + by_role 明细
    """
    from memory.cost_tracker import cost_tracker
    if record_id:
        return JSONResponse({"ok": True, "summary": cost_tracker.get_project_summary(record_id)})
    return JSONResponse({"ok": True, "summaries": cost_tracker.get_all_summaries()})


@app.get("/api/records")
async def list_records():
    """从多维表格拉取项目列表（供 dashboard 选择触发）。"""
    from config import BITABLE_APP_TOKEN, PROJECT_TABLE_ID, FIELD_MAP_PROJECT as FP
    if not BITABLE_APP_TOKEN or not PROJECT_TABLE_ID:
        return JSONResponse({"ok": False, "error": "BITABLE 未配置", "records": []})
    try:
        from feishu.bitable import BitableClient
        client = BitableClient()
        raw = await client.list_records(PROJECT_TABLE_ID)
        records = []
        for r in raw:
            f = r["fields"]
            records.append({
                "record_id": r["record_id"],
                "client_name": f.get(FP["client_name"], ""),
                "brief": (f.get(FP["brief"], "") or "")[:100],
                "project_type": f.get(FP["project_type"], ""),
                "status": f.get(FP["status"], ""),
            })
        return JSONResponse({"ok": True, "records": records})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e), "records": []})


@app.post("/api/trigger/{record_id}")
async def trigger_pipeline(record_id: str):
    """HTTP 触发真实流水线。

    并发去重语义：
      - 如果该 record_id 正在运行中 → 返回 already_running=True，前端静默跳转到实时视图
      - 跑完后 _running_record_ids 会被释放，可以再次触发（断点续审场景必需）
    """
    if record_id in _running_record_ids:
        return JSONResponse({
            "ok": True,
            "already_running": True,
            "record_id": record_id,
            "message": "项目已在运行中，已跳转到实时视图",
        })
    _running_record_ids.add(record_id)
    _track_task(_launch_pipeline(record_id))
    return JSONResponse({"ok": True, "record_id": record_id})


@app.post("/api/report")
async def trigger_report(request: Request):
    """触发数据分析师生成业务报告。"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    report_type = body.get("report_type", "weekly")
    if report_type not in ("weekly", "insight", "decision"):
        report_type = "weekly"

    import time
    from agents.base import BaseAgent

    record_id = f"report_{int(time.time())}"
    agent = BaseAgent(
        role_id="data_analyst",
        record_id=record_id,
        event_bus=event_bus,
        task_filter={"report_type": report_type},
    )
    _track_task(_run_report_agent(agent, record_id))
    return JSONResponse({"ok": True, "record_id": record_id, "report_type": report_type})


async def _run_report_agent(agent, record_id: str) -> None:
    try:
        logger.info("[Report] start data analyst for %s", record_id)
        await agent.run()
    except Exception:
        logger.exception("[Report] data analyst failed for %s", record_id)


@app.post("/api/demo/start")
async def start_demo():
    """在服务端发射 mock 事件到 EventBus，dashboard 通过全局 SSE 自动接收。"""
    _track_task(_run_server_mock())
    return JSONResponse({"ok": True, "record_id": "recDEMO001"})


async def _run_server_mock():
    """服务端 mock：把模拟事件逐条发布到 EventBus，dashboard 实时渲染。"""
    import random
    rid = "recDEMO001"

    roles = [
        ("account_manager", "客户经理"),
        ("strategist", "策略师"),
        ("copywriter", "文案"),
        ("reviewer", "审核"),
        ("project_manager", "项目经理"),
    ]

    def pub(etype, payload, role="", name="", rnd=0):
        event_bus.publish(rid, etype, payload, agent_role=role, agent_name=name, round_num=rnd)

    pub("pipeline.started", {
        "project_name": "星耀科技",
        "brief": "双十一全渠道电商营销 - 主推 AI 智能音箱新品首发，目标 GMV 500万",
        "stages": [r[0] for r in roles],
        "stage_names": {r[0]: r[1] for r in roles},
    })
    await asyncio.sleep(0.5)

    # 每个 Agent 的模拟场景
    scenes = [
        {
            "thinkings": [
                "分析 Brief 内容：客户星耀科技，项目类型为电商大促。核心诉求是双十一期间推广 AI 智能音箱新品，目标 GMV 500万。\n需要解读客户的核心卖点、目标人群和投放策略偏好。",
                "Brief 解读完成。客户核心关注点：1) 产品智能交互体验 2) 年轻科技人群 3) 性价比定位。建议内容矩阵覆盖小红书种草+抖音短视频+微信公众号深度测评。",
            ],
            "tools": [
                ("read_project", {"record_id": rid, "fields": ["Brief 内容", "品牌调性"]}, "客户名称: 星耀科技\nBrief: 双十一 AI 智能音箱新品首发\n品牌调性: 科技感、年轻化"),
                ("search_knowledge", {"query": "电商大促 智能硬件 营销"}, "命中 2 个文件:\n1. raw/某品牌618电商营销全案.md (命中3词)\n2. wiki/电商大促/brief解读经验.md (命中2词)"),
                ("read_knowledge", {"filepath": "wiki/电商大促/brief解读经验.md"}, "## 经验教训\n电商大促 Brief 解读要抓住三个核心：促销节奏、流量结构、内容货架匹配度"),
                ("write_project", {"record_id": rid, "field": "Brief 解读", "value": "核心卖点: AI语音交互+全屋智能控制..."}, "写入成功"),
                ("update_status", {"record_id": rid, "status": "策略中"}, "状态更新成功: 解读中 -> 策略中"),
            ],
        },
        {
            "thinkings": [
                "根据客户经理的 Brief 解读，制定内容策略矩阵。目标平台：小红书、抖音、微信公众号。需要覆盖种草、测评、促销转化三个阶段。",
                "策略方案已定：9篇内容矩阵，按平台和内容类型交叉分布。小红书主打种草笔记，抖音主打开箱短视频，微信主打深度测评。",
            ],
            "tools": [
                ("read_project", {"record_id": rid, "fields": ["Brief 解读"]}, "核心卖点: AI语音交互+全屋智能控制\n目标人群: 25-35岁科技爱好者"),
                ("search_knowledge", {"query": "内容策略 矩阵 电商"}, "命中: wiki/电商大促/内容策略模板.md"),
                ("batch_create_content", {"record_id": rid, "items": [{"title": "AI音箱开箱体验", "platform": "小红书"}, {"title": "智能家居生活vlog", "platform": "抖音"}, {"title": "深度测评：这个音箱值不值", "platform": "微信公众号"}]}, "批量创建 3 条内容成功"),
                ("write_project", {"record_id": rid, "field": "策略方案", "value": "9篇内容矩阵..."}, "写入成功"),
                ("update_status", {"record_id": rid, "status": "撰写中"}, "状态更新成功: 策略中 -> 撰写中"),
            ],
        },
        {
            "thinkings": [
                "开始撰写第一篇小红书种草笔记。标题：《被这个 AI 音箱种草了！全屋智能控制太香》。需要贴合小红书调性，使用口语化表达。",
                "三篇核心内容初稿完成。小红书笔记 800 字，抖音脚本 300 字，微信测评 2000 字。整体围绕「智能交互改变生活」叙事主线。",
            ],
            "tools": [
                ("read_project", {"record_id": rid, "fields": ["策略方案"]}, "9篇内容矩阵，覆盖种草/测评/转化..."),
                ("list_content", {"record_id": rid}, "共 3 条内容:\n1. AI音箱开箱体验 (小红书)\n2. 智能家居生活vlog (抖音)\n3. 深度测评 (微信公众号)"),
                ("search_knowledge", {"query": "小红书 文案 种草"}, "命中: wiki/电商大促/小红书文案套路.md"),
                ("write_content", {"content_id": "rec001", "field": "成稿内容", "value": "被这个AI音箱种草了..."}, "写入成功"),
                ("write_content", {"content_id": "rec002", "field": "成稿内容", "value": "【智能家居vlog脚本】..."}, "写入成功"),
                ("write_content", {"content_id": "rec003", "field": "成稿内容", "value": "深度测评：星耀AI音箱..."}, "写入成功"),
                ("update_status", {"record_id": rid, "status": "审核中"}, "状态更新成功: 撰写中 -> 审核中"),
            ],
        },
        {
            "thinkings": [
                "开始审核 3 篇内容稿件。审核维度：1) 品牌调性一致性 2) 广告法合规 3) 平台规则适配 4) 信息准确性。",
                "审核完成。整体通过率 78%。主要问题：1篇小红书笔记使用了极限词「最好」，1篇抖音脚本缺少产品价格信息。已标注修改建议。",
            ],
            "tools": [
                ("list_content", {"record_id": rid}, "共 3 条内容，均已成稿"),
                ("search_knowledge", {"query": "审核 合规 广告法"}, "命中: raw/某品牌618电商营销全案.md (合规审核章节)"),
                ("write_content", {"content_id": "rec001", "field": "审核状态", "value": "通过"}, "写入成功"),
                ("write_content", {"content_id": "rec002", "field": "审核状态", "value": "需修改"}, "写入成功"),
                ("write_content", {"content_id": "rec003", "field": "审核状态", "value": "通过"}, "写入成功"),
                ("write_project", {"record_id": rid, "field": "审核总评", "value": "通过率78%，2处需修改"}, "写入成功"),
                ("update_status", {"record_id": rid, "status": "排期中"}, "状态更新成功: 审核中 -> 排期中"),
            ],
        },
        {
            "thinkings": [
                "综合审核结果，安排内容发布排期。按照双十一倒推：预热期(10.20-10.31) 投放种草内容，爆发期(11.1-11.11) 投放促销转化内容。",
                "交付排期已完成。3篇内容已分配发布日期，关键时间节点已标注。项目交付摘要已写入主表。",
            ],
            "tools": [
                ("read_project", {"record_id": rid, "fields": ["审核总评", "策略方案"]}, "审核通过率78%，策略方案完整"),
                ("write_content", {"content_id": "rec001", "field": "计划发布日期", "value": "2025-10-25"}, "写入成功"),
                ("write_content", {"content_id": "rec002", "field": "计划发布日期", "value": "2025-10-28"}, "写入成功"),
                ("write_content", {"content_id": "rec003", "field": "计划发布日期", "value": "2025-11-05"}, "写入成功"),
                ("write_project", {"record_id": rid, "field": "交付摘要", "value": "3篇内容已完成排期"}, "写入成功"),
                ("send_message", {"chat_id": "oc_xxx", "content": "项目交付就绪"}, "消息发送成功"),
                ("update_status", {"record_id": rid, "status": "已完成"}, "状态更新成功: 排期中 -> 已完成"),
            ],
        },
    ]

    prev_role = ""
    for si, (role_id, role_name) in enumerate(roles):
        # stage_changed
        pub("pipeline.stage_changed", {
            "stage_index": si + 1,
            "stage_total": 5,
            "current_role": role_id,
            "current_name": role_name,
            "prev_role": prev_role,
            "prev_duration": round(8 + random.random() * 15, 1) if prev_role else 0,
        }, role_id, role_name)
        prev_role = role_id
        await asyncio.sleep(0.4)

        # agent.started
        pub("agent.started", {
            "project_name": "星耀科技",
            "project_type": "电商大促",
            "max_iterations": 12,
        }, role_id, role_name)
        await asyncio.sleep(0.2)

        scene = scenes[si]

        # first thinking
        pub("agent.thinking", {"content": scene["thinkings"][0]}, role_id, role_name, 1)
        await asyncio.sleep(0.6)

        # tools
        for ti, (tname, targs, tresult) in enumerate(scene["tools"]):
            rnd = ti // 2 + 1
            pub("tool.called", {"tool_name": tname, "arguments": targs}, role_id, role_name, rnd)
            await asyncio.sleep(0.2)
            pub("tool.returned", {"tool_name": tname, "result": tresult}, role_id, role_name, rnd)
            await asyncio.sleep(0.15)

        # final thinking
        pub("agent.thinking", {"content": scene["thinkings"][1]}, role_id, role_name, len(scene["tools"]) // 2 + 2)
        await asyncio.sleep(0.4)

        # agent.completed
        pub("agent.completed", {"output_length": 500 + random.randint(0, 1000)}, role_id, role_name)
        await asyncio.sleep(0.3)

    # pipeline.completed
    pub("pipeline.completed", {
        "total_time": 127.3,
        "ok_count": 5,
        "total_stages": 5,
        "pass_rate": 0.78,
        "status": "已完成",
    })


@app.get("/api/pipeline/{record_id}/history")
async def pipeline_history(record_id: str):
    """返回指定项目的所有历史事件。"""
    return JSONResponse(event_bus.get_history(record_id))


@app.get("/api/tool-stats")
async def tool_stats(
    limit: int = 50,
    since_hours: float = 0,
    record_id: str = "",
):
    """读取 logs/tool_calls.jsonl，返回工具调用统计 + 最近失败记录。

    - limit: 最近失败记录条数上限（默认 50）
    - since_hours: 仅统计最近 N 小时内的记录（0=全量历史）
    - record_id: 仅统计指定 record_id 的调用（空=全部 record）；与 since_hours 可叠加
    """
    import json as _json
    from collections import defaultdict
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from pathlib import Path as _Path

    # 固定绝对路径，与 tools/__init__.py 保持一致
    jsonl = _Path(__file__).resolve().parent / "logs" / "tool_calls.jsonl"
    records: list[dict] = []
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(_json.loads(line))
            except Exception:
                continue

    # 按 record_id 过滤（"本次运行"视图）—— 优先级最高，能极大缩小数据集
    target_rid = (record_id or "").strip()
    if target_rid:
        records = [r for r in records if r.get("record_id") == target_rid]

    # 按时间窗口过滤（since_hours > 0 时启用）
    if since_hours > 0:
        cutoff = _dt.now(_tz.utc) - _td(hours=since_hours)
        def _ts(r: dict) -> _dt:
            try:
                return _dt.fromisoformat(r.get("ts", "")).astimezone(_tz.utc)
            except Exception:
                return _dt.min.replace(tzinfo=_tz.utc)
        records = [r for r in records if _ts(r) >= cutoff]

    # 聚合每个工具的统计
    stats: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "ok": 0, "fail": 0, "durations": [], "errors": [],
        "last_fail_ts": None, "last_fail_role": None,
    })
    for r in records:
        t = r.get("tool", "unknown")
        s = stats[t]
        s["total"] += 1
        if r.get("success"):
            s["ok"] += 1
        else:
            s["fail"] += 1
            if r.get("error"):
                s["errors"].append(r["error"])
            if r.get("ts"):
                s["last_fail_ts"] = r["ts"]
            if r.get("role_id"):
                s["last_fail_role"] = r["role_id"]
        d = r.get("duration_ms")
        if d is not None:
            s["durations"].append(d)

    tool_list = []
    for tool, s in sorted(stats.items()):
        total = s["total"]
        ok = s["ok"]
        fail = s["fail"]
        rate = round(ok / total * 100, 1) if total else 0.0
        durations = s["durations"]
        avg_ms = round(sum(durations) / len(durations)) if durations else None
        tool_list.append({
            "tool": tool,
            "total": total,
            "ok": ok,
            "fail": fail,
            "success_rate": rate,
            "avg_ms": avg_ms,
            "top_errors": list(dict.fromkeys(s["errors"]))[:3],
            "last_fail_ts": s["last_fail_ts"],
            "last_fail_role": s["last_fail_role"],
        })

    # 最近失败记录（倒序，含时间戳）
    recent_failures = [
        r for r in reversed(records) if not r.get("success")
    ][:limit]

    # 元信息
    oldest_ts = records[0].get("ts") if records else None
    newest_ts = records[-1].get("ts") if records else None

    return JSONResponse({
        "ok": True,
        "total_records": len(records),
        "since_hours": since_hours,
        "record_id": target_rid,  # 回显前端传入的过滤条件，便于一致性校验
        "oldest_ts": oldest_ts,
        "newest_ts": newest_ts,
        "tool_stats": tool_list,
        "recent_failures": recent_failures,
    })


@app.get("/stream")
async def global_event_stream():
    """全局 SSE 端点：接收所有项目的实时事件。Dashboard 默认连这个。"""

    async def generate():
        try:
            async for evt in event_bus.subscribe_all():
                data = json.dumps(evt, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/stream/{record_id}")
async def event_stream(record_id: str):
    """SSE 端点：推送指定项目的实时事件。"""

    async def generate():
        try:
            async for evt in event_bus.subscribe(record_id):
                data = json.dumps(evt, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Webhook 端点 ──

def _extract_record_id(event: dict[str, Any]) -> str | None:
    data = event.get("event", {})

    candidates = [
        data.get("record_id"),
        data.get("record", {}).get("record_id"),
        data.get("record", {}).get("id"),
        data.get("data", {}).get("record_id"),
        data.get("data", {}).get("record", {}).get("record_id"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


async def _launch_pipeline(record_id: str) -> None:
    try:
        logger.info("[Webhook] start pipeline for %s", record_id)
        orchestrator = Orchestrator(record_id=record_id, event_bus=event_bus)
        await orchestrator.run()
        await _trigger_sync_once()
    except asyncio.CancelledError:
        logger.info("[Webhook] pipeline cancelled for %s (shutdown)", record_id)
        raise  # 必须 re-raise 让 task 状态变为 cancelled
    except Exception:
        logger.exception("[Webhook] pipeline failed for %s", record_id)
    finally:
        # 释放运行中锁，允许同 record_id 后续重新触发（恢复人审场景必需）
        _running_record_ids.discard(record_id)


@app.post("/webhook/event")
async def webhook_event(request: Request):
    payload = await request.json()

    challenge = payload.get("challenge")
    if challenge:
        token = payload.get("token") or payload.get("header", {}).get("token", "")
        if WEBHOOK_VERIFICATION_TOKEN and token and token != WEBHOOK_VERIFICATION_TOKEN:
            raise HTTPException(status_code=401, detail="invalid verification token")
        return JSONResponse({"challenge": challenge})

    header = payload.get("header", {})
    event_type = header.get("event_type") or payload.get("type") or ""
    if "bitable.record.created" not in event_type and "record.created" not in event_type:
        raise HTTPException(status_code=400, detail="unsupported event type")

    token = payload.get("token") or header.get("token", "")
    if WEBHOOK_VERIFICATION_TOKEN and token and token != WEBHOOK_VERIFICATION_TOKEN:
        raise HTTPException(status_code=401, detail="invalid verification token")

    record_id = _extract_record_id(payload)
    if not record_id:
        raise HTTPException(status_code=400, detail="record_id missing")

    if record_id in _processed_record_ids:
        return JSONResponse({"ok": True, "duplicate": True, "record_id": record_id})

    _processed_record_ids.add(record_id)
    _track_task(_launch_pipeline(record_id))
    return JSONResponse({"ok": True, "record_id": record_id})


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args()

    def _run(coro) -> int:
        try:
            return asyncio.run(coro)
        except KeyboardInterrupt:
            logger.warning("用户中断 (KeyboardInterrupt)，退出")
            return 130

    if args.command == "run":
        return _run(run_pipeline(args.record_id))
    if args.command == "sync":
        direction = getattr(args, "direction", "up")
        return _run(run_sync(direction))
    if args.command == "report":
        report_type = getattr(args, "report_type", "weekly")
        return _run(run_report(report_type))
    if args.command == "serve":
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=WEBHOOK_PORT)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
