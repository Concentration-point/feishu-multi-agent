/**
 * fromEvents · 从真实 SSE 事件流投影出 AgentSession
 *
 * 底层逻辑：
 *   - pipeline.started / stage_changed / completed → 时间线 & 项目元信息
 *   - tool.called + tool.returned 配对 → 耗时、工具统计、审计日志
 *   - batch_create_content.arguments.items → drafts 骨架
 *   - write_content.arguments.value (field_name="draft_content") → drafts 正文（未截断）
 *   - write_project.arguments (field_name="brief_analysis"|"strategy"|"review_summary"|"delivery") → 各角色结构化产出
 *
 * 策略：能投出真值就投真值；拿不到的字段用 '—' 占位，避免和 mock 混淆。
 */

import type {
  AgentSession,
  AuditEntry,
  BriefCard,
  ChannelRow,
  ContentDraft,
  CopywriterDeck,
  ExperienceCard,
  ExperienceEvolution,
  ExperiencePhase,
  Milestone,
  NegotiationEntry,
  PlanBlock,
  PMDeck,
  Platform,
  PlatformSubAgentSummary,
  ReviewItem,
  ReviewVerdict,
  ReviewerDeck,
  RoleId,
  StageHeaderMeta,
  StrategyDeck,
  TimelineStep,
  ToolCall,
  ToolKind,
  ToolStat,
  MemoryProgressItem,
  KnowledgeChip,
  RiskBadge,
} from "../types";
import type { CopywriterPlatformMeta, PipelineEvent } from "../../types";

// =============== 角色 / 平台映射 ===============

const ROLE_MAP: Record<string, RoleId> = {
  account_manager: "account",
  strategist: "strategy",
  copywriter: "copy",
  reviewer: "review",
  project_manager: "pm",
};

const ROLE_NAME: Record<RoleId, string> = {
  account: "客户经理",
  strategy: "策略师",
  copy: "文案",
  review: "审核",
  pm: "项目经理",
};

const ROLE_ORDER: RoleId[] = ["account", "strategy", "copy", "review", "pm"];

/**
 * 平台识别关键词规则 —— 按优先级匹配 raw platform 字段中包含的关键词。
 *
 * Agent 的输出不规范（会写 "抖音脚本" "微博话题" 等），所以用关键词包含而非精确匹配；
 * 命中不到的兜到 "other"，避免"抖音脚本"被误判成小红书那种硬伤。
 */
const PLATFORM_RULES: Array<{ match: string[]; id: Platform }> = [
  { match: ["公众号", "微信公众号"], id: "gzh" },
  { match: ["小红书", "xhs", "Xiaohongshu"], id: "xhs" },
  { match: ["抖音", "Douyin", "TikTok"], id: "dy" },
  { match: ["微博", "Weibo"], id: "wb" },
  { match: ["B站", "哔哩", "Bilibili"], id: "bili" },
  { match: ["知乎", "Zhihu"], id: "zhihu" },
];

function normalizePlatform(raw: string): Platform {
  const s = (raw || "").trim();
  if (!s) return "other";
  for (const rule of PLATFORM_RULES) {
    for (const kw of rule.match) {
      if (s.includes(kw)) return rule.id;
    }
  }
  return "other";
}

const STAGE_LABELS: { role: RoleId; label: string }[] = [
  { role: "account", label: "Brief 解读" },
  { role: "strategy", label: "策略中" },
  { role: "copy", label: "撰写中" },
  { role: "review", label: "审核中" },
  { role: "pm", label: "排期中" },
];

const MEMORY_PROGRESS_DEF: { field: string; label: string }[] = [
  { field: "brief_analysis", label: "Brief 解读" },
  { field: "strategy", label: "策略方案" },
  { field: "draft_content", label: "文案撰写" },
  { field: "review_summary", label: "审核总评" },
  { field: "delivery", label: "交付摘要" },
];

// =============== 工具元信息 ===============

const TOOL_KIND: Record<string, ToolKind> = {
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

const CONTENT_PRODUCING_TOOLS = new Set(["write_content", "batch_create_content"]);

// =============== 辅助 ===============

function normalizeRole(raw: string): RoleId | null {
  return ROLE_MAP[raw] ?? null;
}

function shortTime(timestamp: number): string {
  const d = new Date(timestamp * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function asString(v: unknown): string {
  if (typeof v === "string") return v;
  if (v == null) return "";
  return String(v);
}

function safeJson(v: unknown): unknown {
  if (typeof v !== "string") return v;
  const t = v.trim();
  if ((t.startsWith("{") && t.endsWith("}")) || (t.startsWith("[") && t.endsWith("]"))) {
    try {
      return JSON.parse(t);
    } catch {
      return v;
    }
  }
  return v;
}

function clamp(str: string, n: number): string {
  if (str.length <= n) return str;
  return str.slice(0, n).trimEnd() + "…";
}

/**
 * 清洗从文案 agent 那里拿到的正文——
 * 去掉 <!-- 注释 -->、前导 markdown 标题、多余空白。
 * 用来产生"干净的摘要"不是给 full body 用的。
 */
function cleanForExcerpt(src: string): string {
  if (!src) return "";
  let s = src;
  // 删除 HTML 注释（含多行）
  s = s.replace(/<!--[\s\S]*?-->/g, "");
  // 删除 markdown 头部前的所有 `# 标题` 行
  s = s.replace(/^\s*#{1,6}\s+[^\n]*\n+/gm, "");
  // 合并多余空行
  s = s.replace(/\n{2,}/g, "\n").trim();
  return s;
}

/**
 * 从 review_summary 中取针对某个草稿的点评——
 * 跳过 markdown 标题，抓第一个有意义的段落。
 */
function extractFirstParagraph(text: string): string {
  const lines = text.split("\n");
  for (const raw of lines) {
    const l = raw.trim();
    if (!l) continue;
    if (/^#{1,6}\s/.test(l)) continue; // markdown 标题
    if (/^[-*]\s/.test(l) || /^\d+\.\s/.test(l)) {
      // 列表项首字符后取内容
      return l.replace(/^[-*]\s+/, "").replace(/^\d+\.\s+/, "");
    }
    return l;
  }
  return "";
}

function parseMarkdownBlocks(md: string, sectionNames: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  if (!md) return out;
  for (const name of sectionNames) {
    const re = new RegExp(
      `##\\s*(?:\\d+\\.?\\s*)?${name.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&")}\\s*\\n([\\s\\S]*?)(?=\\n##\\s|$)`,
    );
    const m = md.match(re);
    if (m) out[name] = m[1].trim();
  }
  return out;
}

// =============== 事件聚合 ===============

interface AggregatedToolCall {
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

interface EventSnapshot {
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

interface ContentRowState {
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

function aggregate(events: PipelineEvent[]): EventSnapshot {
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
          const row = snap.contentRows.get(rid);
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
        } else if (name === "write_content") {
          // already handled above, duplicate guard
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

// =============== 投影 ===============

function buildTimelineSteps(snap: EventSnapshot): TimelineStep[] {
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

function buildRoleCounts(snap: EventSnapshot): Record<RoleId, number> {
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

function buildToolCalls(snap: EventSnapshot): ToolCall[] {
  const out: ToolCall[] = [];
  for (const [key, agg] of snap.toolCallsByKey) {
    const transition =
      agg.stateTransitions.length > 0 ? agg.stateTransitions[agg.stateTransitions.length - 1] : undefined;
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

function buildAccountDeck(snap: EventSnapshot): BriefCard {
  const ba = snap.writtenFields.get("brief_analysis") ?? "";
  const secs = parseMarkdownBlocks(ba, [
    "项目摘要",
    "目标理解",
    "受众与场景理解",
    "关键信息与约束",
    "准入结论",
  ]);

  const blocks: PlanBlock[] = [
    { label: "Client", value: snap.client || "—" },
    { label: "Campaign", value: snap.projectType || "—" },
    { label: "Brief", value: clamp(snap.brief || "—", 160) },
    { label: "Status", value: snap.projectStatus || "—" },
  ];
  if (secs["目标理解"]) blocks.push({ label: "Target", value: secs["目标理解"] });
  if (secs["受众与场景理解"]) blocks.push({ label: "Audience", value: secs["受众与场景理解"] });
  if (secs["准入结论"]) blocks.push({ label: "Gate", value: secs["准入结论"] });

  const toolCount = Array.from(snap.toolCallsByKey.values())
    .filter((a) => a.role === "account")
    .reduce((s, a) => s + a.calls, 0);

  return {
    header: {
      title: "客户经理 · Brief 解读",
      subtitle: "ACCOUNT · R1",
      meta: accountMeta(snap, toolCount),
    },
    kicker: `CLIENT BRIEF · ${snap.client || "—"}`,
    title: snap.projectType || "—",
    tagline: clamp(snap.brief || "—", 260),
    blocks,
  };
}

function accountMeta(snap: EventSnapshot, toolCount: number): StageHeaderMeta[] {
  return [
    { label: "产出", value: snap.writtenFields.has("brief_analysis") ? "已交付" : "进行中" },
    { label: "工具", value: `${toolCount} 次` },
    { label: "状态", value: snap.projectStatus || "—" },
  ];
}

function buildStrategyDeck(snap: EventSnapshot): StrategyDeck {
  const strat = snap.writtenFields.get("strategy") ?? "";
  const secs = parseMarkdownBlocks(strat, [
    "目标受众",
    "核心洞察",
    "品牌调性",
    "核心策略",
    "KPI",
    "转化路径",
    "内容矩阵",
  ]);

  const blocks: PlanBlock[] = [];
  if (secs["目标受众"]) blocks.push({ label: "Target Audience", value: secs["目标受众"] });
  if (secs["核心洞察"]) blocks.push({ label: "Core Insight", value: secs["核心洞察"] });
  if (secs["品牌调性"]) blocks.push({ label: "Brand Tone", value: secs["品牌调性"] });
  if (secs["核心策略"]) blocks.push({ label: "Core Strategy", value: secs["核心策略"] });
  if (secs["KPI"]) blocks.push({ label: "KPI Funnel", value: secs["KPI"] });
  if (blocks.length === 0 && strat) {
    blocks.push({ label: "Strategy Digest", value: strat });
  }
  if (blocks.length === 0) {
    blocks.push({ label: "Strategy", value: "— 策略尚未生成" });
  }

  // 渠道分工：从 drafts 反推
  const channelMap = new Map<string, { count: number; roleDesc: string }>();
  for (const rid of snap.draftOrder) {
    const row = snap.contentRows.get(rid);
    if (!row) continue;
    const key = row.platform || "其他";
    const cur = channelMap.get(key);
    const roleDesc = row.content_type || "";
    channelMap.set(key, {
      count: (cur?.count ?? 0) + 1,
      roleDesc: cur?.roleDesc ? cur.roleDesc : roleDesc,
    });
  }
  const channels: ChannelRow[] = Array.from(channelMap, ([name, v]) => ({
    name,
    role: v.roleDesc || "—",
    count: v.count,
  }));

  const toolCount = countByRole(snap, "strategy");
  const kickerParts = ["CAMPAIGN STRATEGY"];
  if (snap.projectType) kickerParts.push(snap.projectType);

  const firstLine = strat.split("\n").find((l) => l.trim()) ?? "";
  const cleanFirst = firstLine.replace(/^#+\s*/, "").trim();

  return {
    header: {
      title: "策略方案 · 内容总纲",
      subtitle: "STRATEGIST · R1",
      meta: [
        { label: "渠道", value: String(channels.length || "—") },
        { label: "篇目", value: String(snap.draftOrder.length || "—") },
        { label: "工具", value: `${toolCount} 次` },
      ],
    },
    kicker: kickerParts.join(" · "),
    title: clamp(cleanFirst || "围绕项目节点制定内容策略", 80),
    tagline: clamp(strat.split("\n").filter((l) => l.trim())[1] ?? snap.brief ?? "—", 220),
    blocks,
    channels,
  };
}

function buildCopywriterDeck(snap: EventSnapshot): CopywriterDeck {
  const drafts: ContentDraft[] = [];
  let idx = 0;
  for (const rid of snap.draftOrder) {
    const row = snap.contentRows.get(rid);
    if (!row) continue;
    idx++;
    const platform = normalizePlatform(row.platform);
    const full = row.draft_content ?? "";
    const cleanedExcerpt = cleanForExcerpt(full);
    // 当 draft_content 未回传（文案 Agent 未调 write_content）时，fullBody 回退
    // 展示策略师下发的骨架信息，避免 drawer 与预览卡片出现"预览有内容/详情空"的断裂
    const skeletonFallback = full
      ? null
      : [
          row.key_message ? `**核心卖点**\n\n${row.key_message}` : null,
          row.target_audience ? `**目标人群**\n\n${row.target_audience}` : null,
          row.content_type ? `**内容类型**\n\n${row.content_type}` : null,
        ]
          .filter(Boolean)
          .join("\n\n");
    const fullBody = full
      ? full
      : skeletonFallback
        ? `${skeletonFallback}\n\n---\n\n> ⚠️ 完整正文尚未回传（文案 Agent 未调用 write_content("draft_content")），当前仅展示策略师下发的骨架信息。`
        : "— 尚未撰写";
    drafts.push({
      id: rid,
      seq: row.sequence || idx,
      platform,
      contentType: row.content_type || "—",
      title: row.title || `Draft ${idx}`,
      excerpt: clamp(cleanedExcerpt || row.key_message || "—", 160),
      fullBody,
      wordCount: row.word_count ?? full.length,
      status: full ? "done" : "draft",
    });
  }

  const knowledge: KnowledgeChip[] = [];
  const seen = new Set<string>();
  for (const q of snap.searchQueries.slice(-8).reverse()) {
    if (seen.has(q)) continue;
    seen.add(q);
    knowledge.push({ label: clamp(q, 40), kind: "purple" });
    if (knowledge.length >= 5) break;
  }

  const totalWords = drafts.reduce((s, d) => s + (d.wordCount || 0), 0);
  const toolCount = countByRole(snap, "copy");

  // fan-out 子 agent 摘要：非空才下发，历史项目不出现该字段
  const platformSubAgents: PlatformSubAgentSummary[] = Array.from(
    snap.copywriterPlatformSubAgents,
    ([platform, v]) => ({
      platform,
      patchApplied: v.patchApplied,
      toolCalls: v.toolCalls,
    }),
  ).sort((a, b) => a.platform.localeCompare(b.platform));

  const deck: CopywriterDeck = {
    header: {
      title: `文案 · ${drafts.length} 篇产出`,
      subtitle: "COPYWRITER · R2",
      meta: [
        { label: "产出", value: `${drafts.length} 篇` },
        { label: "字数", value: totalWords.toLocaleString() },
        { label: "工具", value: `${toolCount} 次` },
      ],
    },
    drafts,
    knowledge,
  };
  if (platformSubAgents.length > 0) {
    deck.platformSubAgents = platformSubAgents;
  }
  return deck;
}

function buildReviewerDeck(snap: EventSnapshot): ReviewerDeck {
  const items: ReviewItem[] = [];
  const review = snap.writtenFields.get("review_summary") ?? "";
  // 先尝试 per-draft review status：很多文案 row 不一定带 review status，
  // 从 human_review 参数和 review_summary 的 markdown 里提取大致结论
  for (const rid of snap.draftOrder) {
    const row = snap.contentRows.get(rid);
    if (!row) continue;
    const verdict = detectVerdictForDraft(row, review);
    const action: ReviewItem["action"] =
      verdict === "approve" ? "APPROVE" : verdict === "revise" ? "REVISE" : "REJECT";
    items.push({
      id: rid,
      draftSeq: row.sequence,
      verdict,
      platform: normalizePlatform(row.platform),
      title: `${row.platform}｜${row.title}`,
      note: extractNoteForDraft(row, review),
      action,
    });
  }
  const approved = items.filter((i) => i.verdict === "approve").length;
  const revise = items.filter((i) => i.verdict === "revise").length;
  const reject = items.filter((i) => i.verdict === "reject").length;
  return {
    header: {
      title: `审核报告 · ${items.length} 篇产出`,
      subtitle: "REVIEWER · R3",
      meta: [
        { label: "通过", value: String(approved) },
        { label: "待修订", value: String(revise) },
        { label: "问题", value: String(reject) },
      ],
    },
    items,
  };
}

/**
 * 优先级：
 *   1. row.review_status（审核 agent 写到内容行的最权威字段）
 *   2. review_summary 中能定位到本草稿标题的片段做关键词匹配
 *   3. 都拿不到时，根据 draft 状态降级（有正文 → approve, 没正文 → revise）
 *
 * 关键陷阱：审核 agent 的 review_summary 开头通常是
 *   "本轮审核概况 通过条数：5 驳回条数：0 ..."
 * 旧版正则 `/驳回/` 直接命中"驳回条数"导致全 reject。新版只匹配判词，
 * 不匹配统计句（"X条数"、"X率"）。
 */
function detectVerdictForDraft(row: ContentRowState, review: string): ReviewVerdict {
  // 1. 优先用每条内容自己的 review_status（审核 agent 写到内容行的字段）
  const rowStatus = (row.review_status || "").trim();
  if (rowStatus) {
    if (/^通过$|^approved?$|^pass$/i.test(rowStatus)) return "approve";
    if (/需修改|需完善|需修订|revise/i.test(rowStatus)) return "revise";
    if (/驳回|退回|reject/i.test(rowStatus)) return "reject";
    // 未识别但有值 — 通常是新枚举或自然语言，按 draft 状态降级
  }

  // 2. fallback：在 review_summary 里找针对本草稿的段落
  if (review) {
    const titleKey = row.title.slice(0, 10);
    const seq = `seq ${row.sequence}|第${row.sequence}`;
    const slice = sliceAroundKeyOrNull(review, [
      row.title,
      titleKey,
      `seq_${row.sequence}`,
      seq,
    ]);
    if (slice) {
      // 只匹配判词，避免命中"驳回条数：X"、"通过率"这种统计性表述
      if (/驳回(?!条数)|退回|不通过(?!率)|不达标|red\s*flag/i.test(slice)) return "reject";
      if (/需修改|需完善|需修订|建议(?:调整|补充|修订)/i.test(slice)) return "revise";
      if (/通过(?!率|条数)|approved?/i.test(slice)) return "approve";
    }
  }

  // 3. 降级：有正文视为通过（避免没真实审核结果时硬判驳回）
  return row.draft_content ? "approve" : "revise";
}

function extractNoteForDraft(row: ContentRowState, review: string): string {
  // 优先用每条内容自己的 review_feedback
  if (row.review_feedback) return clamp(row.review_feedback, 130);
  if (!review) return row.draft_content ? "已完成，待审核。" : "尚未撰写。";
  const slice = sliceAroundKeyOrNull(review, [row.title, row.title.slice(0, 10)]);
  if (!slice) return row.draft_content ? "已完成，待审核。" : "尚未撰写。";
  const firstMeaningful = extractFirstParagraph(slice);
  return clamp(firstMeaningful || "已产出，审核意见待生成。", 130);
}

/**
 * 在文本里找到第一个 key 的位置，截取后续 280 字符。
 * 找不到任何 key 时返回 null（不再像旧版 fallback 到 text.slice(0, 200)，
 * 那会让所有草稿都吃到 review_summary 开头的统计句导致误判）。
 */
function sliceAroundKeyOrNull(text: string, keys: string[]): string | null {
  for (const k of keys) {
    if (!k) continue;
    const i = text.indexOf(k);
    if (i >= 0) return text.slice(i, i + 280);
  }
  return null;
}

function buildPMDeck(snap: EventSnapshot): PMDeck {
  const milestones: Milestone[] = STAGE_LABELS.map(({ role, label }, i) => {
    const isActive = snap.activeRole === role && !snap.pipelineCompleted;
    const done =
      snap.pipelineCompleted ||
      (snap.activeRole
        ? ROLE_ORDER.indexOf(role) < ROLE_ORDER.indexOf(snap.activeRole)
        : snap.stagesVisited.includes(role));
    return {
      id: `m${i + 1}`,
      title: `M${i + 1} · ${ROLE_NAME[role]}`,
      summary: isActive
        ? `当前阶段：${label}`
        : done
          ? `${label} · 已完成`
          : `${label} · 待开始`,
      done: done && !isActive,
    };
  });

  return {
    header: {
      title: "项目进度",
      subtitle: "PROJECT MANAGER · R4",
      meta: [
        {
          label: "完成",
          value: `${milestones.filter((m) => m.done).length} / ${milestones.length}`,
        },
        {
          label: "通过率",
          value: snap.passRate > 0 ? `${Math.round(snap.passRate * 100)}%` : "—",
        },
        { label: "状态", value: snap.pipelineCompleted ? "已完成" : snap.projectStatus || "进行中" },
      ],
    },
    milestones,
  };
}

function buildMemoryProgress(snap: EventSnapshot): MemoryProgressItem[] {
  const activeIdx = snap.activeRole ? ROLE_ORDER.indexOf(snap.activeRole) : -1;
  return MEMORY_PROGRESS_DEF.map((def, i) => {
    const written = snap.writtenFields.has(def.field) || def.field === "draft_content"
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

function buildAuditLog(snap: EventSnapshot): AuditEntry[] {
  return snap.auditLog.slice(-12).reverse();
}

function buildToolStats(snap: EventSnapshot): ToolStat[] {
  return Array.from(snap.toolStatsMap, ([name, count]) => ({ name, count })).sort(
    (a, b) => b.count - a.count,
  );
}

function buildRiskBadges(snap: EventSnapshot): RiskBadge[] {
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

  const wikiWrites = Array.from(snap.toolCallsByKey.values()).filter((t) => t.name === "write_wiki").reduce((s, t) => s + t.calls, 0);
  if (wikiWrites > 0) {
    badges.push({ label: `知识沉淀 ${wikiWrites} 次`, kind: "ok" });
  }

  return badges;
}

function countByRole(snap: EventSnapshot, role: RoleId): number {
  let n = 0;
  for (const agg of snap.toolCallsByKey.values()) {
    if (agg.role === role) n += agg.calls;
  }
  return n;
}

function buildExperienceEvolution(snap: EventSnapshot): ExperienceEvolution {
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

// =============== 公开接口 ===============

/**
 * 判断事件流是否足以构成一个有效 session。
 * 至少要有 pipeline.started，否则前端认为没 live 数据，回退到 mock。
 */
export function hasLiveSession(events: PipelineEvent[]): boolean {
  return events.some((e) => e.event_type === "pipeline.started");
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
