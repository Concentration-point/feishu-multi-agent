from __future__ import annotations

from pathlib import Path

from .common import ensure_dir, is_video_file, write_json


def transcript_run(directory: str) -> dict:
    root = Path(directory).resolve()
    transcripts_dir = ensure_dir(root / "transcripts")
    items = []
    missing = []

    try:
        import shutil

        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
    except Exception:
        ffmpeg_path = None
        ffprobe_path = None

    try:
        import importlib.util as importlib_util

        has_faster_whisper = bool(importlib_util.find_spec("faster_whisper"))
        has_whisper = bool(importlib_util.find_spec("whisper"))
    except Exception:
        has_faster_whisper = False
        has_whisper = False

    if not ffmpeg_path:
        missing.append("ffmpeg")
    if not ffprobe_path:
        missing.append("ffprobe")
    if not (has_faster_whisper or has_whisper):
        missing.append("faster-whisper/whisper")

    for path in sorted(root.iterdir()):
        if not is_video_file(path):
            continue
        out_json = transcripts_dir / f"{path.stem}.json"
        out_md = transcripts_dir / f"{path.stem}.md"
        data = {
            "file": path.name,
            "path": str(path),
            "status": "blocked" if missing else "ready",
            "engine": None,
            "reason": (
                f"缺少 backend：{', '.join(missing)}，这版不乱装，先把结构搭稳。"
                if missing
                else "backend 就绪，下一步可以接真识别。"
            ),
        }
        write_json(out_json, data)
        out_md.write_text(
            "# Transcript Placeholder\n\n"
            f"- file: {path.name}\n"
            f"- status: {data['status']}\n"
            f"- reason: {data['reason']}\n",
            encoding="utf-8",
        )
        items.append(
            {
                "file": path.name,
                "status": data["status"],
                "json": str(out_json),
                "markdown": str(out_md),
            }
        )

    return {
        "status": "blocked" if missing else "ok",
        "directory": str(root),
        "backend": {
            "ffmpeg": bool(ffmpeg_path),
            "ffprobe": bool(ffprobe_path),
            "faster_whisper": has_faster_whisper,
            "whisper": has_whisper,
        },
        "missing": missing,
        "items": items,
        "message": (
            "文字稿入口已经接上，但真后端还没齐。"
            if missing
            else "backend 已齐，可以开始真转录。"
        ),
    }
