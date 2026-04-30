/**
 * CostDetailDrawer — 角色 token 成本详情侧边抽屉
 *
 * 从 CostBanner 的角色 Pill 点击后滑入，展示：
 *   - 逐次 LLM 调用（stage / iteration / prompt↑ / completion↓）
 *   - 工具调用汇总（工具名 + 次数）
 */

import { X } from "lucide-react";

/* ── 数据类型（与 /api/costs 响应对齐）─────────────────────────── */
export interface LlmCallDetail {
  ts: number;
  stage: string;
  iteration: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface RoleDetail {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  calls: number;
  llm_calls: LlmCallDetail[];
  tool_calls: Record<string, number>;
}

interface Props {
  roleId: string;
  roleLabel: string;
  roleColor: string;
  detail: RoleDetail;
  onClose: () => void;
}

/* ── 工具函数 ────────────────────────────────────────────────────── */
function fmtK(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

function stageLabel(stage: string, iteration: number | null): string {
  if (stage === "reflect") return "自省蒸馏";
  if (stage === "unit_react_loop") return `单测循环${iteration != null ? ` #${iteration}` : ""}`;
  if (stage === "react_loop") return `ReAct 第 ${iteration ?? "?"} 轮`;
  return stage + (iteration != null ? ` #${iteration}` : "");
}

/* ── 主组件 ─────────────────────────────────────────────────────── */
export function CostDetailDrawer({ roleId: _roleId, roleLabel, roleColor, detail, onClose }: Props) {
  const toolEntries = Object.entries(detail.tool_calls).sort((a, b) => b[1] - a[1]);

  return (
    <div
      style={{
        position:        "fixed",
        top:             56,   /* TopBar 高度 */
        right:           0,
        bottom:          0,
        width:           320,
        background:      "rgba(14, 17, 24, 0.97)",
        borderLeft:      "1px solid rgba(255,255,255,.08)",
        backdropFilter:  "blur(12px)",
        display:         "flex",
        flexDirection:   "column",
        zIndex:          50,
        fontFamily:      "var(--font-mono)",
        overflow:        "hidden",
        animation:       "slideInRight .18s ease-out",
      }}
    >
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>

      {/* 头部 */}
      <div
        style={{
          display:      "flex",
          alignItems:   "center",
          gap:          10,
          padding:      "14px 16px 12px",
          borderBottom: "1px solid rgba(255,255,255,.07)",
          flexShrink:   0,
        }}
      >
        <span
          style={{
            width:        8,
            height:       8,
            borderRadius: "50%",
            background:   roleColor,
            flexShrink:   0,
          }}
        />
        <span style={{ color: "var(--color-text-1)", fontWeight: 600, fontSize: 13, flex: 1 }}>
          {roleLabel}
        </span>
        <button
          onClick={onClose}
          style={{
            background:  "none",
            border:      "none",
            cursor:      "pointer",
            color:       "var(--color-text-4)",
            padding:     4,
            lineHeight:  1,
            borderRadius: 4,
          }}
        >
          <X size={14} />
        </button>
      </div>

      {/* 汇总行 */}
      <div
        style={{
          display:    "flex",
          gap:        12,
          padding:    "10px 16px",
          borderBottom: "1px solid rgba(255,255,255,.05)",
          flexShrink: 0,
        }}
      >
        <Metric label="总计" value={fmtK(detail.total_tokens)} color={roleColor} />
        <Metric label="输入↑" value={fmtK(detail.prompt_tokens)} color="var(--color-text-3)" />
        <Metric label="输出↓" value={fmtK(detail.completion_tokens)} color="var(--color-text-3)" />
        <Metric label="调用" value={String(detail.calls)} color="var(--color-text-3)" />
      </div>

      {/* 滚动内容区 */}
      <div
        className="scroll-thin"
        style={{ flex: 1, overflowY: "auto", padding: "12px 16px 24px" }}
      >
        {/* LLM 调用明细 */}
        <Section title="LLM 调用明细" count={detail.llm_calls.length}>
          {detail.llm_calls.map((call, i) => (
            <div
              key={i}
              style={{
                display:      "flex",
                flexDirection: "column",
                gap:          4,
                padding:      "8px 10px",
                borderRadius: 6,
                background:   "rgba(255,255,255,.03)",
                border:       "1px solid rgba(255,255,255,.05)",
                marginBottom: 6,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "var(--color-text-2)", fontSize: 11 }}>
                  {stageLabel(call.stage, call.iteration)}
                </span>
                <span style={{ color: roleColor, fontWeight: 700, fontSize: 12 }}>
                  {fmtK(call.total_tokens)}
                </span>
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                <TokenBar label="↑" value={call.prompt_tokens} total={call.total_tokens} color="var(--acc-cyan)" />
                <TokenBar label="↓" value={call.completion_tokens} total={call.total_tokens} color="var(--acc-violet)" />
              </div>
            </div>
          ))}
        </Section>

        {/* 工具调用统计 */}
        {toolEntries.length > 0 && (
          <Section title="工具调用统计" count={toolEntries.reduce((s, [, n]) => s + n, 0)}>
            {toolEntries.map(([name, count]) => (
              <div
                key={name}
                style={{
                  display:      "flex",
                  alignItems:   "center",
                  justifyContent: "space-between",
                  padding:      "5px 10px",
                  borderRadius: 5,
                  background:   "rgba(255,255,255,.025)",
                  marginBottom: 4,
                }}
              >
                <span style={{ color: "var(--color-text-3)", fontSize: 11 }}>{name}</span>
                <span
                  style={{
                    color:       "var(--acc-amber)",
                    fontWeight:  600,
                    fontSize:    12,
                    minWidth:    20,
                    textAlign:   "right",
                  }}
                >
                  × {count}
                </span>
              </div>
            ))}
          </Section>
        )}
      </div>
    </div>
  );
}

/* ── 小型子组件 ──────────────────────────────────────────────────── */
function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          display:      "flex",
          alignItems:   "center",
          gap:          6,
          marginBottom: 8,
        }}
      >
        <span
          style={{
            color:         "var(--color-text-4)",
            fontSize:      10,
            letterSpacing: ".1em",
            textTransform: "uppercase",
          }}
        >
          {title}
        </span>
        <span
          style={{
            background:   "rgba(255,255,255,.06)",
            borderRadius: 4,
            padding:      "1px 5px",
            fontSize:     10,
            color:        "var(--color-text-3)",
          }}
        >
          {count}
        </span>
      </div>
      {children}
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ color: "var(--color-text-4)", fontSize: 9, letterSpacing: ".1em", textTransform: "uppercase" }}>
        {label}
      </span>
      <span style={{ color, fontWeight: 700, fontSize: 13 }}>{value}</span>
    </div>
  );
}

function TokenBar({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5, flex: 1 }}>
      <span style={{ color: "var(--color-text-4)", fontSize: 10, width: 10 }}>{label}</span>
      <div
        style={{
          flex:         1,
          height:       3,
          borderRadius: 2,
          background:   "rgba(255,255,255,.07)",
          overflow:     "hidden",
        }}
      >
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
      <span style={{ color: "var(--color-text-3)", fontSize: 10, minWidth: 28, textAlign: "right" }}>
        {fmtK(value)}
      </span>
    </div>
  );
}
