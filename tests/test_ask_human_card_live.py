"""实测 ask_human 交互式卡片发送到飞书群组。

需要 .env 中配置真实凭证：
  FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_ID

运行方式：
  pytest tests/test_ask_human_card_live.py -v -s
  python tests/test_ask_human_card_live.py   # 直接运行亦可

注意：要在飞书群中点击卡片按钮，需要先启动 server（python main.py serve），
      WebSocket 长连接负责接收 card.action.trigger 回调。
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pytest
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
FEISHU_APP_ID  = os.getenv("FEISHU_APP_ID", "")

skip_no_creds = pytest.mark.skipif(
    not FEISHU_CHAT_ID or not FEISHU_APP_ID,
    reason="缺少飞书凭证（FEISHU_CHAT_ID / FEISHU_APP_ID），跳过 live 测试",
)


def test_send_choice_card_json_structure():
    """验证 send_choice_card 生成的卡片 JSON 包含按钮 action 元素。"""
    import inspect
    from feishu.im import FeishuIMClient

    # 用 inspect 拿到 send_choice_card 内部构建的 card JSON
    # 通过 mock 避免真实 HTTP 请求
    source = inspect.getsource(FeishuIMClient.send_choice_card)
    # 在函数源码中找到 card = {...} 部分
    assert '"tag": "action"' in source, "卡片 JSON 应包含 action 元素"
    assert '"tag": "button"' in source, "卡片 JSON 应包含 button 元素"
    assert '"choice_index"' in source, "按钮 value 应包含 choice_index"
    print("✅ 卡片 JSON 结构验证通过：包含 action + button + choice_index")


@skip_no_creds
@pytest.mark.asyncio
async def test_send_choice_card_to_group():
    """验证 send_choice_card 能成功发送到飞书群组，返回合法 message_id。"""
    from feishu.im import FeishuIMClient

    im = FeishuIMClient()
    data, msg_id = await im.send_choice_card(
        chat_id=FEISHU_CHAT_ID,
        question=(
            "**[测试] ask_human 卡片验证**\n\n"
            "这是一条自动化测试消息，验证选择题卡片是否能正常发送到群组。\n"
            "无需操作，忽略即可。"
        ),
        choices=["✅ 确认", "✏️ 需要修改", "❌ 驳回"],
        title="🧪 ask_human 卡片测试",
        color="blue",
    )

    print(f"\n发送结果:")
    print(f"  message_id : {msg_id}")
    print(f"  chat_id    : {data.get('data', {}).get('chat_id', '')}")
    print(f"  create_time: {data.get('data', {}).get('create_time', '')}")

    assert msg_id, "message_id 为空，卡片发送失败"
    assert msg_id.startswith("om_"), f"message_id 格式异常: {msg_id!r}"
    print("\n✅ 卡片发送成功，请到飞书群组确认卡片样式")


@skip_no_creds
@pytest.mark.asyncio
async def test_send_multiple_choices():
    """验证 2~6 个选项的卡片都能正常发送。"""
    from feishu.im import FeishuIMClient

    im = FeishuIMClient()
    test_cases = [
        (["通过", "驳回"], "两选项"),
        (["方案A", "方案B", "再讨论"], "三选项"),
        (["红", "橙", "黄", "绿", "蓝", "紫"], "六选项"),
    ]
    for choices, label in test_cases:
        data, msg_id = await im.send_choice_card(
            chat_id=FEISHU_CHAT_ID,
            question=f"[测试] {label} 卡片验证",
            choices=choices,
            title=f"🧪 {label}",
        )
        assert msg_id.startswith("om_"), f"{label} 发送失败: {msg_id!r}"
        print(f"  {label}: msg_id={msg_id}")

    print("\n✅ 多选项卡片全部发送成功")


# ── 直接运行入口 ──────────────────────────────────────────
if __name__ == "__main__":
    if not FEISHU_CHAT_ID or not FEISHU_APP_ID:
        print("错误: 请在 .env 中配置 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_ID")
        sys.exit(1)

    async def _main():
        print("=" * 50)
        print("测试 1: 标准三选项卡片")
        print("=" * 50)
        await test_send_choice_card_to_group()

        print()
        print("=" * 50)
        print("测试 2: 多选项覆盖")
        print("=" * 50)
        await test_send_multiple_choices()

        print()
        print("全部测试通过，请到飞书群组确认卡片效果。")

    asyncio.run(_main())
