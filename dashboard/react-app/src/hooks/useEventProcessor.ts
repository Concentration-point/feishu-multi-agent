import { useCallback } from "react";
import { usePipelineStore } from "../stores/usePipelineStore";
import { useConsoleStore } from "../console/useConsoleStore";
import type { RoleId } from "../console/types";
import type { PipelineEvent } from "../types";

const ROLE_FIELD_MAP: Record<string, string> = {
  account_manager: "brief_analysis",
  strategist: "strategy",
  reviewer: "review_summary",
  project_manager: "delivery",
};

const STATUS_MAP: Record<string, string> = {
  account_manager: "解读中",
  strategist: "策略中",
  copywriter: "撰写中",
  reviewer: "审核中",
  project_manager: "排期中",
};

/** pipeline event 的 agent_role → ConsoleStore 的 RoleId */
const CONSOLE_ROLE_MAP: Record<string, RoleId> = {
  account_manager: "account",
  strategist: "strategy",
  copywriter: "copy",
  reviewer: "review",
  project_manager: "pm",
};

export function useEventProcessor() {
  const store = usePipelineStore();

  return useCallback(
    (evt: PipelineEvent) => {
      // 事件过滤：已选定 recordId 时只接受匹配事件
      // 防止 Mock 演示（recDEMO001）或其他并发项目事件污染当前视图
      const currentRid = usePipelineStore.getState().recordId;
      if (currentRid && evt.record_id && evt.record_id !== currentRid) {
        return;
      }
      store.pushEvent(evt);
      const p = evt.payload;
      const type = evt.event_type;

      switch (type) {
        case "pipeline.started":
          store.setProject(
            (p.project_name as string) || "Agent Pipeline",
            (p.brief as string) || "",
          );
          store.setConnection("live", "运行中");
          // 流水线启动 → 主视图焦点对齐到第一棒（客户经理）
          useConsoleStore.getState().setRole("account");
          break;

        case "pipeline.stage_changed": {
          const role = p.current_role as string;
          const prevRole = p.prev_role as string;
          const currentState = usePipelineStore.getState();
          if (currentState.activeRole && currentState.activeRole !== role) {
            store.setStageState(currentState.activeRole, "completed");
          }
          store.setActiveRole(role);
          store.setStageState(role, "active");
          store.setStageMeta(role, "R1");
          if (prevRole && ROLE_FIELD_MAP[prevRole]) {
            store.fillField(ROLE_FIELD_MAP[prevRole]);
          }
          if (STATUS_MAP[role]) {
            store.setProjectStatus(STATUS_MAP[role]);
          }
          // 主视图焦点跟随流水线当前阶段自动切换
          const consoleRole = CONSOLE_ROLE_MAP[role];
          if (consoleRole) {
            useConsoleStore.getState().setRole(consoleRole);
          }
          break;
        }

        case "pipeline.completed": {
          const currentState = usePipelineStore.getState();
          if (currentState.activeRole) {
            store.setStageState(currentState.activeRole, "completed");
          }
          store.setConnection("done", "已完成");
          store.setProjectStatus((p.status as string) || "已完成");
          break;
        }

        case "tool.called": {
          const toolName = p.tool_name as string;
          store.addToolCall(toolName);
          if (evt.agent_role) {
            store.setStageMeta(evt.agent_role, `R${evt.round}`);
          }
          if (
            toolName === "create_content" ||
            toolName === "batch_create_content"
          ) {
            const count =
              toolName === "batch_create_content"
                ? ((p.arguments as Record<string, unknown>)?.items as unknown[] || []).length || 3
                : 1;
            store.setContentTotal(count);
          }
          break;
        }

        case "tool.returned": {
          const toolName = p.tool_name as string;
          const result = (p.result as string) || "";
          if (toolName === "write_content" && result.includes("成功")) {
            store.incrementContentDone();
          }
          break;
        }

        case "agent.completed": {
          if (evt.agent_role) {
            store.setStageState(evt.agent_role, "completed");
            const currentState = usePipelineStore.getState();
            const startEvt = currentState.events.find(
              (e) =>
                e.event_type === "agent.started" &&
                e.agent_role === evt.agent_role,
            );
            if (startEvt) {
              const dur = (evt.timestamp - startEvt.timestamp).toFixed(1);
              store.setStageMeta(evt.agent_role, `${dur}s`);
            }
          }
          break;
        }

        case "state.updated": {
          const field = p.field as string;
          const value = p.value;
          if (field && value) store.fillField(field);
          if (p.status) store.setProjectStatus(p.status as string);
          break;
        }
      }
    },
    [store],
  );
}
