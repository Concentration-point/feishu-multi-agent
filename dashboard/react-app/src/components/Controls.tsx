import { useState } from "react";
import { motion } from "framer-motion";
import { Play, Pause, RotateCcw, Zap } from "lucide-react";
import { usePipelineStore } from "../stores/usePipelineStore";

interface ControlsProps {
  onDemo: () => void;
  onReconnect: () => void;
}

export function Controls({ onDemo, onReconnect }: ControlsProps) {
  const { events, status } = usePipelineStore();
  const [paused, setPaused] = useState(false);
  const [demoRunning, setDemoRunning] = useState(false);
  const count = events.length;
  const pct = Math.min((count / 60) * 100, 100);
  const isActive = status === "live" || status === "done" || status === "replay";

  const handleDemo = () => {
    setDemoRunning(true);
    onDemo();
  };

  return (
    <div className="controls">
      <div className="controls-left">
        <motion.button
          className="btn btn-accent"
          onClick={handleDemo}
          disabled={demoRunning || isActive}
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.95 }}
        >
          <Zap size={13} />
          <span>{demoRunning ? "运行中..." : "Mock 演示"}</span>
        </motion.button>
        <motion.button
          className="btn"
          onClick={() => setPaused(!paused)}
          disabled={!isActive}
          whileTap={{ scale: 0.95 }}
        >
          {paused ? <Play size={13} /> : <Pause size={13} />}
          <span>{paused ? "继续" : "暂停"}</span>
        </motion.button>
        <motion.button
          className="btn"
          onClick={onReconnect}
          disabled={!isActive}
          whileTap={{ scale: 0.95 }}
        >
          <RotateCcw size={13} />
          <span>断开重连</span>
        </motion.button>
      </div>
      <div className="controls-center">
        <div className="progress-track">
          <motion.div
            className="progress-fill"
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
          {status === "live" && (
            <motion.div
              className="progress-glow"
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.4, ease: "easeOut" }}
            />
          )}
        </div>
        <span className="progress-label">{count} 事件</span>
      </div>
    </div>
  );
}
