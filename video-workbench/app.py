from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.video_workbench.probe import probe_directory
from src.video_workbench.rename_ops import (
    apply_rename,
    preview_rename,
    rollback_rename,
)


def print_output(data, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    status = data.get("status")
    if status:
        print(f"status: {status}")

    if "directory" in data:
        print(f"directory: {data['directory']}")

    if data.get("items"):
        print("items:")
        for item in data["items"]:
            line = f"- {item['name']}"
            if item.get("duration_sec") is not None:
                line += f" | {item['duration_sec']}s"
            if item.get("size_bytes") is not None:
                line += f" | {item['size_bytes']} bytes"
            print(line)

    if data.get("changes"):
        print("changes:")
        for c in data["changes"]:
            print(f"- {c['old']} -> {c['new']} ({c['action']})")

    if data.get("conflicts"):
        print("conflicts:")
        for c in data["conflicts"]:
            print(f"- {c}")

    if data.get("message"):
        print(data["message"])

    if data.get("log_path"):
        print(f"log: {data['log_path']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video-workbench")
    parser.add_argument("--json", action="store_true", dest="as_json")

    subparsers = parser.add_subparsers(dest="command")

    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument("directory")

    rename_parser = subparsers.add_parser("rename")
    rename_sub = rename_parser.add_subparsers(dest="rename_command")

    rename_preview = rename_sub.add_parser("preview")
    rename_preview.add_argument("directory")
    rename_preview.add_argument("--rule", required=True)

    rename_apply = rename_sub.add_parser("apply")
    rename_apply.add_argument("directory")
    rename_apply.add_argument("--rule", required=True)

    rename_rollback = rename_sub.add_parser("rollback")
    rename_rollback.add_argument("directory")
    rename_rollback.add_argument("--map", required=True, dest="map_path")

    transcript_parser = subparsers.add_parser("transcript")
    transcript_sub = transcript_parser.add_subparsers(dest="transcript_command")
    transcript_run = transcript_sub.add_parser("run")
    transcript_run.add_argument("directory")

    docx_parser = subparsers.add_parser("docx")
    docx_sub = docx_parser.add_subparsers(dest="docx_command")
    docx_build = docx_sub.add_parser("build")
    docx_build.add_argument("directory")

    mindmap_parser = subparsers.add_parser("mindmap")
    mindmap_sub = mindmap_parser.add_subparsers(dest="mindmap_command")
    mindmap_build = mindmap_sub.add_parser("build")
    mindmap_build.add_argument("directory")

    pipeline_parser = subparsers.add_parser("pipeline")
    pipeline_sub = pipeline_parser.add_subparsers(dest="pipeline_command")
    pipeline_run = pipeline_sub.add_parser("run")
    pipeline_run.add_argument("directory")

    return parser


def not_implemented(feature: str, directory: str) -> dict:
    return {
        "status": "not_implemented",
        "directory": str(Path(directory).resolve()),
        "message": f"{feature} 还没接真实 backend，这版先把骨架搭稳。",
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "probe":
        result = probe_directory(args.directory)
        print_output(result, args.as_json)
        return 0

    if args.command == "rename":
        if args.rename_command == "preview":
            result = preview_rename(args.directory, args.rule)
            print_output(result, args.as_json)
            return 0
        if args.rename_command == "apply":
            result = apply_rename(args.directory, args.rule)
            print_output(result, args.as_json)
            return 0
        if args.rename_command == "rollback":
            result = rollback_rename(args.directory, args.map_path)
            print_output(result, args.as_json)
            return 0

    if args.command == "transcript" and args.transcript_command == "run":
        print_output(not_implemented("transcript.run", args.directory), args.as_json)
        return 0

    if args.command == "docx" and args.docx_command == "build":
        print_output(not_implemented("docx.build", args.directory), args.as_json)
        return 0

    if args.command == "mindmap" and args.mindmap_command == "build":
        print_output(not_implemented("mindmap.build", args.directory), args.as_json)
        return 0

    if args.command == "pipeline" and args.pipeline_command == "run":
        print_output(not_implemented("pipeline.run", args.directory), args.as_json)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
