/**
 * roleProjectors/account · 客户经理 BriefCard 投影
 *
 * 输入 EventSnapshot，输出 BriefCard。
 * brief_analysis 模板固定以"准入结论"收尾，左给 PlanGrid（解读章节），右给 GateBanner。
 */

import type { EventSnapshot } from "../eventNormalizer";
import type { BriefCard, PlanBlock, GateInfo, StageHeaderMeta } from "../../types";
import {
  SECTION_LABEL_MAP,
  clamp,
  extractAllSections,
  parseGateVerdict,
  sliceAtSection,
} from "../statusClassifier";

function accountMeta(snap: EventSnapshot, toolCount: number): StageHeaderMeta[] {
  return [
    { label: "产出", value: snap.writtenFields.has("brief_analysis") ? "已交付" : "进行中" },
    { label: "工具", value: `${toolCount} 次` },
    { label: "状态", value: snap.projectStatus || "—" },
  ];
}

export function buildAccountDeck(snap: EventSnapshot): BriefCard {
  const ba = snap.writtenFields.get("brief_analysis") ?? "";

  // 顶层逻辑：brief_analysis 模板固定以 "准入结论" 收尾、之后可选 "修订说明"
  // 在 "准入结论" 处硬切：左给 PlanGrid（解读章节），右给 GateBanner
  // "修订说明" 整段丢弃（"本轮无" 占位无展示价值；有反馈时该信息也只对内部审计有意义）
  const gateSplit = sliceAtSection(ba, "准入结论");
  const briefBody = gateSplit ? gateSplit.before : ba;
  let gateBody = gateSplit ? gateSplit.after : "";
  if (gateBody) {
    const reviseSplit = sliceAtSection(gateBody, "修订说明");
    if (reviseSplit) gateBody = reviseSplit.before;
    gateBody = gateBody.trim();
  }

  // 左侧动态抽全部章节，未识别节名兜底用原文标题
  const blocks: PlanBlock[] = extractAllSections(briefBody).map(({ title, body }) => ({
    label: SECTION_LABEL_MAP[title] ?? title,
    value: body,
  }));

  let gate: GateInfo | undefined;
  if (gateBody) {
    const { verdict, label } = parseGateVerdict(gateBody);
    gate = { verdict, label, body: gateBody };
  }

  const toolCount = Array.from(snap.toolCallsByKey.values())
    .filter((a) => a.role === "account")
    .reduce((s, a) => s + a.calls, 0);

  return {
    header: {
      title: "客户经理 · Brief 解读",
      subtitle: "ACCOUNT · R1",
      meta: accountMeta(snap, toolCount),
    },
    kicker: `CLIENT BRIEF · ${snap.client || "—"}`,
    title: snap.projectType || "—",
    tagline: clamp(snap.brief || "—", 260),
    blocks,
    gate,
  };
}
