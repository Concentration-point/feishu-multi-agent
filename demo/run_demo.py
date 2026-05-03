from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

BRIEFS_DIR = Path(__file__).resolve().parent / "briefs"
REQUIRED_MODULES = ["openai"]
REQUIRED_ENV = [
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "BITABLE_APP_TOKEN",
    "PROJECT_TABLE_ID",
    "CONTENT_TABLE_ID",
    "LLM_API_KEY",
]


def check_readiness() -> tuple[list[str], list[str]]:
    missing_modules: list[str] = []
    missing_env: list[str] = []

    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except Exception:
            missing_modules.append(module)

    for key in REQUIRED_ENV:
        if not os.getenv(key):
            missing_env.append(key)

    return missing_modules, missing_env


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        force=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a demo pipeline for multi-agent-feishu")
    parser.add_argument("--scene", default="电商大促", help="预设场景名称，如：电商大促 / 新品发布 / 品牌传播")
    parser.add_argument("--record-id", help="直接使用现有 record_id，跳过创建 demo brief")
    return parser


def load_scene_payload(scene: str) -> dict:
    path = BRIEFS_DIR / f"{scene}.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到场景预设: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


async def create_demo_brief(scene: str) -> str:
    from config import FIELD_MAP_PROJECT as FP, PROJECT_TABLE_ID
    from feishu.bitable import BitableClient

    payload = load_scene_payload(scene)
    client = BitableClient()
    fields = {
        FP["client_name"]: payload["client_name"],
        FP["brief"]: payload["brief"],
        FP["project_type"]: payload["project_type"],
        FP["brand_tone"]: payload["brand_tone"],
        FP["dept_style"]: payload["dept_style"],
        FP["status"]: "待处理",
    }
    return await client.create_record(PROJECT_TABLE_ID, fields)


def _preview(text: str | None, max_len: int = 200) -> str:
    """取文本前 max_len 字符作为摘要预览，折叠换行。"""
    if not text or not text.strip():
        return "（空）"
    flat = text.strip().replace("\n", " | ")
    if len(flat) > max_len:
        return flat[:max_len] + "..."
    return flat


async def print_summary(record_id: str, elapsed: float = 0.0) -> None:
    from memory.project import ContentMemory, ProjectMemory

    pm = ProjectMemory(record_id)
    project = await pm.load()
    cm = ContentMemory()
    rows = await cm.list_by_project(project.client_name)

    drafted = [row for row in rows if row.draft and row.draft.strip()]
    approved = [row for row in rows if row.review_status == "通过"]
    scheduled = [row for row in rows if row.publish_date]
    content_count = len(rows) or 1

    print("\n" + "=" * 70)
    print("  Demo 结果总览")
    print("=" * 70)
    print(f"record_id:  {record_id}")
    print(f"客户名称:   {project.client_name}")
    print(f"项目类型:   {project.project_type}")
    print(f"项目状态:   {project.status}")
    print(f"审核通过率: {project.review_pass_rate:.0%}")
    print(f"内容统计:   共 {len(rows)} 条 | 成稿 {len(drafted)} | 通过 {len(approved)} | 已排期 {len(scheduled)}")

    # ── AI 各阶段产出预览 ──
    print("\n" + "-" * 70)
    print("  AI 产出预览（各阶段关键输出）")
    print("-" * 70)

    print(f"\n[客户经理] Brief 解读（{len(project.brief_analysis or '')} 字）:")
    print(f"  {_preview(project.brief_analysis)}")

    print(f"\n[策略师] 策略方案（{len(project.strategy or '')} 字）:")
    print(f"  {_preview(project.strategy)}")

    print(f"\n[审核] 审核总评（{len(project.review_summary or '')} 字）:")
    print(f"  {_preview(project.review_summary)}")

    print(f"\n[项目经理] 交付摘要（{len(project.delivery or '')} 字）:")
    print(f"  {_preview(project.delivery)}")

    # ── 内容明细 + 成稿预览 ──
    if rows:
        print("\n" + "-" * 70)
        print("  内容明细（文案成稿预览）")
        print("-" * 70)
        for row in rows:
            status_tag = row.review_status or "-"
            date_tag = row.publish_date or "-"
            print(f"\n  #{row.seq} [{row.platform}] {row.title}")
            print(f"     类型={row.content_type} | 审核={status_tag} | 发布={date_tag}")
            draft_preview = _preview(row.draft, 120)
            print(f"     成稿: {draft_preview}")

    # ── 效率对比 ──
    if elapsed > 0:
        human_hours = {
            "Brief 解读": 2.0,
            "策略制定": 4.0,
            "文案撰写": content_count * 1.5,
            "内容审核": content_count * 0.5,
            "排期交付": 1.0,
        }
        total_human = sum(human_hours.values())
        ai_min = elapsed / 60

        print("\n" + "-" * 70)
        print("  效率对比（AI vs 人工估算）")
        print("-" * 70)
        for step, hours in human_hours.items():
            print(f"  {step:<10} 人工约 {hours:.1f}h")
        print(f"  {'─' * 30}")
        print(f"  人工合计:  {total_human:.1f} 工时（{total_human / 8:.1f} 人天）")
        print(f"  AI 耗时:   {ai_min:.1f} 分钟")
        print(f"  效率提升:  ~{total_human * 60 / max(elapsed, 1):.0f}x")

    print("\n" + "=" * 70)


async def main() -> int:
    configure_logging()
    args = build_parser().parse_args()

    missing_modules, missing_env = check_readiness()
    if missing_modules or missing_env:
        print("Demo 运行条件不满足：")
        if missing_modules:
            print(f"- 缺少 Python 依赖: {missing_modules}")
        if missing_env:
            print(f"- 缺少 .env 配置: {missing_env}")
        print("建议先执行: python scripts/check_demo_ready.py")
        return 1

    from orchestrator import Orchestrator

    if args.record_id:
        record_id = args.record_id
        print(f"使用已有 record_id: {record_id}")
    else:
        print(f"创建 demo brief: {args.scene}")
        record_id = await create_demo_brief(args.scene)
        print(f"已创建 record_id: {record_id}")

    print("\n启动 Orchestrator...")
    started = time.perf_counter()
    orchestrator = Orchestrator(record_id=record_id)
    results = await orchestrator.run()
    elapsed = time.perf_counter() - started

    print("\n阶段执行情况:")
    for item in results:
        mark = "OK" if item.ok else "FAIL"
        print(f"- {item.role_id}: {mark} ({item.duration_sec:.1f}s)")
        if item.error:
            print(f"  error: {item.error[:200]}")

    print(f"\n总耗时: {elapsed:.1f}s")
    await print_summary(record_id, elapsed=elapsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
