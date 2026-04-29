export type NodeState = "done" | "active" | "queued" | "idle" | "rejected";
export type NodeTone  = "mint" | "cyan" | "violet" | "rose" | "amber";

export interface DagNodeData {
  id:    string;
  stage: string;
  label: string;
  sub:   string;
  code:  string;
  tone:  NodeTone;
  state: NodeState;
  pct:   number;
  stat:  string;
  x: number;
  y: number;
  w?: number;
  h?: number;
}

export interface DagEdgeData {
  from:   string;
  to:     string;
  state:  "done" | "active" | "queued" | "rejected";
  curve?: "loop";
}
