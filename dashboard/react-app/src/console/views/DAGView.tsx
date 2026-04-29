import { useCallback, useMemo, useState } from "react";
import { DAGCanvas } from "../components/dag/DAGCanvas";
import { deriveDagData } from "../components/dag/dagUtils";
import { useConsoleStore } from "../useConsoleStore";
import type { DagNodeData, DagEdgeData } from "../components/dag/dagTypes";
import type { AgentSession, RoleId } from "../types";

/* ── fallback：session 完全为空时展示的静态 mock ──────────────────── */
const COLS = { intake: 100, strategy: 360, draft: 660, review: 980, deliver: 1240 } as const;
const W = 200;
const H = 96;

const FALLBACK_NODES: DagNodeData[] = [
  { id: "account",    stage: "INTAKE",    x: COLS.intake,    y: 280, w: W, h: H, label: "客户经理", sub: "Brief 解读",       tone: "cyan",   state: "queued", pct: 0, code: "A1", stat: "排队中" },
  { id: "strategist", stage: "STRATEGY",  x: COLS.strategy,  y: 280, w: W, h: H, label: "策略师",   sub: "内容总纲 + 渠道",   tone: "violet", state: "queued", pct: 0, code: "S1", stat: "排队中" },
  { id: "cw_0",       stage: "DRAFT",     x: COLS.draft,     y: 280, w: W, h: H, label: "文案",     sub: "内容撰写",          tone: "rose",   state: "queued", pct: 0, code: "C1", stat: "排队中" },
  { id: "reviewer",   stage: "REVIEW",    x: COLS.review,    y: 280, w: W, h: H, label: "审核",     sub: "质量门 + 品牌",     tone: "amber",  state: "queued", pct: 0, code: "R1", stat: "排队中" },
  { id: "pm",         stage: "DELIVER",   x: COLS.deliver,   y: 280, w: W, h: H, label: "项目经理", sub: "编排交付",          tone: "mint",   state: "idle",   pct: 0, code: "P1", stat: "等待上游" },
];

const FALLBACK_EDGES: DagEdgeData[] = [
  { from: "account",    to: "strategist", state: "queued" },
  { from: "strategist", to: "cw_0",       state: "queued" },
  { from: "cw_0",       to: "reviewer",   state: "queued" },
  { from: "reviewer",   to: "pm",         state: "queued" },
];

/* ── 判断 session 是否有实质数据 ──────────────────────────────────── */
function hasRealData(session: AgentSession): boolean {
  return (
    session.timelineSteps?.length > 0 ||
    session.copywriter?.drafts?.length > 0 ||
    session.reviewer?.items?.length > 0
  );
}

interface DAGViewProps {
  session: AgentSession;
}

/* 节点 ID → 对应的角色 tab */
const NODE_TO_ROLE: Record<string, RoleId> = {
  account:    "account",
  strategist: "strategy",
  reviewer:   "review",
  pm:         "pm",
};

function nodeIdToRole(nodeId: string): RoleId | null {
  if (nodeId in NODE_TO_ROLE) return NODE_TO_ROLE[nodeId];
  if (nodeId.startsWith("cw_")) return "copy";
  return null;
}

export function DAGView({ session }: DAGViewProps) {
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const { setRole, setGraphMode } = useConsoleStore();

  /* 节点点击：高亮 → 切换至对应角色视图 */
  const handleNodeClick = useCallback((nodeId: string) => {
    setActiveNodeId(nodeId);
    const role = nodeIdToRole(nodeId);
    if (role) {
      setRole(role);
      setGraphMode(false);
    }
  }, [setRole, setGraphMode]);

  /* 从 session 派生节点/边（memoized，避免每帧重算） */
  const { nodes, edges } = useMemo(() => {
    if (hasRealData(session)) {
      return deriveDagData(session);
    }
    return { nodes: FALLBACK_NODES, edges: FALLBACK_EDGES };
  }, [session]);

  /* 统计徽章数据 */
  const activeCount   = nodes.filter((n) => n.state === "active").length;
  const rejectedCount = nodes.filter((n) => n.state === "rejected").length;
  const doneCount     = nodes.filter((n) => n.state === "done").length;

  const header = (
    <>
      {/* Run 信息（左上，跟随画布 transform） */}
      <div style={{
        position:      "absolute",
        left:          24,
        top:           20,
        display:       "flex",
        flexDirection: "column",
        gap:           6,
        pointerEvents: "none",
      }}>
        <span style={{
          fontFamily:    "var(--font-mono)",
          fontSize:      10,
          letterSpacing: ".12em",
          textTransform: "uppercase",
          color:         "var(--acc-cyan)",
        }}>
          {session.campaign || "pipeline"} · {session.timeline || "live"}
        </span>
        <h2 style={{
          margin:        0,
          fontSize:      18,
          fontWeight:    500,
          letterSpacing: "-.01em",
          color:         "var(--color-text-1)",
          maxWidth:      480,
        }}>{session.client || "Agent Console"}</h2>
      </div>

      {/* Stats pills（右上，跟随画布 transform） */}
      <div style={{
        position:      "absolute",
        top:           20,
        right:         24,
        display:       "flex",
        gap:           8,
        pointerEvents: "none",
      }}>
        <StatPill label="done"     value={String(doneCount)}     tone="mint"   />
        <StatPill label="active"   value={String(activeCount)}   tone="cyan"   />
        <StatPill label="rejected" value={String(rejectedCount)} tone="coral"  />
      </div>
    </>
  );

  return (
    <div style={{ width: "100%", height: "100%", position: "relative", overflow: "hidden" }}>
      <DAGCanvas
        nodes={nodes}
        edges={edges}
        activeNodeId={activeNodeId}
        onNodeClick={handleNodeClick}
        header={header}
      />
    </div>
  );
}

function StatPill({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div style={{
      display:     "flex",
      alignItems:  "center",
      gap:         8,
      padding:     "6px 11px",
      background:  "var(--color-bg-1)",
      border:      "1px solid rgba(255,255,255,.07)",
      borderRadius: 7,
    }}>
      <span style={{
        fontFamily:    "var(--font-mono)",
        fontSize:      10,
        letterSpacing: ".1em",
        textTransform: "uppercase",
        color:         "var(--color-text-4)",
      }}>{label}</span>
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize:   13,
        fontWeight: 600,
        color:      `var(--acc-${tone})`,
      }}>{value}</span>
    </div>
  );
}
