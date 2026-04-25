/**
 * useConsoleStore · 新面板的 UI 状态
 *
 * 仅管 UI 状态：当前角色、抽屉开关、抽屉绑定的 toolCall ID、NEW/OLD 模式。
 * 业务数据来自 mock/SSE，**不存** zustand，避免和现有 usePipelineStore 互相污染。
 */

import { create } from "zustand";
import type { RoleId, ViewMode } from "./types";

interface ConsoleStore {
  activeRole: RoleId;
  viewMode: ViewMode;
  drawerOpen: boolean;
  /** 绑定的 toolCall.id 或 "draft:seq_N" 或 "notes" */
  drawerKey: string | null;

  setRole: (role: RoleId) => void;
  setViewMode: (mode: ViewMode) => void;
  openDrawer: (key: string) => void;
  closeDrawer: () => void;
}

export const useConsoleStore = create<ConsoleStore>((set) => ({
  // 默认焦点：客户经理（流水线第一棒），避免打开就停在"文案"上造成阶段感错位
  activeRole: "account",
  viewMode: "new",
  drawerOpen: false,
  drawerKey: null,

  setRole: (activeRole) => set({ activeRole }),
  setViewMode: (viewMode) => set({ viewMode }),
  openDrawer: (key) => set({ drawerOpen: true, drawerKey: key }),
  closeDrawer: () => set({ drawerOpen: false }),
}));
