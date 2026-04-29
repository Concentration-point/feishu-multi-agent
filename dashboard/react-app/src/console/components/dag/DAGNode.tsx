import type { DagNodeData } from "./dagTypes";

export const NODE_W = 200;
export const NODE_H = 96;

const TONE: Record<string, { main: string; bg: string; border: string }> = {
  mint:   { main: "var(--acc-mint)",   bg: "var(--acc-mint-bg)",   border: "var(--acc-mint-border)"   },
  cyan:   { main: "var(--acc-cyan)",   bg: "var(--acc-cyan-bg)",   border: "var(--acc-cyan-border)"   },
  violet: { main: "var(--acc-violet)", bg: "var(--acc-violet-bg)", border: "var(--acc-violet-border)" },
  rose:   { main: "var(--acc-rose)",   bg: "var(--acc-rose-bg)",   border: "var(--acc-rose-border)"   },
  amber:  { main: "var(--acc-amber)",  bg: "var(--acc-amber-bg)",  border: "var(--acc-amber-border)"  },
};

const STATE_STRIPE: Record<string, { color: string; glow: string }> = {
  done:     { color: "var(--acc-mint)",          glow: "var(--glow-mint)" },
  active:   { color: "var(--acc-cyan)",          glow: "var(--glow-cyan)" },
  queued:   { color: "rgba(255,255,255,.15)",    glow: "none" },
  idle:     { color: "rgba(255,255,255,.08)",    glow: "none" },
  rejected: { color: "var(--acc-coral)",         glow: "0 0 20px rgba(240,134,114,.15)" },
};

const STATE_GLYPH: Record<string, { ch: string; color: string }> = {
  done:     { ch: "✓", color: "var(--acc-mint)"  },
  active:   { ch: "↻", color: "var(--acc-cyan)"  },
  queued:   { ch: "◌", color: "rgba(255,255,255,.3)" },
  idle:     { ch: "·", color: "rgba(255,255,255,.2)" },
  rejected: { ch: "✕", color: "var(--acc-coral)" },
};

interface DAGNodeProps {
  node:    DagNodeData;
  active?: boolean;
  onClick?: () => void;
}

export function DAGNode({ node, active = false, onClick }: DAGNodeProps) {
  const w      = node.w ?? NODE_W;
  const h      = node.h ?? NODE_H;
  const tone   = TONE[node.tone]          ?? TONE.mint;
  const stripe = STATE_STRIPE[node.state] ?? STATE_STRIPE.idle;
  const glyph  = STATE_GLYPH[node.state]  ?? STATE_GLYPH.idle;
  const isActive   = node.state === "active";
  const isRejected = node.state === "rejected";

  return (
    <div
      data-node
      onClick={onClick}
      title="点击查看详情"
      style={{
        position:   "absolute",
        left:       node.x,
        top:        node.y,
        width:      w,
        height:     h,
        background: "var(--color-bg-2)",
        border:     `1px solid ${active ? tone.border : "rgba(255,255,255,.07)"}`,
        borderRadius: 10,
        cursor:     "pointer",
        overflow:   "hidden",
        boxShadow:  active
          ? `0 0 0 2px ${tone.bg}, ${stripe.glow !== "none" ? stripe.glow : "none"}`
          : stripe.glow !== "none" ? stripe.glow : undefined,
        transition: "border-color .18s, box-shadow .18s",
      }}
    >
      {/* 左侧状态色条 */}
      <div style={{
        position:   "absolute",
        left: 0, top: 0, bottom: 0,
        width:      3,
        background: stripe.color,
        animation:  isActive ? "pua-pulse 1.6s ease-in-out infinite" : "none",
      }} />

      <div style={{
        padding:        "10px 13px 10px 15px",
        display:        "flex",
        flexDirection:  "column",
        gap:            5,
        height:         "100%",
        boxSizing:      "border-box",
      }}>
        {/* 顶部：code 徽章 + 名称 + state 图标 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{
              fontFamily:      "var(--font-mono)",
              fontSize:        9.5,
              letterSpacing:   ".1em",
              padding:         "2px 6px",
              borderRadius:    3,
              background:      tone.bg,
              color:           tone.main,
              border:          `1px solid ${tone.border}`,
            }}>{node.code}</span>
            <span style={{ fontSize: 13, fontWeight: 500, color: "var(--color-text-1)" }}>
              {node.label}
            </span>
          </div>
          <StateGlyph glyph={glyph} pulse={isActive} />
        </div>

        {/* 副标题 */}
        <div style={{ fontSize: 11.5, color: "var(--color-text-3)" }}>
          {node.sub}
        </div>

        {/* 底部：进度条 + metadata */}
        <div style={{ marginTop: "auto" }}>
          {node.state !== "idle" && node.state !== "queued" && (
            <ProgressBar pct={node.pct} color={isRejected ? "var(--acc-coral)" : tone.main} />
          )}
          <div style={{
            fontFamily:  "var(--font-mono)",
            fontSize:    10,
            color:       isRejected ? "var(--acc-coral)" : "var(--color-text-4)",
            marginTop:   5,
          }}>{node.stat}</div>
        </div>
      </div>
    </div>
  );
}

function StateGlyph({ glyph, pulse }: { glyph: { ch: string; color: string }; pulse: boolean }) {
  return (
    <span style={{
      width:       18,
      height:      18,
      borderRadius: "50%",
      border:      `1px solid ${glyph.color}`,
      color:       glyph.color,
      display:     "grid",
      placeItems:  "center",
      fontSize:    10,
      fontFamily:  "var(--font-mono)",
      flexShrink:  0,
      animation:   pulse ? "pua-pulse 1.4s ease-in-out infinite" : "none",
    }}>{glyph.ch}</span>
  );
}

function ProgressBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div style={{
      height:       2,
      borderRadius: 1,
      background:   "rgba(255,255,255,.07)",
      overflow:     "hidden",
    }}>
      <div style={{
        height:       "100%",
        width:        `${Math.min(100, Math.max(0, pct))}%`,
        background:   color,
        borderRadius: 1,
        transition:   "width .6s ease",
      }} />
    </div>
  );
}
