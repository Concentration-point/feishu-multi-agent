/**
 * Agent Console · 一等公民数据模型
 *
 * 顶层语义：AgentSession 是整个面板的唯一数据源。
 * 所有角色视图从 session 中切片读取自己关心的字段；工具调用和审计日志是次要信息。
 */

export type RoleId = "account" | "strategy" | "copy" | "review" | "pm";
export type Platform = "xhs" | "gzh" | "dy" | "wb" | "bili" | "zhihu" | "other";
export type DraftStatus = "done" | "draft" | "review";
export type ReviewVerdict = "approve" | "revise" | "reject";
export type ToolKind = "info" | "warn" | "ok" | "purple";
export type AuditKind = "info" | "ok" | "warn";
export type MemoryState = "done" | "current" | "pending";
export type ViewMode = "new" | "old";

/**
 * ToolCall · 次要信息
 *
 * 面板里用 chip 形态渲染；点击展开抽屉才看 request/response。
 * producesContent=true 的工具（如 write_content）chip 禁止渲染正文——正文只在主视图出现一次。
 */
export interface ToolCall {
  id: string;
  name: string;
  role: RoleId;
  round: number;
  calls: number;
  avgMs: number;
  kind: ToolKind;
  producesContent?: boolean;
  /** 状态转移专用描述，如 "策略中 → 撰写中" */
  stateTransition?: string;
  request?: unknown;
  response?: unknown;
  /** 多次调用时的分批展示，每条一行 */
  invocations?: { label: string; ms: number; note?: string }[];
}

/** 文案角色的一等公民 */
export interface ContentDraft {
  /** 唯一键（飞书 record_id 或 pending:N 占位），用于 React key + drawer 路由 */
  id: string;
  seq: number;
  platform: Platform;
  contentType: string;
  title: string;
  excerpt: string;
  fullBody: string;
  wordCount: number;
  status: DraftStatus;
}

/** 审核角色的一等公民 */
export interface ReviewItem {
  /** 唯一键（文案 row 的 record_id），避免多条 draftSeq 相同时 React key 冲突 */
  id: string;
  draftSeq: number;
  verdict: ReviewVerdict;
  platform: Platform;
  title: string;
  note: string;
  action: "APPROVE" | "REVISE" | "REJECT";
}

/** PM 角色的一等公民 */
export interface Milestone {
  id: string;
  title: string;
  summary: string;
  done: boolean;
}

export interface TimelineStep {
  label: string;
  done: boolean;
  current: boolean;
}

export interface PlanBlock {
  label: string;
  value: string;
  /** value 中可能包含高亮片段，用 `<strong>text</strong>` 即由组件转换 */
  highlights?: string[];
}

export interface ChannelRow {
  name: string;
  role: string;
  count: number;
}

export interface AuditEntry {
  time: string;
  name: string;
  durMs: number;
  kind: AuditKind;
}

export interface ToolStat {
  name: string;
  count: number;
}

export interface MemoryProgressItem {
  label: string;
  state: MemoryState;
}

export interface RiskBadge {
  label: string;
  kind: "warn" | "error" | "ok";
}

/** 经验进化可视化 */
export type ExperiencePhase = "loaded" | "distilled" | "scored" | "merging" | "merged" | "saved" | "skipped";

export interface ExperienceCard {
  roleId: string;
  roleName: string;
  category: string;
  lesson: string;
  confidence: number;
  threshold: number;
  passed: boolean;
  phase: ExperiencePhase;
  factors?: {
    pass_rate: number | null;
    task_completed: boolean;
    no_rework: boolean;
    knowledge_cited: boolean;
  };
  mergedFrom?: number;
  bitableSaved?: boolean;
  wikiSaved?: boolean;
  /** loaded 阶段专用：从 Bitable 加载的经验条数 */
  bitableCount?: number;
  /** loaded 阶段专用：是否加载了正式沉淀经验 */
  formalLoaded?: boolean;
}

export interface ExperienceEvolution {
  cards: ExperienceCard[];
  /** loaded 阶段的角色 ID 列表 */
  loadedRoles: string[];
  totalDistilled: number;
  passedScoring: number;
  mergedGroups: number;
  finalSettled: number;
  settled: boolean;
}

export interface KnowledgeChip {
  label: string;
  kind: ToolKind;
}

/** 协商日志条目 */
export interface NegotiationEntry {
  time: string;
  upstream: string;
  downstream: string;
  /** "started" | "message" | "response" | "completed" | "skipped" */
  phase: string;
  content?: string;
  round?: number;
  resolved?: boolean;
}

export interface NegotiationLog {
  entries: NegotiationEntry[];
  totalRounds: number;
  totalMessages: number;
}

export interface StageHeaderMeta {
  label: string;
  value: string;
}

export interface StageSectionHeader {
  title: string;
  subtitle: string;
  meta: StageHeaderMeta[];
}

/** 客户经理角色的一等公民 */
export interface BriefCard {
  header: StageSectionHeader;
  kicker: string;
  title: string;
  tagline: string;
  blocks: PlanBlock[];
}

/** 策略师角色的一等公民 */
export interface StrategyDeck {
  header: StageSectionHeader;
  kicker: string;
  title: string;
  tagline: string;
  blocks: PlanBlock[];
  channels: ChannelRow[];
}

/**
 * Copywriter fan-out 场景下每个平台子 agent 的元信息摘要。
 * 历史（非 fan-out）项目此字段不会出现，视图层用 optional 兜底。
 */
export interface PlatformSubAgentSummary {
  /** 平台原始名称（后端 payload.task_filter.platform），如 "小红书" */
  platform: string;
  /** true=命中专属 soul 补丁；false=未命中走基础 soul 软兜底 */
  patchApplied: boolean;
  /** 该子 agent 调用工具的累计次数（tool.called 计数） */
  toolCalls: number;
}

export interface CopywriterDeck {
  header: StageSectionHeader;
  drafts: ContentDraft[];
  knowledge: KnowledgeChip[];
  /** Copywriter fan-out 场景下的平台子 agent 摘要；历史项目为空时不下发 */
  platformSubAgents?: PlatformSubAgentSummary[];
}

export interface ReviewerDeck {
  header: StageSectionHeader;
  items: ReviewItem[];
}

export interface PMDeck {
  header: StageSectionHeader;
  milestones: Milestone[];
}

/** 顶层 session */
export interface AgentSession {
  client: string;
  campaign: string;
  timeline: string;

  /** TopBar tabs 上的计数 */
  roleCounts: Record<RoleId, number>;

  /** 所有角色共用的时间线 */
  timelineSteps: TimelineStep[];

  /** 所有工具调用——由各角色视图按 role 过滤 */
  toolCalls: ToolCall[];

  /** 各角色主视图切片 */
  account: BriefCard;
  strategy: StrategyDeck;
  copywriter: CopywriterDeck;
  reviewer: ReviewerDeck;
  pm: PMDeck;

  /** 右侧栏 */
  memoryProgress: MemoryProgressItem[];
  auditLog: AuditEntry[];
  toolStats: ToolStat[];
  riskBadges: RiskBadge[];

  /** 经验进化可视化 */
  experienceEvolution: ExperienceEvolution;

  /** 协商日志 */
  negotiationLog: NegotiationLog;
}
