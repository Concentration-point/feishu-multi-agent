/**
 * AccountView
 *
 * 一等公民：Brief 卡片（客户目标、预算、时间线、画像、品牌 tone）。
 * 次要信息：底部 tool chip row。
 */

import { StageHeader } from "../components/StageHeader";
import { ToolChipRow } from "../components/ToolChipRow";
import { PlanHero, PlanGrid } from "./shared/PlanPrimitives";
import type { AgentSession } from "../types";

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
      <PlanGrid blocks={deck.blocks} />
      <ToolChipRow calls={toolCalls} />
    </div>
  );
}
