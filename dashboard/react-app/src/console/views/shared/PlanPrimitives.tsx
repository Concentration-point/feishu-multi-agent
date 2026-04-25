/**
 * Plan 原语 · 给 Account / Strategy View 共用
 *
 * Hero 板：kicker + 大标题 + tagline，右上角青绿 radial glow。
 * PlanGrid：2 列要素卡，**只渲染有真值的 block**，避免 "—" 占位。
 * Block value 用 MarkdownBody（compact density）渲染 —— agent 真实输出
 * 常带 markdown，裸字符串展示会丢层次。
 */

import { MarkdownBody } from "../../components/MarkdownBody";
import type { PlanBlock } from "../../types";

interface PlanHeroProps {
  kicker: string;
  title: string;
  tagline: string;
}

const PLACEHOLDER = new Set(["—", "-", ""]);

function isPlaceholder(value: string): boolean {
  return PLACEHOLDER.has(value.trim());
}

export function PlanHero({ kicker, title, tagline }: PlanHeroProps) {
  const titleReal = !isPlaceholder(title);
  const taglineReal = !isPlaceholder(tagline);

  return (
    <div
      className="relative bg-gradient-to-br from-bg-1 to-bg-2 border border-border rounded-lg my-6 overflow-hidden"
      style={{ padding: "32px 36px" }}
    >
      <span
        aria-hidden
        className="absolute top-0 right-0 pointer-events-none"
        style={{
          width: "260px",
          height: "100%",
          background:
            "radial-gradient(circle at right top, var(--color-accent-glow), transparent 70%)",
        }}
      />
      <div className="relative">
        <div className="font-mono text-[10px] tracking-[0.14em] text-accent uppercase mb-3">
          {kicker}
        </div>
        <h2
          className="font-serif font-medium tracking-[-0.01em] text-text-1 leading-tight"
          style={{
            fontSize: titleReal ? "28px" : "20px",
            marginBottom: taglineReal ? "12px" : 0,
            color: titleReal ? "var(--color-text-1)" : "var(--color-text-3)",
          }}
        >
          {titleReal ? title : "等待 Agent 产出中 · · ·"}
        </h2>
        {taglineReal && (
          <p
            className="text-text-2 leading-[1.7]"
            style={{ fontSize: "14px", maxWidth: "720px" }}
          >
            {tagline}
          </p>
        )}
      </div>
    </div>
  );
}

export function PlanGrid({ blocks }: { blocks: PlanBlock[] }) {
  const realBlocks = blocks.filter((b) => !isPlaceholder(b.value));

  if (realBlocks.length === 0) {
    return (
      <div
        className="border border-dashed border-border rounded-lg text-text-3 text-[13px] flex items-center justify-center"
        style={{ padding: "40px", minHeight: "120px" }}
      >
        <span className="font-mono tracking-[0.1em]">等待结构化数据...</span>
      </div>
    );
  }

  return (
    <div
      className="grid gap-4"
      style={{
        gridTemplateColumns:
          realBlocks.length === 1
            ? "1fr"
            : "repeat(auto-fit, minmax(280px, 1fr))",
      }}
    >
      {realBlocks.map((b, i) => (
        <div
          key={i}
          style={{
            background: "var(--color-bg-1)",
            border: "1px solid var(--color-border)",
            borderRadius: "8px",
            padding: "20px 24px",
          }}
        >
          <div
            className="font-mono"
            style={{
              fontSize: "10px",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--color-text-3)",
              marginBottom: "10px",
            }}
          >
            {b.label}
          </div>
          <MarkdownBody density="compact">{b.value}</MarkdownBody>
        </div>
      ))}
    </div>
  );
}
