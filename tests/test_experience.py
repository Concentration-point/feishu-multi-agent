"""阶段六经验系统测试。

运行方式:
    python tests/test_experience.py

层级:
1. 本地逻辑: 置信度计算 + wiki 双写
2. 经验池联调: Bitable save/query/get_experience
3. 闭环对比: 两次真实 Agent 运行，验证第一次沉淀、第二次注入
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("test_experience")


TEST_CATEGORY = "_test_自动化验证"
TEST_PROJECT_A = "阶段六经验闭环-A"
TEST_PROJECT_B = "阶段六经验闭环-B"
TEST_SCENE = "电商大促"


class TestReport:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.passed.append(name)
        logger.info("PASS: %s %s", name, detail)

    def fail(self, name: str, detail: str = "") -> None:
        self.failed.append(name)
        logger.error("FAIL: %s %s", name, detail)

    def summary(self) -> bool:
        total = len(self.passed) + len(self.failed)
        print("\n" + "=" * 60)
        print(f"测试报告: {len(self.passed)}/{total} 通过")
        print("=" * 60)
        if self.passed:
            print("\n通过:")
            for item in self.passed:
                print(f"  - {item}")
        if self.failed:
            print("\n失败:")
            for item in self.failed:
                print(f"  - {item}")
        print("=" * 60)
        return not self.failed


report = TestReport()


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


def env_value(key: str) -> str:
    env_path = ROOT / ".env"
    file_values = load_env_file(env_path)
    return os.getenv(key) or file_values.get(key, "")


def has_required_env(keys: list[str]) -> tuple[bool, list[str]]:
    missing = [key for key in keys if not env_value(key)]
    return not missing, missing


async def test_confidence_scoring() -> None:
    from orchestrator import Orchestrator

    cases = [
        {
            "name": "高质量完成",
            "args": {"pass_rate": 0.9, "task_completed": True, "no_rework": True, "knowledge_cited": True},
            "expect_min": 0.85,
        },
        {
            "name": "返工后通过",
            "args": {"pass_rate": 0.3, "task_completed": True, "no_rework": False, "knowledge_cited": False},
            "expect_max": 0.7,
        },
        {
            "name": "阈值附近",
            "args": {"pass_rate": 0.5, "task_completed": True, "no_rework": True, "knowledge_cited": True},
            "expect_min": 0.7,
        },
        {
            "name": "完全失败",
            "args": {"pass_rate": 0.0, "task_completed": False, "no_rework": False, "knowledge_cited": False},
            "expect_max": 0.1,
        },
        {
            "name": "pass_rate 为空时兜底",
            "args": {"pass_rate": None, "task_completed": True, "no_rework": True, "knowledge_cited": False},
            "expect_min": 0.5,
            "expect_max": 0.9,
        },
    ]

    for case in cases:
        score = Orchestrator._calc_confidence(**case["args"])
        min_v = case.get("expect_min", 0.0)
        max_v = case.get("expect_max", 1.0)
        ok = min_v <= score <= max_v
        print(f"  {'PASS' if ok else 'FAIL'} {case['name']}: score={score:.2f}, expect={min_v:.2f}-{max_v:.2f}")
        if not ok:
            report.fail(f"置信度打分-{case['name']}", f"score={score:.2f}")
            return

    report.ok("置信度打分公式", f"{len(cases)} 组用例通过")


async def test_wiki_write() -> None:
    from config import KNOWLEDGE_BASE_PATH
    from memory.experience import ExperienceManager, _sanitize_name

    em = ExperienceManager()
    card = {
        "situation": "测试场景：电商大促小红书种草",
        "action": "使用成分数据替代感性表述",
        "outcome": "互动率提升 40%",
        "lesson": "科技类品牌小红书笔记避免感叹号，优先用成分数据说话",
        "category": TEST_CATEGORY,
        "applicable_roles": ["copywriter"],
    }

    rel_path = await em.save_to_wiki(card, 0.85)
    if not rel_path:
        report.fail("经验写入 wiki", "返回空路径")
        return
    report.ok("经验写入 wiki", rel_path)

    full_path = Path(KNOWLEDGE_BASE_PATH) / rel_path
    content = full_path.read_text(encoding="utf-8")
    if "成分数据" not in content or "confidence: 0.85" not in content:
        report.fail("wiki 内容校验", "缺少关键内容或置信度")
        return
    report.ok("wiki 内容校验")

    state_file = Path(KNOWLEDGE_BASE_PATH) / ".sync_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    dirty_keys = [key for key in state if "test" in key and "自动化" in key]
    if not dirty_keys:
        report.fail("wiki dirty 标记", "未写入 .sync_state.json")
        return
    report.ok("wiki dirty 标记")

    index_file = Path(KNOWLEDGE_BASE_PATH) / "wiki" / "_index.md"
    if "copywriter" not in index_file.read_text(encoding="utf-8"):
        report.fail("wiki 索引更新", "_index.md 未更新")
        return
    report.ok("wiki 索引更新")

    sanitized_cat = _sanitize_name(TEST_CATEGORY)
    shutil.rmtree(Path(KNOWLEDGE_BASE_PATH) / "wiki" / sanitized_cat, ignore_errors=True)
    em._update_wiki_index(Path(KNOWLEDGE_BASE_PATH) / "wiki")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    for key in [key for key in list(state) if "test" in key and "自动化" in key]:
        state.pop(key, None)
    state.pop("wiki/_index.md", None)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def test_hook_reflect() -> None:
    if not env_value("LLM_API_KEY"):
        report.ok("Hook 自省-跳过", "缺少 LLM_API_KEY")
        return

    from agents.base import BaseAgent
    from config import LLM_API_KEY, LLM_BASE_URL
    from openai import AsyncOpenAI

    mock_messages = [
        {"role": "system", "content": "你是智策传媒的客户经理。"},
        {"role": "user", "content": "请处理电商大促项目。"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_project",
                        "arguments": '{"fields": ["brief_content", "brand_tone"]}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": '{"brief_content": "双十一电商大促，主推精华液", "brand_tone": "科技感、专业可信赖"}',
        },
        {
            "role": "assistant",
            "content": "Brief 解读完成。核心诉求是双十一期间推广精华液，目标受众 25-35 岁女性。",
        },
    ]

    agent = BaseAgent.__new__(BaseAgent)
    agent.role_id = "account_manager"
    agent.soul = type("Soul", (), {"name": "客户经理"})()
    agent._llm = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    card = await agent._hook_reflect(mock_messages)
    if not card:
        report.fail("Hook 自省", "返回 None")
        return

    required = ["situation", "action", "outcome", "lesson", "category", "applicable_roles"]
    missing = [field for field in required if field not in card]
    if missing:
        report.fail("Hook 自省", f"缺少字段: {missing}")
        return
    if len(card.get("lesson", "")) < 10:
        report.fail("Hook 自省", f"lesson 过短: {card.get('lesson', '')}")
        return

    print(f"  Hook 经验卡预览: {json.dumps(card, ensure_ascii=False)[:200]}")
    report.ok("Hook 自省", card["lesson"][:60])


def bitable_ready() -> bool:
    ready, _ = has_required_env([
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "BITABLE_APP_TOKEN",
        "EXPERIENCE_TABLE_ID",
    ])
    return ready


async def test_bitable_experience() -> None:
    if not bitable_ready():
        report.ok("Bitable 经验池-跳过", "缺少飞书或经验池配置")
        return

    from config import EXPERIENCE_TABLE_ID
    from feishu.bitable import BitableClient
    from memory.experience import ExperienceManager
    from tools import AgentContext, ToolRegistry

    em = ExperienceManager()
    client = BitableClient()
    card = {
        "situation": "Bitable 测试经验",
        "action": "测试写入",
        "outcome": "验证 CRUD",
        "lesson": "这是自动化测试写入的经验，请忽略。",
        "category": TEST_CATEGORY,
        "applicable_roles": ["account_manager"],
    }

    record_id = await em.save_experience(card, 0.88, "测试项目")
    if not record_id:
        report.fail("经验写入 Bitable", "返回 None")
        return
    report.ok("经验写入 Bitable", f"record_id={record_id}")

    results = await em.query_top_k("account_manager", TEST_CATEGORY)
    if not any(item.get("record_id") == record_id for item in results):
        report.fail("经验查询 query_top_k", "未查到刚写入的记录")
        return
    report.ok("经验查询 query_top_k", f"命中 {len(results)} 条")

    registry = ToolRegistry()
    ctx = AgentContext(record_id="test", project_name="test", role_id="test")
    tool_result = await registry.call_tool(
        "get_experience",
        {"role_id": "account_manager", "category": TEST_CATEGORY},
        ctx,
    )
    if "找到" not in tool_result:
        report.fail("get_experience 工具查询", tool_result[:120])
        return
    report.ok("get_experience 工具查询")

    await client.delete_record(EXPERIENCE_TABLE_ID, record_id)
    report.ok("Bitable 测试记录清理", record_id)


async def delete_records_by_filter(client, table_id: str, filter_expr: str) -> int:
    records = await client.list_records(table_id, filter_expr)
    for record in records:
        await client.delete_record(table_id, record["record_id"])
    return len(records)


async def create_project_record(client, client_name: str, brief: str) -> str:
    from config import FIELD_MAP_PROJECT as FP, PROJECT_TABLE_ID

    payload = {
        FP["client_name"]: client_name,
        FP["brief"]: brief,
        FP["project_type"]: TEST_SCENE,
        FP["brand_tone"]: "科技感、专业可信赖、避免过度促销感",
        FP["dept_style"]: "要求输出结构化、清晰、有行动建议",
        FP["status"]: "待处理",
    }
    return await client.create_record(PROJECT_TABLE_ID, payload)


async def cleanup_compare_data(client) -> tuple[int, int]:
    from config import EXPERIENCE_TABLE_ID, FIELD_MAP_EXPERIENCE as FE, FIELD_MAP_PROJECT as FP, PROJECT_TABLE_ID

    project_filter = (
        f'OR(CurrentValue.[{FP["client_name"]}]="{TEST_PROJECT_A}",' 
        f'CurrentValue.[{FP["client_name"]}]="{TEST_PROJECT_B}")'
    )
    exp_filter = (
        f'OR(CurrentValue.[{FE["source_project"]}]="{TEST_PROJECT_A}",' 
        f'CurrentValue.[{FE["source_project"]}]="{TEST_PROJECT_B}")'
    )
    deleted_projects = await delete_records_by_filter(client, PROJECT_TABLE_ID, project_filter)
    deleted_experiences = await delete_records_by_filter(client, EXPERIENCE_TABLE_ID, exp_filter)
    return deleted_projects, deleted_experiences


async def test_evolution_compare() -> None:
    ready, missing = has_required_env([
        "LLM_API_KEY",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "BITABLE_APP_TOKEN",
        "PROJECT_TABLE_ID",
        "EXPERIENCE_TABLE_ID",
    ])
    if not ready:
        report.ok("第三层闭环对比-跳过", f"缺少配置: {missing}")
        return

    from agents.base import BaseAgent
    from feishu.bitable import BitableClient
    from memory.experience import ExperienceManager
    from orchestrator import Orchestrator, StageResult

    client = BitableClient()
    em = ExperienceManager(client=client)

    deleted_projects, deleted_experiences = await cleanup_compare_data(client)
    if deleted_projects or deleted_experiences:
        print(f"已清理历史闭环测试数据: 项目 {deleted_projects} 条, 经验 {deleted_experiences} 条")

    record_a = None
    record_b = None
    saved_count_before = 0
    saved_count_after = 0
    injected_text = ""

    try:
        record_a = await create_project_record(
            client,
            TEST_PROJECT_A,
            "双十一电商大促，主推新款精华液，预算5万，目标25-35岁女性消费者，需要公众号深度种草文章和小红书种草笔记",
        )
        agent_a = BaseAgent(role_id="account_manager", record_id=record_a)
        output_a = await agent_a.run()
        if not agent_a._pending_experience:
            report.fail("第三层闭环对比", "第一次运行未产出经验卡")
            return

        saved_count_before = len(await em.query_top_k("account_manager", TEST_SCENE, k=20))
        settled_card = dict(agent_a._pending_experience)
        settled_card["category"] = TEST_SCENE

        orchestrator = Orchestrator(record_a)
        orchestrator.stage_results = [
            StageResult(role_id="account_manager", ok=True, duration_sec=0.0, output=output_a or "")
        ]
        await orchestrator._settle_experiences(
            [{"role_id": "account_manager", "card": settled_card, "agent": agent_a}],
            TEST_PROJECT_A,
            0.8,
        )
        saved_count_after = len(await em.query_top_k("account_manager", TEST_SCENE, k=20))
        if saved_count_after < saved_count_before:
            report.fail("第三层闭环对比", "第一次沉淀后经验数异常减少")
            return

        record_b = await create_project_record(
            client,
            TEST_PROJECT_B,
            "双十一电商大促，主推高保湿精华液，预算6万，目标25-35岁女性消费者，需要公众号深度种草文章和小红书种草笔记",
        )
        agent_b = BaseAgent(role_id="account_manager", record_id=record_b)
        injected_text = await agent_b._load_experiences(TEST_SCENE)
        if not injected_text.strip():
            report.fail("第三层闭环对比", "第二次运行前未加载到历史经验")
            return
        output_b = await agent_b.run()

        print("\n============ 第三层闭环对比报告 ============")
        print(f"记录 A: {record_a}")
        print(f"记录 B: {record_b}")
        print(f"经验池数量: {saved_count_before} -> {saved_count_after}")
        print(f"第一次输出长度: {len(output_a or '')}")
        print(f"第二次输出长度: {len(output_b or '')}")
        print(f"第二次注入预览: {(injected_text or '')[:160]}")
        print("============================================")

        report.ok(
            "第三层闭环对比",
            f"经验数 {saved_count_before}->{saved_count_after}，第二次已注入历史经验",
        )
    finally:
        try:
            deleted_projects, deleted_experiences = await cleanup_compare_data(client)
            print(
                f"闭环测试清理完成: 项目 {deleted_projects} 条, 经验 {deleted_experiences} 条"
            )
        except Exception as exc:
            print(f"闭环测试清理失败: {type(exc).__name__}: {exc}")


async def main() -> None:
    print("=" * 60)
    print("经验系统测试")
    print("=" * 60)

    print("\n--- 第一层: 本地逻辑 ---\n")
    for name, fn in [
        ("置信度打分", test_confidence_scoring),
        ("wiki 写入", test_wiki_write),
        ("Hook 自省", test_hook_reflect),
    ]:
        try:
            await fn()
        except Exception as exc:
            report.fail(name, f"{type(exc).__name__}: {exc}")

    print("\n--- 第二层: 经验池联调 ---\n")
    try:
        await test_bitable_experience()
    except Exception as exc:
        report.fail("Bitable 经验池", f"{type(exc).__name__}: {exc}")

    print("\n--- 第三层: 闭环对比 ---\n")
    try:
        await test_evolution_compare()
    except Exception as exc:
        report.fail("第三层闭环对比", f"{type(exc).__name__}: {exc}")

    all_passed = report.summary()
    raise SystemExit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
