"""工具调用成功率分析脚本（T005/T008）。

用法:
    python scripts/analyze_tool_stats.py                    # 分析 logs/raw_run.log
    python scripts/analyze_tool_stats.py logs/my.log       # 指定日志文件
    python scripts/analyze_tool_stats.py logs/my.log --extract-jsonl  # 从日志提取 TOOL_STAT 行写 JSONL
    python scripts/analyze_tool_stats.py logs/tool_calls.jsonl --jsonl  # 结构化日志模式
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def detect_encoding(path: Path) -> str:
    """依次尝试常见编码，返回第一个能解出中文的编码。"""
    for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312"]:
        try:
            text = path.read_text(encoding=enc)
            if "调用工具" in text or "tool" in text.lower():
                return enc
        except Exception:
            continue
    return "utf-8"


def analyze_plain_log(log_path: Path) -> dict:
    """从普通日志文件分析工具调用（基于 logger.info 行）。

    统计口径（A类技术失败）：
    - 失败 = 行中含 '工具执行错误' 或 '工具.*执行异常'
    - 成功 = 行中含 '调用工具 {name}(' 且无对应失败行
    """
    enc = detect_encoding(log_path)
    print(f"[INFO] 使用编码: {enc}")
    content = log_path.read_text(encoding=enc, errors="replace")
    lines = content.splitlines()

    # 工具调用次数
    call_pattern = re.compile(r"调用工具 (\w+)\(")
    all_calls = call_pattern.findall(content)
    call_counter = Counter(all_calls)

    # 失败行
    error_lines = [l for l in lines if "工具执行错误" in l or "执行异常" in l]
    error_tool_pattern = re.compile(r"工具 (\w+) 执行异常")
    error_counter: Counter = Counter()
    error_details: dict[str, list[str]] = defaultdict(list)
    for line in error_lines:
        m = error_tool_pattern.search(line)
        tool = m.group(1) if m else "unknown"
        error_counter[tool] += 1
        # 提取报错类型
        exc_match = re.search(r"工具执行错误: (\w+Error|\w+Exception|[A-Z]\w+):", line)
        exc_type = exc_match.group(1) if exc_match else "Unknown"
        error_details[tool].append(exc_type)

    # 每个工具的统计
    stats = {}
    all_tools = set(call_counter.keys()) | set(error_counter.keys())
    for tool in sorted(all_tools):
        total = call_counter.get(tool, 0)
        fail = error_counter.get(tool, 0)
        ok = total - fail
        rate = (ok / total * 100) if total > 0 else 0.0
        stats[tool] = {
            "total": total,
            "ok": ok,
            "fail": fail,
            "success_rate": round(rate, 1),
            "top_errors": list(set(error_details.get(tool, [])))[:3],
        }

    return {
        "source": str(log_path),
        "encoding": enc,
        "total_lines": len(lines),
        "total_calls": len(all_calls),
        "total_errors": len(error_lines),
        "tools": stats,
    }


def analyze_jsonl(log_path: Path) -> dict:
    """从结构化 JSONL 日志分析（T005 改造后产出的格式）。"""
    records = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "ok": 0, "fail": 0, "durations": [], "errors": []})
    for r in records:
        tool = r.get("tool", "unknown")
        stats[tool]["total"] += 1
        if r.get("success"):
            stats[tool]["ok"] += 1
        else:
            stats[tool]["fail"] += 1
            if r.get("error"):
                stats[tool]["errors"].append(r["error"])
        if r.get("duration_ms") is not None:
            stats[tool]["durations"].append(r["duration_ms"])

    result = {}
    for tool, s in sorted(stats.items()):
        total = s["total"]
        ok = s["ok"]
        fail = s["fail"]
        rate = (ok / total * 100) if total > 0 else 0.0
        avg_ms = (sum(s["durations"]) / len(s["durations"])) if s["durations"] else None
        result[tool] = {
            "total": total,
            "ok": ok,
            "fail": fail,
            "success_rate": round(rate, 1),
            "avg_ms": round(avg_ms, 0) if avg_ms else None,
            "top_errors": list(set(s["errors"]))[:3],
        }

    return {
        "source": str(log_path),
        "total_records": len(records),
        "tools": result,
    }


def print_report(data: dict) -> None:
    """打印 Markdown 格式报告。"""
    print(f"\n# 工具调用成功率报告")
    print(f"\n- 数据源: `{data['source']}`")
    print(f"- 总调用次数: {data.get('total_calls', data.get('total_records', '?'))}")
    print(f"- 总失败次数: {data.get('total_errors', '?')}")

    tools = data["tools"]
    if not tools:
        print("\n> 暂无工具调用数据")
        return

    print("\n## 工具成功率明细\n")
    print("| 工具名 | 总调用 | 成功 | 失败 | 成功率 | 平均耗时 | 主要报错 |")
    print("|--------|--------|------|------|--------|----------|--------|")
    for tool, s in sorted(tools.items(), key=lambda x: x[1]["success_rate"]):
        avg = f"{s.get('avg_ms', '-')}ms" if s.get("avg_ms") else "-"
        errors = ", ".join(s["top_errors"]) if s["top_errors"] else "-"
        mark = "[FAIL]" if s["success_rate"] < 80 else ("[WARN]" if s["success_rate"] < 95 else "[OK]  ")
        print(f"| {tool} | {s['total']} | {s['ok']} | {s['fail']} | {mark} {s['success_rate']}% | {avg} | {errors} |")

    # Top 3 最高风险工具
    risky = sorted(tools.items(), key=lambda x: x[1]["success_rate"])[:3]
    print("\n## Top 3 高风险工具（按成功率升序）\n")
    for i, (tool, s) in enumerate(risky, 1):
        print(f"{i}. **{tool}** — 成功率 {s['success_rate']}%，失败 {s['fail']} 次，报错类型: {', '.join(s['top_errors']) or '无'}")


def extract_jsonl(log_path: Path) -> Path:
    """从日志里提取 TOOL_STAT 行，写到同名 .jsonl 文件。"""
    enc = detect_encoding(log_path)
    out_path = log_path.with_suffix(".jsonl")
    count = 0
    with open(log_path, encoding=enc, errors="replace") as fin, \
         open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            if "TOOL_STAT: " not in line:
                continue
            try:
                json_part = line.split("TOOL_STAT: ", 1)[1].strip()
                json.loads(json_part)  # 验证合法
                fout.write(json_part + "\n")
                count += 1
            except Exception:
                continue
    print(f"[INFO] 提取 {count} 条 TOOL_STAT 记录 → {out_path}")
    return out_path


def main():
    args = sys.argv[1:]
    use_jsonl = "--jsonl" in args
    extract = "--extract-jsonl" in args
    paths = [a for a in args if not a.startswith("--")]
    log_path = Path(paths[0]) if paths else Path("logs/raw_run.log")

    if not log_path.exists():
        print(f"[ERROR] 文件不存在: {log_path}")
        sys.exit(1)

    if extract:
        log_path = extract_jsonl(log_path)
        use_jsonl = True

    data = analyze_jsonl(log_path) if use_jsonl else analyze_plain_log(log_path)
    print_report(data)

    # 同时输出 JSON 供后续消费
    out = log_path.with_suffix(".stats.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[INFO] 结构化数据已写入: {out}")


if __name__ == "__main__":
    main()
