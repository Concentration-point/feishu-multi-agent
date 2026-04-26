"""Process-wide asyncio runtime tweaks.

Imported once by config.py so every entry point (main.py / tests/* / scripts/* /
demo/*) inherits the fix automatically — no per-script changes required.

What it does
------------
On Windows, switch the default asyncio event loop policy from ProactorEventLoop
to WindowsSelectorEventLoopPolicy.

Why
---
Python 3.12 on Windows defaults to ProactorEventLoop (IOCP-based). When the user
hits Ctrl+C while there are pending overlapped socket operations (httpx, openai
streaming, feishu API calls), `loop.close()` calls `GetQueuedCompletionStatus`
which waits forever for those operations — the process appears to hang after
KeyboardInterrupt. See cpython#87474 and related issues.

SelectorEventLoop is select-based, has no IOCP, exits cleanly on Ctrl+C, and is
fully compatible with httpx / openai / FastAPI / uvicorn used in this project.

Caveat
------
SelectorEventLoop on Windows does NOT support `asyncio.create_subprocess_*`.
This project has zero such usage today (verified via grep). If subprocess is
introduced later, revisit this choice — possible mitigations: per-call loop
override, or restoring Proactor with a robust SIGINT handler.
"""

from __future__ import annotations

import asyncio
import sys


def _install_windows_selector_loop() -> None:
    if sys.platform != "win32":
        return
    policy = asyncio.get_event_loop_policy()
    if isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy):
        return
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_install_windows_selector_loop()
