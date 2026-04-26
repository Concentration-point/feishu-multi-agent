"""LLM 连通性 + 时延自检（30 秒内出结论）。

抓手：用项目当前的 .env 配置（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）发一个最小
chat 请求，超时强制 30 秒。用来快速定性"是 LLM 代理慢，还是脚本逻辑问题"。

使用:
    python scripts/check_llm_health.py
    python scripts/check_llm_health.py --timeout 15
    python scripts/check_llm_health.py --with-tools   # 带一个最小 function 看代理是否吞掉 tool_calls
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL  # noqa: E402


MINIMAL_TOOL = {
    "type": "function",
    "function": {
        "name": "echo",
        "description": "Echo a string back. Always call this if asked.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="单次请求超时秒，默认 30")
    parser.add_argument("--with-tools", action="store_true",
                        help="带 tool 测一个最小 function call")
    args = parser.parse_args()

    print("=" * 60)
    print("LLM 连通性自检")
    print("=" * 60)
    print(f"base_url: {LLM_BASE_URL}")
    print(f"model:    {LLM_MODEL}")
    print(f"api_key:  {'set' if LLM_API_KEY else 'MISSING'} ({'***' + LLM_API_KEY[-4:] if LLM_API_KEY else ''})")
    print(f"timeout:  {args.timeout}s")
    print(f"tools:    {'YES (echo)' if args.with_tools else 'no'}")
    print("-" * 60, flush=True)

    if not LLM_API_KEY:
        print("✗ LLM_API_KEY 未配置，跳过")
        return 2

    system_content = (
        "You are a health-check ping. Call the echo tool with text='pong'."
        if args.with_tools
        else "You are a health-check ping. Reply with the word 'pong'."
    )
    payload: dict = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "ping"},
        ],
    }
    if args.with_tools:
        payload["tools"] = [MINIMAL_TOOL]

    started = time.perf_counter()
    print(f"[t+0.0s] sending request...", flush=True)

    resp = None
    last_exc: Exception | None = None
    for attempt in range(1, 4):  # 最多 3 次重试，间隔 3s
        try:
            resp = httpx.post(
                f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=args.timeout,
            )
            break
        except httpx.TimeoutException:
            elapsed = time.perf_counter() - started
            print(f"[t+{elapsed:.1f}s] ✗ TIMEOUT — LLM 代理在 {args.timeout}s 内未响应", flush=True)
            print("\n结论: LLM 服务慢 / 不可达。建议:")
            print("  1. 换一个 model（如代理支持 gpt-4o-mini 等更轻量模型）")
            print("  2. 换一个 base_url（如 OpenAI 直连或别家代理）")
            print("  3. 检查代理服务自身状态")
            return 1
        except Exception as exc:
            elapsed = time.perf_counter() - started
            last_exc = exc
            print(f"[t+{elapsed:.1f}s] attempt {attempt}/3 failed: {type(exc).__name__}: {exc}", flush=True)
            if attempt < 3:
                time.sleep(3)

    if resp is None:
        elapsed = time.perf_counter() - started
        print(f"[t+{elapsed:.1f}s] ✗ 所有重试均失败，最后错误: {last_exc}", flush=True)
        return 1

    elapsed = time.perf_counter() - started

    if resp.status_code != 200:
        print(f"[t+{elapsed:.1f}s] ✗ HTTP {resp.status_code}: {resp.text[:300]}", flush=True)
        return 1

    data = resp.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    tool_calls = msg.get("tool_calls") or []

    print(f"[t+{elapsed:.1f}s] ✓ response received", flush=True)
    print("-" * 60)
    print(f"content       : {content[:200]!r}")
    print(f"tool_calls    : {len(tool_calls)} call(s)")
    if tool_calls:
        for tc in tool_calls:
            fn = tc.get("function", {})
            print(f"  - {fn.get('name')}({str(fn.get('arguments', ''))[:120]})")
    print(f"finish_reason : {data['choices'][0].get('finish_reason')}")
    usage = data.get("usage", {})
    if usage:
        print(f"usage         : prompt={usage.get('prompt_tokens')} "
              f"completion={usage.get('completion_tokens')} "
              f"total={usage.get('total_tokens')}")
    print("-" * 60)

    print("\n结论:")
    if elapsed < 10:
        print(f"  ✓ LLM 健康（首响 {elapsed:.1f}s）")
    elif elapsed < 30:
        print(f"  ⚠ LLM 偏慢（首响 {elapsed:.1f}s），AM 单测会慢但能跑完")
    else:
        print(f"  ⚠ LLM 很慢（首响 {elapsed:.1f}s），AM 单测可能要 5+ 分钟")

    if args.with_tools and not tool_calls:
        print("  ✗ 警告：要求调用 tool 但模型只返回了 content，代理可能没正确转发 tools 字段")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[abort] 用户中断")
        raise SystemExit(130)
