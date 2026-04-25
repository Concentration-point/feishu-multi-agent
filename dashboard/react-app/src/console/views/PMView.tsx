/**
 * PMView
 *
 * 一等公民：里程碑卡片 + 顶部时间线。
 * 次要信息：底部 tool chip row。
 */

import { StageHeader, SectionTitle } from "../components/StageHeader";
import { TimelineStrip } from "../components/TimelineStrip";
import { ToolChipRow } from "../components/ToolChipRow";
import type { AgentSession } from "../types";

interface PMViewProps {
  session: AgentSession;
}

export function PMView({ session }: PMViewProps) {
  const deck = session.pm;
  const toolCalls = session.toolCalls.filter((t) => t.role === "pm");

  return (
    <div>
      <StageHeader header={deck.header} />
      <div className="mt-6">
        <TimelineStrip steps={session.timelineSteps} />
      </div>

      <SectionTitle>Milestones</SectionTitle>
      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}
      >
        {deck.milestones.map((m) => (
          <div
            key={m.id}
            className="group relative overflow-hidden transition-colors"
            style={{
              background: "var(--color-bg-1)",
              border: "1px solid var(--color-border)",
              borderRadius: "10px",
              padding: "22px 26px",
              opacity: m.done ? 1 : 0.82,
            }}
          >
            <span
              className="absolute top-0 left-0 bg-accent opacity-0 group-hover:opacity-100 transition-opacity"
              style={{ width: "3px", height: "100%" }}
            />
            <div
              className="flex items-center gap-2 font-mono text-text-3"
              style={{ marginBottom: "10px", fontSize: "11px" }}
            >
              <span
                className={`rounded-full ${m.done ? "bg-accent" : "bg-text-4"}`}
                style={{ width: "6px", height: "6px" }}
              />
              <span>{m.done ? "完成" : "进行中 / 未开始"}</span>
            </div>
            <h4
              className="font-serif font-semibold text-text-1"
              style={{
                fontSize: "17px",
                lineHeight: 1.4,
                marginBottom: "10px",
              }}
            >
              {m.title}
            </h4>
            <p
              className="text-text-2"
              style={{ fontSize: "13.5px", lineHeight: 1.72 }}
            >
              {m.summary}
            </p>
          </div>
        ))}
      </div>

      <ToolChipRow calls={toolCalls} />
    </div>
  );
}
