/**
 * StageHeader
 *
 * 一等公民：当前角色的主标题 + 关键数字 meta。
 * 所有角色视图共用。
 */

import type { StageSectionHeader } from "../types";

interface StageHeaderProps {
  header: StageSectionHeader;
}

export function StageHeader({ header }: StageHeaderProps) {
  return (
    <div
      className="flex items-baseline flex-wrap gap-x-4 gap-y-2 border-b border-border-soft"
      style={{ marginBottom: "4px", paddingBottom: "18px" }}
    >
      <h1
        className="font-serif font-medium tracking-[-0.01em] text-text-1"
        style={{ fontSize: "24px" }}
      >
        {header.title}
      </h1>
      <span className="font-mono text-[11px] text-text-3 tracking-[0.05em] uppercase">
        {header.subtitle}
      </span>
      <div className="ml-auto flex gap-5 font-mono text-[11px] text-text-3 flex-wrap">
        {header.meta.map((m, i) => (
          <span key={i} className="whitespace-nowrap">
            <span className="text-text-4">{m.label}</span>{" "}
            <strong className="text-accent font-semibold">{m.value}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * 配合 Plan 类视图用的小 Kicker 条
 */
export function SectionTitle({ children }: { children: string }) {
  return (
    <div className="flex items-center gap-2.5 mt-6 mb-3.5 font-mono text-[11px] tracking-[0.12em] uppercase text-text-3">
      <span>{children}</span>
      <span className="flex-1 h-px bg-border-soft" />
    </div>
  );
}
