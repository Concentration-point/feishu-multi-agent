import type { CSSProperties } from "react";
import type { DagNodeData, DagEdgeData } from "./dagTypes";
import { NODE_W, NODE_H } from "./DAGNode";

const STROKE: Record<string, string> = {
  done:     "var(--acc-mint)",
  active:   "var(--acc-cyan)",
  queued:   "rgba(255,255,255,.15)",
  rejected: "var(--acc-coral)",
};

const DASH: Record<string, string> = {
  done:     "none",
  active:   "4 4",
  queued:   "3 4",
  rejected: "6 4",
};

const MARKER_ID: Record<string, string> = {
  done:     "dag-arr-mint",
  active:   "dag-arr-cyan",
  queued:   "dag-arr-muted",
  rejected: "dag-arr-coral",
};

interface EdgeProps {
  edge:  DagEdgeData;
  nodes: Record<string, DagNodeData>;
}

export function DAGEdge({ edge, nodes }: EdgeProps) {
  const a = nodes[edge.from];
  const b = nodes[edge.to];
  if (!a || !b) return null;

  const aw = a.w ?? NODE_W;
  const ah = a.h ?? NODE_H;
  const bw = b.w ?? NODE_W;
  const bh = b.h ?? NODE_H;

  const stroke = STROKE[edge.state] ?? "rgba(255,255,255,.15)";
  const dash   = DASH[edge.state]   ?? "none";
  const marker = MARKER_ID[edge.state] ?? "dag-arr-muted";

  if (edge.curve === "loop") {
    const sx = a.x;
    const sy = a.y + 14;
    const ex = b.x + bw;
    const ey = b.y + bh - 14;
    const d  = `M ${sx} ${sy} C ${sx - 80} ${sy - 70}, ${ex + 80} ${ey + 70}, ${ex} ${ey}`;
    const lx = (sx + ex) / 2 - 54;
    const ly = Math.min(sy, ey) - 90;
    return (
      <g>
        <path
          d={d}
          stroke={stroke}
          strokeWidth="1.6"
          fill="none"
          strokeDasharray={dash}
          markerEnd={`url(#${marker})`}
          style={{ animation: "flow-dash 1s linear infinite" }}
        />
        <foreignObject x={lx} y={ly} width={110} height={22}>
          <div style={{
            display:      "inline-block",
            padding:      "3px 8px",
            fontFamily:   "var(--font-mono)",
            fontSize:     10,
            letterSpacing: ".04em",
            color:        "var(--acc-coral)",
            background:   "var(--color-bg-1)",
            border:       "1px solid var(--acc-coral-border)",
            borderRadius: 4,
            boxShadow:    "0 0 10px var(--acc-coral-bg)",
            whiteSpace:   "nowrap",
          }}>✕ rejected · retry</div>
        </foreignObject>
      </g>
    );
  }

  const x1 = a.x + aw;
  const y1 = a.y + ah / 2;
  const x2 = b.x;
  const y2 = b.y + bh / 2;
  const cx = (x1 + x2) / 2;
  const d  = `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;

  return (
    <g>
      <path
        d={d}
        stroke={stroke}
        strokeWidth="1.6"
        fill="none"
        strokeDasharray={dash}
        markerEnd={`url(#${marker})`}
        style={{ animation: edge.state === "active" ? "flow-dash 1s linear infinite" : "none" }}
      />
      {edge.state === "active" && (
        <circle
          r={3.5}
          fill="var(--acc-cyan)"
          style={{
            filter:      "drop-shadow(0 0 8px var(--acc-cyan))",
            offsetPath:  `path("${d}")`,
            animation:   "flow-particle 2s linear infinite",
          } as CSSProperties & { offsetPath?: string }}
        />
      )}
    </g>
  );
}

export function DAGMarkerDefs() {
  const defs: [string, string][] = [
    ["dag-arr-mint",  "var(--acc-mint)"],
    ["dag-arr-cyan",  "var(--acc-cyan)"],
    ["dag-arr-muted", "rgba(255,255,255,.15)"],
    ["dag-arr-coral", "var(--acc-coral)"],
  ];
  return (
    <defs>
      {defs.map(([id, fill]) => (
        <marker
          key={id}
          id={id}
          viewBox="0 0 10 10"
          refX="9" refY="5"
          markerWidth="6" markerHeight="6"
          orient="auto"
        >
          <path d="M0,0 L10,5 L0,10 Z" fill={fill} />
        </marker>
      ))}
    </defs>
  );
}
