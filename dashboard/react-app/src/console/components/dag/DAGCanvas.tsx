import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { DagNodeData, DagEdgeData } from "./dagTypes";
import { DAGNode, NODE_W } from "./DAGNode";
import { DAGEdge, DAGMarkerDefs } from "./DAGEdge";

const CANVAS_W = 1480;
const CANVAS_H = 600;

const STAGE_RAILS = [
  { x: 100,  label: "01 · INTAKE",          color: "cyan"   },
  { x: 360,  label: "02 · STRATEGY",        color: "violet" },
  { x: 660,  label: "03 · DRAFT",           color: "rose"   },
  { x: 980,  label: "04 · REVIEW",          color: "amber"  },
  { x: 1240, label: "05 · DELIVER",         color: "mint"   },
];

interface DAGCanvasProps {
  nodes:         DagNodeData[];
  edges:         DagEdgeData[];
  activeNodeId?: string | null;
  onNodeClick?:  (id: string) => void;
  header?:       ReactNode;
}

export function DAGCanvas({ nodes, edges, activeNodeId, onNodeClick, header }: DAGCanvasProps) {
  const [zoom, setZoom] = useState(0.78);
  const [pan,  setPan]  = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!wrapRef.current) return;
    const r = wrapRef.current.getBoundingClientRect();
    setPan({
      x: (r.width  - CANVAS_W * 0.78) / 2,
      y: (r.height - CANVAS_H * 0.78) / 2,
    });
  }, []);

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (!wrapRef.current) return;
    const r      = wrapRef.current.getBoundingClientRect();
    const mx     = e.clientX - r.left;
    const my     = e.clientY - r.top;
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const next   = Math.max(0.25, Math.min(2.5, zoom * factor));
    setZoom(next);
    setPan({ x: mx - (mx - pan.x) * (next / zoom), y: my - (my - pan.y) * (next / zoom) });
  };

  const onMouseDown = (e: React.MouseEvent) => {
    const t = e.target as HTMLElement;
    if (t.closest("[data-node]") || t.closest("[data-control]")) return;
    dragRef.current = { sx: e.clientX, sy: e.clientY, px: pan.x, py: pan.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragRef.current) return;
    const d = dragRef.current;
    setPan({ x: d.px + (e.clientX - d.sx), y: d.py + (e.clientY - d.sy) });
  };
  const onMouseUp = () => { dragRef.current = null; };

  const fitView = () => {
    if (!wrapRef.current) return;
    const r = wrapRef.current.getBoundingClientRect();
    const z = Math.min((r.width - 60) / CANVAS_W, (r.height - 60) / CANVAS_H);
    setZoom(z);
    setPan({ x: (r.width - CANVAS_W * z) / 2, y: (r.height - CANVAS_H * z) / 2 });
  };
  const resetZoom = () => {
    if (!wrapRef.current) return;
    const r = wrapRef.current.getBoundingClientRect();
    setZoom(1);
    setPan({ x: (r.width - CANVAS_W) / 2, y: (r.height - CANVAS_H) / 2 });
  };

  const nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));

  return (
    <div
      ref={wrapRef}
      onWheel={onWheel}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      style={{
        position:  "absolute",
        inset:     0,
        overflow:  "hidden",
        cursor:    dragRef.current ? "grabbing" : "grab",
        background: `
          radial-gradient(ellipse at 30% 50%, rgba(168,155,255,.05) 0%, transparent 55%),
          radial-gradient(ellipse at 75% 50%, rgba(111,217,241,.04) 0%, transparent 55%),
          var(--color-bg-0)
        `,
      }}
    >
      {/* 点阵 grid（随 pan/zoom 同步移动） */}
      <div style={{
        position:            "absolute",
        inset:               0,
        backgroundImage:     "radial-gradient(circle, rgba(255,255,255,.04) 1px, transparent 1px)",
        backgroundSize:      `${24 * zoom}px ${24 * zoom}px`,
        backgroundPosition:  `${pan.x}px ${pan.y}px`,
        pointerEvents:       "none",
      }} />

      {/* 右下角 Zoom 控件 */}
      <div data-control style={{
        position:       "absolute",
        bottom:         16,
        right:          16,
        display:        "flex",
        flexDirection:  "column",
        background:     "var(--color-bg-1)",
        border:         "1px solid rgba(255,255,255,.07)",
        borderRadius:   8,
        overflow:       "hidden",
        zIndex:         10,
        boxShadow:      "0 4px 12px rgba(0,0,0,.4)",
      }}>
        <ZoomBtn title="放大" onClick={() => setZoom((z) => Math.min(2.5, z * 1.2))}>+</ZoomBtn>
        <HRule />
        <div data-control style={{
          padding:     "4px 0",
          textAlign:   "center",
          fontFamily:  "var(--font-mono)",
          fontSize:    10,
          color:       "var(--color-text-3)",
          minWidth:    32,
        }}>{Math.round(zoom * 100)}%</div>
        <HRule />
        <ZoomBtn title="缩小" onClick={() => setZoom((z) => Math.max(0.25, z / 1.2))}>−</ZoomBtn>
        <HRule />
        <ZoomBtn title="适应窗口" small onClick={fitView}>⤢</ZoomBtn>
        <HRule />
        <ZoomBtn title="重置 1:1" small onClick={resetZoom}>1:1</ZoomBtn>
      </div>

      {/* 操作提示 */}
      <div data-control style={{
        position:     "absolute",
        bottom:       16,
        right:        72,
        fontFamily:   "var(--font-mono)",
        fontSize:     10,
        color:        "var(--color-text-4)",
        background:   "var(--color-bg-1)",
        border:       "1px solid rgba(255,255,255,.07)",
        padding:      "5px 9px",
        borderRadius: 6,
        zIndex:       10,
      }}>scroll = zoom · drag = pan</div>

      {/* 画布内容区 */}
      <div style={{
        position:        "absolute",
        left:            0,
        top:             0,
        width:           CANVAS_W,
        height:          CANVAS_H,
        transform:       `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
        transformOrigin: "0 0",
      }}>
        {/* 可选 header（run 信息） */}
        {header}

        {/* 泳道 rails */}
        {STAGE_RAILS.map((s) => (
          <StageRail key={s.x} x={s.x} label={s.label} color={s.color} />
        ))}

        {/* SVG 边线层 */}
        <svg style={{
          position:     "absolute",
          left:         0,
          top:          0,
          width:        CANVAS_W,
          height:       CANVAS_H,
          pointerEvents:"none",
          overflow:     "visible",
        }}>
          <DAGMarkerDefs />
          {edges.map((e, i) => (
            <DAGEdge key={`${e.from}-${e.to}-${i}`} edge={e} nodes={nodeMap} />
          ))}
        </svg>

        {/* 节点层 */}
        {nodes.map((n) => (
          <DAGNode
            key={n.id}
            node={n}
            active={activeNodeId === n.id}
            onClick={() => onNodeClick?.(n.id)}
          />
        ))}

        {/* 图例 */}
        <Legend />
      </div>
    </div>
  );
}

function StageRail({ x, label, color }: { x: number; label: string; color: string }) {
  return (
    <>
      <div style={{
        position:     "absolute",
        left:         x - 10,
        top:          110,
        width:        NODE_W + 20,
        height:       460,
        border:       "1px dashed rgba(255,255,255,.07)",
        borderRadius: 12,
        pointerEvents:"none",
      }} />
      <div style={{
        position:      "absolute",
        left:          x,
        top:           122,
        fontFamily:    "var(--font-mono)",
        fontSize:      10,
        letterSpacing: ".16em",
        color:         `var(--acc-${color})`,
        pointerEvents: "none",
      }}>{label}</div>
    </>
  );
}

const LEGEND_ITEMS = [
  { color: "var(--acc-mint)",          label: "complete",           dashed: false },
  { color: "var(--acc-cyan)",          label: "active",             dashed: true  },
  { color: "rgba(255,255,255,.15)",    label: "queued",             dashed: true  },
  { color: "var(--acc-coral)",         label: "rejected · loop",    dashed: true  },
];

function Legend() {
  return (
    <div style={{
      position:    "absolute",
      bottom:      16,
      left:        24,
      padding:     "10px 14px",
      background:  "var(--color-bg-1)",
      border:      "1px solid rgba(255,255,255,.07)",
      borderRadius: 8,
      display:     "flex",
      alignItems:  "center",
      gap:         16,
    }}>
      <span style={{
        fontFamily:    "var(--font-mono)",
        fontSize:      10,
        letterSpacing: ".1em",
        textTransform: "uppercase",
        color:         "var(--color-text-4)",
      }}>Legend</span>
      {LEGEND_ITEMS.map((item) => (
        <span key={item.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            width:      22,
            height:     1.5,
            display:    "inline-block",
            background: item.dashed
              ? `repeating-linear-gradient(90deg, ${item.color} 0 4px, transparent 4px 8px)`
              : item.color,
          }} />
          <span style={{
            fontFamily:  "var(--font-mono)",
            fontSize:    10.5,
            color:       "var(--color-text-3)",
          }}>{item.label}</span>
        </span>
      ))}
    </div>
  );
}

function ZoomBtn({
  children, onClick, title, small,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  small?: boolean;
}) {
  return (
    <button
      data-control
      onClick={onClick}
      title={title}
      style={{
        width:       32,
        height:      small ? 24 : 28,
        border:      "none",
        background:  "transparent",
        color:       "var(--color-text-2)",
        fontFamily:  "var(--font-mono)",
        fontSize:    small ? 10 : 14,
        cursor:      "pointer",
        display:     "grid",
        placeItems:  "center",
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--color-bg-2)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
    >{children}</button>
  );
}

function HRule() {
  return <div style={{ height: 1, background: "rgba(255,255,255,.07)" }} />;
}
