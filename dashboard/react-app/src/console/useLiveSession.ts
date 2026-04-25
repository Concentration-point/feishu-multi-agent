/**
 * useLiveSession
 *
 * 一等公民：从 usePipelineStore.events 投影出真实 AgentSession。
 * 回退策略：若事件流为空（无 pipeline.started），返回 mock，便于无后端也能演示。
 */

import { useMemo } from "react";
import { usePipelineStore } from "../stores/usePipelineStore";
import { MOCK_SESSION } from "../mocks/agentSession";
import { hasLiveSession, projectAgentSession } from "./selectors/fromEvents";
import type { AgentSession } from "./types";

export interface LiveSessionResult {
  session: AgentSession;
  isLive: boolean;
  /** 有 recordId 但首个真实事件尚未到达（避免回退 mock 造成数据污染） */
  isWaiting: boolean;
  /** 事件数量，用来驱动内部 memo */
  eventCount: number;
}

export function useLiveSession(): LiveSessionResult {
  const events = usePipelineStore((s) => s.events);
  const recordId = usePipelineStore((s) => s.recordId);

  return useMemo(() => {
    const live = hasLiveSession(events);
    // 场景1：已选定 recordId 但首个事件尚未到达 → waiting，不回退 mock
    if (recordId && !live) {
      return {
        session: MOCK_SESSION,
        isLive: false,
        isWaiting: true,
        eventCount: events.length,
      };
    }
    // 场景2：无 recordId 且无事件 → 首次加载展示 mock 演示数据
    if (!live) {
      return {
        session: MOCK_SESSION,
        isLive: false,
        isWaiting: false,
        eventCount: events.length,
      };
    }
    // 场景3：已有真实事件流 → 投影真实 session
    return {
      session: projectAgentSession(events),
      isLive: true,
      isWaiting: false,
      eventCount: events.length,
    };
  }, [events, recordId]);
}
