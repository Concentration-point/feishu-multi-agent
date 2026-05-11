"""Validate project commit messages before Git creates the commit object."""

from __future__ import annotations

import re
import sys
from pathlib import Path


CJK_RE = re.compile(r"[\u4e00-\u9fff]")
MOJIBAKE_RE = re.compile(r"(?:æ|è|é|å|ç|ã|ï¼|Â|�)")
QUESTION_RUN_RE = re.compile(r"\?{4,}")


def _non_comment_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if not line.startswith("#")]


def validate_message_text(text: str) -> list[str]:
    lines = _non_comment_lines(text)
    while lines and not lines[0].strip():
        lines.pop(0)

    if not lines:
        return ["提交说明不能为空。"]

    subject = lines[0].strip()
    body_lines = [line.strip() for line in lines[1:] if line.strip()]
    errors: list[str] = []

    if len(subject) < 6:
        errors.append("提交标题过短，请用一句中文说明本次提交做了什么。")

    if not CJK_RE.search(subject):
        errors.append("提交标题必须包含中文，不能使用英文-only 标题。")

    if not body_lines:
        errors.append("提交说明必须包含中文正文，写清原因、关键改动和验证结果。")
    elif not CJK_RE.search("\n".join(body_lines)):
        errors.append("提交正文必须包含中文说明。")

    if QUESTION_RUN_RE.search(text):
        errors.append("提交说明包含连续问号，疑似中文已被 PowerShell 或终端编码损坏。")

    if MOJIBAKE_RE.search(text):
        errors.append("提交说明包含 mojibake 乱码特征，请重新用 UTF-8 message 文件提交。")

    return errors


def validate_message_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ["提交说明文件不是合法 UTF-8，请重新保存为 UTF-8。"]

    return validate_message_text(text)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：python scripts/validate_commit_message.py <commit-msg-file>", file=sys.stderr)
        return 2

    errors = validate_message_file(Path(argv[1]))
    if not errors:
        return 0

    print("提交说明未通过项目规则：", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    print("", file=sys.stderr)
    print("建议使用 UTF-8 message 文件提交，例如：git commit -F commit-message.txt", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
