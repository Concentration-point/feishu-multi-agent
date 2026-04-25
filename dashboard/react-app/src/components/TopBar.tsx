import { motion, AnimatePresence } from "framer-motion";
import { Activity, CheckCircle2, Radio, WifiOff, History } from "lucide-react";
import { usePipelineStore } from "../stores/usePipelineStore";
import { useElapsed } from "../hooks/useElapsed";
import type { ConnectionStatus } from "../types";

const statusConfig: Record<
  ConnectionStatus,
  { icon: typeof Activity; color: string; glow: string }
> = {
  idle: { icon: Radio, color: "#6b6b76", glow: "none" },
  live: { icon: Activity, color: "#3aba6e", glow: "0 0 12px rgba(58,186,110,0.6)" },
  done: { icon: CheckCircle2, color: "#5b8def", glow: "none" },
  error: { icon: WifiOff, color: "#e55353", glow: "none" },
  replay: { icon: History, color: "#5b8def", glow: "none" },
};

export function TopBar() {
  const { projectTitle, projectBrief, status, statusText, startTime } =
    usePipelineStore();
  const elapsed = useElapsed(startTime);
  const cfg = statusConfig[status];
  const Icon = cfg.icon;

  return (
    <header className="topbar">
      <div className="topbar-left">
        <motion.h1
          className="topbar-title"
          key={projectTitle}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          {projectTitle}
        </motion.h1>
        <AnimatePresence mode="wait">
          {projectBrief && (
            <motion.span
              className="topbar-brief"
              key={projectBrief}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.25 }}
            >
              {projectBrief}
            </motion.span>
          )}
        </AnimatePresence>
      </div>
      <div className="topbar-right">
        <motion.div
          className="status-indicator"
          animate={{
            boxShadow: status === "live" ? cfg.glow : "none",
          }}
          transition={{ duration: 0.5 }}
        >
          <Icon
            size={14}
            color={cfg.color}
            className={status === "live" ? "pulse-icon" : ""}
          />
        </motion.div>
        <span className="status-text" style={{ color: cfg.color }}>
          {statusText}
        </span>
        <span className="elapsed">{elapsed}</span>
      </div>
    </header>
  );
}
