import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Markdown from "react-markdown";
import {
  Brain,
  Wrench,
  ArrowDownRight,
  Info,
  AlertTriangle,
  ChevronDown,
  UserCheck,
  Lightbulb,
  PenTool,
  ShieldCheck,
  ClipboardList,
  Radio,
} from "lucide-react";
import { usePipelineStore } from "../stores/usePipelineStore";
import type { PipelineEvent } from "../types";

/* ── 角色 Tab 定义 ── */
const ROLE_TABS = [
  { id: "account_manager", name: "客户经理", Icon: UserCheck },
  { id: "strategist", name: "策略师", Icon: Lightbulb },
  { id: "copywriter", name: "文案", Icon: PenTool },
  { id: "reviewer", name: "审核", Icon: ShieldCheck },
  { id: "project_manager", name: "项目经理", Icon: ClipboardList },
] as const;

const SYSTEM_TAB = { id: "_system" as const, name: "系统", Icon: Radio };

type TabId = (typeof ROLE_TABS)[number]["id"] | typeof SYSTEM_TAB.id;

/* ── 事件类型配置 ── */
const TYPE_CONFIG: Record<
  string,
  {
    css: string;
    label: string;
    Icon: typeof Brain;
    color: string;
    borderColor: string;
  }
> = {
  "agent.thinking": {
    css: "thinking",
    label: "思考",
    Icon: Brain,
    color: "#e5a82e",
    borderColor: "#e5a82e",
  },
  "tool.called": {
    css: "tool-call",
    label: "调用",
    Icon: Wrench,
    color: "#3abab4",
    borderColor: "#3abab4",
  },
  "tool.returned": {
    css: "tool-return",
    label: "返回",
    Icon: ArrowDownRight,
    color: "#5b8def",
    borderColor: "#5b8def",
  },
  "pipeline.rejection": {
    css: "rejection",
    label: "驳回",
    Icon: AlertTriangle,
    color: "#e55353",
    borderColor: "#e55353",
  },
};

const SYSTEM_CONFIG = {
  css: "system",
  label: "系统",
  Icon: Info,
  color: "#a0a0ab",
  borderColor: "#6b6b76",
};

/* ── 渲染模式 ── */
type RenderMode = "md" | "code" | "plain";

/* ═══════════════════════════════════════════════
   文本格式化管线
   目标：把工具的原始输出变成人能快速扫读的内容
   ═══════════════════════════════════════════════ */

// 纯 ID 字段 — 工具参数/返回值中只用于寻址、对人无意义
const PURE_ID_KEYS = new Set([
  "record_id", "content_id", "content_record_id",
  "chat_id", "record_ids",
]);

/** 规范化 Markdown 结构：拆开黏在一起的标题和列表 */
function normalizeMd(raw: string): string {
  return raw
    .replace(/\\n/g, "\n")
    .replace(/([^\n])\s*(#{1,6}\s)/g, "$1\n$2")
    .replace(/([^\n])[\s]+(- )/g, "$1\n$2")
    .replace(/([^\n#])[\s]+(\d+[.)]\s)/g, "$1\n$2")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** 检测是否含 Markdown 结构 */
function hasMdStructure(text: string): boolean {
  return /(?:^|\n)\s*#{1,6}\s/.test(text) ||
    /(?:^|\n)\s*[-*]\s/.test(text) ||
    /(?:^|\n)\s*\d+[.)]\s/.test(text) ||
    /\*\*[^*]+\*\*/.test(text) ||
    /`[^`]+`/.test(text);
}

/** 尝试将字符串解析为 JSON（对象或数组） */
function tryParseJson(raw: string): unknown | null {
  const trimmed = raw.trim();
  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return null;
    }
  }
  return null;
}

/** 从 JSON 对象中提取有意义的值，跳过 ID 和空值 */
function flattenJsonValues(obj: Record<string, unknown>): string[] {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (PURE_ID_KEYS.has(k)) continue;
    if (v === "" || v === null || v === undefined) continue;
    if (typeof v === "string") {
      parts.push(v);
    } else if (typeof v === "number") {
      parts.push(String(v));
    } else if (Array.isArray(v)) {
      // 数组：提取每项的 title/name，或展平为字符串
      for (const item of v) {
        if (typeof item === "string") {
          parts.push(item);
        } else if (typeof item === "object" && item !== null) {
          const rec = item as Record<string, unknown>;
          // 取可读字段
          const label = (rec.title || rec.name || rec.message || "") as string;
          if (label) parts.push(label);
        }
      }
    }
  }
  return parts;
}

/**
 * 格式化 JSON 对象的返回值（如 read_project）
 * { "client_name":"cdss", "brief_content":"六一...", "status":"解读中" }
 * → "cdss · 六一... · 解读中"
 * 长内容（>60字）单独一行，短标签加 [] 括起
 */
function formatJsonObject(obj: Record<string, unknown>): string {
  const vals = flattenJsonValues(obj);
  if (vals.length === 0) return "—";

  // 找出最长的值作为主体内容（brief/content 类），其余做标签
  let mainIdx = 0;
  let maxLen = 0;
  for (let i = 0; i < vals.length; i++) {
    if (vals[i].length > maxLen) {
      maxLen = vals[i].length;
      mainIdx = i;
    }
  }

  if (vals.length === 1) return vals[0];

  const main = vals[mainIdx];
  const tags = vals.filter((_, i) => i !== mainIdx && _.length > 0);
  // 短标签用 [] 包裹
  const tagStr = tags.map((t) => (t.length <= 20 ? `[${t}]` : t)).join(" ");
  return tagStr ? `${main}\n${tagStr}` : main;
}

/**
 * 格式化 JSON 数组返回值（如 list_content）
 * 每项提取标题/平台等可读字段，输出编号列表
 */
function formatJsonArray(arr: unknown[]): string {
  if (arr.length === 0) return "（空列表）";

  // 收集所有项的值，找出在每一项都出现的值（如 project_name）→ 去掉冗余
  const allItemVals: string[][] = [];
  for (const item of arr) {
    if (typeof item === "object" && item !== null) {
      allItemVals.push(flattenJsonValues(item as Record<string, unknown>));
    }
  }
  const redundant = new Set<string>();
  if (allItemVals.length > 1) {
    for (const v of allItemVals[0]) {
      if (allItemVals.every((vals) => vals.includes(v))) {
        redundant.add(v);
      }
    }
  }

  const lines: string[] = [];
  for (let i = 0; i < arr.length; i++) {
    const item = arr[i];
    if (typeof item === "string") {
      lines.push(`${i + 1}. ${item}`);
    } else if (typeof item === "object" && item !== null) {
      const rec = item as Record<string, unknown>;
      const vals = flattenJsonValues(rec).filter((v) => !redundant.has(v));
      const display = vals.slice(0, 4).join(" · ");
      lines.push(`${i + 1}. ${display || JSON.stringify(rec)}`);
    }
  }
  return lines.join("\n");
}

/* ── 工具调用参数展示 ── */
function extractToolContent(args: Record<string, unknown>): { text: string; mode: RenderMode } {
  // 1. 检查是否有大段 markdown 值（如 request_human_review 的 value）
  for (const [k, v] of Object.entries(args)) {
    if (PURE_ID_KEYS.has(k)) continue;
    if (typeof v === "string" && v.length > 80 && hasMdStructure(v)) {
      return { text: normalizeMd(v), mode: "md" };
    }
  }

  // 2. 提取有意义的值
  const parts: string[] = [];
  for (const [k, v] of Object.entries(args)) {
    if (PURE_ID_KEYS.has(k)) continue;
    if (Array.isArray(v)) {
      const items = v.map((item) =>
        typeof item === "object" && item !== null
          ? ((item as Record<string, unknown>).title ||
              (item as Record<string, unknown>).name ||
              JSON.stringify(item)) as string
          : String(item),
      );
      parts.push(items.join("、"));
    } else if (typeof v === "string" && v.length > 0) {
      parts.push(v);
    } else if (typeof v === "number") {
      parts.push(String(v));
    }
  }
  return { text: parts.join(" · ") || "—", mode: "code" };
}

/* ── 工具返回结果清洗 ── */
function cleanToolResult(raw: string): { text: string; mode: RenderMode } {
  const trimmed = raw.trim();

  // 1. 尝试 JSON 解析
  const parsed = tryParseJson(trimmed);
  if (parsed !== null) {
    if (Array.isArray(parsed)) {
      return { text: formatJsonArray(parsed), mode: "plain" };
    }
    if (typeof parsed === "object") {
      // JSON 对象中可能有 message 字段（如 batch_create_content）
      const obj = parsed as Record<string, unknown>;
      if (typeof obj.message === "string") {
        const extras = flattenJsonValues(obj).filter((v) => v !== obj.message);
        const text = extras.length > 0
          ? `${obj.message}\n${extras.join("、")}`
          : obj.message;
        return { text, mode: "plain" };
      }
      return { text: formatJsonObject(obj), mode: "plain" };
    }
  }

  // 2. Markdown 内容
  const normalized = normalizeMd(trimmed);
  if (hasMdStructure(normalized)) {
    return { text: normalized, mode: "md" };
  }

  // 3. 纯文本清理
  const cleaned = normalized
    .split("\n")
    .map((line) => {
      // 保留状态转换行
      if (line.includes("->") || line.includes("→")) return line;
      // 单行 "key: value" → 只保留 value
      const m = line.match(/^\s*[\w\u4e00-\u9fff]+\s*[:：]\s*(.+)$/);
      return m ? m[1].trim() : line;
    })
    .filter(Boolean)
    .join("\n");
  return { text: cleaned, mode: "plain" };
}

/* ── 事件展示提取 ── */
function getEventDisplay(evt: PipelineEvent) {
  const type = evt.event_type;
  const p = evt.payload;

  if (TYPE_CONFIG[type]) {
    const cfg = TYPE_CONFIG[type];
    let content = "";
    let label = cfg.label;
    let renderMode: RenderMode = "plain";

    if (type === "agent.thinking") {
      const raw = normalizeMd((p.content as string) || "");
      content = raw;
      renderMode = hasMdStructure(raw) ? "md" : "plain";
    } else if (type === "tool.called") {
      const toolName = p.tool_name as string;
      label = `调用 ${toolName}`;
      const extracted = extractToolContent(
        (p.arguments as Record<string, unknown>) || {},
      );
      content = extracted.text;
      renderMode = extracted.mode;
    } else if (type === "tool.returned") {
      label = `${p.tool_name} 返回`;
      const result = cleanToolResult((p.result as string) || "");
      content = result.text;
      renderMode = result.mode;
    } else if (type === "pipeline.rejection") {
      content = `通过率 ${(((p.pass_rate as number) || 0) * 100).toFixed(0)}% < 60%，触发返工 ${p.attempt}/${p.max_attempts}`;
    }
    return { ...cfg, label, content, renderMode };
  }

  if (type === "pipeline.started") {
    return { ...SYSTEM_CONFIG, label: "流水线启动", content: `项目: ${p.project_name || "未知"}`, renderMode: "plain" as RenderMode };
  }
  if (type === "pipeline.stage_changed") {
    return { ...SYSTEM_CONFIG, label: "角色切换", content: `${p.current_name} 开始工作`, renderMode: "plain" as RenderMode };
  }
  if (type === "pipeline.completed") {
    const t = p.total_time ? (p.total_time as number).toFixed(1) + "s" : "";
    return { ...SYSTEM_CONFIG, label: "流水线完成", content: `总耗时 ${t} | 通过 ${p.ok_count}/${p.total_stages}`, renderMode: "plain" as RenderMode };
  }
  return null;
}

/** 判断事件属于哪个 Tab */
function getEventTab(evt: PipelineEvent): TabId {
  if (evt.agent_role && ROLE_TABS.some((r) => r.id === evt.agent_role)) {
    return evt.agent_role as TabId;
  }
  return "_system";
}

/* ── EventBlock 组件 ── */
function EventBlock({ evt, index }: { evt: PipelineEvent; index: number }) {
  const [collapsed, setCollapsed] = useState(true);
  const display = getEventDisplay(evt);
  if (!display) return null;

  const { css, label, Icon, color, borderColor, content, renderMode } = display;
  const lines = content.split("\n").length;
  const isLong = lines > 5 || content.length > 300;

  const renderContent = () => {
    switch (renderMode) {
      case "md":
        return (
          <div className="md-content">
            <Markdown>{content}</Markdown>
          </div>
        );
      case "code":
        return <code className="mono">{content}</code>;
      default:
        return content;
    }
  };

  return (
    <motion.div
      className={`event-block ${css}`}
      style={{ borderLeftColor: borderColor }}
      initial={{ opacity: 0, x: -12, scale: 0.98 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={{
        duration: 0.25,
        delay: Math.min(index * 0.015, 0.08),
        ease: "easeOut",
      }}
      layout
    >
      <div className="event-header">
        <span className={`event-tag ${css}`} style={{ color, borderColor }}>
          <Icon size={11} />
          <span>{label}</span>
        </span>
        {evt.round > 0 && <span className="event-round">R{evt.round}</span>}
      </div>
      {content && (
        <>
          <div className={`event-body ${isLong && collapsed ? "collapsed" : ""}`}>
            {renderContent()}
          </div>
          {isLong && (
            <button className="event-expand" onClick={() => setCollapsed(!collapsed)}>
              <ChevronDown
                size={12}
                style={{
                  transform: collapsed ? "rotate(0)" : "rotate(180deg)",
                  transition: "transform 200ms",
                }}
              />
              {collapsed ? "展开全部" : "收起"}
            </button>
          )}
        </>
      )}
    </motion.div>
  );
}

/* ── EventStream 主组件 ── */
export function EventStream() {
  const events = usePipelineStore((s) => s.events);
  const activeRole = usePipelineStore((s) => s.activeRole);
  const stages = usePipelineStore((s) => s.stages);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  // null = 自动跟随活跃角色, 具体值 = 手动锁定
  const [lockedTab, setLockedTab] = useState<TabId | null>(null);
  const currentTab: TabId = lockedTab ?? ((activeRole as TabId) || "_system");

  // 活跃角色切换时，如果没有手动锁定，自动跟随 + 重置滚动
  const prevActiveRef = useRef(activeRole);
  useEffect(() => {
    if (activeRole && activeRole !== prevActiveRef.current) {
      prevActiveRef.current = activeRole;
      if (!lockedTab) {
        setAutoScroll(true);
      }
    }
  }, [activeRole, lockedTab]);

  // 按 Tab 分组事件 + 统计数量
  const { tabEvents, tabCounts } = useMemo(() => {
    const grouped: Record<string, PipelineEvent[]> = {};
    const counts: Record<string, number> = {};
    for (const evt of events) {
      const display = getEventDisplay(evt);
      if (!display) continue;
      const tab = getEventTab(evt);
      if (!grouped[tab]) grouped[tab] = [];
      grouped[tab].push(evt);
      counts[tab] = (counts[tab] || 0) + 1;
    }
    return { tabEvents: grouped, tabCounts: counts };
  }, [events]);

  const visibleEvents = tabEvents[currentTab] || [];

  // 新事件到达时自动滚动
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [visibleEvents.length, autoScroll, currentTab]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const el = scrollRef.current;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
    setShowScrollBtn(!atBottom);
  };

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      setAutoScroll(true);
      setShowScrollBtn(false);
    }
  };

  const handleTabClick = (tabId: TabId) => {
    if (tabId === currentTab && lockedTab) {
      // 再次点击当前已锁定的 Tab → 解锁回自动模式
      setLockedTab(null);
    } else {
      setLockedTab(tabId);
    }
    setAutoScroll(true);
    setShowScrollBtn(false);
  };

  return (
    <div className="left-panel">
      {/* ── Tab 栏 ── */}
      <div className="stream-tabs">
        {ROLE_TABS.map((tab) => {
          const isActive = currentTab === tab.id;
          const stageState = stages[tab.id]?.state || "waiting";
          const count = tabCounts[tab.id] || 0;
          const { Icon } = tab;

          return (
            <motion.button
              key={tab.id}
              className={`stream-tab ${isActive ? "active" : ""} ${stageState}`}
              onClick={() => handleTabClick(tab.id)}
              whileTap={{ scale: 0.96 }}
            >
              <Icon size={13} />
              <span className="tab-name">{tab.name}</span>
              {count > 0 && (
                <motion.span
                  className="tab-badge"
                  key={count}
                  initial={{ scale: 1.4 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 15 }}
                >
                  {count}
                </motion.span>
              )}
              {isActive && (
                <motion.div
                  className="tab-indicator"
                  layoutId="tab-indicator"
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                />
              )}
            </motion.button>
          );
        })}
        {/* 系统 Tab */}
        <motion.button
          className={`stream-tab ${currentTab === "_system" ? "active" : ""}`}
          onClick={() => handleTabClick("_system")}
          whileTap={{ scale: 0.96 }}
        >
          <SYSTEM_TAB.Icon size={13} />
          <span className="tab-name">{SYSTEM_TAB.name}</span>
          {(tabCounts["_system"] || 0) > 0 && (
            <span className="tab-badge">{tabCounts["_system"]}</span>
          )}
          {currentTab === "_system" && (
            <motion.div
              className="tab-indicator"
              layoutId="tab-indicator"
              transition={{ type: "spring", stiffness: 380, damping: 30 }}
            />
          )}
        </motion.button>

        {/* 自动跟随指示 */}
        {!lockedTab && activeRole && (
          <span className="tab-auto-hint">自动跟随</span>
        )}
        {lockedTab && (
          <button
            className="tab-auto-btn"
            onClick={() => { setLockedTab(null); setAutoScroll(true); }}
          >
            恢复自动
          </button>
        )}
      </div>

      {/* ── 事件流区域 ── */}
      <div className="panel-header">
        <AnimatePresence>
          {showScrollBtn && (
            <motion.button
              className="btn btn-small scroll-btn"
              onClick={scrollToBottom}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
            >
              <ChevronDown size={12} />
              回到底部
            </motion.button>
          )}
        </AnimatePresence>
      </div>
      <div className="event-stream" ref={scrollRef} onScroll={handleScroll}>
        <AnimatePresence mode="wait">
          <motion.div
            key={currentTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="event-list"
          >
            {visibleEvents.map((evt, i) => (
              <EventBlock
                key={`${evt.event_type}-${evt.timestamp}-${i}`}
                evt={evt}
                index={i}
              />
            ))}
            {visibleEvents.length === 0 && (
              <div className="stream-empty">
                <Brain size={28} color="#2a2a36" />
                <span>
                  {currentTab === "_system"
                    ? "等待流水线启动..."
                    : "该角色尚未开始工作"}
                </span>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
