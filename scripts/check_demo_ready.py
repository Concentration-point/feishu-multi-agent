from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_MODULES = ["httpx", "dotenv", "openai", "fastapi", "uvicorn"]
REQUIRED_ENV = [
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "BITABLE_APP_TOKEN",
    "PROJECT_TABLE_ID",
    "CONTENT_TABLE_ID",
    "LLM_API_KEY",
]


def mask(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def check_modules() -> list[str]:
    missing: list[str] = []
    print("\n[1/6] Python 依赖")
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
            print(f"  OK      {module}")
        except Exception as exc:
            print(f"  MISSING {module}: {type(exc).__name__}: {exc}")
            missing.append(module)
    return missing


def check_env() -> list[str]:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    missing: list[str] = []
    print("\n[2/6] .env 配置")
    if not (ROOT / ".env").exists():
        print("  MISSING .env 文件不存在")
        missing.append(".env")

    for key in REQUIRED_ENV:
        value = os.getenv(key, "")
        if value:
            print(f"  OK      {key}={mask(value)}")
        else:
            print(f"  MISSING {key}")
            missing.append(key)
    return missing


async def check_feishu_token() -> bool:
    print("\n[3/6] 飞书 tenant_access_token")
    try:
        from feishu.auth import TokenManager

        token = await TokenManager().get_token()
        print(f"  OK      token={mask(token)}")
        return True
    except Exception as exc:
        print(f"  FAIL    {type(exc).__name__}: {exc}")
        return False


async def check_bitable_tables() -> tuple[bool, list[dict], list[dict]]:
    print("\n[4/6] 多维表格连通性")
    try:
        from config import CONTENT_TABLE_ID, PROJECT_TABLE_ID
        from feishu.bitable import BitableClient

        client = BitableClient()
        project_rows = await client.list_records(PROJECT_TABLE_ID, page_size=3)
        content_rows = await client.list_records(CONTENT_TABLE_ID, page_size=3)
        print(f"  OK      PROJECT_TABLE_ID 可读，样本数={len(project_rows)}")
        print(f"  OK      CONTENT_TABLE_ID 可读，样本数={len(content_rows)}")
        return True, project_rows, content_rows
    except Exception as exc:
        print(f"  FAIL    {type(exc).__name__}: {exc}")
        return False, [], []


def check_field_mapping_config() -> bool:
    print("\n[5/6] 字段映射配置完整性")
    try:
        from config import FIELD_MAP_CONTENT, FIELD_MAP_PROJECT

        print(f"  OK      项目主表字段数={len(FIELD_MAP_PROJECT)}")
        print(f"  OK      内容排期表字段数={len(FIELD_MAP_CONTENT)}")
        for key, name in FIELD_MAP_PROJECT.items():
            if not name:
                raise ValueError(f"FIELD_MAP_PROJECT.{key} 为空")
        for key, name in FIELD_MAP_CONTENT.items():
            if not name:
                raise ValueError(f"FIELD_MAP_CONTENT.{key} 为空")
        return True
    except Exception as exc:
        print(f"  FAIL    {type(exc).__name__}: {exc}")
        return False


def _sample_field_names(rows: list[dict]) -> set[str]:
    names: set[str] = set()
    for row in rows:
        names.update((row.get("fields") or {}).keys())
    return names


def check_sample_fields(project_rows: list[dict], content_rows: list[dict]) -> bool:
    print("\n[6/6] 样本字段名校验")
    from config import FIELD_MAP_CONTENT, FIELD_MAP_PROJECT

    ok = True
    project_sample = _sample_field_names(project_rows)
    content_sample = _sample_field_names(content_rows)

    if not project_sample:
        print("  WARN    项目主表没有样本记录，无法字段级比对；只能确认表可读")
    else:
        missing = [name for name in FIELD_MAP_PROJECT.values() if name not in project_sample]
        if missing:
            ok = False
            print(f"  FAIL    项目主表样本缺字段: {missing}")
            print(f"          当前样本字段: {sorted(project_sample)}")
        else:
            print("  OK      项目主表样本字段覆盖代码映射")

    if not content_sample:
        print("  WARN    内容排期表没有样本记录，无法字段级比对；只能确认表可读")
    else:
        missing = [name for name in FIELD_MAP_CONTENT.values() if name not in content_sample]
        if missing:
            ok = False
            print(f"  FAIL    内容排期表样本缺字段: {missing}")
            print(f"          当前样本字段: {sorted(content_sample)}")
        else:
            print("  OK      内容排期表样本字段覆盖代码映射")

    return ok


async def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether demo can run")
    parser.add_argument("--skip-network", action="store_true", help="只检查本地依赖和配置，不请求飞书")
    parser.add_argument("--no-field-sample", action="store_true", help="跳过样本记录字段名校验")
    args = parser.parse_args()

    module_missing = check_modules()
    env_missing = check_env()

    token_ok = True
    table_ok = True
    project_rows: list[dict] = []
    content_rows: list[dict] = []

    if not args.skip_network and not module_missing and not env_missing:
        token_ok = await check_feishu_token()
        if token_ok:
            table_ok, project_rows, content_rows = await check_bitable_tables()
        else:
            table_ok = False
    elif args.skip_network:
        print("\n[3/6] 飞书 tenant_access_token: SKIP")
        print("[4/6] 多维表格连通性: SKIP")
    else:
        print("\n[3/6] 飞书 tenant_access_token: SKIP（依赖或 .env 不完整）")
        print("[4/6] 多维表格连通性: SKIP（依赖或 .env 不完整）")

    fields_config_ok = check_field_mapping_config()
    sample_fields_ok = True
    if args.skip_network or args.no_field_sample or not table_ok:
        print("\n[6/6] 样本字段名校验: SKIP")
    else:
        sample_fields_ok = check_sample_fields(project_rows, content_rows)

    print("\n" + "=" * 60)
    ready = (
        not module_missing
        and not env_missing
        and token_ok
        and table_ok
        and fields_config_ok
        and sample_fields_ok
    )
    if ready:
        print("DEMO_READY: YES")
        print("可以尝试：python demo/run_demo.py --scene 电商大促")
    else:
        print("DEMO_READY: NO")
        if module_missing:
            print(f"缺依赖：{module_missing}")
        if env_missing:
            print(f"缺配置：{env_missing}")
        if not token_ok:
            print("飞书鉴权失败：检查 FEISHU_APP_ID / FEISHU_APP_SECRET")
        if not table_ok:
            print("多维表格不可读：检查 BITABLE_APP_TOKEN / TABLE_ID / 应用权限")
        if not fields_config_ok or not sample_fields_ok:
            print("字段映射不完整：检查 docs/field-mapping-reference.md")
    print("=" * 60)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
