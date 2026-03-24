from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .backend import find_ffmpeg, find_ffprobe
from .common import ensure_dir, is_video_file, write_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASR_PYTHON = PROJECT_ROOT / ".venv_asr" / "Scripts" / "python.exe"


TRANSCRIBE_SNIPPET = r'''
import json, sys
from faster_whisper import WhisperModel

video_path = sys.argv[1]
audio_path = sys.argv[2]
out_json = sys.argv[3]
out_md = sys.argv[4]

model = WhisperModel("tiny", device="cpu", compute_type="int8")
segments, info = model.transcribe(audio_path, language="zh")
segments = list(segments)

payload = {
    "file": video_path,
    "status": "ok",
    "language": getattr(info, "language", None),
    "duration": getattr(info, "duration", None),
    "segments": [
        {
            "start": s.start,
            "end": s.end,
            "text": s.text.strip(),
        }
        for s in segments
    ]
}

with open(out_json, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

with open(out_md, "w", encoding="utf-8") as f:
    f.write("# Transcript\n\n")
    f.write(f"- file: {video_path}\n")
    f.write(f"- status: ok\n")
    f.write(f"- language: {payload['language']}\n\n")
    for item in payload["segments"]:
        f.write(f"- [{item['start']:.2f}-{item['end']:.2f}] {item['text']}\n")
'''


def _has_local_asr() -> bool:
    if not ASR_PYTHON.exists():
        return False
    cmd = [str(ASR_PYTHON), "-c", "import importlib.util as u; print(bool(u.find_spec('faster_whisper'))) "]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and "True" in result.stdout


def _extract_audio(video_path: Path, audio_path: Path, ffmpeg_path: str) -> tuple[bool, str]:
    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "ffmpeg failed")[:2000]
    return True, "ok"


def _transcribe_with_venv(video_path: Path, audio_path: Path, out_json: Path, out_md: Path) -> tuple[bool, str]:
    cmd = [
        str(ASR_PYTHON),
        "-c",
        TRANSCRIBE_SNIPPET,
        str(video_path.name),
        str(audio_path),
        str(out_json),
        str(out_md),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "transcribe failed")[:3000]
        return False, err
    return True, "ok"


def transcript_run(directory: str) -> dict:
    root = Path(directory).resolve()
    transcripts_dir = ensure_dir(root / "transcripts")
    audio_dir = ensure_dir(root / "audio_tmp")
    items = []
    missing = []

    ffmpeg_path = find_ffmpeg()
    ffprobe_path = find_ffprobe()
    venv_faster_whisper = _has_local_asr()

    if not ffmpeg_path:
        missing.append("ffmpeg")
    if not ffprobe_path:
        missing.append("ffprobe")
    if not venv_faster_whisper:
        missing.append("faster-whisper(.venv_asr)")

    if missing:
        for path in sorted(root.iterdir()):
            if not is_video_file(path):
                continue
            out_json = transcripts_dir / f"{path.stem}.json"
            out_md = transcripts_dir / f"{path.stem}.md"
            data = {
                "file": path.name,
                "path": str(path),
                "status": "blocked",
                "engine": None,
                "reason": f"缺少 backend：{', '.join(missing)}",
            }
            write_json(out_json, data)
            out_md.write_text(
                "# Transcript Placeholder\n\n"
                f"- file: {path.name}\n"
                f"- status: blocked\n"
                f"- reason: {data['reason']}\n",
                encoding="utf-8",
            )
            items.append({"file": path.name, "status": "blocked", "json": str(out_json), "markdown": str(out_md)})

        return {
            "status": "blocked",
            "directory": str(root),
            "backend": {
                "ffmpeg": bool(ffmpeg_path),
                "ffprobe": bool(ffprobe_path),
                "venv_faster_whisper": venv_faster_whisper,
                "ffmpeg_path": ffmpeg_path,
                "ffprobe_path": ffprobe_path,
            },
            "missing": missing,
            "items": items,
            "message": "backend 还没齐。",
        }

    for path in sorted(root.iterdir()):
        if not is_video_file(path):
            continue

        out_json = transcripts_dir / f"{path.stem}.json"
        out_md = transcripts_dir / f"{path.stem}.md"
        audio_path = audio_dir / f"{path.stem}.wav"

        ok_audio, audio_msg = _extract_audio(path, audio_path, ffmpeg_path)
        if not ok_audio:
            payload = {
                "file": path.name,
                "status": "error",
                "step": "extract_audio",
                "reason": audio_msg,
            }
            write_json(out_json, payload)
            out_md.write_text(
                "# Transcript Error\n\n"
                f"- file: {path.name}\n"
                f"- status: error\n"
                f"- step: extract_audio\n"
                f"- reason: {audio_msg}\n",
                encoding="utf-8",
            )
            items.append({"file": path.name, "status": "error", "json": str(out_json), "markdown": str(out_md)})
            continue

        ok_transcribe, transcribe_msg = _transcribe_with_venv(path, audio_path, out_json, out_md)
        if not ok_transcribe:
            payload = {
                "file": path.name,
                "status": "error",
                "step": "transcribe",
                "reason": transcribe_msg,
            }
            write_json(out_json, payload)
            out_md.write_text(
                "# Transcript Error\n\n"
                f"- file: {path.name}\n"
                f"- status: error\n"
                f"- step: transcribe\n"
                f"- reason: {transcribe_msg}\n",
                encoding="utf-8",
            )
            items.append({"file": path.name, "status": "error", "json": str(out_json), "markdown": str(out_md)})
            continue

        items.append({"file": path.name, "status": "ok", "json": str(out_json), "markdown": str(out_md)})

    overall = "ok" if items and all(i["status"] == "ok" for i in items) else "partial"
    return {
        "status": overall,
        "directory": str(root),
        "backend": {
            "ffmpeg": bool(ffmpeg_path),
            "ffprobe": bool(ffprobe_path),
            "venv_faster_whisper": venv_faster_whisper,
            "ffmpeg_path": ffmpeg_path,
            "ffprobe_path": ffprobe_path,
        },
        "missing": [],
        "items": items,
        "message": "真转录链路已经跑了；成没成看每个文件状态。",
    }
