/**
 * ToolDrawer
 *
 * 一等公民：被点击工具的 request / response（或文案的全文）。
 * 右侧 560px 抽屉，ESC 关闭，点击 backdrop 关闭。
 * 产出型工具（write_content）不再粘贴正文——提示去主面板看产出，避免双渲染。
 */

import { type ReactNode, useEffect, useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useConsoleStore } from "../useConsoleStore";
import { JsonBlock } from "./JsonBlock";
import { MarkdownBody } from "./MarkdownBody";
import { toolLabel } from "../toolLabels";
import type { AgentSession, ContentDraft, ToolCall } from "../types";

interface ToolDrawerProps {
  session: AgentSession;
}

interface DrawerContent {
  title: string;
  sub: string;
  body: ReactNode;
}

export function ToolDrawer({ session }: ToolDrawerProps) {
  const { drawerOpen, drawerKey, closeDrawer } = useConsoleStore();

  // ESC 关闭
  useEffect(() => {
    if (!drawerOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeDrawer();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [drawerOpen, closeDrawer]);

  const content = useMemo<DrawerContent | null>(() => {
    if (!drawerKey) return null;

    if (drawerKey.startsWith("draft:")) {
      const id = drawerKey.slice("draft:".length);
      // 以 id 精准匹配（避免多 draft sequence 相同造成的张冠李戴）
      const draft = session.copywriter.drafts.find((d) => d.id === id);
      if (draft) return renderDraftDrawer(draft);
    }

    const tool = session.toolCalls.find((t) => t.id === drawerKey);
    if (tool) return renderToolDrawer(tool);

    return null;
  }, [drawerKey, session]);

  return (
    <AnimatePresence>
      {drawerOpen && (
        <>
          <motion.div
            className="fixed inset-0 bg-black/50 z-[99]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeDrawer}
          />
          <motion.aside
            className="fixed top-0 right-0 h-screen w-[560px] bg-bg-1 border-l border-border z-[100] flex flex-col shadow-[-20px_0_60px_rgba(0,0,0,0.4)]"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", ease: [0.32, 0.72, 0, 1], duration: 0.25 }}
          >
            <header
              className="flex items-center"
              style={{
                padding: "18px 24px",
                borderBottom: "1px solid var(--color-border)",
                gap: "14px",
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: "15px",
                  fontWeight: 600,
                  color: "var(--color-accent)",
                  letterSpacing: "0.01em",
                }}
              >
                {content?.title ?? "—"}
              </div>
              <div
                className="font-mono"
                style={{
                  fontSize: "10.5px",
                  color: "var(--color-text-3)",
                  marginLeft: "auto",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {content?.sub ?? ""}
              </div>
              <button
                type="button"
                onClick={closeDrawer}
                className="bg-transparent border border-border text-text-2 w-[26px] h-[26px] rounded grid place-items-center hover:text-text-1 hover:border-accent transition-colors"
              >
                <X size={14} />
              </button>
            </header>
            <div
              className="scroll-thin flex-1 overflow-y-auto"
              style={{ padding: "28px 36px 48px" }}
            >
              {content?.body ?? (
                <div className="text-text-3 text-sm">未找到对应内容。</div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function renderToolDrawer(tool: ToolCall): DrawerContent {
  const durLabel =
    tool.avgMs >= 1000 ? `${(tool.avgMs / 1000).toFixed(2)}s` : `${tool.avgMs}ms`;
  const sub = `${tool.name}() · R${tool.round} · ${tool.calls}× · avg ${durLabel}`;

  return {
    title: toolLabel(tool.name),
    sub,
    body: (
      <>
        {tool.invocations && tool.invocations.length > 0 && (
          <DrawerSection label={`INVOKED · ${tool.calls} 次`}>
            <pre className="scroll-thin bg-bg-0 border border-border rounded-md p-4 font-mono text-[12px] leading-[1.65] overflow-x-auto">
              {tool.invocations.map((inv, i) => (
                <div key={i} className="flex gap-4">
                  <span className="text-accent">
                    {inv.label}
                    {inv.note ? ` → ${inv.note}` : ""}
                  </span>
                  <span className="text-text-4 ml-auto">
                    {inv.ms >= 1000 ? `${(inv.ms / 1000).toFixed(1)}s` : `${inv.ms}ms`}
                  </span>
                </div>
              ))}
            </pre>
          </DrawerSection>
        )}

        {extractMarkdownPayload(tool.request) && (
          <DrawerSection label="产出内容 · Agent 写入的 Markdown">
            <div
              style={{
                padding: "18px 20px",
                background: "var(--color-bg-0)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                maxHeight: "420px",
                overflowY: "auto",
              }}
              className="scroll-thin"
            >
              <MarkdownBody density="full">
                {extractMarkdownPayload(tool.request)!}
              </MarkdownBody>
            </div>
          </DrawerSection>
        )}

        {tool.request !== undefined && (
          <DrawerSection label="REQUEST · params">
            <JsonBlock value={tool.request} />
          </DrawerSection>
        )}

        {tool.response !== undefined && (
          <DrawerSection label="RESPONSE · 返回值">
            <JsonBlock value={tool.response} />
          </DrawerSection>
        )}

        {tool.stateTransition && (
          <DrawerSection label="STATE TRANSITION">
            <div className="font-mono text-[12px] text-accent bg-bg-0 border border-border rounded-md p-4">
              {tool.stateTransition}
            </div>
          </DrawerSection>
        )}

        {tool.producesContent && (
          <DrawerSection label="产出内容 · 见主面板文案卡片">
            <div className="text-text-3 text-[12px]">
              工具 bubble 不再重复渲染文案正文，正文作为一等产出显示在主区域。
            </div>
          </DrawerSection>
        )}
      </>
    ),
  };
}

function renderDraftDrawer(draft: ContentDraft): DrawerContent {
  const PLATFORM_LABEL: Record<string, string> = {
    xhs: "小红书",
    gzh: "公众号",
    dy: "抖音",
    wb: "微博",
    bili: "B站",
    zhihu: "知乎",
    other: "其它",
  };
  const platformLabel = PLATFORM_LABEL[draft.platform] ?? "其它";
  const PLATFORM_COLOR: Record<string, string> = {
    xhs: "#fca5a5",
    gzh: "var(--color-accent)",
    dy: "var(--color-purple)",
    wb: "var(--color-warn)",
    bili: "var(--color-info)",
    zhihu: "var(--color-info)",
    other: "var(--color-text-3)",
  };

  return {
    title: `${platformLabel} · seq ${draft.seq}`,
    sub: `${draft.wordCount.toLocaleString()} 字 · 草稿 #${draft.seq}`,
    body: (
      <article style={{ paddingTop: "4px" }}>
        {/* 元信息薄条 —— 平台色小点 + 类型标签，放在标题上方做 kicker */}
        <div
          className="font-mono"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            fontSize: "10.5px",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--color-text-3)",
            marginBottom: "18px",
          }}
        >
          <span
            aria-hidden
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: PLATFORM_COLOR[draft.platform],
              boxShadow: `0 0 8px ${PLATFORM_COLOR[draft.platform]}55`,
            }}
          />
          <span>{platformLabel}</span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span>{draft.contentType}</span>
        </div>

        {/* 标题 —— 独立成块，大号 serif，无 label */}
        <h1
          style={{
            fontFamily: "var(--font-serif)",
            fontSize: "26px",
            fontWeight: 600,
            lineHeight: 1.35,
            letterSpacing: "-0.01em",
            color: "var(--color-text-1)",
            margin: "0 0 8px",
          }}
        >
          {draft.title}
        </h1>

        {/* 标题下的细分隔线 —— 编辑部气质的语言，不用 "正文" 文字 label */}
        <div
          aria-hidden
          style={{
            width: "40px",
            height: "2px",
            background: "var(--color-accent)",
            borderRadius: "2px",
            marginBottom: "26px",
            opacity: 0.7,
          }}
        />

        {/* 正文 —— 直接跑 MarkdownBody，周围没任何包裹，靠排版自身撑秩序 */}
        <MarkdownBody density="full">{draft.fullBody}</MarkdownBody>
      </article>
    ),
  };
}

/**
 * 从 tool.request 里挖出 agent 写入的 markdown 正文。
 * 覆盖 write_project / write_content / request_human_review / write_wiki 这四种。
 */
function extractMarkdownPayload(request: unknown): string | null {
  if (!request || typeof request !== "object") return null;
  const r = request as Record<string, unknown>;

  const candidates: unknown[] = [
    r.content,
    r.value,
    r.brief_analysis,
    r.strategy,
    r.review_summary,
    r.delivery,
  ];

  for (const c of candidates) {
    if (typeof c === "string" && c.length >= 60 && isMarkdownish(c)) {
      return c;
    }
  }
  return null;
}

function isMarkdownish(s: string): boolean {
  return (
    /^\s*#{1,6}\s/m.test(s) ||
    /\n\s*-\s+/.test(s) ||
    /\*\*[^*]+\*\*/.test(s) ||
    /\n\s*\d+\.\s+/.test(s)
  );
}

function DrawerSection({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="mb-5">
      <div className="font-mono text-[10px] tracking-[0.1em] uppercase text-text-3 mb-2">
        {label}
      </div>
      {children}
    </div>
  );
}
