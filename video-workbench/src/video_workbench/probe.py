from __future__ import annotations

from pathlib import Path

from .common import is_video_file


def probe_directory(directory: str) -> dict:
    root = Path(directory).resolve()
    if not root.exists() or not root.is_dir():
        return {
            "status": "error",
            "directory": str(root),
            "message": "目录不存在，或者它根本不是目录。",
            "items": [],
        }

    items = []
    for path in sorted(root.iterdir()):
        if not is_video_file(path):
            continue
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "duration_sec": None,
                "has_transcript": False,
                "has_docx": False,
                "has_mindmap": False,
            }
        )

    return {
        "status": "ok",
        "directory": str(root),
        "total_files": len(list(root.iterdir())),
        "video_files": len(items),
        "items": items,
        "message": f"扫完了，找到 {len(items)} 个视频文件。",
    }
