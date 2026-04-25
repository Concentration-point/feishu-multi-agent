import asyncio
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


class ReActLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.iterations = 0
        self.tools: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        if "调用工具" in message:
            self.iterations += 1
            marker = f"第 {self.iterations} 轮"
            print(f"{marker}: {message}")
            tool_name = message.split("调用工具", 1)[-1].strip()
            tool_name = tool_name.split("(", 1)[0].strip()
            if tool_name and tool_name not in self.tools:
                self.tools.append(tool_name)
        elif "输出最终结果" in message or "循环结束" in message:
            print(message)


async def main() -> int:
    env_path = ROOT / ".env"
    file_values = load_env_file(env_path)
    llm_key = os.getenv("LLM_API_KEY") or file_values.get("LLM_API_KEY", "")
    feishu_app_id = os.getenv("FEISHU_APP_ID") or file_values.get("FEISHU_APP_ID", "")

    if not env_path.exists() or not llm_key or not feishu_app_id:
        print("跳过 LLM 集成测试：缺少 .env 配置")
        return 0

    from agents.base import BaseAgent
    from config import FIELD_MAP_PROJECT as FP, PROJECT_TABLE_ID
    from feishu.bitable import BitableClient
    from memory.project import ProjectMemory

    client = BitableClient()
    payload = {
        FP["client_name"]: "阶段二测试客户",
        FP["brief"]: "双十一电商大促，主推新款精华液，预算5万，目标25-35岁女性消费者，需要公众号深度种草文章和小红书种草笔记",
        FP["project_type"]: "电商大促",
        FP["brand_tone"]: "科技感、专业可信赖、避免过度促销感",
        FP["dept_style"]: "所有产出必须包含明确的用户行动号召(CTA)",
        FP["status"]: "待处理",
    }

    print("========== 阶段二集成测试开始 ==========")
    started_at = time.perf_counter()

    record_id = await client.create_record(PROJECT_TABLE_ID, payload)
    print(f"测试记录创建成功: {record_id}")

    handler = ReActLogHandler()
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    agent_logger = logging.getLogger("agents.base")
    old_level = agent_logger.level
    agent_logger.setLevel(logging.INFO)
    agent_logger.addHandler(handler)

    final_output = ""
    error: Exception | None = None

    try:
        agent = BaseAgent(role_id="account_manager", record_id=record_id)
        final_output = await agent.run()
        print("\n最终输出:")
        print(final_output or "(空)")
    except Exception as exc:
        error = exc
    finally:
        agent_logger.removeHandler(handler)
        agent_logger.setLevel(old_level)

    if error is not None:
        print(f"✗ Agent 运行失败: {type(error).__name__}: {error}")
        print(f"测试记录 {record_id} 已保留在表格中，可手动查看或删除")
        return 1

    pm = ProjectMemory(record_id)
    proj = await pm.load()
    brief_analysis = proj.brief_analysis or ""
    status_value = proj.status or ""

    brief_ok = len(brief_analysis) > 100
    status_ok = status_value == "解读中"

    print("\n验证结果:")
    if brief_ok:
        print(f"✓ Brief 解读字段已写入 ({len(brief_analysis)} 字)")
    else:
        print(f"✗ Brief 解读字段异常: 长度={len(brief_analysis)} 内容预览={brief_analysis[:120]}")
    if status_ok:
        print('✓ 状态字段已更新为"解读中"')
    else:
        print(f'✗ 状态字段异常: 当前值="{status_value}"')

    elapsed = time.perf_counter() - started_at
    print("\n========== 阶段二集成测试报告 ==========")
    print(f"测试记录 ID: {record_id}")
    print(f"ReAct 循环轮次: {handler.iterations} 轮")
    print(f"调用工具列表: {', '.join(handler.tools) if handler.tools else '(未记录到工具调用)'}")
    print(f"Brief 解读字段: {'✓ 已写入' if brief_ok else '✗ 未达标'} ({len(brief_analysis)} 字)")
    status_text = '✓ 已更新为"解读中"' if status_ok else f'✗ 当前为"{status_value}"'
    print(f"状态字段: {status_text}")
    print(f"总耗时: {elapsed:.1f} 秒")
    print("========================================")
    print(f"测试记录 {record_id} 已保留在表格中，可手动查看或删除")

    return 0 if brief_ok and status_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
