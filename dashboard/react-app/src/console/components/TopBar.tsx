/**
 * TopBar
 *
 * 一等公民：角色 tab（读者一眼知道现在看的是谁的产出）。
 * 次要信息：品牌、LIVE/MOCK 徽章、触发项目、NEW/OLD 模式。
 *
 * 签名交互（layoutId 滑轨）：tab 激活指示器用 framer-motion layoutId，
 *   切换角色时在 tabs 之间流畅滑动，不是淡入淡出。
 * 次级交互：tab 按压 scale-97、徽章 hover 发光、触发按钮 icon 滑入。
 *
 * padding 用 inline style 锁死——不再依赖 Tailwind arbitrary value 是否生效。
 */

import { AnimatePresence, motion } from "framer-motion";
import { Play, Radio, Database } from "lucide-react";
import { useConsoleStore } from "../useConsoleStore";
import type { AgentSession, RoleId } from "../types";

const ROLES: { id: RoleId; label: string }[] = [
  { id: "account", label: "客户经理" },
  { id: "strategy", label: "策略师" },
  { id: "copy", label: "文案" },
  { id: "review", label: "审核" },
  { id: "pm", label: "项目经理" },
];

interface TopBarProps {
  session: AgentSession;
  isLive?: boolean;
  onShowPicker?: () => void;
}

export function TopBar({ session, isLive = false, onShowPicker }: TopBarProps) {
  const { activeRole, viewMode, setRole, setViewMode } = useConsoleStore();

  return (
    <header
      className="relative flex items-center border-b border-border bg-bg-1"
      style={{
        height: "56px",
        flexShrink: 0,
        paddingLeft: "24px",
        paddingRight: "20px",
        gap: "28px",
      }}
    >
      {/* 背景 ambient 光晕 · 只在 active role tab 下方隐约透出 */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          background:
            "linear-gradient(180deg, rgba(110,231,183,0.025) 0%, transparent 60%)",
        }}
      />

      {/* 品牌区 */}
      <div
        className="relative flex items-center font-mono font-semibold text-text-2"
        style={{
          gap: "10px",
          fontSize: "11.5px",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
        }}
      >
        <motion.span
          aria-hidden
          animate={{
            boxShadow: [
              "0 0 0px rgba(110,231,183,0.6), 0 0 0 3px rgba(110,231,183,0.08)",
              "0 0 14px rgba(110,231,183,0.6), 0 0 0 4px rgba(110,231,183,0.12)",
              "0 0 0px rgba(110,231,183,0.6), 0 0 0 3px rgba(110,231,183,0.08)",
            ],
          }}
          transition={{ duration: 2.4, ease: "easeInOut", repeat: Infinity }}
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: "var(--color-accent)",
          }}
        />
        <span>{session.client || "AGENT"} · CONSOLE</span>
      </div>

      {/* 竖直分隔线 */}
      <span
        aria-hidden
        style={{
          height: "20px",
          width: "1px",
          background: "var(--color-border)",
        }}
      />

      {/* 角色 tabs */}
      <nav
        className="relative flex items-center"
        style={{ gap: "2px", flex: 1 }}
      >
        {ROLES.map((r) => {
          const active = r.id === activeRole;
          return (
            <motion.button
              key={r.id}
              type="button"
              onClick={() => setRole(r.id)}
              whileTap={{ scale: 0.96 }}
              transition={{ type: "spring", stiffness: 400, damping: 28 }}
              className="relative flex items-center font-medium"
              style={{
                gap: "8px",
                padding: "8px 14px",
                borderRadius: "6px",
                fontSize: "13px",
                color: active ? "var(--color-accent)" : "var(--color-text-3)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                zIndex: 1,
              }}
              onMouseEnter={(e) => {
                if (!active) e.currentTarget.style.color = "var(--color-text-1)";
              }}
              onMouseLeave={(e) => {
                if (!active) e.currentTarget.style.color = "var(--color-text-3)";
              }}
            >
              {/* 激活态背景 · layoutId 在 tabs 间滑动 */}
              {active && (
                <motion.span
                  layoutId="role-active-pill"
                  aria-hidden
                  style={{
                    position: "absolute",
                    inset: 0,
                    borderRadius: "6px",
                    background: "var(--color-bg-2)",
                    border: "1px solid var(--color-border)",
                    zIndex: -1,
                  }}
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}

              <span style={{ position: "relative" }}>{r.label}</span>

              <motion.span
                className="font-mono"
                animate={{
                  color: active ? "var(--color-accent-dim)" : "var(--color-text-4)",
                  backgroundColor: active
                    ? "rgba(16, 185, 129, 0.12)"
                    : "var(--color-bg-3)",
                }}
                transition={{ duration: 0.2 }}
                style={{
                  fontSize: "11px",
                  padding: "1px 7px",
                  borderRadius: "3px",
                  position: "relative",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {session.roleCounts[r.id]}
              </motion.span>

              {/* 激活态下方小点 · layoutId 和 pill 同步滑动 */}
              {active && (
                <motion.span
                  layoutId="role-active-dot"
                  aria-hidden
                  style={{
                    position: "absolute",
                    left: "50%",
                    bottom: "-13px",
                    transform: "translateX(-50%)",
                    width: "5px",
                    height: "5px",
                    borderRadius: "50%",
                    background: "var(--color-accent)",
                    boxShadow: "0 0 8px rgba(110,231,183,0.6)",
                  }}
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
            </motion.button>
          );
        })}
      </nav>

      {/* 右侧工具组 */}
      <div
        className="relative flex items-center"
        style={{ gap: "10px" }}
      >
        {/* LIVE / MOCK 徽章 */}
        <AnimatePresence mode="wait">
          <motion.span
            key={isLive ? "live" : "mock"}
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.95 }}
            transition={{ duration: 0.18 }}
            className="inline-flex items-center font-mono"
            title={
              isLive
                ? "来自真实 SSE 事件流"
                : "使用 mock 数据（尚未连接 pipeline）"
            }
            style={{
              gap: "6px",
              padding: "4px 10px",
              borderRadius: "999px",
              fontSize: "10px",
              letterSpacing: "0.08em",
              fontWeight: 600,
              color: isLive ? "var(--color-accent)" : "var(--color-text-3)",
              background: isLive
                ? "rgba(16, 185, 129, 0.1)"
                : "var(--color-bg-2)",
              border: `1px solid ${
                isLive ? "rgba(110, 231, 183, 0.35)" : "var(--color-border)"
              }`,
              boxShadow: isLive
                ? "0 0 14px rgba(16, 185, 129, 0.15)"
                : "none",
            }}
          >
            {isLive ? (
              <motion.span
                animate={{ opacity: [1, 0.4, 1] }}
                transition={{ duration: 1.6, repeat: Infinity }}
                style={{ display: "inline-flex" }}
              >
                <Radio size={10} />
              </motion.span>
            ) : (
              <Database size={10} />
            )}
            {isLive ? "LIVE" : "MOCK"}
          </motion.span>
        </AnimatePresence>

        {/* 选项目 */}
        {onShowPicker && (
          <motion.button
            type="button"
            onClick={onShowPicker}
            whileHover="hover"
            whileTap={{ scale: 0.96 }}
            initial="rest"
            animate="rest"
            variants={{ rest: {}, hover: {} }}
            title="挑选项目 · 触发真实 pipeline"
            className="inline-flex items-center font-mono"
            style={{
              gap: "7px",
              padding: "6px 14px",
              borderRadius: "6px",
              fontSize: "11.5px",
              color: "var(--color-text-2)",
              background: "var(--color-bg-2)",
              border: "1px solid var(--color-border)",
              cursor: "pointer",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = "var(--color-accent)";
              e.currentTarget.style.borderColor =
                "rgba(110, 231, 183, 0.4)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "var(--color-text-2)";
              e.currentTarget.style.borderColor = "var(--color-border)";
            }}
          >
            <motion.span
              variants={{
                rest: { x: 0 },
                hover: { x: 2 },
              }}
              transition={{ type: "spring", stiffness: 400, damping: 22 }}
              style={{ display: "inline-flex" }}
            >
              <Play size={12} strokeWidth={2.4} />
            </motion.span>
            <span>选项目</span>
          </motion.button>
        )}

        {/* NEW / OLD 切换 */}
        <div
          className="relative flex items-center"
          style={{
            gap: "0",
            padding: "3px",
            background: "var(--color-bg-2)",
            borderRadius: "7px",
            border: "1px solid var(--color-border)",
          }}
        >
          {(["new", "old"] as const).map((m) => {
            const isActive = viewMode === m;
            return (
              <button
                key={m}
                type="button"
                onClick={() => setViewMode(m)}
                className="relative font-mono font-semibold"
                style={{
                  padding: "5px 12px",
                  fontSize: "10.5px",
                  letterSpacing: "0.08em",
                  borderRadius: "5px",
                  color: isActive
                    ? "var(--color-accent)"
                    : "var(--color-text-3)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  transition: "color 0.18s ease",
                }}
              >
                {isActive && (
                  <motion.span
                    layoutId="view-mode-slider"
                    aria-hidden
                    style={{
                      position: "absolute",
                      inset: 0,
                      borderRadius: "5px",
                      background: "var(--color-bg-0)",
                      boxShadow: "0 1px 4px rgba(0,0,0,0.3)",
                      zIndex: -1,
                    }}
                    transition={{
                      type: "spring",
                      stiffness: 380,
                      damping: 32,
                    }}
                  />
                )}
                {m.toUpperCase()}
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
}
