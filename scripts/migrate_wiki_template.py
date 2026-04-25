from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import KNOWLEDGE_BASE_PATH
from tools.write_wiki import build_wiki_document, strip_frontmatter

ROLE_PREFIXES = {
    "account_manager": "account_manager",
    "strategist": "strategist",
    "copywriter": "copywriter",
    "reviewer": "reviewer",
    "project_manager": "project_manager",
}


def infer_role_from_name(stem: str) -> str:
    lower = stem.lower()
    for prefix, role in ROLE_PREFIXES.items():
        if lower.startswith(prefix):
            return role
    return ""


def normalize_body(text: str) -> str:
    text = strip_frontmatter(text)
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def migrate_file(path: Path, apply: bool = False) -> tuple[bool, str]:
    raw = path.read_text(encoding="utf-8")
    body = normalize_body(raw)
    category = path.parent.name
    title = path.stem
    role = infer_role_from_name(title)

    if body.startswith("# ") and "## 元信息" in body and "## 正文" in body:
        return False, "already_new_template"

    new_doc = build_wiki_document(
        title=title,
        content=body,
        category=category,
        role=role,
        confidence=0.0,
    )

    if apply:
        path.write_text(new_doc, encoding="utf-8")
    return True, "migrated"


def main() -> int:
    apply = "--apply" in sys.argv
    wiki_dir = Path(KNOWLEDGE_BASE_PATH) / "wiki"
    total = 0
    changed = 0
    skipped = 0

    for path in sorted(wiki_dir.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        total += 1
        did_change, reason = migrate_file(path, apply=apply)
        if did_change:
            changed += 1
            print(f"MIGRATE {path}: {reason}")
        else:
            skipped += 1
            print(f"SKIP    {path}: {reason}")

    mode = "APPLY" if apply else "DRY_RUN"
    print(f"MODE={mode} TOTAL={total} CHANGED={changed} SKIPPED={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
