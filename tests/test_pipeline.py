from __future__ import annotations

import asyncio
import httpx
import logging
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


TEST_PROJECT_NAME = "全流程测试"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def missing_config_keys() -> list[str]:
    env_path = ROOT / ".env"
    values = load_env_file(env_path)
    required = [
        "LLM_API_KEY",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "BITABLE_APP_TOKEN",
        "PROJECT_TABLE_ID",
        "CONTENT_TABLE_ID",
    ]
    missing: list[str] = []
    for key in required:
        value = os.getenv(key) or values.get(key, "")
        if not value:
            missing.append(key)
    return missing


def fixed_placeholder_draft(title: str) -> str:
    base = f"{title}；适合3-8岁，含安全认证，六一送礼更安心，欢迎咨询了解。"
    filler = "温馨有爱寓教于乐安全可靠立即下单亲子陪伴更放心。"
    text = (base + filler).replace("\n", "").replace(" ", "")
    return text[:50]


async def seed_placeholder_drafts(record_id: str) -> int:
    from memory.project import ContentMemory, ProjectMemory
    from tools import AgentContext
    from tools.write_content import execute as write_content_execute

    pm = ProjectMemory(record_id)
    proj = await pm.load()
    cm = ContentMemory()
    rows = await cm.list_by_project(proj.client_name)
    ctx = AgentContext(
        record_id=record_id,
        project_name=proj.client_name,
        role_id="copywriter_test",
    )

    for row in rows:
        placeholder = fixed_placeholder_draft(row.title)
        await write_content_execute(
            {
                "content_record_id": row.record_id,
                "field_name": "draft_content",
                "value": placeholder,
            },
            ctx,
        )

    await pm.update_status("审核中")
    return len(rows)


async def delete_record(client, table_id: str, record_id: str) -> None:
    url = f"{client._table_url(table_id)}/{record_id}"
    headers = await client._headers()
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.delete(url, headers=headers)
    client._parse_resp(resp)


async def cleanup_existing_test_data(client) -> tuple[int, int]:
    from config import (
        CONTENT_TABLE_ID,
        FIELD_MAP_CONTENT as FC,
        FIELD_MAP_PROJECT as FP,
        PROJECT_TABLE_ID,
    )

    project_filter = f'CurrentValue.[{FP["client_name"]}]="{TEST_PROJECT_NAME}"'
    content_filter = f'CurrentValue.[{FC["project_name"]}]="{TEST_PROJECT_NAME}"'

    project_records = await client.list_records(PROJECT_TABLE_ID, project_filter)
    content_records = await client.list_records(CONTENT_TABLE_ID, content_filter)

    for record in content_records:
        await delete_record(client, CONTENT_TABLE_ID, record["record_id"])

    for record in project_records:
        await delete_record(client, PROJECT_TABLE_ID, record["record_id"])

    return len(project_records), len(content_records)


async def main() -> int:
    env_path = ROOT / ".env"
    missing = missing_config_keys()
    if not env_path.exists() or missing:
        print("跳过全流程测试：缺少 .env 配置")
        if missing:
            print(f"缺少键: {missing}")
        return 0

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    from agents.base import BaseAgent
    from config import FIELD_MAP_PROJECT as FP, PROJECT_TABLE_ID
    from feishu.bitable import BitableClient
    from memory.project import ContentMemory, ProjectMemory

    client = BitableClient()
    deleted_projects, deleted_contents = await cleanup_existing_test_data(client)
    if deleted_projects or deleted_contents:
        print(
            f"已清理同名历史数据: 主表 {deleted_projects} 条, 内容表 {deleted_contents} 条"
        )

    payload = {
        FP["client_name"]: TEST_PROJECT_NAME,
        FP["brief"]: "六一儿童节促销，主推儿童益智玩具套装，预算3万，目标28-40岁家长群体，需要公众号科普文+小红书种草+抖音开箱脚本",
        FP["project_type"]: "电商大促",
        FP["brand_tone"]: "温馨有爱、寓教于乐、安全可靠",
        FP["dept_style"]: "文案必须包含适用年龄段说明和安全认证信息",
        FP["status"]: "待处理",
    }

    record_id = await client.create_record(PROJECT_TABLE_ID, payload)
    print(f"创建测试 Brief 成功: {record_id}")

    started_at = time.perf_counter()

    for role_id in ("account_manager", "strategist"):
        print(f"\n[测试] 运行阶段: {role_id}")
        agent = BaseAgent(role_id=role_id, record_id=record_id)
        await agent.run()

    seeded_count = await seed_placeholder_drafts(record_id)
    print(f"\n[测试] 已写入固定 50 字占位 draft: {seeded_count} 条")

    for role_id in ("reviewer", "project_manager"):
        print(f"\n[测试] 运行阶段: {role_id}")
        agent = BaseAgent(role_id=role_id, record_id=record_id)
        await agent.run()

    elapsed = time.perf_counter() - started_at

    pm = ProjectMemory(record_id)
    proj = await pm.load()
    cm = ContentMemory()
    content_records = await cm.list_by_project(proj.client_name)

    approved_records = [item for item in content_records if item.review_status == "通过"]
    drafted_records = [item for item in content_records if item.draft]
    scheduled_approved = [item for item in approved_records if item.publish_date]

    brief_len = len(proj.brief_analysis or "")
    strategy_len = len(proj.strategy or "")
    review_len = len(proj.review_summary or "")
    delivery_len = len(proj.delivery or "")

    project_checks = {
        "Brief解读": bool(proj.brief_analysis.strip()),
        "策略方案": bool(proj.strategy.strip()),
        "审核总评": bool(proj.review_summary.strip()),
        "交付摘要": bool(proj.delivery.strip()),
        "项目状态": proj.status == "已完成",
    }
    content_checks = {
        "内容行数量": len(content_records) >= 4,
        "成稿数量": len(drafted_records) == len(content_records) and len(content_records) > 0,
        "通过内容发布日期": len(scheduled_approved) == len(approved_records),
    }

    print("\n项目主表验证:")
    print(f"{'✓' if project_checks['Brief解读'] else '✗'} Brief解读: {brief_len} 字")
    print(f"{'✓' if project_checks['策略方案'] else '✗'} 策略方案: {strategy_len} 字")
    print(f"{'✓' if project_checks['审核总评'] else '✗'} 审核总评: {review_len} 字")
    print(f"{'✓' if project_checks['交付摘要'] else '✗'} 交付摘要: {delivery_len} 字")
    print(f"{'✓' if project_checks['项目状态'] else '✗'} 项目状态: {proj.status}")

    print("\n内容排期表验证:")
    print(f"{'✓' if content_checks['内容行数量'] else '✗'} 关联内容行: {len(content_records)}")
    print(f"{'✓' if content_checks['成稿数量'] else '✗'} 有成稿行: {len(drafted_records)}/{len(content_records)}")
    print(f"{'✓' if content_checks['通过内容发布日期'] else '✗'} 通过且已排期: {len(scheduled_approved)}/{len(approved_records)}")

    total_minutes = int(elapsed // 60)
    total_seconds = elapsed - total_minutes * 60
    print("\n============ 全流程测试报告 ============")
    print(f"记录 ID: {record_id}")
    print(f"总耗时: {total_minutes} 分 {total_seconds:.1f} 秒")
    print("")
    print(f"[客户经理] / Brief 解读 ({brief_len} 字)")
    print(f"[策略师]   / 创建 {len(content_records)} 条内容行")
    print(f"[文案]     / 使用 50 字占位稿 {len(drafted_records)}/{len(content_records)} 条")
    print(f"[审核]     / 通过率 {proj.review_pass_rate:.0%}")
    print(f"[项目经理] / 交付摘要，{len(scheduled_approved)} 条已排期")
    print("")
    print(f"项目状态: {proj.status}")
    print("========================================")
    print(f"测试记录 {record_id} 已保留在表格中，可手动查看或删除")

    all_ok = all(project_checks.values()) and all(content_checks.values())
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
