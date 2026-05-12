/**
 * roleProjectors/shared · 跨角色复用的投影函数
 *
 * 包含：时间线 / 工具调用 / 工具统计 / 审计日志 / 风险徽章 / 经验进化 / 工具调用计数。
 * 各角色 deck 之外但仍属 AgentSession 顶层字段的构建都聚在这里。
 */

import type { EventSnapshot } from "../eventNormalizer";
import { ROLE_ORDER, STAGE_LABELS } from "../eventNormalizer";
import { clamp } from "../statusClassifier";
import type {
  AuditEntry,
  ExperienceEvolution,
  MemoryProgressItem,
  RiskBadge,
  RoleId,
  TimelineStep,
  ToolCall,
  ToolStat,
} from "../../types";
import { MEMORY_PROGRESS_DEF } from "../eventNormalizer";

export function buildTimelineSteps(snap: EventSnapshot): TimelineStep[] {
  return STAGE_LABELS.map(({ role, label }) => {
    const current = snap.activeRole === role && !snap.pipelineCompleted;
    const done =
      snap.pipelineCompleted ||
      (snap.activeRole
        ? ROLE_ORDER.indexOf(role) < ROLE_ORDER.indexOf(snap.activeRole)
        : snap.stagesVisited.includes(role));
    return {
      label,
      done: done && !current,
      current,
    };
  });
}

export function buildRoleCounts(snap: EventSnapshot): Record<RoleId, number> {
  const counts: Record<RoleId, number> = {
    account: 0,
    strategy: 0,
    copy: 0,
    review: 0,
    pm: 0,
  };
  for (const agg of snap.toolCallsByKey.values()) {
    counts[agg.role] = (counts[agg.role] ?? 0) + agg.calls;
  }
  return counts;
}

export function buildToolCalls(snap: EventSnapshot): ToolCall[] {
  const out: ToolCall[] = [];
  for (const [key, agg] of snap.toolCallsByKey) {
    const transition =
      agg.stateTransitions.length > 0
        ? agg.stateTransitions[agg.stateTransitions.length - 1]
        : undefined;
    out.push({
      id: key,
      name: agg.name,
      role: agg.role,
      round: agg.round,
      calls: agg.calls,
      avgMs: agg.calls ? Math.round(agg.totalMs / agg.calls) : 0,
      kind: agg.kind,
      producesContent: agg.producesContent,
      stateTransition: transition,
      request: agg.firstRequest,
      response: agg.firstResponse,
      invocations: agg.invocations.length ? agg.invocations : undefined,
    });
  }
  // 按 role 顺序 + name 稳定
  out.sort((a, b) => {
    const ra = ROLE_ORDER.indexOf(a.role);
    const rb = ROLE_ORDER.indexOf(b.role);
    if (ra !== rb) return ra - rb;
    return a.name.localeCompare(b.name);
  });
  return out;
}

export function countByRole(snap: EventSnapshot, role: RoleId): number {
  let n = 0;
  for (const agg of snap.toolCallsByKey.values()) {
    if (agg.role === role) n += agg.calls;
  }
  return n;
}

export function buildMemoryProgress(snap: EventSnapshot): MemoryProgressItem[] {
  const activeIdx = snap.activeRole ? ROLE_ORDER.indexOf(snap.activeRole) : -1;
  return MEMORY_PROGRESS_DEF.map((def, i) => {
    const written =
      snap.writtenFields.has(def.field) || def.field === "draft_content"
        ? def.field === "draft_content"
          ? snap.draftOrder.some((rid) => snap.contentRows.get(rid)?.draft_content)
          : true
        : false;
    let state: MemoryProgressItem["state"] = "pending";
    if (written) state = "done";
    else if (i === activeIdx) state = "current";
    else if (activeIdx >= 0 && i < activeIdx) state = "done";
    return { label: def.label, state };
  });
}

export function buildAuditLog(snap: EventSnapshot): AuditEntry[] {
  return snap.auditLog.slice(-12).reverse();
}

export function buildToolStats(snap: EventSnapshot): ToolStat[] {
  return Array.from(snap.toolStatsMap, ([name, count]) => ({ name, count })).sort(
    (a, b) => b.count - a.count,
  );
}

export function buildRiskBadges(snap: EventSnapshot): RiskBadge[] {
  const badges: RiskBadge[] = [];
  const reviewStatus = snap.writtenFields.get("review_status") ?? "";
  const redFlag = snap.writtenFields.get("review_red_flag") ?? "";

  if (reviewStatus === "timeout_auto_approved") {
    badges.push({ label: "人审超时默认同意", kind: "warn" });
  } else if (reviewStatus === "rejected") {
    badges.push({ label: "人工驳回", kind: "error" });
  } else if (reviewStatus === "approved") {
    badges.push({ label: "人工通过", kind: "ok" });
  }

  if (redFlag && redFlag !== "无") {
    badges.push({ label: `红线风险: ${clamp(redFlag, 24)}`, kind: "error" });
  }

  const wikiWrites = Array.from(snap.toolCallsByKey.values())
    .filter((t) => t.name === "write_wiki")
    .reduce((s, t) => s + t.calls, 0);
  if (wikiWrites > 0) {
    badges.push({ label: `知识沉淀 ${wikiWrites} 次`, kind: "ok" });
  }

  return badges;
}

export function buildExperienceEvolution(snap: EventSnapshot): ExperienceEvolution {
  return {
    cards: snap.experienceCards,
    loadedRoles: snap.experienceLoadedRoles,
    totalDistilled: snap.experienceSummary.total,
    passedScoring: snap.experienceSummary.passed,
    mergedGroups: snap.experienceSummary.merged,
    finalSettled: snap.experienceSummary.settled,
    settled: snap.experienceSettled,
  };
}
