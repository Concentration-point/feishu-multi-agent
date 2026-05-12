/**
 * roleProjectors/copy · 文案 CopywriterDeck 投影
 *
 * 把 contentRows + draftOrder 摊成 ContentDraft[]，把 fan-out 子 agent 摘要汇总。
 */

import type { EventSnapshot } from "../eventNormalizer";
import { normalizePlatform } from "../eventNormalizer";
import type {
  ContentDraft,
  CopywriterDeck,
  KnowledgeChip,
  PlatformSubAgentSummary,
} from "../../types";
import { clamp, cleanForExcerpt } from "../statusClassifier";
import { countByRole } from "./shared";

export function buildCopywriterDeck(snap: EventSnapshot): CopywriterDeck {
  const drafts: ContentDraft[] = [];
  let idx = 0;
  for (const rid of snap.draftOrder) {
    const row = snap.contentRows.get(rid);
    if (!row) continue;
    idx++;
    const platform = normalizePlatform(row.platform);
    const full = row.draft_content ?? "";
    const cleanedExcerpt = cleanForExcerpt(full);
    // 当 draft_content 未回传（文案 Agent 未调 write_content）时，fullBody 回退
    // 展示策略师下发的骨架信息，避免 drawer 与预览卡片出现"预览有内容/详情空"的断裂
    const skeletonFallback = full
      ? null
      : [
          row.key_message ? `**核心卖点**\n\n${row.key_message}` : null,
          row.target_audience ? `**目标人群**\n\n${row.target_audience}` : null,
          row.content_type ? `**内容类型**\n\n${row.content_type}` : null,
        ]
          .filter(Boolean)
          .join("\n\n");
    const fullBody = full
      ? full
      : skeletonFallback
        ? `${skeletonFallback}\n\n---\n\n> ⚠️ 完整正文尚未回传（文案 Agent 未调用 write_content("draft_content")），当前仅展示策略师下发的骨架信息。`
        : "— 尚未撰写";
    drafts.push({
      id: rid,
      seq: row.sequence || idx,
      platform,
      contentType: row.content_type || "—",
      title: row.title || `Draft ${idx}`,
      excerpt: clamp(cleanedExcerpt || row.key_message || "—", 160),
      fullBody,
      wordCount: row.word_count ?? full.length,
      status: full ? "done" : "draft",
    });
  }

  const knowledge: KnowledgeChip[] = [];
  const seen = new Set<string>();
  for (const q of snap.searchQueries.slice(-8).reverse()) {
    if (seen.has(q)) continue;
    seen.add(q);
    knowledge.push({ label: clamp(q, 40), kind: "purple" });
    if (knowledge.length >= 5) break;
  }

  const totalWords = drafts.reduce((s, d) => s + (d.wordCount || 0), 0);
  const toolCount = countByRole(snap, "copy");

  // fan-out 子 agent 摘要：非空才下发，历史项目不出现该字段
  const platformSubAgents: PlatformSubAgentSummary[] = Array.from(
    snap.copywriterPlatformSubAgents,
    ([platform, v]) => ({
      platform,
      patchApplied: v.patchApplied,
      toolCalls: v.toolCalls,
    }),
  ).sort((a, b) => a.platform.localeCompare(b.platform));

  const deck: CopywriterDeck = {
    header: {
      title: `文案 · ${drafts.length} 篇产出`,
      subtitle: "COPYWRITER · R2",
      meta: [
        { label: "产出", value: `${drafts.length} 篇` },
        { label: "字数", value: totalWords.toLocaleString() },
        { label: "工具", value: `${toolCount} 次` },
      ],
    },
    drafts,
    knowledge,
  };
  if (platformSubAgents.length > 0) {
    deck.platformSubAgents = platformSubAgents;
  }
  return deck;
}
