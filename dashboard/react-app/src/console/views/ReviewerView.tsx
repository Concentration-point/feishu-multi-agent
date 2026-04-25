/**
 * ReviewerView
 *
 * 一等公民：checklist 条目（每篇稿子的评审结论 + 操作按钮）。
 * 次要信息：底部 tool chip row。
 */

import { Check, AlertTriangle, X } from "lucide-react";
import { StageHeader, SectionTitle } from "../components/StageHeader";
import { ToolChipRow } from "../components/ToolChipRow";
import type { AgentSession, ReviewVerdict } from "../types";

interface ReviewerViewProps {
  session: AgentSession;
}

const VERDICT_STYLE: Record<
  ReviewVerdict,
  { borderLeft: string; iconBg: string; iconFg: string }
> = {
  approve: {
    borderLeft: "var(--color-accent)",
    iconBg: "rgba(16, 185, 129, 0.15)",
    iconFg: "var(--color-accent)",
  },
  revise: {
    borderLeft: "var(--color-warn)",
    iconBg: "rgba(251, 191, 36, 0.15)",
    iconFg: "var(--color-warn)",
  },
  reject: {
    borderLeft: "var(--color-danger)",
    iconBg: "rgba(248, 113, 113, 0.15)",
    iconFg: "var(--color-danger)",
  },
};

const VERDICT_ICON: Record<ReviewVerdict, typeof Check> = {
  approve: Check,
  revise: AlertTriangle,
  reject: X,
};

const ACTION_LABEL: Record<ReviewVerdict, string> = {
  approve: "APPROVE",
  revise: "REVISE",
  reject: "REJECT",
};

export function ReviewerView({ session }: ReviewerViewProps) {
  const deck = session.reviewer;
  const toolCalls = session.toolCalls.filter((t) => t.role === "review");

  return (
    <div>
      <StageHeader header={deck.header} />

      <SectionTitle>Per-Draft Assessment</SectionTitle>
      {deck.items.length === 0 ? (
        <div
          className="border border-dashed border-border rounded-lg text-text-3 text-[13px] flex items-center justify-center"
          style={{ padding: "60px", minHeight: "160px" }}
        >
          <span className="font-mono tracking-[0.1em]">审核 Agent 待文案完成后介入 · · ·</span>
        </div>
      ) : (
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {deck.items.map((item) => {
          const style = VERDICT_STYLE[item.verdict];
          const Icon = VERDICT_ICON[item.verdict];
          return (
            <div
              key={item.id}
              style={{
                display: "grid",
                gridTemplateColumns: "auto 1fr auto",
                gap: "18px",
                alignItems: "center",
                background: "var(--color-bg-1)",
                border: "1px solid var(--color-border)",
                borderLeftWidth: "3px",
                borderLeftColor: style.borderLeft,
                borderRadius: "8px",
                padding: "20px 26px",
              }}
            >
              <div
                className="rounded-full grid place-items-center"
                style={{
                  width: "26px",
                  height: "26px",
                  background: style.iconBg,
                  color: style.iconFg,
                  flexShrink: 0,
                }}
              >
                <Icon size={13} strokeWidth={3} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div
                  className="font-semibold text-text-1"
                  style={{ fontSize: "13.5px", marginBottom: "6px", lineHeight: 1.45 }}
                >
                  {item.title}
                </div>
                <div
                  className="text-text-2"
                  style={{ fontSize: "12.5px", lineHeight: 1.6 }}
                >
                  {item.note}
                </div>
              </div>
              <button
                type="button"
                className="font-mono bg-bg-2 text-text-2 border border-border hover:text-accent hover:border-accent transition-colors"
                style={{
                  padding: "6px 14px",
                  borderRadius: "5px",
                  fontSize: "11px",
                  letterSpacing: "0.06em",
                  flexShrink: 0,
                }}
              >
                {ACTION_LABEL[item.verdict]}
              </button>
            </div>
          );
        })}
      </div>
      )}

      <ToolChipRow calls={toolCalls} />
    </div>
  );
}
