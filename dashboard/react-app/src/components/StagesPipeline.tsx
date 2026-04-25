import { motion } from "framer-motion";
import {
  UserCheck,
  Lightbulb,
  PenTool,
  ShieldCheck,
  ClipboardList,
  ChevronRight,
} from "lucide-react";
import { usePipelineStore } from "../stores/usePipelineStore";
import type { StageState } from "../types";

const STAGE_CONFIG = [
  { role: "account_manager", name: "客户经理", Icon: UserCheck },
  { role: "strategist", name: "策略师", Icon: Lightbulb },
  { role: "copywriter", name: "文案", Icon: PenTool },
  { role: "reviewer", name: "审核", Icon: ShieldCheck },
  { role: "project_manager", name: "项目经理", Icon: ClipboardList },
] as const;

const stateStyles: Record<StageState, { border: string; bg: string; dot: string; opacity: number }> = {
  waiting: {
    border: "transparent",
    bg: "transparent",
    dot: "#3a3a44",
    opacity: 0.4,
  },
  active: {
    border: "#e5a82e",
    bg: "rgba(229,168,46,0.1)",
    dot: "#e5a82e",
    opacity: 1,
  },
  completed: {
    border: "#33333d",
    bg: "rgba(58,186,110,0.06)",
    dot: "#3aba6e",
    opacity: 0.7,
  },
};

export function StagesPipeline() {
  const stages = usePipelineStore((s) => s.stages);

  return (
    <div className="stages">
      {STAGE_CONFIG.map((cfg, i) => {
        const stage = stages[cfg.role] || { state: "waiting", meta: "" };
        const style = stateStyles[stage.state];
        const { Icon } = cfg;

        return (
          <div key={cfg.role} className="stage-wrapper">
            {i > 0 && (
              <motion.div
                className="stage-connector"
                animate={{
                  opacity: stage.state !== "waiting" ? 1 : 0.3,
                  background:
                    stage.state !== "waiting"
                      ? "linear-gradient(90deg, #3aba6e, #e5a82e)"
                      : "#33333d",
                }}
                transition={{ duration: 0.5 }}
              >
                <ChevronRight size={12} className="connector-arrow" />
              </motion.div>
            )}
            <motion.div
              className="stage-card"
              animate={{
                borderColor: style.border,
                backgroundColor: style.bg,
                opacity: style.opacity,
              }}
              transition={{ duration: 0.4, ease: "easeOut" }}
              whileHover={{ scale: 1.04, transition: { duration: 0.15 } }}
            >
              <motion.div
                className="stage-icon-ring"
                animate={{
                  boxShadow:
                    stage.state === "active"
                      ? "0 0 20px rgba(229,168,46,0.4), 0 0 40px rgba(229,168,46,0.15)"
                      : stage.state === "completed"
                        ? "0 0 12px rgba(58,186,110,0.3)"
                        : "none",
                  borderColor: style.dot,
                }}
                transition={{ duration: 0.5 }}
              >
                <Icon
                  size={18}
                  color={
                    stage.state === "active"
                      ? "#e5a82e"
                      : stage.state === "completed"
                        ? "#3aba6e"
                        : "#6b6b76"
                  }
                />
                {stage.state === "active" && (
                  <motion.div
                    className="stage-pulse-ring"
                    animate={{ scale: [1, 1.8], opacity: [0.6, 0] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: "easeOut" }}
                  />
                )}
              </motion.div>
              <span className="stage-name">{cfg.name}</span>
              <motion.span
                className="stage-meta"
                key={stage.meta}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.2 }}
              >
                {stage.meta}
              </motion.span>
            </motion.div>
          </div>
        );
      })}
    </div>
  );
}
