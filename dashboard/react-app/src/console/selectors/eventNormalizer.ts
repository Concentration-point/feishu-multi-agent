/**
 * eventNormalizer · 历史事件 + 实时 SSE → CanonicalEvent (EventSnapshot)
 *
 * 把 PipelineEvent 流跑一遍状态机，聚合出后续角色投影需要的全量结构化快照。
 * 此文件只关心：事件 → 状态。所有"如何展示给前端"的逻辑都放到 roleProjectors/。
 *
 * 公开的 CanonicalEvent 即 EventSnapshot，role-projectors 共享同一个只读视图。
 */

import type { PipelineEvent, CopywriterPlatformMeta } from "../../types";
import type {
  AuditEntry,
  ExperienceCard,
  ExperiencePhase,
  NegotiationEntry,
  RoleId,
  ToolKind,
} from "../types";
import { asString, clamp, safeJson, shortTime } from "./statusClassifier";

// =============== 角色 / 平台映射 ===============

export const ROLE_MAP: Record<string, RoleId> = {
  account_manager: "account",
  strategist: "strategy",
  copywriter: "copy",
  reviewer: "review",
  project_manager: "pm",
};

export const ROLE_NAME: Record<RoleId, string> = {
  account: "客户经理",
  strategy: "策略师",
  copy: "文案",
  review: "审核",
  pm: "项目经理",
};

export const ROLE_ORDER: RoleId[] = ["account", "strategy", "copy", "review", "pm"];

/**
 * 平台识别关键词规则 —— 按优先级匹配 raw platform 字段中包含的关键词。
 *
 * Agent 的输出不规范（会写 "抖音脚本" "微博话题" 等），所以用关键词包含而非精确匹配；
 * 命中不到的兜到 "other"，避免"抖音脚本"被误判成小红书那种硬伤。
 */
const PLATFORM_RULES: Array<{ match: string[]; id: import("../types").Platform }> = [
  { match: ["公众号", "微信公众号"], id: "gzh" },
  { match: ["小红书", "xhs", "Xiaohongshu"], id: "xhs" },
  { match: ["抖音", "Douyin", "TikTok"], id: "dy" },
  { match: ["微博", "Weibo"], id: "wb" },
  { match: ["B站", "哔哩", "Bilibili"], id: "bili" },
  { match: ["知乎", "Zhihu"], id: "zhihu" },
];

export function normalizePlatform(raw: string): import("../types").Platform {
  const s = (raw || "").trim();
  if (!s) return "other";
  for (const rule of PLATFORM_RULES) {
    for (const kw of rule.match) {
      if (s.includes(kw)) return rule.id;
    }
  }
  return "other";
}

export const STAGE_LABELS: { role: RoleId; label: string }[] = [
  { role: "account", label: "Brief 解读" },
  { role: "strategy", label: "策略中" },
  { role: "copy", label: "撰写中" },
  { role: "review", label: "审核中" },
  { role: "pm", label: "排期中" },
];

export const MEMORY_PROGRESS_DEF: { field: string; label: string }[] = [
  { field: "brief_analysis", label: "Brief 解读" },
  { field: "strategy", label: "策略方案" },
  { field: "draft_content", label: "文案撰写" },
  { field: "review_summary", label: "审核总评" },
  { field: "delivery", label: "交付摘要" },
];

// =============== 工具元信息 ===============

export const TOOL_KIND: Record<string, ToolKind> = {
  read_project: "info",
  write_project: "ok",
  update_status: "warn",
  list_content: "info",
  create_content: "ok",
  batch_create_content: "ok",
  write_content: "ok",
  search_knowledge: "purple",
  read_knowledge: "purple",
  write_wiki: "purple",
  send_message: "warn",
  get_experience: "purple",
  request_human_review: "warn",
};

export const CONTENT_PRODUCING_TOOLS = new Set(["write_content", "batch_create_content"]);

// =============== 辅助 ===============

export function normalizeRole(raw: string): RoleId | null {
  return ROLE_MAP[raw] ?? null;
}

// =============== 类型 ===============

export interface AggregatedToolCall {
  name: string;
  role: RoleId;
  round: number;
  calls: number;
  totalMs: number;
  kind: ToolKind;
  firstRequest?: unknown;
  firstResponse?: unknown;
  stateTransitions: string[];
  invocations: { label: string; ms: number; note?: string }[];
  producesContent: boolean;
}

export interface ContentRowState {
  record_id: string;
  sequence: number;
  title: string;
  platform: string;
  content_type: string;
  key_message: string;
  target_audience: string;
  draft_content?: string;
  word_count?: number;
  status?: string;
  /** 审核 agent 调 write_content(field_name="review_status") 写入的逐条审核结论 */
  review_status?: string;
  /** 审核 agent 调 write_content(field_name="review_feedback") 写入的逐条反馈 */
  review_feedback?: string;
}

export interface EventSnapshot {
  client: string;
  projectType: string;
  brief: string;
  projectStatus: string;
  activeRole: RoleId | null;
  lastCompletedRole: RoleId | null;

  stagesVisited: RoleId[];
  pipelineCompleted: boolean;
  passRate: number;

  toolCallsByKey: Map<string, AggregatedToolCall>;
  auditLog: AuditEntry[];

  /** field_name → 最新 content */
  writtenFields: Map<string, string>;
  /** content_record_id → draft 内容载体 */
  contentRows: Map<string, ContentRowState>;
  /** 策略师创建 drafts 的顺序，用来保持 seq */
  draftOrder: string[];

  searchQueries: string[];
  humanReviews: { role: RoleId; arg: Record<string, unknown> }[];

  toolStatsMap: Map<string, number>;

  /**
   * Copywriter fan-out 场景下按 platform 聚合的子 agent 状态。
   * - key: 原始 platform 字符串（payload.task_filter.platform）
   * - value.patchApplied: 命中专属 soul 补丁
   * - value.toolCalls: 子 agent 累计 tool.called 次数
   * 非 fan-out 项目此 map 始终为空。
   */
  copywriterPlatformSubAgents: Map<string, { patchApplied: boolean; toolCalls: number }>;

  /** 经验进化可视化 */
  experienceCards: ExperienceCard[];
  experienceLoadedRoles: string[];
  experienceSettled: boolean;
  experienceSummary: { total: number; passed: number; merged: number; settled: number };

  /** 协商日志 */
  negotiationEntries: NegotiationEntry[];
  negotiationTotalRounds: number;
  negotiationTotalMessages: number;
}

// =============== 主循环 ===============

/**
 * 把 PipelineEvent[] 折叠成 EventSnapshot。
 *
 * 流程：
 *   - pipeline.* 维护项目元信息、活跃角色、阶段进度
 *   - tool.called / tool.returned 配对计算耗时、聚合 chip、专项捕获产出
 *   - experience.* 升级经验卡片阶段
 *   - negotiation.* 累计协商日志
 */
export function aggregate(events: PipelineEvent[]): EventSnapshot {
  const snap: EventSnapshot = {
    client: "",
    projectType: "",
    brief: "",
    projectStatus: "",
    activeRole: null,
    lastCompletedRole: null,
    stagesVisited: [],
    pipelineCompleted: false,
    passRate: 0,
    toolCallsByKey: new Map(),
    auditLog: [],
    writtenFields: new Map(),
    contentRows: new Map(),
    draftOrder: [],
    searchQueries: [],
    humanReviews: [],
    toolStatsMap: new Map(),
    copywriterPlatformSubAgents: new Map(),
    experienceCards: [],
    experienceLoadedRoles: [],
    experienceSettled: false,
    experienceSummary: { total: 0, passed: 0, merged: 0, settled: 0 },
    negotiationEntries: [],
    negotiationTotalRounds: 0,
    negotiationTotalMessages: 0,
  };

  /** 记录 tool.called 时间戳，用于和 tool.returned 配对计算耗时 */
  const pendingCalls = new Map<
    string,
    { ts: number; role: RoleId; args: unknown; round: number; name: string }
  >();
  /** sequence → pending record_id 占位（等 batch_create_content 返回时替换为真 id） */
  const pendingByOrder: string[] = [];

  for (const evt of events) {
    const p = evt.payload as Record<string, unknown>;
    const t = evt.event_type;
    const role = normalizeRole(evt.agent_role);

    // Copywriter fan-out 元信息聚合：每个 copy 子 agent 事件都可能带
    // task_filter.platform / platform_patch / fallback_used，统一在 switch 前处理。
    // 非 copy 或非 fan-out 事件直接跳过，不污染其他 role 状态。
    if (role === "copy") {
      const meta = p as CopywriterPlatformMeta;
      const platformRaw =
        meta && typeof meta.task_filter === "object" && meta.task_filter !== null
          ? meta.task_filter.platform
          : undefined;
      if (typeof platformRaw === "string" && platformRaw.length > 0) {
        const patchApplied =
          typeof meta.platform_patch === "string" && meta.platform_patch.length > 0;
        const cur = snap.copywriterPlatformSubAgents.get(platformRaw) ?? {
          patchApplied: false,
          toolCalls: 0,
        };
        // patchApplied 只要有一次事件明确命中就 true（platform_patch 出现意味该 agent 加载了补丁）
        if (patchApplied) cur.patchApplied = true;
        if (t === "tool.called") cur.toolCalls += 1;
        snap.copywriterPlatformSubAgents.set(platformRaw, cur);
      }
    }

    switch (t) {
      case "pipeline.started":
        snap.client = asString(p.project_name).trim();
        snap.brief = asString(p.brief);
        break;

      case "pipeline.stage_changed": {
        const cur = normalizeRole(asString(p.current_role));
        const prev = normalizeRole(asString(p.prev_role));
        if (cur) {
          snap.activeRole = cur;
          if (!snap.stagesVisited.includes(cur)) snap.stagesVisited.push(cur);
        }
        if (prev) snap.lastCompletedRole = prev;
        break;
      }

      case "pipeline.completed":
        snap.pipelineCompleted = true;
        snap.projectStatus = asString(p.status) || "已完成";
        snap.passRate = typeof p.pass_rate === "number" ? p.pass_rate : 0;
        snap.activeRole = null;
        break;

      case "agent.started":
        if (!snap.projectType) {
          snap.projectType = asString(p.project_type);
        }
        break;

      case "tool.called": {
        if (!role) break;
        const name = asString(p.tool_name);
        const args = p.arguments ?? {};
        const round = evt.round || 0;
        const keyId = `${role}:${name}:${round}:${evt.timestamp}`;

        pendingCalls.set(keyId, { ts: evt.timestamp, role, args, round, name });

        // 工具统计
        snap.toolStatsMap.set(name, (snap.toolStatsMap.get(name) ?? 0) + 1);

        // 聚合 chip
        const chipKey = `${role}:${name}`;
        const agg = snap.toolCallsByKey.get(chipKey) ?? {
          name,
          role,
          round,
          calls: 0,
          totalMs: 0,
          kind: TOOL_KIND[name] ?? "info",
          firstRequest: args,
          stateTransitions: [],
          invocations: [],
          producesContent: CONTENT_PRODUCING_TOOLS.has(name),
        } satisfies AggregatedToolCall;
        agg.calls++;
        if (agg.firstRequest === undefined) agg.firstRequest = args;
        if (round < agg.round || agg.round === 0) agg.round = round;
        snap.toolCallsByKey.set(chipKey, agg);

        // 专项捕获
        const a = args as Record<string, unknown>;

        if (name === "batch_create_content") {
          const items = (a.items ?? []) as Array<Record<string, unknown>>;
          // 用 pending:N 作占位，结果返回时再替换为真 record_id
          for (const it of items) {
            const rid = `pending:${pendingByOrder.length}`;
            const row: ContentRowState = {
              record_id: rid,
              sequence: Number(it.sequence ?? 0),
              title: asString(it.title),
              platform: asString(it.platform),
              content_type: asString(it.content_type),
              key_message: asString(it.key_message ?? it.key_point ?? ""),
              target_audience: asString(it.target_audience ?? ""),
            };
            snap.contentRows.set(rid, row);
            pendingByOrder.push(rid);
            if (!snap.draftOrder.includes(rid)) snap.draftOrder.push(rid);
          }
        } else if (name === "create_content") {
          const rid = asString(a.record_id) || `pending:${asString(a.sequence)}`;
          const row: ContentRowState = {
            record_id: rid,
            sequence: Number(a.sequence ?? 0),
            title: asString(a.title),
            platform: asString(a.platform),
            content_type: asString(a.content_type),
            key_message: asString(a.key_message ?? ""),
            target_audience: asString(a.target_audience ?? ""),
          };
          snap.contentRows.set(rid, row);
          if (!snap.draftOrder.includes(rid)) snap.draftOrder.push(rid);
        } else if (name === "write_content") {
          const rid = asString(a.content_record_id);
          const field = asString(a.field_name);
          const value = asString(a.value);
          let row = snap.contentRows.get(rid);
          // pending 替换失败时兜底：用真实 record_id 自动建行，避免正文静默丢失
          if (!row && rid && field === "draft_content") {
            row = {
              record_id: rid,
              sequence: snap.draftOrder.length + 1,
              title: `Draft ${snap.draftOrder.length + 1}`,
              platform: "",
              content_type: "",
              key_message: "",
              target_audience: "",
            };
            snap.contentRows.set(rid, row);
            snap.draftOrder.push(rid);
          }
          if (row) {
            if (field === "draft_content") row.draft_content = value;
            else if (field === "word_count") row.word_count = Number(value) || undefined;
            else if (field === "draft_status" || field === "status") row.status = value;
            // 逐条审核结论：审核 agent 写入的最权威 verdict 来源
            else if (field === "review_status" || field === "审核状态") row.review_status = value;
            else if (field === "review_feedback" || field === "审核反馈") row.review_feedback = value;
          }
        } else if (name === "write_project") {
          const field = asString(a.field_name);
          const content = asString(a.content);
          if (field) snap.writtenFields.set(field, content);
        } else if (name === "update_status") {
          snap.projectStatus = asString(a.status) || snap.projectStatus;
          agg.stateTransitions.push(`→ ${asString(a.status)}`);
        } else if (name === "search_knowledge") {
          const q = asString(a.query);
          if (q) {
            snap.searchQueries.push(q);
            agg.invocations.push({ label: clamp(q, 40), ms: 0 });
          }
        } else if (name === "read_knowledge") {
          agg.invocations.push({ label: clamp(asString(a.filepath), 50), ms: 0 });
        } else if (name === "request_human_review") {
          snap.humanReviews.push({ role, arg: a });
        }

        break;
      }

      case "experience.loaded": {
        const roleId = asString(p.role_id);
        if (!snap.experienceLoadedRoles.includes(roleId)) {
          snap.experienceLoadedRoles.push(roleId);
        }
        const roleName = ROLE_NAME[ROLE_MAP[roleId] ?? "account"] ?? roleId;
        const bitableCount = typeof p.bitable_count === "number" ? p.bitable_count : 0;
        // loaded 事件生成一张“加载”卡片（不进漏斗统计）
        snap.experienceCards.push({
          roleId,
          roleName,
          category: asString(p.category) || "未分类",
          lesson: `加载 ${bitableCount} 条 Bitable 经验` + (p.formal_loaded ? " + 正式沉淀区" : ""),
          confidence: 0,
          threshold: 0,
          passed: true,
          phase: "loaded",
          bitableCount,
          formalLoaded: !!p.formal_loaded,
        });
        break;
      }

      case "experience.distilled": {
        const roleId = asString(p.role_id);
        const roleName = ROLE_NAME[ROLE_MAP[roleId] ?? "account"] ?? roleId;
        // 将已有的 loaded 卡片升级为 distilled，或新建
        const existing = snap.experienceCards.find((c) => c.roleId === roleId && c.phase === "loaded");
        if (existing) {
          existing.phase = "distilled";
          existing.lesson = asString(p.lesson) || existing.lesson;
          existing.category = asString(p.category) || existing.category;
        } else {
          snap.experienceCards.push({
            roleId,
            roleName,
            category: asString(p.category) || "未分类",
            lesson: asString(p.lesson),
            confidence: 0,
            threshold: 0,
            passed: true,
            phase: "distilled",
          });
        }
        break;
      }

      case "experience.scored": {
        const roleId = asString(p.role_id);
        const confidence = typeof p.confidence === "number" ? p.confidence : 0;
        const threshold = typeof p.threshold === "number" ? p.threshold : 0.7;
        const passed = !!p.passed;
        const phase: ExperiencePhase = passed ? "scored" : "skipped";
        const factors = p.factors as ExperienceCard["factors"] | undefined;
        const roleName = ROLE_NAME[ROLE_MAP[roleId] ?? "account"] ?? roleId;
        // 升级已有 distilled 卡片，或新建
        const prev = snap.experienceCards.find((c) => c.roleId === roleId && (c.phase === "distilled" || c.phase === "loaded"));
        if (prev) {
          prev.phase = phase;
          prev.confidence = confidence;
          prev.threshold = threshold;
          prev.passed = passed;
          prev.factors = factors;
          if (asString(p.lesson)) prev.lesson = asString(p.lesson);
          if (asString(p.category)) prev.category = asString(p.category);
        } else {
          snap.experienceCards.push({
            roleId,
            roleName,
            category: asString(p.category) || "未分类",
            lesson: asString(p.lesson),
            confidence,
            threshold,
            passed,
            phase,
            factors,
          });
        }
        break;
      }

      case "experience.merging": {
        const roleId = asString(p.role_id);
        const card = snap.experienceCards.find((c) => c.roleId === roleId && c.phase === "scored");
        if (card) card.phase = "merging";
        break;
      }

      case "experience.merged": {
        const roleId = asString(p.role_id);
        const card = snap.experienceCards.find((c) => c.roleId === roleId && c.phase === "merging");
        if (card) {
          card.phase = "merged";
          card.mergedFrom = typeof p.merged_from === "number" ? p.merged_from : 0;
          if (typeof p.new_confidence === "number") card.confidence = p.new_confidence;
        }
        break;
      }

      case "experience.saved": {
        const roleId = asString(p.role_id);
        const card = snap.experienceCards.find(
          (c) => c.roleId === roleId && (c.phase === "scored" || c.phase === "merged"),
        );
        if (card) {
          card.phase = "saved";
          card.bitableSaved = !!p.bitable_saved;
          card.wikiSaved = !!p.wiki_saved;
          if (typeof p.confidence === "number") card.confidence = p.confidence;
        }
        break;
      }

      case "negotiation.started": {
        const upstream = asString(p.upstream_name) || asString(p.upstream_role);
        const downstream = asString(p.downstream_name) || asString(p.downstream_role);
        snap.negotiationEntries.push({
          time: shortTime(evt.timestamp),
          upstream,
          downstream,
          phase: "started",
        });
        snap.auditLog.push({
          time: shortTime(evt.timestamp),
          name: `协商启动: ${downstream} → ${upstream}`,
          durMs: 0,
          kind: "info",
        });
        break;
      }

      case "negotiation.message": {
        const sender = asString(p.sender_name) || asString(p.sender);
        const receiver = asString(p.receiver_name) || asString(p.receiver);
        snap.negotiationEntries.push({
          time: shortTime(evt.timestamp),
          upstream: receiver,
          downstream: sender,
          phase: "message",
          content: clamp(asString(p.content), 120),
          round: typeof p.round === "number" ? p.round : undefined,
        });
        snap.negotiationTotalMessages += 1;
        snap.auditLog.push({
          time: shortTime(evt.timestamp),
          name: `协商消息: ${sender}`,
          durMs: 0,
          kind: "info",
        });
        break;
      }

      case "negotiation.response": {
        const sender = asString(p.sender_name) || asString(p.sender);
        const resolved = !!p.resolved;
        snap.negotiationEntries.push({
          time: shortTime(evt.timestamp),
          upstream: sender,
          downstream: asString(p.receiver_name) || asString(p.receiver),
          phase: "response",
          content: clamp(asString(p.content), 120),
          round: typeof p.round === "number" ? p.round : undefined,
          resolved,
        });
        snap.negotiationTotalMessages += 1;
        snap.auditLog.push({
          time: shortTime(evt.timestamp),
          name: `协商回应: ${sender}` + (resolved ? " ✓共识" : ""),
          durMs: 0,
          kind: resolved ? "ok" : "info",
        });
        break;
      }

      case "negotiation.completed": {
        const rounds = typeof p.rounds === "number" ? p.rounds : 0;
        snap.negotiationTotalRounds += rounds;
        snap.negotiationEntries.push({
          time: shortTime(evt.timestamp),
          upstream: asString(p.upstream_role),
          downstream: asString(p.downstream_role),
          phase: "completed",
          round: rounds,
        });
        snap.auditLog.push({
          time: shortTime(evt.timestamp),
          name: `协商完成: ${rounds} 轮`,
          durMs: 0,
          kind: "ok",
        });
        break;
      }

      case "negotiation.skipped": {
        snap.negotiationEntries.push({
          time: shortTime(evt.timestamp),
          upstream: "",
          downstream: evt.agent_role || "",
          phase: "skipped",
          content: asString(p.reason),
        });
        break;
      }

      case "experience.settle_completed": {
        snap.experienceSettled = true;
        snap.experienceSummary = {
          total: typeof p.total_distilled === "number" ? p.total_distilled : 0,
          passed: typeof p.passed_scoring === "number" ? p.passed_scoring : 0,
          merged: typeof p.merged_groups === "number" ? p.merged_groups : 0,
          settled: typeof p.final_settled === "number" ? p.final_settled : 0,
        };
        break;
      }

      case "tool.returned": {
        if (!role) break;
        const name = asString(p.tool_name);
        const result = asString(p.result);

        // 找到最近的配对（优先同工具名同角色的最晚一次）
        let match:
          | { ts: number; role: RoleId; args: unknown; round: number; name: string }
          | null = null;
        let matchKey = "";
        for (const [k, v] of pendingCalls) {
          if (v.role === role && v.name === name) {
            if (!match || v.ts > match.ts) {
              match = v;
              matchKey = k;
            }
          }
        }
        // 兜底：角色匹配就行（防止工具名 mismatch）
        if (!match) {
          for (const [k, v] of pendingCalls) {
            if (v.role === role) {
              if (!match || v.ts > match.ts) {
                match = v;
                matchKey = k;
              }
            }
          }
        }
        if (match && matchKey) pendingCalls.delete(matchKey);

        const ms = match ? Math.max(0, Math.round((evt.timestamp - match.ts) * 1000)) : 0;

        // batch_create_content 回包：把 pending:N 替换为真正的 record_ids
        if (name === "batch_create_content") {
          const parsed = safeJson(result) as Record<string, unknown> | string;
          if (parsed && typeof parsed === "object") {
            const recordIds = (parsed as Record<string, unknown>).record_ids;
            if (Array.isArray(recordIds) && pendingByOrder.length > 0) {
              // 取最后一批 pending（batch_create 可能被调用多次）
              const batchSize = recordIds.length;
              const startIdx = Math.max(0, pendingByOrder.length - batchSize);
              for (let i = 0; i < batchSize; i++) {
                const pendingRid = pendingByOrder[startIdx + i];
                const realRid = asString(recordIds[i]);
                if (!pendingRid || !realRid) continue;
                const row = snap.contentRows.get(pendingRid);
                if (!row) continue;
                // 用真 id 重建
                const newRow = { ...row, record_id: realRid };
                snap.contentRows.delete(pendingRid);
                snap.contentRows.set(realRid, newRow);
                const orderIdx = snap.draftOrder.indexOf(pendingRid);
                if (orderIdx >= 0) snap.draftOrder[orderIdx] = realRid;
                pendingByOrder[startIdx + i] = realRid;
              }
            }
          }
        }

        // create_content 回包：从结果字符串提取 record_id，替换 pending:${sequence}
        // create_content 工具返回格式："内容行已创建，record_id=recviz..."
        if (name === "create_content" && match) {
          const a = match.args as Record<string, unknown>;
          const seq = asString(a.sequence);
          const pendingRid = `pending:${seq}`;
          const m = result.match(/record_id[=：]\s*([A-Za-z0-9]+)/);
          if (m) {
            const realRid = m[1];
            const row = snap.contentRows.get(pendingRid);
            if (row && realRid && realRid !== pendingRid) {
              const newRow = { ...row, record_id: realRid };
              snap.contentRows.delete(pendingRid);
              snap.contentRows.set(realRid, newRow);
              const orderIdx = snap.draftOrder.indexOf(pendingRid);
              if (orderIdx >= 0) snap.draftOrder[orderIdx] = realRid;
            }
          }
        }

        // 更新聚合 chip
        const chipKey = `${role}:${name}`;
        const agg = snap.toolCallsByKey.get(chipKey);
        if (agg) {
          agg.totalMs += ms;
          if (agg.firstResponse === undefined) agg.firstResponse = safeJson(result);
          if (name === "search_knowledge" && agg.invocations.length) {
            const last = agg.invocations[agg.invocations.length - 1];
            if (last.ms === 0) last.ms = ms;
          }
          if (name === "update_status") {
            agg.stateTransitions.push(asString(result).slice(0, 40));
          }
          if (name === "write_content" && match) {
            const a = match.args as Record<string, unknown>;
            if (asString(a.field_name) === "draft_content") {
              agg.invocations.push({
                label: `seq · ${asString(a.content_record_id).slice(-4)}`,
                ms,
              });
            }
          }
        }

        // 审计日志
        snap.auditLog.push({
          time: shortTime(evt.timestamp),
          name,
          durMs: ms,
          kind: agg?.kind === "ok" ? "ok" : agg?.kind === "warn" ? "warn" : "info",
        });

        // 从结果中补抓 draft 字数 / status
        if (name === "write_content" && match) {
          const a = match.args as Record<string, unknown>;
          const rid = asString(a.content_record_id);
          const row = snap.contentRows.get(rid);
          if (row) {
            const m = result.match(/(\d+)\s*字/);
            if (m && !row.word_count) row.word_count = Number(m[1]);
            if (/成功|已写入/.test(result) && !row.status) row.status = "done";
          }
        }

        break;
      }
    }
  }

  return snap;
}
