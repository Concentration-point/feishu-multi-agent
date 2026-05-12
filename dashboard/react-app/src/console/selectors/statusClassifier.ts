/**
 * statusClassifier · 状态分类 + 文本切片工具集
 *
 * 集中处理：
 *   - 准入结论 verdict 判定（pass / reject / conditional / review）
 *   - 审核 verdict 判定（approve / revise / reject），含"驳回条数"等统计句陷阱过滤
 *   - markdown 章节抽取 / 切片
 *   - 字符串清洗与展示截断
 *
 * 不依赖 eventNormalizer 任何具体状态结构，纯函数。
 */

import type { ContentRowState } from "./eventNormalizer";
import type { GateVerdict, ReviewVerdict } from "../types";

// =============== 通用字符串工具 ===============

export function shortTime(timestamp: number): string {
  const d = new Date(timestamp * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export function asString(v: unknown): string {
  if (typeof v === "string") return v;
  if (v == null) return "";
  return String(v);
}

export function safeJson(v: unknown): unknown {
  if (typeof v !== "string") return v;
  const t = v.trim();
  if ((t.startsWith("{") && t.endsWith("}")) || (t.startsWith("[") && t.endsWith("]"))) {
    try {
      return JSON.parse(t);
    } catch {
      return v;
    }
  }
  return v;
}

export function clamp(str: string, n: number): string {
  if (str.length <= n) return str;
  return str.slice(0, n).trimEnd() + "…";
}

// =============== Markdown 章节抽取 ===============

/**
 * 清洗从文案 agent 那里拿到的正文——
 * 去掉 <!-- 注释 -->、前导 markdown 标题、多余空白。
 * 用来产生"干净的摘要"不是给 full body 用的。
 */
export function cleanForExcerpt(src: string): string {
  if (!src) return "";
  let s = src;
  // 删除 HTML 注释（含多行）
  s = s.replace(/<!--[\s\S]*?-->/g, "");
  // 删除 markdown 头部前的所有 `# 标题` 行
  s = s.replace(/^\s*#{1,6}\s+[^\n]*\n+/gm, "");
  // 合并多余空行
  s = s.replace(/\n{2,}/g, "\n").trim();
  return s;
}

/**
 * 从 review_summary 中取针对某个草稿的点评——
 * 跳过 markdown 标题，抓第一个有意义的段落。
 */
export function extractFirstParagraph(text: string): string {
  const lines = text.split("\n");
  for (const raw of lines) {
    const l = raw.trim();
    if (!l) continue;
    if (/^#{1,6}\s/.test(l)) continue; // markdown 标题
    if (/^[-*]\s/.test(l) || /^\d+\.\s/.test(l)) {
      // 列表项首字符后取内容
      return l.replace(/^[-*]\s+/, "").replace(/^\d+\.\s+/, "");
    }
    return l;
  }
  return "";
}

/**
 * 按 markdown heading 抽节内容。
 * 支持 ##/###/#### 等任意级别（`#+`），可选编号前缀（如 "8. "），
 * 节体在下一个 `#+` heading 或 EOF 处终止——避免遇到非同级 heading 时贪婪到 EOF。
 */
export function parseMarkdownBlocks(md: string, sectionNames: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  if (!md) return out;
  for (const name of sectionNames) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(
      `(?:^|\\n)#+[ \\t]*(?:\\d+[ \\t]*\\.?[ \\t]*)?${escaped}[^\\n]*\\n([\\s\\S]*?)(?=\\n#+[ \\t]+|$)`,
    );
    const m = md.match(re);
    if (m) out[name] = m[1].trim();
  }
  return out;
}

/**
 * 在某个"分隔节标题"处把 markdown 切成 (before, after, headLineEnd)。
 * 用于 brief_analysis 在"准入结论"处硬切左右两段。
 *   - splitName: 节标题文本（不含编号/井号），如 "准入结论"
 *   - 返回 null 表示没找到该节
 */
export function sliceAtSection(
  md: string,
  splitName: string,
): { before: string; after: string } | null {
  const escaped = splitName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(
    `(?:^|\\n)#+[ \\t]*(?:\\d+[ \\t]*\\.?[ \\t]*)?${escaped}[^\\n]*\\n?`,
  );
  const m = re.exec(md);
  if (!m || m.index === undefined) return null;
  const before = md.slice(0, m.index).replace(/\s+$/, "");
  const after = md.slice(m.index + m[0].length);
  return { before, after };
}

/**
 * 动态把 brief markdown 拆成所有 `#+ N. 标题` 章节，按出现顺序返回。
 * 不依赖固定节名清单——agent 偶发增删节也能跟得上。
 */
export function extractAllSections(md: string): { title: string; body: string }[] {
  const out: { title: string; body: string }[] = [];
  const re = /(?:^|\n)#+[ \t]*(?:\d+[ \t]*\.?[ \t]*)?([^\n#][^\n]*?)[ \t]*\n([\s\S]*?)(?=\n#+[ \t]+|$)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(md)) !== null) {
    const title = m[1].trim();
    const body = m[2].trim();
    if (title && body) out.push({ title, body });
  }
  return out;
}

/**
 * 已知节名 → PlanGrid 卡片标签（保持视觉一致，未识别节名直接用中文原标题）。
 * 与 agents/account_manager/soul.md 模板对齐，可容错节名变体。
 */
export const SECTION_LABEL_MAP: Record<string, string> = {
  品牌调研: "Brand Research",
  项目摘要: "Summary",
  目标与受众: "Target & Audience",
  目标理解: "Target",
  受众与场景理解: "Audience",
  关键约束: "Constraints",
  关键信息与约束: "Constraints",
  运营与转化承接: "Conversion",
  合规与风险: "Compliance",
  信息获取记录: "Sources",
  已确认信息: "Confirmed",
  缺失信息: "Missing",
};

// =============== verdict 判定 ===============

/**
 * 从 "准入结论" 文本前 80 字解析 verdict：
 *   - 不通过 / 拒绝 / 驳回 → reject
 *   - 有条件 / 条件通过 / 待补充 / 待修改 / 待人审 → conditional
 *   - 通过（不带 不/未）→ pass
 *   - 其它 → review
 */
export function parseGateVerdict(body: string): { verdict: GateVerdict; label: string } {
  const head = body.slice(0, 80);
  if (/不通过|拒绝|驳回|REJECT/i.test(head)) {
    return { verdict: "reject", label: "不通过" };
  }
  if (/有条件|条件通过|待补充|待修改|待人审|CONDITIONAL/i.test(head)) {
    return { verdict: "conditional", label: "有条件通过" };
  }
  if (/(?<![不未])通过|PASS/.test(head)) {
    return { verdict: "pass", label: "通过" };
  }
  return { verdict: "review", label: "待审" };
}

/**
 * 在文本里找到第一个 key 的位置，截取后续 280 字符。
 * 找不到任何 key 时返回 null（不再像旧版 fallback 到 text.slice(0, 200)，
 * 那会让所有草稿都吃到 review_summary 开头的统计句导致误判）。
 */
export function sliceAroundKeyOrNull(text: string, keys: string[]): string | null {
  for (const k of keys) {
    if (!k) continue;
    const i = text.indexOf(k);
    if (i >= 0) return text.slice(i, i + 280);
  }
  return null;
}

/**
 * 优先级：
 *   1. row.review_status（审核 agent 写到内容行的最权威字段）
 *   2. review_summary 中能定位到本草稿标题的片段做关键词匹配
 *   3. 都拿不到时，根据 draft 状态降级（有正文 → approve, 没正文 → revise）
 *
 * 关键陷阱：审核 agent 的 review_summary 开头通常是
 *   "本轮审核概况 通过条数：5 驳回条数：0 ..."
 * 旧版正则 `/驳回/` 直接命中"驳回条数"导致全 reject。新版只匹配判词，
 * 不匹配统计句（"X条数"、"X率"）。
 */
export function detectVerdictForDraft(row: ContentRowState, review: string): ReviewVerdict {
  // 1. 优先用每条内容自己的 review_status（审核 agent 写到内容行的字段）
  const rowStatus = (row.review_status || "").trim();
  if (rowStatus) {
    if (/^通过$|^approved?$|^pass$/i.test(rowStatus)) return "approve";
    if (/需修改|需完善|需修订|revise/i.test(rowStatus)) return "revise";
    if (/驳回|退回|reject/i.test(rowStatus)) return "reject";
    // 未识别但有值 — 通常是新枚举或自然语言，按 draft 状态降级
  }

  // 2. fallback：在 review_summary 里找针对本草稿的段落
  if (review) {
    const titleKey = row.title.slice(0, 10);
    const seq = `seq ${row.sequence}|第${row.sequence}`;
    const slice = sliceAroundKeyOrNull(review, [
      row.title,
      titleKey,
      `seq_${row.sequence}`,
      seq,
    ]);
    if (slice) {
      // 只匹配判词，避免命中"驳回条数：X"、"通过率"这种统计性表述
      if (/驳回(?!条数)|退回|不通过(?!率)|不达标|red\s*flag/i.test(slice)) return "reject";
      if (/需修改|需完善|需修订|建议(?:调整|补充|修订)/i.test(slice)) return "revise";
      if (/通过(?!率|条数)|approved?/i.test(slice)) return "approve";
    }
  }

  // 3. 降级：有正文视为通过（避免没真实审核结果时硬判驳回）
  return row.draft_content ? "approve" : "revise";
}
