from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def find_ffmpeg() -> str | None:
    candidates = list((PROJECT_ROOT / "tools" / "ffmpeg").rglob("ffmpeg.exe"))
    if candidates:
        return str(candidates[0])
    return shutil.which("ffmpeg")


def find_ffprobe() -> str | None:
    candidates = list((PROJECT_ROOT / "tools" / "ffmpeg").rglob("ffprobe.exe"))
    if candidates:
        return str(candidates[0])
    return shutil.which("ffprobe")
