import { create } from "zustand";
import type { ConnectionStatus, PipelineEvent, StageState } from "../types";

interface PipelineStore {
  // Connection
  recordId: string;
  status: ConnectionStatus;
  statusText: string;
  startTime: number | null;

  // Project info
  projectTitle: string;
  projectBrief: string;
  projectStatus: string;

  // Events
  events: PipelineEvent[];

  // Stages
  stages: Record<string, { state: StageState; meta: string }>;
  activeRole: string;

  // Right panel
  toolCounts: Record<string, number>;
  contentTotal: number;
  contentDone: number;
  filledFields: Set<string>;

  // Actions
  setRecordId: (id: string) => void;
  setConnection: (status: ConnectionStatus, text: string) => void;
  setProject: (title: string, brief: string) => void;
  pushEvent: (evt: PipelineEvent) => void;
  setStageState: (role: string, state: StageState) => void;
  setStageMeta: (role: string, meta: string) => void;
  setActiveRole: (role: string) => void;
  addToolCall: (name: string) => void;
  setContentTotal: (n: number) => void;
  incrementContentDone: () => void;
  fillField: (field: string) => void;
  setProjectStatus: (s: string) => void;
  reset: () => void;
}

const INITIAL_STAGES: Record<string, { state: StageState; meta: string }> = {
  account_manager: { state: "waiting", meta: "" },
  strategist: { state: "waiting", meta: "" },
  copywriter: { state: "waiting", meta: "" },
  reviewer: { state: "waiting", meta: "" },
  project_manager: { state: "waiting", meta: "" },
};

export const usePipelineStore = create<PipelineStore>((set) => ({
  recordId: "",
  status: "idle",
  statusText: "等待连接",
  startTime: null,

  projectTitle: "Agent Pipeline",
  projectBrief: "",
  projectStatus: "待处理",

  events: [],

  stages: { ...INITIAL_STAGES },
  activeRole: "",

  toolCounts: {},
  contentTotal: 0,
  contentDone: 0,
  filledFields: new Set(),

  setRecordId: (id) => set({ recordId: id }),
  setConnection: (status, statusText) =>
    set({ status, statusText, startTime: status === "live" ? Date.now() : null }),
  setProject: (projectTitle, projectBrief) => set({ projectTitle, projectBrief }),
  pushEvent: (evt) => set((s) => ({ events: [...s.events, evt] })),
  setStageState: (role, state) =>
    set((s) => ({
      stages: { ...s.stages, [role]: { ...s.stages[role], state } },
    })),
  setStageMeta: (role, meta) =>
    set((s) => ({
      stages: { ...s.stages, [role]: { ...s.stages[role], meta } },
    })),
  setActiveRole: (activeRole) => set({ activeRole }),
  addToolCall: (name) =>
    set((s) => ({
      toolCounts: { ...s.toolCounts, [name]: (s.toolCounts[name] || 0) + 1 },
    })),
  setContentTotal: (n) => set((s) => ({ contentTotal: s.contentTotal + n })),
  incrementContentDone: () => set((s) => ({ contentDone: s.contentDone + 1 })),
  fillField: (field) =>
    set((s) => {
      const next = new Set(s.filledFields);
      next.add(field);
      return { filledFields: next };
    }),
  setProjectStatus: (projectStatus) => set({ projectStatus }),
  reset: () =>
    set({
      events: [],
      stages: { ...INITIAL_STAGES },
      activeRole: "",
      status: "idle",
      statusText: "等待连接",
      startTime: null,
      projectTitle: "Agent Pipeline",
      projectBrief: "",
      projectStatus: "待处理",
      toolCounts: {},
      contentTotal: 0,
      contentDone: 0,
      filledFields: new Set(),
    }),
}));
