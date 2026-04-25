from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import KNOWLEDGE_BASE_PATH
from tools.write_wiki import strip_frontmatter


def analyze_markdown(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    body = strip_frontmatter(raw)
    issues: list[str] = []

    has_frontmatter = raw.startswith("---\n")
    has_html_comment = bool(re.search(r"<!--.*?-->", raw, flags=re.S))
    has_long_blank_runs = bool(re.search(r"\n{3,}", raw))
    has_h1 = body.lstrip().startswith("# ")
    has_body_section = "## 正文" in body
    has_meta_section = "## 元信息" in body
    has_nul = "\x00" in raw

    if has_html_comment:
        issues.append("html_comment")
    if has_long_blank_runs:
        issues.append("too_many_blank_lines")
    if has_nul:
        issues.append("nul_byte")
    if not has_h1:
        issues.append("missing_h1")
    if not has_meta_section:
        issues.append("missing_meta_section")
    if not has_body_section:
        issues.append("missing_body_section")

    return {
        "path": path.as_posix(),
        "size": len(raw),
        "has_frontmatter": has_frontmatter,
        "has_html_comment": has_html_comment,
        "has_long_blank_runs": has_long_blank_runs,
        "has_nul": has_nul,
        "has_h1": has_h1,
        "has_meta_section": has_meta_section,
        "has_body_section": has_body_section,
        "issues": issues,
    }


def main() -> int:
    base = Path(KNOWLEDGE_BASE_PATH)
    targets = sorted((base / "wiki").rglob("*.md"))
    report = {
        "total": 0,
        "problematic": 0,
        "files": [],
    }

    for path in targets:
        if path.name.startswith("_"):
            continue
        item = analyze_markdown(path)
        report["total"] += 1
        if item["issues"]:
            report["problematic"] += 1
        report["files"].append(item)

    out_path = base / "wiki_audit_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"AUDIT_TOTAL={report['total']}")
    print(f"AUDIT_PROBLEMATIC={report['problematic']}")
    print(f"REPORT={out_path}")
    print("TOP_ISSUES:")
    for item in report["files"]:
        if item["issues"]:
            print(f"- {item['path']}: {', '.join(item['issues'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
