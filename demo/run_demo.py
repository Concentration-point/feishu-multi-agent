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


async def print_summary(record_id: str) -> None:
    from memory.project import ContentMemory, ProjectMemory

    pm = ProjectMemory(record_id)
    project = await pm.load()
    cm = ContentMemory()
    rows = await cm.list_by_project(project.client_name)

    drafted = [row for row in rows if row.draft and row.draft.strip()]
    approved = [row for row in rows if row.review_status == "通过"]
    scheduled = [row for row in rows if row.publish_date]

    print("\n" + "=" * 60)
    print("Demo 结果总览")
    print("=" * 60)
    print(f"record_id: {record_id}")
    print(f"客户名称: {project.client_name}")
    print(f"项目类型: {project.project_type}")
    print(f"项目状态: {project.status}")
    print(f"Brief 解读长度: {len(project.brief_analysis or '')}")
    print(f"策略方案长度: {len(project.strategy or '')}")
    print(f"审核总评长度: {len(project.review_summary or '')}")
    print(f"交付摘要长度: {len(project.delivery or '')}")
    print(f"审核通过率: {project.review_pass_rate:.0%}")
    print(f"内容总数: {len(rows)}")
    print(f"已有成稿: {len(drafted)}/{len(rows)}")
    print(f"审核通过: {len(approved)}/{len(rows)}")
    print(f"已排期: {len(scheduled)}/{len(rows)}")

    if rows:
        print("\n内容明细:")
        for row in rows:
            print(
                f"- #{row.seq} {row.title} | {row.platform} | {row.content_type} | "
                f"审核={row.review_status or '-'} | 发布={row.publish_date or '-'}"
            )
    print("=" * 60)


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
    await print_summary(record_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
