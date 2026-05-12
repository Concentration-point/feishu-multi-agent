/**
 * fromEvents · SSE 事件流 → AgentSession 的薄编排层
 *
 * 底层逻辑：
 *   - pipeline.started / stage_changed / completed → 时间线 & 项目元信息
 *   - tool.called + tool.returned 配对 → 耗时、工具统计、审计日志
 *   - batch_create_content.arguments.items → drafts 骨架
 *   - write_content.arguments.value (field_name="draft_content") → drafts 正文（未截断）
 *   - write_project.arguments (field_name="brief_analysis"|"strategy"|"review_summary"|"delivery") → 各角色结构化产出
 *
 * 拆分布局：
 *   - eventNormalizer.ts —— 把事件流折叠成 EventSnapshot
 *   - statusClassifier.ts —— 准入/审核 verdict 正则 + markdown 切片工具
 *   - roleProjectors/{account,strategy,copy,review,pm}.ts —— 各角色 Deck 构造
 *   - roleProjectors/shared.ts —— 跨角色复用的时间线/工具/审计/经验进化构造
 *
 * 本文件只做"对外 API + 编排"，不再承载具体投影逻辑。
 */

import type { PipelineEvent } from "../../types";
import type { AgentSession } from "../types";
import { aggregate } from "./eventNormalizer";
import { buildAccountDeck } from "./roleProjectors/account";
import { buildStrategyDeck } from "./roleProjectors/strategy";
import { buildCopywriterDeck } from "./roleProjectors/copy";
import { buildReviewerDeck } from "./roleProjectors/review";
import { buildPMDeck } from "./roleProjectors/pm";
import {
  buildAuditLog,
  buildExperienceEvolution,
  buildMemoryProgress,
  buildRiskBadges,
  buildRoleCounts,
  buildTimelineSteps,
  buildToolCalls,
  buildToolStats,
} from "./roleProjectors/shared";

/**
 * 判断事件流是否足以构成一个有效 session。
 *
 * 原先只认 pipeline.started，但 SSE 建连晚于 pipeline.started 发布时（典型场景：
 * 流水线已在运行，用户才打开 Dashboard），前端会永远看到 mock session。
 * 现在扩展为：只要有任何 agent/pipeline 级别的真实事件，就视为 live。
 */
export function hasLiveSession(events: PipelineEvent[]): boolean {
  const LIVE_SIGNALS = new Set([
    "pipeline.started",
    "pipeline.failed",
    "pipeline.stage_changed",
    "pipeline.completed",
    "pipeline.aborted",
    "agent.started",
    "agent.completed",
    "tool.called",
  ]);
  return events.some((e) => LIVE_SIGNALS.has(e.event_type));
}

export function projectAgentSession(events: PipelineEvent[]): AgentSession {
  const snap = aggregate(events);

  return {
    client: snap.client || "—",
    campaign: snap.projectType || "—",
    timeline: "—",
    roleCounts: buildRoleCounts(snap),
    timelineSteps: buildTimelineSteps(snap),
    toolCalls: buildToolCalls(snap),
    account: buildAccountDeck(snap),
    strategy: buildStrategyDeck(snap),
    copywriter: buildCopywriterDeck(snap),
    reviewer: buildReviewerDeck(snap),
    pm: buildPMDeck(snap),
    memoryProgress: buildMemoryProgress(snap),
    auditLog: buildAuditLog(snap),
    toolStats: buildToolStats(snap),
    riskBadges: buildRiskBadges(snap),
    experienceEvolution: buildExperienceEvolution(snap),
    negotiationLog: {
      entries: snap.negotiationEntries,
      totalRounds: snap.negotiationTotalRounds,
      totalMessages: snap.negotiationTotalMessages,
    },
  };
}
