"""人机交互 end-to-end 测试：发送带按钮的选择卡片 → 用户点击按钮 → WebSocket 回调解析。

双通道测试：
  1. card.action.trigger（主通道）—— 用户点击卡片按钮，WebSocket 实时接收
  2. im.message.receive_v1（兜底）—— 用户在群里打字回复数字或选项文字

运行方式（需要 .env 中配置飞书凭证）：
  python tests/test_ask_human_interactive_live.py

前置条件：
  1. 飞书开放平台已订阅 card.action.trigger 和 im.message.receive_v1 事件
  2. 机器人已开启"交互式卡片"功能
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
TIMEOUT = 120  # 秒

QUESTION = (
    "**[人机交互测试]** ask_human 按钮回调验证\n\n"
    "这是一条端到端测试消息。\n"
    "请**点击下方按钮**选择你的决定，脚本将通过 WebSocket 实时检测并打印你的回复。"
)
CHOICES = ["✅ 通过", "✏️ 需要修改", "❌ 驳回"]


async def run():
    if not FEISHU_CHAT_ID or not FEISHU_APP_ID:
        print("错误: 请在 .env 中配置 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_ID")
        sys.exit(1)

    from feishu.im import FeishuIMClient
    from feishu import card_actions
    from feishu import ws_client

    # ── 步骤 1: 绑定主循环 + 启动 WebSocket ──────────────
    card_actions.set_main_loop(asyncio.get_running_loop())
    ws_client.start()
    await asyncio.sleep(2)  # 等 WebSocket 建立连接

    if not ws_client.is_alive():
        # 给 WebSocket 线程一点时间完成 patch 导入
        await asyncio.sleep(3)
        if not ws_client.is_alive():
            print("错误: WebSocket 线程未启动，请检查 FEISHU_APP_ID/SECRET 和 lark-oapi 安装")
            sys.exit(1)

    print("WebSocket 长连接已启动 ✓")

    # ── 步骤 2: 注册 Future + 发送卡片 ──────────────────
    fut = card_actions.register(FEISHU_CHAT_ID, CHOICES)
    print(f"已注册 chat_id={FEISHU_CHAT_ID}，等待用户选择...")

    im = FeishuIMClient()
    print("发送选择卡片到飞书群组...")
    data, msg_id = await im.send_choice_card(
        chat_id=FEISHU_CHAT_ID,
        question=QUESTION,
        choices=CHOICES,
        title="🧪 按钮回调测试",
        color="orange",
    )
    print(f"卡片已发送  message_id={msg_id}")
    print()
    print("=" * 60)
    print("请到飞书群中点击卡片按钮选择：")
    for i, c in enumerate(CHOICES, 1):
        print(f"  {i}  →  {c}")
    print("（也可在群里直接回复数字或选项文字作为兜底）")
    print("=" * 60)
    print(f"等待中（超时 {TIMEOUT}s）...")
    print()

    # ── 步骤 3: 等待 Future（按钮回调 或 文字兜底） ──────
    try:
        choice = await asyncio.wait_for(fut, timeout=TIMEOUT)
        print("=" * 60)
        print(f"收到用户选择！")
        print(f"  选择结果 : {choice}")
        print("=" * 60)
        print()
        print("✅ 人机交互测试通过 — 按钮回调 + 文字兜底双通道验证完成")
    except asyncio.TimeoutError:
        card_actions.cancel_wait(FEISHU_CHAT_ID)
        print(f"超时（{TIMEOUT}s），未收到用户选择")
        sys.exit(1)
    finally:
        card_actions.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
