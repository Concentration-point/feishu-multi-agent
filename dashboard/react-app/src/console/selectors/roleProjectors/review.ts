/**
 * roleProjectors/review · 审核 ReviewerDeck 投影
 *
 * 对每条 draft 通过 statusClassifier.detectVerdictForDraft 判定，
 * 再从 review_summary / row.review_feedback 提取 note。
 */

import type { ContentRowState, EventSnapshot } from "../eventNormalizer";
import { normalizePlatform } from "../eventNormalizer";
import type { ReviewItem, ReviewerDeck } from "../../types";
import {
  clamp,
  detectVerdictForDraft,
  extractFirstParagraph,
  sliceAroundKeyOrNull,
} from "../statusClassifier";

function extractNoteForDraft(row: ContentRowState, review: string): string {
  // 优先用每条内容自己的 review_feedback
  if (row.review_feedback) return clamp(row.review_feedback, 130);
  if (!review) return row.draft_content ? "已完成，待审核。" : "尚未撰写。";
  const slice = sliceAroundKeyOrNull(review, [row.title, row.title.slice(0, 10)]);
  if (!slice) return row.draft_content ? "已完成，待审核。" : "尚未撰写。";
  const firstMeaningful = extractFirstParagraph(slice);
  return clamp(firstMeaningful || "已产出，审核意见待生成。", 130);
}

export function buildReviewerDeck(snap: EventSnapshot): ReviewerDeck {
  const items: ReviewItem[] = [];
  const review = snap.writtenFields.get("review_summary") ?? "";
  // 先尝试 per-draft review status：很多文案 row 不一定带 review status，
  // 从 human_review 参数和 review_summary 的 markdown 里提取大致结论
  for (const rid of snap.draftOrder) {
    const row = snap.contentRows.get(rid);
    if (!row) continue;
    const verdict = detectVerdictForDraft(row, review);
    const action: ReviewItem["action"] =
      verdict === "approve" ? "APPROVE" : verdict === "revise" ? "REVISE" : "REJECT";
    items.push({
      id: rid,
      draftSeq: row.sequence,
      verdict,
      platform: normalizePlatform(row.platform),
      title: `${row.platform}｜${row.title}`,
      note: extractNoteForDraft(row, review),
      action,
    });
  }
  const approved = items.filter((i) => i.verdict === "approve").length;
  const revise = items.filter((i) => i.verdict === "revise").length;
  const reject = items.filter((i) => i.verdict === "reject").length;
  return {
    header: {
      title: `审核报告 · ${items.length} 篇产出`,
      subtitle: "REVIEWER · R3",
      meta: [
        { label: "通过", value: String(approved) },
        { label: "待修订", value: String(revise) },
        { label: "问题", value: String(reject) },
      ],
    },
    items,
  };
}
