/**
 * ToolChipRow
 *
 * 工具调用信息在这里一律次要化：chip 形态、低对比、可点击展开抽屉。
 * 产出型工具（write_content / batch_create_content）的 chip **不渲染正文**——正文只在主视图渲染一次。
 * 超过 6 个 chip 默认折叠，点击 "+N" 全量展开。
 */

import { useState } from "react";
import { useConsoleStore } from "../useConsoleStore";
import { toolLabel } from "../toolLabels";
import type { ToolCall, ToolKind } from "../types";

const KIND_COLOR: Record<ToolKind, string> = {
  info: "text-info",
  warn: "text-warn",
  ok: "text-accent",
  purple: "text-purple",
};

const MAX_VISIBLE = 6;

interface ToolChipRowProps {
  label?: string;
  calls: ToolCall[];
}

export function ToolChipRow({ label = "工具调用", calls }: ToolChipRowProps) {
  const openDrawer = useConsoleStore((s) => s.openDrawer);
  const drawerKey = useConsoleStore((s) => s.drawerKey);
  const [expanded, setExpanded] = useState(false);

  if (calls.length === 0) return null;

  const visible = expanded ? calls : calls.slice(0, MAX_VISIBLE);
  const hiddenCount = calls.length - visible.length;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "6px",
        margin: "16px 0 20px",
        alignItems: "center",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: "11px",
          letterSpacing: "0.08em",
          color: "var(--color-text-4)",
          marginRight: "6px",
          position: "relative",
          paddingLeft: "10px",
        }}
      >
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: 0,
            top: "50%",
            transform: "translateY(-50%)",
            width: "2px",
            height: "11px",
            background: "var(--color-accent)",
            opacity: 0.6,
            borderRadius: "2px",
          }}
        />
        {label}
      </span>

      {visible.map((c) => {
        const active = drawerKey === c.id;
        const transition = cleanTransition(c.stateTransition);
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => openDrawer(c.id)}
            title={c.name}
            className={`inline-flex items-center gap-2 transition-colors cursor-pointer ${
              active
                ? "bg-accent/10 border-accent/30 text-accent"
                : "bg-bg-2 border-border text-text-2 hover:bg-bg-3 hover:border-accent/30 hover:text-text-1"
            }`}
            style={{
              padding: "5px 12px",
              borderRadius: "999px",
              borderWidth: "1px",
              borderStyle: "solid",
              fontSize: "12px",
              lineHeight: 1.3,
              fontFamily: "var(--font-sans)",
            }}
          >
            <span
              className={`rounded-full bg-current opacity-80 ${KIND_COLOR[c.kind]}`}
              style={{ width: "6px", height: "6px", flexShrink: 0 }}
            />
            <span>{toolLabel(c.name)}</span>
            {c.calls > 1 && (
              <span
                className="font-mono text-text-3"
                style={{ fontSize: "10.5px", fontVariantNumeric: "tabular-nums" }}
              >
                × {c.calls}
              </span>
            )}
            {transition && (
              <span className="text-text-3" style={{ fontSize: "11.5px" }}>
                · {transition}
              </span>
            )}
            {!transition && c.avgMs > 0 && (
              <span
                className="font-mono text-text-4"
                style={{
                  fontSize: "10px",
                  marginLeft: "2px",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {c.avgMs >= 1000
                  ? `${(c.avgMs / 1000).toFixed(1)}s`
                  : `${c.avgMs}ms`}
              </span>
            )}
          </button>
        );
      })}

      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="font-mono text-text-3 hover:text-accent transition-colors"
          style={{
            padding: "3px 10px",
            borderRadius: "999px",
            borderWidth: "1px",
            borderStyle: "dashed",
            borderColor: "var(--color-border)",
            background: "transparent",
            fontSize: "10.5px",
          }}
        >
          +{hiddenCount} more
        </button>
      )}

      {expanded && calls.length > MAX_VISIBLE && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="font-mono text-text-3 hover:text-accent transition-colors"
          style={{
            padding: "3px 10px",
            borderRadius: "999px",
            background: "transparent",
            fontSize: "10.5px",
          }}
        >
          收起
        </button>
      )}
    </div>
  );
}

/**
 * 过滤掉 "错误：..." / 长文本 result — 只保留明显的 A → B 形式 or 短文本 (<= 24 字)
 */
function cleanTransition(raw?: string): string {
  if (!raw) return "";
  const s = raw.trim();
  if (s.startsWith("错误") || s.startsWith("Error")) return "";
  if (s.length > 24) return "";
  return s;
}
