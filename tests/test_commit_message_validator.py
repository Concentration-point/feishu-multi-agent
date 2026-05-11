from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_commit_message import validate_message_text


def test_accepts_chinese_subject_and_body():
    message = """文档：固化中文提交说明规则

说明：
- 新增本地 commit-msg hook，提交前校验中文标题和正文。
- 阻断连续问号和 mojibake 乱码，避免再次污染 GitHub 提交列表。
- 验证命令：python -m pytest tests/test_commit_message_validator.py -q。
"""

    assert validate_message_text(message) == []


def test_rejects_english_only_title():
    errors = validate_message_text(
        """fix webhook auth

说明：
- 补充测试。
"""
    )

    assert any("提交标题必须包含中文" in error for error in errors)


def test_rejects_missing_body():
    errors = validate_message_text("修复：强化 Webhook 鉴权\n")

    assert any("提交说明必须包含中文正文" in error for error in errors)


def test_rejects_question_mark_corruption():
    errors = validate_message_text(
        """??????????? fail-closed

说明：
- 模拟已经被 PowerShell 写坏的提交标题。
"""
    )

    assert any("连续问号" in error for error in errors)


def test_rejects_mojibake_corruption():
    errors = validate_message_text(
        """æ–‡æ¡£ï¼šè®°å½•åŸºçº¿æ—§å¤±è´¥

说明：
- 模拟 UTF-8 被错误解码后的 mojibake。
"""
    )

    assert any("mojibake" in error for error in errors)
