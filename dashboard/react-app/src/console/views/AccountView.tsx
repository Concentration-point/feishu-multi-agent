/**
 * AccountView
 *
 * 一等公民：Brief Hero（Client/Campaign/Brief 已归位 kicker/title/tagline）。
 * 二等公民：CLIENT BRIEF 之下左右分栏：左 Brief 解读（PlanGrid，4 份）/ 右 Gate 准入结论（3 份）。
 * 末位：底部 tool chip row。
 *
 * 设计要点：
 *   - 不再重复展示 Client/Campaign/Brief/Status（Hero + StageHeader meta 已承载）
 *   - Brief 解读 vs Gate = 4:3，左主右辅；无 gate 时 PlanGrid 占满整行
 */

import { StageHeader } from "../components/StageHeader";
import { ToolChipRow } from "../components/ToolChipRow";
import { MarkdownBody } from "../components/MarkdownBody";
import { PlanHero, PlanGrid } from "./shared/PlanPrimitives";
import type { AgentSession, GateInfo, GateVerdict } from "../types";

interface AccountViewProps {
  session: AgentSession;
}

export function AccountView({ session }: AccountViewProps) {
  const deck = session.account;
  const toolCalls = session.toolCalls.filter((t) => t.role === "account");

  return (
    <div>
      <StageHeader header={deck.header} />
      <PlanHero kicker={deck.kicker} title={deck.title} tagline={deck.tagline} />
      {deck.gate ? (
        <div
          className="grid gap-4 my-4 items-stretch"
          style={{ gridTemplateColumns: "minmax(0, 4fr) minmax(0, 3fr)" }}
        >
          <div className="min-w-0">
            <PlanGrid blocks={deck.blocks} />
          </div>
          <div className="min-w-0">
            <GateBanner gate={deck.gate} />
          </div>
        </div>
      ) : (
        <PlanGrid blocks={deck.blocks} />
      )}
      <ToolChipRow calls={toolCalls} />
    </div>
  );
}

/**
 * Gate 准入结论 整行 banner
 *   - 左侧 4px verdict 色条
 *   - 顶部 kicker (GATE · 准入结论) + verdict 徽章
 *   - 全宽 MarkdownBody，不裁剪
 */
const VERDICT_COLOR: Record<GateVerdict, string> = {
  pass: "var(--color-accent)",
  conditional: "var(--color-warn)",
  reject: "var(--color-danger)",
  review: "var(--color-info)",
};

const VERDICT_GLOW: Record<GateVerdict, string> = {
  pass: "rgba(110, 231, 183, 0.10)",
  conditional: "rgba(251, 191, 36, 0.10)",
  reject: "rgba(248, 113, 113, 0.10)",
  review: "rgba(96, 165, 250, 0.10)",
};

function GateBanner({ gate }: { gate: GateInfo }) {
  const color = VERDICT_COLOR[gate.verdict];
  const glow = VERDICT_GLOW[gate.verdict];

  return (
    <div
      className="relative overflow-hidden h-full"
      style={{
        background: "var(--color-bg-1)",
        border: "1px solid var(--color-border)",
        borderLeft: `4px solid ${color}`,
        borderRadius: "8px",
        padding: "20px 24px 22px 28px",
      }}
    >
      <span
        aria-hidden
        className="absolute top-0 right-0 pointer-events-none"
        style={{
          width: "240px",
          height: "100%",
          background: `radial-gradient(circle at right top, ${glow}, transparent 70%)`,
        }}
      />
      <div className="relative flex items-center gap-3 mb-3">
        <span
          className="font-mono"
          style={{
            fontSize: "10px",
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--color-text-3)",
          }}
        >
          GATE · 准入结论
        </span>
        <span
          className="font-mono"
          style={{
            fontSize: "10.5px",
            letterSpacing: "0.08em",
            padding: "3px 10px",
            borderRadius: "4px",
            border: `1px solid ${color}`,
            color,
            background: glow,
            fontWeight: 600,
          }}
        >
          {gate.label.toUpperCase()}
        </span>
      </div>
      <div className="relative">
        <MarkdownBody>{gate.body}</MarkdownBody>
      </div>
    </div>
  );
}
