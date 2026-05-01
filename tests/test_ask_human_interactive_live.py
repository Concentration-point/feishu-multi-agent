"""人机交互 end-to-end 测试：发送选择卡片 → 等待用户在飞书群回复 → 打印收到的选择。

不依赖 lark-oapi，使用现有 list_messages 轮询接收回复。

运行方式：
  python tests/test_ask_human_interactive_live.py

流程：
  1. 脚本发送选择题卡片到飞书群
  2. 你在飞书群回复数字（1 / 2 / 3）或选项文字
  3. 脚本检测到回复后打印结果并退出
"""
import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
FEISHU_APP_ID  = os.getenv("FEISHU_APP_ID", "")
POLL_INTERVAL  = 4    # 秒，轮询间隔
TIMEOUT        = 120  # 秒，等待超时

QUESTION = (
    "**[人机交互测试]** ask_human 收发验证\n\n"
    "这是一条端到端测试消息。\n"
    "请在下方选择你的决定，脚本将实时检测并打印你的回复。"
)
CHOICES = ["✅ 通过", "✏️ 需要修改", "❌ 驳回"]


def _extract_text(content_str: str) -> str:
    import json
    try:
        c = json.loads(content_str)
        if "text" in c:
            return c["text"].strip()
        if "content" in c:
            parts = []
            for line in c["content"]:
                for seg in line:
                    if seg.get("tag") == "text":
                        parts.append(seg.get("text", ""))
            return "".join(parts).strip()
    except Exception:
        pass
    return content_str.strip()


def _match_choice(text: str, choices: list[str]) -> str | None:
    """将用户回复文本匹配到选项，返回选项文字或 None。"""
    stripped = text.strip()

    # 数字匹配：1 / 2 / 3
    if stripped.isdigit():
        idx = int(stripped) - 1
        if 0 <= idx < len(choices):
            return choices[idx]

    # 完整文本匹配（大小写不敏感）
    lower = stripped.lower()
    for c in choices:
        if c.lower() == lower:
            return c

    # 包含匹配（兜底）
    for c in choices:
        if c.lower() in lower:
            return c

    return None


async def run():
    if not FEISHU_CHAT_ID or not FEISHU_APP_ID:
        print("错误: 请在 .env 中配置 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_ID")
        sys.exit(1)

    from feishu.im import FeishuIMClient
    im = FeishuIMClient()

    # ── 步骤 1: 发送选择卡片 ─────────────────────────────
    print("发送选择卡片到飞书群组...")
    data, msg_id = await im.send_choice_card(
        chat_id=FEISHU_CHAT_ID,
        question=QUESTION,
        choices=CHOICES,
        title="🧪 人机交互测试",
        color="orange",
    )
    send_time = str(int(time.time()))
    print(f"卡片已发送  message_id={msg_id}")
    print()
    print("=" * 50)
    print("请在飞书群中回复数字选择：")
    for i, c in enumerate(CHOICES, 1):
        print(f"  {i}  →  {c}")
    print("=" * 50)
    print(f"等待中（超时 {TIMEOUT}s）...")
    print()

    # ── 步骤 2: 轮询群消息，检测回复 ────────────────────
    elapsed = 0
    while elapsed < TIMEOUT:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        try:
            messages = await im.list_messages(
                chat_id=FEISHU_CHAT_ID,
                start_time=send_time,
                page_size=20,
            )
        except Exception as exc:
            print(f"  [轮询] 获取消息失败: {exc}，继续等待...")
            continue

        for msg in messages:
            # 只处理真人消息
            if not im.is_user_message(msg):
                continue
            # 跳过机器人自己发的卡片
            body = msg.get("body", {})
            if msg.get("msg_type") == "interactive":
                continue

            text = _extract_text(body.get("content", ""))
            if not text:
                continue

            matched = _match_choice(text, CHOICES)
            if matched is None:
                continue  # 不是有效选项，忽略（群聊噪音）

            # ── 步骤 3: 匹配成功，打印结果 ──────────────
            sender = msg.get("sender", {})
            open_id = sender.get("id", "unknown")
            print("=" * 50)
            print(f"收到回复！")
            print(f"  用户原文 : {text!r}")
            print(f"  匹配选项 : {matched}")
            print(f"  发送者   : {open_id}")
            print(f"  耗时     : {elapsed}s")
            print("=" * 50)
            print()
            print("✅  人机交互测试通过 — ask_human 收发链路验证完成")
            return

        print(f"  [轮询] 已等待 {elapsed}s，暂无有效回复...")

    print(f"超时（{TIMEOUT}s），未收到有效回复")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
