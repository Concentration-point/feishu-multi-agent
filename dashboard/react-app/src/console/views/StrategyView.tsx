/**
 * StrategyView
 *
 * 一等公民：Hero 板（策略题眼）+ 2×2 要素 + 渠道分工表。
 * 次要信息：底部 tool chip row。
 */

import { StageHeader, SectionTitle } from "../components/StageHeader";
import { ToolChipRow } from "../components/ToolChipRow";
import { PlanHero, PlanGrid } from "./shared/PlanPrimitives";
import type { AgentSession } from "../types";

interface StrategyViewProps {
  session: AgentSession;
}

export function StrategyView({ session }: StrategyViewProps) {
  const deck = session.strategy;
  const toolCalls = session.toolCalls.filter((t) => t.role === "strategy");

  return (
    <div>
      <StageHeader header={deck.header} />

      <PlanHero kicker={deck.kicker} title={deck.title} tagline={deck.tagline} />
      <PlanGrid blocks={deck.blocks} />

      <SectionTitle>Channel Plan</SectionTitle>
      <div
        style={{
          background: "var(--color-bg-1)",
          border: "1px solid var(--color-border)",
          borderRadius: "10px",
          overflow: "hidden",
        }}
      >
        {deck.channels.map((c, i) => (
          <div
            key={i}
            style={{
              display: "grid",
              gridTemplateColumns: "140px 1fr auto",
              gap: "24px",
              alignItems: "center",
              padding: "18px 28px",
              borderBottom:
                i < deck.channels.length - 1
                  ? "1px solid var(--color-border-soft)"
                  : "none",
              transition: "background 0.18s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--color-bg-2)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
            }}
          >
            <div
              className="font-mono font-semibold text-text-1"
              style={{
                fontSize: "12.5px",
                letterSpacing: "0.04em",
                display: "flex",
                alignItems: "center",
                gap: "10px",
              }}
            >
              <span
                aria-hidden
                style={{
                  width: "6px",
                  height: "6px",
                  borderRadius: "50%",
                  background: "var(--color-accent)",
                  boxShadow: "0 0 8px rgba(110, 231, 183, 0.4)",
                  flexShrink: 0,
                }}
              />
              {c.name}
            </div>
            <div
              className="text-text-2"
              style={{ fontSize: "13px", lineHeight: 1.6 }}
            >
              {c.role}
            </div>
            <div
              className="font-mono font-semibold text-accent"
              style={{
                fontSize: "11px",
                padding: "4px 12px",
                borderRadius: "999px",
                background: "rgba(16, 185, 129, 0.1)",
                border: "1px solid rgba(110, 231, 183, 0.2)",
                letterSpacing: "0.04em",
                fontVariantNumeric: "tabular-nums",
                whiteSpace: "nowrap",
              }}
            >
              {c.count} 篇
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: "24px" }}>
        <ToolChipRow calls={toolCalls} />
      </div>
    </div>
  );
}
