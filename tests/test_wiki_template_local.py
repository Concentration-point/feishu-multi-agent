from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.write_wiki import build_wiki_document, prepare_docx_markdown


def main() -> int:
    doc = build_wiki_document(
        title="测试标题",
        content="## 场景\nabc\n\n## 策略\ndef\n\n<!-- hidden -->\n\n## 结果\nxyz",
        category="电商大促",
        role="copywriter",
        confidence=0.88,
    )
    cleaned = prepare_docx_markdown(doc)

    assert "created:" not in cleaned, "frontmatter should be stripped"
    assert "<!-- hidden -->" not in cleaned, "html comments should be removed"
    assert cleaned.startswith("# 测试标题"), "cleaned markdown should keep title"
    assert "## 正文" in cleaned, "cleaned markdown should keep body section"
    print("PASS: wiki template + docx markdown cleanup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
