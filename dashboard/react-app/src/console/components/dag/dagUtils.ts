/**
 * dagUtils — 从 AgentSession 派生 DAG 节点/边数据
 *
 * timelineSteps 索引：
 *   [0] account  [1] strategy  [2] copy  [3] review  [4] pm
 */

import type {
  AgentSession,
  TimelineStep,
  ContentDraft,
  ReviewItem,
} from "../../types";
import type { DagNodeData, DagEdgeData, NodeState } from "./dagTypes";

const NODE_W = 200;
const NODE_H = 96;

const COLS = {
  intake:   100,
  strategy: 360,
  draft:    660,
  review:   980,
  deliver:  1240,
} as const;

const PLATFORM_LABEL: Record<string, string> = {
  gzh:   "公众号",
  xhs:   "小红书",
  dy:    "抖音",
  wb:    "微博",
  bili:  "B站",
  zhihu: "知乎",
  other: "通用",
};

/* ── 辅助：TimelineStep → NodeState / pct ─────────────────────────── */

function stepState(step: TimelineStep | undefined): NodeState {
  if (!step) return "queued";
  if (step.done)    return "done";
  if (step.current) return "active";
  return "queued";
}

/**
 * 从 roleCounts 推算当前 active 节点的进度百分比。
 * 每个角色的"典型工具调用总数"不同，用权重把 call 数映射到 0-90%。
 */
function activePct(
  role: "account" | "strategy" | "copy" | "review" | "pm",
  roleCounts: AgentSession["roleCounts"],
): number {
  const weights = { account: 12, strategy: 8, copy: 4, review: 10, pm: 12 } as const;
  const count   = roleCounts?.[role] ?? 0;
  return Math.min(90, count * weights[role]);
}

function stepPct(
  step: TimelineStep | undefined,
  role: "account" | "strategy" | "copy" | "review" | "pm",
  roleCounts: AgentSession["roleCounts"],
): number {
  if (!step)        return 0;
  if (step.done)    return 100;
  if (step.current) return activePct(role, roleCounts);
  return 0;
}

function nodeToEdge(state: NodeState): DagEdgeData["state"] {
  if (state === "done")   return "done";
  if (state === "active") return "active";
  return "queued";
}

/* ── 辅助：草稿节点状态 ───────────────────────────────────────────── */

function draftNodeState(
  draft: ContentDraft,
  rejectedSeqs: Set<number>,
  copyStep: TimelineStep | undefined,
  roleCounts: AgentSession["roleCounts"],
): { state: NodeState; pct: number; stat: string } {
  if (rejectedSeqs.has(draft.seq)) {
    return { state: "rejected", pct: 100, stat: "驳回 · 重写中" };
  }
  if (draft.status === "done" || draft.status === "review") {
    const wc = draft.wordCount > 0 ? `${draft.wordCount}字` : "已完成";
    return { state: "done", pct: 100, stat: wc };
  }
  // draft.status === "draft"
  const running = copyStep?.current ?? false;
  return {
    state: running ? "active" : "queued",
    pct:   running ? activePct("copy", roleCounts) : 0,
    stat:  running ? "↻ 撰写中" : "排队中",
  };
}

/* ── 辅助：计算 N 个草稿节点的纵向坐标 ─────────────────────────── */

function cwYPositions(count: number): number[] {
  const spacing = 24;
  const totalH  = count * NODE_H + (count - 1) * spacing;
  const railTop = 130;                        // 泳道顶部留出标签
  const railH   = 460;                        // 泳道高度
  const baseY   = railTop + Math.max(0, (railH - totalH) / 2);
  return Array.from({ length: count }, (_, i) => baseY + i * (NODE_H + spacing));
}

/* ── 主导出 ──────────────────────────────────────────────────────── */

export function deriveDagData(session: AgentSession): {
  nodes: DagNodeData[];
  edges: DagEdgeData[];
} {
  const steps   = session.timelineSteps;   // 长度 5，可能为空
  const drafts  = session.copywriter?.drafts ?? [];
  const reviews = session.reviewer?.items  ?? [];

  const nodes: DagNodeData[] = [];
  const edges: DagEdgeData[] = [];

  /* Account ────────────────────────────────────────────────────── */
  const accStep    = steps[0];
  const accState   = stepState(accStep);
  const accCount   = session.roleCounts?.account ?? 0;
  const accStat    = accStep?.done
    ? (accCount > 0 ? `${accCount} tools · 完成` : "已完成")
    : accStep?.current
    ? `↻ ${accCount} tools`
    : "排队中";

  nodes.push({
    id: "account", stage: "INTAKE",
    x: COLS.intake, y: 280, w: NODE_W, h: NODE_H,
    label: "客户经理", sub: "Brief 解读", code: "A1", tone: "cyan",
    state: accState, pct: stepPct(accStep, "account", session.roleCounts), stat: accStat,
  });

  /* Strategist ─────────────────────────────────────────────────── */
  const strStep  = steps[1];
  const strState = stepState(strStep);
  const strCount = session.roleCounts?.strategy ?? 0;
  const strStat  = strStep?.done
    ? (strCount > 0 ? `${strCount} tools · 完成` : "已完成")
    : strStep?.current
    ? `↻ ${strCount} tools`
    : "排队中";

  nodes.push({
    id: "strategist", stage: "STRATEGY",
    x: COLS.strategy, y: 280, w: NODE_W, h: NODE_H,
    label: "策略师", sub: "内容总纲 + 渠道", code: "S1", tone: "violet",
    state: strState, pct: stepPct(strStep, "strategy", session.roleCounts), stat: strStat,
  });

  edges.push({ from: "account", to: "strategist", state: nodeToEdge(accState) });

  /* Copywriter 节点（fan-out 或单节点占位） ─────────────────────── */
  const copyStep = steps[2];

  // 被驳回的草稿 seq 集合（从 ReviewItem 中提取）
  const rejectedSeqs = new Set(
    reviews
      .filter((r: ReviewItem) => r.verdict === "reject" || r.action === "REJECT")
      .map((r: ReviewItem) => r.draftSeq)
  );

  if (drafts.length === 0) {
    /* 无草稿 → 单个占位节点 */
    const cwState = stepState(copyStep);
    nodes.push({
      id: "cw_0", stage: "DRAFT",
      x: COLS.draft, y: 280, w: NODE_W, h: NODE_H,
      label: "文案", sub: "内容撰写", code: "C1", tone: "rose",
      state: cwState,
      pct:   stepPct(copyStep, "copy", session.roleCounts),
      stat:  copyStep?.current ? "↻ 撰写中" : copyStep?.done ? "已完成" : "排队中",
    });
    edges.push({ from: "strategist", to: "cw_0", state: nodeToEdge(strState) });
    edges.push({ from: "cw_0", to: "reviewer",  state: nodeToEdge(cwState)  });
  } else {
    /* fan-out：每条草稿一个节点 */
    const ys = cwYPositions(drafts.length);

    drafts.forEach((draft: ContentDraft, i: number) => {
      const cwId   = `cw_${draft.seq}`;
      const { state, pct, stat } = draftNodeState(draft, rejectedSeqs, copyStep, session.roleCounts);
      const platform = draft.platform !== "other"
        ? (PLATFORM_LABEL[draft.platform] ?? draft.platform)
        : draft.contentType;

      nodes.push({
        id: cwId, stage: "DRAFT",
        x: COLS.draft, y: ys[i], w: NODE_W, h: NODE_H,
        label: `文案 #${draft.seq}`,
        sub:   platform,
        code:  `C${draft.seq}`,
        tone:  "rose",
        state, pct, stat,
      });

      // 策略师 → 文案：策略师已完成就算边已激活/完成
      edges.push({ from: "strategist", to: cwId, state: nodeToEdge(strState) });

      // 文案 → 审核：草稿已发出则 done，否则 queued
      const toReviewState: DagEdgeData["state"] =
        (draft.status === "review" || draft.status === "done") ? "done" : "queued";
      edges.push({ from: cwId, to: "reviewer", state: toReviewState });

      // 驳回回路
      if (state === "rejected") {
        edges.push({ from: "reviewer", to: cwId, state: "rejected", curve: "loop" });
      }
    });
  }

  /* Reviewer ───────────────────────────────────────────────────── */
  const revStep    = steps[3];
  let   revState:  NodeState;
  let   revPct:    number;
  let   revStat:   string;

  if (reviews.length > 0) {
    const approveCount = reviews.filter((r: ReviewItem) => r.verdict === "approve").length;
    const rejectCount  = reviews.filter((r: ReviewItem) => r.verdict === "reject").length;
    if (revStep?.done || approveCount === reviews.length) {
      revState = "done";
      revPct   = 100;
      revStat  = `${reviews.length} 篇全通过`;
    } else {
      revState = revStep?.current ? "active" : "done";
      revPct   = Math.round((approveCount / reviews.length) * 100);
      revStat  = rejectCount > 0
        ? `↻ ${rejectCount} 篇驳回`
        : `↻ ${session.roleCounts?.review ?? 0} tools`;
    }
  } else {
    revState = stepState(revStep);
    revPct   = stepPct(revStep, "review", session.roleCounts);
    revStat  = revStep?.current
      ? `↻ ${session.roleCounts?.review ?? 0} tools`
      : revStep?.done ? "审核完成" : "等待文案";
  }

  nodes.push({
    id: "reviewer", stage: "REVIEW",
    x: COLS.review, y: 280, w: NODE_W, h: NODE_H,
    label: "审核", sub: "质量门 + 品牌", code: "R1", tone: "amber",
    state: revState, pct: revPct, stat: revStat,
  });

  /* PM ─────────────────────────────────────────────────────────── */
  const pmStep  = steps[4];
  const pmState = pmStep ? stepState(pmStep) : ("idle" as NodeState);
  const pmCount = session.roleCounts?.pm ?? 0;
  const pmStat  = pmStep?.done
    ? (pmCount > 0 ? `${pmCount} tools · 已交付` : "已交付")
    : pmStep?.current
    ? `↻ ${pmCount} tools`
    : "等待上游";

  nodes.push({
    id: "pm", stage: "DELIVER",
    x: COLS.deliver, y: 280, w: NODE_W, h: NODE_H,
    label: "项目经理", sub: "编排交付", code: "P1", tone: "mint",
    state: pmState, pct: stepPct(pmStep, "pm", session.roleCounts), stat: pmStat,
  });

  edges.push({ from: "reviewer", to: "pm", state: nodeToEdge(revState) });

  return { nodes, edges };
}
