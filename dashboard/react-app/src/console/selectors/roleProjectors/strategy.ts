/**
 * roleProjectors/strategy · 策略师 StrategyDeck 投影
 *
 * 把 strategy 字段切成已知节，渠道分工从 drafts 反推。
 */

import type { EventSnapshot } from "../eventNormalizer";
import type { ChannelRow, PlanBlock, StrategyDeck } from "../../types";
import { clamp, parseMarkdownBlocks } from "../statusClassifier";
import { countByRole } from "./shared";

export function buildStrategyDeck(snap: EventSnapshot): StrategyDeck {
  const strat = snap.writtenFields.get("strategy") ?? "";
  const secs = parseMarkdownBlocks(strat, [
    "目标受众",
    "核心洞察",
    "品牌调性",
    "核心策略",
    "KPI",
    "转化路径",
    "内容矩阵",
  ]);

  const blocks: PlanBlock[] = [];
  if (secs["目标受众"]) blocks.push({ label: "Target Audience", value: secs["目标受众"] });
  if (secs["核心洞察"]) blocks.push({ label: "Core Insight", value: secs["核心洞察"] });
  if (secs["品牌调性"]) blocks.push({ label: "Brand Tone", value: secs["品牌调性"] });
  if (secs["核心策略"]) blocks.push({ label: "Core Strategy", value: secs["核心策略"] });
  if (secs["KPI"]) blocks.push({ label: "KPI Funnel", value: secs["KPI"] });
  if (blocks.length === 0 && strat) {
    blocks.push({ label: "Strategy Digest", value: strat });
  }
  if (blocks.length === 0) {
    blocks.push({ label: "Strategy", value: "— 策略尚未生成" });
  }

  // 渠道分工：从 drafts 反推
  const channelMap = new Map<string, { count: number; roleDesc: string }>();
  for (const rid of snap.draftOrder) {
    const row = snap.contentRows.get(rid);
    if (!row) continue;
    const key = row.platform || "其他";
    const cur = channelMap.get(key);
    const roleDesc = row.content_type || "";
    channelMap.set(key, {
      count: (cur?.count ?? 0) + 1,
      roleDesc: cur?.roleDesc ? cur.roleDesc : roleDesc,
    });
  }
  const channels: ChannelRow[] = Array.from(channelMap, ([name, v]) => ({
    name,
    role: v.roleDesc || "—",
    count: v.count,
  }));

  const toolCount = countByRole(snap, "strategy");
  const kickerParts = ["CAMPAIGN STRATEGY"];
  if (snap.projectType) kickerParts.push(snap.projectType);

  const firstLine = strat.split("\n").find((l) => l.trim()) ?? "";
  const cleanFirst = firstLine.replace(/^#+\s*/, "").trim();

  return {
    header: {
      title: "策略方案 · 内容总纲",
      subtitle: "STRATEGIST · R1",
      meta: [
        { label: "渠道", value: String(channels.length || "—") },
        { label: "篇目", value: String(snap.draftOrder.length || "—") },
        { label: "工具", value: `${toolCount} 次` },
      ],
    },
    kicker: kickerParts.join(" · "),
    title: clamp(cleanFirst || "围绕项目节点制定内容策略", 80),
    tagline: clamp(strat.split("\n").filter((l) => l.trim())[1] ?? snap.brief ?? "—", 220),
    blocks,
    channels,
  };
}
