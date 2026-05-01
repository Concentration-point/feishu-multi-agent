"""Live test for account_manager ask_human in the BBQ brief scenario.

Run:
  python tests/test_account_manager_bbq.py

Optional env vars:
  ASK_HUMAN_TEST_TIMEOUT=60
  ASK_HUMAN_REQUIRE_REPLY=1
  ASK_HUMAN_START_WS=1

Notes:
  - This script uses a real Bitable record and a real LLM call.
  - It verifies that account_manager can trigger ask_human.
  - For reply collection, it prefers WebSocket and also adds a polling fallback.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


CLIENT_NAME_RAW = "BBQ ask_human live test"
BRIEF_TEXT = (
    "We are a new neighborhood BBQ shop. We want more late-night foot traffic after the holiday. "
    "The brief intentionally omits budget, main platforms, and available assets. "
    "Please produce the brief analysis first."
)
PROJECT_TYPE = "日常运营"
BRAND_TONE = "烟火气，年轻，真实，不要空喊口号"
DEPT_STYLE = "Do not invent budget, platform, or asset constraints."

MIN_BRIEF_ANALYSIS_CHARS = 300
EXPECTED_TOOLS = ["read_project", "search_web", "search_knowledge", "ask_human"]


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


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class LiveLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.react_iterations = 0
        self.tools: list[str] = []
        self.ask_human_called = False
        self.ask_human_card_sent = False
        self.ask_human_reply_received = False
        self.ask_human_reply_choice = ""
        self.choice_card_sent = False
        self.choice_card_message_id = ""
        self.ws_started = False
        self.ws_reply_matched = False
        self.poll_reply_matched = False
        self.recent_lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.recent_lines.append(message)
        if len(self.recent_lines) > 30:
            self.recent_lines.pop(0)

        logger_name = record.name

        if "调用工具" in message:
            tool_name = self._extract_tool_name(message)
            self.react_iterations += 1
            if tool_name and tool_name not in self.tools:
                self.tools.append(tool_name)
            if tool_name == "ask_human":
                self.ask_human_called = True
            print(f"[react] {message}", flush=True)
            return

        if logger_name == "tools.ask_human":
            if "卡片已发出" in message:
                self.ask_human_card_sent = True
            if "收到选择" in message:
                self.ask_human_reply_received = True
                self.ask_human_reply_choice = self._extract_choice(message)
            print(f"[ask_human] {message}", flush=True)
            return

        if logger_name == "feishu.im" and "send_choice_card OK" in message:
            self.choice_card_sent = True
            self.choice_card_message_id = self._extract_message_id(message)
            print(f"[im] {message}", flush=True)
            return

        if logger_name == "feishu.card_actions":
            print(f"[card_actions] {message}", flush=True)
            return

        if logger_name == "feishu.ws_client":
            if "WebSocket daemon 线程已启动" in message or "长连接已建立" in message:
                self.ws_started = True
            if "用户回复已匹配选项" in message:
                self.ws_reply_matched = True
            print(f"[ws] {message}", flush=True)
            return

    @staticmethod
    def _extract_tool_name(message: str) -> str:
        tail = message.split("调用工具", 1)[-1].strip()
        return tail.split("(", 1)[0].strip()

    @staticmethod
    def _extract_choice(message: str) -> str:
        match = re.search(r"choice=([\"'].*?[\"'])", message)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_message_id(message: str) -> str:
        match = re.search(r"msg_id=([^\s]+)", message)
        return match.group(1) if match else ""


async def heartbeat(
    started_at: float,
    stop_event: asyncio.Event,
    handler: LiveLogHandler,
    interval_seconds: float = 10.0,
) -> None:
    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                elapsed = time.perf_counter() - started_at
                wait_state = "waiting_reply" if handler.ask_human_card_sent and not handler.ask_human_reply_received else "running"
                print(
                    f"[heartbeat] elapsed={elapsed:.0f}s state={wait_state} tools={handler.tools}",
                    flush=True,
                )
    except asyncio.CancelledError:
        pass


async def poll_for_reply(
    *,
    stop_event: asyncio.Event,
    handler: LiveLogHandler,
    chat_id: str,
    start_time_unix: str,
    interval_seconds: float = 4.0,
) -> None:
    """Fallback for live test: poll messages and resolve ask_human manually."""
    from feishu.card_actions import resolve_by_message
    from feishu.im import FeishuIMClient

    im = FeishuIMClient()
    seen_message_ids: set[str] = set()

    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                continue
            except asyncio.TimeoutError:
                pass

            if not handler.ask_human_card_sent or handler.ask_human_reply_received:
                continue

            try:
                messages = await im.list_messages(
                    chat_id=chat_id,
                    start_time=start_time_unix,
                    page_size=20,
                )
            except Exception as exc:
                print(f"[poll] list_messages failed: {exc}", flush=True)
                continue

            for msg in messages:
                message_id = msg.get("message_id", "")
                if message_id:
                    if message_id in seen_message_ids:
                        continue
                    seen_message_ids.add(message_id)

                if not im.is_user_message(msg):
                    continue

                text = im.extract_text_from_message(msg).strip()
                if not text:
                    continue

                print(f"[poll] user message: {text!r}", flush=True)
                if resolve_by_message(chat_id, text):
                    handler.poll_reply_matched = True
                    print(f"[poll] matched reply: {text!r}", flush=True)
                    return
    except asyncio.CancelledError:
        pass


async def main() -> int:
    env_path = ROOT / ".env"
    file_values = load_env_file(env_path)

    llm_key = os.getenv("LLM_API_KEY") or file_values.get("LLM_API_KEY", "")
    feishu_app_id = os.getenv("FEISHU_APP_ID") or file_values.get("FEISHU_APP_ID", "")
    feishu_app_secret = os.getenv("FEISHU_APP_SECRET") or file_values.get("FEISHU_APP_SECRET", "")
    feishu_chat_id = os.getenv("FEISHU_CHAT_ID") or file_values.get("FEISHU_CHAT_ID", "")
    project_table_id = os.getenv("PROJECT_TABLE_ID") or file_values.get("PROJECT_TABLE_ID", "")

    missing = [
        name
        for name, value in [
            ("LLM_API_KEY", llm_key),
            ("FEISHU_APP_ID", feishu_app_id),
            ("FEISHU_APP_SECRET", feishu_app_secret),
            ("FEISHU_CHAT_ID", feishu_chat_id),
            ("PROJECT_TABLE_ID", project_table_id),
        ]
        if not value
    ]
    if missing:
        print(f"Skip live test: missing config {missing}")
        return 0

    ask_human_timeout = int(os.getenv("ASK_HUMAN_TEST_TIMEOUT", "60"))
    require_reply = env_bool("ASK_HUMAN_REQUIRE_REPLY", default=False)
    start_ws = env_bool("ASK_HUMAN_START_WS", default=True)
    os.environ["ASK_HUMAN_TIMEOUT"] = str(ask_human_timeout)

    from agents.base import BaseAgent
    from config import FIELD_MAP_PROJECT as FP
    from feishu import card_actions, ws_client
    from feishu.bitable import BitableClient
    from memory.project import ProjectMemory

    test_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    test_client_name = f"[TEST-{test_tag}] {CLIENT_NAME_RAW}"

    payload = {
        FP["client_name"]: test_client_name,
        FP["brief"]: BRIEF_TEXT,
        FP["project_type"]: PROJECT_TYPE,
        FP["brand_tone"]: BRAND_TONE,
        FP["dept_style"]: DEPT_STYLE,
        FP["status"]: "待处理",
    }

    print("=" * 72)
    print("account_manager BBQ ask_human live test")
    print("=" * 72)
    print(f"client_name      : {test_client_name}")
    print(f"project_type     : {PROJECT_TYPE}")
    print(f"ask_human_timeout: {ask_human_timeout}s")
    print(f"start_ws         : {start_ws}")
    print(f"require_reply    : {require_reply}")
    print("-" * 72)
    print(f"brief            : {BRIEF_TEXT}")
    print("-" * 72)
    print("Reply to the Feishu group with a plain number like 1 / 2 / 3.")
    print("This script now uses both WebSocket and polling fallback.")
    print("-" * 72)

    handler = LiveLogHandler()
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))

    logger_names = [
        "agents.base",
        "tools.ask_human",
        "feishu.im",
        "feishu.card_actions",
        "feishu.ws_client",
    ]
    loggers: dict[str, tuple[logging.Logger, int]] = {}
    for logger_name in logger_names:
        logger_obj = logging.getLogger(logger_name)
        loggers[logger_name] = (logger_obj, logger_obj.level)
        logger_obj.setLevel(logging.INFO)
        logger_obj.addHandler(handler)

    card_actions.set_main_loop(asyncio.get_running_loop())
    if start_ws:
        ws_client.start()
        await asyncio.sleep(2.0)
        print(f"ws_client_alive   : {ws_client.is_alive()}")
        print("-" * 72)

    started_at = time.perf_counter()
    start_time_unix = str(int(time.time()))
    client = BitableClient()
    record_id = await client.create_record(project_table_id, payload)
    print(f"record_id         : {record_id}")
    print("-" * 72)

    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat(started_at, stop_event, handler))
    poll_task = asyncio.create_task(
        poll_for_reply(
            stop_event=stop_event,
            handler=handler,
            chat_id=feishu_chat_id,
            start_time_unix=start_time_unix,
        )
    )

    error: Exception | None = None
    final_output = ""

    try:
        agent = BaseAgent(role_id="account_manager", record_id=record_id)
        final_output = await agent.run()
    except Exception as exc:
        error = exc
    finally:
        stop_event.set()
        try:
            await heartbeat_task
        except Exception:
            pass
        try:
            await poll_task
        except Exception:
            pass
        for logger_obj, old_level in loggers.values():
            logger_obj.removeHandler(handler)
            logger_obj.setLevel(old_level)
        card_actions.shutdown()

    elapsed = time.perf_counter() - started_at

    if error is not None:
        print(f"[error] Agent run failed: {type(error).__name__}: {error}")
        print(f"[hint] record kept in Bitable: {record_id}")
        return 1

    pm = ProjectMemory(record_id)
    project = await pm.load()
    brief_analysis = project.brief_analysis or ""
    status_value = project.status or ""

    checks: list[tuple[str, bool, str]] = [
        ("ask_human called", handler.ask_human_called, f"tools={handler.tools}"),
        ("choice card sent", handler.choice_card_sent, f"msg_id={handler.choice_card_message_id or '(none)'}"),
        ("brief_analysis written", len(brief_analysis) >= MIN_BRIEF_ANALYSIS_CHARS, f"len={len(brief_analysis)}"),
    ]

    if start_ws:
        checks.append(("ws_client started", handler.ws_started, f"is_alive={ws_client.is_alive()}"))
    if require_reply:
        checks.append((
            "ask_human got reply",
            handler.ask_human_reply_received,
            f"choice={handler.ask_human_reply_choice or '(none)'} ws={handler.ws_reply_matched} poll={handler.poll_reply_matched}",
        ))

    missing_tools = [tool for tool in EXPECTED_TOOLS if tool not in handler.tools]
    checks.append(("required tools present", not missing_tools, f"missing={missing_tools or '(none)'}"))

    print()
    print("=" * 72)
    print("verification")
    print("=" * 72)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}: {detail}")

    print("-" * 72)
    print(f"status            : {status_value}")
    print(f"react_iterations  : {handler.react_iterations}")
    print(f"tools             : {handler.tools}")
    print(f"ask_human_called  : {handler.ask_human_called}")
    print(f"card_sent         : {handler.choice_card_sent}")
    print(f"reply_received    : {handler.ask_human_reply_received}")
    print(f"reply_via_ws      : {handler.ws_reply_matched}")
    print(f"reply_via_poll    : {handler.poll_reply_matched}")
    print(f"final_output_head : {(final_output or '(empty)')[:200]}")
    print(f"brief_head        : {brief_analysis[:300] if brief_analysis else '(empty)'}")
    print(f"elapsed           : {elapsed:.1f}s")
    print(f"record_id         : {record_id}")
    print("=" * 72)

    failed = [name for name, ok, _detail in checks if not ok]
    if failed:
        print(f"[result] FAIL -> {failed}")
        return 1

    print("[result] PASS")
    return 0


def _run() -> int:
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[abort] user interrupted test")
        return 130


if __name__ == "__main__":
    raise SystemExit(_run())
