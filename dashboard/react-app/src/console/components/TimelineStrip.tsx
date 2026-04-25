/**
 * TimelineStrip
 *
 * 一等公民：当前状态节点（pulse + glow）。
 * 次要信息：已完成 / 未开始节点。
 *
 * 排版：中文标签用 Plex Sans（避免 mono 字体下中文 fallback 到系统丑字），
 * 序号 / 箭头用 JetBrains Mono 保留工程气质。
 */

import { motion } from "framer-motion";
import type { TimelineStep } from "../types";

interface TimelineStripProps {
  steps: TimelineStep[];
}

export function TimelineStrip({ steps }: TimelineStripProps) {
  return (
    <div
      className="scroll-none"
      style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        margin: "20px 0 28px",
        padding: "12px 18px",
        background: "var(--color-bg-1)",
        border: "1px solid var(--color-border-soft)",
        borderRadius: "8px",
        overflowX: "auto",
      }}
    >
      {steps.map((step, i) => {
        const bg = step.current
          ? "rgba(16, 185, 129, 0.12)"
          : step.done
            ? "var(--color-bg-2)"
            : "var(--color-bg-2)";
        const fg = step.current
          ? "var(--color-accent)"
          : step.done
            ? "var(--color-text-2)"
            : "var(--color-text-3)";
        const border = step.current
          ? "1px solid rgba(110, 231, 183, 0.32)"
          : "1px solid transparent";

        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              flexShrink: 0,
            }}
          >
            <motion.span
              initial={{ opacity: 0, y: -2 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, duration: 0.24 }}
              className="font-sans"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                whiteSpace: "nowrap",
                padding: "5px 12px 5px 10px",
                borderRadius: "999px",
                border,
                background: bg,
                color: fg,
                fontSize: "12px",
                fontWeight: step.current ? 500 : 400,
                letterSpacing: "0.01em",
                boxShadow: step.current
                  ? "0 0 12px rgba(16, 185, 129, 0.18)"
                  : "none",
                transition: "box-shadow 0.2s",
              }}
            >
              <span
                className="font-mono"
                style={{
                  fontSize: "10px",
                  color: step.current
                    ? "var(--color-accent-dim)"
                    : "var(--color-text-4)",
                  fontVariantNumeric: "tabular-nums",
                  minWidth: "14px",
                  textAlign: "right",
                }}
              >
                {String(i + 1).padStart(2, "0")}
              </span>
              {step.current ? (
                <motion.span
                  animate={{ scale: [1, 1.4, 1], opacity: [1, 0.5, 1] }}
                  transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
                  style={{
                    width: "5px",
                    height: "5px",
                    borderRadius: "50%",
                    background: "currentColor",
                  }}
                />
              ) : (
                <span
                  style={{
                    width: "5px",
                    height: "5px",
                    borderRadius: "50%",
                    background: "currentColor",
                    opacity: step.done ? 0.9 : 0.45,
                  }}
                />
              )}
              {step.label}
            </motion.span>
            {i < steps.length - 1 && (
              <span
                className="font-mono"
                style={{
                  color: "var(--color-text-4)",
                  fontSize: "11px",
                  opacity: 0.7,
                }}
              >
                →
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
