/**
 * ExperienceEvolution · 经验进化可视化
 *
 * 一等公民：每条经验卡片的生命周期（蒸馏 → 打分 → 去重合并 → 沉淀）。
 * 设计：漏斗式进度 + 卡片列表 + 置信度条形图 + 阶段标记。
 *
 * 用色约定：
 *   - 青绿（accent）：已沉淀
 *   - 琥珀（warn）：合并中 / 已合并
 *   - 红（danger）：跳过（低置信度）
 *   - 紫（purple）：打分中
 */

import { motion } from "framer-motion";
import type { ExperienceEvolution as EvolutionData, ExperienceCard, ExperiencePhase } from "../types";

interface ExperienceEvolutionProps {
  data: EvolutionData;
}

const PHASE_META: Record<ExperiencePhase, { label: string; color: string; icon: string }> = {
  loaded:    { label: "已加载", color: "rgba(96, 165, 250, 0.8)", icon: "▽" },
  distilled: { label: "蒸馏", color: "var(--color-text-3)", icon: "◇" },
  scored:    { label: "已评分", color: "rgba(168, 130, 255, 0.85)", icon: "◈" },
  merging:   { label: "合并中", color: "var(--color-warn, #f0b429)", icon: "⟐" },
  merged:    { label: "已合并", color: "var(--color-warn, #f0b429)", icon: "⬡" },
  saved:     { label: "已沉淀", color: "var(--color-accent)", icon: "✦" },
  skipped:   { label: "跳过", color: "var(--color-danger, #e55353)", icon: "✕" },
};

const ROLE_COLORS: Record<string, string> = {
  account_manager: "#60a5fa",
  strategist: "#a78bfa",
  copywriter: "#34d399",
  reviewer: "#fbbf24",
  project_manager: "#f87171",
};

export function ExperienceEvolution({ data }: ExperienceEvolutionProps) {
  if (data.cards.length === 0 && !data.settled) {
    return <EmptyState />;
  }

  const savedCount = data.cards.filter((c) => c.phase === "saved").length;
  const skippedCount = data.cards.filter((c) => c.phase === "skipped").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* 漏斗摘要 */}
      {data.settled && (
        <FunnelSummary
          total={data.totalDistilled}
          passed={data.passedScoring}
          merged={data.mergedGroups}
          settled={data.finalSettled}
        />
      )}

      {/* 未完成时的实时统计 */}
      {!data.settled && data.cards.length > 0 && (
        <div
          className="font-mono"
          style={{
            display: "flex",
            gap: "12px",
            fontSize: "10.5px",
            color: "var(--color-text-3)",
            letterSpacing: "0.06em",
          }}
        >
          <span>评分 <strong style={{ color: "var(--color-text-1)" }}>{data.cards.length}</strong></span>
          <span>通过 <strong style={{ color: "var(--color-accent)" }}>{savedCount}</strong></span>
          <span>跳过 <strong style={{ color: "var(--color-danger, #e55353)" }}>{skippedCount}</strong></span>
        </div>
      )}

      {/* 卡片列表 */}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {data.cards.map((card, i) => (
          <ExperienceCardRow key={`${card.roleId}-${i}`} card={card} index={i} />
        ))}
      </div>
    </div>
  );
}

function FunnelSummary({
  total,
  passed,
  merged,
  settled,
}: {
  total: number;
  passed: number;
  merged: number;
  settled: number;
}) {
  const steps = [
    { label: "蒸馏", value: total, color: "var(--color-text-2)" },
    { label: "通过", value: passed, color: "rgba(168, 130, 255, 0.85)" },
    { label: "合并", value: merged, color: "var(--color-warn, #f0b429)" },
    { label: "沉淀", value: settled, color: "var(--color-accent)" },
  ];

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "4px",
        padding: "8px 12px",
        borderRadius: "8px",
        background: "var(--color-bg-2)",
        border: "1px solid var(--color-border-soft)",
      }}
    >
      {steps.map((step, i) => (
        <div
          key={step.label}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "4px",
          }}
        >
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: i * 0.08, duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "2px",
              minWidth: "40px",
            }}
          >
            <span
              className="font-mono"
              style={{
                fontSize: "15px",
                fontWeight: 700,
                color: step.color,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {step.value}
            </span>
            <span
              className="font-sans"
              style={{
                fontSize: "9.5px",
                color: "var(--color-text-4)",
                letterSpacing: "0.08em",
              }}
            >
              {step.label}
            </span>
          </motion.div>
          {i < steps.length - 1 && (
            <span
              className="font-mono"
              style={{
                color: "var(--color-text-4)",
                fontSize: "10px",
                opacity: 0.5,
                margin: "0 2px",
              }}
            >
              →
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function ExperienceCardRow({ card, index }: { card: ExperienceCard; index: number }) {
  const meta = PHASE_META[card.phase];
  const roleColor = ROLE_COLORS[card.roleId] ?? "var(--color-text-2)";
  const confPercent = Math.min(100, Math.round(card.confidence * 100));
  const threshPercent = Math.round(card.threshold * 100);

  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.06, duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
      className="group"
      style={{
        position: "relative",
        padding: "10px 12px",
        borderRadius: "8px",
        background: "var(--color-bg-2)",
        border: "1px solid var(--color-border-soft)",
        overflow: "hidden",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = meta.color;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--color-border-soft)";
      }}
    >
      {/* 左侧阶段指示线 */}
      <span
        aria-hidden
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: "3px",
          background: meta.color,
          borderRadius: "3px 0 0 3px",
        }}
      />

      {/* 头部：角色 + 阶段标记 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "6px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: roleColor,
              flexShrink: 0,
            }}
          />
          <span
            className="font-sans"
            style={{ fontSize: "12px", color: "var(--color-text-1)", fontWeight: 500 }}
          >
            {card.roleName}
          </span>
          <span
            className="font-mono"
            style={{
              fontSize: "10px",
              color: "var(--color-text-4)",
              letterSpacing: "0.04em",
            }}
          >
            {card.category}
          </span>
        </div>
        <span
          className="font-mono"
          style={{
            fontSize: "10px",
            padding: "2px 7px",
            borderRadius: "999px",
            background: `${meta.color}18`,
            color: meta.color,
            border: `1px solid ${meta.color}40`,
            letterSpacing: "0.06em",
            whiteSpace: "nowrap",
          }}
        >
          {meta.icon} {meta.label}
          {card.mergedFrom ? ` (${card.mergedFrom}→1)` : ""}
        </span>
      </div>

      {/* 经验教训 */}
      {card.lesson && (
        <div
          className="font-sans"
          style={{
            fontSize: "11.5px",
            color: "var(--color-text-2)",
            lineHeight: 1.55,
            marginBottom: "8px",
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {card.lesson}
        </div>
      )}

      {/* 置信度进度条 */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <div
          style={{
            flex: 1,
            height: "4px",
            borderRadius: "2px",
            background: "var(--color-bg-0)",
            position: "relative",
            overflow: "hidden",
          }}
        >
          {/* 阈值标记线 */}
          <span
            aria-hidden
            style={{
              position: "absolute",
              left: `${threshPercent}%`,
              top: 0,
              bottom: 0,
              width: "1px",
              background: "var(--color-text-4)",
              opacity: 0.6,
              zIndex: 2,
            }}
          />
          <motion.div
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ delay: index * 0.06 + 0.15, duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: `${confPercent}%`,
              background: card.passed
                ? "linear-gradient(90deg, rgba(16, 185, 129, 0.5), rgba(16, 185, 129, 0.9))"
                : "linear-gradient(90deg, rgba(229, 83, 83, 0.4), rgba(229, 83, 83, 0.7))",
              borderRadius: "2px",
              transformOrigin: "left center",
            }}
          />
        </div>
        <span
          className="font-mono"
          style={{
            fontSize: "10px",
            fontWeight: 600,
            fontVariantNumeric: "tabular-nums",
            color: card.passed ? "var(--color-accent)" : "var(--color-danger, #e55353)",
            minWidth: "30px",
            textAlign: "right",
          }}
        >
          {confPercent}%
        </span>
      </div>

      {/* 置信因子 tooltip 区域 */}
      {card.factors && (
        <div
          className="font-mono"
          style={{
            display: "flex",
            gap: "8px",
            marginTop: "5px",
            fontSize: "9.5px",
            color: "var(--color-text-4)",
            letterSpacing: "0.04em",
          }}
        >
          <FactorChip label="通过率" value={card.factors.pass_rate != null ? `${Math.round(card.factors.pass_rate * 100)}%` : "—"} ok={card.factors.pass_rate != null && card.factors.pass_rate >= 0.5} />
          <FactorChip label="任务" value={card.factors.task_completed ? "✓" : "✕"} ok={card.factors.task_completed} />
          <FactorChip label="无返工" value={card.factors.no_rework ? "✓" : "✕"} ok={card.factors.no_rework} />
          <FactorChip label="知识引用" value={card.factors.knowledge_cited ? "✓" : "✕"} ok={card.factors.knowledge_cited} />
        </div>
      )}

      {/* 存储标记 */}
      {card.phase === "saved" && (
        <div
          className="font-mono"
          style={{
            display: "flex",
            gap: "6px",
            marginTop: "4px",
            fontSize: "9.5px",
          }}
        >
          {card.bitableSaved && (
            <span style={{ color: "var(--color-accent)", opacity: 0.8 }}>Bitable ✓</span>
          )}
          {card.wikiSaved && (
            <span style={{ color: "var(--color-accent)", opacity: 0.8 }}>Wiki ✓</span>
          )}
        </div>
      )}
    </motion.div>
  );
}

function FactorChip({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <span style={{ color: ok ? "var(--color-accent-dim, #6ee7b7)" : "var(--color-text-4)" }}>
      {label}:{value}
    </span>
  );
}

function EmptyState() {
  return (
    <div
      className="font-mono"
      style={{
        padding: "14px 10px",
        fontSize: "11px",
        color: "var(--color-text-4)",
        border: "1px dashed var(--color-border)",
        borderRadius: "5px",
        letterSpacing: "0.05em",
        textAlign: "center",
      }}
    >
      等待经验沉淀...
    </div>
  );
}
