from __future__ import annotations

from pathlib import Path

from .common import ensure_dir, fmt_date, is_video_file, read_json, write_json


def _video_files(root: Path) -> list[Path]:
    return [p for p in sorted(root.iterdir()) if is_video_file(p)]


def _build_name(path: Path, index: int, rule: str) -> str:
    values = {
        "stem": path.stem,
        "ext": path.suffix.lstrip("."),
        "index": f"{index:02d}",
        "mtime_date": fmt_date(path.stat().st_mtime),
    }
    new_stem = rule.format(**values)
    return f"{new_stem}{path.suffix.lower()}"


def preview_rename(directory: str, rule: str) -> dict:
    root = Path(directory).resolve()
    files = _video_files(root)
    changes = []
    conflicts = []
    seen_targets = set()

    for i, path in enumerate(files, start=1):
        new_name = _build_name(path, i, rule)
        action = "keep" if new_name == path.name else "rename"
        changes.append({"old": path.name, "new": new_name, "action": action})

        if new_name in seen_targets:
            conflicts.append(f"目标文件名重复：{new_name}")
        seen_targets.add(new_name)

        target = root / new_name
        if target.exists() and target.name != path.name:
            conflicts.append(f"目标已存在：{new_name}")

    status = "conflict" if conflicts else "ok"
    return {
        "status": status,
        "directory": str(root),
        "rule": rule,
        "changes": changes,
        "conflicts": conflicts,
        "message": "先看预览，别一把梭直接改。" if not conflicts else "发现命名冲突，先别动。",
    }


def apply_rename(directory: str, rule: str) -> dict:
    preview = preview_rename(directory, rule)
    root = Path(directory).resolve()
    if preview["conflicts"]:
        return preview

    changes = [c for c in preview["changes"] if c["action"] == "rename"]
    temp_moves = []

    for idx, change in enumerate(changes, start=1):
        old_path = root / change["old"]
        tmp_path = root / f".__vwb_tmp__{idx}{old_path.suffix.lower()}"
        old_path.rename(tmp_path)
        temp_moves.append((tmp_path, root / change["new"]))

    for tmp_path, final_path in temp_moves:
        tmp_path.rename(final_path)

    log_path = ensure_dir(root / "logs") / "rename-log.json"
    log_data = {
        "status": "ok",
        "directory": str(root),
        "rule": rule,
        "renamed": [{"old": c["old"], "new": c["new"]} for c in changes],
    }
    write_json(log_path, log_data)

    return {
        "status": "ok",
        "directory": str(root),
        "rule": rule,
        "changes": preview["changes"],
        "conflicts": [],
        "log_path": str(log_path),
        "message": f"改完了，{len(changes)} 个文件已落盘，回滚日志也写好了。",
    }


def rollback_rename(directory: str, map_path: str) -> dict:
    root = Path(directory).resolve()
    data = read_json(Path(map_path).resolve())
    renamed = data.get("renamed", [])

    temp_moves = []
    for idx, item in enumerate(renamed, start=1):
        current = root / item["new"]
        old_path = root / item["old"]
        if not current.exists():
            continue
        tmp_path = root / f".__vwb_rb__{idx}{current.suffix.lower()}"
        current.rename(tmp_path)
        temp_moves.append((tmp_path, old_path))

    for tmp_path, old_path in temp_moves:
        tmp_path.rename(old_path)

    return {
        "status": "ok",
        "directory": str(root),
        "changes": [
            {"old": item["new"], "new": item["old"], "action": "rollback"}
            for item in renamed
        ],
        "conflicts": [],
        "message": f"回滚完了，恢复 {len(temp_moves)} 个文件名。",
    }
