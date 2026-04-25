/**
 * Sidebar · 共享记忆 + 审计日志 + 工具统计
 *
 * 一等公民：项目主线进度（当前卡点、已完成、待开始）。
 * 次要信息：工具审计日志（倒序）、工具调用统计（背景进度条可视化）。
 *
 * 设计系统对齐：
 *   - padding / spacing 全部 inline 锁死，不依赖 Tailwind arbitrary value
 *   - section title 左侧自带 2px 青绿线 —— 和主面板的"签名青绿"一致
 *   - current 进度点双层 pulse + glow ring，和 TopBar 的品牌点呼吸同频
 *   - audit 日志每条 hover 出现左侧彩条，和 Copywriter 卡片一致
 *   - 统计条背景色用 gradient + 数字 tabular-nums 防抖
 *   - Mount 时条形图有 staggered fill-in 动效
 */

import { motion } from "framer-motion";
import { toolLabel } from "../toolLabels";
import type { AgentSession, MemoryState } from "../types";

interface SidebarProps {
  session: AgentSession;
}

export function Sidebar({ session }: SidebarProps) {
  const totalTools = session.toolStats.reduce((a, c) => a + c.count, 0);
  const doneCount = session.memoryProgress.filter(
    (m) => m.state === "done",
  ).length;
  const maxToolCount = Math.max(...session.toolStats.map((t) => t.count), 1);

  return (
    <aside
      className="scroll-thin"
      style={{
        borderLeft: "1px solid var(--color-border)",
        background: "var(--color-bg-1)",
        overflowY: "auto",
        padding: "24px 22px 40px",
        display: "flex",
        flexDirection: "column",
        gap: "32px",
      }}
    >
      {/* 共享记忆 */}
      <section>
        <SideTitle
          label="共享记忆 · 项目主线"
          count={`${doneCount} / ${session.memoryProgress.length}`}
        />
        <ol
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "2px",
            listStyle: "none",
            margin: 0,
            padding: 0,
          }}
        >
          {session.memoryProgress.map((m, i) => (
            <motion.li
              key={i}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04, duration: 0.24, ease: [0.32, 0.72, 0, 1] }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                padding: "9px 4px",
                fontSize: "12.5px",
                color:
                  m.state === "done"
                    ? "var(--color-text-1)"
                    : m.state === "current"
                      ? "var(--color-accent)"
                      : "var(--color-text-3)",
                fontWeight: m.state === "current" ? 500 : 400,
                borderRadius: "4px",
              }}
            >
              <ProgressDot state={m.state} />
              <span>{m.label}</span>
              {m.state === "current" && (
                <motion.span
                  animate={{ opacity: [0.4, 1, 0.4] }}
                  transition={{ duration: 1.8, repeat: Infinity }}
                  className="font-mono"
                  style={{
                    marginLeft: "auto",
                    fontSize: "10px",
                    color: "var(--color-accent-dim)",
                    letterSpacing: "0.1em",
                  }}
                >
                  WORKING
                </motion.span>
              )}
            </motion.li>
          ))}
        </ol>
      </section>

      {/* 风险与沉淀态 */}
      <section>
        <SideTitle label="错误态 / 风险态" count={String(session.riskBadges.length)} />
        {session.riskBadges.length === 0 ? (
          <EmptyHint text="当前无显著风险" />
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {session.riskBadges.map((badge, i) => (
              <div
                key={`${badge.label}-${i}`}
                style={{
                  padding: "6px 10px",
                  borderRadius: "999px",
                  fontSize: "11px",
                  border: `1px solid ${badge.kind === "error" ? "var(--color-danger, #e55353)" : badge.kind === "warn" ? "var(--color-warn)" : "var(--color-accent)"}`,
                  color: badge.kind === "error" ? "var(--color-danger, #e55353)" : badge.kind === "warn" ? "var(--color-warn)" : "var(--color-accent)",
                }}
              >
                {badge.label}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 审计日志 */}
      <section>
        <SideTitle label="工具调用日志" count={String(totalTools)} />
        <div
          className="font-mono"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "1px",
            fontSize: "11px",
          }}
        >
          {session.auditLog.length === 0 ? (
            <EmptyHint text="等待 Agent 调用工具..." />
          ) : (
            session.auditLog.map((a, i) => (
              <AuditRow key={i} entry={a} index={i} />
            ))
          )}
        </div>
      </section>

      {/* 工具调用统计 */}
      <section>
        <SideTitle label="工具调用统计" count={String(totalTools)} />
        {session.toolStats.length === 0 ? (
          <EmptyHint text="尚无调用数据" />
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "4px",
            }}
          >
            {session.toolStats.map((s, i) => (
              <StatRow
                key={s.name}
                name={s.name}
                count={s.count}
                scale={s.count / maxToolCount}
                index={i}
              />
            ))}
          </div>
        )}
      </section>
    </aside>
  );
}

/* ============ 子组件 ============ */

function SideTitle({ label, count }: { label: string; count: string }) {
  return (
    <div
      className="flex items-center justify-between font-mono"
      style={{
        fontSize: "10px",
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: "var(--color-text-3)",
        marginBottom: "14px",
        paddingLeft: "10px",
        position: "relative",
      }}
    >
      <span
        aria-hidden
        style={{
          position: "absolute",
          left: 0,
          top: "2px",
          bottom: "2px",
          width: "2px",
          background: "var(--color-accent)",
          borderRadius: "2px",
          opacity: 0.85,
        }}
      />
      <span>{label}</span>
      <span
        className="font-mono font-semibold"
        style={{
          color: "var(--color-accent)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {count}
      </span>
    </div>
  );
}

function ProgressDot({ state }: { state: MemoryState }) {
  if (state === "done") {
    return (
      <span
        className="grid place-items-center font-bold"
        style={{
          width: "16px",
          height: "16px",
          borderRadius: "50%",
          background: "var(--color-accent)",
          color: "var(--color-bg-0)",
          fontSize: "9px",
          flexShrink: 0,
          border: "1.5px solid var(--color-accent)",
        }}
      >
        ✓
      </span>
    );
  }
  if (state === "current") {
    return (
      <span
        className="relative grid place-items-center"
        style={{
          width: "16px",
          height: "16px",
          borderRadius: "50%",
          border: "1.5px solid var(--color-accent)",
          boxShadow: "0 0 0 3px rgba(16, 185, 129, 0.15)",
          flexShrink: 0,
        }}
      >
        <motion.span
          animate={{ scale: [1, 1.3, 1], opacity: [1, 0.55, 1] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: "var(--color-accent)",
          }}
        />
      </span>
    );
  }
  return (
    <span
      style={{
        width: "16px",
        height: "16px",
        borderRadius: "50%",
        border: "1.5px solid var(--color-text-4)",
        flexShrink: 0,
      }}
    />
  );
}

function AuditRow({
  entry,
  index,
}: {
  entry: AgentSession["auditLog"][number];
  index: number;
}) {
  const color =
    entry.kind === "ok"
      ? "var(--color-accent)"
      : entry.kind === "warn"
        ? "var(--color-warn)"
        : "var(--color-info)";

  // 如果原始 name 是 "tool_name → seq_4" 这种复合名，先拆出工具名做映射
  const parts = entry.name.split("·").map((s) => s.trim());
  const mainPart = parts[0] || entry.name;
  const suffix = parts.slice(1).join(" · ");
  const [coreName, ...rest] = mainPart.split(/\s*→\s*|\s+/);
  const afterArrow = rest.length > 0 ? ` → ${rest.join(" ")}` : "";
  const displayMain = coreName ? toolLabel(coreName) + afterArrow : mainPart;
  const displayFull = suffix ? `${displayMain} · ${suffix}` : displayMain;

  return (
    <motion.div
      initial={{ opacity: 0, y: -2 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.02, duration: 0.18 }}
      className="group"
      title={entry.name}
      style={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: "42px 1fr auto",
        gap: "10px",
        padding: "8px 10px",
        borderRadius: "5px",
        color: "var(--color-text-3)",
        alignItems: "center",
        cursor: "pointer",
        transition: "background 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--color-bg-2)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
      }}
    >
      <span
        aria-hidden
        className="group-hover:opacity-100"
        style={{
          position: "absolute",
          left: 0,
          top: "8px",
          bottom: "8px",
          width: "2px",
          background: color,
          borderRadius: "2px",
          opacity: 0,
          transition: "opacity 0.15s",
        }}
      />
      <span
        className="font-mono"
        style={{
          color: "var(--color-text-4)",
          fontSize: "10px",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {entry.time}
      </span>
      <span
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: "12px",
          color,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {displayFull}
      </span>
      <span
        className="font-mono"
        style={{
          fontSize: "10px",
          color: "var(--color-text-4)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {entry.durMs >= 1000
          ? `${(entry.durMs / 1000).toFixed(1)}s`
          : `${entry.durMs}ms`}
      </span>
    </motion.div>
  );
}

function StatRow({
  name,
  count,
  scale,
  index,
}: {
  name: string;
  count: number;
  scale: number;
  index: number;
}) {
  return (
    <div
      title={name}
      style={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: "1fr auto",
        alignItems: "center",
        gap: "10px",
        padding: "7px 12px",
        borderRadius: "4px",
        overflow: "hidden",
      }}
    >
      <motion.div
        aria-hidden
        initial={{ scaleX: 0 }}
        animate={{ scaleX: scale }}
        transition={{
          delay: 0.15 + index * 0.05,
          duration: 0.6,
          ease: [0.32, 0.72, 0, 1],
        }}
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(90deg, rgba(16, 185, 129, 0.14), rgba(16, 185, 129, 0.02))",
          borderRadius: "4px",
          transformOrigin: "left center",
        }}
      />
      <span
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: "12px",
          color: "var(--color-text-2)",
          zIndex: 1,
          position: "relative",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {toolLabel(name)}
      </span>
      <span
        className="font-mono"
        style={{
          fontSize: "11.5px",
          color: "var(--color-accent)",
          fontWeight: 600,
          zIndex: 1,
          position: "relative",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {count}
      </span>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div
      className="font-mono"
      style={{
        padding: "14px 10px",
        fontSize: "11px",
        color: "var(--color-text-4)",
        border: "1px dashed var(--color-border)",
        borderRadius: "5px",
        letterSpacing: "0.05em",
        textAlign: "center",
      }}
    >
      {text}
    </div>
  );
}
