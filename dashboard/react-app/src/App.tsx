import { useState, useCallback } from "react";
import { TopBar as OldTopBar } from "./components/TopBar";
import { StagesPipeline } from "./components/StagesPipeline";
import { Controls } from "./components/Controls";
import { EventStream } from "./components/EventStream";
import { InfoPanel } from "./components/InfoPanel";
import { RecordPicker } from "./components/RecordPicker";
import { useSSE } from "./hooks/useSSE";
import { useEventProcessor } from "./hooks/useEventProcessor";
import { usePipelineStore } from "./stores/usePipelineStore";
import { ConsoleApp } from "./console/ConsoleApp";
import { useLiveSession } from "./console/useLiveSession";
import type { PipelineEvent } from "./types";

/**
 * 根组件
 *
 * NEW 模式：ConsoleApp 接入实时 session（来自 SSE，fallback 到 mock）
 * OLD 模式：复用现有的 TopBar / StagesPipeline / EventStream / InfoPanel，保留对比 review 能力
 *
 * RecordPicker 由根组件统一持有，NEW/OLD 都可以通过它触发真实 pipeline。
 */
export default function App() {
  const [showPicker, setShowPicker] = useState(false);
  const processEvent = useEventProcessor();
  const store = usePipelineStore();
  const { session, isLive, isWaiting } = useLiveSession();

  useSSE("/stream", processEvent);

  const handleDemo = useCallback(() => {
    fetch("/api/demo/start", { method: "POST" }).catch(() => {});
  }, []);

  const handleReconnect = useCallback(() => {
    store.reset();
    setShowPicker(true);
  }, [store]);

  const handleSelectRecord = useCallback(
    (recordId: string, clientName: string) => {
      setShowPicker(false);
      store.reset();
      store.setProject(clientName || "Agent Pipeline", `record: ${recordId}`);
      store.setRecordId(recordId);
      store.setConnection("live", "运行中");
      fetch(`/api/trigger/${recordId}`, { method: "POST" })
        .then((r) => r.json())
        .then(async (data) => {
          if (data.already_running) {
            // 后端告知：该项目已在运行，前端静默跳转到实时视图
            store.setConnection("live", "已在运行中 · 接入实时流");
            store.setProject(
              clientName || "Agent Pipeline",
              `${recordId} · 运行中`,
            );
            // 已在运行 → SSE 是「从此刻起」流，错过的 pipeline.started/stage_changed 等
            // 老事件需要从磁盘回放进 store，否则 useLiveSession 的 hasLiveSession 永假，
            // 触发 WaitingOverlay 卡死在「等待首个事件到达」。
            try {
              const r = await fetch(`/api/runs/${recordId}`);
              const runData = await r.json();
              if (runData.has_run && Array.isArray(runData.events)) {
                for (const evt of runData.events as PipelineEvent[]) {
                  processEvent(evt);
                }
              }
            } catch {
              /* 历史拉取失败不影响实时流，下游照常依赖 SSE */
            }
          }
        })
        .catch(() => {
          store.setConnection("error", "触发失败");
        });
    },
    [store, processEvent],
  );

  const handleReplay = useCallback(
    (recordId: string, clientName: string) => {
      setShowPicker(false);
      store.reset();
      store.setProject(clientName || "Agent Pipeline", `回放: ${recordId}`);
      store.setRecordId(recordId);
      store.setConnection("replay", "加载回放...");

      fetch(`/api/runs/${recordId}`)
        .then((r) => r.json())
        .then((data) => {
          if (!data.has_run || !data.events || data.events.length === 0) {
            store.setConnection("error", "无执行记录");
            return;
          }
          const events: PipelineEvent[] = data.events;
          for (const evt of events) {
            processEvent(evt);
          }
          store.setConnection("done", `回放完成 (${events.length} 事件)`);
        })
        .catch(() => {
          store.setConnection("error", "加载失败");
        });
    },
    [store, processEvent],
  );

  const oldPanel = (
    <div className="dashboard">
      <OldTopBar />
      <Controls onDemo={handleDemo} onReconnect={handleReconnect} />
      <StagesPipeline />
      <div className="main-content">
        <EventStream />
        <InfoPanel />
      </div>
    </div>
  );

  return (
    <>
      {showPicker && (
        <div
          className="fixed inset-0 flex items-start justify-center overflow-auto"
          style={{ zIndex: 200, background: "rgba(0,0,0,0.72)" }}
          onClick={(e) => {
            if (e.currentTarget === e.target) setShowPicker(false);
          }}
        >
          <div
            className="relative w-full"
            style={{ maxWidth: "960px", marginTop: "48px", padding: "0 16px" }}
          >
            <button
              type="button"
              onClick={() => setShowPicker(false)}
              className="absolute text-text-2 hover:text-accent font-mono text-sm"
              style={{ right: "24px", top: "-28px" }}
            >
              ESC / 关闭 ×
            </button>
            <RecordPicker
              visible={true}
              onSelect={handleSelectRecord}
              onReplay={handleReplay}
            />
          </div>
        </div>
      )}
      <ConsoleApp
        session={session}
        oldPanel={oldPanel}
        isLive={isLive}
        isWaiting={isWaiting}
        onShowPicker={() => setShowPicker(true)}
      />
    </>
  );
}
