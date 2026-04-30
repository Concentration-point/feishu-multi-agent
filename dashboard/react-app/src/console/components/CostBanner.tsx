/**
 * CostBanner — 显示在 DAG 图上方的 LLM token 成本统计条
 *
 * - 数据来源：GET /api/costs?record_id=...，每 5s 轮询一次
 * - 点击角色 Pill → 在 DAG 区域右侧弹出 CostDetailDrawer
 * - 布局：左侧总量 | 中间按角色分列 Pill | 右侧调用次数
 */

import { useState } from "react";
import { useEffect } from "react";
import { usePipelineStore } from "../../stores/usePipelineStore";
import { CostDetailDrawer } from "./CostDetailDrawer";
import type { RoleDetail } from "./CostDetailDrawer";

/* ── 角色元信息 ─────────────────────────────────────────────────── */
const ROLE_META: Record<string, { label: string; color: string }> = {
  account_manager: { label: "客户经理", color: "var(--acc-cyan)"   },
  strategist:      { label: "策略师",   color: "var(--acc-violet)" },
  copywriter:      { label: "文案",     color: "var(--acc-rose)"   },
  reviewer:        { label: "审核",     color: "var(--acc-amber)"  },
  project_manager: { label: "项目经理", color: "var(--acc-mint)"   },
};

/* ── 数据类型 ────────────────────────────────────────────────────── */
interface CostSummary {
  record_id: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  by_role: Record<string, RoleDetail>;
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
  const [summary, setSummary]         = useState<CostSummary | null>(null);
  const [activeRole, setActiveRole]   = useState<string | null>(null);

  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;

    async function poll() {
      try {
        const res  = await fetch(`/api/costs?record_id=${encodeURIComponent(recordId!)}`);
        const data = await res.json();
        if (!cancelled && data.ok) setSummary(data.summary);
      } catch { /* 轮询失败不影响 DAG 渲染 */ }
    }

    poll();
    const timer = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [recordId]);

  /* 点击其他区域关闭 Drawer */
  const handleBannerClick = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("[data-role-pill]")) return;
    setActiveRole(null);
  };

  const roleEntries = summary
    ? Object.entries(summary.by_role).sort((a, b) => b[1].total_tokens - a[1].total_tokens)
    : [];

  const activeDetail = activeRole && summary ? summary.by_role[activeRole] : null;
  const activeMeta   = activeRole ? (ROLE_META[activeRole] ?? { label: activeRole, color: "var(--color-text-3)" }) : null;

  return (
    <>
      {/* ── Banner 条 ── */}
      <div
        onClick={handleBannerClick}
        style={{
          height:         48,
          flexShrink:     0,
          display:        "flex",
          alignItems:     "center",
          gap:            16,
          padding:        "0 20px",
          background:     "rgba(14, 17, 23, 0.92)",
          borderBottom:   "1px solid rgba(255,255,255,.06)",
          backdropFilter: "blur(8px)",
          fontFamily:     "var(--font-mono)",
          fontSize:       11,
          letterSpacing:  ".06em",
          overflowX:      "auto",
          scrollbarWidth: "none",
          position:       "relative",
          zIndex:         10,
        }}
      >
        {/* 左：总 token */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <span style={{ color: "var(--color-text-4)", textTransform: "uppercase" }}>tokens</span>
          <span style={{
            color:      summary && summary.total_tokens > 0 ? "var(--acc-cyan)" : "var(--color-text-4)",
            fontWeight: 700,
            fontSize:   14,
          }}>
            {summary ? fmtK(summary.total_tokens) : "—"}
          </span>
          {summary && (
            <span style={{ color: "var(--color-text-4)" }}>
              ({fmtK(summary.prompt_tokens)}↑ {fmtK(summary.completion_tokens)}↓)
            </span>
          )}
        </div>

        {/* 分隔线 */}
        <div style={{ width: 1, height: 24, background: "rgba(255,255,255,.08)", flexShrink: 0 }} />

        {/* 中：角色 Pill */}
        {roleEntries.length > 0 ? (
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {roleEntries.map(([roleId, stat]) => {
              const meta    = ROLE_META[roleId] ?? { label: roleId, color: "var(--color-text-3)" };
              const isActive = activeRole === roleId;
              return (
                <RolePill
                  key={roleId}
                  label={meta.label}
                  color={meta.color}
                  tokens={stat.total_tokens}
                  calls={stat.calls}
                  isActive={isActive}
                  onClick={() => setActiveRole(isActive ? null : roleId)}
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
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          <span style={{ color: "var(--color-text-4)", textTransform: "uppercase" }}>calls</span>
          <span style={{ color: "var(--color-text-2)", fontWeight: 600 }}>
            {summary ? summary.calls : "—"}
          </span>
        </div>
      </div>

      {/* ── 详情 Drawer（绝对定位叠在 DAG 画布上方右侧）── */}
      {activeRole && activeDetail && activeMeta && (
        <CostDetailDrawer
          roleId={activeRole}
          roleLabel={activeMeta.label}
          roleColor={activeMeta.color}
          detail={activeDetail}
          onClose={() => setActiveRole(null)}
        />
      )}
    </>
  );
}

/* ── 角色 Pill ──────────────────────────────────────────────────── */
function RolePill({
  label, color, tokens, calls, isActive, onClick,
}: {
  label: string; color: string; tokens: number; calls: number;
  isActive: boolean; onClick: () => void;
}) {
  return (
    <button
      data-role-pill
      onClick={onClick}
      title={`${calls} 次 LLM 调用 · ${tokens.toLocaleString()} tokens · 点击查看详情`}
      style={{
        display:      "flex",
        alignItems:   "center",
        gap:          6,
        padding:      "3px 9px",
        borderRadius: 5,
        background:   isActive ? "rgba(255,255,255,.09)" : "rgba(255,255,255,.04)",
        border:       `1px solid ${isActive ? color : "rgba(255,255,255,.06)"}`,
        cursor:       "pointer",
        transition:   "background .12s, border-color .12s",
        fontFamily:   "var(--font-mono)",
        fontSize:     11,
      }}
    >
      <span style={{
        width: 6, height: 6, borderRadius: "50%",
        background: color, flexShrink: 0,
        boxShadow: isActive ? `0 0 6px ${color}` : "none",
      }} />
      <span style={{ color: "var(--color-text-3)" }}>{label}</span>
      <span style={{ color, fontWeight: 600 }}>{fmtK(tokens)}</span>
    </button>
  );
}
