/**
 * ConsoleApp · 新面板根组件
 *
 * 布局：48px topbar + (stage | 340px sidebar)
 * 一等公民：当前角色的主视图（由 useConsoleStore.activeRole 决定）
 * 次要信息：所有工具调用都被收敛到 chip 行 + sidebar 审计日志 + 右侧抽屉
 */

import { useState, useEffect, useCallback, type ReactElement, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";
import { ToolDrawer } from "./components/ToolDrawer";
import { AccountView } from "./views/AccountView";
import { StrategyView } from "./views/StrategyView";
import { CopywriterView } from "./views/CopywriterView";
import { ReviewerView } from "./views/ReviewerView";
import { PMView } from "./views/PMView";
import { DAGView } from "./views/DAGView";
import { ToolHealthView } from "./views/ToolHealthView";
import { CostBanner } from "./components/CostBanner";
import { useConsoleStore } from "./useConsoleStore";
import { usePipelineStore } from "../stores/usePipelineStore";
import type { AgentSession, RoleId } from "./types";

interface ConsoleAppProps {
  session: AgentSession;
  /** OLD 模式下交给外部渲染的老面板节点 */
  oldPanel?: ReactNode;
  /** 来自真实 SSE 流就 true，mock 数据就 false */
  isLive?: boolean;
  /** 已选 recordId 但首个事件未到达 → 显示等待遮罩，避免 mock 污染 */
  isWaiting?: boolean;
  /** 触发选项目弹窗（RecordPicker） */
  onShowPicker?: () => void;
}

const VIEW_MAP: Record<RoleId, (props: { session: AgentSession }) => ReactElement> = {
  account: AccountView,
  strategy: StrategyView,
  copy: CopywriterView,
  review: ReviewerView,
  pm: PMView,
};

export function ConsoleApp({ session, oldPanel, isLive, isWaiting, onShowPicker }: ConsoleAppProps) {
  const activeRole  = useConsoleStore((s) => s.activeRole);
  const viewMode    = useConsoleStore((s) => s.viewMode);
  const graphMode   = useConsoleStore((s) => s.graphMode);
  const healthMode  = useConsoleStore((s) => s.healthMode);
  const View = VIEW_MAP[activeRole];

  return (
    <div
      className="relative"
      style={{
        zIndex: 1,
        height: "100vh",
        width: "100vw",
        display: "grid",
        gridTemplateRows: "56px 1fr",
        overflow: "hidden",
      }}
    >
      <TopBar session={session} isLive={isLive} onShowPicker={onShowPicker} />
      {isWaiting && <WaitingOverlay onRetry={onShowPicker} />}

      {viewMode === "new" ? (
        healthMode ? (
          /* 工具健康面板：全屏，不带 Sidebar */
          <div style={{ position: "relative", overflow: "hidden", minHeight: 0 }}>
            <ToolHealthView />
          </div>
        ) : graphMode ? (
          /* DAG 全屏画布：token 成本条 + DAG 画布，铺满内容区 */
          <div style={{ display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0 }}>
            <CostBanner />
            <div style={{ flex: 1, position: "relative", overflow: "hidden", minHeight: 0 }}>
              <DAGView session={session} />
            </div>
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1fr) 340px",
              overflow: "hidden",
              minHeight: 0,
            }}
          >
            <main
              className="scroll-thin"
              style={{
                overflowY: "auto",
                padding: "28px 36px 80px",
                minWidth: 0,
              }}
            >
              <div style={{ maxWidth: "1080px", margin: "0 auto" }}>
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeRole}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.18 }}
                  >
                    <View session={session} />
                  </motion.div>
                </AnimatePresence>
              </div>
            </main>
            <Sidebar session={session} />
          </div>
        )
      ) : (
        <div style={{ overflow: "hidden", minHeight: 0 }}>{oldPanel}</div>
      )}

      <ToolDrawer session={session} />
    </div>
  );
}

const WAIT_TIMEOUT_MS = 30_000;

function WaitingOverlay({ onRetry }: { onRetry?: () => void }) {
  const [timedOut, setTimedOut] = useState(false);

  // 每次 WaitingOverlay 挂载时重置计时器（recordId 变化会触发 remount）
  useEffect(() => {
    setTimedOut(false);
    const timer = setTimeout(() => setTimedOut(true), WAIT_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, []);

  const handleRetry = useCallback(() => {
    // 清空 store 状态，让 onShowPicker 重新选择
    usePipelineStore.getState().reset();
    onRetry?.();
  }, [onRetry]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      style={{
        position: "absolute",
        top: "56px",
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(10, 12, 16, 0.78)",
        backdropFilter: "blur(4px)",
        zIndex: 150,
        display: "grid",
        placeItems: "center",
        pointerEvents: "auto",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "18px",
          padding: "36px 52px",
          borderRadius: "16px",
          background: "rgba(24, 28, 36, 0.92)",
          border: timedOut
            ? "1px solid rgba(239, 68, 68, 0.4)"
            : "1px solid rgba(110, 231, 183, 0.25)",
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          fontFamily: "var(--font-sans)",
          color: "var(--color-text-1)",
          minWidth: "320px",
        }}
      >
        {timedOut ? (
          /* ── 超时状态：错误提示 + 重试 ── */
          <>
            <div
              style={{
                width: "34px",
                height: "34px",
                borderRadius: "50%",
                background: "rgba(239, 68, 68, 0.15)",
                display: "grid",
                placeItems: "center",
                fontSize: "18px",
                color: "rgba(239, 68, 68, 0.9)",
              }}
            >
              !
            </div>
            <div style={{ textAlign: "center" }}>
              <div
                style={{
                  fontSize: "15px",
                  fontWeight: 500,
                  letterSpacing: "0.02em",
                  marginBottom: "6px",
                  color: "rgba(239, 68, 68, 0.9)",
                }}
              >
                等待超时
              </div>
              <div
                className="font-mono"
                style={{
                  fontSize: "11.5px",
                  color: "var(--color-text-3)",
                  letterSpacing: "0.05em",
                  marginBottom: "16px",
                }}
              >
                流水线可能启动失败，请检查后端日志
              </div>
              <button
                type="button"
                onClick={handleRetry}
                style={{
                  padding: "8px 24px",
                  borderRadius: "8px",
                  border: "1px solid rgba(110, 231, 183, 0.4)",
                  background: "rgba(110, 231, 183, 0.1)",
                  color: "rgba(110, 231, 183, 0.9)",
                  fontSize: "13px",
                  fontWeight: 500,
                  cursor: "pointer",
                  letterSpacing: "0.03em",
                }}
              >
                重试
              </button>
            </div>
          </>
        ) : (
          /* ── 正常等待状态：转圈 ── */
          <>
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1.4, repeat: Infinity, ease: "linear" }}
              style={{
                width: "34px",
                height: "34px",
                borderRadius: "50%",
                border: "3px solid rgba(110, 231, 183, 0.18)",
                borderTopColor: "rgba(110, 231, 183, 0.85)",
              }}
            />
            <div style={{ textAlign: "center" }}>
              <div
                style={{
                  fontSize: "15px",
                  fontWeight: 500,
                  letterSpacing: "0.02em",
                  marginBottom: "6px",
                }}
              >
                等待首个事件到达
              </div>
              <div
                className="font-mono"
                style={{
                  fontSize: "11.5px",
                  color: "var(--color-text-3)",
                  letterSpacing: "0.05em",
                }}
              >
                流水线启动中，SSE 通道已就绪
              </div>
            </div>
          </>
        )}
      </div>
    </motion.div>
  );
}
