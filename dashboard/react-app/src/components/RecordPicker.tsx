/**
 * RecordPicker · 项目选择 / 回放切换器
 *
 * command-palette 密度：顶部搜索、分组列表、紧凑单行。
 * 一等公民：搜索框（随输随筛）+ "有回放记录"的项目（最高频的动作是再跑一遍 demo）。
 * 次要信息：record_id / 项目类型 / 事件数量 —— 这些靠 mono 小字贴在右侧。
 *
 * 键盘支持：↑↓ 选中，Enter 触发，Esc 关闭（Esc 由上层 App.tsx 接管）。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  RefreshCw,
  Search,
  History,
  Play,
  ArrowUp,
  ArrowDown,
  CornerDownLeft,
} from "lucide-react";
import type { RecordItem, RunInfo } from "../types";

interface RecordPickerProps {
  visible: boolean;
  onSelect: (recordId: string, clientName: string) => void;
  onReplay: (recordId: string, clientName: string) => void;
}

type Mode = "replay" | "run";

interface EnrichedRecord extends RecordItem {
  mode: Mode;
  run?: RunInfo;
}

export function RecordPicker({
  visible,
  onSelect,
  onReplay,
}: RecordPickerProps) {
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [runs, setRuns] = useState<Map<string, RunInfo>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const load = () => {
    setLoading(true);
    setError("");
    Promise.all([
      fetch("/api/records").then((r) => r.json()),
      fetch("/api/runs")
        .then((r) => r.json())
        .catch(() => ({ ok: false, runs: [] })),
    ])
      .then(([recordsData, runsData]) => {
        if (recordsData.ok && recordsData.records) {
          setRecords(recordsData.records);
        } else {
          setError(recordsData.error || "无项目记录");
        }
        if (runsData.ok && runsData.runs) {
          const runMap = new Map<string, RunInfo>();
          for (const run of runsData.runs as RunInfo[]) {
            runMap.set(run.record_id, run);
          }
          setRuns(runMap);
        }
      })
      .catch(() => setError("加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (visible) {
      load();
      setQuery("");
      setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 60);
    }
  }, [visible]);

  // 把 records + runs 合成单一列表，分组后筛选
  const { replays, runnable, filteredCount } = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filter = (r: RecordItem) => {
      if (!q) return true;
      return (
        r.client_name?.toLowerCase().includes(q) ||
        r.brief?.toLowerCase().includes(q) ||
        r.record_id?.toLowerCase().includes(q) ||
        r.project_type?.toLowerCase().includes(q)
      );
    };

    const replays: EnrichedRecord[] = [];
    const runnable: EnrichedRecord[] = [];
    for (const r of records) {
      if (!filter(r)) continue;
      const run = runs.get(r.record_id);
      if (run && run.status === "completed") {
        replays.push({ ...r, mode: "replay", run });
      } else {
        runnable.push({ ...r, mode: "run", run });
      }
    }
    return {
      replays,
      runnable,
      filteredCount: replays.length + runnable.length,
    };
  }, [records, runs, query]);

  // 统一扁平列表用于键盘导航
  const flat: EnrichedRecord[] = useMemo(
    () => [...replays, ...runnable],
    [replays, runnable],
  );

  useEffect(() => {
    setCursor((c) => Math.min(c, Math.max(0, flat.length - 1)));
  }, [flat.length]);

  const trigger = (rec: EnrichedRecord) => {
    if (rec.mode === "replay") onReplay(rec.record_id, rec.client_name);
    else onSelect(rec.record_id, rec.client_name);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (flat.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (c + 1) % flat.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (c - 1 + flat.length) % flat.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      trigger(flat[cursor]);
    }
  };

  // 滚动跟随 cursor
  useEffect(() => {
    const el = listRef.current?.querySelector(
      `[data-cursor-idx="${cursor}"]`,
    ) as HTMLElement | null;
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  if (!visible) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
      onKeyDown={onKeyDown}
      tabIndex={-1}
      style={{
        background: "var(--color-bg-1)",
        border: "1px solid var(--color-border)",
        borderRadius: "12px",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        maxHeight: "min(78vh, 720px)",
        boxShadow: "0 20px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(0,0,0,0.2)",
      }}
    >
      {/* 头部 · 搜索主角 */}
      <div
        style={{
          padding: "14px 20px",
          borderBottom: "1px solid var(--color-border)",
          display: "flex",
          alignItems: "center",
          gap: "12px",
          background: "var(--color-bg-0)",
        }}
      >
        <Search size={14} color="var(--color-text-3)" strokeWidth={2} />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索项目名、Brief、record_id..."
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            color: "var(--color-text-1)",
            fontSize: "14px",
            fontFamily: "var(--font-sans)",
            lineHeight: 1.4,
            letterSpacing: "0.01em",
          }}
        />
        <motion.button
          type="button"
          onClick={load}
          whileTap={{ rotate: 180 }}
          title="刷新"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "5px 10px",
            borderRadius: "6px",
            background: "var(--color-bg-2)",
            border: "1px solid var(--color-border)",
            color: "var(--color-text-2)",
            fontSize: "11px",
            fontFamily: "var(--font-mono)",
            cursor: "pointer",
          }}
        >
          <RefreshCw size={11} />
          刷新
        </motion.button>
        <span
          className="font-mono"
          style={{
            fontSize: "11px",
            color: "var(--color-text-3)",
            padding: "4px 10px",
            borderRadius: "999px",
            background: "var(--color-bg-2)",
            border: "1px solid var(--color-border)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {filteredCount} / {records.length}
        </span>
      </div>

      {/* 列表主体 */}
      <div
        ref={listRef}
        className="scroll-thin"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "8px",
          minHeight: 0,
        }}
      >
        {loading && <LoadingLine />}
        {error && <EmptyLine text={error} />}

        {!loading && !error && filteredCount === 0 && (
          <EmptyLine
            text={query ? `未找到与 "${query}" 匹配的项目` : "暂无项目记录"}
          />
        )}

        {!loading && !error && replays.length > 0 && (
          <Group
            label="有回放记录"
            count={replays.length}
            hint="Agent 已跑过、可直接再看一遍"
            tintColor="var(--color-info)"
          >
            {replays.map((r, i) => (
              <Row
                key={r.record_id}
                record={r}
                index={i}
                cursorIdx={cursor}
                onTrigger={trigger}
                onHover={setCursor}
              />
            ))}
          </Group>
        )}

        {!loading && !error && runnable.length > 0 && (
          <Group
            label="可触发"
            count={runnable.length}
            hint="尚未运行过，点击启动流水线"
            tintColor="var(--color-accent)"
            startIndex={replays.length}
          >
            {runnable.map((r, i) => (
              <Row
                key={r.record_id}
                record={r}
                index={replays.length + i}
                cursorIdx={cursor}
                onTrigger={trigger}
                onHover={setCursor}
              />
            ))}
          </Group>
        )}
      </div>

      {/* 快捷键提示 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "18px",
          padding: "10px 20px",
          borderTop: "1px solid var(--color-border)",
          background: "var(--color-bg-0)",
          fontFamily: "var(--font-mono)",
          fontSize: "10.5px",
          color: "var(--color-text-4)",
          letterSpacing: "0.04em",
        }}
      >
        <KeyHint icon={<ArrowUp size={10} />} label="上" />
        <KeyHint icon={<ArrowDown size={10} />} label="下" />
        <KeyHint icon={<CornerDownLeft size={10} />} label="打开" />
        <span style={{ marginLeft: "auto" }}>ESC 关闭</span>
      </div>
    </motion.div>
  );
}

/* ============ 子组件 ============ */

function Group({
  label,
  count,
  hint,
  tintColor,
  children,
}: {
  label: string;
  count: number;
  hint: string;
  tintColor: string;
  startIndex?: number;
  children: React.ReactNode;
}) {
  return (
    <section style={{ marginBottom: "10px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "10px 14px 6px",
        }}
      >
        <span
          aria-hidden
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: tintColor,
          }}
        />
        <span
          className="font-mono"
          style={{
            fontSize: "10.5px",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--color-text-2)",
            fontWeight: 600,
          }}
        >
          {label}
        </span>
        <span
          className="font-mono"
          style={{
            fontSize: "10.5px",
            color: "var(--color-text-4)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {count}
        </span>
        <span
          style={{
            fontSize: "11.5px",
            color: "var(--color-text-4)",
            marginLeft: "4px",
          }}
        >
          · {hint}
        </span>
      </div>
      {children}
    </section>
  );
}

function Row({
  record,
  index,
  cursorIdx,
  onTrigger,
  onHover,
}: {
  record: EnrichedRecord;
  index: number;
  cursorIdx: number;
  onTrigger: (r: EnrichedRecord) => void;
  onHover: (i: number) => void;
}) {
  const selected = index === cursorIdx;
  const isReplay = record.mode === "replay";

  return (
    <div
      data-cursor-idx={index}
      onMouseEnter={() => onHover(index)}
      style={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: "20px minmax(0, 1.15fr) minmax(0, 1.6fr) auto",
        gap: "14px",
        alignItems: "center",
        padding: "10px 16px",
        borderRadius: "6px",
        background: selected ? "var(--color-bg-2)" : "transparent",
        cursor: "default",
        transition: "background 0.12s",
      }}
    >
      {selected && (
        <motion.span
          layoutId="picker-cursor-bar"
          aria-hidden
          style={{
            position: "absolute",
            left: 0,
            top: "10px",
            bottom: "10px",
            width: "2px",
            borderRadius: "2px",
            background: "var(--color-accent)",
            boxShadow: "0 0 8px rgba(16,185,129,0.4)",
          }}
          transition={{ type: "spring", stiffness: 400, damping: 32 }}
        />
      )}

      {/* icon */}
      <span
        style={{
          display: "grid",
          placeItems: "center",
          color: isReplay ? "var(--color-info)" : "var(--color-accent)",
        }}
      >
        {isReplay ? <History size={14} /> : <Play size={13} />}
      </span>

      {/* 客户名 + 状态 */}
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "13.5px",
            fontWeight: 500,
            color: "var(--color-text-1)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {record.client_name || "未命名"}
        </div>
        <div
          className="font-mono"
          style={{
            fontSize: "10.5px",
            color: "var(--color-text-4)",
            marginTop: "2px",
            fontVariantNumeric: "tabular-nums",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={record.record_id}
        >
          {record.record_id}
        </div>
      </div>

      {/* brief + 类型 */}
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "12.5px",
            color: "var(--color-text-2)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            lineHeight: 1.5,
          }}
        >
          {record.brief || "—"}
        </div>
        <div
          style={{
            fontSize: "10.5px",
            color: "var(--color-text-4)",
            marginTop: "2px",
            letterSpacing: "0.04em",
          }}
        >
          {record.project_type || "未分类"} · {record.status || "待处理"}
        </div>
      </div>

      {/* 右侧行动按钮 · 点击入口收敛到这里 */}
      <ActionButton isReplay={isReplay} record={record} onTrigger={onTrigger} />
    </div>
  );
}

function ActionButton({
  isReplay,
  record,
  onTrigger,
}: {
  isReplay: boolean;
  record: EnrichedRecord;
  onTrigger: (r: EnrichedRecord) => void;
}) {
  const color = isReplay ? "var(--color-info)" : "var(--color-accent)";
  const borderColor = isReplay ? "rgba(96, 165, 250, 0.35)" : "rgba(110, 231, 183, 0.35)";
  const bg = isReplay ? "rgba(96, 165, 250, 0.08)" : "rgba(16, 185, 129, 0.08)";
  const bgHover = isReplay ? "rgba(96, 165, 250, 0.18)" : "rgba(16, 185, 129, 0.18)";

  return (
    <motion.button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onTrigger(record);
      }}
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.96 }}
      transition={{ type: "spring", stiffness: 400, damping: 26 }}
      title={isReplay ? "加载历史事件回放" : "触发真实流水线"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "7px",
        padding: "6px 14px 6px 12px",
        borderRadius: "7px",
        fontFamily: "var(--font-sans)",
        fontSize: "12.5px",
        fontWeight: 500,
        letterSpacing: "0.02em",
        color,
        background: bg,
        border: `1px solid ${borderColor}`,
        cursor: "pointer",
        whiteSpace: "nowrap",
        transition: "background 0.16s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = bgHover;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = bg;
      }}
    >
      {isReplay ? (
        <History size={12} strokeWidth={2.4} />
      ) : (
        <Play size={11} strokeWidth={2.6} />
      )}
      <span>{isReplay ? "回放" : "触发"}</span>
      {isReplay && (
        <span
          className="font-mono"
          style={{
            fontSize: "10.5px",
            color: "var(--color-text-3)",
            fontVariantNumeric: "tabular-nums",
            opacity: 0.8,
          }}
        >
          {record.run?.event_count ?? 0}
        </span>
      )}
    </motion.button>
  );
}

function LoadingLine() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "22px 18px",
        fontSize: "12.5px",
        color: "var(--color-text-3)",
        fontFamily: "var(--font-mono)",
      }}
    >
      <motion.span
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
        style={{ display: "inline-flex" }}
      >
        <RefreshCw size={13} />
      </motion.span>
      加载中...
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return (
    <div
      style={{
        padding: "36px 18px",
        textAlign: "center",
        fontSize: "12.5px",
        color: "var(--color-text-3)",
        fontFamily: "var(--font-mono)",
        letterSpacing: "0.04em",
      }}
    >
      {text}
    </div>
  );
}

function KeyHint({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
      }}
    >
      <span
        aria-hidden
        style={{
          display: "grid",
          placeItems: "center",
          width: "20px",
          height: "18px",
          borderRadius: "4px",
          background: "var(--color-bg-2)",
          border: "1px solid var(--color-border)",
          color: "var(--color-text-2)",
        }}
      >
        {icon}
      </span>
      {label}
    </span>
  );
}

