/**
 * CopywriterView
 *
 * 一等公民：文案瀑布流卡片（真正的产出）。
 * 次要信息：顶部 tool chip row（含 write_content chip，但 chip 不渲染正文）、底部知识库引用。
 */

import { useConsoleStore } from "../useConsoleStore";
import { StageHeader, SectionTitle } from "../components/StageHeader";
import { TimelineStrip } from "../components/TimelineStrip";
import { ToolChipRow } from "../components/ToolChipRow";
import type { AgentSession, ContentDraft, Platform, PlatformSubAgentSummary } from "../types";

const PLATFORM_LABEL: Record<Platform, string> = {
  xhs: "小红书",
  gzh: "公众号",
  dy: "抖音",
  wb: "微博",
  bili: "B站",
  zhihu: "知乎",
  other: "其它",
};

const PLATFORM_CLASS: Record<Platform, string> = {
  xhs: "bg-danger/10 text-[#fca5a5]",
  gzh: "bg-accent-dim/10 text-accent",
  dy: "bg-purple/10 text-purple",
  wb: "bg-warn/10 text-warn",
  bili: "bg-info/10 text-info",
  zhihu: "bg-info/10 text-info",
  other: "bg-bg-3 text-text-3",
};

const STATUS_LABEL = {
  done: "已完成",
  draft: "草稿",
  review: "审核中",
} as const;

const STATUS_DOT = {
  done: "bg-accent",
  draft: "bg-warn",
  review: "bg-info",
} as const;

interface CopywriterViewProps {
  session: AgentSession;
}

export function CopywriterView({ session }: CopywriterViewProps) {
  const deck = session.copywriter;
  const toolCalls = session.toolCalls.filter((t) => t.role === "copy");

  return (
    <div>
      <StageHeader header={deck.header} />
      <TimelineStrip steps={session.timelineSteps} />
      <ToolChipRow label="上下文准备" calls={toolCalls} />

      {deck.platformSubAgents && deck.platformSubAgents.length > 0 && (
        <PlatformSubAgentPanel agents={deck.platformSubAgents} />
      )}

      <SectionTitle>Drafts · 本轮产出</SectionTitle>
      {deck.drafts.length === 0 ? (
        <div
          className="border border-dashed border-border rounded-lg text-text-3 text-[13px] flex items-center justify-center"
          style={{ padding: "60px", minHeight: "160px" }}
        >
          <span className="font-mono tracking-[0.1em]">
            文案 Agent 尚未开始撰写 · · ·
          </span>
        </div>
      ) : (
        <div
          className="grid gap-5"
          style={{
            gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))",
          }}
        >
          {deck.drafts.map((d) => (
            <DraftCard key={d.id} draft={d} />
          ))}
        </div>
      )}

      {deck.knowledge.length > 0 && (
        <>
          <SectionTitle>Recently Tapped Knowledge</SectionTitle>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "8px",
              marginTop: "4px",
              marginBottom: "24px",
            }}
          >
            {deck.knowledge.map((k, i) => (
              <span
                key={i}
                className="font-sans"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "6px 14px 6px 12px",
                  borderRadius: "999px",
                  background: "var(--color-bg-2)",
                  border: "1px solid var(--color-border)",
                  color: "var(--color-text-2)",
                  fontSize: "12.5px",
                  letterSpacing: "0.01em",
                  lineHeight: 1.3,
                  whiteSpace: "nowrap",
                  transition: "all 0.18s",
                  cursor: "default",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "rgba(167, 139, 250, 0.35)";
                  e.currentTarget.style.color = "var(--color-text-1)";
                  e.currentTarget.style.background = "var(--color-bg-3)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-border)";
                  e.currentTarget.style.color = "var(--color-text-2)";
                  e.currentTarget.style.background = "var(--color-bg-2)";
                }}
              >
                <span
                  aria-hidden
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    background: "var(--color-purple)",
                    boxShadow: "0 0 6px rgba(167, 139, 250, 0.5)",
                    flexShrink: 0,
                  }}
                />
                {k.label}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function DraftCard({ draft }: { draft: ContentDraft }) {
  const openDrawer = useConsoleStore((s) => s.openDrawer);

  return (
    <button
      type="button"
      onClick={() => openDrawer(`draft:${draft.id}`)}
      className="group relative text-left transition-all cursor-pointer hover:-translate-y-[1px]"
      style={{
        background: "var(--color-bg-1)",
        border: "1px solid var(--color-border)",
        borderRadius: "10px",
        padding: "24px 28px 22px",
        overflow: "hidden",
        display: "block",
        width: "100%",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "rgba(110, 231, 183, 0.3)";
        e.currentTarget.style.boxShadow = "0 6px 24px rgba(0, 0, 0, 0.3)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--color-border)";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      <span
        className="absolute top-0 left-0 bg-accent opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ width: "3px", height: "100%" }}
      />

      <div
        className="flex items-center gap-2 font-mono text-text-3"
        style={{ marginBottom: "14px", fontSize: "11px" }}
      >
        <span
          className={`font-medium ${PLATFORM_CLASS[draft.platform]}`}
          style={{
            padding: "2px 8px",
            borderRadius: "3px",
            fontSize: "10px",
            letterSpacing: "0.05em",
          }}
        >
          {PLATFORM_LABEL[draft.platform]}
        </span>
        <span className="text-text-3">{draft.contentType}</span>
        <span className="ml-auto text-text-4">#seq {draft.seq}</span>
      </div>

      <h3
        className="font-serif font-semibold text-text-1"
        style={{
          fontSize: "17px",
          lineHeight: 1.4,
          letterSpacing: "-0.005em",
          marginBottom: "12px",
        }}
      >
        {draft.title}
      </h3>

      <p
        className="text-text-2 overflow-hidden"
        style={{
          fontSize: "13.5px",
          lineHeight: 1.75,
          display: "-webkit-box",
          WebkitLineClamp: 4,
          WebkitBoxOrient: "vertical",
          marginBottom: "16px",
        }}
      >
        {draft.excerpt}
      </p>

      <div
        className="flex items-center justify-between font-mono text-text-3"
        style={{
          paddingTop: "14px",
          borderTop: "1px dashed var(--color-border-soft)",
          fontSize: "11px",
        }}
      >
        <span className="inline-flex items-center gap-1.5">
          <span
            className={`rounded-full ${STATUS_DOT[draft.status]}`}
            style={{ width: "6px", height: "6px" }}
          />
          {STATUS_LABEL[draft.status]}
        </span>
        <span className="text-text-4">{draft.wordCount.toLocaleString()} 字</span>
      </div>
    </button>
  );
}

function PlatformSubAgentPanel({ agents }: { agents: PlatformSubAgentSummary[] }) {
  return (
    <div
      className="border border-border rounded-lg bg-bg-1"
      style={{ padding: "14px 18px", marginTop: "16px", marginBottom: "18px" }}
    >
      <div
        className="font-mono text-text-3 uppercase tracking-[0.12em]"
        style={{ fontSize: "10.5px", marginBottom: "10px" }}
      >
        平台子 Agent · fan-out 分工
      </div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "10px",
        }}
      >
        {agents.map((a) => {
          const patchBadge = a.patchApplied
            ? { text: "✓ 专属补丁", cls: "bg-accent/10 text-accent" }
            : { text: "⚠ 软兜底", cls: "bg-warn/10 text-warn" };
          return (
            <div
              key={a.platform}
              className="border border-border-soft rounded-md bg-bg-2"
              style={{
                padding: "8px 12px",
                display: "inline-flex",
                alignItems: "center",
                gap: "10px",
                fontSize: "12px",
              }}
            >
              <span className="font-medium text-text-1">{a.platform}</span>
              <span
                className={`font-mono ${patchBadge.cls}`}
                style={{
                  padding: "2px 8px",
                  borderRadius: "3px",
                  fontSize: "10.5px",
                  letterSpacing: "0.03em",
                }}
              >
                {patchBadge.text}
              </span>
              <span className="font-mono text-text-3" style={{ fontSize: "11px" }}>
                {a.toolCalls} calls
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
