export interface PipelineEvent {
  event_type: string;
  timestamp: number;
  record_id: string;
  agent_role: string;
  agent_name: string;
  round: number;
  payload: Record<string, unknown>;
}

/**
 * Copywriter fan-out 场景下 event.payload 可能携带的平台信息。
 *
 * 后端 BaseAgent._publish 在 fan-out 子 agent 所有事件上都会注入这些字段：
 *   - task_filter.platform: 当前子 agent 负责的平台（如 "小红书"）
 *   - platform_patch: 命中了专属 soul 补丁（值 = platform 名）
 *   - fallback_used: true 表示未命中专属补丁，走基础 soul 软兜底
 * platform_patch 和 fallback_used 互斥二选一，非 fan-out 场景两者都不出现。
 *
 * 仅用于 type narrow，不替换原 `payload: Record<string, unknown>`。
 */
export interface CopywriterPlatformMeta {
  task_filter?: { platform?: string };
  platform_patch?: string;
  fallback_used?: boolean;
}

export interface RecordItem {
  record_id: string;
  client_name: string;
  brief: string;
  project_type: string;
  status: string;
}

export type StageState = "waiting" | "active" | "completed";

export interface StageInfo {
  role: string;
  name: string;
  state: StageState;
  meta: string;
}

export type ConnectionStatus = "idle" | "live" | "done" | "error" | "replay";

export interface RunInfo {
  record_id: string;
  project_name: string;
  event_count: number;
  status: string;
  started_at: number;
  completed_at: number;
}
