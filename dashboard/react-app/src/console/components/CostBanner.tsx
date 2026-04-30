/**
 * CostBanner — 显示在 DAG 图上方的 LLM token 成本统计条
 *
 * 数据来源：GET /api/costs?record_id=...，每 5s 轮询一次
 * 布局：左侧总量 | 中间按角色分列 | 右侧调用次数
 */

import { useEffect, useState } from "react";
import { usePipelineStore } from "../../stores/usePipelineStore";

/* ── 角色元信息 ─────────────────────────────────────────────────── */
const ROLE_META: Record<string, { label: string; color: string }> = {
  account_manager: { label: "客户经理", color: "var(--acc-cyan)"   },
  strategist:      { label: "策略师",   color: "var(--acc-violet)" },
  copywriter:      { label: "文案",     color: "var(--acc-rose)"   },
  reviewer:        { label: "审核",     color: "var(--acc-amber)"  },
  project_manager: { label: "项目经理", color: "var(--acc-mint)"   },
};

/* ── 数据类型 ────────────────────────────────────────────────────── */
interface RoleStat {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

interface CostSummary {
  record_id: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  by_role: Record<string, RoleStat>;
}

/* ── 工具函数 ────────────────────────────────────────────────────── */
function fmtK(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

/* ── 主组件 ─────────────────────────────────────────────────────── */
export function CostBanner() {
  const recordId = usePipelineStore((s) => s.recordId);
  const [summary, setSummary] = useState<CostSummary | null>(null);

  useEffect(() => {
    if (!recordId) return;

    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(`/api/costs?record_id=${encodeURIComponent(recordId!)}`);
        const data = await res.json();
        if (!cancelled && data.ok) setSummary(data.summary);
      } catch {
        /* 轮询失败不影响 DAG 渲染 */
      }
    }

    poll();
    const timer = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [recordId]);

  const roleEntries = summary
    ? Object.entries(summary.by_role).sort(
        (a, b) => b[1].total_tokens - a[1].total_tokens,
      )
    : [];

  return (
    <div
      style={{
        height:          48,
        flexShrink:      0,
        display:         "flex",
        alignItems:      "center",
        gap:             16,
        padding:         "0 20px",
        background:      "rgba(14, 17, 23, 0.92)",
        borderBottom:    "1px solid rgba(255,255,255,.06)",
        backdropFilter:  "blur(8px)",
        fontFamily:      "var(--font-mono)",
        fontSize:        11,
        letterSpacing:   ".06em",
        overflowX:       "auto",
        scrollbarWidth:  "none",
      }}
    >
      {/* 左：总 token 量 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        <span style={{ color: "var(--color-text-4)", textTransform: "uppercase" }}>
          tokens
        </span>
        <span
          style={{
            color:      summary && summary.total_tokens > 0 ? "var(--acc-cyan)" : "var(--color-text-4)",
            fontWeight: 700,
            fontSize:   14,
          }}
        >
          {summary ? fmtK(summary.total_tokens) : "—"}
        </span>
        {summary && (
          <span style={{ color: "var(--color-text-4)" }}>
            ({fmtK(summary.prompt_tokens)}↑ {fmtK(summary.completion_tokens)}↓)
          </span>
        )}
      </div>

      {/* 分隔线 */}
      <div
        style={{
          width:      1,
          height:     24,
          background: "rgba(255,255,255,.08)",
          flexShrink: 0,
        }}
      />

      {/* 中：按角色分列 */}
      {roleEntries.length > 0 ? (
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {roleEntries.map(([roleId, stat]) => {
            const meta = ROLE_META[roleId] ?? { label: roleId, color: "var(--color-text-3)" };
            return (
              <RolePill
                key={roleId}
                label={meta.label}
                color={meta.color}
                tokens={stat.total_tokens}
                calls={stat.calls}
              />
            );
          })}
        </div>
      ) : (
        <span style={{ color: "var(--color-text-4)" }}>暂无角色数据</span>
      )}

      {/* 弹性空间 */}
      <div style={{ flex: 1 }} />

      {/* 右：总调用次数 */}
      <div
        style={{
          display:    "flex",
          alignItems: "center",
          gap:        6,
          flexShrink: 0,
        }}
      >
        <span style={{ color: "var(--color-text-4)", textTransform: "uppercase" }}>
          calls
        </span>
        <span style={{ color: "var(--color-text-2)", fontWeight: 600 }}>
          {summary ? summary.calls : "—"}
        </span>
      </div>
    </div>
  );
}

/* ── 角色 Token Pill ─────────────────────────────────────────────── */
function RolePill({
  label,
  color,
  tokens,
  calls,
}: {
  label: string;
  color: string;
  tokens: number;
  calls: number;
}) {
  return (
    <div
      title={`${calls} 次调用 · ${tokens.toLocaleString()} tokens`}
      style={{
        display:      "flex",
        alignItems:   "center",
        gap:          6,
        padding:      "3px 9px",
        borderRadius: 5,
        background:   "rgba(255,255,255,.04)",
        border:       "1px solid rgba(255,255,255,.06)",
        cursor:       "default",
      }}
    >
      {/* 角色色点 */}
      <span
        style={{
          width:        6,
          height:       6,
          borderRadius: "50%",
          background:   color,
          flexShrink:   0,
        }}
      />
      <span style={{ color: "var(--color-text-3)" }}>{label}</span>
      <span style={{ color, fontWeight: 600 }}>{fmtK(tokens)}</span>
    </div>
  );
}
