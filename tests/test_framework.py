import asyncio
import importlib
import pkgutil
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


EXPECTED_TOOLS = [
    "read_project",
    "write_project",
    "update_status",
    "list_content",
    "create_content",
    "batch_create_content",
    "write_content",
    "send_message",
    "search_knowledge",
    "get_experience",
]


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.total = 7

    def ok(self, title: str, reason: str = "") -> None:
        self.passed += 1
        print(f"✓ {title}")
        if reason:
            print(f"  原因: {reason}")

    def fail(self, title: str, reason: str = "") -> None:
        print(f"✗ {title}")
        if reason:
            print(f"  原因: {reason}")

    def summary(self) -> int:
        print(f"\n汇总: {self.passed}/{self.total} 项通过。")
        return 0 if self.passed == self.total else 1


def print_block(title: str, content: str) -> None:
    print(f"\n--- {title} ---")
    print(content)
    print(f"--- 结束: {title} ---")


def schema_errors(schema: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["SCHEMA 不是 dict"]
    if schema.get("type") != "function":
        errors.append("SCHEMA.type 不是 'function'")
    fn = schema.get("function")
    if not isinstance(fn, dict):
        errors.append("SCHEMA.function 不是 dict")
        return errors
    for key in ("name", "description", "parameters"):
        if key not in fn:
            errors.append(f"SCHEMA.function 缺少 {key}")
    if "parameters" in fn and not isinstance(fn["parameters"], dict):
        errors.append("SCHEMA.function.parameters 不是 dict")
    return errors


def find_candidate_soul_files() -> list[str]:
    return [
        str(path.relative_to(ROOT))
        for path in (ROOT / "agents").rglob("*.md")
        if "_shared" not in path.parts
    ]


def test_tool_registry(report: Report) -> None:
    from tools import ToolRegistry

    registry = ToolRegistry()
    names = sorted(registry.tool_names)
    print_block("已注册工具", "\n".join(names) + f"\n总数: {len(names)}")

    missing = [name for name in EXPECTED_TOOLS if name not in names]
    extra = [name for name in names if name not in EXPECTED_TOOLS]

    module_errors: list[str] = []
    import tools as tools_pkg

    for _, mod_name, _ in pkgutil.iter_modules(tools_pkg.__path__):
        if mod_name.startswith("_"):
            continue
        mod = importlib.import_module(f"tools.{mod_name}")
        schema = getattr(mod, "SCHEMA", None)
        execute = getattr(mod, "execute", None)
        if not isinstance(schema, dict):
            module_errors.append(f"{mod_name}: SCHEMA 不是 dict")
            continue
        if not callable(execute):
            module_errors.append(f"{mod_name}: execute 不可调用")
        errs = schema_errors(schema)
        if errs:
            module_errors.append(f"{mod_name}: {'; '.join(errs)}")

    if missing or module_errors:
        parts: list[str] = []
        if missing:
            parts.append(f"缺少工具: {missing}")
        if extra:
            parts.append(f"额外工具: {extra}")
        if module_errors:
            parts.append("；".join(module_errors))
        report.fail("1. ToolRegistry 工具发现", " | ".join(parts))
        return

    detail = f"发现 {len(names)} 个工具，全部具备 SCHEMA/execute，schema 格式有效"
    if extra:
        detail += f"，额外工具: {extra}"
    report.ok("1. ToolRegistry 工具发现", detail)


def test_soul_parse(report: Report) -> list[str]:
    from agents.base import parse_soul

    soul_path = ROOT / "agents" / "account_manager" / "soul.md"
    if not soul_path.exists():
        candidates = find_candidate_soul_files()
        report.fail(
            "2. soul.md 解析",
            f"缺少目标文件 {soul_path.relative_to(ROOT)}；候选 md 文件: {candidates}",
        )
        return []

    text = soul_path.read_text(encoding="utf-8")
    soul = parse_soul(text)
    errors: list[str] = []

    if not isinstance(soul.role_id, str) or soul.role_id != "account_manager":
        errors.append(f"role_id 异常: {soul.role_id!r}")
    if not isinstance(soul.name, str) or not soul.name.strip():
        errors.append("name 为空")
    if not isinstance(soul.tools, list) or len(soul.tools) == 0:
        errors.append(f"tools 异常: {soul.tools!r}")
    if not isinstance(soul.max_iterations, int) or soul.max_iterations <= 0:
        errors.append(f"max_iterations 异常: {soul.max_iterations!r}")
    if not isinstance(soul.body, str) or not soul.body.strip():
        errors.append("body 为空")
    if "---" in soul.body:
        errors.append("body 中仍包含 '---'，frontmatter 未正确分离")

    print_block("soul frontmatter", str(asdict(soul)))
    print_block("soul body 前 200 字符", soul.body[:200])

    if errors:
        report.fail("2. soul.md 解析", "；".join(errors))
        return soul.tools if isinstance(soul.tools, list) else []

    report.ok(
        "2. soul.md 解析",
        f"role_id={soul.role_id}, name={soul.name}, tools={len(soul.tools)}, max_iterations={soul.max_iterations}",
    )
    return soul.tools


def test_shared_knowledge(report: Report) -> None:
    shared_dir = ROOT / "agents" / "_shared"
    required = ["company.md", "sop.md", "quality_standards.md"]

    if not shared_dir.exists():
        report.fail("3. _shared/ 共享知识加载", "agents/_shared 目录不存在")
        return

    present = {path.name: path for path in sorted(shared_dir.glob("*.md"))}
    missing = [name for name in required if name not in present]

    total_chars = 0
    lines: list[str] = []
    empty_files: list[str] = []

    for name, path in present.items():
        content = path.read_text(encoding="utf-8")
        chars = len(content.strip())
        total_chars += chars
        lines.append(f"{name}: {chars} 字")
        if not content.strip():
            empty_files.append(name)

    print_block("共享知识文件统计", "\n".join(lines) + f"\n总字数: {total_chars}")

    problems: list[str] = []
    if missing:
        problems.append(f"缺少文件: {missing}")
    if empty_files:
        problems.append(f"空文件: {empty_files}")

    if problems:
        report.fail("3. _shared/ 共享知识加载", "；".join(problems))
        return

    report.ok("3. _shared/ 共享知识加载", f"文件齐全，总字数 {total_chars}")


def test_tool_permission_filter(report: Report, soul_tools: list[str]) -> None:
    from tools import ToolRegistry

    soul_path = ROOT / "agents" / "account_manager" / "soul.md"
    if not soul_path.exists():
        report.fail(
            "4. 工具权限过滤",
            "无法读取 agents/account_manager/soul.md，无法按角色声明过滤工具",
        )
        return

    registry = ToolRegistry()
    filtered = registry.get_tools(soul_tools)
    filtered_names = [
        tool["function"]["name"]
        for tool in filtered
        if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
    ]
    undeclared = [name for name in filtered_names if name not in soul_tools]
    schema_failures: list[str] = []

    for tool in filtered:
        errs = schema_errors(tool)
        if errs:
            name = tool.get("function", {}).get("name", "<unknown>")
            schema_failures.append(f"{name}: {'; '.join(errs)}")

    problems: list[str] = []
    if len(filtered) != len(soul_tools):
        problems.append(f"返回数量 {len(filtered)} != 声明数量 {len(soul_tools)}")
    if "batch_create_content" in filtered_names:
        problems.append("出现未声明工具 batch_create_content")
    if undeclared:
        problems.append(f"包含未声明工具: {undeclared}")
    if schema_failures:
        problems.append("；".join(schema_failures))

    print_block("角色声明工具", "\n".join(soul_tools))
    print_block("过滤后工具", "\n".join(filtered_names))

    if problems:
        report.fail("4. 工具权限过滤", " | ".join(problems))
        return

    report.ok("4. 工具权限过滤", f"过滤后 {len(filtered)} 个工具，和 soul.md 声明一致")


def test_system_prompt(report: Report) -> None:
    try:
        from agents.base import BaseAgent
        from memory.project import BriefProject
    except Exception as exc:
        report.fail("5. System prompt 装配", f"导入失败: {type(exc).__name__}: {exc}")
        return

    try:
        agent = BaseAgent(role_id="account_manager", record_id="test_record_fake")
    except Exception as exc:
        report.fail("5. System prompt 装配", f"实例化失败: {type(exc).__name__}: {exc}")
        return

    dummy = BriefProject(record_id="test_record_fake")
    try:
        prompt = agent._build_system_prompt(dummy)
    except Exception as exc:
        report.fail("5. System prompt 装配", f"装配失败: {type(exc).__name__}: {exc}")
        return

    sections = prompt.split("\n\n---\n\n")
    lines = [
        f"段落 {idx + 1}: {len(section)} 字, 标题={section.splitlines()[0] if section.splitlines() else '<空>'}"
        for idx, section in enumerate(sections)
    ]
    print_block("system prompt 结构", "\n".join(lines))

    problems: list[str] = []
    if agent.shared_knowledge and agent.shared_knowledge not in prompt:
        problems.append("未包含 _shared 内容")
    if agent.soul.body and agent.soul.body not in prompt:
        problems.append("未包含 soul body")

    if problems:
        report.fail("5. System prompt 装配", "；".join(problems))
        return

    report.ok("5. System prompt 装配", f"共 {len(sections)} 段，包含 shared + soul 内容")


def test_status_machine(report: Report) -> None:
    try:
        mod = importlib.import_module("tools.update_status")
    except Exception as exc:
        report.fail("6. 状态机校验", f"导入 update_status 失败: {type(exc).__name__}: {exc}")
        return

    transitions = getattr(mod, "_TRANSITIONS", None)
    execute = getattr(mod, "execute", None)
    if not isinstance(transitions, dict):
        report.fail("6. 状态机校验", "未找到本地状态机定义 _TRANSITIONS")
        return

    ok_flow = "解读中" in transitions.get("待处理", [])
    bad_flow = "已完成" not in transitions.get("待处理", [])
    execute_note = "execute 真实调用依赖 Bitable，本项仅校验本地状态机表"

    if ok_flow and bad_flow:
        report.ok("6. 状态机校验", f"待处理 -> 解读中 合法；待处理 -> 已完成 非法。{execute_note}")
        return

    details = []
    if not ok_flow:
        details.append("待处理 -> 解读中 未被允许")
    if not bad_flow:
        details.append("待处理 -> 已完成 被错误允许")
    if not callable(execute):
        details.append("execute 不可调用")
    report.fail("6. 状态机校验", "；".join(details) or execute_note)


async def test_real_tools(report: Report) -> None:
    from tools import AgentContext
    from tools.send_message import execute as send_message_execute
    from tools.search_knowledge import execute as search_knowledge_execute
    from tools.get_experience import execute as get_experience_execute

    context = AgentContext(
        record_id="test_record_fake",
        project_name="test_project",
        role_id="account_manager",
    )

    try:
        send_result = await send_message_execute({"message": "framework smoke test"}, context)
        search_result = await search_knowledge_execute({"query": "双十一 精华液"}, context)
        exp_result = await get_experience_execute({"role_id": "account_manager", "category": "电商大促"}, context)
    except Exception as exc:
        report.fail("7. 工具行为验证", f"执行异常: {type(exc).__name__}: {exc}")
        return

    print_block(
        "工具返回",
        "\n".join(
            [
                f"send_message: {send_result}",
                f"search_knowledge: {search_result}",
                f"get_experience: {exp_result}",
            ]
        ),
    )

    problems: list[str] = []
    if not isinstance(send_result, str):
        problems.append("send_message 未返回字符串")
    if not isinstance(search_result, str):
        problems.append("search_knowledge 未返回字符串")
    if not isinstance(exp_result, str):
        problems.append("get_experience 未返回字符串")
    # 真实实现：send_message 应返回发送/记录结果
    if not send_result.strip():
        problems.append("send_message 返回为空")
    # 真实实现：search_knowledge 应返回搜索结果或"未找到"
    if not search_result.strip():
        problems.append("search_knowledge 返回为空")
    # 真实实现：get_experience 应返回经验内容或"未找到"
    if not exp_result.strip():
        problems.append("get_experience 返回为空")

    if problems:
        report.fail("7. 工具行为验证", "；".join(problems))
        return

    report.ok("7. 工具行为验证", "三个工具均可本地执行并返回非空结果")


async def main() -> int:
    report = Report()

    test_tool_registry(report)
    soul_tools = test_soul_parse(report)
    test_shared_knowledge(report)
    test_tool_permission_filter(report, soul_tools)
    test_system_prompt(report)
    test_status_machine(report)
    await test_real_tools(report)

    return report.summary()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
