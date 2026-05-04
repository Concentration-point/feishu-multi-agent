/**
 * ReportTrigger
 *
 * 顶部栏「数据分析」按钮：
 *   - 主按钮：BarChart 图标 + 文案「数据分析」
 *   - hover/click 弹出 3 个报告类型（周报 / 洞察 / 决策）
 *   - 选中后 POST /api/report，按钮 in-place 显示状态：
 *       idle → sending → sent (2.4s) → idle
 *       失败：error (3s) → idle
 *
 * 与 TopBar 现有按钮风格一致：font-mono、6px 圆角、绿色 accent hover。
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BarChart3, Check, Loader2, AlertCircle, ChevronDown } from "lucide-react";

type ReportType = "weekly" | "insight" | "decision";
type Status = "idle" | "sending" | "sent" | "error";

const REPORT_OPTIONS: { type: ReportType; label: string; hint: string }[] = [
  { type: "weekly",   label: "运营周报", hint: "全维度汇总" },
  { type: "insight",  label: "数据洞察", hint: "聚焦异常现象" },
  { type: "decision", label: "决策建议", hint: "面向管理层" },
];

export function ReportTrigger() {
  const [open, setOpen]       = useState(false);
  const [status, setStatus]   = useState<Status>("idle");
  const [errorMsg, setErrMsg] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);
  const resetTimer = useRef<number | null>(null);

  // 点击外部关闭下拉
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // 卸载时清理 reset timer
  useEffect(() => {
    return () => {
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    };
  }, []);

  const trigger = useCallback(async (type: ReportType) => {
    setOpen(false);
    setStatus("sending");
    setErrMsg("");
    try {
      const res = await fetch("/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_type: type }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      setStatus("sent");
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
      resetTimer.current = window.setTimeout(() => setStatus("idle"), 2400);
    } catch (e) {
      setStatus("error");
      setErrMsg(e instanceof Error ? e.message : "触发失败");
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
      resetTimer.current = window.setTimeout(() => setStatus("idle"), 3000);
    }
  }, []);

  // 按钮内容随状态切换
  const renderButton = () => {
    if (status === "sending") {
      return (
        <>
          <motion.span
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
            style={{ display: "inline-flex" }}
          >
            <Loader2 size={12} />
          </motion.span>
          <span>启动中...</span>
        </>
      );
    }
    if (status === "sent") {
      return (
        <>
          <Check size={12} strokeWidth={2.6} />
          <span>已触发 · 见飞书</span>
        </>
      );
    }
    if (status === "error") {
      return (
        <>
          <AlertCircle size={12} />
          <span title={errorMsg}>触发失败</span>
        </>
      );
    }
    return (
      <>
        <BarChart3 size={12} strokeWidth={2.4} />
        <span>数据分析</span>
        <ChevronDown
          size={11}
          style={{
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform .18s ease",
          }}
        />
      </>
    );
  };

  // 状态对应的颜色
  const colorFor = () => {
    if (status === "sent")    return { fg: "var(--color-accent)",     bd: "rgba(110,231,183,0.4)" };
    if (status === "error")   return { fg: "rgba(239,68,68,0.95)",    bd: "rgba(239,68,68,0.4)"   };
    if (status === "sending") return { fg: "var(--color-text-1)",     bd: "rgba(110,231,183,0.3)" };
    return { fg: "var(--color-text-2)", bd: "var(--color-border)" };
  };

  const c = colorFor();
  const interactive = status === "idle";

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <motion.button
        type="button"
        onClick={() => interactive && setOpen((v) => !v)}
        whileTap={interactive ? { scale: 0.96 } : undefined}
        title="生成数据分析报告并推送到飞书"
        className="inline-flex items-center font-mono"
        style={{
          gap: "7px",
          padding: "6px 14px",
          borderRadius: "6px",
          fontSize: "11.5px",
          color: c.fg,
          background: "var(--color-bg-2)",
          border: `1px solid ${c.bd}`,
          cursor: interactive ? "pointer" : "default",
          transition: "color .18s ease, border-color .18s ease",
          minWidth: "120px",
          justifyContent: "center",
        }}
        onMouseEnter={(e) => {
          if (!interactive) return;
          e.currentTarget.style.color = "var(--color-accent)";
          e.currentTarget.style.borderColor = "rgba(110, 231, 183, 0.4)";
        }}
        onMouseLeave={(e) => {
          if (!interactive) return;
          e.currentTarget.style.color = "var(--color-text-2)";
          e.currentTarget.style.borderColor = "var(--color-border)";
        }}
      >
        {renderButton()}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.16 }}
            className="font-mono"
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              right: 0,
              minWidth: "200px",
              padding: "6px",
              borderRadius: "8px",
              background: "var(--color-bg-1)",
              border: "1px solid var(--color-border)",
              boxShadow: "0 12px 32px rgba(0,0,0,0.45)",
              zIndex: 50,
            }}
          >
            {REPORT_OPTIONS.map((opt) => (
              <button
                key={opt.type}
                type="button"
                onClick={() => trigger(opt.type)}
                className="w-full text-left"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  gap: "2px",
                  padding: "8px 10px",
                  borderRadius: "5px",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--color-text-2)",
                  width: "100%",
                  transition: "background .12s ease, color .12s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--color-bg-2)";
                  e.currentTarget.style.color = "var(--color-accent)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color = "var(--color-text-2)";
                }}
              >
                <span style={{ fontSize: "12px", letterSpacing: ".02em" }}>
                  {opt.label}
                </span>
                <span
                  style={{
                    fontSize: "10px",
                    color: "var(--color-text-4)",
                    letterSpacing: ".04em",
                  }}
                >
                  {opt.hint}
                </span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
