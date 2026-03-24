from __future__ import annotations

from pathlib import Path

from .common import ensure_dir


def _extract_bullets(text: str) -> list[str]:
    bullets = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("- "):
            bullets.append(s[2:].strip())
    return bullets


def mindmap_build(directory: str) -> dict:
    root = Path(directory).resolve()
    transcripts_dir = root / "transcripts"
    mindmaps_dir = ensure_dir(root / "mindmaps")

    items = []
    transcript_files = sorted(transcripts_dir.glob("*.md")) if transcripts_dir.exists() else []

    for transcript in transcript_files:
        text = transcript.read_text(encoding="utf-8")
        bullets = _extract_bullets(text)
        title = transcript.stem

        md_outline = [f"# {title}"]
        if bullets:
            md_outline.extend([f"- {b}" for b in bullets])
        else:
            md_outline.append("- 暂无可用结构，等真实 transcript 接上后再抽主题")

        mermaid = ["mindmap", f"  root(({title}))"]
        if bullets:
            for b in bullets:
                mermaid.append(f"    {b}")
        else:
            mermaid.append("    transcript placeholder")

        md_path = mindmaps_dir / f"{title}.md"
        mmd_path = mindmaps_dir / f"{title}.mmd"
        md_path.write_text("\n".join(md_outline) + "\n", encoding="utf-8")
        mmd_path.write_text("\n".join(mermaid) + "\n", encoding="utf-8")
        items.append({"source": str(transcript), "markdown": str(md_path), "mermaid": str(mmd_path), "status": "ok"})

    status = "ok" if items else "empty"
    return {
        "status": status,
        "directory": str(root),
        "items": items,
        "message": "思维导图骨架生成完了。" if items else "还没找到 transcript，脑图先无从下手。",
    }
