"""pytest 配置 — 排除脚本式验收测试，只收集真正的 pytest 用例。

脚本式测试（test_bitable / test_agent 等）设计为独立运行:
    python tests/test_bitable.py
    python tests/test_knowledge.py
    ...

pytest 只收集 test_webhook.py 等标准 pytest 用例。
"""

# 排除脚本式验收测试文件，避免 pytest 收集后因缺少 fixture / async 问题报错
collect_ignore = [
    "test_bitable.py",
    "test_agent.py",
    "test_agent_live.py",
    "test_framework.py",
    "test_knowledge.py",
    "test_experience.py",
    "test_im.py",
    "test_pipeline.py",
    "test_account_manager_bbq.py",
]
