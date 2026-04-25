import { motion, AnimatePresence } from "framer-motion";
import {
  Database,
  CalendarCheck,
  BarChart3,
  Circle,
  CheckCircle2,
} from "lucide-react";
import { usePipelineStore } from "../stores/usePipelineStore";

const MEMORY_FIELDS = [
  { key: "brief_analysis", label: "Brief 解读" },
  { key: "strategy", label: "策略方案" },
  { key: "review_summary", label: "审核总评" },
  { key: "delivery", label: "交付摘要" },
];

function MemoryCard() {
  const filledFields = usePipelineStore((s) => s.filledFields);
  const projectStatus = usePipelineStore((s) => s.projectStatus);

  return (
    <motion.div
      className="info-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
    >
      <div className="card-header">
        <Database size={14} color="#6b6b76" />
        <span className="card-title">共享记忆 / 项目主表</span>
      </div>
      <div className="memory-fields">
        {MEMORY_FIELDS.map((field) => {
          const filled = filledFields.has(field.key);
          return (
            <motion.div
              key={field.key}
              className={`memory-field ${filled ? "filled" : ""}`}
              animate={
                filled
                  ? { backgroundColor: ["rgba(229,168,46,0.15)", "transparent"] }
                  : {}
              }
              transition={{ duration: 1.5 }}
            >
              <AnimatePresence mode="wait">
                {filled ? (
                  <motion.div
                    key="filled"
                    initial={{ scale: 0, rotate: -90 }}
                    animate={{ scale: 1, rotate: 0 }}
                    transition={{
                      type: "spring",
                      stiffness: 500,
                      damping: 15,
                    }}
                  >
                    <CheckCircle2 size={14} color="#3aba6e" />
                  </motion.div>
                ) : (
                  <motion.div key="empty" exit={{ scale: 0 }}>
                    <Circle size={14} color="#3a3a44" />
                  </motion.div>
                )}
              </AnimatePresence>
              <span className="field-label">{field.label}</span>
            </motion.div>
          );
        })}
      </div>
      <div className="project-status-bar">
        <motion.span
          className="status-label"
          key={projectStatus}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {projectStatus}
        </motion.span>
      </div>
    </motion.div>
  );
}

function ContentCard() {
  const contentTotal = usePipelineStore((s) => s.contentTotal);
  const contentDone = usePipelineStore((s) => s.contentDone);
  const pct = contentTotal > 0 ? (contentDone / contentTotal) * 100 : 0;

  return (
    <motion.div
      className="info-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.2 }}
    >
      <div className="card-header">
        <CalendarCheck size={14} color="#6b6b76" />
        <span className="card-title">内容排期 / 进度</span>
      </div>
      <div className="content-progress">
        <div className="progress-track">
          <motion.div
            className="progress-fill accent"
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
        <motion.span
          className="progress-text"
          key={`${contentDone}-${contentTotal}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          {contentDone} / {contentTotal} 完成
        </motion.span>
      </div>
    </motion.div>
  );
}

function ToolStatsCard() {
  const toolCounts = usePipelineStore((s) => s.toolCounts);
  const entries = Object.entries(toolCounts).sort((a, b) => b[1] - a[1]);

  return (
    <motion.div
      className="info-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.3 }}
    >
      <div className="card-header">
        <BarChart3 size={14} color="#6b6b76" />
        <span className="card-title">工具调用统计</span>
      </div>
      <div className="tool-stats">
        <AnimatePresence>
          {entries.length === 0 ? (
            <div className="tool-empty">等待数据</div>
          ) : (
            entries.map(([name, count]) => (
              <motion.div
                key={name}
                className="tool-row"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25 }}
                layout
              >
                <span className="tool-name">{name}</span>
                <motion.span
                  className="tool-count"
                  key={count}
                  initial={{ scale: 1.3 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 400 }}
                >
                  {count}
                </motion.span>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

export function InfoPanel() {
  return (
    <div className="right-panel">
      <MemoryCard />
      <ContentCard />
      <ToolStatsCard />
    </div>
  );
}
